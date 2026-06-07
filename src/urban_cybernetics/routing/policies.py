"""Simple routing policies for the M13 authority interface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from urban_cybernetics.observability import ObservationFrame
from urban_cybernetics.routing.decision import RouteChoiceRequest


class RouteSelectionPolicy(Protocol):
    """Policy interface for choosing from supplied candidate routes."""

    def select_route(
        self,
        *,
        request: RouteChoiceRequest,
        frames: tuple[ObservationFrame, ...],
    ) -> tuple[str, ...]:
        """Return one route from request.candidate_routes."""


class CandidateRoutePolicy:
    """Boring M13 policy: always select the first supplied candidate route."""

    def select_route(
        self,
        *,
        request: RouteChoiceRequest,
        frames: tuple[ObservationFrame, ...],
    ) -> tuple[str, ...]:
        return request.candidate_routes[0]


class LowestObservedCountRoutePolicy:
    """Select the candidate route with the lowest visible observation count."""

    def __init__(
        self,
        route_sensor_map: Mapping[tuple[str, ...], tuple[str, ...]],
    ) -> None:
        self._route_sensor_map = {
            tuple(route): tuple(sensor_ids)
            for route, sensor_ids in route_sensor_map.items()
        }
        for route, sensor_ids in self._route_sensor_map.items():
            if not route:
                raise ValueError("route_sensor_map routes must be non-empty")
            if any(not sensor_id for sensor_id in sensor_ids):
                raise ValueError("route_sensor_map sensor IDs must be non-empty")

    @property
    def route_sensor_map(self) -> Mapping[tuple[str, ...], tuple[str, ...]]:
        """Read-only route-to-sensor mapping snapshot."""

        return dict(self._route_sensor_map)

    def select_route(
        self,
        *,
        request: RouteChoiceRequest,
        frames: tuple[ObservationFrame, ...],
    ) -> tuple[str, ...]:
        scored_routes = [
            (self.route_score(route, frames), route_index, route)
            for route_index, route in enumerate(request.candidate_routes)
        ]
        _, _, selected_route = min(scored_routes)
        return selected_route

    def route_score(
        self,
        route: tuple[str, ...],
        frames: tuple[ObservationFrame, ...],
    ) -> int:
        """Sum visible counts for sensors mapped to one route.

        If no visible frames match a route, the score is zero.
        """

        sensor_ids = set(self._route_sensor_map.get(tuple(route), ()))
        return sum(
            frame.primary_count
            for frame in frames
            if frame.sensor_id in sensor_ids
        )
