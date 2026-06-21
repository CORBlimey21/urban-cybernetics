"""Immutable routing request and decision artifacts."""

from __future__ import annotations

from dataclasses import dataclass


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True, slots=True)
class RoutingAuthorityConfig:
    """Declared identity and policy configuration for one routing authority."""

    authority_id: str
    authority_type: str
    policy_name: str

    def __post_init__(self) -> None:
        _require_non_empty(self.authority_id, "authority_id")
        _require_non_empty(self.authority_type, "authority_type")
        _require_non_empty(self.policy_name, "policy_name")


@dataclass(frozen=True, slots=True)
class RouteChoiceRequest:
    """Demand-level route-choice request over precomputed candidate routes."""

    request_id: str
    demand_id: str
    origin_node_id: str
    destination_node_id: str
    departure_tick: int
    candidate_routes: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.request_id, "request_id")
        _require_non_empty(self.demand_id, "demand_id")

        candidate_routes = tuple(tuple(route) for route in self.candidate_routes)
        if not candidate_routes:
            raise ValueError("candidate_routes must be non-empty")
        if any(not route for route in candidate_routes):
            raise ValueError("candidate route tuples must be non-empty")
        object.__setattr__(self, "candidate_routes", candidate_routes)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Sealed routing decision artifact produced by a routing authority."""

    decision_id: str
    authority_id: str
    request_id: str
    demand_id: str
    decision_tick: int
    selected_route: tuple[str, ...]
    frame_ids_used: tuple[str, ...]
    policy_name: str
    schema_version: str = "m13.route_decision.v1"

    def __post_init__(self) -> None:
        _require_non_empty(self.decision_id, "decision_id")
        _require_non_empty(self.authority_id, "authority_id")
        _require_non_empty(self.request_id, "request_id")
        _require_non_empty(self.demand_id, "demand_id")
        _require_non_empty(self.policy_name, "policy_name")
        selected_route = tuple(self.selected_route)
        if not selected_route:
            raise ValueError("selected_route must be non-empty")
        object.__setattr__(self, "selected_route", selected_route)
        object.__setattr__(self, "frame_ids_used", tuple(self.frame_ids_used))
