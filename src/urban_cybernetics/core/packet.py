"""Passive packet records."""

from __future__ import annotations

from dataclasses import dataclass

from .lifecycle import LifecycleState


@dataclass(frozen=True, slots=True)
class Packet:
    """Conserved movement unit instantiated and advanced by the loading engine."""

    packet_id: str
    demand_id: str
    route_intent: tuple[str, ...]
    lifecycle_state: LifecycleState
    packet_unit_weight: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_intent", tuple(self.route_intent))
        _validate_unit_packet_weight(self.packet_unit_weight)


def _validate_unit_packet_weight(packet_unit_weight: int) -> None:
    if type(packet_unit_weight) is not int:
        raise TypeError("packet_unit_weight must be an int")
    if packet_unit_weight != 1:
        raise ValueError("weighted packets are not supported in the base loading model")
