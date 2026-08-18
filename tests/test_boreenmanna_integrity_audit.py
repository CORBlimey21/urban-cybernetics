"""Focused scientific-integrity tests for the Boreenmanna audit layer."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from urban_cybernetics.compiler.osm_experiment import compile_boreenmanna_experiment
from urban_cybernetics.compiler.model import canonical_json
from urban_cybernetics.core import DemandDeclaration, JunctionSpec, Link, MovementSpec, Node
from urban_cybernetics.experiments.boreenmanna import (
    _execute_case,
    build_boreenmanna_demand_scenarios,
)
from urban_cybernetics.experiments.boreenmanna_audit import (
    AuditedRunManifest,
    BoreenmannaAuditIntegrityError,
    BoreenmannaIntegrityAuditPackage,
    DrainPolicy,
    RepresentationParityManifest,
    build_representation_parity_manifest,
    drain_engine,
    engine_is_empty,
    periodic_gating_validation,
    run_audited_case,
)
from urban_cybernetics.extensions.fractional_service_credit import (
    FRACTIONAL_CREDIT,
    FractionalServiceCreditConfig,
    FractionalServiceCreditLoadingEngine,
)
from urban_cybernetics.loading import GeneralMovementAllocator, LoadingEngine
from urban_cybernetics.loading.lane_group_extension import MOVEMENT_PARTIAL_FIFO


OSM = Path(__file__).parent / "fixtures/osm/boreenmanna_south_link_compact.osm"


def _link(link_id: str, *, free_flow_ticks: int = 1) -> Link:
    return Link(
        link_id=link_id,
        free_flow_ticks=free_flow_ticks,
        declared_sending_capacity_per_tick=1,
        declared_receiving_capacity_per_tick=1,
        declared_storage_capacity_packets=20,
        length_m=10.0,
        lane_count=1,
        free_flow_speed_mps=10.0,
        jam_density_veh_per_km_per_lane=2_000.0,
        backward_wave_speed_mps=10.0,
        capacity_veh_per_hour_per_lane=3_600.0,
        tick_duration_seconds=1.0,
    )


def test_drain_clears_a_fractional_fixture_that_is_incomplete_at_evaluation() -> None:
    def execute():
        engine = FractionalServiceCreditLoadingEngine(
            links={"L": _link("L")},
            fractional_service_credit_config=FractionalServiceCreditConfig(
                mode=FRACTIONAL_CREDIT,
                continuous_capacity_by_link=(("L", 0.25),),
            ),
            executable_semantic_hash="drain-clearing-fixture",
        )
        engine.instantiate(DemandDeclaration("D", 0, ("L",)))
        engine.step()
        engine.step()
        assert not engine_is_empty(engine)
        outcome = drain_engine(
            engine,
            evaluation_horizon_tick=2,
            declared_demand_count=1,
            demand_origin_by_id={"D": "L"},
            policy=DrainPolicy(maximum_drain_ticks=10),
        )
        return engine, outcome

    first_engine, first = execute()
    replay_engine, replay = execute()
    assert first.completed_at_evaluation == 0
    assert first.eventually_completed == 1
    assert first.final_completion_tick == 4
    assert first.drain_duration_ticks == 2
    assert first.reached_empty_condition
    assert first == replay
    assert first_engine.event_log == replay_engine.event_log
    assert first_engine.fractional_service_credit_evidence == (
        replay_engine.fractional_service_credit_evidence
    )
    assert first_engine.check_conservation()


def test_drain_reports_permanently_closed_movement_at_maximum_horizon() -> None:
    movement = MovementSpec("U", "D")
    node = Node(
        "N",
        incoming_link_ids=("U",),
        outgoing_link_ids=("D",),
        junction_spec=JunctionSpec(
            node_id="N",
            incoming_link_ids=("U",),
            outgoing_link_ids=("D",),
            movement_specs=(movement,),
        ),
    )
    engine = LoadingEngine(
        links={"U": _link("U"), "D": _link("D")},
        nodes=(node,),
        node_transfer_policy=GeneralMovementAllocator((node,)),
    )
    engine.set_movement_governance_open("N", movement.movement_id, False)
    engine.instantiate(DemandDeclaration("blocked", 0, ("U", "D")))
    engine.step()
    engine.step()
    outcome = drain_engine(
        engine,
        evaluation_horizon_tick=2,
        declared_demand_count=1,
        demand_origin_by_id={"blocked": "U"},
        policy=DrainPolicy(maximum_drain_ticks=5),
    )
    assert not outcome.reached_empty_condition
    assert outcome.reached_maximum_drain_horizon
    assert outcome.residual_active_packets == 1
    assert outcome.terminal_tick == 7
    assert engine.check_conservation()


@pytest.fixture(scope="module")
def compilation():
    return compile_boreenmanna_experiment(OSM)


def test_evaluation_metrics_are_unchanged_by_drain(compilation) -> None:
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    original = _execute_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        FRACTIONAL_CREDIT,
    )["summary"]
    audited = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        FRACTIONAL_CREDIT,
        verify_replay=True,
    )
    evaluation = audited.deterministic["evaluation_metrics"]
    for key in (
        "completed_throughput",
        "incomplete_packets",
        "mean_queue_delay_ticks",
        "peak_queue",
        "movement_throughput",
        "blocked_transfer_requests_by_reason",
        "spillback_occurrence",
        "canonical_event_count",
    ):
        assert canonical_json(evaluation[key]) == canonical_json(original[key])
    assert audited.deterministic["drain_outcome"]["eventually_completed"] == 28
    assert audited.deterministic["replay_passed"]


def test_representation_manifest_proves_common_parity_and_rejects_perturbation(
    compilation,
) -> None:
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    manifest = build_representation_parity_manifest(
        compilation,
        scenario,
        FRACTIONAL_CREDIT,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
    )
    restored = RepresentationParityManifest.from_dict(manifest.to_dict())
    assert restored.manifest_hash == manifest.manifest_hash
    assert len({item.common_input_hash for item in manifest.variants}) == 1
    assert len({item.representation_input_hash for item in manifest.variants}) == 3

    common = manifest.variants[0].common_input_json.replace(
        '"fixed_seed":0', '"fixed_seed":1'
    )
    perturbed = replace(manifest.variants[0], common_input_json=common, common_input_hash="")
    with pytest.raises(BoreenmannaAuditIntegrityError, match="common input differs"):
        RepresentationParityManifest(
            family_id=manifest.family_id,
            variants=(perturbed, *manifest.variants[1:]),
        )


def test_periodic_gating_matches_exact_recurrence_and_exposes_phase_aliasing() -> None:
    result = periodic_gating_validation()
    assert result["results"][0]["expected_service_ticks"] == (
        result["results"][0]["observed_service_ticks"]
    )
    assert result["results"][1]["expected_service_ticks"] == (
        result["results"][1]["observed_service_ticks"]
    )
    assert result["results"][0]["service_count"] == 8
    assert result["results"][1]["service_count"] == 0


def test_audit_package_round_trip_and_tamper_detection(compilation) -> None:
    scenario = build_boreenmanna_demand_scenarios(compilation)[0]
    run = run_audited_case(
        compilation,
        scenario,
        MOVEMENT_PARTIAL_FIFO,
        FRACTIONAL_CREDIT,
        verify_replay=False,
    )
    parity = build_representation_parity_manifest(
        compilation,
        scenario,
        FRACTIONAL_CREDIT,
        offset_ticks=0,
        drain_policy=DrainPolicy(),
    )
    package = BoreenmannaIntegrityAuditPackage(
        compilation_package_hash=compilation.package.package_hash,
        original_matrix_hash="original-v1-matrix",
        core_runs=(run,),
        parity_manifests=(parity,),
        phase_results_json='{"runs":[]}',
        scaling_results_json='{"cases":[]}',
        periodic_gating_json='{"status":"tested"}',
        performance_json='{"measurement_class":"machine_dependent"}',
    )
    restored = BoreenmannaIntegrityAuditPackage.from_json(package.to_json())
    assert restored.deterministic_hash == package.deterministic_hash
    tampered = deepcopy(package.to_dict())
    tampered["phase_results"]["runs"] = [{"tampered": True}]
    with pytest.raises(BoreenmannaAuditIntegrityError, match="hash mismatch"):
        BoreenmannaIntegrityAuditPackage.from_dict(tampered)


def test_audited_run_manifest_rejects_forged_deterministic_payload() -> None:
    manifest = AuditedRunManifest("{\"value\":1}", "{}")
    with pytest.raises(BoreenmannaAuditIntegrityError, match="hash mismatch"):
        AuditedRunManifest("{\"value\":2}", "{}", deterministic_hash=manifest.deterministic_hash)
