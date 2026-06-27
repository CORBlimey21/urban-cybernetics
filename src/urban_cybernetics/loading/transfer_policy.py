"""Minimal node transfer policy abstractions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from urban_cybernetics.core.node import (
    PARITY_NODE_MODEL_AUTO,
    PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO,
    PARITY_NODE_MODEL_ONE_TO_ONE,
    PARITY_NODE_MODEL_PRIORITY_MERGE,
    PARITY_NODE_MODEL_STRICT_DIVERGE,
    Node,
)


@dataclass(frozen=True, slots=True)
class TransferCandidate:
    """Immutable candidate for one physical transfer across a node boundary."""

    packet_id: str
    upstream_link_id: str
    downstream_link_id: str
    boundary_id: str
    eligibility_tick: int
    eligibility_sequence_number: int
    queued: bool = False


@dataclass(frozen=True, slots=True)
class NodeTransferTrace:
    """Read-only trace for one parity node allocation decision."""

    node_id: str
    node_model: str
    candidate_packet_ids: tuple[str, ...]
    approved_packet_ids: tuple[str, ...]
    receiving_slots_by_downstream_link: tuple[tuple[str, int], ...]
    merge_deficit_by_incoming_link_id: tuple[tuple[str, float], ...] = ()


class NodeTransferPolicy(Protocol):
    """Policy interface for allocating candidate node transfers."""

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferCandidate, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        """Return immutable candidates the engine may execute this tick."""


class StrictFIFOJunctionPolicy:
    """Base policy that forbids bypassing packets ahead on an upstream link."""

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferCandidate, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        approved_candidates: list[TransferCandidate] = []
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
    def _candidate_sort_key(candidate: TransferCandidate) -> tuple[int, int, str]:
        return (
            candidate.eligibility_tick,
            candidate.eligibility_sequence_number,
            candidate.packet_id,
        )

    def _respects_upstream_fifo(
        self,
        candidate: TransferCandidate,
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
            queued_downstream = queued_downstream_by_packet_id.get(packet_id_ahead)
            if queued_downstream is not None:
                return False
            return False
        return True


class GlobalFIFOMergePolicy(StrictFIFOJunctionPolicy):
    """Global FIFO allocation policy for candidates competing for receiving slots."""


class ParityNodeTransferPolicy(StrictFIFOJunctionPolicy):
    """M6 parity node family for one-to-one, diverge, and priority merge nodes."""

    def __init__(self, nodes: Iterable[Node]) -> None:
        self._nodes = tuple(nodes)
        self._node_by_incoming_link_id: dict[str, Node] = {}
        self._resolved_model_by_node_id: dict[str, str] = {}
        self._merge_priority_order_by_node_id: dict[str, tuple[str, ...]] = {}
        self._merge_priority_weight_by_node_id: dict[str, dict[str, int]] = {}
        self._merge_deficit_by_node_incoming: dict[tuple[str, str], float] = {}
        self._last_transfer_traces: tuple[NodeTransferTrace, ...] = ()
        self._validate_nodes()

    @property
    def last_transfer_traces(self) -> tuple[NodeTransferTrace, ...]:
        """Return the most recent parity node transfer traces."""

        return self._last_transfer_traces

    def choose_transfers(
        self,
        *,
        candidates: tuple[TransferCandidate, ...],
        receiving_slots_by_downstream_link: Mapping[str, int],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        approved_candidates: list[TransferCandidate] = []
        approved_packet_ids: set[str] = set()
        remaining_slots = dict(receiving_slots_by_downstream_link)
        traces: list[NodeTransferTrace] = []

        candidates_by_node_id: dict[str | None, list[TransferCandidate]] = {}
        for candidate in candidates:
            node = self._node_by_incoming_link_id.get(candidate.upstream_link_id)
            node_id = node.node_id if node is not None else None
            candidates_by_node_id.setdefault(node_id, []).append(candidate)

        for node in sorted(self._nodes, key=lambda item: item.node_id):
            node_candidates = tuple(candidates_by_node_id.pop(node.node_id, ()))
            if not node_candidates:
                continue
            model = self._resolved_model_by_node_id[node.node_id]
            if model == PARITY_NODE_MODEL_PRIORITY_MERGE:
                node_approved = self._choose_priority_merge_transfers(
                    node=node,
                    candidates=node_candidates,
                    remaining_slots=remaining_slots,
                    approved_packet_ids=approved_packet_ids,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            else:
                node_approved = self._choose_strict_fifo_transfers(
                    candidates=node_candidates,
                    remaining_slots=remaining_slots,
                    approved_packet_ids=approved_packet_ids,
                    packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id=queued_downstream_by_packet_id,
                )
            approved_candidates.extend(node_approved)
            traces.append(
                self._node_trace(
                    node=node,
                    model=model,
                    candidates=node_candidates,
                    approved_candidates=tuple(node_approved),
                    remaining_slots=remaining_slots,
                )
            )

        for node_candidates in candidates_by_node_id.values():
            node_approved = self._choose_strict_fifo_transfers(
                candidates=tuple(node_candidates),
                remaining_slots=remaining_slots,
                approved_packet_ids=approved_packet_ids,
                packet_ids_by_upstream_link=packet_ids_by_upstream_link,
                queued_downstream_by_packet_id=queued_downstream_by_packet_id,
            )
            approved_candidates.extend(node_approved)

        self._last_transfer_traces = tuple(traces)
        return tuple(approved_candidates)

    def _validate_nodes(self) -> None:
        for node in self._nodes:
            for incoming_link_id in node.incoming_link_ids:
                if incoming_link_id in self._node_by_incoming_link_id:
                    raise ValueError(
                        f"incoming link {incoming_link_id} belongs to multiple parity nodes"
                    )
                self._node_by_incoming_link_id[incoming_link_id] = node
            model = self._resolve_node_model(node)
            self._resolved_model_by_node_id[node.node_id] = model
            if model == PARITY_NODE_MODEL_PRIORITY_MERGE:
                priority_order, weight_by_link = self._normalise_merge_priorities(node)
                self._merge_priority_order_by_node_id[node.node_id] = priority_order
                self._merge_priority_weight_by_node_id[node.node_id] = weight_by_link
                for incoming_link_id in priority_order:
                    self._merge_deficit_by_node_incoming[
                        (node.node_id, incoming_link_id)
                    ] = 0.0

    def _resolve_node_model(self, node: Node) -> str:
        incoming_count = len(node.incoming_link_ids)
        outgoing_count = len(node.outgoing_link_ids)
        if incoming_count > 1 and outgoing_count > 1:
            raise ValueError(
                f"unsupported parity node {node.node_id}: multi-input/multi-output "
                "nodes require a later node model"
            )
        if node.node_model == PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO:
            raise ValueError(
                f"unsupported parity node {node.node_id}: legacy_global_fifo is "
                "not parity node evidence"
            )
        if node.node_model == PARITY_NODE_MODEL_AUTO:
            if incoming_count == 1 and outgoing_count == 1:
                return PARITY_NODE_MODEL_ONE_TO_ONE
            if incoming_count == 1:
                return PARITY_NODE_MODEL_STRICT_DIVERGE
            return PARITY_NODE_MODEL_PRIORITY_MERGE
        if node.node_model == PARITY_NODE_MODEL_ONE_TO_ONE and (
            incoming_count != 1 or outgoing_count != 1
        ):
            raise ValueError(f"node {node.node_id} is not one-to-one")
        if node.node_model == PARITY_NODE_MODEL_STRICT_DIVERGE and (
            incoming_count != 1 or outgoing_count <= 1
        ):
            raise ValueError(f"node {node.node_id} is not a strict diverge")
        if node.node_model == PARITY_NODE_MODEL_PRIORITY_MERGE and (
            incoming_count <= 1 or outgoing_count != 1
        ):
            raise ValueError(f"node {node.node_id} is not a priority merge")
        return node.node_model

    @staticmethod
    def _normalise_merge_priorities(
        node: Node,
    ) -> tuple[tuple[str, ...], dict[str, int]]:
        if not node.merge_priorities:
            raise ValueError(
                f"priority merge node {node.node_id} requires declared priorities"
            )
        priority_order = tuple(link_id for link_id, _ in node.merge_priorities)
        if set(priority_order) != set(node.incoming_link_ids):
            raise ValueError(
                f"priority merge node {node.node_id} priorities must match incoming links"
            )
        weight_by_link = dict(node.merge_priorities)
        return priority_order, weight_by_link

    def _choose_strict_fifo_transfers(
        self,
        *,
        candidates: tuple[TransferCandidate, ...],
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        approved_candidates: list[TransferCandidate] = []
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

    def _choose_priority_merge_transfers(
        self,
        *,
        node: Node,
        candidates: tuple[TransferCandidate, ...],
        remaining_slots: dict[str, int],
        approved_packet_ids: set[str],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> tuple[TransferCandidate, ...]:
        downstream_link_id = node.outgoing_link_ids[0]
        available_slots = remaining_slots.get(downstream_link_id, 0)
        if available_slots <= 0:
            return ()

        candidates_by_upstream = {
            incoming_link_id: sorted(
                (
                    candidate
                    for candidate in candidates
                    if candidate.upstream_link_id == incoming_link_id
                ),
                key=self._candidate_sort_key,
            )
            for incoming_link_id in node.incoming_link_ids
        }
        active_incoming_link_ids = tuple(
            incoming_link_id
            for incoming_link_id, incoming_candidates in candidates_by_upstream.items()
            if incoming_candidates
        )
        if not active_incoming_link_ids:
            return ()

        weight_by_link = self._merge_priority_weight_by_node_id[node.node_id]
        active_weight_total = sum(
            weight_by_link[incoming_link_id]
            for incoming_link_id in active_incoming_link_ids
        )
        for incoming_link_id in active_incoming_link_ids:
            self._merge_deficit_by_node_incoming[(node.node_id, incoming_link_id)] += (
                weight_by_link[incoming_link_id] / active_weight_total
            ) * available_slots

        approved_candidates: list[TransferCandidate] = []
        priority_order = self._merge_priority_order_by_node_id[node.node_id]
        while remaining_slots.get(downstream_link_id, 0) > 0:
            selectable_candidates: list[tuple[float, int, TransferCandidate, str]] = []
            for priority_index, incoming_link_id in enumerate(priority_order):
                if incoming_link_id not in candidates_by_upstream:
                    continue
                candidate = self._first_fifo_candidate(
                    candidates_by_upstream[incoming_link_id],
                    approved_packet_ids,
                    packet_ids_by_upstream_link,
                    queued_downstream_by_packet_id,
                )
                if candidate is None:
                    continue
                selectable_candidates.append(
                    (
                        self._merge_deficit_by_node_incoming[
                            (node.node_id, incoming_link_id)
                        ],
                        -priority_index,
                        candidate,
                        incoming_link_id,
                    )
                )
            if not selectable_candidates:
                break
            _, _, candidate, incoming_link_id = max(
                selectable_candidates,
                key=lambda item: (item[0], item[1]),
            )
            approved_candidates.append(candidate)
            approved_packet_ids.add(candidate.packet_id)
            remaining_slots[downstream_link_id] -= 1
            self._merge_deficit_by_node_incoming[(node.node_id, incoming_link_id)] -= 1
        return tuple(approved_candidates)

    def _first_fifo_candidate(
        self,
        candidates: list[TransferCandidate],
        approved_packet_ids: set[str],
        packet_ids_by_upstream_link: Mapping[str, tuple[str, ...]],
        queued_downstream_by_packet_id: Mapping[str, str],
    ) -> TransferCandidate | None:
        for candidate in candidates:
            if candidate.packet_id in approved_packet_ids:
                continue
            if self._respects_upstream_fifo(
                candidate,
                approved_packet_ids,
                packet_ids_by_upstream_link,
                queued_downstream_by_packet_id,
            ):
                return candidate
            return None
        return None

    def _node_trace(
        self,
        *,
        node: Node,
        model: str,
        candidates: tuple[TransferCandidate, ...],
        approved_candidates: tuple[TransferCandidate, ...],
        remaining_slots: Mapping[str, int],
    ) -> NodeTransferTrace:
        deficit_items: tuple[tuple[str, float], ...] = ()
        if model == PARITY_NODE_MODEL_PRIORITY_MERGE:
            deficit_items = tuple(
                (
                    incoming_link_id,
                    self._merge_deficit_by_node_incoming[
                        (node.node_id, incoming_link_id)
                    ],
                )
                for incoming_link_id in self._merge_priority_order_by_node_id[
                    node.node_id
                ]
            )
        return NodeTransferTrace(
            node_id=node.node_id,
            node_model=model,
            candidate_packet_ids=tuple(
                candidate.packet_id
                for candidate in sorted(candidates, key=self._candidate_sort_key)
            ),
            approved_packet_ids=tuple(
                candidate.packet_id for candidate in approved_candidates
            ),
            receiving_slots_by_downstream_link=tuple(sorted(remaining_slots.items())),
            merge_deficit_by_incoming_link_id=deficit_items,
        )
