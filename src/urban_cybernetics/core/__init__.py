"""Core records for the minimal packet lifecycle simulator."""

from .demand import DemandDeclaration
from .event import Event, EventType
from .lifecycle import LifecycleState
from .link import Link
from .packet import Packet

__all__ = [
    "DemandDeclaration",
    "Event",
    "EventType",
    "LifecycleState",
    "Link",
    "Packet",
]
