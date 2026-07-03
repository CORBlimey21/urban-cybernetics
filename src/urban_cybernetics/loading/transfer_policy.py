"""Movement-allocation abstractions for junction transfer decisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from urban_cybernetics.core.node import (
    JUNCTION_FIFO_PARTIAL_BY_MOVEMENT,
    JUNCTION_FIFO_STRICT,
    PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO,
    JunctionSpec,
    MovementSpec,
    Node,
    movement_id,
)


STAGE1_MOVEMENT_ALLOCATOR_ID = "uc_movement_allocator_stage1_v1"
STAGE2_MOVEMENT_ALLOCATOR_ID = "uc_movement_allocator_stage2_v1"
REJECTED_DOWNSTREAM_SUPPLY = "downstream_supply_unavailable"
REJECTED_UPSTREAM_FIFO = "upstream_fifo_blocked"
REJECTED_MOVEMENT_UNDECLARED = "movement_not_declared"
REJECTED_NOT_SELECTED = "not_selected_this_tick"
REJECTED_CONFLICT_RESOURCE_CAPACITY = "conflict_resource_capacity_unavailable"
REJECTED_LANE_GROUP_CAPACITY = "lane_group_capacity_unavailable"
REJECTED_SIGNAL_CLOSED = "signal_gate_closed"
REJECTED_GOVERNANCE_CLOSED = "governance_gate_closed"
UNSUPPORTED_ADAPTIVE_CONTROL = "adaptive_control_unsupported"


@dataclass(frozen=True, slots=True)
class TransferRequest:
    """Immutable request for one packet to execute one movement this tick."""

    packet_id: str
    upstream_link_id: str
    downstream_link_id: str
    boundary_id: str
    eligibility_tick: int
    eligibility_sequence_number: int
    queued: bool = False
    node_id: str | None = None
    movement_id: str = ""

    def __post_init__(self) -> None:
        if not self.movement_id:
            object.__setattr__(
                self,
                "movement_id",
                movement_id(self.upstream_link_id, self.downstream_link_id),
            )


TransferCandidate = TransferRequest


@dataclass(frozen=True, slots=True)
class RejectedTransfer:
    """A transfer request that was not approved and the allocator reason."""

    transfer_request: TransferRequest
    reason: str


@dataclass(frozen=True, slots=True)
class MovementFlowSummary:
    """Per-movement request and approval summary for one allocation decision."""

    movement_id: str
    upstream_link_id: str
    downstream_link_id: str
    requested_count: int
    approved_count: int
    rejected_count: int


@dataclass(frozen=True, slots=True)
class AllocationTrace:
    """Read-only replay evidence for one junction allocation decision."""

    node_id: str
    allocator_id: str
    candidate_packet_ids: tuple[str, ...]
    approved_packet_ids: tuple[str, ...]
    rejected_transfer_reasons: tuple[tuple[str, str], ...]
    receiving_slots_by_downstream_link: tuple[tuple[str, int], ...]
    movement_flow_summaries: tuple[MovementFlowSummary, ...]
    conflict_resource_capacity_by_id: tuple[tuple[str, int], ...] = ()
    lane_group_capacity_by_id: tuple[tuple[str, int], ...] = ()
    open_signal_group_ids: tuple[str, ...] = ()
    closed_movement_ids: tuple[str, ...] = ()
    priority_deficit_by_movement_id: tuple[tuple[str, float], ...] = ()

    @property
    def node_model(self) -> str:
        """Compatibility label for older trace readers."""

        return "movement_allocation"

    @property
    def merge_deficit_by_incoming_link_id(self) -> tuple[tuple[str, float], ...]:
        """Compatibility view for older declared-priority merge traces."""

        return self.priority_deficit_by_movement_id


NodeTransferTrace = AllocationTrace


@dataclass(frozen=True, slots=True)
class JunctionAllocationInput:
    """Loading-owned allocation problem for one junction and tick."""

    node_id: str
    junction_spec: JunctionSpec | None
    transfer_requests: tuple[TransferRequest, ...]
    receiving_slots_by_downstream_link: Mapping[str, int]
    packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]]
    queued_downstream_by_packet_id: Mapping[str, str]
    conflict_resource_capacity_by_id: Mapping[str, int] | None = None
    lane_group_capacity_by_id: Mapping[str, int] | None = None
    open_signal_group_ids: frozenset[str] = frozenset()
    closed_movement_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class JunctionAllocationDecision:
    """Allocator output consumed by loading to execute canonical events."""

    approved_transfers: tuple[TransferRequest, ...]
    rejected_transfers: tuple[RejectedTransfer, ...]
    movement_flow_summaries: tuple[MovementFlowSummary, ...]
    updated_allocator_state: tuple[tuple[str, float], ...]
    allocation_traces: tuple[AllocationTrace, ...]


class NodeTransferPolicy(Protocol):
    """Legacy transfer-policy interface retained for comparison paths."""

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferRequest, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferRequest, ...]:
        """Return immutable requests the engine may execute this tick."""


class MovementAllocator(Protocol):
    """General movement allocation interface for production parity loading."""

    @property
    def last_allocation_traces(self) -> tuple[AllocationTrace, ...]:
        """Return allocation traces from the most recent allocation."""

    def allocate(
        self,
        *,
        allocation_inputs: tuple[JunctionAllocationInput, ...],
    ) -> JunctionAllocationDecision:
        """Return an allocation decision for the current loading tick."""


class StrictFIFOJunctionPolicy:
    """Legacy FIFO policy that forbids bypassing packets ahead on a link."""

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferRequest, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferRequest, ...]:
        approved_candidates: list[TransferRequest] = []
        approved_packet_ids: set[str] = set()
        blocked_upstream_link_ids: set[str] = set()
        remaining_slots = dict(receiving_slots_by_downstream_link)

        for candidate in sorted(candidates, key=self._candidate_sort_key):
            if candidate.upstream_link_id in blocked_upstream_link_ids:
                continue
            if not self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
            ):
                continue
            if remaining_slots.get(candidate.downstream_link_id, 0) <= 0:
                blocked_upstream_link_ids.add(candidate.upstream_link_id)
                continue

            approved_candidates.append(candidate)
            approved_packet_ids.add(candidate.packet_id)
            remaining_slots[candidate.downstream_link_id] -= 1

        return tuple(approved_candidates)

    @staticmethod
    def _candidate_sort_key(candidate: TransferRequest) -> tuple[int, int, str]:
        return (
            candidate.eligibility_tick,
            candidate.eligibility_sequence_number,
            candidate.packet_id,
        )

    def _respects_upstream_fifo(
        self,
        candidate: TransferRequest,
        approved_packet_ids: set[str],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> bool:
        packet_ids_on_upstream_link = packet_ids_by_upstream_link.get(
            candidate.upstream_link_id,
            (),
        )
        try:
            packet_position = packet_ids_on_upstream_link.index(candidate.packet_id)
        except ValueError:
            return False

        for packet_id_ahead in packet_ids_on_upstream_link[:packet_position]:
            if packet_id_ahead in approved_packet_ids:
                continue
            if queued_downstream_by_packet_id.get(packet_id_ahead) is not None:
                return False
            return False
        return True


class GlobalFIFOMergePolicy(StrictFIFOJunctionPolicy):
    """Legacy global FIFO allocation policy for comparison/regression runs."""


class GeneralMovementAllocator(StrictFIFOJunctionPolicy):
    """Stage 2 movement allocator for declarative junction specifications."""

    allocator_id = STAGE2_MOVEMENT_ALLOCATOR_ID

    def __init__(self, nodes: Iterable[Node]) -> None:
        self._nodes = tuple(nodes)
        self._junction_spec_by_node_id: dict[str, JunctionSpec] = {}
        self._node_by_incoming_link_id: dict[str, Node] = {}
        self._movement_by_node_and_links: dict[
            tuple[str, str, str],
            MovementSpec,
        ] = {}
        self._movement_order_by_node_id: dict[str, tuple[str, ...]] = {}
        self._lane_group_ids_by_junction_spec_id: dict[
            int,
            dict[str, tuple[str, ...]],
        ] = {}
        self._movement_deficit_by_node_movement: dict[tuple[str, str], float] = {}
        self._last_allocation_traces: tuple[AllocationTrace, ...] = ()
        self._validate_nodes()

    @property
    def last_allocation_traces(self) -> tuple[AllocationTrace, ...]:
        """Return movement-allocation traces from the most recent allocation."""

        return self._last_allocation_traces

    @property
    def last_transfer_traces(self) -> tuple[AllocationTrace, ...]:
        """Compatibility alias for older node-transfer trace readers."""

        return self._last_allocation_traces

    def allocate(
        self,
        *,
        allocation_inputs: tuple[JunctionAllocationInput, ...],
    ) -> JunctionAllocationDecision:
        approved_transfers: list[TransferRequest] = []
        rejected_transfers: list[RejectedTransfer] = []
        movement_summaries: list[MovementFlowSummary] = []
        traces: list[AllocationTrace] = []
        approved_packet_ids: set[str] = set()
        remaining_slots = (
            dict(allocation_inputs[0].receiving_slots_by_downstream_link)
            if allocation_inputs
            else {}
        )

        for allocation_input in allocation_inputs:
            node_decision = self._allocate_one_junction(
                allocation_input,
                remaining_slots=remaining_slots,
                approved_packet_ids=approved_packet_ids,
            )
            approved_transfers.extend(node_decision.approved_transfers)
            rejected_transfers.extend(node_decision.rejected_transfers)
            movement_summaries.extend(node_decision.movement_flow_summaries)
            traces.extend(node_decision.allocation_traces)
            for transfer in node_decision.approved_transfers:
                approved_packet_ids.add(transfer.packet_id)

        self._last_allocation_traces = tuple(traces)
        return JunctionAllocationDecision(
            approved_transfers=tuple(approved_transfers),
            rejected_transfers=tuple(rejected_transfers),
            movement_flow_summaries=tuple(movement_summaries),
            updated_allocator_state=tuple(
                (f"{node_id}:{movement_id_value}", deficit)
                for (node_id, movement_id_value), deficit in sorted(
                    self._movement_deficit_by_node_movement.items()
                )
            ),
            allocation_traces=tuple(traces),
        )

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferRequest, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferRequest, ...]:
        """Compatibility adapter for callers that have not built allocation inputs."""

        allocation_inputs = self._allocation_inputs_from_flat_candidates(
            candidates=candidates,
            receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
            packet_ids_by_upstream_link=packet_ids_by_upstream_link,
            queued_downstream_by_packet_id=queued_downstream_by_packet_id,
        )
        return self.allocate(allocation_inputs=allocation_inputs).approved_transfers

    def _validate_nodes(self) -> None:
        for node in self._nodes:
            if node.node_model == PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO:
                raise ValueError(
                    f"unsupported movement allocation node {node.node_id}: "
                    "legacy_global_fifo is not parity movement evidence"
                )
            junction_spec = node.junction_spec
            assert junction_spec is not None
            self._validate_stage2_junction_spec(junction_spec)
            self._junction_spec_by_node_id[node.node_id] = junction_spec
            for incoming_link_id in node.incoming_link_ids:
                if incoming_link_id in self._node_by_incoming_link_id:
                    raise ValueError(
                        f"incoming link {incoming_link_id} belongs to multiple junctions"
                    )
                self._node_by_incoming_link_id[incoming_link_id] = node
            movement_order = tuple(
                movement.movement_id for movement in junction_spec.movement_specs
            )
            self._movement_order_by_node_id[node.node_id] = movement_order
            self._lane_group_ids_by_junction_spec_id[id(junction_spec)] = (
                junction_spec.lane_group_ids_by_movement_id
            )
            for movement in junction_spec.movement_specs:
                self._movement_by_node_and_links[
                    (
                        node.node_id,
                        movement.upstream_link_id,
                        movement.downstream_link_id,
                    )
                ] = movement
                self._movement_deficit_by_node_movement[
                    (node.node_id, movement.movement_id)
                ] = 0.0

    def _validate_stage2_junction_spec(self, junction_spec: JunctionSpec) -> None:
        unsupported_reasons: list[str] = []
        if "adaptive_control" in junction_spec.governance_refs:
            unsupported_reasons.append(UNSUPPORTED_ADAPTIVE_CONTROL)
        for movement in junction_spec.movement_specs:
            if ("adaptive_control", "true") in movement.provenance:
                unsupported_reasons.append(UNSUPPORTED_ADAPTIVE_CONTROL)
        if unsupported_reasons:
            unique_reasons = tuple(dict.fromkeys(unsupported_reasons))
            raise ValueError(
                f"unsupported Stage 2 junction semantics for {junction_spec.node_id}: "
                f"{unique_reasons}"
            )

    def _allocation_inputs_from_flat_candidates(
        self,
        *,
        candidates: tuple[TransferRequest, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[JunctionAllocationInput, ...]:
        candidates_by_node_id: dict[str, list[TransferRequest]] = {}
        fallback_candidates: list[TransferRequest] = []
        for candidate in candidates:
            node = self._node_by_incoming_link_id.get(candidate.upstream_link_id)
            if node is None:
                fallback_candidates.append(candidate)
                continue
            candidates_by_node_id.setdefault(node.node_id, []).append(candidate)

        allocation_inputs: list[JunctionAllocationInput] = []
        for node in sorted(self._nodes, key=lambda item: item.node_id):
            node_candidates = tuple(candidates_by_node_id.get(node.node_id, ()))
            if not node_candidates:
                continue
            allocation_inputs.append(
                JunctionAllocationInput(
                    node_id=node.node_id,
                    junction_spec=self._junction_spec_by_node_id[node.node_id],
                    transfer_requests=node_candidates,
                    receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            )
        if fallback_candidates:
            allocation_inputs.append(
                JunctionAllocationInput(
                    node_id="__implicit_junction__",
                    junction_spec=None,
                    transfer_requests=tuple(fallback_candidates),
                    receiving_slots_by_downstream_link=receiving_slots_by_downstream_link,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            )
        return tuple(allocation_inputs)

    def _allocate_one_junction(
        self,
        allocation_input: JunctionAllocationInput,
        *,
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
    ) -> JunctionAllocationDecision:
        if allocation_input.junction_spec is None:
            approved = self._choose_strict_fifo_transfers(
                candidates=allocation_input.transfer_requests,
                remaining_slots=remaining_slots,
                approved_packet_ids=approved_packet_ids,
                packet_ids_by_upstream_link=allocation_input.packet_ids_by_upstream_link,
                queued_downstream_by_packet_id=(
                    allocation_input.queued_downstream_by_packet_id
                ),
            )
            rejected = self._rejected_transfers(
                allocation_input.transfer_requests,
                approved,
                remaining_slots,
                allocation_input.packet_ids_by_upstream_link,
                allocation_input.queued_downstream_by_packet_id,
                approved_packet_ids,
            )
            summaries = self._movement_flow_summaries(
                allocation_input.transfer_requests,
                approved,
            )
            trace = self._allocation_trace(
                allocation_input=allocation_input,
                approved_transfers=approved,
                rejected_transfers=rejected,
                remaining_slots=remaining_slots,
                movement_flow_summaries=summaries,
            )
            return JunctionAllocationDecision(
                approved_transfers=approved,
                rejected_transfers=rejected,
                movement_flow_summaries=summaries,
                updated_allocator_state=(),
                allocation_traces=(trace,),
            )

        approved = self._choose_movement_transfers(
            allocation_input=allocation_input,
            remaining_slots=remaining_slots,
            approved_packet_ids=approved_packet_ids,
        )
        rejected = self._rejected_transfers(
            allocation_input.transfer_requests,
            approved,
            remaining_slots,
            allocation_input.packet_ids_by_upstream_link,
            allocation_input.queued_downstream_by_packet_id,
            approved_packet_ids,
            junction_spec=allocation_input.junction_spec,
            allocation_input=allocation_input,
        )
        summaries = self._movement_flow_summaries(
            allocation_input.transfer_requests,
            approved,
        )
        trace = self._allocation_trace(
            allocation_input=allocation_input,
            approved_transfers=approved,
            rejected_transfers=rejected,
            remaining_slots=remaining_slots,
            movement_flow_summaries=summaries,
        )
        return JunctionAllocationDecision(
            approved_transfers=approved,
            rejected_transfers=rejected,
            movement_flow_summaries=summaries,
            updated_allocator_state=tuple(
                (movement_id_value, deficit)
                for (node_id, movement_id_value), deficit in sorted(
                    self._movement_deficit_by_node_movement.items()
                )
                if node_id == allocation_input.node_id
            ),
            allocation_traces=(trace,),
        )

    def _choose_movement_transfers(
        self,
        *,
        allocation_input: JunctionAllocationInput,
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
    ) -> tuple[TransferRequest, ...]:
        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        remaining_conflict_capacity = self._conflict_resource_capacity(
            allocation_input,
        )
        remaining_lane_capacity = self._lane_group_capacity(allocation_input)
        requests_by_movement_id: dict[str, list[TransferRequest]] = {
            movement.movement_id: []
            for movement in junction_spec.movement_specs
        }
        movement_by_id = junction_spec.movement_by_id
        for request in sorted(
            allocation_input.transfer_requests,
            key=self._candidate_sort_key,
        ):
            movement = movement_by_id.get(request.movement_id)
            if movement is None:
                continue
            requests_by_movement_id[movement.movement_id].append(request)

        for downstream_link_id in sorted(junction_spec.outgoing_link_ids):
            active_movements = tuple(
                movement
                for movement in junction_spec.movement_specs
                if movement.downstream_link_id == downstream_link_id
                and requests_by_movement_id.get(movement.movement_id)
            )
            if not active_movements:
                continue
            available_slots = remaining_slots.get(downstream_link_id, 0)
            if available_slots <= 0:
                continue
            active_weight_total = sum(
                movement.priority_weight for movement in active_movements
            )
            for movement in active_movements:
                self._movement_deficit_by_node_movement[
                    (allocation_input.node_id, movement.movement_id)
                ] += (movement.priority_weight / active_weight_total) * available_slots

        approved_transfers: list[TransferRequest] = []
        approved_packet_ids_for_node = set(approved_packet_ids)
        while True:
            selectable = self._selectable_movement_requests(
                allocation_input=allocation_input,
                requests_by_movement_id=requests_by_movement_id,
                approved_packet_ids=approved_packet_ids_for_node,
                remaining_slots=remaining_slots,
                remaining_conflict_capacity=remaining_conflict_capacity,
                remaining_lane_capacity=remaining_lane_capacity,
            )
            if not selectable:
                break
            _, _, _, request, movement = max(
                selectable,
                key=lambda item: (item[0], item[1], item[2]),
            )
            approved_transfers.append(request)
            approved_packet_ids_for_node.add(request.packet_id)
            self._movement_deficit_by_node_movement[
                (allocation_input.node_id, movement.movement_id)
            ] -= 1
            remaining_slots[request.downstream_link_id] -= 1
            self._consume_movement_resources(
                movement,
                junction_spec,
                remaining_conflict_capacity,
                remaining_lane_capacity,
            )
        return tuple(approved_transfers)

    def _selectable_movement_requests(
        self,
        *,
        allocation_input: JunctionAllocationInput,
        requests_by_movement_id: Mapping[str, list[TransferRequest]],
        approved_packet_ids: set[str],
        remaining_slots: Mapping[str, int],
        remaining_conflict_capacity: Mapping[str, int],
        remaining_lane_capacity: Mapping[str, int],
    ) -> list[tuple[float, int, tuple[int, int, str], TransferRequest, MovementSpec]]:
        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        selectable: list[
            tuple[float, int, tuple[int, int, str], TransferRequest, MovementSpec]
        ] = []
        movement_order = self._movement_order_by_node_id[allocation_input.node_id]
        priority_index_by_movement = {
            movement_id_value: index
            for index, movement_id_value in enumerate(movement_order)
        }
        movement_by_id = junction_spec.movement_by_id
        for movement_id_value in movement_order:
            movement = movement_by_id[movement_id_value]
            if remaining_slots.get(movement.downstream_link_id, 0) <= 0:
                continue
            if not self._movement_runtime_open(movement, allocation_input):
                continue
            if not self._movement_resources_available(
                movement,
                junction_spec,
                remaining_conflict_capacity,
                remaining_lane_capacity,
            ):
                continue
            request = self._first_fifo_request(
                requests=requests_by_movement_id.get(movement_id_value, ()),
                approved_packet_ids=approved_packet_ids,
                allocation_input=allocation_input,
                candidate_movement=movement,
            )
            if request is None:
                continue
            selectable.append(
                (
                    self._movement_deficit_by_node_movement[
                        (allocation_input.node_id, movement_id_value)
                    ],
                    -priority_index_by_movement[movement_id_value],
                    tuple(-value for value in self._candidate_sort_key(request)[:2])
                    + (request.packet_id,),
                    request,
                    movement,
                )
            )
        return selectable

    def _first_fifo_request(
        self,
        *,
        requests: Iterable[TransferRequest],
        approved_packet_ids: set[str],
        allocation_input: JunctionAllocationInput,
        candidate_movement: MovementSpec,
    ) -> TransferRequest | None:
        for request in requests:
            if request.packet_id in approved_packet_ids:
                continue
            if self._respects_junction_fifo(
                request,
                candidate_movement,
                approved_packet_ids,
                allocation_input,
            ):
                return request
            return None
        return None

    def _respects_junction_fifo(
        self,
        candidate: TransferRequest,
        candidate_movement: MovementSpec,
        approved_packet_ids: set[str],
        allocation_input: JunctionAllocationInput,
    ) -> bool:
        junction_spec = allocation_input.junction_spec
        if junction_spec is None or junction_spec.fifo_policy == JUNCTION_FIFO_STRICT:
            return self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                allocation_input.packet_ids_by_upstream_link,
                allocation_input.queued_downstream_by_packet_id,
            )

        if junction_spec.fifo_policy != JUNCTION_FIFO_PARTIAL_BY_MOVEMENT:
            raise ValueError(f"unsupported junction fifo_policy: {junction_spec.fifo_policy}")

        packet_ids_on_upstream_link = allocation_input.packet_ids_by_upstream_link.get(
            candidate.upstream_link_id,
            (),
        )
        request_by_packet_id = {
            request.packet_id: request for request in allocation_input.transfer_requests
        }
        movement_by_id = junction_spec.movement_by_id
        try:
            packet_position = packet_ids_on_upstream_link.index(candidate.packet_id)
        except ValueError:
            return False
        for packet_id_ahead in packet_ids_on_upstream_link[:packet_position]:
            if packet_id_ahead in approved_packet_ids:
                continue
            ahead_request = request_by_packet_id.get(packet_id_ahead)
            if ahead_request is None:
                return False
            ahead_movement = movement_by_id.get(ahead_request.movement_id)
            if ahead_movement is None:
                return False
            if self._movements_are_coupled(candidate_movement, ahead_movement, junction_spec):
                return False
        return True

    def _conflict_resource_capacity(
        self,
        allocation_input: JunctionAllocationInput,
    ) -> dict[str, int]:
        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        capacity = junction_spec.conflict_resource_capacity_by_id
        if allocation_input.conflict_resource_capacity_by_id is not None:
            capacity.update(
                self._normalise_runtime_capacity(
                    allocation_input.conflict_resource_capacity_by_id,
                    supported_ids=set(junction_spec.conflict_resource_ids),
                    field_name="conflict_resource_capacity_by_id",
                )
            )
        return capacity

    def _lane_group_capacity(
        self,
        allocation_input: JunctionAllocationInput,
    ) -> dict[str, int]:
        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        capacity = junction_spec.lane_group_capacity_by_id
        if allocation_input.lane_group_capacity_by_id is not None:
            capacity.update(
                self._normalise_runtime_capacity(
                    allocation_input.lane_group_capacity_by_id,
                    supported_ids=set(junction_spec.lane_group_ids),
                    field_name="lane_group_capacity_by_id",
                )
            )
        return capacity

    @staticmethod
    def _normalise_runtime_capacity(
        capacity_by_id: Mapping[str, int],
        *,
        supported_ids: set[str],
        field_name: str,
    ) -> dict[str, int]:
        normalised: dict[str, int] = {}
        for resource_id, capacity in capacity_by_id.items():
            if resource_id not in supported_ids:
                raise ValueError(f"{field_name} references unknown id: {resource_id}")
            if not isinstance(capacity, int):
                raise TypeError(f"{field_name} values must be ints")
            if capacity < 0:
                raise ValueError(f"{field_name} values must be non-negative")
            normalised[resource_id] = capacity
        return normalised

    def _movement_runtime_open(
        self,
        movement: MovementSpec,
        allocation_input: JunctionAllocationInput,
    ) -> bool:
        if movement.movement_id in allocation_input.closed_movement_ids:
            return False
        if (
            movement.signal_group_id is not None
            and movement.signal_group_id not in allocation_input.open_signal_group_ids
        ):
            return False
        return True

    def _movement_resources_available(
        self,
        movement: MovementSpec,
        junction_spec: JunctionSpec,
        remaining_conflict_capacity: Mapping[str, int],
        remaining_lane_capacity: Mapping[str, int],
    ) -> bool:
        for resource_id in movement.conflict_resource_ids:
            if remaining_conflict_capacity.get(resource_id, 0) <= 0:
                return False
        lane_group_ids_by_movement = self._lane_group_ids_by_movement_id(
            junction_spec
        )
        for lane_group_id in lane_group_ids_by_movement[movement.movement_id]:
            if remaining_lane_capacity.get(lane_group_id, 0) <= 0:
                return False
        return True

    def _consume_movement_resources(
        self,
        movement: MovementSpec,
        junction_spec: JunctionSpec,
        remaining_conflict_capacity: dict[str, int],
        remaining_lane_capacity: dict[str, int],
    ) -> None:
        for resource_id in movement.conflict_resource_ids:
            remaining_conflict_capacity[resource_id] -= 1
        lane_group_ids_by_movement = self._lane_group_ids_by_movement_id(
            junction_spec
        )
        for lane_group_id in lane_group_ids_by_movement[movement.movement_id]:
            remaining_lane_capacity[lane_group_id] -= 1

    def _conflict_resource_capacity_after_approved(
        self,
        allocation_input: JunctionAllocationInput,
        approved_transfers: tuple[TransferRequest, ...],
    ) -> dict[str, int]:
        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        remaining = self._conflict_resource_capacity(allocation_input)
        movement_by_id = junction_spec.movement_by_id
        for transfer in approved_transfers:
            movement = movement_by_id.get(transfer.movement_id)
            if movement is None:
                continue
            for resource_id in movement.conflict_resource_ids:
                remaining[resource_id] -= 1
        return remaining

    def _lane_group_capacity_after_approved(
        self,
        allocation_input: JunctionAllocationInput,
        approved_transfers: tuple[TransferRequest, ...],
    ) -> dict[str, int]:
        junction_spec = allocation_input.junction_spec
        assert junction_spec is not None
        remaining = self._lane_group_capacity(allocation_input)
        movement_by_id = junction_spec.movement_by_id
        lane_group_ids_by_movement = self._lane_group_ids_by_movement_id(junction_spec)
        for transfer in approved_transfers:
            movement = movement_by_id.get(transfer.movement_id)
            if movement is None:
                continue
            for lane_group_id in lane_group_ids_by_movement[movement.movement_id]:
                remaining[lane_group_id] -= 1
        return remaining

    @staticmethod
    def _conflict_resources_available_for_movement(
        movement: MovementSpec,
        remaining_conflict_capacity: Mapping[str, int],
    ) -> bool:
        return all(
            remaining_conflict_capacity.get(resource_id, 0) > 0
            for resource_id in movement.conflict_resource_ids
        )

    def _lane_groups_available_for_movement(
        self,
        movement: MovementSpec,
        junction_spec: JunctionSpec,
        remaining_lane_capacity: Mapping[str, int],
    ) -> bool:
        lane_group_ids_by_movement = self._lane_group_ids_by_movement_id(
            junction_spec
        )
        return all(
            remaining_lane_capacity.get(lane_group_id, 0) > 0
            for lane_group_id in lane_group_ids_by_movement[movement.movement_id]
        )

    def _movements_are_coupled(
        self,
        first: MovementSpec,
        second: MovementSpec,
        junction_spec: JunctionSpec,
    ) -> bool:
        if first.movement_id == second.movement_id:
            return True
        if first.downstream_link_id == second.downstream_link_id:
            return True
        if set(first.conflict_resource_ids) & set(second.conflict_resource_ids):
            return True
        lane_groups_by_movement = self._lane_group_ids_by_movement_id(junction_spec)
        return bool(
            set(lane_groups_by_movement[first.movement_id])
            & set(lane_groups_by_movement[second.movement_id])
        )

    def _lane_group_ids_by_movement_id(
        self,
        junction_spec: JunctionSpec,
    ) -> dict[str, tuple[str, ...]]:
        cached = self._lane_group_ids_by_junction_spec_id.get(id(junction_spec))
        if cached is not None:
            return cached
        return junction_spec.lane_group_ids_by_movement_id

    def _choose_strict_fifo_transfers(
        self,
        *,
        candidates: tuple[TransferRequest, ...],
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferRequest, ...]:
        approved_candidates: list[TransferRequest] = []
        blocked_upstream_link_ids: set[str] = set()
        for candidate in sorted(candidates, key=self._candidate_sort_key):
            if candidate.upstream_link_id in blocked_upstream_link_ids:
                continue
            if not self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
            ):
                continue
            if remaining_slots.get(candidate.downstream_link_id, 0) <= 0:
                blocked_upstream_link_ids.add(candidate.upstream_link_id)
                continue
            approved_candidates.append(candidate)
            approved_packet_ids.add(candidate.packet_id)
            remaining_slots[candidate.downstream_link_id] -= 1
        return tuple(approved_candidates)

    def _rejected_transfers(
        self,
        transfer_requests: tuple[TransferRequest, ...],
        approved_transfers: tuple[TransferRequest, ...],
        remaining_slots: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
        approved_packet_ids: set[str],
        *,
        junction_spec: JunctionSpec | None = None,
        allocation_input: JunctionAllocationInput | None = None,
    ) -> tuple[RejectedTransfer, ...]:
        approved_set = set(approved_transfers)
        movement_by_id = junction_spec.movement_by_id if junction_spec else {}
        remaining_conflict_capacity: dict[str, int] = {}
        remaining_lane_capacity: dict[str, int] = {}
        if junction_spec is not None:
            assert allocation_input is not None
            remaining_conflict_capacity = self._conflict_resource_capacity_after_approved(
                allocation_input,
                approved_transfers,
            )
            remaining_lane_capacity = self._lane_group_capacity_after_approved(
                allocation_input,
                approved_transfers,
            )
        rejected: list[RejectedTransfer] = []
        for request in transfer_requests:
            if request in approved_set:
                continue
            if junction_spec is not None and request.movement_id not in movement_by_id:
                reason = REJECTED_MOVEMENT_UNDECLARED
            elif junction_spec is not None and request.movement_id in movement_by_id:
                assert allocation_input is not None
                movement = movement_by_id[request.movement_id]
                if request.movement_id in allocation_input.closed_movement_ids:
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
                    set(approved_packet_ids)
                    | {item.packet_id for item in approved_transfers},
                    allocation_input,
                ):
                    reason = REJECTED_UPSTREAM_FIFO
                elif not self._conflict_resources_available_for_movement(
                    movement,
                    remaining_conflict_capacity,
                ):
                    reason = REJECTED_CONFLICT_RESOURCE_CAPACITY
                elif not self._lane_groups_available_for_movement(
                    movement,
                    junction_spec,
                    remaining_lane_capacity,
                ):
                    reason = REJECTED_LANE_GROUP_CAPACITY
                elif remaining_slots.get(request.downstream_link_id, 0) <= 0:
                    reason = REJECTED_DOWNSTREAM_SUPPLY
                else:
                    reason = REJECTED_NOT_SELECTED
            elif not self._respects_upstream_fifo(
                request,
                set(approved_packet_ids)
                | {item.packet_id for item in approved_transfers},
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
            ):
                reason = REJECTED_UPSTREAM_FIFO
            elif remaining_slots.get(request.downstream_link_id, 0) <= 0:
                reason = REJECTED_DOWNSTREAM_SUPPLY
            else:
                reason = REJECTED_NOT_SELECTED
            rejected.append(RejectedTransfer(request, reason))
        return tuple(rejected)

    def _movement_flow_summaries(
        self,
        transfer_requests: tuple[TransferRequest, ...],
        approved_transfers: tuple[TransferRequest, ...],
    ) -> tuple[MovementFlowSummary, ...]:
        approved_by_movement: dict[str, int] = {}
        requested_by_movement: dict[str, tuple[str, str, int]] = {}
        for request in transfer_requests:
            upstream_link_id, downstream_link_id, count = requested_by_movement.get(
                request.movement_id,
                (request.upstream_link_id, request.downstream_link_id, 0),
            )
            requested_by_movement[request.movement_id] = (
                upstream_link_id,
                downstream_link_id,
                count + 1,
            )
        for transfer in approved_transfers:
            approved_by_movement[transfer.movement_id] = (
                approved_by_movement.get(transfer.movement_id, 0) + 1
            )
        return tuple(
            MovementFlowSummary(
                movement_id=movement_id_value,
                upstream_link_id=upstream_link_id,
                downstream_link_id=downstream_link_id,
                requested_count=requested_count,
                approved_count=approved_by_movement.get(movement_id_value, 0),
                rejected_count=(
                    requested_count - approved_by_movement.get(movement_id_value, 0)
                ),
            )
            for movement_id_value, (
                upstream_link_id,
                downstream_link_id,
                requested_count,
            ) in sorted(requested_by_movement.items())
        )

    def _allocation_trace(
        self,
        *,
        allocation_input: JunctionAllocationInput,
        approved_transfers: tuple[TransferRequest, ...],
        rejected_transfers: tuple[RejectedTransfer, ...],
        remaining_slots: Mapping[str, int],
        movement_flow_summaries: tuple[MovementFlowSummary, ...],
    ) -> AllocationTrace:
        priority_deficits: tuple[tuple[str, float], ...] = ()
        if allocation_input.junction_spec is not None:
            priority_deficits = tuple(
                (
                    movement_id_value,
                    self._movement_deficit_by_node_movement[
                        (allocation_input.node_id, movement_id_value)
                    ],
                )
                for movement_id_value in self._movement_order_by_node_id[
                    allocation_input.node_id
                ]
            )
        return AllocationTrace(
            node_id=allocation_input.node_id,
            allocator_id=self.allocator_id,
            candidate_packet_ids=tuple(
                request.packet_id
                for request in sorted(
                    allocation_input.transfer_requests,
                    key=self._candidate_sort_key,
                )
            ),
            approved_packet_ids=tuple(
                request.packet_id for request in approved_transfers
            ),
            rejected_transfer_reasons=tuple(
                (rejected.transfer_request.packet_id, rejected.reason)
                for rejected in rejected_transfers
            ),
            receiving_slots_by_downstream_link=tuple(sorted(remaining_slots.items())),
            movement_flow_summaries=movement_flow_summaries,
            conflict_resource_capacity_by_id=tuple(
                sorted(
                    (
                        allocation_input.conflict_resource_capacity_by_id
                        or (
                            allocation_input.junction_spec.conflict_resource_capacity_by_id
                            if allocation_input.junction_spec is not None
                            else {}
                        )
                    ).items()
                )
            ),
            lane_group_capacity_by_id=tuple(
                sorted(
                    (
                        allocation_input.lane_group_capacity_by_id
                        or (
                            allocation_input.junction_spec.lane_group_capacity_by_id
                            if allocation_input.junction_spec is not None
                            else {}
                        )
                    ).items()
                )
            ),
            open_signal_group_ids=tuple(sorted(allocation_input.open_signal_group_ids)),
            closed_movement_ids=tuple(sorted(allocation_input.closed_movement_ids)),
            priority_deficit_by_movement_id=priority_deficits,
        )


ParityNodeTransferPolicy = GeneralMovementAllocator
