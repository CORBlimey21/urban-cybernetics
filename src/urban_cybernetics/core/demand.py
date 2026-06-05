"""Demand declarations for synthetic invariant tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemandDeclaration:
    """Committed demand input before packet instantiation."""

    demand_id: str
    departure_tick: int
    # TODO: In the full model, route intent is assigned by a routing authority.
    # This field exists only to support synthetic invariant tests before routing authorities exist.
    route_intent: tuple[str, ...]
