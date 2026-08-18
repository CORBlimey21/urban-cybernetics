"""Boreenmanna V3 compilation, parity, replay, and package tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from urban_cybernetics.compiler.model import canonical_json
from urban_cybernetics.compiler.osm_experiment import compile_boreenmanna_experiment
from urban_cybernetics.experiments.boreenmanna import build_boreenmanna_demand_scenarios
from urban_cybernetics.experiments.boreenmanna_audit import (
    DrainPolicy,
    build_representation_parity_manifest,
    run_audited_case,
)
from urban_cybernetics.experiments.boreenmanna_discharge_readiness_v3 import (
    BoreenmannaDischargeReadinessV3Package,
    BoreenmannaV3IntegrityError,
    analytical_v3_validation,
)
from urban_cybernetics.extensions.discharge_readiness_fractional_service import (
    COMPACT_EVIDENCE,
    DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
    FORENSIC_EVIDENCE,
    SUMMARY_EVIDENCE,
    discharge_readiness_config_for_executable,
)
from urban_cybernetics.extensions.gate_aware_fractional_service import (
    GATE_AWARE_FRACTIONAL_SERVICE_MODE,
)
from urban_cybernetics.loading.lane_group_extension import MOVEMENT_PARTIAL_FIFO


OSM = Path(__file__).parent / "fixtures/osm/boreenmanna_south_link_compact.osm"


@pytest.fixture(scope="module")
def compilation():
    return compile_boreenmanna_experiment(OSM)


def test_compact_boreenmanna_v3_replays_conserves_and_records_readiness(compilation) -> None:
    executable = compilation.synthetic_result.require_executable()
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    config = discharge_readiness_config_for_executable(
        executable, tau_green_seconds=2.0, tau_red_seconds=10.0
    )
    run = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
        service_config_override=config,
        verify_replay=True,
    )
    data = run.deterministic
    assert data["replay_passed"]
    assert data["conservation_passed"]
    assert data["event_cache_consistency_passed"]
    assert data["count_consistency_passed"]
    assert data["readiness_evidence_mode"] == FORENSIC_EVIDENCE
    assert data["readiness_logical_evidence_record_count"] > 0
    assert data["readiness_summary"]["domains"]
    assert data["evaluation_metrics"]["queue_delay_by_boundary"]


def test_boreenmanna_infinite_red_memory_collapses_v3_to_v2(compilation) -> None:
    executable = compilation.synthetic_result.require_executable()
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    v2 = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        GATE_AWARE_FRACTIONAL_SERVICE_MODE,
        verify_replay=False,
    )
    config = discharge_readiness_config_for_executable(
        executable,
        tau_green_seconds=2.0,
        tau_red_seconds=None,
        initial_readiness=1.0,
        evidence_mode=SUMMARY_EVIDENCE,
    )
    v3 = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
        service_config_override=config,
        verify_replay=False,
    )
    assert v3.deterministic["physical_event_log_hash"] == (
        v2.deterministic["physical_event_log_hash"]
    )
    assert v3.deterministic["service_credit_configuration_hash"] != (
        v2.deterministic["service_credit_configuration_hash"]
    )


def test_boreenmanna_v3_evidence_modes_preserve_physics_digest_and_parity(compilation) -> None:
    executable = compilation.synthetic_result.require_executable()
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    runs = []
    for mode in (FORENSIC_EVIDENCE, COMPACT_EVIDENCE, SUMMARY_EVIDENCE):
        config = discharge_readiness_config_for_executable(
            executable, evidence_mode=mode
        )
        run = run_audited_case(
            compilation,
            scenario,
            MOVEMENT_PARTIAL_FIFO,
            DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
            service_config_override=config,
            verify_replay=False,
        )
        runs.append(run)
    assert len({run.deterministic["physical_event_log_hash"] for run in runs}) == 1
    assert len(
        {run.deterministic["readiness_logical_evidence_digest"] for run in runs}
    ) == 1
    retained = [run.deterministic["readiness_retained_record_count"] for run in runs]
    assert retained[0] > retained[1] > retained[2] == 0
    assert len(
        {run.deterministic["readiness_physical_config_hash"] for run in runs}
    ) == 1
    assert len(
        {run.deterministic["readiness_recording_config_hash"] for run in runs}
    ) == 3

    parity = build_representation_parity_manifest(
        compilation,
        scenario,
        DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
        service_config_override=discharge_readiness_config_for_executable(executable),
    )
    assert len({item.common_input_hash for item in parity.variants}) == 1


def test_v3_package_round_trip_tamper_and_analytical_contract(compilation) -> None:
    executable = compilation.synthetic_result.require_executable()
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    config = discharge_readiness_config_for_executable(executable)
    run = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
        service_config_override=config,
        verify_replay=False,
    )
    parity = build_representation_parity_manifest(
        compilation,
        scenario,
        DISCHARGE_READINESS_FRACTIONAL_SERVICE_MODE,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
        service_config_override=config,
    )
    analytical = analytical_v3_validation()
    assert all(item["physical_events_identical"] for item in analytical["collapse_to_v2"])
    package = BoreenmannaDischargeReadinessV3Package(
        compilation_package_hash=compilation.package.package_hash,
        executable_semantic_hash=executable.executable_semantic_hash,
        parent_v2_file_sha256="a" * 64,
        parent_v2_deterministic_hash="b" * 64,
        v2_baseline_json=canonical_json([]),
        v3_core_runs=(run,),
        parity_manifests=(parity,),
        analytical_results_json=canonical_json(analytical),
        sensitivity_results_json=canonical_json({"runs": []}),
        benchmark_deterministic_json=canonical_json({"runs": []}),
        performance_json=canonical_json({"measurement_class": "machine_dependent"}),
    )
    restored = BoreenmannaDischargeReadinessV3Package.from_json(package.to_json())
    assert restored.deterministic_hash == package.deterministic_hash
    tampered = deepcopy(package.to_dict())
    tampered["sensitivity_results"]["runs"] = [{"tampered": True}]
    with pytest.raises(BoreenmannaV3IntegrityError, match="hash mismatch"):
        BoreenmannaDischargeReadinessV3Package.from_dict(tampered)
