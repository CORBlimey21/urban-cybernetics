"""Focused external-validation contract for de Souza Figure 9(a-c)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from urban_cybernetics.canonical_validation.desouza_figure9 import (
    FIGURE9_BACKWARD_WAVE_SPEED_MPS,
    FIGURE9_EQUAL_CASE_ID,
    FIGURE9_EQUAL_PRIORITY_SEQUENCE,
    FIGURE9_EQUAL_PRIORITY_WEIGHTS,
    FIGURE9_FREE_FLOW_SPEED_MPS,
    FIGURE9_JAM_DENSITY_VEH_PER_M,
    FIGURE9_LINK_LENGTH_M,
    figure9_departures_l1,
    figure9_departures_l2,
    run_figure9_equal_priority,
)


ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "data/validation/desouza_figure9a_equal_comparison_summary_v1.json"


@lru_cache(maxsize=1)
def _result():
    return run_figure9_equal_priority()


def test_equal_fixture_uses_exact_declared_and_inherited_parameters() -> None:
    result = _result()

    assert result.case_id == FIGURE9_EQUAL_CASE_ID
    assert FIGURE9_LINK_LENGTH_M == 150.0
    assert FIGURE9_FREE_FLOW_SPEED_MPS == 30.0
    assert FIGURE9_BACKWARD_WAVE_SPEED_MPS == 6.0
    assert FIGURE9_JAM_DENSITY_VEH_PER_M == 0.1
    assert result.alpha_1 == 0.5
    assert result.priority_sequence == FIGURE9_EQUAL_PRIORITY_SEQUENCE == ("L1", "L2")
    assert result.priority_weights == FIGURE9_EQUAL_PRIORITY_WEIGHTS
    assert len(figure9_departures_l1()) == 36
    assert len(figure9_departures_l2()) == 20


def test_equal_case_closure_conservation_fifo_identity_and_replay_are_exact() -> None:
    result = _result()

    assert result.all_checks_pass
    assert result.event_log_sha256 == (
        "bb6ffdfba021737354dc6b4f4b406ca9a1985cbd158e007db84f281e70f3c840"
    )
    assert all(
        f3 == g1 + g2
        for f3, g1, g2 in zip(
            result.cumulative_inflow_l3,
            result.cumulative_outflow_l1,
            result.cumulative_outflow_l2,
        )
    )


def test_equal_service_and_post_change_queue_behaviour_are_preserved() -> None:
    result = _result()

    assert result.constrained_service_count_l1_through_t40 == 7
    assert result.constrained_service_count_l2_through_t40 == 6
    assert max(result.eligible_queue_l1[:41]) == 2
    assert max(result.eligible_queue_l2[:41]) == 3
    assert max(result.eligible_queue_l1[40:]) == 4
    assert max(result.eligible_queue_l2[40:]) == 4
    assert result.eligible_queue_l1[-1] == 0
    assert result.eligible_queue_l2[-1] == 0


def test_equal_reference_integrity_and_metrics_are_fixed() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    assert summary["source_integrity"]["G1"]["sha256"] == (
        "8906678de58c29cec0534fb41ac5719cad1d7e24d45b072e422a12b100583cc4"
    )
    assert summary["source_integrity"]["G2"]["sha256"] == (
        "406bbde17b9220429460a0dca065d0e52077eb5300c6be72581a07b59ad08825"
    )
    assert summary["source_integrity"]["G1"]["point_count"] == 36
    assert summary["source_integrity"]["G2"]["point_count"] == 42
    assert summary["source_integrity"]["G2"]["sorted_value_decrease_count"] == 7
    assert summary["series"]["G1"]["rmse_vehicles"] == pytest.approx(1.950998658160109)
    assert summary["series"]["G2"]["rmse_vehicles"] == pytest.approx(1.3664632472628822)


def test_material_difference_has_read_only_audit_without_mutation() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    audit = summary["read_only_first_divergence_audit"]

    assert audit["kernel_mutated"] is False
    assert audit["parameters_or_references_tuned"] is False
    assert audit["series"]["G1"]["first_absolute_difference_over_2"]["time_seconds"] == 62
    assert audit["series"]["G2"]["first_absolute_difference_over_2"]["time_seconds"] == 39
