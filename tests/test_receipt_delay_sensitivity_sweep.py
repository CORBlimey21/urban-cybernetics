# SPDX-License-Identifier: MPL-2.0
"""R1b receipt-delay sensitivity sweep tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.experiments import run_r1b_delay_sensitivity_sweep


DELAY_VALUES = (0, 1, 2, 3, 5)


class ReceiptDelaySensitivitySweepTest(unittest.TestCase):
    def test_sweep_executes_all_delay_cases(self) -> None:
        run = run_r1b_delay_sensitivity_sweep(stale_delay_values=DELAY_VALUES)
        result = run.result

        self.assertEqual(result.stale_delay_values, DELAY_VALUES)
        self.assertEqual(len(result.case_results), len(DELAY_VALUES))
        self.assertEqual(
            result.case_result_ids,
            tuple(case.case_result_id for case in result.case_results),
        )

    def test_delay_values_are_recorded_per_case(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result

        self.assertEqual(
            tuple(case.stale_receipt_delay_ticks for case in result.case_results),
            DELAY_VALUES,
        )

    def test_visibility_changes_across_stale_delay_values(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result
        stale_visible_frame_sets = {
            case.stale_receipt_delay_ticks: self.visible_frame_ids(case, "stale")
            for case in result.case_results
        }

        self.assertGreater(
            len(set(stale_visible_frame_sets.values())),
            1,
        )
        self.assertNotEqual(
            stale_visible_frame_sets[0],
            stale_visible_frame_sets[5],
        )

    def test_decisions_are_recorded_per_case(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result

        for case in result.case_results:
            with self.subTest(delay=case.stale_receipt_delay_ticks):
                self.assertEqual(len(case.decision_ids), 6)
                self.assertTrue(
                    all(
                        decision_id.startswith("decision:")
                        for decision_id in case.decision_ids
                    )
                )
                self.assertEqual(
                    dict(case.metrics.decision_count_by_authority),
                    {"fresh": 3, "stale": 3},
                )

    def test_divergence_metric_exists_and_at_least_one_case_diverges(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result

        divergence_counts = tuple(
            case.metrics.route_divergence_count for case in result.case_results
        )

        self.assertTrue(all(count >= 0 for count in divergence_counts))
        self.assertGreater(max(divergence_counts), 0)

    def test_packet_outcome_summaries_are_recorded_per_case(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result

        for case in result.case_results:
            with self.subTest(delay=case.stale_receipt_delay_ticks):
                self.assertEqual(len(case.packet_ids), 6)
                self.assertEqual(len(case.packet_path_summaries), 6)
                self.assertEqual(case.metrics.completed_packet_count, 6)
                self.assertTrue(
                    all(
                        summary.selected_route == summary.realised_path
                        for summary in case.packet_path_summaries
                    )
                )

    def test_realised_stale_outcomes_can_change_across_delays(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result
        stale_realised_paths_by_delay = {
            case.stale_receipt_delay_ticks: tuple(
                summary.realised_path
                for summary in case.packet_path_summaries
                if summary.authority_id == "stale"
            )
            for case in result.case_results
        }

        self.assertGreater(len(set(stale_realised_paths_by_delay.values())), 1)

    def test_provenance_records_sweep_artifacts_generically(self) -> None:
        run = run_r1b_delay_sensitivity_sweep(stale_delay_values=DELAY_VALUES)
        result = run.result
        index = run.run_summary.artifact_index

        self.assertEqual(
            index.output_artifact_ids,
            (result.sweep_result_id, *result.case_result_ids),
        )
        self.assertEqual(
            index.input_artifact_ids,
            tuple(case.source_result_id for case in result.case_results),
        )
        self.assertGreater(len(index.frame_ids), 0)
        self.assertGreater(len(index.receipt_ids), 0)
        self.assertGreater(len(index.decision_ids), 0)
        self.assertGreater(len(index.packet_ids), 0)
        self.assertEqual(run.run_summary.validation_status, "passed")

    def test_sweep_result_is_immutable(self) -> None:
        result = run_r1b_delay_sensitivity_sweep(
            stale_delay_values=DELAY_VALUES
        ).result

        with self.assertRaises(FrozenInstanceError):
            result.stale_delay_values = ()
        with self.assertRaises(FrozenInstanceError):
            result.case_results[0].stale_receipt_delay_ticks = 99

    def visible_frame_ids(
        self,
        case,
        authority_id: str,
    ) -> tuple[tuple[int, tuple[str, ...]], ...]:
        for visible_frames in case.visible_frames_by_authority:
            if visible_frames.authority_id == authority_id:
                return visible_frames.frame_ids_by_decision_tick
        self.fail(f"missing visible frames for authority_id={authority_id}")


if __name__ == "__main__":
    unittest.main()
