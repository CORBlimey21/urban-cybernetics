"""Synthetic Cork experiment, representation matrix, and small-junction tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from urban_cybernetics.compiler import CompilationDisposition, ProvenanceClass
from urban_cybernetics.compiler.osm_experiment import (
    BoreenmannaExperimentCompilationPackage,
    SyntheticExperimentIntegrityError,
    compile_boreenmanna_experiment,
)
from urban_cybernetics.compiler.osm_small_junction import (
    SmallJunctionPackage,
    compile_small_unsignalized_fixture,
)
from urban_cybernetics.experiments.boreenmanna import (
    BoreenmannaExperimentMatrix,
    build_boreenmanna_demand_scenarios,
    run_boreenmanna_experiment_matrix,
)


BOREENMANNA = (
    Path(__file__).parent
    / "fixtures"
    / "osm"
    / "boreenmanna_south_link_compact.osm"
)
SMALL = (
    Path(__file__).parent
    / "fixtures"
    / "osm"
    / "simple_unsignalized_diverge_fixture.osm"
)


@pytest.fixture(scope="module")
def compilation():
    return compile_boreenmanna_experiment(BOREENMANNA)


@pytest.fixture(scope="module")
def matrix_result():
    return run_boreenmanna_experiment_matrix(BOREENMANNA)


def test_third_pass_executes_without_reinterpreting_prior_refusals(compilation) -> None:
    assert compilation.base.source_strict_result.disposition == CompilationDisposition.UNRESOLVED
    assert compilation.base.reviewed_candidate_result.disposition == CompilationDisposition.UNRESOLVED
    result = compilation.synthetic_result
    assert result.disposition == CompilationDisposition.EXECUTABLE_WITH_WARNINGS
    assert result.is_executable
    assert result.require_executable().executable_semantic_hash == (
        result.evidence_bundle.executable_semantic_hash
    )
    assert result.evidence_bundle.executable_semantic_hash


def test_all_compiler_fields_sourced_from_synthetic_records_are_classified_synthetic(
    compilation,
) -> None:
    synthetic_refs = {
        record.evidence_id
        for record in compilation.synthetic_source.records
        if record.evidence_id.startswith("synthetic-evidence:")
    }
    sourced = [
        item
        for item in compilation.synthetic_result.provenance
        if synthetic_refs & set(item.evidence_refs)
    ]
    assert sourced
    assert all(
        item.classification == ProvenanceClass.SYNTHETIC_EXPERIMENT
        for item in sourced
    )
    plan = compilation.synthetic_result.require_executable().signal_plan
    assert all(
        provenance.resolution_status == "synthetic_experiment"
        for controller in plan.controllers
        for provenance in controller.provenance
    )


def test_synthetic_plan_is_exact_simple_and_contains_clearance(compilation) -> None:
    executable = compilation.synthetic_result.require_executable()
    assert executable.tick_duration_seconds == 2.0
    assert len(executable.signal_plan.controllers) == 9
    for controller in executable.signal_plan.controllers:
        assert controller.cycle_ticks == 40
        assert controller.offset_ticks == 0
        assert tuple(stage.duration_ticks for stage in controller.stages) == (
            18,
            2,
            15,
            5,
        )
        assert not controller.stages[1].permitted_movement_ids
        assert not controller.stages[3].permitted_movement_ids
    assert any(
        controller.node_id == "367554319"
        and len(controller.controlled_movement_ids) == 2
        for controller in executable.signal_plan.controllers
    )


def test_synthetic_package_round_trip_and_tamper_detection(compilation) -> None:
    package = compilation.package
    restored = BoreenmannaExperimentCompilationPackage.from_json(package.to_json())
    assert restored.package_hash == package.package_hash
    tampered = deepcopy(package.to_dict())
    tampered["dossier"]["items"][0]["reason"] = "tampered"
    with pytest.raises(SyntheticExperimentIntegrityError, match="item hash mismatch"):
        BoreenmannaExperimentCompilationPackage.from_dict(tampered)


def test_demand_scenarios_are_hashed_compact_and_cover_seven_routes(compilation) -> None:
    moderate, stress = build_boreenmanna_demand_scenarios(compilation)
    assert (len(moderate.demands), len(stress.demands)) == (28, 84)
    assert len({item.route_name for item in moderate.demands}) == 7
    assert moderate.fixed_seed == stress.fixed_seed == 0
    assert moderate.scenario_hash != stress.scenario_hash
    assert all(item.classification == "synthetic_experiment" for item in stress.demands)


def test_matrix_runs_all_modes_with_exact_replay_and_detectable_differences(
    matrix_result,
) -> None:
    compilation, scenarios, matrix = matrix_result
    assert compilation.package.package_hash == (
        "9511409b044b479c750ea5ca5b58877176a6adbf787b834974c11e03182ac617"
    )
    assert matrix.matrix_hash == (
        "b2f1be3f69ee271cf6b7db2a260207816d49fbbfc7d1f1f2c82ec269e366ebcf"
    )
    assert len(scenarios) == 2
    assert len(matrix.runs) == 12
    assert BoreenmannaExperimentMatrix.from_json(matrix.to_json()).matrix_hash == matrix.matrix_hash
    assert all(item.deterministic["replay_passed"] for item in matrix.runs)
    assert all(item.deterministic["conservation_passed"] for item in matrix.runs)
    assert all(item.deterministic["count_consistency_passed"] for item in matrix.runs)
    assert len(
        {item.deterministic["fractional_credit_configuration_hash"] for item in matrix.runs}
    ) == 2
    moderate_fractional = {
        item.deterministic["representation_mode"]: item.deterministic
        for item in matrix.runs
        if item.deterministic["scenario_id"] == "moderate"
        and item.deterministic["service_credit_mode"] == "fractional_credit"
    }
    assert moderate_fractional["shared_link_fifo"]["completed_throughput"] < (
        moderate_fractional["movement_partial_fifo"]["completed_throughput"]
    )
    assert moderate_fractional["explicit_lane_group_fifo"][
        "mean_queue_delay_ticks"
    ] < moderate_fractional["shared_link_fifo"]["mean_queue_delay_ticks"]
    assert compilation.synthetic_result.require_executable().executable_semantic_hash


def test_fixture_backed_unsignalized_selection_compiles_and_smokes() -> None:
    run = compile_small_unsignalized_fixture(SMALL)
    assert run.strict_result.disposition == CompilationDisposition.UNRESOLVED
    assert run.reviewed_result.is_executable
    assert not run.reviewed_result.require_executable().signal_plan.controllers
    assert run.package.smoke_summary["completed_count"] == 4
    assert run.package.smoke_summary["conservation_passed"]
    assert run.package.smoke_summary["replay_passed"]
    assert run.package.performance_summary["measurement_class"] == "machine_dependent"
    assert run.package.selection.source_status == (
        "synthetic_osm_fixture_pending_second_pinned_real_export"
    )
    restored = SmallJunctionPackage.from_json(run.package.to_json())
    assert restored.package_hash == run.package.package_hash

    repeated = compile_small_unsignalized_fixture(SMALL)
    assert repeated.package.package_hash == run.package.package_hash

    payload = run.package.to_dict()
    payload["smoke_summary"]["completed_count"] = 3
    with pytest.raises(ValueError, match="hash mismatch"):
        SmallJunctionPackage.from_dict(payload)
