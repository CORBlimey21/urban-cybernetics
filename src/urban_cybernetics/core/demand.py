"""Demand declarations for synthetic invariant tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DemandDeclaration:
    """Committed demand input before packet instantiation."""

    demand_id: str
    departure_tick: int
    # TODO: route intent assigned by routing authority in full model.
    # This field exists only to support synthetic invariant tests before routing authorities exist.
    route_intent: tuple[str, ...]
    packet_unit_weight: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_intent", tuple(self.route_intent))
        _validate_unit_packet_weight(self.packet_unit_weight)


def _validate_unit_packet_weight(packet_unit_weight: int) -> None:
    if type(packet_unit_weight) is not int:
        raise TypeError("packet_unit_weight must be an int")
    if packet_unit_weight != 1:
        raise ValueError("weighted packets are not supported in the base loading model")
