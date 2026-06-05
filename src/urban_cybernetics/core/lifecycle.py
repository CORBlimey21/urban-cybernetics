"""Packet lifecycle states."""

from __future__ import annotations

from enum import Enum


class LifecycleState(Enum):
    """Lifecycle state labels for packet conservation accounting."""

    IN_TRANSIT = "in_transit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
