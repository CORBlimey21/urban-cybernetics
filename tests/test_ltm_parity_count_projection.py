# SPDX-License-Identifier: MPL-2.0
"""M2 event-to-count parity projection tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import (
    DemandDeclaration,
    Event,
    EventType,
    LifecycleState,
    Link,
    Node,
    Packet,
)
from urban_cybernetics.loading import (
    COUNT_ORDERING_CONVENTION,
    COUNT_TICK_CONVENTION,
    ENTRY_BOUNDARY,
    EXIT_BOUNDARY,
    LoadingEngine,
    count_consistency_report,
    cumulative_count_series,
    cumulative_count_projection,
    route_key_for_packet,
)


class LTMParityCountProjectionTest(unittest.TestCase):
    def test_count_projection_uses_inclusive_tick_convention(self) -> None:
        engine = LoadingEngine(links={"L1": Link("L1", free_flow_ticks=1)})
        engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )

        before_completion = engine.cumulative_count_projection(max_tick=0)
        engine.step()
        after_completion = engine.cumulative_count_projection(max_tick=1)

        self.assertEqual(before_completion.tick_convention, COUNT_TICK_CONVENTION)
        self.assertEqual(
            self.aggregate_count(before_completion, "L1", 0),
            (1, 0),
        )
        self.assertEqual(
            self.aggregate_count(after_completion, "L1", 1),
            (1, 1),
        )

    def test_same_tick_transfer_ordinals_follow_event_sequence_order(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
            }
        )
        packet = engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )

        engine.step()
        ordinals = engine.packet_boundary_ordinals()
        packet_ordinals = [
            ordinal
            for ordinal in ordinals
            if ordinal.packet_id == packet.packet_id
        ]

        self.assertEqual(
            [
                (ordinal.boundary_type, ordinal.link_id)
                for ordinal in packet_ordinals
            ],
            [
                (ENTRY_BOUNDARY, "L1"),
                (EXIT_BOUNDARY, "L1"),
                (ENTRY_BOUNDARY, "L2"),
            ],
        )
        self.assertLess(
            packet_ordinals[1].sequence_number,
            packet_ordinals[2].sequence_number,
        )
        self.assertEqual(
            {ordinal.physical_tick for ordinal in packet_ordinals[1:]},
            {1},
        )

    def test_packet_boundary_ordinals_map_each_count_increment_to_packet(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
                "L3": Link(
                    "L3",
                    free_flow_ticks=1,
                    declared_receiving_capacity_per_tick=2,
                ),
            },
            nodes=(
                Node(
                    "N",
                    incoming_link_ids=("L1", "L2"),
                    outgoing_link_ids=("L3",),
                ),
            ),
        )
        packet_l1 = engine.instantiate(
            DemandDeclaration("D-L1", departure_tick=0, route_intent=("L1", "L3"))
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration("D-L2", departure_tick=0, route_intent=("L2", "L3"))
        )

        engine.step()
        l3_entry_ordinals = [
            ordinal
            for ordinal in engine.packet_boundary_ordinals()
            if ordinal.link_id == "L3" and ordinal.boundary_type == ENTRY_BOUNDARY
        ]

        self.assertEqual(
            [ordinal.packet_id for ordinal in l3_entry_ordinals],
            [packet_l1.packet_id, packet_l2.packet_id],
        )
        self.assertEqual(
            [ordinal.aggregate_ordinal for ordinal in l3_entry_ordinals],
            [1, 2],
        )
        self.assertEqual(
            [ordinal.route_ordinal for ordinal in l3_entry_ordinals],
            [1, 1],
        )

    def test_route_disaggregated_counts_sum_to_aggregate_counts(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(
                    "L1",
                    free_flow_ticks=1,
                    declared_sending_capacity_per_tick=2,
                ),
                "L2": Link("L2", free_flow_ticks=1),
                "L3": Link("L3", free_flow_ticks=1),
            }
        )
        packet_l2 = engine.instantiate(
            DemandDeclaration("D-L2", departure_tick=0, route_intent=("L1", "L2"))
        )
        packet_l3 = engine.instantiate(
            DemandDeclaration("D-L3", departure_tick=0, route_intent=("L1", "L3"))
        )
        engine.step()

        projection = engine.cumulative_count_projection()
        report = engine.count_consistency_report()

        self.assertTrue(projection.route_counts_supported)
        self.assertEqual(projection.route_count_support_reason, "packet_route_intent")
        self.assertTrue(report.is_consistent)
        l1_route_counts = [
            counts
            for counts in projection.route_counts
            if counts.link_id == "L1" and counts.tick == 1
        ]
        self.assertEqual(sum(counts.entries for counts in l1_route_counts), 2)
        self.assertEqual(sum(counts.exits for counts in l1_route_counts), 2)
        self.assertFalse(
            any(
                counts.link_id == "L2" and counts.route_link_ids == ("L1", "L3")
                for counts in projection.route_counts
            )
        )
        route_key_l2 = route_key_for_packet(engine.packets[packet_l2.packet_id])
        route_key_l3 = route_key_for_packet(engine.packets[packet_l3.packet_id])
        self.assertEqual(
            engine.route_cumulative_counts("L1", route_key_l2).entries,
            1,
        )
        self.assertEqual(
            engine.route_cumulative_counts("L1", route_key_l3).entries,
            1,
        )

    def test_route_disaggregated_counts_are_explicitly_unsupported_without_packets(self) -> None:
        events = (
            Event(0, "P1", EventType.INSTANTIATED, "L1", 0),
            Event(1, "P1", EventType.LINK_ENTRY, "L1", 0),
        )

        projection = cumulative_count_projection(events, link_ids=("L1",))
        report = count_consistency_report(events, link_ids=("L1",))

        self.assertFalse(projection.route_counts_supported)
        self.assertEqual(projection.route_counts, ())
        self.assertEqual(
            projection.route_count_support_reason,
            "packet_route_intent_unavailable",
        )
        self.assertFalse(report.route_counts_supported)

    def test_prefix_reconstruction_reports_counts_for_event_prefix(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
            }
        )
        engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1", "L2"))
        )
        engine.step()

        prefix = engine.cumulative_count_projection(prefix_event_count=3)
        full = engine.cumulative_count_projection()

        self.assertEqual(prefix.checked_event_count, 3)
        self.assertEqual(self.aggregate_count(prefix, "L1", 1), (1, 1))
        self.assertEqual(self.aggregate_count(prefix, "L2", 1), (0, 0))
        self.assertEqual(self.aggregate_count(full, "L2", 1), (1, 0))

    def test_count_consistency_report_detects_negative_storage_projection(self) -> None:
        events = (
            Event(0, "P1", EventType.LINK_EXIT, "L1", 0),
        )

        report = count_consistency_report(events, link_ids=("L1",))

        self.assertFalse(report.is_consistent)
        self.assertIn("L1:exits_exceed_entries_at_tick_0", report.ineligibility_reasons)

    def test_count_consistency_report_detects_noncanonical_event_order(self) -> None:
        events = (
            Event(1, "P1", EventType.LINK_ENTRY, "L1", 0),
            Event(0, "P2", EventType.LINK_ENTRY, "L1", 0),
        )

        report = count_consistency_report(events, link_ids=("L1",))

        self.assertFalse(report.is_consistent)
        self.assertIn(
            "event_sequence_not_prefix_contiguous:expected_0:actual_1",
            report.ineligibility_reasons,
        )
        self.assertIn(
            "events_not_ordered_by_tick_then_sequence",
            report.ineligibility_reasons,
        )

    def test_count_consistency_report_rejects_negative_prefix(self) -> None:
        events = (
            Event(0, "P1", EventType.LINK_ENTRY, "L1", 0),
        )

        report = count_consistency_report(
            events,
            link_ids=("L1",),
            prefix_event_count=-1,
        )

        self.assertFalse(report.is_consistent)
        self.assertEqual(
            report.ineligibility_reasons,
            ("prefix_event_count cannot be negative",),
        )

    def test_count_projection_is_read_only_and_does_not_mutate_engine(self) -> None:
        engine = LoadingEngine(links={"L1": Link("L1", free_flow_ticks=1)})
        engine.instantiate(
            DemandDeclaration("D1", departure_tick=0, route_intent=("L1",))
        )
        before_events = engine.event_log
        before_packets = dict(engine.packets)

        projection = engine.cumulative_count_projection()
        report = engine.count_consistency_report()

        self.assertEqual(engine.event_log, before_events)
        self.assertEqual(dict(engine.packets), before_packets)
        self.assertTrue(report.is_consistent)
        with self.assertRaises(FrozenInstanceError):
            projection.packet_ordinals[0].aggregate_ordinal = 99

    def test_indexed_aggregate_projection_matches_raw_event_reconstruction(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=2),
                "L3": Link("L3", free_flow_ticks=1),
            }
        )
        for index in range(6):
            route = ("L1", "L2") if index % 2 == 0 else ("L1", "L3")
            engine.instantiate(
                DemandDeclaration(
                    f"D{index}",
                    departure_tick=0,
                    route_intent=route,
                )
            )
        for _ in range(3):
            engine.step()

        projection = engine.cumulative_count_projection()
        expected = tuple(
            counts
            for link_id in ("L1", "L2", "L3")
            for counts in cumulative_count_series(
                engine.event_log,
                link_id,
                projection.max_tick,
            )
        )

        self.assertEqual(projection.aggregate_counts, expected)

    def test_route_metadata_mismatch_fails_report_instead_of_guessing(self) -> None:
        events = (
            Event(0, "P1", EventType.LINK_ENTRY, "L9", 0),
        )
        packets = {
            "P1": Packet(
                packet_id="P1",
                demand_id="D1",
                route_intent=("L1",),
                lifecycle_state=LifecycleState.IN_TRANSIT,
            )
        }

        report = count_consistency_report(
            events,
            link_ids=("L9",),
            packets=packets,
        )

        self.assertFalse(report.is_consistent)
        self.assertIn("outside route_intent", report.ineligibility_reasons[0])

    def aggregate_count(
        self,
        projection,
        link_id: str,
        tick: int,
    ) -> tuple[int, int]:
        counts = next(
            counts
            for counts in projection.aggregate_counts
            if counts.link_id == link_id and counts.tick == tick
        )
        return counts.entries, counts.exits


if __name__ == "__main__":
    unittest.main()
