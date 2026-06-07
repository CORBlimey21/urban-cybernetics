"""Generic run provenance spine tests."""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.core import EventType
from urban_cybernetics.observability import ObservationFrame
from urban_cybernetics.provenance import (
    RunArtifactIndex,
    RunConfigSnapshot,
    RunMetadata,
    RunRecorder,
    RunSummary,
)
from urban_cybernetics.routing import FrameReceipt, RouteDecision


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "urban_cybernetics"


class RunProvenanceTest(unittest.TestCase):
    def test_run_metadata_is_frozen_and_validates_fields(self) -> None:
        with self.assertRaises(ValueError):
            RunMetadata(run_id="", scenario_name="generic")
        with self.assertRaises(ValueError):
            RunMetadata(run_id="run-1", scenario_name="")

        metadata = RunMetadata(
            run_id="run-1",
            scenario_name="generic scenario",
            created_at="2026-06-07T10:00:00Z",
            code_version="test-version",
        )

        with self.assertRaises(FrozenInstanceError):
            metadata.scenario_name = "changed"

    def test_config_snapshot_is_immutable_and_detached(self) -> None:
        source_config = {
            "scenario": "synthetic",
            "ticks": 5,
            "enabled": True,
            "nested": {"policy": "baseline", "weights": [1, 2, 3]},
        }

        snapshot = RunConfigSnapshot(run_id="run-1", config=source_config)
        source_config["ticks"] = 99
        source_config["nested"]["weights"].append(4)  # type: ignore[index]

        self.assertEqual(snapshot.config["ticks"], 5)
        self.assertEqual(
            snapshot.config["nested"]["weights"],  # type: ignore[index]
            (1, 2, 3),
        )

        with self.assertRaises(TypeError):
            snapshot.config["ticks"] = 6  # type: ignore[index]
        with self.assertRaises(TypeError):
            snapshot.config["nested"]["policy"] = "changed"  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            snapshot.run_id = "changed"

    def test_config_snapshot_rejects_complex_objects(self) -> None:
        with self.assertRaises(TypeError):
            RunConfigSnapshot(run_id="run-1", config={"object": object()})
        with self.assertRaises(TypeError):
            RunConfigSnapshot(run_id="run-1", config={1: "not a string key"})

    def test_artifact_index_normalizes_ids_to_tuples(self) -> None:
        frame_ids = ["frame-1"]
        receipt_ids = ["receipt-1"]
        decision_ids = ["decision-1"]
        packet_ids = ["packet-1"]

        index = RunArtifactIndex(
            run_id="run-1",
            input_artifact_ids=["manifest-1"],
            output_artifact_ids=["summary-1"],
            frame_ids=frame_ids,
            receipt_ids=receipt_ids,
            decision_ids=decision_ids,
            packet_ids=packet_ids,
            event_count=3,
        )
        frame_ids.append("frame-2")
        receipt_ids.append("receipt-2")
        decision_ids.append("decision-2")
        packet_ids.append("packet-2")

        self.assertEqual(index.input_artifact_ids, ("manifest-1",))
        self.assertEqual(index.output_artifact_ids, ("summary-1",))
        self.assertEqual(index.frame_ids, ("frame-1",))
        self.assertEqual(index.receipt_ids, ("receipt-1",))
        self.assertEqual(index.decision_ids, ("decision-1",))
        self.assertEqual(index.packet_ids, ("packet-1",))
        self.assertIsInstance(index.frame_ids, tuple)

        with self.assertRaises(FrozenInstanceError):
            index.event_count = 4

    def test_artifact_index_rejects_negative_event_count(self) -> None:
        with self.assertRaises(ValueError):
            RunArtifactIndex(run_id="run-1", event_count=-1)

    def test_run_summary_validates_validation_status(self) -> None:
        metadata = RunMetadata(run_id="run-1", scenario_name="generic")
        index = RunArtifactIndex(run_id="run-1")

        for status in ("not_run", "passed", "failed"):
            with self.subTest(status=status):
                summary = RunSummary(
                    metadata=metadata,
                    config_snapshot=None,
                    artifact_index=index,
                    validation_status=status,
                )
                self.assertEqual(summary.validation_status, status)

        with self.assertRaises(ValueError):
            RunSummary(
                metadata=metadata,
                config_snapshot=None,
                artifact_index=index,
                validation_status="unknown",
            )

    def test_generic_run_summary_does_not_depend_on_m15(self) -> None:
        metadata = RunMetadata(run_id="run-generic", scenario_name="smoke")
        config = RunConfigSnapshot(
            run_id="run-generic",
            config={"network": "tiny", "seed": 123},
        )
        index = RunArtifactIndex(
            run_id="run-generic",
            input_artifact_ids=("topology:tiny", "manifest:tiny"),
            output_artifact_ids=("artifact:summary",),
            event_count=0,
        )

        summary = RunSummary(
            metadata=metadata,
            config_snapshot=config,
            artifact_index=index,
            validation_status="not_run",
            notes=("generic provenance summary",),
        )

        self.assertEqual(summary.metadata.scenario_name, "smoke")
        self.assertEqual(
            summary.artifact_index.input_artifact_ids,
            ("topology:tiny", "manifest:tiny"),
        )
        self.assertEqual(summary.artifact_index.decision_ids, ())

    def test_recorder_collects_vertical_slice_artifact_references(self) -> None:
        frame = self.frame("frame:S1:1")
        receipt = FrameReceipt(
            receipt_id="receipt:authority:frame:S1:1:1",
            authority_id="authority",
            frame_id=frame.frame_id,
            receipt_tick=1,
            publication_tick=1,
            measurement_tick=1,
            sensor_id="S1",
        )
        decision = RouteDecision(
            decision_id="decision:authority:R1:1",
            authority_id="authority",
            request_id="R1",
            demand_id="D1",
            decision_tick=1,
            selected_route=("L1",),
            frame_ids_used=(frame.frame_id,),
            policy_name="first_candidate",
        )
        recorder = RunRecorder(
            RunMetadata(run_id="run-vertical", scenario_name="vertical slice summary")
        )

        recorder.record_config({"scenario": "constructed vertical slice"})
        recorder.record_input_artifact_ids(("manifest:constructed",))
        recorder.record_output_artifact_ids(("decision-log:constructed",))
        recorder.record_frames((frame,))
        recorder.record_receipts((receipt,))
        recorder.record_decisions((decision,))
        recorder.record_packet_ids(("P1", "P2"))
        recorder.record_event_count(7)
        summary = recorder.seal(validation_status="passed")

        self.assertEqual(summary.validation_status, "passed")
        self.assertIsNotNone(summary.config_snapshot)
        self.assertEqual(
            summary.config_snapshot.config["scenario"],  # type: ignore[union-attr]
            "constructed vertical slice",
        )
        self.assertEqual(
            summary.artifact_index.input_artifact_ids,
            ("manifest:constructed",),
        )
        self.assertEqual(
            summary.artifact_index.output_artifact_ids,
            ("decision-log:constructed",),
        )
        self.assertEqual(summary.artifact_index.frame_ids, (frame.frame_id,))
        self.assertEqual(summary.artifact_index.receipt_ids, (receipt.receipt_id,))
        self.assertEqual(summary.artifact_index.decision_ids, (decision.decision_id,))
        self.assertEqual(summary.artifact_index.packet_ids, ("P1", "P2"))
        self.assertEqual(summary.artifact_index.event_count, 7)

    def test_recorder_cannot_mutate_after_seal(self) -> None:
        recorder = RunRecorder(RunMetadata(run_id="run-1", scenario_name="generic"))

        summary = recorder.seal()

        with self.assertRaises(RuntimeError):
            recorder.record_event_count(1)
        with self.assertRaises(FrozenInstanceError):
            summary.validation_status = "passed"

    def test_provenance_does_not_mutate_artifacts(self) -> None:
        frame = self.frame("frame:S1:1")
        decision = RouteDecision(
            decision_id="decision:authority:R1:1",
            authority_id="authority",
            request_id="R1",
            demand_id="D1",
            decision_tick=1,
            selected_route=("L1",),
            frame_ids_used=(frame.frame_id,),
            policy_name="first_candidate",
        )
        before_frame = frame
        before_decision = decision
        recorder = RunRecorder(RunMetadata(run_id="run-1", scenario_name="generic"))

        recorder.record_frames((frame,))
        recorder.record_decisions((decision,))
        recorder.seal()

        self.assertEqual(frame, before_frame)
        self.assertEqual(decision, before_decision)

    def test_dependency_hygiene(self) -> None:
        for package_name in ("loading", "observability", "routing"):
            with self.subTest(package_name=package_name):
                self.assertNotIn(
                    "urban_cybernetics.provenance",
                    self.imports_in_package(SRC_ROOT / package_name),
                )

        self.assertNotIn(
            "urban_cybernetics.loading.engine",
            self.imports_in_package(SRC_ROOT / "provenance"),
        )

    def frame(self, frame_id: str) -> ObservationFrame:
        return ObservationFrame(
            frame_id=frame_id,
            sensor_id="S1",
            observed_link_id="L1",
            boundary_event_type=EventType.LINK_EXIT,
            measurement_tick=1,
            aggregation_window_ticks=1,
            window_start_tick_exclusive=0,
            window_end_tick_inclusive=1,
            publication_tick=1,
            primary_count=1,
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
