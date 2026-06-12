"""R1a repeated asymmetric-information routing experiment tests."""

from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from urban_cybernetics.experiments import (
    R1aExperimentResult,
    run_repeated_fresh_vs_stale_authority_experiment,
)
from urban_cybernetics.experiments.r1a import ROUTE_A, ROUTE_B


class RepeatedAuthorityExperimentTest(unittest.TestCase):
    def test_repeated_decision_cycle_records_multiple_decisions(self) -> None:
        run = run_repeated_fresh_vs_stale_authority_experiment()
        result = run.result

        self.assertEqual(result.decision_ticks, (3, 4, 5))
        self.assertEqual(len(result.observation_frame_ids), 6)
        self.assertEqual(len(result.decision_ids), 6)
        self.assertEqual(len(result.packet_ids), 6)
        self.assertEqual(len(result.cycle_results), 6)
        self.assertEqual(
            sorted(
                {
                    cycle.decision_tick
                    for cycle in result.cycle_results
                }
            ),
            [3, 4, 5],
        )

    def test_visibility_divergence_between_fresh_and_stale_authorities(self) -> None:
        result = run_repeated_fresh_vs_stale_authority_experiment().result

        fresh_first = self.cycle(result, authority_id="fresh", decision_tick=3)
        stale_first = self.cycle(result, authority_id="stale", decision_tick=3)
        fresh_second = self.cycle(result, authority_id="fresh", decision_tick=4)
        stale_second = self.cycle(result, authority_id="stale", decision_tick=4)

        self.assertGreater(len(fresh_first.visible_frame_ids), 0)
        self.assertGreater(len(fresh_second.visible_frame_ids), 0)
        self.assertEqual(stale_first.visible_frame_ids, ())
        self.assertEqual(stale_second.visible_frame_ids, ())
        self.assertNotEqual(
            fresh_first.visible_frame_ids,
            stale_first.visible_frame_ids,
        )

    def test_route_choice_divergence_is_possible_from_visibility_delay(self) -> None:
        result = run_repeated_fresh_vs_stale_authority_experiment().result

        fresh_first = self.cycle(result, authority_id="fresh", decision_tick=3)
        stale_first = self.cycle(result, authority_id="stale", decision_tick=3)
        fresh_second = self.cycle(result, authority_id="fresh", decision_tick=4)
        stale_second = self.cycle(result, authority_id="stale", decision_tick=4)

        self.assertEqual(fresh_first.selected_route, ROUTE_B)
        self.assertEqual(stale_first.selected_route, ROUTE_A)
        self.assertEqual(fresh_second.selected_route, ROUTE_B)
        self.assertEqual(stale_second.selected_route, ROUTE_A)

    def test_packets_realise_paths_consistent_with_route_decisions(self) -> None:
        result = run_repeated_fresh_vs_stale_authority_experiment().result

        for cycle in result.cycle_results:
            with self.subTest(
                authority_id=cycle.authority_id,
                decision_tick=cycle.decision_tick,
            ):
                self.assertEqual(len(cycle.packet_outcomes), 1)
                outcome = cycle.packet_outcomes[0]
                self.assertEqual(outcome.selected_route, cycle.selected_route)
                self.assertEqual(outcome.realised_path, cycle.selected_route)
                self.assertIsNotNone(outcome.completion_tick)
                self.assertEqual(cycle.packet_ids, (outcome.packet_id,))

    def test_provenance_records_relevant_artifact_identifiers(self) -> None:
        run = run_repeated_fresh_vs_stale_authority_experiment()
        result = run.result
        index = run.run_summary.artifact_index

        self.assertEqual(index.output_artifact_ids, (result.result_id,))
        self.assertEqual(index.frame_ids, result.observation_frame_ids)
        self.assertEqual(index.receipt_ids, result.receipt_ids)
        self.assertEqual(index.decision_ids, result.decision_ids)
        self.assertEqual(index.packet_ids, result.packet_ids)
        self.assertGreater(index.event_count, 0)
        self.assertEqual(run.run_summary.validation_status, "passed")

    def test_result_artifact_is_immutable(self) -> None:
        result = run_repeated_fresh_vs_stale_authority_experiment().result

        with self.assertRaises(FrozenInstanceError):
            result.packet_ids = ()
        with self.assertRaises(FrozenInstanceError):
            result.cycle_results[0].selected_route = ROUTE_A

    def cycle(
        self,
        result: R1aExperimentResult,
        *,
        authority_id: str,
        decision_tick: int,
    ):
        for cycle_result in result.cycle_results:
            if (
                cycle_result.authority_id == authority_id
                and cycle_result.decision_tick == decision_tick
            ):
                return cycle_result
        self.fail(
            f"missing cycle for authority_id={authority_id} "
            f"decision_tick={decision_tick}"
        )


if __name__ == "__main__":
    unittest.main()
