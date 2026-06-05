"""Immutable lifecycle events owned by the loading engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventType(Enum):
    """Lifecycle event labels for the first simulator milestone."""

    INSTANTIATED = "instantiated"
    LINK_ENTRY = "link_entry"
    LINK_EXIT = "link_exit"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Event:
    """Append-only physical record emitted by the loading engine."""

    sequence_number: int
    packet_id: str
    event_type: EventType
    entity_id: str
    physical_tick: int
