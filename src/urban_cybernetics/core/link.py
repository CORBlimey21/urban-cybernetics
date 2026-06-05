"""Immutable link metadata for synthetic loading tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    """Single directed link with fixed free-flow traversal time."""

    link_id: str
    free_flow_ticks: int
