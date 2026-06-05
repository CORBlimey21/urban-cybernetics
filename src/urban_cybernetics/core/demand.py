"""Demand declarations for synthetic invariant tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemandDeclaration:
    """Committed demand input before packet instantiation."""

    demand_id: str
    departure_tick: int
    # TODO: route intent assigned by routing authority in full model.
    # This field exists only to support synthetic invariant tests before routing authorities exist.
    route_intent: tuple[str, ...]
