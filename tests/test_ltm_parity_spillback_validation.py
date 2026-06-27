"""M5 spillback validation fixtures for the parity loading profile."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.core import DemandDeclaration, EventType, LifecycleState, Link
from urban_cybernetics.loading import LoadingEngine, ReceivingCause
from urban_cybernetics.validation import build_spillback_validation_report


class LTMParitySpillbackValidationTest(unittest.TestCase):
    def test_two_link_downstream_receiving_bottleneck_queue_curve(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, sending_capacity=5),
                "L2": self.physical_link("L2", storage=5, receiving_capacity=1),
            }
        )
        packets = [
            engine.instantiate(
                DemandDeclaration(
                    f"D{index}",
                    departure_tick=0,
                    route_intent=("L1", "L2"),
                )
            )
            for index in range(3)
        ]

        engine.step()
        report = build_spillback_validation_report(engine)
        trace = report.boundary_traces[0]

        self.assertTrue(report.is_valid)
        self.assertEqual(trace.boundary_id, "boundary:L1->L2")
        self.assertEqual(trace.queue_entry_count, 2)
        self.assertEqual(trace.queue_exit_count, 0)
        self.assertEqual(trace.max_queue_length, 2)
        self.assertEqual(trace.active_queue_length_from_events, 2)
        self.assertEqual(trace.active_queue_length_from_engine, 2)
        self.assertEqual(trace.queue_curve[1].cumulative_queue_entries, 2)
        self.assertEqual(trace.queue_curve[1].queue_length, 2)
        self.assertIn(
            ReceivingCause.RECEIVING_CAPACITY_EXHAUSTED.value,
            trace.downstream_receiving_causes,
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [packets[0].packet_id],
        )
        self.assertEqual(
            engine.packet_ids_in_queue("L1", "L2"),
            (packets[1].packet_id, packets[2].packet_id),
        )

    def test_two_link_vacancy_spillback_is_delayed_by_backward_wave_lag(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, receiving_capacity=5),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=5),
            }
        )
        blocker = engine.instantiate(
            DemandDeclaration("D-BLOCKER", departure_tick=0, route_intent=("L2",))
        )
        upstream = engine.instantiate(
            DemandDeclaration("D-UP", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        blocked_report = build_spillback_validation_report(engine)
        engine.step()
        still_blocked_report = build_spillback_validation_report(engine)
        engine.step()
        released_report = build_spillback_validation_report(engine)

        blocked_trace = blocked_report.boundary_traces[0]
        still_blocked_trace = still_blocked_report.boundary_traces[0]
        released_trace = released_report.boundary_traces[0]
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L2", 1),
            [blocker.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 1),
            [],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 2),
            [],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 3),
            [upstream.packet_id],
        )
        self.assertEqual(blocked_trace.active_queue_length_from_events, 1)
        self.assertEqual(still_blocked_trace.active_queue_length_from_events, 1)
        self.assertEqual(released_trace.active_queue_length_from_events, 0)
        self.assertEqual(released_trace.queue_exit_count, 1)
        self.assertIn(
            ReceivingCause.PHYSICAL_SHORTAGE.value,
            blocked_trace.downstream_receiving_causes,
        )
        self.assertTrue(released_report.is_valid)

    def test_three_link_spillback_propagates_after_intermediate_vacancy_lag(
        self,
    ) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, receiving_capacity=5),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=5),
                "L3": self.physical_link("L3", storage=1, receiving_capacity=5),
            }
        )
        blocker = engine.instantiate(
            DemandDeclaration("D-BLOCKER", departure_tick=0, route_intent=("L3",))
        )
        middle = engine.instantiate(
            DemandDeclaration("D-MID", departure_tick=0, route_intent=("L2", "L3"))
        )
        upstream = engine.instantiate(
            DemandDeclaration("D-UP", departure_tick=0, route_intent=("L1", "L2", "L3"))
        )

        for _ in range(4):
            engine.step()
        propagation_report = build_spillback_validation_report(engine)
        by_boundary = {
            trace.boundary_id: trace
            for trace in propagation_report.boundary_traces
        }

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_EXIT, "L3", 1),
            [blocker.packet_id],
        )
        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L3", 3),
            [middle.packet_id],
        )
        self.assertEqual(
            engine.packet_ids_in_queue("L1", "L2"),
            (upstream.packet_id,),
        )
        self.assertEqual(by_boundary["boundary:L2->L3"].queue_exit_count, 1)
        self.assertEqual(by_boundary["boundary:L2->L3"].active_queue_length_from_events, 0)
        self.assertEqual(by_boundary["boundary:L1->L2"].queue_entry_count, 1)
        self.assertEqual(by_boundary["boundary:L1->L2"].active_queue_length_from_events, 1)
        self.assertIn(
            ReceivingCause.PHYSICAL_SHORTAGE.value,
            by_boundary["boundary:L1->L2"].downstream_receiving_causes,
        )

        engine.step()
        released_report = build_spillback_validation_report(engine)
        released_by_boundary = {
            trace.boundary_id: trace
            for trace in released_report.boundary_traces
        }

        self.assertEqual(
            self.link_event_packet_ids(engine, EventType.LINK_ENTRY, "L2", 5),
            [upstream.packet_id],
        )
        self.assertEqual(
            released_by_boundary["boundary:L1->L2"].active_queue_length_from_events,
            0,
        )
        self.assertTrue(released_report.is_valid)

    def test_declared_blockage_fixture_records_governance_closure_not_physical_shortage(
        self,
    ) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, sending_capacity=5),
                "L2": self.physical_link("L2", storage=5, receiving_capacity=5),
            }
        )
        engine.set_receiving_open("L2", False)
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        for _ in range(3):
            engine.step()
        report = build_spillback_validation_report(engine)
        trace = report.boundary_traces[0]

        self.assertTrue(report.is_valid)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), (packet.packet_id,))
        self.assertEqual(trace.active_queue_length_from_events, 1)
        self.assertEqual(trace.active_queue_length_from_engine, 1)
        self.assertEqual(
            trace.downstream_receiving_causes,
            (ReceivingCause.GOVERNANCE_CLOSED.value,),
        )

    def test_spillback_report_is_read_only(self) -> None:
        engine = self.parity_engine(
            links={
                "L1": self.physical_link("L1", storage=5, sending_capacity=5),
                "L2": self.physical_link("L2", storage=1, receiving_capacity=5),
            }
        )
        engine.instantiate(
            DemandDeclaration("D-BLOCKER", departure_tick=0, route_intent=("L2",))
        )
        engine.instantiate(
            DemandDeclaration("D-UP", departure_tick=0, route_intent=("L1", "L2"))
        )
        engine.step()
        before_events = engine.event_log
        before_packets = dict(engine.packets)
        before_queue = engine.packet_ids_in_queue("L1", "L2")

        build_spillback_validation_report(engine)

        self.assertEqual(engine.event_log, before_events)
        self.assertEqual(dict(engine.packets), before_packets)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), before_queue)

    def test_legacy_profile_is_not_valid_spillback_parity_evidence(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
            }
        )
        engine.set_receiving_open("L2", False)
        engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )
        engine.step()

        report = build_spillback_validation_report(engine)

        self.assertFalse(report.is_valid)
        self.assertEqual(report.invariant_violations, ("model_profile_not_parity_ltm_v1",))

    def parity_engine(self, *, links: dict[str, Link]) -> LoadingEngine:
        return LoadingEngine(
            links=links,
            model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
        )

    def physical_link(
        self,
        link_id: str,
        *,
        storage: int = 5,
        sending_capacity: int = 5,
        receiving_capacity: int = 5,
    ) -> Link:
        return Link(
            link_id=link_id,
            free_flow_ticks=1,
            declared_sending_capacity_per_tick=sending_capacity,
            declared_receiving_capacity_per_tick=receiving_capacity,
            declared_storage_capacity_packets=storage,
            length_m=10.0,
            lane_count=1,
            free_flow_speed_mps=10.0,
            jam_density_veh_per_km_per_lane=100.0,
            backward_wave_speed_mps=5.0,
            capacity_veh_per_hour_per_lane=1200.0,
            tick_duration_seconds=1.0,
        )

    def link_event_packet_ids(
        self,
        engine: LoadingEngine,
        event_type: EventType,
        link_id: str,
        tick: int,
    ) -> list[str]:
        return [
            event.packet_id
            for event in engine.event_log
            if event.event_type == event_type
            and event.entity_id == link_id
            and event.physical_tick == tick
        ]


if __name__ == "__main__":
    unittest.main()
