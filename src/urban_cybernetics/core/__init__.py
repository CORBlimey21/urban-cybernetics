"""Core records for the minimal packet lifecycle simulator."""

from .demand import DemandDeclaration
from .event import Event, EventType
from .lifecycle import LifecycleState
from .link import (
    DEFAULT_FD_RELATIVE_TOLERANCE,
    DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS,
    FundamentalDiagramConsistencyReport,
    Link,
    ResolvedPhysicalLinkParameters,
    TimestepAdmissibilityReport,
)
from .node import (
    JUNCTION_FIFO_PARTIAL_BY_MOVEMENT,
    JUNCTION_FIFO_STRICT,
    JunctionSpec,
    MovementSpec,
    Node,
    movement_id,
)
from .packet import Packet

__all__ = [
    "DemandDeclaration",
    "Event",
    "EventType",
    "DEFAULT_FD_RELATIVE_TOLERANCE",
    "DEFAULT_MINIMUM_TIMESTEP_LAG_TICKS",
    "FundamentalDiagramConsistencyReport",
    "LifecycleState",
    "Link",
    "JunctionSpec",
    "JUNCTION_FIFO_PARTIAL_BY_MOVEMENT",
    "JUNCTION_FIFO_STRICT",
    "MovementSpec",
    "Node",
    "Packet",
    "ResolvedPhysicalLinkParameters",
    "TimestepAdmissibilityReport",
    "movement_id",
]
