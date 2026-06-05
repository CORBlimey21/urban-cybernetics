"""Minimal loading engine for packet lifecycle invariant tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from urban_cybernetics.core import DemandDeclaration, Event, EventType, LifecycleState, Link, Packet


class EventCacheConsistencyError(RuntimeError):
    """Raised when materialised packet state disagrees with engine-owned events."""


class LoadingEngine:
    """Owns physical truth, lifecycle events, and derived simulation state."""

    def __init__(self, links: dict[str, Link]) -> None:
        self.current_tick = 0
        self._event_log: list[Event] = []
        self._packets: dict[str, Packet] = {}
        self.links = dict(links)
        self._next_packet_number = 1
        self._current_link_entry_ticks: dict[str, int] = {}
        self._current_link_ids: dict[str, str] = {}

    @property
    def event_log(self) -> tuple[Event, ...]:
        """Read-only view of the engine-owned event log."""

        return tuple(self._event_log)

    @property
    def packets(self) -> Mapping[str, Packet]:
        """Read-only view of materialised packet records."""

        return MappingProxyType(self._packets)

    def append_event(self, packet_id: str, event_type: EventType, entity_id: str) -> Event:
        """Append a loading-engine-owned lifecycle event."""

        event = Event(
            sequence_number=len(self._event_log),
            packet_id=packet_id,
            event_type=event_type,
            entity_id=entity_id,
            physical_tick=self.current_tick,
        )
        self._event_log.append(event)
        return event

    def instantiate(self, demand: DemandDeclaration) -> Packet:
        """Instantiate one packet from one demand declaration."""

        if len(demand.route_intent) != 1:
            raise ValueError("minimal loading engine supports exactly one-link route intents")

        link_id = demand.route_intent[0]
        if link_id not in self.links:
            raise KeyError(f"unknown link_id in route_intent: {link_id}")

        packet_id = f"P{self._next_packet_number}"
        self._next_packet_number += 1
        packet = Packet(
            packet_id=packet_id,
            demand_id=demand.demand_id,
            route_intent=demand.route_intent,
            lifecycle_state=LifecycleState.IN_TRANSIT,
        )
        self._packets[packet_id] = packet
        self._current_link_ids[packet_id] = link_id
        self._current_link_entry_ticks[packet_id] = self.current_tick
        self.append_event(packet_id, EventType.INSTANTIATED, link_id)
        self.append_event(packet_id, EventType.LINK_ENTRY, link_id)
        return packet

    def step(self) -> None:
        """Advance the loading engine by exactly one deterministic tick."""

        self.current_tick += 1
        active_packet_ids = sorted(
            packet_id
            for packet_id, packet in self._packets.items()
            if packet.lifecycle_state == LifecycleState.IN_TRANSIT
        )

        for packet_id in active_packet_ids:
            link_id = self._current_link_ids[packet_id]
            link = self.links[link_id]
            entry_tick = self._current_link_entry_ticks[packet_id]
            if self.current_tick - entry_tick < link.free_flow_ticks:
                continue

            self.append_event(packet_id, EventType.LINK_EXIT, link_id)
            self.append_event(packet_id, EventType.COMPLETED, link_id)
            self._packets[packet_id] = replace(
                self._packets[packet_id],
                lifecycle_state=LifecycleState.COMPLETED,
            )
            del self._current_link_ids[packet_id]
            del self._current_link_entry_ticks[packet_id]

    def _lifecycle_states_implied_by_events(self) -> dict[str, LifecycleState]:
        """Derive final packet lifecycle states from the primary event log."""

        instantiated_packet_ids: set[str] = set()
        lifecycle_states: dict[str, LifecycleState] = {}

        for expected_sequence_number, event in enumerate(self._event_log):
            if event.sequence_number != expected_sequence_number:
                raise EventCacheConsistencyError(
                    f"event sequence_number {event.sequence_number} does not match "
                    f"append order {expected_sequence_number}"
                )

            if event.packet_id not in self._packets:
                raise EventCacheConsistencyError(
                    f"event references unknown packet_id {event.packet_id}"
                )

            if event.event_type == EventType.INSTANTIATED:
                if event.packet_id in instantiated_packet_ids:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} has multiple instantiation events"
                    )
                instantiated_packet_ids.add(event.packet_id)
                lifecycle_states[event.packet_id] = LifecycleState.IN_TRANSIT
                continue

            if event.packet_id not in instantiated_packet_ids:
                raise EventCacheConsistencyError(
                    f"event {event.event_type.name} references packet_id {event.packet_id} "
                    "before instantiation"
                )

            if event.event_type == EventType.COMPLETED:
                lifecycle_states[event.packet_id] = LifecycleState.COMPLETED
            elif event.event_type == EventType.CANCELLED:
                lifecycle_states[event.packet_id] = LifecycleState.CANCELLED

        for packet_id in self._packets:
            if packet_id not in instantiated_packet_ids:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} exists without an instantiation event"
                )

        return lifecycle_states

    def check_event_cache_consistency(self) -> bool:
        """Verify that materialised packet records match engine-owned events."""

        lifecycle_states = self._lifecycle_states_implied_by_events()
        for packet_id, event_state in lifecycle_states.items():
            packet_state = self._packets[packet_id].lifecycle_state
            if packet_state != event_state:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} lifecycle cache is {packet_state.name}, "
                    f"but event log implies {event_state.name}"
                )
        return True

    def conservation_summary(self) -> dict[str, int]:
        """Compute the simplified conservation ledger from the primary event log."""

        self.check_event_cache_consistency()
        lifecycle_states = self._lifecycle_states_implied_by_events()
        instantiated = len(lifecycle_states)
        completed = sum(
            state == LifecycleState.COMPLETED for state in lifecycle_states.values()
        )
        cancelled = sum(
            state == LifecycleState.CANCELLED for state in lifecycle_states.values()
        )
        in_flight = sum(
            state == LifecycleState.IN_TRANSIT for state in lifecycle_states.values()
        )
        return {
            "instantiated": instantiated,
            "in_flight": in_flight,
            "completed": completed,
            "cancelled": cancelled,
        }

    def check_conservation(self) -> bool:
        """Verify simplified whole-network conservation."""

        summary = self.conservation_summary()
        return summary["instantiated"] == (
            summary["in_flight"] + summary["completed"] + summary["cancelled"]
        )
