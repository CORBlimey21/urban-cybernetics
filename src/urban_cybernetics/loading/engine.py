"""Minimal loading engine for packet lifecycle invariant tests."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import replace
from types import MappingProxyType

from urban_cybernetics.config import (
    ACADEMIC_LTM_PARITY_PROFILE_ID,
    DEFAULT_LOADING_PROFILE_ID,
    SUPPORTED_LOADING_PROFILE_IDS,
)
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
    CountConsistencyReport,
    CumulativeBoundaryCounts,
    CumulativeCountProjection,
    LinkStorageView,
    PacketBoundaryOrdinal,
    RouteCumulativeBoundaryCounts,
    RouteTravelTimeCurve,
    count_consistency_report,
    cumulative_count_projection,
    cumulative_count_series,
    cumulative_counts,
    cumulative_entries,
    cumulative_exits,
    link_storage,
    link_storage_series,
    packet_boundary_ordinals,
    route_cumulative_count_series,
    route_cumulative_counts,
    route_travel_time_curves,
)
from urban_cybernetics.loading.receiving import (
    LinkReceivingView,
    LinkSupplyView,
    ReceivingDecisionTrace,
    bounded_integer_receiving_capacity_carry,
    link_receiving_view,
    parity_link_supply_view,
    parity_supply_as_receiving_view,
    receiving_decision_trace,
)
from urban_cybernetics.loading.sending import (
    LinkSendingView,
    ParityLinkSendingTrace,
    bounded_integer_capacity_carry,
    link_sending_view,
    parity_link_sending_trace,
)
from urban_cybernetics.loading.transfer_policy import (
    GeneralMovementAllocator,
    GlobalFIFOMergePolicy,
    JunctionAllocationDecision,
    JunctionAllocationInput,
    MovementAllocator,
    NodeTransferTrace,
    NodeTransferPolicy,
    REJECTED_CONFLICT_RESOURCE_CAPACITY,
    REJECTED_DOWNSTREAM_SUPPLY,
    REJECTED_GOVERNANCE_CLOSED,
    REJECTED_LANE_GROUP_CAPACITY,
    REJECTED_SIGNAL_CLOSED,
    TransferRequest,
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
        model_profile_id: str = DEFAULT_LOADING_PROFILE_ID,
        parity_sending_capacity_vehicles_per_tick_by_link: Mapping[str, float]
        | None = None,
        parity_receiving_capacity_vehicles_per_tick_by_link: Mapping[str, float]
        | None = None,
    ) -> None:
        if model_profile_id not in SUPPORTED_LOADING_PROFILE_IDS:
            raise ValueError(f"unsupported loading profile: {model_profile_id}")
        self.current_tick = 0
        self._event_log: list[Event] = []
        self._packets: dict[str, Packet] = {}
        self.links = dict(links)
        node_tuple = nodes or ()
        self.nodes = {node.node_id: node for node in node_tuple}
        self.model_profile_id = model_profile_id
        self.movement_allocator = node_transfer_policy or self._default_node_policy(node_tuple)
        self.node_transfer_policy = self.movement_allocator
        self._node_by_incoming_link_id: dict[str, Node] = {}
        self._next_packet_number = 1
        self._pending_demands: list[DemandDeclaration] = []
        self._pending_demand_ids: set[str] = set()
        self._instantiated_demand_ids: set[str] = set()
        self._packet_instantiation_orders: dict[str, int] = {}
        self._packet_route_index: dict[str, int] = {}
        self._current_link_entry_ticks: dict[str, int] = {}
        self._current_link_ids: dict[str, str] = {}
        self._current_link_storage_by_link_id: dict[str, int] = {
            link_id: 0 for link_id in self.links
        }
        self._packet_ids_by_link_id: dict[str, list[str]] = {
            link_id: [] for link_id in self.links
        }
        self._current_link_entry_metadata_by_packet_id: dict[str, tuple[str, int, int]] = {}
        self._completed_packet_ids: set[str] = set()
        self._cancelled_packet_ids: set[str] = set()
        self._queues: dict[str, deque[str]] = {}
        self._queue_entry_metadata_by_packet_id: dict[str, tuple[int, int]] = {}
        self._queued_downstream_by_packet_id: dict[str, str] = {}
        self._queued_packet_ids_by_upstream_link: dict[str, deque[str]] = {}
        self._same_tick_link_entries_by_link_id: dict[str, int] = {
            link_id: 0 for link_id in self.links
        }
        self._parity_sending_capacity_rate_by_link_id = (
            self._normalise_parity_sending_capacity_rates(
                parity_sending_capacity_vehicles_per_tick_by_link
            )
        )
        self._parity_sending_capacity_carry_by_link_id: dict[str, float] = {
            link_id: 0.0 for link_id in self.links
        }
        self._parity_sending_capacity_carry_in_by_link_id: dict[str, float] = {
            link_id: 0.0 for link_id in self.links
        }
        self._parity_sending_integer_capacity_by_link_id: dict[str, int] = {
            link_id: self.links[link_id].declared_sending_capacity_per_tick
            for link_id in self.links
        }
        self._parity_receiving_capacity_rate_by_link_id = (
            self._normalise_parity_receiving_capacity_rates(
                parity_receiving_capacity_vehicles_per_tick_by_link
            )
        )
        self._parity_receiving_capacity_carry_by_link_id: dict[str, float] = {
            link_id: 0.0 for link_id in self.links
        }
        self._parity_receiving_capacity_carry_in_by_link_id: dict[str, float] = {
            link_id: 0.0 for link_id in self.links
        }
        self._parity_receiving_integer_capacity_by_link_id: dict[str, int] = {
            link_id: self.links[link_id].declared_receiving_capacity_per_tick
            for link_id in self.links
        }
        self._receiving_open_by_link: dict[str, bool] = {
            link_id: True for link_id in self.links
        }
        self._closed_movement_ids_by_node_id: dict[str, set[str]] = {}
        self._open_signal_group_ids: set[str] = set()
        self._conflict_resource_capacity_by_node_id: dict[str, dict[str, int]] = {}
        self._lane_group_capacity_by_node_id: dict[str, dict[str, int]] = {}
        self._last_rejected_transfer_reason_by_candidate: dict[TransferRequest, str] = {}
        self._validate_nodes(node_tuple)

    @property
    def event_log(self) -> tuple[Event, ...]:
        """Read-only view of the engine-owned event log."""

        return tuple(self._event_log)

    @property
    def packets(self) -> Mapping[str, Packet]:
        """Read-only view of materialised packet records."""

        return MappingProxyType(self._packets)

    @property
    def pending_demands(self) -> tuple[DemandDeclaration, ...]:
        """Demand declarations waiting for origin storage before instantiation."""

        return tuple(self._pending_demands)

    @property
    def completed_packet_ids(self) -> frozenset[str]:
        """Current completed packet IDs from engine-owned materialised events."""

        return frozenset(self._completed_packet_ids)

    def node_transfer_traces(self) -> tuple[NodeTransferTrace, ...]:
        """Return read-only traces from the most recent movement allocation."""

        return tuple(
            getattr(
                self.movement_allocator,
                "last_allocation_traces",
                getattr(self.movement_allocator, "last_transfer_traces", ()),
            )
        )

    def allocation_traces(self) -> tuple[NodeTransferTrace, ...]:
        """Return read-only traces from the most recent movement allocation."""

        return self.node_transfer_traces()

    @property
    def movement_allocator_id(self) -> str:
        """Stable allocator identity for provenance records."""

        return str(
            getattr(
                self.movement_allocator,
                "allocator_id",
                type(self.movement_allocator).__name__,
            )
        )

    @property
    def movement_spec_hash(self) -> str:
        """Deterministic fingerprint of static movement specs consumed by loading."""

        payload = {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "incoming_link_ids": list(node.incoming_link_ids),
                    "outgoing_link_ids": list(node.outgoing_link_ids),
                    "movement_specs": [
                        {
                            "movement_id": movement.movement_id,
                            "upstream_link_id": movement.upstream_link_id,
                            "downstream_link_id": movement.downstream_link_id,
                            "priority_weight": movement.priority_weight,
                            "lane_group_ids": list(movement.lane_group_ids),
                            "conflict_resource_ids": list(
                                movement.conflict_resource_ids
                            ),
                            "signal_group_id": movement.signal_group_id,
                            "provenance": list(movement.provenance),
                        }
                        for movement in node.junction_spec.movement_specs
                    ],
                    "lane_group_ids": list(node.junction_spec.lane_group_ids),
                    "movement_lane_group_mappings": [
                        (movement_id, list(lane_group_ids))
                        for movement_id, lane_group_ids in (
                            node.junction_spec.movement_lane_group_mappings
                        )
                    ],
                    "lane_group_capacities": list(
                        node.junction_spec.lane_group_capacities
                    ),
                    "conflict_resource_ids": list(
                        node.junction_spec.conflict_resource_ids
                    ),
                    "conflict_resource_capacities": list(
                        node.junction_spec.conflict_resource_capacities
                    ),
                    "governance_refs": list(node.junction_spec.governance_refs),
                    "fifo_policy": node.junction_spec.fifo_policy,
                }
                for node in sorted(self.nodes.values(), key=lambda item: item.node_id)
            ],
        }
        serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def _default_node_policy(self, nodes: tuple[Node, ...]) -> NodeTransferPolicy | MovementAllocator:
        if self.model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID:
            return GeneralMovementAllocator(nodes)
        return GlobalFIFOMergePolicy()

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

    def _movement_ids_for_node(self, node_id: str) -> set[str]:
        if node_id not in self.nodes:
            raise KeyError(f"unknown node_id: {node_id}")
        return {
            movement.movement_id
            for movement in self.nodes[node_id].junction_spec.movement_specs
        }

    @staticmethod
    def _validate_runtime_capacity(capacity: int) -> None:
        if not isinstance(capacity, int):
            raise TypeError("runtime capacity must be an int")
        if capacity < 0:
            raise ValueError("runtime capacity must be non-negative")

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

    def set_signal_group_open(self, signal_group_id: str, is_open: bool) -> None:
        """Set engine-owned signal gate state read by movement allocation."""

        if not isinstance(signal_group_id, str) or not signal_group_id:
            raise ValueError("signal_group_id must be non-empty")
        if is_open:
            self._open_signal_group_ids.add(signal_group_id)
        else:
            self._open_signal_group_ids.discard(signal_group_id)

    def set_movement_governance_open(
        self,
        node_id: str,
        movement_id: str,
        is_open: bool,
    ) -> None:
        """Set engine-owned governance closure state for one movement."""

        movement_ids = self._movement_ids_for_node(node_id)
        if movement_id not in movement_ids:
            raise KeyError(f"unknown movement_id for {node_id}: {movement_id}")
        closed = self._closed_movement_ids_by_node_id.setdefault(node_id, set())
        if is_open:
            closed.discard(movement_id)
        else:
            closed.add(movement_id)

    def set_conflict_resource_capacity(
        self,
        node_id: str,
        resource_id: str,
        capacity: int,
    ) -> None:
        """Set runtime conflict-resource capacity for one junction resource."""

        self._validate_runtime_capacity(capacity)
        resource_ids = set(self.nodes[node_id].junction_spec.conflict_resource_ids)
        if resource_id not in resource_ids:
            raise KeyError(f"unknown conflict resource for {node_id}: {resource_id}")
        self._conflict_resource_capacity_by_node_id.setdefault(node_id, {})[
            resource_id
        ] = capacity

    def set_lane_group_capacity(
        self,
        node_id: str,
        lane_group_id: str,
        capacity: int,
    ) -> None:
        """Set runtime lane-group capacity for one junction lane group."""

        self._validate_runtime_capacity(capacity)
        lane_group_ids = set(self.nodes[node_id].junction_spec.lane_group_ids)
        if lane_group_id not in lane_group_ids:
            raise KeyError(f"unknown lane group for {node_id}: {lane_group_id}")
        self._lane_group_capacity_by_node_id.setdefault(node_id, {})[
            lane_group_id
        ] = capacity

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

    def packet_boundary_ordinals(
        self,
        *,
        link_ids: Iterable[str] | None = None,
        max_tick: int | None = None,
    ) -> tuple[PacketBoundaryOrdinal, ...]:
        """Return event-derived packet ordinals for boundary count increments."""

        ordinal_link_ids = tuple(link_ids) if link_ids is not None else tuple(self.links)
        for link_id in ordinal_link_ids:
            self._validate_count_link_id(link_id)
        return packet_boundary_ordinals(
            self.event_log,
            packets=self.packets,
            link_ids=ordinal_link_ids,
            max_tick=self.current_tick if max_tick is None else max_tick,
        )

    def route_cumulative_counts(
        self,
        link_id: str,
        route_key: str,
        tick: int | None = None,
    ) -> RouteCumulativeBoundaryCounts:
        """Return event-derived route-disaggregated counts for one link and route."""

        self._validate_count_link_id(link_id)
        return route_cumulative_counts(
            self.event_log,
            self.packets,
            link_id=link_id,
            route_key=route_key,
            tick=self.current_tick if tick is None else tick,
        )

    def route_cumulative_count_series(
        self,
        link_id: str,
        route_key: str,
        max_tick: int | None = None,
    ) -> tuple[RouteCumulativeBoundaryCounts, ...]:
        """Return route-disaggregated counts from tick 0 through max_tick."""

        self._validate_count_link_id(link_id)
        return route_cumulative_count_series(
            self.event_log,
            self.packets,
            link_id=link_id,
            route_key=route_key,
            max_tick=self.current_tick if max_tick is None else max_tick,
        )

    def cumulative_count_projection(
        self,
        *,
        max_tick: int | None = None,
        prefix_event_count: int | None = None,
    ) -> CumulativeCountProjection:
        """Return a complete read-only M2 count projection from canonical events."""

        return cumulative_count_projection(
            self.event_log,
            link_ids=tuple(self.links),
            packets=self.packets,
            max_tick=self.current_tick if max_tick is None else max_tick,
            prefix_event_count=prefix_event_count,
        )

    def route_travel_time_curves(
        self,
        *,
        max_tick: int | None = None,
    ) -> tuple[RouteTravelTimeCurve, ...]:
        """Return route-keyed completed-packet travel-time curves."""

        return route_travel_time_curves(
            self.event_log,
            self.packets,
            max_tick=self.current_tick if max_tick is None else max_tick,
        )

    def count_consistency_report(
        self,
        *,
        max_tick: int | None = None,
        prefix_event_count: int | None = None,
    ) -> CountConsistencyReport:
        """Return an M2 count/ordinal consistency report for validation artifacts."""

        return count_consistency_report(
            self.event_log,
            link_ids=tuple(self.links),
            packets=self.packets,
            max_tick=self.current_tick if max_tick is None else max_tick,
            prefix_event_count=prefix_event_count,
        )

    def link_storage(
        self,
        link_id: str,
        tick: int | None = None,
    ) -> LinkStorageView:
        """Return count-derived packet storage for one link."""

        self._validate_count_link_id(link_id)
        if tick is None:
            return LinkStorageView(
                link_id=link_id,
                tick=self.current_tick,
                storage=self._current_link_storage_by_link_id[link_id],
            )
        return link_storage(
            self.event_log,
            link_id,
            tick,
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
        if tick is None:
            return self._current_link_sending_view(
                link_id,
                excluded_packet_ids=self._queued_packet_ids_on_upstream_link(link_id),
            )
        return link_sending_view(
            self.event_log,
            self.links[link_id],
            view_tick,
            excluded_packet_ids=self._queued_packet_ids_on_upstream_link(
                link_id,
                view_tick,
            ),
        )

    def parity_link_sending_trace(
        self,
        link_id: str,
        tick: int | None = None,
        *,
        already_consumed_count: int = 0,
        excluded_packet_ids: Iterable[str] = (),
    ) -> ParityLinkSendingTrace:
        """Return a count- and ordinal-derived parity sending trace."""

        self._validate_count_link_id(link_id)
        view_tick = self.current_tick if tick is None else tick
        carry_in = (
            self._parity_sending_capacity_carry_in_by_link_id[link_id]
            if tick is None or tick == self.current_tick
            else 0.0
        )
        return parity_link_sending_trace(
            self.event_log,
            self.packets,
            self.links[link_id],
            view_tick,
            capacity_carry_in=carry_in,
            capacity_vehicles_per_tick=(
                self._parity_sending_capacity_rate_by_link_id[link_id]
            ),
            already_consumed_count=already_consumed_count,
            excluded_packet_ids=excluded_packet_ids,
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
        if tick is None:
            return self._current_link_receiving_view(
                link_id,
                already_accepted_count=already_accepted_count,
            )
        if self._uses_parity_receiving():
            carry_in = (
                self._parity_receiving_capacity_carry_in_by_link_id[link_id]
                if tick == self.current_tick
                else 0.0
            )
            return parity_supply_as_receiving_view(
                self.event_log,
                self.links[link_id],
                view_tick,
                receiving_open=self.is_receiving_open(link_id),
                receiving_capacity_carry_in=carry_in,
                already_accepted_count=already_accepted_count,
                capacity_vehicles_per_tick=(
                    self._parity_receiving_capacity_rate_by_link_id[link_id]
                ),
            )
        return link_receiving_view(
            self.event_log,
            self.links[link_id],
            view_tick,
            self.is_receiving_open(link_id),
            already_accepted_count=already_accepted_count,
        )

    def parity_link_supply_view(
        self,
        link_id: str,
        tick: int | None = None,
        *,
        already_accepted_count: int = 0,
    ) -> LinkSupplyView:
        """Return a parity receiving supply view derived from canonical events."""

        self._validate_count_link_id(link_id)
        view_tick = self.current_tick if tick is None else tick
        carry_in = (
            self._parity_receiving_capacity_carry_in_by_link_id[link_id]
            if tick is None or tick == self.current_tick
            else 0.0
        )
        return parity_link_supply_view(
            self.event_log,
            self.links[link_id],
            view_tick,
            receiving_open=self.is_receiving_open(link_id),
            receiving_capacity_carry_in=carry_in,
            already_accepted_count=already_accepted_count,
            capacity_vehicles_per_tick=(
                self._parity_receiving_capacity_rate_by_link_id[link_id]
            ),
        )

    def receiving_decision_trace(
        self,
        link_id: str,
        tick: int | None = None,
        *,
        already_accepted_count: int = 0,
    ) -> ReceivingDecisionTrace:
        """Return a parity receiving trace for validation and provenance."""

        self._validate_count_link_id(link_id)
        view_tick = self.current_tick if tick is None else tick
        carry_in = (
            self._parity_receiving_capacity_carry_in_by_link_id[link_id]
            if tick is None or tick == self.current_tick
            else 0.0
        )
        return receiving_decision_trace(
            self.event_log,
            self.links[link_id],
            view_tick,
            receiving_open=self.is_receiving_open(link_id),
            receiving_capacity_carry_in=carry_in,
            already_accepted_count=already_accepted_count,
            capacity_vehicles_per_tick=(
                self._parity_receiving_capacity_rate_by_link_id[link_id]
            ),
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
        self._apply_event_to_materialised_views(event)
        return event

    def _apply_event_to_materialised_views(self, event: Event) -> None:
        """Update engine-owned acceleration views from one canonical event."""

        if event.event_type == EventType.LINK_ENTRY:
            self._current_link_storage_by_link_id[event.entity_id] += 1
            self._packet_ids_by_link_id[event.entity_id].append(event.packet_id)
            self._current_link_ids[event.packet_id] = event.entity_id
            self._current_link_entry_ticks[event.packet_id] = event.physical_tick
            self._current_link_entry_metadata_by_packet_id[event.packet_id] = (
                event.entity_id,
                event.physical_tick,
                event.sequence_number,
            )
            self._same_tick_link_entries_by_link_id[event.entity_id] += 1
        elif event.event_type == EventType.LINK_EXIT:
            self._current_link_storage_by_link_id[event.entity_id] -= 1
            if self._current_link_storage_by_link_id[event.entity_id] < 0:
                raise EventCacheConsistencyError(
                    f"materialised storage is negative for {event.entity_id}"
                )
            self._remove_packet_from_current_link(event.packet_id, event.entity_id)
            self._current_link_ids.pop(event.packet_id, None)
            self._current_link_entry_ticks.pop(event.packet_id, None)
            self._current_link_entry_metadata_by_packet_id.pop(event.packet_id, None)
        elif event.event_type == EventType.QUEUE_ENTRY:
            upstream_link_id, downstream_link_id = self._parse_boundary_id(event.entity_id)
            self._queues.setdefault(event.entity_id, deque()).append(event.packet_id)
            self._queue_entry_metadata_by_packet_id[event.packet_id] = (
                event.physical_tick,
                event.sequence_number,
            )
            self._queued_downstream_by_packet_id[event.packet_id] = downstream_link_id
            self._queued_packet_ids_by_upstream_link.setdefault(
                upstream_link_id,
                deque(),
            ).append(event.packet_id)
        elif event.event_type == EventType.QUEUE_EXIT:
            upstream_link_id, _ = self._parse_boundary_id(event.entity_id)
            queue = self._queues.setdefault(event.entity_id, deque())
            if not queue or queue[0] != event.packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {event.packet_id} exits queue {event.entity_id} "
                    "out of FIFO order or without queue entry"
                )
            queue.popleft()
            self._queue_entry_metadata_by_packet_id.pop(event.packet_id, None)
            self._queued_downstream_by_packet_id.pop(event.packet_id, None)
            upstream_queue = self._queued_packet_ids_by_upstream_link.setdefault(
                upstream_link_id,
                deque(),
            )
            if not upstream_queue or upstream_queue[0] != event.packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {event.packet_id} exits upstream queue "
                    f"{upstream_link_id} out of FIFO order or without queue entry"
                )
            upstream_queue.popleft()
        elif event.event_type == EventType.COMPLETED:
            self._completed_packet_ids.add(event.packet_id)
        elif event.event_type == EventType.CANCELLED:
            self._cancelled_packet_ids.add(event.packet_id)

    def _remove_packet_from_current_link(self, packet_id: str, link_id: str) -> None:
        packet_ids = self._packet_ids_by_link_id[link_id]
        if packet_id not in packet_ids:
            raise EventCacheConsistencyError(
                f"packet_id {packet_id} exits link {link_id} without being present"
            )
        packet_ids.remove(packet_id)

    def instantiate(self, demand: DemandDeclaration) -> Packet | None:
        """Instantiate one packet if its departure tick and origin storage permit it."""

        self._validate_demand_for_instantiation(demand)
        if demand.departure_tick > self.current_tick:
            self._defer_demand(demand)
            return None

        first_link_id = demand.route_intent[0]
        if not self._origin_link_has_storage_for_entry(first_link_id):
            self._defer_demand(demand)
            return None

        return self._instantiate_now(demand)

    def _validate_demand_for_instantiation(self, demand: DemandDeclaration) -> None:
        if demand.demand_id in self._instantiated_demand_ids:
            raise ValueError(f"demand_id has already instantiated: {demand.demand_id}")
        if len(demand.route_intent) < 1:
            raise ValueError("route_intent must contain at least one link_id")
        for link_id in demand.route_intent:
            if link_id not in self.links:
                raise KeyError(f"unknown link_id in route_intent: {link_id}")

    def _defer_demand(self, demand: DemandDeclaration) -> None:
        if demand.demand_id in self._pending_demand_ids:
            return
        self._pending_demands.append(demand)
        self._pending_demand_ids.add(demand.demand_id)

    def _instantiate_now(self, demand: DemandDeclaration) -> Packet:
        first_link_id = demand.route_intent[0]
        packet_number = self._next_packet_number
        packet_id = f"P{packet_number}"
        self._next_packet_number += 1
        self._instantiated_demand_ids.add(demand.demand_id)
        packet = Packet(
            packet_id=packet_id,
            demand_id=demand.demand_id,
            route_intent=demand.route_intent,
            lifecycle_state=LifecycleState.IN_TRANSIT,
            packet_unit_weight=demand.packet_unit_weight,
        )
        self._packets[packet_id] = packet
        self._packet_instantiation_orders[packet_id] = packet_number
        self._packet_route_index[packet_id] = 0
        self.append_event(packet_id, EventType.INSTANTIATED, first_link_id)
        self.append_event(packet_id, EventType.LINK_ENTRY, first_link_id)
        return packet

    def _origin_link_has_storage_for_entry(self, link_id: str) -> bool:
        if self._uses_parity_receiving():
            return (
                self._current_link_receiving_view(link_id).available_receiving_slots
                > 0
            )
        return (
            self._current_link_storage_by_link_id[link_id]
            < self.links[link_id].declared_storage_capacity_packets
        )

    def _instantiate_pending_departures(self) -> None:
        if not self._pending_demands:
            return

        still_pending: list[DemandDeclaration] = []
        self._pending_demand_ids.clear()
        for demand in self._pending_demands:
            if demand.departure_tick > self.current_tick:
                still_pending.append(demand)
                self._pending_demand_ids.add(demand.demand_id)
                continue

            first_link_id = demand.route_intent[0]
            if self._origin_link_has_storage_for_entry(first_link_id):
                self._instantiate_now(demand)
            else:
                still_pending.append(demand)
                self._pending_demand_ids.add(demand.demand_id)
        self._pending_demands = still_pending

    def step(self) -> None:
        """Advance the loading engine by exactly one deterministic tick."""

        self.current_tick += 1
        self._reset_same_tick_receiving_acceptance_counts()
        self._prepare_parity_sending_capacity_for_tick()
        self._prepare_parity_receiving_capacity_for_tick()
        self._instantiate_pending_departures()
        completed_counts_by_link = self._complete_eligible_packets()

        receiving_slots = self._receiving_slots_by_link()
        candidates = self._transfer_candidates(completed_counts_by_link, receiving_slots)
        approved_candidates = self._allocate_transfer_requests(
            transfer_requests=candidates,
            receiving_slots=receiving_slots,
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

    def _uses_parity_sending(self) -> bool:
        return self.model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID

    def _uses_parity_receiving(self) -> bool:
        return self.model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID

    def _normalise_parity_sending_capacity_rates(
        self,
        capacity_by_link_id: Mapping[str, float] | None,
    ) -> dict[str, float]:
        capacity_rates = {
            link_id: float(link.declared_sending_capacity_per_tick)
            for link_id, link in self.links.items()
        }
        if capacity_by_link_id is None:
            return capacity_rates
        for link_id, capacity_rate in capacity_by_link_id.items():
            if link_id not in self.links:
                raise KeyError(
                    f"unknown link_id for parity sending capacity: {link_id}"
                )
            if capacity_rate < 0:
                raise ValueError(
                    "parity sending capacity cannot be negative for "
                    f"{link_id}: {capacity_rate}"
                )
            capacity_rates[link_id] = float(capacity_rate)
        return capacity_rates

    def _normalise_parity_receiving_capacity_rates(
        self,
        capacity_by_link_id: Mapping[str, float] | None,
    ) -> dict[str, float]:
        capacity_rates = {
            link_id: float(link.declared_receiving_capacity_per_tick)
            for link_id, link in self.links.items()
        }
        if capacity_by_link_id is None:
            return capacity_rates
        for link_id, capacity_rate in capacity_by_link_id.items():
            if link_id not in self.links:
                raise KeyError(
                    f"unknown link_id for parity receiving capacity: {link_id}"
                )
            if capacity_rate < 0:
                raise ValueError(
                    "parity receiving capacity cannot be negative for "
                    f"{link_id}: {capacity_rate}"
                )
            capacity_rates[link_id] = float(capacity_rate)
        return capacity_rates

    def _prepare_parity_sending_capacity_for_tick(self) -> None:
        if not self._uses_parity_sending():
            self._parity_sending_integer_capacity_by_link_id = {
                link_id: link.declared_sending_capacity_per_tick
                for link_id, link in self.links.items()
            }
            return

        integer_capacity_by_link: dict[str, int] = {}
        carry_by_link: dict[str, float] = {}
        carry_in_by_link: dict[str, float] = {}
        for link_id, link in self.links.items():
            carry_in = self._parity_sending_capacity_carry_by_link_id[link_id]
            capacity = bounded_integer_capacity_carry(
                link_id=link_id,
                capacity_vehicles_per_tick=(
                    self._parity_sending_capacity_rate_by_link_id[link_id]
                ),
                carry_in=carry_in,
            )
            carry_in_by_link[link_id] = carry_in
            integer_capacity_by_link[link_id] = capacity.integer_capacity
            carry_by_link[link_id] = capacity.carry_out
        self._parity_sending_integer_capacity_by_link_id = integer_capacity_by_link
        self._parity_sending_capacity_carry_in_by_link_id = carry_in_by_link
        self._parity_sending_capacity_carry_by_link_id = carry_by_link

    def _prepare_parity_receiving_capacity_for_tick(self) -> None:
        if not self._uses_parity_receiving():
            self._parity_receiving_integer_capacity_by_link_id = {
                link_id: link.declared_receiving_capacity_per_tick
                for link_id, link in self.links.items()
            }
            return

        integer_capacity_by_link: dict[str, int] = {}
        carry_by_link: dict[str, float] = {}
        carry_in_by_link: dict[str, float] = {}
        for link_id in self.links:
            carry_in = self._parity_receiving_capacity_carry_by_link_id[link_id]
            integer_capacity, carry_out = bounded_integer_receiving_capacity_carry(
                link_id=link_id,
                capacity_vehicles_per_tick=(
                    self._parity_receiving_capacity_rate_by_link_id[link_id]
                ),
                carry_in=carry_in,
            )
            carry_in_by_link[link_id] = carry_in
            integer_capacity_by_link[link_id] = integer_capacity
            carry_by_link[link_id] = carry_out
        self._parity_receiving_integer_capacity_by_link_id = integer_capacity_by_link
        self._parity_receiving_capacity_carry_in_by_link_id = carry_in_by_link
        self._parity_receiving_capacity_carry_by_link_id = carry_by_link

    def _sending_capacity_limit_for_current_tick(self, link_id: str) -> int:
        if self._uses_parity_sending():
            return self._parity_sending_integer_capacity_by_link_id[link_id]
        return self.links[link_id].declared_sending_capacity_per_tick

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
            link_id: self._current_link_receiving_view(link_id).available_receiving_slots
            for link_id in self.links
        }

    def _reset_same_tick_receiving_acceptance_counts(self) -> None:
        self._same_tick_link_entries_by_link_id = {
            link_id: 0 for link_id in self.links
        }

    def _current_link_sending_view(
        self,
        link_id: str,
        excluded_packet_ids: tuple[str, ...] = (),
        already_consumed_count: int = 0,
    ) -> LinkSendingView:
        if self._uses_parity_sending():
            return parity_link_sending_trace(
                self.event_log,
                self.packets,
                self.links[link_id],
                self.current_tick,
                capacity_carry_in=self._parity_sending_capacity_carry_in_by_link_id[
                    link_id
                ],
                capacity_vehicles_per_tick=(
                    self._parity_sending_capacity_rate_by_link_id[link_id]
                ),
                already_consumed_count=already_consumed_count,
                excluded_packet_ids=excluded_packet_ids,
            ).as_legacy_view()

        link = self.links[link_id]
        sending_capacity = link.declared_sending_capacity_per_tick
        excluded_packet_id_set = set(excluded_packet_ids)
        eligible_packet_metadata = sorted(
            (
                (packet_id, entry_tick, sequence_number)
                for packet_id in self._packet_ids_by_link_id[link_id]
                for entry_link_id, entry_tick, sequence_number in (
                    self._current_link_entry_metadata_by_packet_id[packet_id],
                )
                if entry_link_id == link_id
                and packet_id not in excluded_packet_id_set
                and self.current_tick - entry_tick >= link.free_flow_ticks
            ),
            key=lambda item: (item[1], item[2], item[0]),
        )
        eligible_packet_ids = tuple(
            packet_id for packet_id, _, _ in eligible_packet_metadata
        )
        return LinkSendingView(
            link_id=link_id,
            tick=self.current_tick,
            eligible_packet_ids=eligible_packet_ids,
            sending_capacity=sending_capacity,
            sendable_packet_ids=eligible_packet_ids[:sending_capacity],
        )

    def _current_link_receiving_view(
        self,
        link_id: str,
        already_accepted_count: int = 0,
    ) -> LinkReceivingView:
        if self._uses_parity_receiving():
            return parity_supply_as_receiving_view(
                self.event_log,
                self.links[link_id],
                self.current_tick,
                receiving_open=self.is_receiving_open(link_id),
                receiving_capacity_carry_in=(
                    self._parity_receiving_capacity_carry_in_by_link_id[link_id]
                ),
                already_accepted_count=already_accepted_count,
                capacity_vehicles_per_tick=(
                    self._parity_receiving_capacity_rate_by_link_id[link_id]
                ),
            )

        link = self.links[link_id]
        receiving_capacity = link.declared_receiving_capacity_per_tick
        storage_capacity = link.declared_storage_capacity_packets
        same_tick_accepted_count = self._same_tick_link_entries_by_link_id[link_id]
        accepted_count = already_accepted_count + same_tick_accepted_count
        current_storage = (
            self._current_link_storage_by_link_id[link_id]
            - same_tick_accepted_count
        )
        if current_storage < 0:
            raise EventCacheConsistencyError(
                f"materialised storage before same-tick entries is negative for "
                f"{link_id}: {current_storage}"
            )
        available_receiving_capacity = max(receiving_capacity - accepted_count, 0)
        available_storage_space = max(
            storage_capacity - current_storage - accepted_count,
            0,
        )
        if self.is_receiving_open(link_id):
            available_receiving_slots = min(
                available_receiving_capacity,
                available_storage_space,
            )
        else:
            available_receiving_slots = 0

        return LinkReceivingView(
            link_id=link_id,
            tick=self.current_tick,
            receiving_open=self.is_receiving_open(link_id),
            receiving_capacity=receiving_capacity,
            already_accepted_count=accepted_count,
            current_storage=current_storage,
            storage_capacity=storage_capacity,
            available_storage_space=available_storage_space,
            available_receiving_slots=available_receiving_slots,
        )

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
        self._set_lifecycle_state(packet_id, LifecycleState.QUEUED)

    def _queue_packet_once(
        self,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> None:
        if packet_id in self._queued_downstream_by_packet_id:
            return
        self._queue_packet(packet_id, upstream_link_id, downstream_link_id)

    def _complete_eligible_packets(self) -> dict[str, int]:
        completed_counts_by_link: dict[str, int] = {}
        for link_id in sorted(self.links):
            sending_view = self._current_link_sending_view(
                link_id,
                excluded_packet_ids=self._queued_packet_ids_on_upstream_link(link_id),
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
        consumed_sending_slots_by_link: dict[str, int],
        receiving_slots_by_link: dict[str, int],
    ) -> tuple[TransferRequest, ...]:
        queued_candidates = self._queued_transfer_candidates(
            consumed_sending_slots_by_link,
            receiving_slots_by_link,
        )
        queued_candidate_counts_by_upstream_link: dict[str, int] = {}
        for candidate in queued_candidates:
            queued_candidate_counts_by_upstream_link[candidate.upstream_link_id] = (
                queued_candidate_counts_by_upstream_link.get(
                    candidate.upstream_link_id,
                    0,
                )
                + 1
            )
        active_consumed_slots = dict(consumed_sending_slots_by_link)
        for upstream_link_id, queued_candidate_count in (
            queued_candidate_counts_by_upstream_link.items()
        ):
            active_consumed_slots[upstream_link_id] = (
                active_consumed_slots.get(upstream_link_id, 0)
                + queued_candidate_count
            )
        candidates = [
            *queued_candidates,
            *self._active_transfer_candidates(active_consumed_slots),
        ]
        return tuple(candidates)

    def _queued_transfer_candidates(
        self,
        consumed_sending_slots_by_link: dict[str, int],
        receiving_slots_by_link: dict[str, int],
    ) -> list[TransferRequest]:
        candidates: list[TransferRequest] = []
        for upstream_link_id in sorted(self._queued_packet_ids_by_upstream_link):
            queue = self._queued_packet_ids_by_upstream_link[upstream_link_id]
            if not queue:
                continue
            remaining_sending_capacity = (
                self._sending_capacity_limit_for_current_tick(upstream_link_id)
                - consumed_sending_slots_by_link.get(upstream_link_id, 0)
            )
            if remaining_sending_capacity <= 0:
                continue

            emitted_count = 0
            emitted_count_by_downstream_link: dict[str, int] = {}
            emitted_count_by_boundary: dict[str, int] = {}
            for packet_id in queue:
                if emitted_count >= remaining_sending_capacity:
                    break
                downstream_link_id = self._queued_downstream_by_packet_id[packet_id]
                downstream_slots_remaining = (
                    receiving_slots_by_link.get(downstream_link_id, 0)
                    - emitted_count_by_downstream_link.get(downstream_link_id, 0)
                )
                if downstream_slots_remaining <= 0:
                    break
                boundary_id = self._boundary_id(upstream_link_id, downstream_link_id)
                boundary_queue = self._queues.get(boundary_id)
                boundary_offset = emitted_count_by_boundary.get(boundary_id, 0)
                if (
                    not boundary_queue
                    or len(boundary_queue) <= boundary_offset
                    or boundary_queue[boundary_offset] != packet_id
                ):
                    raise EventCacheConsistencyError(
                        f"packet_id {packet_id} is not in FIFO prefix for "
                        f"queue {boundary_id}"
                    )
                self._validate_transfer_connectivity(
                    upstream_link_id,
                    downstream_link_id,
                )
                eligibility_tick, eligibility_sequence_number = (
                    self._queue_entry_metadata_by_packet_id[packet_id]
                )
                candidates.append(
                    TransferRequest(
                        packet_id=packet_id,
                        upstream_link_id=upstream_link_id,
                        downstream_link_id=downstream_link_id,
                        boundary_id=boundary_id,
                        eligibility_tick=eligibility_tick,
                        eligibility_sequence_number=eligibility_sequence_number,
                        queued=True,
                        node_id=(
                            self._node_by_incoming_link_id[upstream_link_id].node_id
                            if upstream_link_id in self._node_by_incoming_link_id
                            else None
                        ),
                    )
                )
                emitted_count += 1
                emitted_count_by_downstream_link[downstream_link_id] = (
                    emitted_count_by_downstream_link.get(downstream_link_id, 0) + 1
                )
                emitted_count_by_boundary[boundary_id] = boundary_offset + 1
        return candidates

    def _active_transfer_candidates(
        self,
        consumed_sending_slots_by_link: dict[str, int],
    ) -> list[TransferRequest]:
        link_entry_metadata = self._current_link_entry_metadata_by_packet_id
        queued_packet_ids = set(self._queued_downstream_by_packet_id)
        candidates: list[TransferRequest] = []
        for upstream_link_id in sorted(self.links):
            link = self.links[upstream_link_id]
            sending_view = self._current_link_sending_view(
                upstream_link_id,
                excluded_packet_ids=tuple(queued_packet_ids),
                already_consumed_count=consumed_sending_slots_by_link.get(
                    upstream_link_id,
                    0,
                ),
            )
            for packet_id in sending_view.sendable_packet_ids:
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
                    TransferRequest(
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
                        node_id=(
                            self._node_by_incoming_link_id[upstream_link_id].node_id
                            if upstream_link_id in self._node_by_incoming_link_id
                            else None
                        ),
                    )
                )
        return candidates

    def _allocate_transfer_requests(
        self,
        *,
        transfer_requests: tuple[TransferRequest, ...],
        receiving_slots: dict[str, int],
    ) -> tuple[TransferRequest, ...]:
        packet_ids_by_upstream_link = MappingProxyType(
            self._packet_ids_by_upstream_link_for_candidates(transfer_requests)
        )
        queued_downstream_by_packet_id = MappingProxyType(
            dict(self._queued_downstream_by_packet_id)
        )
        receiving_slots_view = MappingProxyType(dict(receiving_slots))
        self._last_rejected_transfer_reason_by_candidate = {}
        if hasattr(self.movement_allocator, "allocate"):
            decision: JunctionAllocationDecision = self.movement_allocator.allocate(
                allocation_inputs=self._junction_allocation_inputs(
                    transfer_requests=transfer_requests,
                    receiving_slots_by_downstream_link=receiving_slots_view,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            )
            self._last_rejected_transfer_reason_by_candidate = {
                rejected.transfer_request: rejected.reason
                for rejected in decision.rejected_transfers
            }
            return decision.approved_transfers
        return self.movement_allocator.choose_transfers(
            candidates=transfer_requests,
            receiving_slots_by_downstream_link=receiving_slots_view,
            packet_ids_by_upstream_link=packet_ids_by_upstream_link,
            queued_downstream_by_packet_id=queued_downstream_by_packet_id,
        )

    def _junction_allocation_inputs(
        self,
        *,
        transfer_requests: tuple[TransferRequest, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[JunctionAllocationInput, ...]:
        requests_by_node_id: dict[str, list[TransferRequest]] = {}
        fallback_requests: list[TransferRequest] = []
        for request in transfer_requests:
            node = self._node_by_incoming_link_id.get(request.upstream_link_id)
            if node is None:
                fallback_requests.append(request)
                continue
            requests_by_node_id.setdefault(node.node_id, []).append(request)

        allocation_inputs: list[JunctionAllocationInput] = []
        for node in sorted(self.nodes.values(), key=lambda item: item.node_id):
            node_requests = tuple(requests_by_node_id.get(node.node_id, ()))
            if not node_requests:
                continue
            allocation_inputs.append(
                JunctionAllocationInput(
                    node_id=node.node_id,
                    junction_spec=node.junction_spec,
                    transfer_requests=node_requests,
                    receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                    conflict_resource_capacity_by_id=MappingProxyType(
                        dict(
                            self._conflict_resource_capacity_by_node_id.get(
                                node.node_id,
                                {},
                            )
                        )
                    ),
                    lane_group_capacity_by_id=MappingProxyType(
                        dict(
                            self._lane_group_capacity_by_node_id.get(
                                node.node_id,
                                {},
                            )
                        )
                    ),
                    open_signal_group_ids=frozenset(self._open_signal_group_ids),
                    closed_movement_ids=frozenset(
                        self._closed_movement_ids_by_node_id.get(node.node_id, set())
                    ),
                )
            )
        if fallback_requests:
            allocation_inputs.append(
                JunctionAllocationInput(
                    node_id="__implicit_junction__",
                    junction_spec=None,
                    transfer_requests=tuple(fallback_requests),
                    receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            )
        return tuple(allocation_inputs)

    def _packet_ids_by_upstream_link_for_candidates(
        self,
        candidates: tuple[TransferRequest, ...],
    ) -> dict[str, tuple[str, ...]]:
        return {
            upstream_link_id: self.packet_ids_on_link(upstream_link_id)
            for upstream_link_id in sorted(
                {candidate.upstream_link_id for candidate in candidates}
            )
        }

    def _execute_approved_transfers(
        self,
        approved_candidates: tuple[TransferRequest, ...],
        candidates: tuple[TransferRequest, ...],
        receiving_slots: dict[str, int],
    ) -> tuple[set[TransferRequest], dict[str, int]]:
        candidate_set = set(candidates)
        approved_candidate_set: set[TransferRequest] = set()
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

    def _execute_transfer_candidate(self, candidate: TransferRequest) -> None:
        if candidate.queued:
            queue = self._queues[candidate.boundary_id]
            if not queue or queue[0] != candidate.packet_id:
                raise EventCacheConsistencyError(
                    f"packet_id {candidate.packet_id} is not first in queue "
                    f"{candidate.boundary_id}"
                )
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
        candidates: tuple[TransferRequest, ...],
        approved_candidate_set: set[TransferRequest],
        remaining_slots: dict[str, int],
    ) -> None:
        for candidate in candidates:
            if candidate in approved_candidate_set or candidate.queued:
                continue
            rejection_reason = self._last_rejected_transfer_reason_by_candidate.get(
                candidate
            )
            if (
                remaining_slots.get(candidate.downstream_link_id, 0) <= 0
                or self._queues.get(candidate.boundary_id)
                or rejection_reason
                in {
                    REJECTED_DOWNSTREAM_SUPPLY,
                    REJECTED_CONFLICT_RESOURCE_CAPACITY,
                    REJECTED_LANE_GROUP_CAPACITY,
                    REJECTED_SIGNAL_CLOSED,
                    REJECTED_GOVERNANCE_CLOSED,
                }
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

    def _queued_packet_ids_by_upstream_link_from_events(
        self,
    ) -> dict[str, tuple[str, ...]]:
        """Derive upstream-link queue membership from queue events."""

        queues: dict[str, deque[str]] = {}
        for event in self._event_log:
            if event.event_type == EventType.QUEUE_ENTRY:
                upstream_link_id, _ = self._parse_boundary_id(event.entity_id)
                queues.setdefault(upstream_link_id, deque()).append(event.packet_id)
            elif event.event_type == EventType.QUEUE_EXIT:
                upstream_link_id, _ = self._parse_boundary_id(event.entity_id)
                queue = queues.setdefault(upstream_link_id, deque())
                if not queue or queue[0] != event.packet_id:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} exits upstream queue "
                        f"{upstream_link_id} out of FIFO order or without queue entry"
                    )
                queue.popleft()
        return {
            upstream_link_id: tuple(packet_ids)
            for upstream_link_id, packet_ids in queues.items()
        }

    def _queued_packet_ids_on_upstream_link(
        self,
        link_id: str,
        tick: int | None = None,
    ) -> tuple[str, ...]:
        if tick is None or tick == self.current_tick:
            return tuple(self._queued_packet_ids_by_upstream_link.get(link_id, ()))

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
        self._set_lifecycle_state(packet_id, LifecycleState.IN_TRANSIT)

    def _complete_packet(self, packet_id: str, link_id: str) -> None:
        self.append_event(packet_id, EventType.LINK_EXIT, link_id)
        self.append_event(packet_id, EventType.COMPLETED, link_id)
        self._set_lifecycle_state(packet_id, LifecycleState.COMPLETED)

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
        """Return current packet IDs physically on a link."""

        self._validate_count_link_id(link_id)
        return tuple(self._packet_ids_by_link_id[link_id])

    def packet_ids_in_queue(
        self,
        upstream_link_id: str,
        downstream_link_id: str,
    ) -> tuple[str, ...]:
        """Return current packet IDs queued at a boundary."""

        boundary_id = self._boundary_id(upstream_link_id, downstream_link_id)
        return tuple(self._queues.get(boundary_id, ()))

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
        event_upstream_queues = self._queued_packet_ids_by_upstream_link_from_events()
        for upstream_link_id in set(event_upstream_queues) | set(
            self._queued_packet_ids_by_upstream_link
        ):
            cache_queue = tuple(
                self._queued_packet_ids_by_upstream_link.get(upstream_link_id, ())
            )
            event_queue = event_upstream_queues.get(upstream_link_id, ())
            if cache_queue != event_queue:
                raise EventCacheConsistencyError(
                    f"upstream queue cache for {upstream_link_id} is {cache_queue}, "
                    f"but event log implies {event_queue}"
                )
        self._check_materialised_loading_views_consistent()
        return True

    def _check_materialised_loading_views_consistent(self) -> None:
        packet_ids_by_link_id = {link_id: [] for link_id in self.links}
        for event in self._event_log:
            if event.event_type == EventType.LINK_ENTRY:
                packet_ids_by_link_id[event.entity_id].append(event.packet_id)
            elif event.event_type == EventType.LINK_EXIT:
                packet_ids_by_link_id[event.entity_id].remove(event.packet_id)

        for link_id in self.links:
            event_storage = len(packet_ids_by_link_id[link_id])
            if self._current_link_storage_by_link_id[link_id] != event_storage:
                raise EventCacheConsistencyError(
                    f"storage cache for {link_id} is "
                    f"{self._current_link_storage_by_link_id[link_id]}, "
                    f"but event log implies {event_storage}"
                )
            if tuple(self._packet_ids_by_link_id[link_id]) != tuple(
                packet_ids_by_link_id[link_id]
            ):
                raise EventCacheConsistencyError(
                    f"membership cache for {link_id} is "
                    f"{tuple(self._packet_ids_by_link_id[link_id])}, "
                    f"but event log implies {tuple(packet_ids_by_link_id[link_id])}"
                )

        event_entry_metadata = self._current_link_entry_metadata_by_packet_id_from_events()
        if self._current_link_entry_metadata_by_packet_id != event_entry_metadata:
            raise EventCacheConsistencyError(
                "current link-entry metadata cache does not match event history"
            )

        event_completed_packet_ids = {
            event.packet_id
            for event in self._event_log
            if event.event_type == EventType.COMPLETED
        }
        if self._completed_packet_ids != event_completed_packet_ids:
            raise EventCacheConsistencyError(
                f"completed packet cache is {self._completed_packet_ids}, "
                f"but event log implies {event_completed_packet_ids}"
            )

        event_queue_entry_metadata = self._queue_entry_metadata_by_packet_id_from_events()
        if self._queue_entry_metadata_by_packet_id != event_queue_entry_metadata:
            raise EventCacheConsistencyError(
                "queue-entry metadata cache does not match event history"
            )

        event_queued_downstream = self._queued_downstream_by_packet_id_from_events()
        if self._queued_downstream_by_packet_id != event_queued_downstream:
            raise EventCacheConsistencyError(
                "queued downstream cache does not match event history"
            )
        self._check_live_queue_membership_consistent()

        same_tick_entries = {
            link_id: sum(
                event.event_type == EventType.LINK_ENTRY
                and event.entity_id == link_id
                and event.physical_tick == self.current_tick
                for event in self._event_log
            )
            for link_id in self.links
        }
        if self._same_tick_link_entries_by_link_id != same_tick_entries:
            raise EventCacheConsistencyError(
                "same-tick receiving acceptance cache does not match event history"
            )

    def _check_live_queue_membership_consistent(self) -> None:
        boundary_queued_packet_ids: list[str] = [
            packet_id
            for queue in self._queues.values()
            for packet_id in queue
        ]
        upstream_queued_packet_ids: list[str] = [
            packet_id
            for queue in self._queued_packet_ids_by_upstream_link.values()
            for packet_id in queue
        ]
        if len(boundary_queued_packet_ids) != len(set(boundary_queued_packet_ids)):
            raise EventCacheConsistencyError(
                "a packet appears in more than one boundary queue"
            )
        if len(upstream_queued_packet_ids) != len(set(upstream_queued_packet_ids)):
            raise EventCacheConsistencyError(
                "a packet appears more than once in upstream queues"
            )
        if set(boundary_queued_packet_ids) != set(upstream_queued_packet_ids):
            raise EventCacheConsistencyError(
                "boundary queue membership does not match upstream queue membership"
            )
        if set(boundary_queued_packet_ids) != set(self._queued_downstream_by_packet_id):
            raise EventCacheConsistencyError(
                "queue membership does not match queued downstream packet IDs"
            )

        terminal_packet_ids = self._completed_packet_ids | self._cancelled_packet_ids
        queued_terminal_packet_ids = sorted(
            set(boundary_queued_packet_ids) & terminal_packet_ids
        )
        if queued_terminal_packet_ids:
            raise EventCacheConsistencyError(
                "terminal packets remain queued: "
                f"{tuple(queued_terminal_packet_ids)}"
            )

        if len(self._pending_demands) != len(self._pending_demand_ids):
            raise EventCacheConsistencyError(
                "pending demand list and pending demand ID cache disagree"
            )
        for demand in self._pending_demands:
            if demand.demand_id not in self._pending_demand_ids:
                raise EventCacheConsistencyError(
                    f"pending demand {demand.demand_id} is missing from ID cache"
                )
            if demand.demand_id in self._instantiated_demand_ids:
                raise EventCacheConsistencyError(
                    f"pending demand {demand.demand_id} has already instantiated"
                )

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
