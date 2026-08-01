"""Routing authority interface and authority-owned decision log."""

from __future__ import annotations

from collections.abc import Iterable

from urban_cybernetics.observability import ObservationFrame
from urban_cybernetics.routing.decision import (
    RouteChoiceRequest,
    RouteDecision,
    RoutingAuthorityConfig,
)
from urban_cybernetics.routing.instruction import (
    RoutingDecisionArtifact,
    RoutingInstruction,
    instruction_from_artifact,
)
from urban_cybernetics.routing.policies import CandidateRoutePolicy, RouteSelectionPolicy


class RoutingAuthority:
    """Consumes observation frames and emits immutable route-decision artifacts."""

    def __init__(
        self,
        config: RoutingAuthorityConfig,
        policy: RouteSelectionPolicy | None = None,
    ) -> None:
        self.config = config
        self._policy = policy or CandidateRoutePolicy()
        self._decision_log: list[RouteDecision] = []
        self._instruction_decision_log: list[RoutingDecisionArtifact] = []

    @property
    def decision_log(self) -> tuple[RouteDecision, ...]:
        """Read-only view of this authority's decision history."""

        return tuple(self._decision_log)

    @property
    def instruction_decision_log(self) -> tuple[RoutingDecisionArtifact, ...]:
        """Read-only packet-level executable-decision history."""

        return tuple(self._instruction_decision_log)

    def issue_instruction(
        self,
        *,
        packet_id: str,
        version: int,
        decision_tick: int,
        effective_tick: int,
        remaining_route: tuple[str, ...],
        route_start_ordinal: int,
        reason: str,
        provenance: tuple[tuple[str, str], ...],
        source_decision_id: str | None = None,
    ) -> tuple[RoutingDecisionArtifact, RoutingInstruction]:
        """Issue linked policy and executable artifacts without touching loading."""

        artifact_id = (
            f"routing-artifact:{self.config.authority_id}:{packet_id}:"
            f"{version}:{decision_tick}"
        )
        artifact = RoutingDecisionArtifact(
            artifact_id=artifact_id,
            authority_id=self.config.authority_id,
            packet_id=packet_id,
            decision_tick=decision_tick,
            proposed_remaining_route=remaining_route,
            route_start_ordinal=route_start_ordinal,
            policy_id=reason,
            provenance=provenance,
            source_decision_id=source_decision_id,
        )
        instruction = instruction_from_artifact(
            artifact,
            instruction_id=(
                f"instruction:{self.config.authority_id}:{packet_id}:{version}"
            ),
            version=version,
            effective_tick=effective_tick,
        )
        self._instruction_decision_log.append(artifact)
        return artifact, instruction

    def decide(
        self,
        *,
        request: RouteChoiceRequest,
        frames: Iterable[ObservationFrame],
        decision_tick: int,
    ) -> RouteDecision:
        """Choose one candidate route and append a sealed decision artifact."""

        frame_tuple = tuple(frames)
        selected_route = tuple(
            self._policy.select_route(request=request, frames=frame_tuple)
        )
        if selected_route not in request.candidate_routes:
            raise ValueError("selected_route must be one of request.candidate_routes")

        decision = RouteDecision(
            decision_id=(
                f"decision:{self.config.authority_id}:"
                f"{request.request_id}:{decision_tick}"
            ),
            authority_id=self.config.authority_id,
            request_id=request.request_id,
            demand_id=request.demand_id,
            decision_tick=decision_tick,
            selected_route=selected_route,
            frame_ids_used=tuple(frame.frame_id for frame in frame_tuple),
            policy_name=self.config.policy_name,
        )
        self._decision_log.append(decision)
        return decision
