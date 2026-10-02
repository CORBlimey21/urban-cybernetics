# SPDX-License-Identifier: MPL-2.0
"""Versioned mesoscopic lane-group FIFO extension above the frozen LTM kernel.

The extension is deliberately injected through the frozen engine's existing
``node_transfer_policy`` seam.  It does not modify packet events, LTM sending or
receiving, link storage, or the v1.0.1 allocator.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Literal

from urban_cybernetics.core import EventType, Node
from urban_cybernetics.core.node import (
    MovementSpec,
)
from urban_cybernetics.loading.transfer_policy import (
    GeneralMovementAllocator,
    JunctionAllocationDecision,
    JunctionAllocationInput,
    RejectedTransfer,
    REJECTED_CONFLICT_RESOURCE_CAPACITY,
    REJECTED_DOWNSTREAM_SUPPLY,
    REJECTED_GOVERNANCE_CLOSED,
    REJECTED_LANE_GROUP_CAPACITY,
    REJECTED_MOVEMENT_UNDECLARED,
    REJECTED_NOT_SELECTED,
    REJECTED_SIGNAL_CLOSED,
    REJECTED_UPSTREAM_FIFO,
    TransferRequest,
)
from urban_cybernetics.loading.engine import (
    EventCacheConsistencyError,
    LoadingEngine,
)


LANE_GROUP_EXTENSION_VERSION = "paper1-lane-group-extension-v1"
EXPLICIT_LANE_GROUP_SCHEMA_VERSION = "explicit-lane-groups-v1"
SHARED_LINK_FIFO = "shared_link_fifo"
MOVEMENT_PARTIAL_FIFO = "movement_partial_fifo"
EXPLICIT_LANE_GROUP_FIFO = "explicit_lane_group_fifo"
QueueRepresentationMode = Literal[
    "shared_link_fifo",
    "movement_partial_fifo",
    "explicit_lane_group_fifo",
]
SUPPORTED_QUEUE_REPRESENTATION_MODES = frozenset(
    (SHARED_LINK_FIFO, MOVEMENT_PARTIAL_FIFO, EXPLICIT_LANE_GROUP_FIFO)
)


@dataclass(frozen=True, slots=True)
class LaneGroupProvenance:
    """Evidence fields reserved for declared or inferred lane-group mappings."""

    source: str
    confidence: float | None
    status: Literal["declared", "inferred"]
    fallback_reason: str | None = None
    compiler_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("lane-group provenance source must be non-empty")
        if self.confidence is not None:
            if not isinstance(self.confidence, (int, float)):
                raise TypeError("lane-group confidence must be numeric")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise ValueError("lane-group confidence must be in [0, 1]")
            object.__setattr__(self, "confidence", float(self.confidence))
        if self.status not in ("declared", "inferred"):
            raise ValueError(f"unsupported lane-group provenance status: {self.status}")
        if self.fallback_reason is not None and not self.fallback_reason:
            raise ValueError("fallback_reason must be non-empty when provided")
        if not isinstance(self.compiler_version, str):
            raise TypeError("compiler_version must be a string")


@dataclass(frozen=True, slots=True)
class ExplicitLaneGroup:
    """One approach queue partition local to an incoming link and junction."""

    lane_group_id: str
    node_id: str
    incoming_link_id: str
    allowed_movement_ids: tuple[str, ...]
    service_capacity_per_tick: int
    provenance: LaneGroupProvenance

    def __post_init__(self) -> None:
        for field_name in ("lane_group_id", "node_id", "incoming_link_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.allowed_movement_ids, tuple):
            raise TypeError("allowed_movement_ids must be a tuple")
        if not self.allowed_movement_ids:
            raise ValueError("allowed_movement_ids must be non-empty")
        if len(set(self.allowed_movement_ids)) != len(self.allowed_movement_ids):
            raise ValueError("allowed_movement_ids must not contain duplicates")
        if any(
            not isinstance(item, str) or not item
            for item in self.allowed_movement_ids
        ):
            raise ValueError("allowed_movement_ids must contain non-empty strings")
        if not isinstance(self.service_capacity_per_tick, int):
            raise TypeError("service_capacity_per_tick must be an int")
        if self.service_capacity_per_tick <= 0:
            raise ValueError("service_capacity_per_tick must be positive")
        if not isinstance(self.provenance, LaneGroupProvenance):
            raise TypeError("provenance must be LaneGroupProvenance")


@dataclass(frozen=True, slots=True)
class LaneGroupExtensionConfig:
    """Versioned topology-side declarations plus the ablation mode switch."""

    representation_mode: QueueRepresentationMode
    lane_groups: tuple[ExplicitLaneGroup, ...]
    schema_version: str = EXPLICIT_LANE_GROUP_SCHEMA_VERSION
    extension_version: str = LANE_GROUP_EXTENSION_VERSION
    reassignment_policy: Literal["retain"] = "retain"

    def __post_init__(self) -> None:
        if self.representation_mode not in SUPPORTED_QUEUE_REPRESENTATION_MODES:
            raise ValueError(
                f"unsupported representation_mode: {self.representation_mode}"
            )
        if self.schema_version != EXPLICIT_LANE_GROUP_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported lane-group schema_version: {self.schema_version}"
            )
        if self.extension_version != LANE_GROUP_EXTENSION_VERSION:
            raise ValueError(
                f"unsupported lane-group extension_version: {self.extension_version}"
            )
        if self.reassignment_policy != "retain":
            raise ValueError("v1 supports only retained lane-group assignments")
        if not isinstance(self.lane_groups, tuple):
            raise TypeError("lane_groups must be a tuple")
        seen: set[tuple[str, str]] = set()
        for lane_group in self.lane_groups:
            if not isinstance(lane_group, ExplicitLaneGroup):
                raise TypeError("lane_groups must contain ExplicitLaneGroup records")
            key = (lane_group.node_id, lane_group.lane_group_id)
            if key in seen:
                raise ValueError(
                    "duplicate lane-group ID within junction: "
                    f"{lane_group.node_id}:{lane_group.lane_group_id}"
                )
            seen.add(key)

    @property
    def config_hash(self) -> str:
        """Return a deterministic identity for topology-side extension metadata."""

        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def validate_against_nodes(self, nodes: Iterable[Node]) -> None:
        """Validate locality, movement coverage, and the frozen-field boundary."""

        node_by_id = {node.node_id: node for node in nodes}
        groups_by_node: dict[str, list[ExplicitLaneGroup]] = {}
        for lane_group in self.lane_groups:
            node = node_by_id.get(lane_group.node_id)
            if node is None:
                raise ValueError(
                    f"lane group references unknown node_id: {lane_group.node_id}"
                )
            if lane_group.incoming_link_id not in node.incoming_link_ids:
                raise ValueError(
                    f"lane group {lane_group.lane_group_id} references unknown "
                    f"incoming link {lane_group.incoming_link_id}"
                )
            movement_by_id = node.junction_spec.movement_by_id
            for movement_id in lane_group.allowed_movement_ids:
                movement = movement_by_id.get(movement_id)
                if movement is None:
                    raise ValueError(
                        f"lane group {lane_group.lane_group_id} references unknown "
                        f"movement_id: {movement_id}"
                    )
                if movement.upstream_link_id != lane_group.incoming_link_id:
                    raise ValueError(
                        f"lane group {lane_group.lane_group_id} is local to "
                        f"{lane_group.incoming_link_id}, not "
                        f"{movement.upstream_link_id}"
                    )
            groups_by_node.setdefault(lane_group.node_id, []).append(lane_group)

        for node_id, lane_groups in groups_by_node.items():
            node = node_by_id[node_id]
            partitioned_links = {
                lane_group.incoming_link_id for lane_group in lane_groups
            }
            mapped = {
                movement_id
                for lane_group in lane_groups
                for movement_id in lane_group.allowed_movement_ids
            }
            required = {
                movement.movement_id
                for movement in node.junction_spec.movement_specs
                if movement.upstream_link_id in partitioned_links
            }
            missing = tuple(sorted(required - mapped))
            if missing:
                raise ValueError(
                    "explicit groups must map every movement on each partitioned "
                    f"incoming link at {node_id}: {missing}"
                )
            if self.representation_mode == EXPLICIT_LANE_GROUP_FIFO and (
                node.junction_spec.lane_group_ids
                or any(
                    movement.lane_group_ids
                    for movement in node.junction_spec.movement_specs
                )
            ):
                raise ValueError(
                    "explicit lane-group mode does not reinterpret frozen "
                    f"lane_group_ids at {node_id}; remove legacy resources from "
                    "the extension fixture or run a baseline mode"
                )


@dataclass(frozen=True, slots=True)
class LaneGroupAllocationTrace:
    """Extension-only allocation evidence; never written to the physical event log."""

    node_id: str
    representation_mode: str
    packet_assignments: tuple[tuple[str, str], ...]
    assigned_queue_lengths: tuple[tuple[str, int], ...]
    approved_packet_lane_groups: tuple[tuple[str, str], ...]


class LaneGroupExtensionAllocator(GeneralMovementAllocator):
    """Mode-selectable allocator using the frozen Stage 2 allocator as baseline."""

    def __init__(
        self,
        nodes: Iterable[Node],
        config: LaneGroupExtensionConfig,
    ) -> None:
        node_tuple = tuple(nodes)
        config.validate_against_nodes(node_tuple)
        self.extension_config = config
        self.allocator_id = (
            f"{LANE_GROUP_EXTENSION_VERSION}:{config.representation_mode}"
        )
        self._groups_by_node_id: dict[str, tuple[ExplicitLaneGroup, ...]] = {
            node_id: tuple(
                lane_group
                for lane_group in config.lane_groups
                if lane_group.node_id == node_id
            )
            for node_id in sorted({item.node_id for item in config.lane_groups})
        }
        self._groups_by_node_movement: dict[
            tuple[str, str], tuple[ExplicitLaneGroup, ...]
        ] = {}
        for node_id, lane_groups in self._groups_by_node_id.items():
            movement_ids = {
                movement_id
                for lane_group in lane_groups
                for movement_id in lane_group.allowed_movement_ids
            }
            for movement_id in movement_ids:
                self._groups_by_node_movement[(node_id, movement_id)] = tuple(
                    lane_group
                    for lane_group in lane_groups
                    if movement_id in lane_group.allowed_movement_ids
                )
        self._assignment_by_node_packet: dict[tuple[str, str], str] = {}
        self._last_lane_group_allocation_traces: tuple[
            LaneGroupAllocationTrace, ...
        ] = ()
        super().__init__(node_tuple)
        # GeneralMovementAllocator assigns its frozen ID as a class attribute only.
        self.allocator_id = (
            f"{LANE_GROUP_EXTENSION_VERSION}:{config.representation_mode}"
        )

    @property
    def last_lane_group_allocation_traces(
        self,
    ) -> tuple[LaneGroupAllocationTrace, ...]:
        return self._last_lane_group_allocation_traces

    def assigned_lane_group(self, node_id: str, packet_id: str) -> str | None:
        """Return the retained extension assignment for queue validation."""

        return self._assignment_by_node_packet.get((node_id, packet_id))

    def has_explicit_groups(self, node_id: str) -> bool:
        """Return whether the extension partitions any approach at a junction."""

        return node_id in self._groups_by_node_id

    def allocate(
        self,
        *,
        allocation_inputs: tuple[JunctionAllocationInput, ...],
    ) -> JunctionAllocationDecision:
        decision = super().allocate(allocation_inputs=allocation_inputs)
        approved_by_node: dict[str, list[TransferRequest]] = {}
        for transfer in decision.approved_transfers:
            node = self._node_by_incoming_link_id.get(transfer.upstream_link_id)
            if node is not None:
                approved_by_node.setdefault(node.node_id, []).append(transfer)
        self._last_lane_group_allocation_traces = tuple(
            self._extension_trace(
                allocation_input,
                tuple(approved_by_node.get(allocation_input.node_id, ())),
            )
            for allocation_input in allocation_inputs
            if (
                self.extension_config.representation_mode
                == EXPLICIT_LANE_GROUP_FIFO
                and allocation_input.node_id in self._groups_by_node_id
            )
        )
        return decision

    def _respects_junction_fifo(
        self,
        candidate: TransferRequest,
        candidate_movement: MovementSpec,
        approved_packet_ids: set[str],
        allocation_input: JunctionAllocationInput,
    ) -> bool:
        mode = self.extension_config.representation_mode
        if mode == SHARED_LINK_FIFO:
            return self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                allocation_input.packet_ids_by_upstream_link,
                allocation_input.queued_downstream_by_packet_id,
            )
        if mode == EXPLICIT_LANE_GROUP_FIFO:
            if allocation_input.node_id not in self._groups_by_node_id:
                return self._respects_upstream_fifo(
                    candidate,
                    approved_packet_ids,
                    allocation_input.packet_ids_by_upstream_link,
                    allocation_input.queued_downstream_by_packet_id,
                )
            return self._respects_explicit_group_fifo(
                candidate,
                approved_packet_ids,
                allocation_input,
            )

        # This is the frozen partial-by-movement rule with the mode selected by
        # experiment config rather than by mutating JunctionSpec.
        junction_spec = allocation_input.junction_spec
        if junction_spec is None:
            return self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                allocation_input.packet_ids_by_upstream_link,
                allocation_input.queued_downstream_by_packet_id,
            )
        packet_ids = allocation_input.packet_ids_by_upstream_link.get(
            candidate.upstream_link_id,
            (),
        )
        request_by_packet_id = {
            request.packet_id: request
            for request in allocation_input.transfer_requests
        }
        try:
            position = packet_ids.index(candidate.packet_id)
        except ValueError:
            return False
        for packet_id_ahead in packet_ids[:position]:
            if packet_id_ahead in approved_packet_ids:
                continue
            ahead_request = request_by_packet_id.get(packet_id_ahead)
            if ahead_request is None:
                return False
            ahead_movement = junction_spec.movement_by_id.get(
                ahead_request.movement_id
            )
            if ahead_movement is None:
                return False
            if self._movements_are_coupled(
                candidate_movement,
                ahead_movement,
                junction_spec,
            ):
                return False
        return True

    def _choose_movement_transfers(
        self,
        *,
        allocation_input: JunctionAllocationInput,
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
    ) -> tuple[TransferRequest, ...]:
        if (
            self.extension_config.representation_mode != EXPLICIT_LANE_GROUP_FIFO
            or allocation_input.node_id not in self._groups_by_node_id
        ):
            return super()._choose_movement_transfers(
                allocation_input=allocation_input,
                remaining_slots=remaining_slots,
                approved_packet_ids=approved_packet_ids,
            )

        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        self._assign_first_eligible_packets(allocation_input)
        remaining_conflict = self._conflict_resource_capacity(allocation_input)
        remaining_group = {
            lane_group.lane_group_id: lane_group.service_capacity_per_tick
            for lane_group in self._groups_by_node_id[allocation_input.node_id]
        }
        requests_by_movement: dict[str, list[TransferRequest]] = {
            movement.movement_id: [] for movement in junction_spec.movement_specs
        }
        for request in sorted(
            allocation_input.transfer_requests,
            key=self._candidate_sort_key,
        ):
            if request.movement_id in requests_by_movement:
                requests_by_movement[request.movement_id].append(request)

        for downstream_link_id in sorted(junction_spec.outgoing_link_ids):
            active = tuple(
                movement
                for movement in junction_spec.movement_specs
                if movement.downstream_link_id == downstream_link_id
                and requests_by_movement[movement.movement_id]
            )
            available_slots = remaining_slots.get(downstream_link_id, 0)
            if not active or available_slots <= 0:
                continue
            weight_total = sum(movement.priority_weight for movement in active)
            for movement in active:
                self._movement_deficit_by_node_movement[
                    (allocation_input.node_id, movement.movement_id)
                ] += (movement.priority_weight / weight_total) * available_slots

        movement_order = self._movement_order_by_node_id[allocation_input.node_id]
        priority_index = {
            movement_id: index
            for index, movement_id in enumerate(movement_order)
        }
        approved: list[TransferRequest] = []
        approved_ids = set(approved_packet_ids)
        while True:
            selectable: list[
                tuple[
                    float,
                    int,
                    tuple[int, int, str],
                    TransferRequest,
                    MovementSpec,
                    str,
                ]
            ] = []
            for movement_id in movement_order:
                movement = junction_spec.movement_by_id[movement_id]
                if remaining_slots.get(movement.downstream_link_id, 0) <= 0:
                    continue
                if not self._movement_runtime_open(movement, allocation_input):
                    continue
                request = self._first_fifo_request(
                    requests=requests_by_movement[movement_id],
                    approved_packet_ids=approved_ids,
                    allocation_input=allocation_input,
                    candidate_movement=movement,
                )
                if request is None:
                    continue
                lane_group_id = self._assignment_by_node_packet[
                    (allocation_input.node_id, request.packet_id)
                ]
                if remaining_group[lane_group_id] <= 0:
                    continue
                if not self._conflict_resources_available_for_movement(
                    movement,
                    remaining_conflict,
                ):
                    continue
                selectable.append(
                    (
                        self._movement_deficit_by_node_movement[
                            (allocation_input.node_id, movement_id)
                        ],
                        -priority_index[movement_id],
                        tuple(
                            -value
                            for value in self._candidate_sort_key(request)[:2]
                        )
                        + (request.packet_id,),
                        request,
                        movement,
                        lane_group_id,
                    )
                )
            if not selectable:
                break
            _, _, _, request, movement, lane_group_id = max(
                selectable,
                key=lambda item: (item[0], item[1], item[2]),
            )
            approved.append(request)
            approved_ids.add(request.packet_id)
            self._movement_deficit_by_node_movement[
                (allocation_input.node_id, movement.movement_id)
            ] -= 1
            remaining_slots[request.downstream_link_id] -= 1
            remaining_group[lane_group_id] -= 1
            for resource_id in movement.conflict_resource_ids:
                remaining_conflict[resource_id] -= 1
        return tuple(approved)

    def _rejected_transfers(
        self,
        transfer_requests: tuple[TransferRequest, ...],
        approved_transfers: tuple[TransferRequest, ...],
        remaining_slots: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
        approved_packet_ids: set[str],
        *,
        junction_spec=None,
        allocation_input: JunctionAllocationInput | None = None,
    ) -> tuple[RejectedTransfer, ...]:
        if (
            self.extension_config.representation_mode != EXPLICIT_LANE_GROUP_FIFO
            or allocation_input is None
            or allocation_input.node_id not in self._groups_by_node_id
        ):
            return super()._rejected_transfers(
                transfer_requests,
                approved_transfers,
                remaining_slots,
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
                approved_packet_ids,
                junction_spec=junction_spec,
                allocation_input=allocation_input,
            )
        assert junction_spec is not None
        approved_set = set(approved_transfers)
        remaining_conflict = self._conflict_resource_capacity_after_approved(
            allocation_input,
            approved_transfers,
        )
        remaining_group = {
            lane_group.lane_group_id: lane_group.service_capacity_per_tick
            for lane_group in self._groups_by_node_id[allocation_input.node_id]
        }
        for transfer in approved_transfers:
            remaining_group[
                self._assignment_by_node_packet[
                    (allocation_input.node_id, transfer.packet_id)
                ]
            ] -= 1
        approved_ids = set(approved_packet_ids) | {
            transfer.packet_id for transfer in approved_transfers
        }
        rejected: list[RejectedTransfer] = []
        for request in transfer_requests:
            if request in approved_set:
                continue
            movement = junction_spec.movement_by_id.get(request.movement_id)
            if movement is None:
                reason = REJECTED_MOVEMENT_UNDECLARED
            elif request.movement_id in allocation_input.closed_movement_ids:
                reason = REJECTED_GOVERNANCE_CLOSED
            elif (
                movement.signal_group_id is not None
                and movement.signal_group_id
                not in allocation_input.open_signal_group_ids
            ):
                reason = REJECTED_SIGNAL_CLOSED
            elif not self._respects_junction_fifo(
                request,
                movement,
                approved_ids,
                allocation_input,
            ):
                reason = REJECTED_UPSTREAM_FIFO
            elif not self._conflict_resources_available_for_movement(
                movement,
                remaining_conflict,
            ):
                reason = REJECTED_CONFLICT_RESOURCE_CAPACITY
            elif remaining_group[
                self._assignment_by_node_packet[
                    (allocation_input.node_id, request.packet_id)
                ]
            ] <= 0:
                reason = REJECTED_LANE_GROUP_CAPACITY
            elif remaining_slots.get(request.downstream_link_id, 0) <= 0:
                reason = REJECTED_DOWNSTREAM_SUPPLY
            else:
                reason = REJECTED_NOT_SELECTED
            rejected.append(RejectedTransfer(request, reason))
        return tuple(rejected)

    def _assign_first_eligible_packets(
        self,
        allocation_input: JunctionAllocationInput,
    ) -> None:
        lane_groups = self._groups_by_node_id[allocation_input.node_id]
        declaration_index = {
            lane_group.lane_group_id: index
            for index, lane_group in enumerate(lane_groups)
        }
        current_packet_ids = {
            request.packet_id for request in allocation_input.transfer_requests
        }
        queue_length = {
            lane_group.lane_group_id: 0 for lane_group in lane_groups
        }
        for packet_id in current_packet_ids:
            retained = self._assignment_by_node_packet.get(
                (allocation_input.node_id, packet_id)
            )
            if retained in queue_length:
                queue_length[retained] += 1
        for request in sorted(
            allocation_input.transfer_requests,
            key=self._candidate_sort_key,
        ):
            key = (allocation_input.node_id, request.packet_id)
            if key in self._assignment_by_node_packet:
                continue
            compatible = self._groups_by_node_movement.get(
                (allocation_input.node_id, request.movement_id),
                (),
            )
            if not compatible:
                continue
            selected = min(
                compatible,
                key=lambda lane_group: (
                    queue_length[lane_group.lane_group_id],
                    declaration_index[lane_group.lane_group_id],
                    lane_group.lane_group_id,
                ),
            )
            self._assignment_by_node_packet[key] = selected.lane_group_id
            queue_length[selected.lane_group_id] += 1

    def _respects_explicit_group_fifo(
        self,
        candidate: TransferRequest,
        approved_packet_ids: set[str],
        allocation_input: JunctionAllocationInput,
    ) -> bool:
        assigned = self._assignment_by_node_packet.get(
            (allocation_input.node_id, candidate.packet_id)
        )
        if assigned is None:
            return False
        packet_ids = allocation_input.packet_ids_by_upstream_link.get(
            candidate.upstream_link_id,
            (),
        )
        try:
            position = packet_ids.index(candidate.packet_id)
        except ValueError:
            return False
        return not any(
            packet_id not in approved_packet_ids
            and self._assignment_by_node_packet.get(
                (allocation_input.node_id, packet_id)
            )
            == assigned
            for packet_id in packet_ids[:position]
        )

    def _extension_trace(
        self,
        allocation_input: JunctionAllocationInput,
        approved: tuple[TransferRequest, ...],
    ) -> LaneGroupAllocationTrace:
        assignments = tuple(
            (
                request.packet_id,
                self._assignment_by_node_packet[
                    (allocation_input.node_id, request.packet_id)
                ],
            )
            for request in sorted(
                allocation_input.transfer_requests,
                key=self._candidate_sort_key,
            )
            if (
                allocation_input.node_id,
                request.packet_id,
            )
            in self._assignment_by_node_packet
        )
        queue_lengths = {
            lane_group.lane_group_id: 0
            for lane_group in self._groups_by_node_id[allocation_input.node_id]
        }
        for _, lane_group_id in assignments:
            queue_lengths[lane_group_id] += 1
        return LaneGroupAllocationTrace(
            node_id=allocation_input.node_id,
            representation_mode=self.extension_config.representation_mode,
            packet_assignments=assignments,
            assigned_queue_lengths=tuple(
                (lane_group.lane_group_id, queue_lengths[lane_group.lane_group_id])
                for lane_group in self._groups_by_node_id[allocation_input.node_id]
            ),
            approved_packet_lane_groups=tuple(
                (
                    transfer.packet_id,
                    self._assignment_by_node_packet[
                        (allocation_input.node_id, transfer.packet_id)
                    ],
                )
                for transfer in approved
            ),
        )


def build_lane_group_allocator(
    nodes: Iterable[Node],
    config: LaneGroupExtensionConfig,
) -> LaneGroupExtensionAllocator:
    """Build the selected ablation allocator without modifying frozen topology."""

    return LaneGroupExtensionAllocator(tuple(nodes), config)


class LaneGroupLoadingEngine(LoadingEngine):
    """Opt-in engine shell that materializes queued exits by lane-group FIFO.

    All physical event creation, link state, LTM mathematics, and integrity
    folds remain owned by ``LoadingEngine``.  This subclass only replaces the
    frozen global upstream-queue head check with an assigned-group head check
    immediately before a queued transfer.
    """

    def __init__(
        self,
        *,
        links,
        nodes: tuple[Node, ...],
        lane_group_config: LaneGroupExtensionConfig,
        **engine_kwargs,
    ) -> None:
        if "node_transfer_policy" in engine_kwargs:
            raise ValueError(
                "LaneGroupLoadingEngine owns node_transfer_policy"
            )
        allocator = LaneGroupExtensionAllocator(nodes, lane_group_config)
        super().__init__(
            links=links,
            nodes=nodes,
            node_transfer_policy=allocator,
            **engine_kwargs,
        )
        self.lane_group_config = lane_group_config

    @property
    def lane_group_allocator(self) -> LaneGroupExtensionAllocator:
        allocator = self.movement_allocator
        assert isinstance(allocator, LaneGroupExtensionAllocator)
        return allocator

    def _prevalidate_link_to_link_transfer(
        self,
        *,
        packet_id: str,
        upstream_link_id: str,
        downstream_link_id: str,
        queue_boundary_id: str | None = None,
    ) -> None:
        if (
            queue_boundary_id is None
            or self.lane_group_config.representation_mode
            != EXPLICIT_LANE_GROUP_FIFO
        ):
            return super()._prevalidate_link_to_link_transfer(
                packet_id=packet_id,
                upstream_link_id=upstream_link_id,
                downstream_link_id=downstream_link_id,
                queue_boundary_id=queue_boundary_id,
            )
        node = self._node_by_incoming_link_id.get(upstream_link_id)
        if node is None or not self.lane_group_allocator.has_explicit_groups(
            node.node_id
        ):
            return super()._prevalidate_link_to_link_transfer(
                packet_id=packet_id,
                upstream_link_id=upstream_link_id,
                downstream_link_id=downstream_link_id,
                queue_boundary_id=queue_boundary_id,
            )
        assigned = self.lane_group_allocator.assigned_lane_group(
            node.node_id,
            packet_id,
        )
        if assigned is None:
            raise EventCacheConsistencyError(
                f"queued packet_id {packet_id} has no explicit lane-group assignment"
            )
        upstream_queue = self._queued_packet_ids_by_upstream_link.get(
            upstream_link_id
        )
        if not upstream_queue or packet_id not in upstream_queue:
            raise EventCacheConsistencyError(
                f"queued packet_id {packet_id} is absent from upstream queue "
                f"{upstream_link_id}"
            )
        original_order = tuple(upstream_queue)
        position = original_order.index(packet_id)
        for packet_id_ahead in original_order[:position]:
            if (
                self.lane_group_allocator.assigned_lane_group(
                    node.node_id,
                    packet_id_ahead,
                )
                == assigned
            ):
                raise EventCacheConsistencyError(
                    f"packet_id {packet_id} is not first in assigned lane group "
                    f"{assigned}"
                )
        if position:
            upstream_queue.clear()
            upstream_queue.extend(
                (
                    packet_id,
                    *original_order[:position],
                    *original_order[position + 1 :],
                )
            )
        try:
            super()._prevalidate_link_to_link_transfer(
                packet_id=packet_id,
                upstream_link_id=upstream_link_id,
                downstream_link_id=downstream_link_id,
                queue_boundary_id=queue_boundary_id,
            )
        except Exception:
            upstream_queue.clear()
            upstream_queue.extend(original_order)
            raise

    def _queued_packet_ids_by_upstream_link_from_events(
        self,
    ) -> dict[str, tuple[str, ...]]:
        """Fold membership while permitting an explicit-group queue bypass."""

        if (
            self.lane_group_config.representation_mode
            != EXPLICIT_LANE_GROUP_FIFO
        ):
            return super()._queued_packet_ids_by_upstream_link_from_events()
        queues: dict[str, deque[str]] = {}
        for event in self._event_log:
            if event.event_type == EventType.QUEUE_ENTRY:
                upstream_link_id, _ = self._parse_boundary_id(event.entity_id)
                queues.setdefault(upstream_link_id, deque()).append(event.packet_id)
            elif event.event_type == EventType.QUEUE_EXIT:
                upstream_link_id, _ = self._parse_boundary_id(event.entity_id)
                queue = queues.setdefault(upstream_link_id, deque())
                try:
                    queue.remove(event.packet_id)
                except ValueError as exc:
                    raise EventCacheConsistencyError(
                        f"packet_id {event.packet_id} exits upstream queue "
                        f"{upstream_link_id} without queue entry"
                    ) from exc
        return {
            link_id: tuple(packet_ids)
            for link_id, packet_ids in queues.items()
            if packet_ids
        }
