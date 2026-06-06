"""Minimal loading engine for packet lifecycle invariant tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    LifecycleState,
    Link,
    Node,
    Packet,
)
from urban_cybernetics.loading.cumulative_counts import (
    CumulativeBoundaryCounts,
    LinkStorageView,
    cumulative_count_series,
    cumulative_counts,
    cumulative_entries,
    cumulative_exits,
    link_storage,
    link_storage_series,
)
from urban_cybernetics.loading.receiving import LinkReceivingView, link_receiving_view
from urban_cybernetics.loading.sending import LinkSendingView, link_sending_view
from urban_cybernetics.loading.transfer_policy import (
    GlobalFIFOMergePolicy,
    NodeTransferPolicy,
    TransferCandidate,
)


class EventCacheConsistencyError(RuntimeError):
    """Raised when materialised packet state disagrees with engine-owned events."""


class LoadingEngine:
    """Owns physical truth, lifecycle events, and derived simulation state."""

    def __init__(
        self,
        links: dict[str, Link],
        nodes: tuple[Node, ...] | None = None,
        node_transfer_policy: NodeTransferPolicy | None = None,
    ) -> None:
        self.current_tick = 0
        self._event_log: list[Event] = []
        self._packets: dict[str, Packet] = {}
        self.links = dict(links)
        self.nodes = {node.node_id: node for node in nodes or ()}
        self.node_transfer_policy = node_transfer_policy or GlobalFIFOMergePolicy()
        self._node_by_incoming_link_id: dict[str, Node] = {}
        self._next_packet_number = 1
        self._packet_instantiation_orders: dict[str, int] = {}
        self._packet_route_index: dict[str, int] = {}
        self._current_link_entry_ticks: dict[str, int] = {}
        self._current_link_ids: dict[str, str] = {}
        self._queues: dict[str, list[str]] = {}
        self._receiving_open_by_link: dict[str, bool] = {
            link_id: True for link_id in self.links
        }
        self._validate_nodes(nodes or ())

    @property
    def event_log(self) -> tuple[Event, ...]:
        """Read-only view of the engine-owned event log."""

        return tuple(self._event_log)

    @property
    def packets(self) -> Mapping[str, Packet]:
        """Read-only view of materialised packet records."""

        return MappingProxyType(self._packets)

    def _validate_nodes(self, nodes: tuple[Node, ...]) -> None:
        node_ids: set[str] = set()
        for node in nodes:
            if node.node_id in node_ids:
                raise ValueError(f"duplicate node_id: {node.node_id}")
            node_ids.add(node.node_id)
            for link_id in node.incoming_link_ids + node.outgoing_link_ids:
                if link_id not in self.links:
                    raise KeyError(
                        f"node {node.node_id} references unknown link_id: {link_id}"
                    )
            for incoming_link_id in node.incoming_link_ids:
                if incoming_link_id in self._node_by_incoming_link_id:
                    raise ValueError(
                        f"incoming link {incoming_link_id} belongs to multiple nodes"
                    )
                self._node_by_incoming_link_id[incoming_link_id] = node

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

    def cumulative_entries(self, link_id: str, tick: int | None = None) -> int:
        """Return event-derived cumulative LINK_ENTRY count for one link."""

        self._validate_count_link_id(link_id)
        return cumulative_entries(
            self.event_log,
            link_id,
            self.current_tick if tick is None else tick,
        )

    def cumulative_exits(self, link_id: str, tick: int | None = None) -> int:
        """Return event-derived cumulative LINK_EXIT count for one link."""

        self._validate_count_link_id(link_id)
        return cumulative_exits(
            self.event_log,
            link_id,
            self.current_tick if tick is None else tick,
        )

    def cumulative_counts(
        self,
        link_id: str,
        tick: int | None = None,
    ) -> CumulativeBoundaryCounts:
        """Return event-derived cumulative entries and exits for one link."""

        self._validate_count_link_id(link_id)
        return cumulative_counts(
            self.event_log,
            link_id,
            self.current_tick if tick is None else tick,
        )

    def cumulative_count_series(
        self,
        link_id: str,
        max_tick: int | None = None,
    ) -> tuple[CumulativeBoundaryCounts, ...]:
        """Return event-derived cumulative counts from tick 0 through max_tick."""

        self._validate_count_link_id(link_id)
        return cumulative_count_series(
            self.event_log,
            link_id,
            self.current_tick if max_tick is None else max_tick,
        )

    def link_storage(
        self,
        link_id: str,
        tick: int | None = None,
    ) -> LinkStorageView:
        """Return count-derived packet storage for one link."""

        self._validate_count_link_id(link_id)
        return link_storage(
            self.event_log,
            link_id,
            self.current_tick if tick is None else tick,
        )

    def link_storage_series(
        self,
        link_id: str,
        max_tick: int | None = None,
    ) -> tuple[LinkStorageView, ...]:
        """Return count-derived link storage from tick 0 through max_tick."""

        self._validate_count_link_id(link_id)
        return link_storage_series(
            self.event_log,
            link_id,
            self.current_tick if max_tick is None else max_tick,
        )

    def link_sending_view(
        self,
        link_id: str,
        tick: int | None = None,
    ) -> LinkSendingView:
        """Return event-derived upstream sending supply for one link."""

        self._validate_count_link_id(link_id)
        view_tick = self.current_tick if tick is None else tick
        return link_sending_view(
            self.event_log,
            self.links[link_id],
            view_tick,
            excluded_packet_ids=self._queued_packet_ids_on_upstream_link(
                link_id,
                view_tick,
            ),
        )

    def link_receiving_view(
        self,
        link_id: str,
        tick: int | None = None,
        already_accepted_count: int = 0,
    ) -> LinkReceivingView:
        """Return event-derived downstream receiving availability for one link."""

        self._validate_count_link_id(link_id)
        view_tick = self.current_tick if tick is None else tick
        return link_receiving_view(
            self.event_log,
            self.links[link_id],
            view_tick,
            self.is_receiving_open(link_id),
            already_accepted_count=already_accepted_count,
        )

    def _validate_count_link_id(self, link_id: str) -> None:
        if link_id not in self.links:
            raise KeyError(f"unknown link_id for cumulative counts: {link_id}")

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

        if len(demand.route_intent) < 1:
            raise ValueError("route_intent must contain at least one link_id")

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
        self._packet_route_index[packet_id] = 0
        self._current_link_ids[packet_id] = first_link_id
        self._current_link_entry_ticks[packet_id] = self.current_tick
        self.append_event(packet_id, EventType.INSTANTIATED, first_link_id)
        self.append_event(packet_id, EventType.LINK_ENTRY, first_link_id)
        return packet

    def step(self) -> None:
        """Advance the loading engine by exactly one deterministic tick."""

        self.check_event_cache_consistency()
        self.current_tick += 1
        completed_counts_by_link = self._complete_eligible_packets()

        candidates = self._transfer_candidates(completed_counts_by_link)
        receiving_slots = self._receiving_slots_by_link()
        approved_candidates = self.node_transfer_policy.choose_transfers(
            candidates=candidates,
            receiving_slots_by_downstream_link=MappingProxyType(dict(receiving_slots)),
            packet_ids_by_upstream_link=MappingProxyType(
                self._packet_ids_by_upstream_link_for_candidates(candidates)
            ),
            queued_downstream_by_packet_id=MappingProxyType(
                self._queued_downstream_by_packet_id_from_events()
            ),
        )
        approved_candidate_set, remaining_slots = self._execute_approved_transfers(
            approved_candidates,
            candidates,
            receiving_slots,
        )
        self._queue_non_approved_candidates(
            candidates,
            approved_candidate_set,
            remaining_slots,
        )

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
            link_id: self.link_receiving_view(
                link_id,
                self.current_tick,
            ).available_receiving_slots
            for link_id in self.links
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
        route_position = self._packet_route_index[packet_id]
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

    def _complete_eligible_packets(self) -> dict[str, int]:
        completed_counts_by_link: dict[str, int] = {}
        for link_id in sorted(self.links):
            sending_view = link_sending_view(
                self.event_log,
                self.links[link_id],
                self.current_tick,
                excluded_packet_ids=self._queued_packet_ids_on_upstream_link(
                    link_id,
                    self.current_tick,
                ),
            )
            for packet_id in sending_view.sendable_packet_ids:
                if self._next_link_id(packet_id) is None:
                    self._complete_packet(packet_id, link_id)
                    completed_counts_by_link[link_id] = (
                        completed_counts_by_link.get(link_id, 0) + 1
                    )
        return completed_counts_by_link

    def _transfer_candidates(
        self,
        consumed_sending_slots_by_link: dict[str, int] | None = None,
    ) -> tuple[TransferCandidate, ...]:
        candidates = [
            *self._queued_transfer_candidates(),
            *self._active_transfer_candidates(consumed_sending_slots_by_link or {}),
        ]
        return tuple(candidates)

    def _queued_transfer_candidates(self) -> list[TransferCandidate]:
        queue_entry_metadata = self._queue_entry_metadata_by_packet_id_from_events()
        candidates: list[TransferCandidate] = []
        for boundary_id in sorted(self._queues):
            upstream_link_id, downstream_link_id = self._parse_boundary_id(boundary_id)
            self._validate_transfer_connectivity(upstream_link_id, downstream_link_id)
            for packet_id in self._queues[boundary_id]:
                eligibility_tick, eligibility_sequence_number = queue_entry_metadata[
                    packet_id
                ]
                candidates.append(
                    TransferCandidate(
                        packet_id=packet_id,
                        upstream_link_id=upstream_link_id,
                        downstream_link_id=downstream_link_id,
                        boundary_id=boundary_id,
                        eligibility_tick=eligibility_tick,
                        eligibility_sequence_number=eligibility_sequence_number,
                        queued=True,
                    )
                )
        return candidates

    def _active_transfer_candidates(
        self,
        consumed_sending_slots_by_link: dict[str, int],
    ) -> list[TransferCandidate]:
        link_entry_metadata = self._current_link_entry_metadata_by_packet_id_from_events()
        queued_packet_ids = set(self._queued_downstream_by_packet_id_from_events())
        candidates: list[TransferCandidate] = []
        for upstream_link_id in sorted(self.links):
            link = self.links[upstream_link_id]
            sending_view = link_sending_view(
                self.event_log,
                link,
                self.current_tick,
                excluded_packet_ids=queued_packet_ids,
            )
            consumed_slots = consumed_sending_slots_by_link.get(upstream_link_id, 0)
            remaining_sending_capacity = max(
                link.declared_sending_capacity_per_tick - consumed_slots,
                0,
            )
            for packet_id in sending_view.eligible_packet_ids[:remaining_sending_capacity]:
                entry_link_id, entry_tick, entry_sequence_number = (
                    link_entry_metadata[packet_id]
                )
                if entry_link_id != upstream_link_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {packet_id} link-entry event implies "
                        f"{entry_link_id}, but sending view implies {upstream_link_id}"
                    )

                downstream_link_id = self._next_link_id(packet_id)
                if downstream_link_id is None:
                    continue

                self._validate_transfer_connectivity(upstream_link_id, downstream_link_id)
                candidates.append(
                    TransferCandidate(
                        packet_id=packet_id,
                        upstream_link_id=upstream_link_id,
                        downstream_link_id=downstream_link_id,
                        boundary_id=self._boundary_id(
                            upstream_link_id,
                            downstream_link_id,
                        ),
                        eligibility_tick=entry_tick
                        + self.links[upstream_link_id].free_flow_ticks,
                        eligibility_sequence_number=entry_sequence_number,
                    )
                )
        return candidates

    def _packet_ids_by_upstream_link_for_candidates(
        self,
        candidates: tuple[TransferCandidate, ...],
    ) -> dict[str, tuple[str, ...]]:
        return {
            upstream_link_id: self.packet_ids_on_link(upstream_link_id)
            for upstream_link_id in sorted(
                {candidate.upstream_link_id for candidate in candidates}
            )
        }

    def _execute_approved_transfers(
        self,
        approved_candidates: tuple[TransferCandidate, ...],
        candidates: tuple[TransferCandidate, ...],
        receiving_slots: dict[str, int],
    ) -> tuple[set[TransferCandidate], dict[str, int]]:
        candidate_set = set(candidates)
        approved_candidate_set: set[TransferCandidate] = set()
        remaining_slots = dict(receiving_slots)

        for candidate in approved_candidates:
            if candidate not in candidate_set:
                raise EventCacheConsistencyError(
                    f"policy approved unknown transfer candidate {candidate}"
                )
            if candidate in approved_candidate_set:
                raise EventCacheConsistencyError(
                    f"policy approved duplicate transfer candidate {candidate}"
                )
            if remaining_slots.get(candidate.downstream_link_id, 0) <= 0:
                raise EventCacheConsistencyError(
                    "policy approved more transfers than downstream receiving slots "
                    f"for {candidate.downstream_link_id}"
                )

            self._execute_transfer_candidate(candidate)
            approved_candidate_set.add(candidate)
            remaining_slots[candidate.downstream_link_id] -= 1

        return approved_candidate_set, remaining_slots

    def _execute_transfer_candidate(self, candidate: TransferCandidate) -> None:
        if candidate.queued:
            queue = self._queues[candidate.boundary_id]
            if not queue or queue[0] != candidate.packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {candidate.packet_id} is not first in queue "
                    f"{candidate.boundary_id}"
                )
            queue.pop(0)
            self.append_event(
                candidate.packet_id,
                EventType.QUEUE_EXIT,
                candidate.boundary_id,
            )

        self._transfer_packet_between_links(
            candidate.packet_id,
            candidate.upstream_link_id,
            candidate.downstream_link_id,
        )

    def _queue_non_approved_candidates(
        self,
        candidates: tuple[TransferCandidate, ...],
        approved_candidate_set: set[TransferCandidate],
        remaining_slots: dict[str, int],
    ) -> None:
        for candidate in candidates:
            if candidate in approved_candidate_set or candidate.queued:
                continue
            if (
                remaining_slots.get(candidate.downstream_link_id, 0) <= 0
                or self._queues.get(candidate.boundary_id)
            ):
                self._queue_packet_once(
                    candidate.packet_id,
                    candidate.upstream_link_id,
                    candidate.downstream_link_id,
                )

    def _validate_transfer_connectivity(
        self,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        node = self._node_by_incoming_link_id.get(upstream_link_id)
        if node is None:
            return
        if downstream_link_id not in node.outgoing_link_ids:
            raise ValueError(
                f"link {downstream_link_id} is not an outgoing link from node {node.node_id}"
            )

    def _queued_downstream_by_packet_id_from_events(self) -> dict[str, str]:
        queued_downstream_by_packet_id: dict[str, str] = {}
        for boundary_id, packet_ids in self._queue_packet_ids_by_boundary_from_events().items():
            _, downstream_link_id = self._parse_boundary_id(boundary_id)
            for packet_id in packet_ids:
                queued_downstream_by_packet_id[packet_id] = downstream_link_id
        return queued_downstream_by_packet_id

    def _queued_packet_ids_on_upstream_link(
        self,
        link_id: str,
        tick: int,
    ) -> tuple[str, ...]:
        queued_packet_ids: list[str] = []
        for boundary_id, packet_ids in self._queue_packet_ids_by_boundary_from_events(
            tick
        ).items():
            upstream_link_id, _ = self._parse_boundary_id(boundary_id)
            if upstream_link_id == link_id:
                queued_packet_ids.extend(packet_ids)
        return tuple(queued_packet_ids)

    def _queue_entry_metadata_by_packet_id_from_events(self) -> dict[str, tuple[int, int]]:
        queues: dict[str, list[tuple[str, int, int]]] = {}
        queue_entry_metadata: dict[str, tuple[int, int]] = {}
        for event in self._event_log:
            if event.event_type == EventType.QUEUE_ENTRY:
                queues.setdefault(event.entity_id, []).append(
                    (event.packet_id, event.physical_tick, event.sequence_number)
                )
                queue_entry_metadata[event.packet_id] = (
                    event.physical_tick,
                    event.sequence_number,
                )
            elif event.event_type == EventType.QUEUE_EXIT:
                queue = queues.setdefault(event.entity_id, [])
                if not queue or queue[0][0] != event.packet_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} exits queue {event.entity_id} "
                        "out of FIFO order or without queue entry"
                    )
                queue.pop(0)
                queue_entry_metadata.pop(event.packet_id, None)
        return queue_entry_metadata

    def _current_link_entry_metadata_by_packet_id_from_events(
        self,
    ) -> dict[str, tuple[str, int, int]]:
        packet_link_entry_metadata: dict[str, tuple[str, int, int]] = {}
        for event in self._event_log:
            if event.event_type == EventType.LINK_ENTRY:
                packet_link_entry_metadata[event.packet_id] = (
                    event.entity_id,
                    event.physical_tick,
                    event.sequence_number,
                )
            elif event.event_type == EventType.LINK_EXIT:
                packet_link_entry_metadata.pop(event.packet_id, None)
        return packet_link_entry_metadata

    def _transfer_packet_between_links(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        self.append_event(packet_id, EventType.LINK_EXIT, upstream_link_id)
        self.append_event(packet_id, EventType.LINK_ENTRY, downstream_link_id)
        self._packet_route_index[packet_id] += 1
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

    def _queue_packet_ids_by_boundary_from_events(
        self,
        tick: int | None = None,
    ) -> dict[str, tuple[str, ...]]:
        """Derive boundary queue membership from queue events."""

        queues: dict[str, list[str]] = {}
        for event in self._event_log:
            if tick is not None and event.physical_tick > tick:
                continue
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

    def _route_indices_implied_by_events(self) -> dict[str, int]:
        """Derive each packet's latest route index from realised link-entry events."""

        route_entry_counts: dict[str, int] = {}
        route_indices: dict[str, int] = {}
        for event in self._event_log:
            if event.event_type != EventType.LINK_ENTRY:
                continue

            packet = self._packets[event.packet_id]
            next_route_index = route_entry_counts.get(event.packet_id, 0)
            if next_route_index >= len(packet.route_intent):
                raise EventCacheConsistencyError(
                    f"packet_id {event.packet_id} has more link-entry events than route links"
                )
            expected_link_id = packet.route_intent[next_route_index]
            if event.entity_id != expected_link_id:
                raise EventCacheConsistencyError(
                    f"packet_id {event.packet_id} entered link {event.entity_id}, "
                    f"but route index {next_route_index} expects {expected_link_id}"
                )
            route_indices[event.packet_id] = next_route_index
            route_entry_counts[event.packet_id] = next_route_index + 1
        return route_indices

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
        route_indices = self._route_indices_implied_by_events()
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
            event_route_index = route_indices.get(packet_id)
            cache_route_index = self._packet_route_index.get(packet_id)
            if cache_route_index != event_route_index:
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} route-index cache is {cache_route_index}, "
                    f"but event log implies {event_route_index}"
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
