# SPDX-License-Identifier: MPL-2.0
"""Focused external-validation contract for de Souza Figure 9(d-f)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from urban_cybernetics.canonical_validation.desouza_figure9 import (
    FIGURE9_ASYMMETRIC_ALPHA_1,
    FIGURE9_ASYMMETRIC_CASE_ID,
    FIGURE9_ASYMMETRIC_PRIORITY_SEQUENCE,
    FIGURE9_ASYMMETRIC_PRIORITY_WEIGHTS,
    run_figure9_asymmetric_priority,
)


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "data/validation/desouza_figure9d_asymmetric_uc_evidence_v1.json"
SUMMARY = ROOT / "data/validation/desouza_figure9d_asymmetric_comparison_summary_v1.json"


@lru_cache(maxsize=1)
def _result():
    return run_figure9_asymmetric_priority()


def test_asymmetric_priority_ambiguity_is_resolved_explicitly_as_three_to_one() -> None:
    result = _result()
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    resolution = evidence["paper_priority_ambiguity_resolution"]

    assert result.case_id == FIGURE9_ASYMMETRIC_CASE_ID
    assert result.alpha_1 == FIGURE9_ASYMMETRIC_ALPHA_1 == 0.75
    assert result.priority_sequence == FIGURE9_ASYMMETRIC_PRIORITY_SEQUENCE
    assert result.priority_sequence == ("L1", "L1", "L1", "L2")
    assert result.priority_weights == FIGURE9_ASYMMETRIC_PRIORITY_WEIGHTS
    assert resolution["selected_alpha_1"] == 0.75
    assert resolution["rejected_textual_value"] == 0.25
    assert resolution["paper_priority_sequence_zero_based"] == [0, 0, 0, 1]
    assert len(resolution["evidence"]) == 6


def test_asymmetric_closure_conservation_fifo_identity_and_replay_are_exact() -> None:
    result = _result()

    assert result.all_checks_pass
    assert result.event_log_sha256 == (
        "d0396a013e5f5f8be91ef10244377aa64e23410b2eed1da1d8622ebf5b359b21"
    )
    assert all(
        f3 == g1 + g2
        for f3, g1, g2 in zip(
            result.cumulative_inflow_l3,
            result.cumulative_outflow_l1,
            result.cumulative_outflow_l2,
        )
    )


def test_asymmetric_service_and_disadvantaged_queue_behaviour_are_preserved() -> None:
    result = _result()

    assert result.constrained_service_count_l1_through_t40 == 8
    assert result.constrained_service_count_l2_through_t40 == 3
    assert result.constrained_service_count_l1_through_t40 / 11 == pytest.approx(8 / 11)
    assert max(result.eligible_queue_l1[:41]) == 2
    assert max(result.eligible_queue_l2[:41]) == 3
    assert max(result.eligible_queue_l1[40:]) == 2
    assert max(result.eligible_queue_l2[40:]) == 5
    assert result.eligible_queue_l1[-1] == 0
    assert result.eligible_queue_l2[-1] == 0


def test_asymmetric_reference_integrity_and_metrics_are_fixed() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    assert summary["source_integrity"]["G1"]["sha256"] == (
        "15a411998a5f09a75c0424980a804be42c30dad81279807d86ddb28f3684343d"
    )
    assert summary["source_integrity"]["G2"]["sha256"] == (
        "f9e239118d5c38ca5c74ab90e2595d25e3116063140d2043c0872c220938bb30"
    )
    assert summary["source_integrity"]["G1"]["point_count"] == 45
    assert summary["source_integrity"]["G2"]["point_count"] == 41
    assert summary["source_integrity"]["G1"]["input_nonincreasing_adjacent_pair_count"] == 4
    assert summary["source_integrity"]["G1"]["sorted_value_decrease_count"] == 4
    assert summary["source_integrity"]["G2"]["sorted_value_decrease_count"] == 4
    assert summary["series"]["G1"]["rmse_vehicles"] == pytest.approx(1.3505965131728346)
    assert summary["series"]["G2"]["rmse_vehicles"] == pytest.approx(1.9254027881458733)


def test_asymmetric_material_difference_has_read_only_audit_without_mutation() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    audit = summary["read_only_first_divergence_audit"]

    assert audit["kernel_mutated"] is False
    assert audit["parameters_or_references_tuned"] is False
    assert audit["series"]["G1"]["first_absolute_difference_over_2"]["time_seconds"] == 38
    assert audit["series"]["G2"]["first_absolute_difference_over_2"]["time_seconds"] == 47
