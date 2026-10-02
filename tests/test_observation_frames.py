# SPDX-License-Identifier: MPL-2.0
"""Observation-frame tests for boundary-count observability."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.observability import (
    ObservationFrame,
    ObservabilityEngine,
    SensorConfig,
)


class ObservationFramesTest(unittest.TestCase):
    def test_observation_frame_is_frozen(self) -> None:
        frame = ObservationFrame(
            frame_id="frame:S1:5",
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

        with self.assertRaises(FrozenInstanceError):
            frame.primary_count = 2

    def test_sensor_rejects_unsupported_event_type(self) -> None:
        with self.assertRaises(ValueError):
            SensorConfig(
                sensor_id="S1",
                observed_link_id="L1",
                boundary_event_type=EventType.QUEUE_ENTRY,
                aggregation_window_ticks=1,
            )

    def test_sensor_rejects_unsupported_noise_model(self) -> None:
        with self.assertRaises(ValueError):
            SensorConfig(
                sensor_id="S1",
                observed_link_id="L1",
                boundary_event_type=EventType.LINK_ENTRY,
                aggregation_window_ticks=1,
                noise_model="gaussian",
            )

    def test_one_tick_link_entry_frame_counts_only_that_tick(self) -> None:
        engine = self.build_single_link_engine()
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        sensor = SensorConfig(
            sensor_id="S-entry-L1",
            observed_link_id="L1",
            boundary_event_type=EventType.LINK_ENTRY,
            aggregation_window_ticks=1,
        )
        sampler = ObservabilityEngine((sensor,))

        frame_at_tick_0 = sampler.sample(
            events=engine.event_log,
            measurement_tick=0,
        )[0]
        frame_at_tick_1 = sampler.sample(
            events=engine.event_log,
            measurement_tick=1,
        )[0]

        self.assertEqual(frame_at_tick_0.primary_count, 1)
        self.assertEqual(frame_at_tick_1.primary_count, 0)
        self.assertEqual(
            frame_at_tick_1.primary_count,
            self.raw_window_count(
                engine.event_log,
                link_id="L1",
                event_type=EventType.LINK_ENTRY,
                start_tick_exclusive=0,
                end_tick_inclusive=1,
            ),
        )

    def test_multi_tick_link_exit_frame_uses_start_exclusive_end_inclusive_window(
        self,
    ) -> None:
        events = (
            Event(0, "P0", EventType.LINK_EXIT, "L1", 2),
            Event(1, "P1", EventType.LINK_EXIT, "L1", 3),
            Event(2, "P2", EventType.LINK_EXIT, "L1", 4),
            Event(3, "P3", EventType.LINK_EXIT, "L1", 5),
            Event(4, "P4", EventType.LINK_EXIT, "L1", 6),
            Event(5, "P5", EventType.LINK_EXIT, "L2", 5),
            Event(6, "P6", EventType.LINK_ENTRY, "L1", 5),
        )
        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id="S-exit-L1",
                    observed_link_id="L1",
                    boundary_event_type=EventType.LINK_EXIT,
                    aggregation_window_ticks=3,
                ),
            )
        )

        frame = sampler.sample(events=events, measurement_tick=5)[0]

        self.assertEqual(frame.window_start_tick_exclusive, 2)
        self.assertEqual(frame.window_end_tick_inclusive, 5)
        self.assertEqual(frame.primary_count, 3)
        self.assertEqual(
            frame.primary_count,
            self.raw_window_count(
                events,
                link_id="L1",
                event_type=EventType.LINK_EXIT,
                start_tick_exclusive=2,
                end_tick_inclusive=5,
            ),
        )

    def test_observation_samples_after_loading_step(self) -> None:
        engine = self.build_single_link_engine()
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id="S-exit-L1",
                    observed_link_id="L1",
                    boundary_event_type=EventType.LINK_EXIT,
                    aggregation_window_ticks=1,
                ),
            )
        )

        engine.step()
        frame = sampler.sample(
            events=engine.event_log,
            measurement_tick=engine.current_tick,
        )[0]

        self.assertEqual(engine.current_tick, 1)
        self.assertEqual(frame.primary_count, 1)
        self.assertEqual(
            frame.primary_count,
            self.raw_window_count(
                engine.event_log,
                link_id="L1",
                event_type=EventType.LINK_EXIT,
                start_tick_exclusive=0,
                end_tick_inclusive=1,
            ),
        )

    def test_sampling_does_not_mutate_loading_state(self) -> None:
        engine = LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            }
        )
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )
        engine.step()
        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id="S-entry-L2",
                    observed_link_id="L2",
                    boundary_event_type=EventType.LINK_ENTRY,
                    aggregation_window_ticks=1,
                ),
            )
        )
        before_event_log = engine.event_log
        before_counts = engine.cumulative_counts("L2")
        before_storage = engine.link_storage("L2")
        before_packets = tuple(engine.packets.items())
        before_queue = engine.packet_ids_in_queue("L1", "L2")

        sampler.sample(events=engine.event_log, measurement_tick=engine.current_tick)

        self.assertEqual(engine.event_log, before_event_log)
        self.assertEqual(engine.cumulative_counts("L2"), before_counts)
        self.assertEqual(engine.link_storage("L2"), before_storage)
        self.assertEqual(tuple(engine.packets.items()), before_packets)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), before_queue)
        self.assertTrue(engine.check_event_cache_consistency())

    def test_publication_delay_is_recorded(self) -> None:
        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id="S-entry-L1",
                    observed_link_id="L1",
                    boundary_event_type=EventType.LINK_ENTRY,
                    aggregation_window_ticks=1,
                    publication_delay_ticks=2,
                ),
            )
        )

        frame = sampler.sample(events=(), measurement_tick=5)[0]

        self.assertEqual(frame.publication_tick, 7)
        self.assertEqual(frame.measurement_tick, 5)

    def test_multiple_sensors_produce_multiple_frames(self) -> None:
        engine = self.build_single_link_engine()
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        engine.step()
        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id="S-entry-L1",
                    observed_link_id="L1",
                    boundary_event_type=EventType.LINK_ENTRY,
                    aggregation_window_ticks=2,
                ),
                SensorConfig(
                    sensor_id="S-exit-L1",
                    observed_link_id="L1",
                    boundary_event_type=EventType.LINK_EXIT,
                    aggregation_window_ticks=1,
                ),
            )
        )

        frames = sampler.sample(events=engine.event_log, measurement_tick=1)

        self.assertEqual(len(frames), 2)
        self.assertEqual(
            {frame.frame_id for frame in frames},
            {"frame:S-entry-L1:1", "frame:S-exit-L1:1"},
        )
        self.assertEqual([frame.primary_count for frame in frames], [1, 1])

    def test_loading_package_does_not_import_observability(self) -> None:
        loading_dir = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "urban_cybernetics"
            / "loading"
        )
        offenders = []
        for path in loading_dir.glob("*.py"):
            if "urban_cybernetics.observability" in path.read_text():
                offenders.append(path.name)

        self.assertEqual(offenders, [])

    def build_single_link_engine(self) -> LoadingEngine:
        return LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=1)})

    def raw_window_count(
        self,
        events: tuple[Event, ...],
        *,
        link_id: str,
        event_type: EventType,
        start_tick_exclusive: int,
        end_tick_inclusive: int,
    ) -> int:
        return sum(
            event.event_type == event_type
            and event.entity_id == link_id
            and start_tick_exclusive < event.physical_tick <= end_tick_inclusive
            for event in events
        )


if __name__ == "__main__":
    unittest.main()
