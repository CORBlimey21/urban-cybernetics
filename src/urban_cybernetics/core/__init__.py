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
    PARITY_NODE_MODEL_AUTO,
    PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO,
    PARITY_NODE_MODEL_ONE_TO_ONE,
    PARITY_NODE_MODEL_PRIORITY_MERGE,
    PARITY_NODE_MODEL_STRICT_DIVERGE,
    SUPPORTED_NODE_MODEL_IDS,
    Node,
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
    "Node",
    "PARITY_NODE_MODEL_AUTO",
    "PARITY_NODE_MODEL_LEGACY_GLOBAL_FIFO",
    "PARITY_NODE_MODEL_ONE_TO_ONE",
    "PARITY_NODE_MODEL_PRIORITY_MERGE",
    "PARITY_NODE_MODEL_STRICT_DIVERGE",
    "Packet",
    "ResolvedPhysicalLinkParameters",
    "SUPPORTED_NODE_MODEL_IDS",
    "TimestepAdmissibilityReport",
]
