"""Immutable link metadata for synthetic loading tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    """Single directed link with declared static loading metadata."""

    link_id: str
    free_flow_ticks: int
    # Static declared sending metadata, not mutable current flow, effective capacity, or BPR capacity.
    declared_sending_capacity_per_tick: int = 1
    # Static declared receiving metadata, not mutable current capacity, traversal capacity, or BPR capacity.
    declared_receiving_capacity_per_tick: int = 1
    # Static packet storage metadata, not mutable current storage or occupancy.
    declared_storage_capacity_packets: int = 1_000_000
