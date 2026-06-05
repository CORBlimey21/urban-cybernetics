"""Immutable link metadata for synthetic loading tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    """Single directed link with declared static receiving metadata."""

    link_id: str
    free_flow_ticks: int
    # Static declared receiving metadata, not mutable current capacity, traversal capacity, or BPR capacity.
    declared_receiving_capacity_per_tick: int = 1
