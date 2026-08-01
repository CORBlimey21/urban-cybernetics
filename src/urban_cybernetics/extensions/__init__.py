"""Opt-in extensions layered above the frozen loading kernel."""

from .executable_routing import (
    EXECUTABLE_ROUTING_EXTENSION_VERSION,
    EXECUTABLE_ROUTING_SCHEMA_VERSION,
    ExecutableRoutingConfig,
    ExecutableRoutingLoadingEngine,
    MovementInstructionEvidence,
)

__all__ = [
    "EXECUTABLE_ROUTING_EXTENSION_VERSION",
    "EXECUTABLE_ROUTING_SCHEMA_VERSION",
    "ExecutableRoutingConfig",
    "ExecutableRoutingLoadingEngine",
    "MovementInstructionEvidence",
]
