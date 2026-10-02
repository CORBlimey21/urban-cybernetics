# SPDX-License-Identifier: MPL-2.0
"""First controlled asymmetric-information routing experiment tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, LifecycleState, Link, Node
from urban_cybernetics.loading import LoadingEngine, packet_ids_on_link_from_events
from urban_cybernetics.observability import (
    ObservationFrame,
    ObservabilityEngine,
    SensorConfig,
)
from urban_cybernetics.routing import (
    AuthorityVisibilityConfig,
    AuthorityVisibleStateResolver,
    LowestObservedCountRoutePolicy,
    RouteChoiceRequest,
    RoutingAuthority,
    RoutingAuthorityConfig,
)


ROUTE_A = ("A1", "A2")
ROUTE_B = ("B1", "B2")
SENSOR_A = "sensor:A1:exit"
SENSOR_B = "sensor:B1:exit"


class FirstAsymmetricInformationExperimentTest(unittest.TestCase):
    def test_lowest_observed_count_policy_chooses_least_observed_route(self) -> None:
        policy = self.build_policy()
        request = self.build_request()
        frames = (
            self.frame("frame:A:5", sensor_id=SENSOR_A, primary_count=5),
            self.frame("frame:B:5", sensor_id=SENSOR_B, primary_count=0),
        )

        selected_route = policy.select_route(request=request, frames=frames)

        self.assertEqual(selected_route, ROUTE_B)
        self.assertEqual(policy.route_score(ROUTE_A, frames), 5)
        self.assertEqual(policy.route_score(ROUTE_B, frames), 0)

    def test_missing_observations_fall_back_to_zero_and_candidate_order(self) -> None:
        policy = self.build_policy()
        request = self.build_request()
        unrelated_frame = self.frame(
            "frame:unrelated:5",
            sensor_id="sensor:other",
            primary_count=99,
        )

        self.assertEqual(policy.select_route(request=request, frames=()), ROUTE_A)
        self.assertEqual(
            policy.select_route(request=request, frames=(unrelated_frame,)),
            ROUTE_A,
        )
        self.assertEqual(policy.route_score(ROUTE_A, (unrelated_frame,)), 0)
        self.assertEqual(policy.route_score(ROUTE_B, (unrelated_frame,)), 0)

    def test_fresh_and_stale_authorities_see_different_frame_sets(self) -> None:
        recent_frame = self.frame(
            "frame:A:5",
            sensor_id=SENSOR_A,
            primary_count=5,
            publication_tick=5,
        )
        resolver = self.build_visibility_resolver()

        fresh_visible = resolver.visible_frames(
            authority_id="fresh",
            frames=(recent_frame,),
            decision_tick=5,
        )
        stale_visible = resolver.visible_frames(
            authority_id="stale",
            frames=(recent_frame,),
            decision_tick=5,
        )

        self.assertEqual(fresh_visible, (recent_frame,))
        self.assertEqual(stale_visible, ())
        self.assertNotEqual(
            tuple(frame.frame_id for frame in fresh_visible),
            tuple(frame.frame_id for frame in stale_visible),
        )

    def test_fresh_and_stale_decisions_differ_and_reference_only_visible_frames(
        self,
    ) -> None:
        frames = (
            self.frame("frame:A:5", sensor_id=SENSOR_A, primary_count=5),
            self.frame("frame:B:5", sensor_id=SENSOR_B, primary_count=0),
        )
        fresh_decision, stale_decision, fresh_visible, stale_visible = (
            self.decide_with_fresh_and_stale_authorities(frames)
        )

        self.assertEqual(fresh_decision.selected_route, ROUTE_B)
        self.assertEqual(stale_decision.selected_route, ROUTE_A)
        self.assertNotEqual(
            fresh_decision.selected_route,
            stale_decision.selected_route,
        )
        self.assertIn(fresh_decision.selected_route, (ROUTE_A, ROUTE_B))
        self.assertIn(stale_decision.selected_route, (ROUTE_A, ROUTE_B))
        self.assertEqual(
            fresh_decision.frame_ids_used,
            tuple(frame.frame_id for frame in fresh_visible),
        )
        self.assertEqual(
            stale_decision.frame_ids_used,
            tuple(frame.frame_id for frame in stale_visible),
        )

    def test_decision_selected_routes_are_applied_to_loading(self) -> None:
        frames = (
            self.frame("frame:A:5", sensor_id=SENSOR_A, primary_count=5),
            self.frame("frame:B:5", sensor_id=SENSOR_B, primary_count=0),
        )
        fresh_decision, stale_decision, _, _ = (
            self.decide_with_fresh_and_stale_authorities(frames)
        )
        engine = self.build_two_route_engine()

        fresh_packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D-fresh",
                departure_tick=0,
                route_intent=fresh_decision.selected_route,
            )
        )
        stale_packet = engine.instantiate(
            DemandDeclaration(
                demand_id="D-stale",
                departure_tick=0,
                route_intent=stale_decision.selected_route,
            )
        )
        self.run_to_completion(engine)

        self.assertEqual(
            self.realised_path(engine, fresh_packet.packet_id),
            fresh_decision.selected_route,
        )
        self.assertEqual(
            self.realised_path(engine, stale_packet.packet_id),
            stale_decision.selected_route,
        )
        self.assertEqual(
            engine.packets[fresh_packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assertEqual(
            engine.packets[stale_packet.packet_id].lifecycle_state,
            LifecycleState.COMPLETED,
        )
        self.assert_no_reroute_events(engine)
        self.assert_synthetic_kernel_consistent(engine, ("A1", "A2", "B1", "B2"))

    def test_generated_frames_drive_asymmetric_decision(self) -> None:
        background_engine = self.build_two_route_engine()
        for demand_number in range(5):
            background_engine.instantiate(
                DemandDeclaration(
                    demand_id=f"D-background-{demand_number}",
                    departure_tick=0,
                    route_intent=ROUTE_A,
                )
            )
        background_engine.step()

        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id=SENSOR_A,
                    observed_link_id="A1",
                    boundary_event_type=EventType.LINK_EXIT,
                    aggregation_window_ticks=1,
                ),
                SensorConfig(
                    sensor_id=SENSOR_B,
                    observed_link_id="B1",
                    boundary_event_type=EventType.LINK_EXIT,
                    aggregation_window_ticks=1,
                ),
            )
        )
        frames = sampler.sample(
            events=background_engine.event_log,
            measurement_tick=background_engine.current_tick,
        )

        self.assertEqual(background_engine.current_tick, 1)
        self.assertEqual(self.frame_by_sensor(frames, SENSOR_A).primary_count, 5)
        self.assertEqual(self.frame_by_sensor(frames, SENSOR_B).primary_count, 0)

        fresh_decision, stale_decision, fresh_visible, stale_visible = (
            self.decide_with_fresh_and_stale_authorities(
                frames,
                decision_tick=background_engine.current_tick,
            )
        )

        self.assertIn(self.frame_by_sensor(frames, SENSOR_A), fresh_visible)
        self.assertEqual(stale_visible, ())
        self.assertEqual(fresh_decision.selected_route, ROUTE_B)
        self.assertEqual(stale_decision.selected_route, ROUTE_A)
        self.assertEqual(
            fresh_decision.frame_ids_used,
            tuple(frame.frame_id for frame in fresh_visible),
        )

    def test_policy_does_not_need_physical_truth(self) -> None:
        authority = self.build_authority("fresh")
        request = self.build_request()
        frames = (self.frame("frame:A:5", sensor_id=SENSOR_A, primary_count=5),)

        decision = authority.decide(
            request=request,
            frames=frames,
            decision_tick=5,
        )

        self.assertEqual(decision.selected_route, ROUTE_B)
        self.assertEqual(decision.frame_ids_used, ("frame:A:5",))

    def build_policy(self) -> LowestObservedCountRoutePolicy:
        return LowestObservedCountRoutePolicy(
            {
                ROUTE_A: (SENSOR_A,),
                ROUTE_B: (SENSOR_B,),
            }
        )

    def build_authority(self, authority_id: str) -> RoutingAuthority:
        return RoutingAuthority(
            RoutingAuthorityConfig(
                authority_id=authority_id,
                authority_type="candidate_route",
                policy_name="lowest_observed_count",
            ),
            policy=self.build_policy(),
        )

    def build_request(self) -> RouteChoiceRequest:
        return RouteChoiceRequest(
            request_id="R1",
            demand_id="D1",
            origin_node_id="origin",
            destination_node_id="destination",
            departure_tick=5,
            candidate_routes=(ROUTE_A, ROUTE_B),
        )

    def build_visibility_resolver(self) -> AuthorityVisibleStateResolver:
        return AuthorityVisibleStateResolver(
            (
                AuthorityVisibilityConfig("fresh", receipt_delay_ticks=0),
                AuthorityVisibilityConfig("stale", receipt_delay_ticks=3),
            )
        )

    def decide_with_fresh_and_stale_authorities(
        self,
        frames: tuple[ObservationFrame, ...],
        *,
        decision_tick: int = 5,
    ):
        resolver = self.build_visibility_resolver()
        request = self.build_request()
        fresh_authority = self.build_authority("fresh")
        stale_authority = self.build_authority("stale")
        fresh_visible = resolver.visible_frames(
            authority_id="fresh",
            frames=frames,
            decision_tick=decision_tick,
        )
        stale_visible = resolver.visible_frames(
            authority_id="stale",
            frames=frames,
            decision_tick=decision_tick,
        )
        fresh_decision = fresh_authority.decide(
            request=request,
            frames=fresh_visible,
            decision_tick=decision_tick,
        )
        stale_decision = stale_authority.decide(
            request=request,
            frames=stale_visible,
            decision_tick=decision_tick,
        )
        return fresh_decision, stale_decision, fresh_visible, stale_visible

    def build_two_route_engine(self) -> LoadingEngine:
        return LoadingEngine(
            links={
                "A1": Link(
                    link_id="A1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=10,
                ),
                "A2": Link(
                    link_id="A2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=10,
                    declared_storage_capacity_packets=20,
                ),
                "B1": Link(
                    link_id="B1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=10,
                ),
                "B2": Link(
                    link_id="B2",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=10,
                    declared_storage_capacity_packets=20,
                ),
            },
            nodes=(
                Node(
                    node_id="route-a-transfer",
                    incoming_link_ids=("A1",),
                    outgoing_link_ids=("A2",),
                ),
                Node(
                    node_id="route-b-transfer",
                    incoming_link_ids=("B1",),
                    outgoing_link_ids=("B2",),
                ),
            ),
        )

    def frame(
        self,
        frame_id: str,
        *,
        sensor_id: str,
        primary_count: int,
        publication_tick: int = 5,
    ) -> ObservationFrame:
        return ObservationFrame(
            frame_id=frame_id,
            sensor_id=sensor_id,
            observed_link_id=sensor_id.split(":")[1],
            boundary_event_type=EventType.LINK_EXIT,
            measurement_tick=publication_tick,
            aggregation_window_ticks=1,
            window_start_tick_exclusive=publication_tick - 1,
            window_end_tick_inclusive=publication_tick,
            publication_tick=publication_tick,
            primary_count=primary_count,
        )

    def frame_by_sensor(
        self,
        frames: tuple[ObservationFrame, ...],
        sensor_id: str,
    ) -> ObservationFrame:
        for frame in frames:
            if frame.sensor_id == sensor_id:
                return frame
        self.fail(f"missing frame for sensor_id={sensor_id}")

    def realised_path(self, engine: LoadingEngine, packet_id: str) -> tuple[str, ...]:
        return tuple(
            event.entity_id
            for event in engine.event_log
            if event.packet_id == packet_id
            and event.event_type == EventType.LINK_ENTRY
        )

    def run_to_completion(self, engine: LoadingEngine) -> None:
        for _ in range(10):
            if all(
                packet.lifecycle_state == LifecycleState.COMPLETED
                for packet in engine.packets.values()
            ):
                return
            engine.step()
        self.fail("packets did not complete within expected synthetic test horizon")

    def assert_synthetic_kernel_consistent(
        self,
        engine: LoadingEngine,
        link_ids: tuple[str, ...],
    ) -> None:
        self.assertTrue(engine.check_conservation())
        for link_id in link_ids:
            for tick in range(engine.current_tick + 1):
                entries = self.raw_event_count(
                    engine,
                    link_id,
                    tick,
                    EventType.LINK_ENTRY,
                )
                exits = self.raw_event_count(
                    engine,
                    link_id,
                    tick,
                    EventType.LINK_EXIT,
                )
                counts = engine.cumulative_counts(link_id, tick)
                self.assertEqual(counts.entries, entries)
                self.assertEqual(counts.exits, exits)
                self.assertLessEqual(counts.exits, counts.entries)
                self.assertEqual(
                    engine.link_storage(link_id, tick).storage,
                    counts.entries - counts.exits,
                )
                self.assertEqual(
                    engine.link_storage(link_id, tick).storage,
                    len(packet_ids_on_link_from_events(engine.event_log, link_id, tick)),
                )
                self.assertLessEqual(
                    engine.link_storage(link_id, tick).storage,
                    engine.links[link_id].declared_storage_capacity_packets,
                )

    def raw_event_count(
        self,
        engine: LoadingEngine,
        link_id: str,
        tick: int,
        event_type: EventType,
    ) -> int:
        return sum(
            event.event_type == event_type
            and event.entity_id == link_id
            and event.physical_tick <= tick
            for event in engine.event_log
        )

    def assert_no_reroute_events(self, engine: LoadingEngine) -> None:
        self.assertFalse(
            [
                event
                for event in engine.event_log
                if event.event_type.name == "REROUTE"
            ]
        )


if __name__ == "__main__":
    unittest.main()
