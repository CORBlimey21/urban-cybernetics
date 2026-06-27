"""Immutable node connectivity records for synthetic junction tests."""

from __future__ import annotations

from dataclasses import dataclass


PARITY_NODE_MODEL_AUTO = "auto"
PARITY_NODE_MODEL_ONE_TO_ONE = "one_to_one"
PARITY_NODE_MODEL_STRICT_DIVERGE = "strict_route_diverge"
PARITY_NODE_MODEL_PRIORITY_MERGE = "priority_merge"
PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO = "legacy_global_fifo"
SUPPORTED_NODE_MODEL_IDS = frozenset(
    (
        PARITY_NODE_MODEL_AUTO,
        PARITY_NODE_MODEL_ONE_TO_ONE,
        PARITY_NODE_MODEL_STRICT_DIVERGE,
        PARITY_NODE_MODEL_PRIORITY_MERGE,
        PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO,
    )
)


@dataclass(frozen=True, slots=True)
class Node:
    """Static node connectivity between directed links."""

    node_id: str
    incoming_link_ids: tuple[str, ...]
    outgoing_link_ids: tuple[str, ...]
    node_model: str = PARITY_NODE_MODEL_AUTO
    merge_priorities: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.node_model not in SUPPORTED_NODE_MODEL_IDS:
            raise ValueError(f"unsupported node_model for {self.node_id}: {self.node_model}")
        _validate_merge_priorities(self.merge_priorities)


def _validate_merge_priorities(
    merge_priorities: tuple[tuple[str, int], ...],
) -> None:
    if not isinstance(merge_priorities, tuple):
        raise TypeError("merge_priorities must be a tuple")
    seen_link_ids: set[str] = set()
    for link_id, weight in merge_priorities:
        _require_non_empty_string(link_id, "merge priority link_id")
        if link_id in seen_link_ids:
            raise ValueError(f"duplicate merge priority for {link_id}")
        seen_link_ids.add(link_id)
        if not isinstance(weight, int):
            raise TypeError("merge priority weight must be an int")
        if weight <= 0:
            raise ValueError("merge priority weight must be positive")


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
