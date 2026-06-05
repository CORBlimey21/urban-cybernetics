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
        self._packet_instantiation_orders: dict[str, int] = {}
        self._route_positions: dict[str, int] = {}
        self._current_link_entry_ticks: dict[str, int] = {}
        self._current_link_ids: dict[str, str] = {}
        self._queues: dict[str, list[str]] = {}
        self._receiving_open_by_link: dict[str, bool] = {
            link_id: True for link_id in self.links
        }

    @property
    def event_log(self) -> tuple[Event, ...]:
        """Read-only view of the engine-owned event log."""

        return tuple(self._event_log)

    @property
    def packets(self) -> Mapping[str, Packet]:
        """Read-only view of materialised packet records."""

        return MappingProxyType(self._packets)

    def set_receiving_open(self, link_id: str, is_open: bool) -> None:
        """Set engine-owned receiving state for a link."""

        if link_id not in self.links:
            raise KeyError(f"unknown link_id for receiving state: {link_id}")
        self._receiving_open_by_link[link_id] = is_open

    def is_receiving_open(self, link_id: str) -> bool:
        """Return engine-owned receiving state for a link."""

        if link_id not in self.links:
            raise KeyError(f"unknown link_id for receiving state: {link_id}")
        return self._receiving_open_by_link.get(link_id, True)

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

        if not 1 <= len(demand.route_intent) <= 2:
            raise ValueError("minimal loading engine supports one-link and two-link route intents")

        for link_id in demand.route_intent:
            if link_id not in self.links:
                raise KeyError(f"unknown link_id in route_intent: {link_id}")

        first_link_id = demand.route_intent[0]
        packet_number = self._next_packet_number
        packet_id = f"P{packet_number}"
        self._next_packet_number += 1
        packet = Packet(
            packet_id=packet_id,
            demand_id=demand.demand_id,
            route_intent=demand.route_intent,
            lifecycle_state=LifecycleState.IN_TRANSIT,
        )
        self._packets[packet_id] = packet
        self._packet_instantiation_orders[packet_id] = packet_number
        self._route_positions[packet_id] = 0
        self._current_link_ids[packet_id] = first_link_id
        self._current_link_entry_ticks[packet_id] = self.current_tick
        self.append_event(packet_id, EventType.INSTANTIATED, first_link_id)
        self.append_event(packet_id, EventType.LINK_ENTRY, first_link_id)
        return packet

    def step(self) -> None:
        """Advance the loading engine by exactly one deterministic tick."""

        self.check_event_cache_consistency()
        self.current_tick += 1
        receiving_slots = self._receiving_slots_by_link()
        released_packet_ids = self._release_queued_packets(receiving_slots)

        for packet_id in self._in_transit_packet_ids(excluding=released_packet_ids):
            link_id = self._current_link_ids[packet_id]
            link = self.links[link_id]
            entry_tick = self._current_link_entry_ticks[packet_id]
            if self.current_tick - entry_tick < link.free_flow_ticks:
                continue

            next_link_id = self._next_link_id(packet_id)
            if next_link_id is None:
                self._complete_packet(packet_id, link_id)
                continue

            self._attempt_node_transfer(packet_id, link_id, next_link_id, receiving_slots)

    @staticmethod
    def _boundary_id(upstream_link_id: str, downstream_link_id: str) -> str:
        return f"boundary:{upstream_link_id}->{downstream_link_id}"

    @staticmethod
    def _parse_boundary_id(boundary_id: str) -> tuple[str, str]:
        boundary = boundary_id.removeprefix("boundary:")
        upstream_link_id, downstream_link_id = boundary.split("->", 1)
        return upstream_link_id, downstream_link_id

    def _receiving_slots_by_link(self) -> dict[str, int]:
        return {
            link_id: (
                link.declared_receiving_capacity_per_tick
                if self.is_receiving_open(link_id)
                else 0
            )
            for link_id, link in self.links.items()
        }

    def _in_transit_packet_ids(self, excluding: set[str] | None = None) -> list[str]:
        excluded_packet_ids = excluding or set()
        return sorted(
            (
                packet_id
                for packet_id, packet in self._packets.items()
                if packet.lifecycle_state == LifecycleState.IN_TRANSIT
                and packet_id not in excluded_packet_ids
            ),
            key=self._packet_fifo_key,
        )

    def _packet_fifo_key(self, packet_id: str) -> tuple[int, int]:
        return (
            self._current_link_entry_ticks[packet_id],
            self._packet_instantiation_orders[packet_id],
        )

    def _next_link_id(self, packet_id: str) -> str | None:
        route_position = self._route_positions[packet_id]
        route_intent = self._packets[packet_id].route_intent
        next_position = route_position + 1
        if next_position >= len(route_intent):
            return None
        return route_intent[next_position]

    def _set_lifecycle_state(self, packet_id: str, lifecycle_state: LifecycleState) -> None:
        self._packets[packet_id] = replace(
            self._packets[packet_id],
            lifecycle_state=lifecycle_state,
        )

    def _queue_packet(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        boundary_id = self._boundary_id(upstream_link_id, downstream_link_id)
        self.append_event(packet_id, EventType.QUEUE_ENTRY, boundary_id)
        self._queues.setdefault(boundary_id, []).append(packet_id)
        self._set_lifecycle_state(packet_id, LifecycleState.QUEUED)

    def _queue_packet_once(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        boundary_id = self._boundary_id(upstream_link_id, downstream_link_id)
        if packet_id in self._queues.get(boundary_id, ()):
            return
        self._queue_packet(packet_id, upstream_link_id, downstream_link_id)

    def _release_queued_packets(self, receiving_slots: dict[str, int]) -> set[str]:
        released_packet_ids: set[str] = set()
        for boundary_id in sorted(self._queues):
            upstream_link_id, downstream_link_id = self._parse_boundary_id(boundary_id)
            queue = self._queues[boundary_id]
            while queue and receiving_slots[downstream_link_id] > 0:
                packet_id = queue[0]
                if not self._attempt_node_transfer(
                    packet_id,
                    upstream_link_id,
                    downstream_link_id,
                    receiving_slots,
                    queued=True,
                ):
                    break
                released_packet_ids.add(packet_id)
        return released_packet_ids

    def _attempt_node_transfer(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
        receiving_slots: dict[str, int],
        *,
        queued: bool = False,
    ) -> bool:
        """Move a packet from one link to the next if downstream receiving permits it."""

        boundary_id = self._boundary_id(upstream_link_id, downstream_link_id)
        if receiving_slots[downstream_link_id] <= 0:
            if not queued:
                self._queue_packet_once(packet_id, upstream_link_id, downstream_link_id)
            return False

        if not queued and self._queues.get(boundary_id):
            self._queue_packet_once(packet_id, upstream_link_id, downstream_link_id)
            return False

        receiving_slots[downstream_link_id] -= 1
        if queued:
            queue = self._queues[boundary_id]
            if not queue or queue[0] != packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} is not first in queue {boundary_id}"
                )
            queue.pop(0)
            self.append_event(packet_id, EventType.QUEUE_EXIT, boundary_id)

        self._transfer_packet_between_links(packet_id, upstream_link_id, downstream_link_id)
        return True

    def _transfer_packet_between_links(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        self.append_event(packet_id, EventType.LINK_EXIT, upstream_link_id)
        self.append_event(packet_id, EventType.LINK_ENTRY, downstream_link_id)
        self._route_positions[packet_id] += 1
        self._current_link_ids[packet_id] = downstream_link_id
        self._current_link_entry_ticks[packet_id] = self.current_tick
        self._set_lifecycle_state(packet_id, LifecycleState.IN_TRANSIT)

    def _complete_packet(self, packet_id: str, link_id: str) -> None:
        self.append_event(packet_id, EventType.LINK_EXIT, link_id)
        self.append_event(packet_id, EventType.COMPLETED, link_id)
        self._set_lifecycle_state(packet_id, LifecycleState.COMPLETED)
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

            if event.event_type == EventType.LINK_ENTRY:
                lifecycle_states[event.packet_id] = LifecycleState.IN_TRANSIT
            elif event.event_type == EventType.QUEUE_ENTRY:
                lifecycle_states[event.packet_id] = LifecycleState.QUEUED
            elif event.event_type == EventType.QUEUE_EXIT:
                lifecycle_states[event.packet_id] = LifecycleState.IN_TRANSIT
            elif event.event_type == EventType.COMPLETED:
                lifecycle_states[event.packet_id] = LifecycleState.COMPLETED
            elif event.event_type == EventType.CANCELLED:
                lifecycle_states[event.packet_id] = LifecycleState.CANCELLED

        for packet_id in self._packets:
            if packet_id not in instantiated_packet_ids:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} exists without an instantiation event"
                )

        return lifecycle_states

    def _queue_packet_ids_by_boundary_from_events(self) -> dict[str, tuple[str, ...]]:
        """Derive boundary queue membership from queue events."""

        queues: dict[str, list[str]] = {}
        for event in self._event_log:
            if event.event_type == EventType.QUEUE_ENTRY:
                queues.setdefault(event.entity_id, []).append(event.packet_id)
            elif event.event_type == EventType.QUEUE_EXIT:
                queue = queues.setdefault(event.entity_id, [])
                if not queue or queue[0] != event.packet_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} exits queue {event.entity_id} "
                        "out of FIFO order or without queue entry"
                    )
                queue.pop(0)
        return {
            boundary_id: tuple(packet_ids)
            for boundary_id, packet_ids in queues.items()
        }

    def _packet_link_ids_implied_by_events(self) -> dict[str, str]:
        """Derive each active packet's current link from link boundary events."""

        packet_link_ids: dict[str, str] = {}
        for event in self._event_log:
            if event.event_type == EventType.LINK_ENTRY:
                packet_link_ids[event.packet_id] = event.entity_id
            elif event.event_type == EventType.LINK_EXIT:
                if packet_link_ids.get(event.packet_id) != event.entity_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} exits link {event.entity_id} "
                        "without being recorded on that link"
                    )
                del packet_link_ids[event.packet_id]
        return packet_link_ids

    def packet_ids_on_link(self, link_id: str) -> tuple[str, ...]:
        """Return packet IDs physically on a link, derived from event history."""

        link_packet_ids: dict[str, list[str]] = {}
        packet_link_ids: dict[str, str] = {}
        for event in self._event_log:
            if event.event_type == EventType.LINK_ENTRY:
                packet_link_ids[event.packet_id] = event.entity_id
                link_packet_ids.setdefault(event.entity_id, []).append(event.packet_id)
            elif event.event_type == EventType.LINK_EXIT:
                if packet_link_ids.get(event.packet_id) != event.entity_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} exits link {event.entity_id} "
                        "without being recorded on that link"
                    )
                packet_link_ids.pop(event.packet_id)
                link_packet_ids[event.entity_id].remove(event.packet_id)
        return tuple(link_packet_ids.get(link_id, ()))

    def packet_ids_in_queue(
        self,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> tuple[str, ...]:
        """Return packet IDs queued at a boundary, derived from event history."""

        boundary_id = self._boundary_id(upstream_link_id, downstream_link_id)
        return self._queue_packet_ids_by_boundary_from_events().get(boundary_id, ())

    def check_event_cache_consistency(self) -> bool:
        """Verify that materialised packet records match engine-owned events."""

        for link_id in self._receiving_open_by_link:
            if link_id not in self.links:
                raise EventCacheConsistencyError(
                    f"receiving state references unknown link_id {link_id}"
                )
        lifecycle_states = self._lifecycle_states_implied_by_events()
        packet_link_ids = self._packet_link_ids_implied_by_events()
        for packet_id, event_state in lifecycle_states.items():
            packet_state = self._packets[packet_id].lifecycle_state
            if packet_state != event_state:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} lifecycle cache is {packet_state.name}, "
                    f"but event log implies {event_state.name}"
                )
            if event_state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED):
                event_link_id = packet_link_ids.get(packet_id)
                cache_link_id = self._current_link_ids.get(packet_id)
                if cache_link_id != event_link_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {packet_id} link cache is {cache_link_id}, "
                        f"but event log implies {event_link_id}"
                    )
            elif packet_id in self._current_link_ids:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} has terminal lifecycle state "
                    f"{event_state.name} but remains in link cache"
                )
        event_queues = self._queue_packet_ids_by_boundary_from_events()
        for boundary_id in set(event_queues) | set(self._queues):
            cache_queue = tuple(self._queues.get(boundary_id, ()))
            event_queue = event_queues.get(boundary_id, ())
            if cache_queue != event_queue:
                raise EventCacheConsistencyError(
                    f"queue cache for {boundary_id} is {cache_queue}, "
                    f"but event log implies {event_queue}"
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
            state in (LifecycleState.IN_TRANSIT, LifecycleState.QUEUED)
            for state in lifecycle_states.values()
        )
        unresolved = 0
        return {
            "instantiated": instantiated,
            "in_flight": in_flight,
            "completed": completed,
            "cancelled": cancelled,
            "unresolved": unresolved,
        }

    def check_conservation(self) -> bool:
        """Verify simplified whole-network conservation."""

        summary = self.conservation_summary()
        return summary["instantiated"] == (
            summary["in_flight"]
            + summary["completed"]
            + summary["cancelled"]
            + summary["unresolved"]
        )
