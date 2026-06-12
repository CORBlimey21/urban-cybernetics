"""Simple routing policies for the M13 authority interface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from urban_cybernetics.observability import (
    LinkTraversalTimeObservationFrame,
    ObservationFrame,
)
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


class LowestObservedTraversalTimeRoutePolicy:
    """Select the candidate route with the lowest visible traversal-time score."""

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
        frames: tuple[LinkTraversalTimeObservationFrame, ...],
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
        frames: tuple[LinkTraversalTimeObservationFrame, ...],
    ) -> float:
        """Sum latest visible mean traversal times for sensors mapped to one route.

        Empty samples and missing observations contribute zero, matching the
        existing count-policy fallback for unknown route conditions.
        """

        latest_frames = self._latest_sampled_frames_by_sensor(frames)
        score = 0.0
        for sensor_id in self._route_sensor_map.get(tuple(route), ()):
            frame = latest_frames.get(sensor_id)
            if frame is None or frame.mean_traversal_time_ticks is None:
                continue
            score += frame.mean_traversal_time_ticks
        return score

    def _latest_sampled_frames_by_sensor(
        self,
        frames: tuple[LinkTraversalTimeObservationFrame, ...],
    ) -> dict[str, LinkTraversalTimeObservationFrame]:
        latest_frames: dict[str, LinkTraversalTimeObservationFrame] = {}
        for frame in sorted(
            frames,
            key=lambda item: (
                item.measurement_tick,
                item.publication_tick,
                item.frame_id,
            ),
        ):
            if frame.sample_count > 0:
                latest_frames[frame.sensor_id] = frame
        return latest_frames
