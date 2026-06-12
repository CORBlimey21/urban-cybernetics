"""O1 observation channel expansion tests."""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import DemandDeclaration, Event, EventType, Link, Node
from urban_cybernetics.loading import LoadingEngine
from urban_cybernetics.observability import (
    LinkTraversalTimeObservationFrame,
    LinkTraversalTimeSensorConfig,
    ObservabilityEngine,
    ProbeObservabilityEngine,
    SensorConfig,
    sample_link_traversal_time_frame,
)
from urban_cybernetics.provenance import RunMetadata, RunRecorder
from urban_cybernetics.routing import (
    AuthorityVisibilityConfig,
    AuthorityVisibleStateResolver,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "urban_cybernetics"


class ObservationChannelExpansionTest(unittest.TestCase):
    def test_traversal_time_frame_is_frozen(self) -> None:
        frame = self.frame(sample_count=1, mean=2.0, minimum=2, maximum=2)

        with self.assertRaises(FrozenInstanceError):
            frame.sample_count = 2

    def test_traversal_time_sensor_validates_fields(self) -> None:
        invalid_kwargs = (
            {"sensor_id": ""},
            {"observed_link_id": ""},
            {"aggregation_window_ticks": 0},
            {"publication_delay_ticks": -1},
            {"noise_model": "gaussian"},
        )

        for kwargs in invalid_kwargs:
            with self.subTest(kwargs=kwargs):
                sensor_kwargs = {
                    "sensor_id": "probe:L1",
                    "observed_link_id": "L1",
                    "aggregation_window_ticks": 1,
                }
                sensor_kwargs.update(kwargs)
                with self.assertRaises(ValueError):
                    LinkTraversalTimeSensorConfig(**sensor_kwargs)

    def test_completed_traversal_produces_sample(self) -> None:
        engine = self.single_link_engine(free_flow_ticks=1)
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        engine.step()

        frame = self.sample(engine, measurement_tick=1)

        self.assertEqual(frame.frame_id, "frame:probe:L1:link_traversal_time:1")
        self.assertEqual(frame.sample_count, 1)
        self.assertEqual(frame.mean_traversal_time_ticks, 1.0)
        self.assertEqual(frame.min_traversal_time_ticks, 1)
        self.assertEqual(frame.max_traversal_time_ticks, 1)

    def test_incomplete_traversal_is_excluded(self) -> None:
        engine = self.single_link_engine(free_flow_ticks=3)
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1",))
        )
        engine.step()

        frame = self.sample(engine, measurement_tick=1)

        self.assert_empty_sample(frame)

    def test_queued_packet_still_on_link_is_excluded_until_link_exit(self) -> None:
        engine = self.two_link_engine()
        engine.instantiate(
            DemandDeclaration(demand_id="D1", departure_tick=0, route_intent=("L1", "L2"))
        )
        engine.set_receiving_open("L2", False)
        engine.step()

        queued_frame = self.sample(engine, measurement_tick=1)

        self.assert_empty_sample(queued_frame)
        self.assertEqual(engine.packet_ids_in_queue("L1", "L2"), ("P1",))

        engine.set_receiving_open("L2", True)
        engine.step()
        released_frame = self.sample(engine, measurement_tick=2)

        self.assertEqual(released_frame.sample_count, 1)
        self.assertEqual(released_frame.mean_traversal_time_ticks, 2.0)

    def test_window_uses_link_exit_tick(self) -> None:
        events = (
            Event(0, "P1", EventType.LINK_ENTRY, "L1", 0),
            Event(1, "P2", EventType.LINK_ENTRY, "L1", 1),
            Event(2, "P1", EventType.LINK_EXIT, "L1", 2),
            Event(3, "P2", EventType.LINK_EXIT, "L1", 4),
        )
        sensor = LinkTraversalTimeSensorConfig(
            sensor_id="probe:L1",
            observed_link_id="L1",
            aggregation_window_ticks=1,
        )

        frame_at_two = sample_link_traversal_time_frame(
            sensor=sensor,
            events=events,
            measurement_tick=2,
        )
        frame_at_three = sample_link_traversal_time_frame(
            sensor=sensor,
            events=events,
            measurement_tick=3,
        )

        self.assertEqual(frame_at_two.sample_count, 1)
        self.assertEqual(frame_at_two.mean_traversal_time_ticks, 2.0)
        self.assert_empty_sample(frame_at_three)

    def test_empty_sample_fields_are_none(self) -> None:
        frame = self.sample(
            self.single_link_engine(free_flow_ticks=1),
            measurement_tick=5,
        )

        self.assert_empty_sample(frame)

    def test_delay_metrics_use_free_flow_ticks_when_available(self) -> None:
        events = (
            Event(0, "P1", EventType.LINK_ENTRY, "L1", 0),
            Event(1, "P1", EventType.LINK_EXIT, "L1", 3),
        )
        sensor = LinkTraversalTimeSensorConfig(
            sensor_id="probe:L1",
            observed_link_id="L1",
            aggregation_window_ticks=5,
        )

        without_metadata = sample_link_traversal_time_frame(
            sensor=sensor,
            events=events,
            measurement_tick=3,
        )
        with_metadata = sample_link_traversal_time_frame(
            sensor=sensor,
            events=events,
            measurement_tick=3,
            link_metadata={"L1": Link(link_id="L1", free_flow_ticks=2)},
        )

        self.assertIsNone(without_metadata.mean_delay_ticks)
        self.assertIsNone(without_metadata.delay_ratio)
        self.assertEqual(with_metadata.mean_traversal_time_ticks, 3.0)
        self.assertEqual(with_metadata.mean_delay_ticks, 1.0)
        self.assertEqual(with_metadata.delay_ratio, 1.5)

    def test_visibility_resolver_accepts_traversal_time_frames(self) -> None:
        frame = self.frame(
            sample_count=1,
            mean=2.0,
            minimum=2,
            maximum=2,
            publication_tick=3,
        )
        resolver = AuthorityVisibleStateResolver(
            (
                AuthorityVisibilityConfig(
                    authority_id="commercial",
                    receipt_delay_ticks=2,
                    accessible_sensor_ids=("probe:L1",),
                ),
                AuthorityVisibilityConfig(
                    authority_id="municipal",
                    receipt_delay_ticks=0,
                    accessible_sensor_ids=("infra:L1",),
                ),
            )
        )

        self.assertEqual(
            resolver.visible_frames(
                authority_id="commercial",
                frames=(frame,),
                decision_tick=4,
            ),
            (),
        )
        self.assertEqual(
            resolver.visible_frames(
                authority_id="commercial",
                frames=(frame,),
                decision_tick=5,
            ),
            (frame,),
        )
        self.assertEqual(
            resolver.visible_frames(
                authority_id="municipal",
                frames=(frame,),
                decision_tick=5,
            ),
            (),
        )
        receipts = resolver.receipts_available_by(
            authority_id="commercial",
            frames=(frame,),
            decision_tick=5,
        )
        self.assertEqual(receipts[0].frame_id, frame.frame_id)
        self.assertEqual(receipts[0].receipt_tick, 5)

    def test_provenance_recorder_records_traversal_time_frame_id(self) -> None:
        frame = self.frame(sample_count=1, mean=2.0, minimum=2, maximum=2)
        recorder = RunRecorder(RunMetadata(run_id="run-o1", scenario_name="probe"))

        recorder.record_frames((frame,))
        summary = recorder.seal()

        self.assertEqual(summary.artifact_index.frame_ids, (frame.frame_id,))

    def test_existing_boundary_count_sampling_still_works(self) -> None:
        events = (
            Event(0, "P1", EventType.LINK_ENTRY, "L1", 1),
            Event(1, "P2", EventType.LINK_ENTRY, "L1", 2),
        )
        sampler = ObservabilityEngine(
            (
                SensorConfig(
                    sensor_id="infra:L1",
                    observed_link_id="L1",
                    boundary_event_type=EventType.LINK_ENTRY,
                    aggregation_window_ticks=1,
                ),
            )
        )

        frame = sampler.sample(events=events, measurement_tick=2)[0]

        self.assertEqual(frame.primary_count, 1)
        self.assertEqual(frame.frame_id, "frame:infra:L1:2")

    def test_dependency_hygiene(self) -> None:
        self.assertNotIn(
            "urban_cybernetics.observability",
            self.imports_in_package(SRC_ROOT / "loading"),
        )
        self.assertNotIn(
            "urban_cybernetics.provenance",
            self.imports_in_package(SRC_ROOT / "loading"),
        )
        self.assertNotIn(
            "urban_cybernetics.loading.engine",
            self.imports_in_package(SRC_ROOT / "routing"),
        )
        self.assertNotIn(
            "urban_cybernetics.routing",
            self.imports_in_package(SRC_ROOT / "observability"),
        )

    def sample(
        self,
        engine: LoadingEngine,
        measurement_tick: int,
    ) -> LinkTraversalTimeObservationFrame:
        sampler = ProbeObservabilityEngine(
            (
                LinkTraversalTimeSensorConfig(
                    sensor_id="probe:L1",
                    observed_link_id="L1",
                    aggregation_window_ticks=1,
                ),
            )
        )
        return sampler.sample(
            events=engine.event_log,
            measurement_tick=measurement_tick,
            link_metadata=engine.links,
        )[0]

    def frame(
        self,
        *,
        sample_count: int,
        mean: float | None,
        minimum: int | None,
        maximum: int | None,
        publication_tick: int = 1,
    ) -> LinkTraversalTimeObservationFrame:
        return LinkTraversalTimeObservationFrame(
            frame_id="frame:probe:L1:link_traversal_time:1",
            sensor_id="probe:L1",
            observed_link_id="L1",
            measurement_tick=1,
            aggregation_window_ticks=1,
            window_start_tick_exclusive=0,
            window_end_tick_inclusive=1,
            publication_tick=publication_tick,
            sample_count=sample_count,
            mean_traversal_time_ticks=mean,
            min_traversal_time_ticks=minimum,
            max_traversal_time_ticks=maximum,
        )

    def assert_empty_sample(self, frame: LinkTraversalTimeObservationFrame) -> None:
        self.assertEqual(frame.sample_count, 0)
        self.assertIsNone(frame.mean_traversal_time_ticks)
        self.assertIsNone(frame.min_traversal_time_ticks)
        self.assertIsNone(frame.max_traversal_time_ticks)
        self.assertIsNone(frame.mean_delay_ticks)
        self.assertIsNone(frame.delay_ratio)

    def single_link_engine(self, *, free_flow_ticks: int) -> LoadingEngine:
        return LoadingEngine(links={"L1": Link(link_id="L1", free_flow_ticks=free_flow_ticks)})

    def two_link_engine(self) -> LoadingEngine:
        return LoadingEngine(
            links={
                "L1": Link(link_id="L1", free_flow_ticks=1),
                "L2": Link(link_id="L2", free_flow_ticks=1),
            },
            nodes=(
                Node(
                    node_id="N1",
                    incoming_link_ids=("L1",),
                    outgoing_link_ids=("L2",),
                ),
            ),
        )

    def imports_in_package(self, package_path: Path) -> set[str]:
        imports: set[str] = set()
        for source_path in package_path.glob("*.py"):
            tree = ast.parse(source_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                if isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
        return imports


if __name__ == "__main__":
    unittest.main()
