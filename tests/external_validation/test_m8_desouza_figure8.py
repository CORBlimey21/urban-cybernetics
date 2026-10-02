# SPDX-License-Identifier: MPL-2.0
"""Focused validation for the seeded de Souza Figure 8 ensemble."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from urban_cybernetics.canonical_validation.desouza_figure8 import (
    FIGURE8_PACKET_COUNT,
    FIGURE8_SEEDS,
    figure8_departures,
    figure8_route_sequence,
    run_figure8_ensemble,
    run_figure8_replication,
    summarise_figure8_ensemble,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = (
    ROOT / "fixtures/visualisation/validation/runs/"
    "m8-pub-dsouza-fig7-dt1-baseline-v1/result.json"
)
SERIES_IDS = (
    "upstream_cumulative_outflow",
    "downstream_1_cumulative_inflow",
    "downstream_2_cumulative_inflow",
)


@lru_cache(maxsize=1)
def _ensemble():
    return run_figure8_ensemble()


@lru_cache(maxsize=1)
def _summary():
    result = json.loads(REFERENCE.read_text(encoding="utf-8"))
    available = {series["series_id"]: series for series in result["observed_series"]}
    deterministic = {
        series_id: tuple(available[series_id]["values"])
        for series_id in SERIES_IDS
    }
    return summarise_figure8_ensemble(_ensemble(), deterministic)


@pytest.mark.parametrize(
    ("seed", "count_l2", "digest"),
    (
        (0, 46, "a4f5921ac62012cb0b50ed8c45d4d443752c1a8617dc1dd3b9da79306b2b3e24"),
        (1, 51, "f27e7df562d1ab7138f99b65f719dc230ba4257fc06b4b2042521c39638ff190"),
        (2, 47, "d9b9d6924913882143b8396ab143da138ba009ba7db749cdef07e612ab52ccf9"),
    ),
)
def test_seeded_route_assignment_is_fixed(seed: int, count_l2: int, digest: str) -> None:
    replication = run_figure8_replication(seed)

    assert replication.route_sequence == figure8_route_sequence(seed)
    assert replication.route_count_l2 == count_l2
    assert replication.route_count_l3 == FIGURE8_PACKET_COUNT - count_l2
    assert replication.route_sequence_sha256 == digest


def test_demand_and_seed_policy_are_exactly_replayable() -> None:
    assert FIGURE8_SEEDS == tuple(range(100))
    assert len(figure8_departures()) == FIGURE8_PACKET_COUNT
    assert figure8_departures() == figure8_departures()
    assert figure8_route_sequence(42) == figure8_route_sequence(42)
    assert figure8_route_sequence(42) != figure8_route_sequence(43)


def test_every_replication_has_exact_closure_and_validation_gates() -> None:
    for replication in _ensemble():
        assert replication.all_checks_pass
        assert all(
            gu == f1 + f2
            for gu, f1, f2 in zip(
                replication.upstream_cumulative_outflow,
                replication.downstream_1_cumulative_inflow,
                replication.downstream_2_cumulative_inflow,
            )
        )


def test_ensemble_converges_to_declared_route_probabilities() -> None:
    route_distribution = _summary()["route_distribution"]

    assert route_distribution["L2_share"]["mean"] == pytest.approx(0.7501470588235294)
    assert route_distribution["L3_share"]["mean"] == pytest.approx(0.24985294117647058)
    assert abs(route_distribution["mean_L2_share_minus_0_75"]) < 0.001
    assert abs(route_distribution["mean_L3_share_minus_0_25"]) < 0.001


def test_deterministic_reference_is_inside_both_bands_at_every_tick() -> None:
    coverage = _summary()["deterministic_coverage"]

    for series_id in SERIES_IDS:
        assert coverage[series_id]["within_envelope_every_tick"] is True
        assert coverage[series_id]["within_p05_p95_every_tick"] is True
        assert coverage[series_id]["envelope_coverage_tick_count"] == 121
        assert coverage[series_id]["p05_p95_coverage_tick_count"] == 121


def test_committed_machine_evidence_retains_every_replication_curve() -> None:
    evidence_path = ROOT / "data/validation/desouza_figure8_ensemble_summary_v1.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert len(evidence["replication_evidence"]) == 100
    for replication in evidence["replication_evidence"]:
        assert len(replication["route_sequence"]) == 68
        for series_id in SERIES_IDS:
            assert len(replication[series_id]) == 121
