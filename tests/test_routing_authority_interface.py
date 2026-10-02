# SPDX-License-Identifier: MPL-2.0
"""Routing authority interface tests for M13."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import EventType
from urban_cybernetics.observability import ObservationFrame
from urban_cybernetics.routing import (
    CandidateRoutePolicy,
    RouteChoiceRequest,
    RouteDecision,
    RoutingAuthority,
    RoutingAuthorityConfig,
)


class RoutingAuthorityInterfaceTest(unittest.TestCase):
    def test_route_choice_request_validates_candidate_routes(self) -> None:
        with self.assertRaises(ValueError):
            RouteChoiceRequest(
                request_id="R1",
                demand_id="D1",
                origin_node_id="N1",
                destination_node_id="N2",
                departure_tick=5,
                candidate_routes=(),
            )
        with self.assertRaises(ValueError):
            RouteChoiceRequest(
                request_id="R1",
                demand_id="D1",
                origin_node_id="N1",
                destination_node_id="N2",
                departure_tick=5,
                candidate_routes=((),),
            )

        request = RouteChoiceRequest(
            request_id="R1",
            demand_id="D1",
            origin_node_id="N1",
            destination_node_id="N2",
            departure_tick=5,
            candidate_routes=(["L1", "L2"], ("L3",)),
        )

        self.assertEqual(request.candidate_routes, (("L1", "L2"), ("L3",)))

    def test_route_decision_is_frozen(self) -> None:
        decision = RouteDecision(
            decision_id="decision:A1:R1:5",
            authority_id="A1",
            request_id="R1",
            demand_id="D1",
            decision_tick=5,
            selected_route=("L1", "L2"),
            frame_ids_used=("frame:S1:5",),
            policy_name="candidate_route",
        )

        with self.assertRaises(FrozenInstanceError):
            decision.selected_route = ("L3",)

    def test_authority_selects_first_candidate_route(self) -> None:
        authority = self.build_authority()
        request = self.build_request()

        decision = authority.decide(
            request=request,
            frames=(),
            decision_tick=5,
        )

        self.assertEqual(decision.selected_route, ("L1", "L2"))
        self.assertEqual(decision.policy_name, "candidate_route")

    def test_decision_references_observation_frames(self) -> None:
        authority = self.build_authority()
        request = self.build_request()
        frames = (
            self.frame("frame:S-entry-L1:5"),
            self.frame("frame:S-exit-L1:5"),
        )

        decision = authority.decide(
            request=request,
            frames=frames,
            decision_tick=5,
        )

        self.assertEqual(
            decision.frame_ids_used,
            ("frame:S-entry-L1:5", "frame:S-exit-L1:5"),
        )

    def test_decision_log_is_append_only_internally_and_read_only_externally(
        self,
    ) -> None:
        authority = self.build_authority()
        request = self.build_request()

        first_decision = authority.decide(
            request=request,
            frames=(),
            decision_tick=5,
        )
        second_decision = authority.decide(
            request=request,
            frames=(),
            decision_tick=6,
        )

        self.assertEqual(authority.decision_log, (first_decision, second_decision))
        with self.assertRaises(AttributeError):
            authority.decision_log.append(first_decision)
        self.assertEqual(authority.decision_log, (first_decision, second_decision))

    def test_authority_does_not_require_loading_engine(self) -> None:
        authority = self.build_authority()
        request = self.build_request()

        decision = authority.decide(
            request=request,
            frames=(self.frame("frame:S1:5"),),
            decision_tick=5,
        )

        self.assertEqual(decision.selected_route, ("L1", "L2"))

    def test_authority_does_not_mutate_observation_frames(self) -> None:
        authority = self.build_authority()
        request = self.build_request()
        frame = self.frame("frame:S1:5")
        before = frame

        authority.decide(request=request, frames=(frame,), decision_tick=5)

        self.assertEqual(frame, before)

    def test_selected_route_must_be_from_candidate_routes(self) -> None:
        class InvalidPolicy:
            def select_route(
                self,
                *,
                request: RouteChoiceRequest,
                frames: tuple[ObservationFrame, ...],
            ) -> tuple[str, ...]:
                return ("L9",)

        authority = RoutingAuthority(
            RoutingAuthorityConfig(
                authority_id="A1",
                authority_type="candidate_route",
                policy_name="invalid_test_policy",
            ),
            policy=InvalidPolicy(),
        )

        with self.assertRaises(ValueError):
            authority.decide(
                request=self.build_request(),
                frames=(),
                decision_tick=5,
            )
        self.assertEqual(authority.decision_log, ())

    def test_loading_package_does_not_import_routing(self) -> None:
        loading_dir = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "urban_cybernetics"
            / "loading"
        )
        offenders = []
        for path in loading_dir.glob("*.py"):
            if "urban_cybernetics.routing" in path.read_text():
                offenders.append(path.name)

        self.assertEqual(offenders, [])

    def test_routing_package_does_not_import_loading_engine(self) -> None:
        routing_dir = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "urban_cybernetics"
            / "routing"
        )
        offenders = []
        forbidden_imports = (
            "urban_cybernetics.loading",
            "LoadingEngine",
        )
        for path in routing_dir.glob("*.py"):
            text = path.read_text()
            if any(forbidden in text for forbidden in forbidden_imports):
                offenders.append(path.name)

        self.assertEqual(offenders, [])

    def test_authority_config_rejects_empty_identity_or_policy(self) -> None:
        with self.assertRaises(ValueError):
            RoutingAuthorityConfig(
                authority_id="",
                authority_type="candidate_route",
                policy_name="candidate_route",
            )
        with self.assertRaises(ValueError):
            RoutingAuthorityConfig(
                authority_id="A1",
                authority_type="candidate_route",
                policy_name="",
            )

    def build_authority(self) -> RoutingAuthority:
        return RoutingAuthority(
            RoutingAuthorityConfig(
                authority_id="A1",
                authority_type="candidate_route",
                policy_name="candidate_route",
            ),
            policy=CandidateRoutePolicy(),
        )

    def build_request(self) -> RouteChoiceRequest:
        return RouteChoiceRequest(
            request_id="R1",
            demand_id="D1",
            origin_node_id="N1",
            destination_node_id="N2",
            departure_tick=5,
            candidate_routes=(("L1", "L2"), ("L3", "L4")),
        )

    def frame(self, frame_id: str) -> ObservationFrame:
        return ObservationFrame(
            frame_id=frame_id,
            sensor_id="S1",
            observed_link_id="L1",
            boundary_event_type=EventType.LINK_ENTRY,
            measurement_tick=5,
            aggregation_window_ticks=1,
            window_start_tick_exclusive=4,
            window_end_tick_inclusive=5,
            publication_tick=5,
            primary_count=1,
        )


if __name__ == "__main__":
    unittest.main()
