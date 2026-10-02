# SPDX-License-Identifier: MPL-2.0
"""V2 analytical, Boreenmanna integration, and package-integrity tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from urban_cybernetics.compiler.model import canonical_json, stable_hash
from urban_cybernetics.compiler.osm_experiment import compile_boreenmanna_experiment
from urban_cybernetics.core import DemandDeclaration
from urban_cybernetics.experiments.boreenmanna import (
    build_boreenmanna_demand_scenarios,
)
from urban_cybernetics.experiments.boreenmanna_audit import (
    DrainPolicy,
    _periodic_fixture_engine,
    build_representation_parity_manifest,
    run_audited_case,
)
from urban_cybernetics.experiments.boreenmanna_gate_aware_v2 import (
    BoreenmannaGateAwareV2ComparisonPackage,
    BoreenmannaGateAwareV2IntegrityError,
    analytical_v1_v2_service_comparison,
)
from urban_cybernetics.extensions.fractional_service_credit import FRACTIONAL_CREDIT
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
)
from urban_cybernetics.loading.lane_group_extension import MOVEMENT_PARTIAL_FIFO


OSM = Path(__file__).parent / "fixtures/osm/boreenmanna_south_link_compact.osm"


@pytest.fixture(scope="module")
def compilation():
    return compile_boreenmanna_experiment(OSM)


def test_analytical_v2_eliminates_alias_and_preserves_green_rates() -> None:
    result = analytical_v1_v2_service_comparison()
    for row in result["permanently_green"]:
        assert row["v1"]["service_count"] == row["expected_service"]
        assert row["v2"]["service_count"] == row["expected_service"]
        assert row["v1"]["configuration_hash"] != row["v2"]["configuration_hash"]
    v2 = [row for row in result["quarter_rate_ggrr"] if row["policy"] == "v2"]
    assert {row["service_count"] for row in v2} == {20}
    v1_offset_two = next(
        row
        for row in result["quarter_rate_ggrr"]
        if row["policy"] == "v1" and row["offset_ticks"] == 2
    )
    assert v1_offset_two["service_count"] == 0


def test_v1_ggrr_physical_and_evidence_regression_fingerprint_is_unchanged() -> None:
    engine, _, _ = _periodic_fixture_engine(
        rate=0.25,
        cycle_ticks=4,
        green_ticks=2,
        offset_ticks=2,
        service_mode=FRACTIONAL_CREDIT,
    )
    for index in range(100):
        engine.instantiate(DemandDeclaration(f"p{index}", 0, ("U", "D")))
    for _ in range(80):
        engine.step()
    payload = {
        "events": [
            [
                item.sequence_number,
                item.packet_id,
                item.event_type.value,
                item.entity_id,
                item.physical_tick,
            ]
            for item in engine.event_log
        ],
        "evidence": [item.to_dict() for item in engine.fractional_service_credit_evidence],
    }
    assert stable_hash("v1-ggrr-regression", payload) == (
        "1f5c54c89b67e922adf82a4737df2e9bcd924fcdbf1ed2116340acb0ef7d5b19"
    )


def test_compact_boreenmanna_v2_replays_conserves_and_keeps_compiler_identity(
    compilation,
) -> None:
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    v2 = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        verify_replay=True,
    )
    v1 = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        FRACTIONAL_CREDIT,
        verify_replay=False,
    )
    assert v2.deterministic["replay_passed"]
    assert v2.deterministic["conservation_passed"]
    assert v2.deterministic["event_cache_consistency_passed"]
    assert v2.deterministic["count_consistency_passed"]
    assert v2.deterministic["service_credit_configuration_hash"] != (
        v1.deterministic["service_credit_configuration_hash"]
    )
    assert v2.deterministic["signal_plan_semantic_hash"] == (
        v1.deterministic["signal_plan_semantic_hash"]
    )
    v1_parity = build_representation_parity_manifest(
        compilation,
        scenario,
        FRACTIONAL_CREDIT,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
    )
    v2_parity = build_representation_parity_manifest(
        compilation,
        scenario,
        GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
    )
    assert json.loads(v1_parity.variants[0].common_input_json)[
        "executable_semantic_hash"
    ] == json.loads(v2_parity.variants[0].common_input_json)[
        "executable_semantic_hash"
    ]
    assert v1_parity.common_input_hash != v2_parity.common_input_hash


def test_v2_representation_parity_and_package_round_trip_tamper(compilation) -> None:
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    run = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        verify_replay=False,
    )
    parity = build_representation_parity_manifest(
        compilation,
        scenario,
        GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
    )
    assert len({item.common_input_hash for item in parity.variants}) == 1
    package = BoreenmannaGateAwareV2ComparisonPackage(
        compilation_package_hash=compilation.package.package_hash,
        executable_semantic_hash=(
            compilation.synthetic_result.require_executable().executable_semantic_hash
        ),
        parent_v1_audit_file_sha256="a" * 64,
        parent_v1_audit_deterministic_hash="b" * 64,
        v1_baseline_json=canonical_json([]),
        v2_core_runs=(run,),
        parity_manifests=(parity,),
        analytical_results_json=canonical_json({"status": "tested"}),
        phase_results_json=canonical_json({"runs": []}),
        performance_json=canonical_json({"measurement_class": "machine_dependent"}),
    )
    restored = BoreenmannaGateAwareV2ComparisonPackage.from_json(package.to_json())
    assert restored.deterministic_hash == package.deterministic_hash
    tampered = deepcopy(package.to_dict())
    tampered["phase_results"]["runs"] = [{"tampered": True}]
    with pytest.raises(BoreenmannaGateAwareV2IntegrityError, match="hash mismatch"):
        BoreenmannaGateAwareV2ComparisonPackage.from_dict(tampered)
