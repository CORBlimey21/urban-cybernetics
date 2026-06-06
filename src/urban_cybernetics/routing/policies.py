"""Simple routing policies for the M13 authority interface."""

from __future__ import annotations

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
