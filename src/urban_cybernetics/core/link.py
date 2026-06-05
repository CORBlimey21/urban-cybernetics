"""Link records for synthetic loading tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Link:
    """Single directed link with minimal receiving metadata."""

    link_id: str
    free_flow_ticks: int
    capacity_per_tick: int = 1
    can_receive: bool = True
