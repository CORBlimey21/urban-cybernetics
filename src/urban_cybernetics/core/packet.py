"""Passive packet records."""

from __future__ import annotations

from dataclasses import dataclass

from .lifecycle import LifecycleState


@dataclass(frozen=True)
class Packet:
    """Conserved movement unit instantiated and advanced by the loading engine."""

    packet_id: str
    demand_id: str
    route_intent: tuple[str, ...]
    lifecycle_state: LifecycleState
