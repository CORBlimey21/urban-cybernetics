# SPDX-License-Identifier: MPL-2.0
"""I1 run outcome inspection tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import Event, EventType, LifecycleState, Link, Packet
from urban_cybernetics.inspection import (
    RunOutcomeSummary,
    build_run_outcome_summary,
)
from urban_cybernetics.provenance import RunMetadata, RunRecorder


class RunInspectionTest(unittest.TestCase):
    def test_travel_time_metrics_come_from_realised_packet_history(self) -> None:
        summary = build_run_outcome_summary(
            run_id="run:i1:travel-time",
            events=self.completed_packet_events((10, 20, 40, 60)),
            packets=self.completed_packets(4),
            links={"L1": Link("L1", free_flow_ticks=10)},
        )

        travel_time = summary.travel_time
        self.assertEqual(travel_time.completed_packet_count, 4)
        self.assertEqual(travel_time.total_system_travel_time_ticks, 130)
        self.assertEqual(travel_time.average_travel_time_ticks, 32.5)
        self.assertEqual(travel_time.median_travel_time_ticks, 30.0)
        self.assertAlmostEqual(travel_time.p95_travel_time_ticks, 57.0)
        self.assertEqual(travel_time.max_travel_time_ticks, 60)

    def test_completion_metrics_match_realised_lifecycle_outcomes(self) -> None:
        events = (
            self.event(0, "P1", EventType.INSTANTIATED, "L1", 0),
            self.event(1, "P1", EventType.LINK_ENTRY, "L1", 0),
            self.event(2, "P2", EventType.INSTANTIATED, "L1", 1),
            self.event(3, "P2", EventType.LINK_ENTRY, "L1", 1),
            self.event(4, "P3", EventType.INSTANTIATED, "L2", 2),
            self.event(5, "P3", EventType.LINK_ENTRY, "L2", 2),
            self.event(6, "P1", EventType.LINK_EXIT, "L1", 5),
            self.event(7, "P1", EventType.COMPLETED, "L1", 5),
        )
        packets = {
            "P1": Packet("P1", "D1", ("L1",), LifecycleState.COMPLETED),
            "P2": Packet("P2", "D2", ("L1",), LifecycleState.IN_TRANSIT),
            "P3": Packet("P3", "D3", ("L2",), LifecycleState.QUEUED),
        }

        summary = build_run_outcome_summary(
            run_id="run:i1:completion",
            events=events,
            packets=packets,
            pending_demand_count=2,
        )

        completion = summary.completion
        self.assertEqual(completion.instantiated_packets, 3)
        self.assertEqual(completion.completed_packets, 1)
        self.assertAlmostEqual(completion.completion_percentage, 100.0 / 3.0)
        self.assertEqual(completion.remaining_active_packets, 1)
        self.assertEqual(completion.remaining_queued_packets, 1)
        self.assertEqual(completion.pending_demand_count, 2)

    def test_link_utilisation_counts_canonical_entry_and_exit_events(self) -> None:
        events = (
            self.event(0, "P1", EventType.INSTANTIATED, "L1", 0),
            self.event(1, "P1", EventType.LINK_ENTRY, "L1", 0),
            self.event(2, "P1", EventType.LINK_EXIT, "L1", 3),
            self.event(3, "P1", EventType.LINK_ENTRY, "L2", 3),
            self.event(4, "P2", EventType.INSTANTIATED, "L1", 4),
            self.event(5, "P2", EventType.LINK_ENTRY, "L1", 4),
            self.event(6, "P1", EventType.LINK_EXIT, "L2", 5),
            self.event(7, "P1", EventType.COMPLETED, "L2", 5),
        )

        summary = build_run_outcome_summary(
            run_id="run:i1:utilisation",
            events=events,
            packets={
                "P1": Packet("P1", "D1", ("L1", "L2"), LifecycleState.COMPLETED),
                "P2": Packet("P2", "D2", ("L1",), LifecycleState.IN_TRANSIT),
            },
            links={
                "L1": Link("L1", free_flow_ticks=1),
                "L2": Link("L2", free_flow_ticks=1),
                "L3": Link("L3", free_flow_ticks=1),
            },
        )

        utilisation = {
            item.link_id: (item.link_entry_count, item.link_exit_count)
            for item in summary.link_utilisation
        }
        self.assertEqual(utilisation["L1"], (2, 1))
        self.assertEqual(utilisation["L2"], (1, 1))
        self.assertEqual(utilisation["L3"], (0, 0))

    def test_free_flow_ratios_report_unavailable_packets_explicitly(self) -> None:
        events = self.completed_packet_events((4, 9), link_id="L1")
        packets = {
            "P1": Packet("P1", "D1", ("L1",), LifecycleState.COMPLETED),
            "P2": Packet("P2", "D2", ("missing-link",), LifecycleState.COMPLETED),
        }

        summary = build_run_outcome_summary(
            run_id="run:i1:free-flow",
            events=events,
            packets=packets,
            links={"L1": Link("L1", free_flow_ticks=2)},
        )

        comparison = summary.free_flow_comparison
        self.assertEqual(comparison.packet_count_with_free_flow, 1)
        self.assertEqual(comparison.unavailable_packet_count, 1)
        self.assertEqual(comparison.unavailable_packet_ids, ("P2",))
        self.assertEqual(comparison.average_ratio, 2.0)
        self.assertEqual(comparison.median_ratio, 2.0)
        self.assertEqual(comparison.p95_ratio, 2.0)

    def test_inspection_summary_artifact_id_is_recordable_through_p1(self) -> None:
        summary = build_run_outcome_summary(
            run_id="run:i1:provenance",
            events=self.completed_packet_events((3,)),
            packets=self.completed_packets(1),
            input_artifact_ids=("manifest:test", "topology:test"),
        )
        recorder = RunRecorder(
            RunMetadata(run_id=summary.run_id, scenario_name="I1 provenance")
        )

        recorder.record_output_artifact_ids((summary.summary_id,))
        run_summary = recorder.seal(validation_status="passed")

        self.assertEqual(
            run_summary.artifact_index.output_artifact_ids,
            (summary.summary_id,),
        )
        self.assertEqual(summary.input_artifact_ids, ("manifest:test", "topology:test"))

    def test_summary_artifact_is_immutable(self) -> None:
        summary = build_run_outcome_summary(
            run_id="run:i1:immutable",
            events=(),
            packets={},
        )

        self.assertIsInstance(summary, RunOutcomeSummary)
        with self.assertRaises(FrozenInstanceError):
            summary.summary_id = "changed"

    def completed_packet_events(
        self,
        travel_times: tuple[int, ...],
        *,
        link_id: str = "L1",
    ) -> tuple[Event, ...]:
        events: list[Event] = []
        sequence_number = 0
        for packet_number, travel_time in enumerate(travel_times, start=1):
            packet_id = f"P{packet_number}"
            start_tick = packet_number - 1
            completion_tick = start_tick + travel_time
            events.extend(
                (
                    self.event(
                        sequence_number,
                        packet_id,
                        EventType.INSTANTIATED,
                        link_id,
                        start_tick,
                    ),
                    self.event(
                        sequence_number + 1,
                        packet_id,
                        EventType.LINK_ENTRY,
                        link_id,
                        start_tick,
                    ),
                    self.event(
                        sequence_number + 2,
                        packet_id,
                        EventType.LINK_EXIT,
                        link_id,
                        completion_tick,
                    ),
                    self.event(
                        sequence_number + 3,
                        packet_id,
                        EventType.COMPLETED,
                        link_id,
                        completion_tick,
                    ),
                )
            )
            sequence_number += 4
        return tuple(events)

    def completed_packets(self, count: int) -> dict[str, Packet]:
        return {
            f"P{packet_number}": Packet(
                packet_id=f"P{packet_number}",
                demand_id=f"D{packet_number}",
                route_intent=("L1",),
                lifecycle_state=LifecycleState.COMPLETED,
            )
            for packet_number in range(1, count + 1)
        }

    def event(
        self,
        sequence_number: int,
        packet_id: str,
        event_type: EventType,
        entity_id: str,
        physical_tick: int,
    ) -> Event:
        return Event(
            sequence_number=sequence_number,
            packet_id=packet_id,
            event_type=event_type,
            entity_id=entity_id,
            physical_tick=physical_tick,
        )


if __name__ == "__main__":
    unittest.main()
