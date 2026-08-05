"""First vertical-slice contracts for provenance-aware network compilation."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from urban_cybernetics.canonical_validation import validate_loading_kernel
from urban_cybernetics.compiler import (
    MANDATORY_LINK_FIELDS,
    CompilationDisposition,
    CompilationNotExecutableError,
    CompilationResultInvariantError,
    CompilerConfig,
    CompilerEvidenceBundle,
    CompilerOverride,
    DiagnosticSeverity,
    EvidenceBundleIntegrityError,
    PhysicalDerivationRecord,
    ProvenanceClass,
    ROUNDING_POLICIES,
    adapt_osm_like,
    compile_network,
)
from urban_cybernetics.compiler.fixtures import (
    fixture_a_overrides,
    fixture_a_payload,
    fixture_a_source,
    fixture_b_source,
    fixture_c_source,
    fixture_d_overrides,
    fixture_d_source,
    fixture_e_source,
)
from urban_cybernetics.core import DemandDeclaration, LifecycleState
from urban_cybernetics.extensions import FIXED_TIME_SIGNAL_SCHEMA_VERSION
from urban_cybernetics.loading.lane_group_extension import EXPLICIT_LANE_GROUP_FIFO


def _compile_a():
    return compile_network(fixture_a_source(), overrides=fixture_a_overrides())


def _link_derivations(result, link_id: str) -> dict[str, PhysicalDerivationRecord]:
    return {
        item.target_field: item
        for item in result.derivations
        if item.artifact_id == f"link:{link_id}"
    }


def _run_a():
    result = _compile_a()
    assert result.is_executable
    engine = result.require_executable().build_loading_engine()
    packet = engine.instantiate(DemandDeclaration("through", 0, ("U1", "M", "O1")))
    assert packet is not None
    for _ in range(5):
        engine.step()
    return engine, packet.packet_id


def test_fixture_a_is_executable_with_mixed_field_level_provenance() -> None:
    result = _compile_a()

    assert result.disposition == CompilationDisposition.EXECUTABLE_WITH_WARNINGS
    assert result.is_executable
    classes = {item.classification for item in result.provenance}
    assert {
        ProvenanceClass.OBSERVED,
        ProvenanceClass.INFERRED,
        ProvenanceClass.DEFAULTED,
        ProvenanceClass.OVERRIDDEN,
    }.issubset(classes)
    assert ProvenanceClass.UNRESOLVED not in classes
    assert all(len(item.record_hash) == 64 for item in result.provenance)
    assert any(item.severity == DiagnosticSeverity.WARNING for item in result.diagnostics)
    with pytest.raises(FrozenInstanceError):
        result.provenance[0].reason = "mutated"  # type: ignore[misc]


def test_exact_initial_link_rules_select_observed_inferred_defaulted_and_override() -> None:
    result = _compile_a()
    by_target = {(item.artifact_id, item.field_path): item for item in result.provenance}

    assert by_target[("link:U1", "lane_count")].classification == ProvenanceClass.OBSERVED
    assert by_target[("link:U2", "lane_count")].classification == ProvenanceClass.DEFAULTED
    assert by_target[("link:M", "lane_count")].classification == ProvenanceClass.INFERRED
    assert by_target[("link:X", "free_flow_speed_mps")].classification == ProvenanceClass.DEFAULTED
    assert (
        by_target[("link:X", "capacity_veh_per_hour_per_lane")].classification
        == ProvenanceClass.DEFAULTED
    )
    speed_override = by_target[("link:O1", "free_flow_speed_mps")]
    assert speed_override.classification == ProvenanceClass.OVERRIDDEN
    assert speed_override.override_id == "override:O1:speed"
    assert speed_override.resolved_value == 10.0


def test_every_emitted_link_has_all_mandatory_numeric_semantics_and_storage() -> None:
    result = _compile_a()
    assert result.is_executable
    for link in result.resolved_graph.links:
        assert link.is_executable
        assert all(getattr(link, field) is not None for field in MANDATORY_LINK_FIELDS)
        assert link.storage_capacity_packets is not None
        assert link.storage_capacity_packets > 0
    assert set(result.require_executable().loading_links()) == {
        item.link_id for item in result.resolved_graph.links
    }


def test_physical_derivations_separate_source_continuous_and_loader_values() -> None:
    result = _compile_a()
    u1 = _link_derivations(result, "U1")

    assert u1["length_m"].normalized_value == 10.0
    assert u1["length_m"].normalized_unit == "metres"
    assert u1["free_flow_speed_mps"].source_unit == "metres_per_second"
    assert u1["free_flow_speed_mps"].normalized_value == 10.0
    assert u1["free_flow_travel_time_seconds"].normalized_value == 1.0
    assert u1["free_flow_lag_ticks"].executable_value == 1
    assert u1["backward_wave_speed_mps"].normalized_value == 5.0
    assert u1["backward_wave_travel_time_seconds"].normalized_value == 2.0
    assert u1["backward_wave_lag_ticks"].executable_value == 2
    assert u1["capacity_veh_per_hour_per_lane"].normalized_value == 3600.0
    assert u1["total_capacity_vehicles_per_hour"].normalized_value == 3600.0
    assert u1["continuous_capacity_vehicles_per_tick"].normalized_value == 1.0
    assert u1["declared_sending_capacity_per_tick"].executable_value == 1
    assert u1["declared_receiving_capacity_per_tick"].executable_value == 1
    assert u1["jam_density_veh_per_km_per_lane"].normalized_value == 200.0
    assert u1["continuous_storage_vehicles"].normalized_value == 2.0
    assert u1["declared_storage_capacity_packets"].executable_value == 2
    assert u1["tick_duration_seconds"].executable_value == 1.0
    loader_link = result.require_executable().loading_links()["U1"]
    loader_physics = loader_link.resolved_physical_parameters()
    assert loader_physics.free_flow_lag_ticks == u1["free_flow_lag_ticks"].executable_value
    assert loader_physics.backward_wave_lag_ticks == u1["backward_wave_lag_ticks"].executable_value


def test_kph_and_mph_speed_conversions_are_unit_explicit() -> None:
    kph = _link_derivations(_compile_a(), "M")["free_flow_speed_mps"]
    assert kph.source_value == 36
    assert kph.source_unit == "kilometres_per_hour"
    assert kph.normalized_value == pytest.approx(10.0)
    assert kph.formula_id == "uc.formula.speed.kph-over-3.6"

    payload = deepcopy(fixture_a_payload())
    for record in payload["records"]:
        if record.get("id") == "U1":
            record["fields"].pop("speed_mps")
            record["fields"]["maxspeed"] = "10 mph"
    mph_result = compile_network(
        adapt_osm_like(payload), overrides=fixture_a_overrides()
    )
    mph = _link_derivations(mph_result, "U1")["free_flow_speed_mps"]
    assert mph.source_value == "10 mph"
    assert mph.source_unit == "miles_per_hour"
    assert mph.normalized_value == pytest.approx(4.4704)
    assert mph.formula_id == "uc.formula.speed.mph-times-1.609344-over-3.6"


def test_lag_capacity_and_storage_discretisation_records_error_and_clamps() -> None:
    result = _compile_a()
    u2 = _link_derivations(result, "U2")
    capacity = u2["declared_sending_capacity_per_tick"]
    assert u2["continuous_capacity_vehicles_per_tick"].normalized_value == pytest.approx(
        1 / 3
    )
    assert capacity.rounding_policy == "floor_then_minimum_one"
    assert capacity.executable_value == 1
    assert capacity.absolute_discretization_error == pytest.approx(2 / 3)
    assert capacity.relative_discretization_error == pytest.approx(2.0)
    assert capacity.clamp_activated

    storage = u2["declared_storage_capacity_packets"]
    assert u2["continuous_storage_vehicles"].normalized_value == pytest.approx(1.5)
    assert storage.executable_value == 1
    assert storage.absolute_discretization_error == pytest.approx(0.5)
    assert storage.relative_discretization_error == pytest.approx(1 / 3)
    assert not storage.clamp_activated
    assert {item.code for item in result.diagnostics} >= {
        "UC.DISCRETIZATION.MINIMUM_ONE_CLAMP",
        "UC.DISCRETIZATION.RELATIVE_ERROR",
    }


def test_non_integral_free_flow_and_backward_wave_lags_use_ceil() -> None:
    payload = deepcopy(fixture_a_payload())
    for record in payload["records"]:
        if record.get("id") == "U1":
            record["fields"]["speed_mps"] = 6.0
            record["fields"]["backward_wave_speed_mps"] = 6.0
    result = compile_network(adapt_osm_like(payload), overrides=fixture_a_overrides())
    u1 = _link_derivations(result, "U1")
    assert u1["free_flow_travel_time_seconds"].normalized_value == pytest.approx(10 / 6)
    assert u1["free_flow_lag_ticks"].executable_value == 2
    assert u1["free_flow_lag_ticks"].rounding_policy == "ceil_then_minimum_one"
    assert u1["backward_wave_travel_time_seconds"].normalized_value == pytest.approx(10 / 6)
    assert u1["backward_wave_lag_ticks"].executable_value == 2


def test_all_rounding_policy_names_and_derivation_hashes_are_stable() -> None:
    records = []
    for policy in sorted(ROUNDING_POLICIES):
        records.append(
            PhysicalDerivationRecord.create(
                artifact_id="link:test",
                target_field=f"field:{policy}",
                source_value=1.25,
                source_unit="vehicles",
                normalized_value=1.25,
                normalized_unit="vehicles",
                executable_value=1,
                executable_unit="unit_packets",
                formula_id="uc.formula.test",
                formula_version="1",
                rounding_policy=policy,
                tick_duration_seconds=1.0,
                reason="rounding-policy schema test",
            )
        )
    assert {item.rounding_policy for item in records} == ROUNDING_POLICIES
    assert all(
        item.derivation_hash == PhysicalDerivationRecord.from_dict(item.to_dict()).derivation_hash
        for item in records
    )
    with pytest.raises(ValueError, match="unsupported rounding policy"):
        replace(records[0], rounding_policy="nearest")


def test_discretisation_warning_threshold_is_configured_and_hash_bound() -> None:
    baseline = _compile_a()
    relaxed = compile_network(
        fixture_a_source(),
        config=CompilerConfig(discretization_relative_error_warning_threshold=10.0),
        overrides=fixture_a_overrides(),
    )
    assert any(
        item.code == "UC.DISCRETIZATION.RELATIVE_ERROR"
        for item in baseline.diagnostics
    )
    assert not any(
        item.code == "UC.DISCRETIZATION.RELATIVE_ERROR"
        for item in relaxed.diagnostics
    )
    assert any(
        item.code == "UC.DISCRETIZATION.MINIMUM_ONE_CLAMP"
        for item in relaxed.diagnostics
    )
    assert (
        baseline.evidence_bundle.executable_semantic_hash
        == relaxed.evidence_bundle.executable_semantic_hash
    )
    assert (
        baseline.evidence_bundle.compilation_identity_hash
        != relaxed.evidence_bundle.compilation_identity_hash
    )


def test_turn_prohibition_and_topological_legal_movement_are_distinct() -> None:
    result = _compile_a()
    movements = {item.movement_id: item for item in result.resolved_graph.movements}
    provenance = {(item.artifact_id, item.field_path): item for item in result.provenance}

    assert movements["movement:U2->X"].permitted is False
    assert movements["movement:U2->M"].permitted is True
    assert provenance[("movement:U2->X", "permitted")].classification == ProvenanceClass.OBSERVED
    assert provenance[("movement:U2->M", "permitted")].classification == ProvenanceClass.INFERRED
    j1 = next(item for item in result.require_executable().topology.nodes if item.node_id == "J1")  # type: ignore[union-attr]
    assert "movement:U2->X" not in j1.junction_spec().movement_by_id


def test_lane_group_output_uses_explicit_partition_shared_fallback_and_frozen_resources() -> None:
    result = _compile_a()
    assert result.is_executable
    config = result.require_executable().lane_group_config

    assert config.representation_mode == EXPLICIT_LANE_GROUP_FIFO
    assert {item.lane_group_id for item in config.lane_groups} == {
        "partition:J1:U1:shared",
        "shared:J1:U2",
    }
    j2 = next(item for item in result.require_executable().topology.nodes if item.node_id == "J2")
    assert j2.lane_group_ids == (
        "resource:J2:M:shared",
        "resource:J2:V:shared",
    )
    config.validate_against_nodes(result.require_executable().topology.as_loading_nodes())
    assert any(item.code == "UC.LANE_GROUP.SHARED_FALLBACK" for item in result.diagnostics)


def test_fixed_time_plan_targets_existing_resolved_contract_and_binds_to_topology() -> None:
    result = _compile_a()
    assert result.is_executable
    plan = result.require_executable().signal_plan

    assert plan.schema_version == FIXED_TIME_SIGNAL_SCHEMA_VERSION
    assert plan.controllers[0].cycle_ticks == 3
    assert tuple(item.duration_ticks for item in plan.controllers[0].stages) == (2, 1)
    engine = result.require_executable().build_loading_engine()
    state = engine.signal_gate_state("movement:U1->M", 1)
    assert state is not None and state.baseline_is_open


def test_compile_time_signal_override_changes_immutable_baseline_not_runtime_commands() -> None:
    offset_override = CompilerOverride.create(
        override_id="override:J1:offset",
        target_artifact_id="controller:J1",
        target_field="offset_ticks",
        replacement_value=1,
        actor="fixture-reviewer",
        source="timing-sheet",
        reason="surveyed controller offset",
    )
    result = compile_network(
        fixture_a_source(), overrides=fixture_a_overrides() + (offset_override,)
    )

    assert result.is_executable
    assert result.require_executable().signal_plan.controllers[0].offset_ticks == 1
    record = next(
        item
        for item in result.provenance
        if item.artifact_id == "controller:J1" and item.field_path == "offset_ticks"
    )
    assert record.classification == ProvenanceClass.OVERRIDDEN
    assert record.override_id == offset_override.override_id


def test_fixture_b_preserves_unresolved_signal_timing_and_refuses_plan() -> None:
    result = compile_network(fixture_b_source(), overrides=fixture_a_overrides())

    assert result.disposition == CompilationDisposition.UNRESOLVED
    assert not result.is_executable
    unresolved = [
        item
        for item in result.provenance
        if item.artifact_id == "controller:J1"
        and item.classification == ProvenanceClass.UNRESOLVED
    ]
    assert {item.field_path for item in unresolved} == {
        "stage:stage:J1:clear:duration_ticks"
    }
    assert any(item.code == "UC.SIGNAL.PLAN_REFUSED" for item in result.diagnostics)
    controller = next(
        item
        for item in result.normalized_graph.records
        if item.record_type == "signal_controller"
    )
    assert controller.values("signalized")[0].normalized_value is True
    assert result.evidence_bundle.signal_plan_hashes == ()


def test_refusal_safety_is_a_result_construction_invariant() -> None:
    successful = _compile_a()
    refused = compile_network(fixture_b_source(), overrides=fixture_a_overrides())

    with pytest.raises(CompilationResultInvariantError, match="successful disposition"):
        replace(refused, _executable=successful.require_executable())
    with pytest.raises(CompilationResultInvariantError, match="successful disposition"):
        replace(successful, _executable=None)
    with pytest.raises(CompilationResultInvariantError, match="disposition"):
        replace(successful, disposition=CompilationDisposition.UNRESOLVED)
    forged_artifact = replace(
        successful.require_executable(), tick_duration_seconds=2.0
    )
    with pytest.raises(CompilationResultInvariantError, match="executable hashes"):
        replace(successful, _executable=forged_artifact)
    with pytest.raises(CompilationResultInvariantError, match="successful disposition"):
        type(successful)(
            source_evidence=successful.source_evidence,
            normalized_graph=successful.normalized_graph,
            resolved_graph=successful.resolved_graph,
            _executable=None,
            diagnostics=successful.diagnostics,
            provenance=successful.provenance,
            derivations=successful.derivations,
            evidence_bundle=successful.evidence_bundle,
            disposition=successful.disposition,
        )


def test_require_executable_fails_closed_with_disposition_and_diagnostic_codes() -> None:
    successful = _compile_a()
    refused = compile_network(fixture_b_source(), overrides=fixture_a_overrides())

    assert successful.require_executable().executable_semantic_hash == (
        successful.evidence_bundle.executable_semantic_hash
    )
    with pytest.raises(CompilationNotExecutableError) as captured:
        refused.require_executable()
    assert captured.value.disposition == CompilationDisposition.UNRESOLVED
    assert "UC.SIGNAL.PLAN_REFUSED" in captured.value.diagnostic_codes
    assert refused.normalized_graph.records
    assert refused.provenance
    assert refused.diagnostics
    assert refused.evidence_bundle.executable_artifacts_json is None


def test_forged_success_failure_json_and_artifact_hashes_are_rejected() -> None:
    successful = _compile_a().evidence_bundle
    refused = compile_network(
        fixture_b_source(), overrides=fixture_a_overrides()
    ).evidence_bundle

    forged_refusal = deepcopy(successful.to_dict())
    forged_refusal["disposition"] = CompilationDisposition.UNRESOLVED.value
    with pytest.raises(EvidenceBundleIntegrityError, match="successful disposition"):
        CompilerEvidenceBundle.from_dict(forged_refusal)

    forged_success = deepcopy(refused.to_dict())
    forged_success["disposition"] = CompilationDisposition.EXECUTABLE.value
    with pytest.raises(EvidenceBundleIntegrityError, match="successful disposition"):
        CompilerEvidenceBundle.from_dict(forged_success)

    semantic_tamper = deepcopy(successful.to_dict())
    semantic_tamper["executable_artifacts"]["executable_semantic_hash"] = "0" * 64
    with pytest.raises(EvidenceBundleIntegrityError, match="executable_semantic_hash"):
        CompilerEvidenceBundle.from_dict(semantic_tamper)

    identity_tamper = deepcopy(successful.to_dict())
    identity_tamper["compilation_identity_hash"] = "0" * 64
    identity_tamper["complete_result_hash"] = "0" * 64
    with pytest.raises(EvidenceBundleIntegrityError, match="compilation_identity_hash"):
        CompilerEvidenceBundle.from_dict(identity_tamper)

    alias_tamper = deepcopy(successful.to_dict())
    alias_tamper["complete_result_hash"] = "0" * 64
    with pytest.raises(EvidenceBundleIntegrityError, match="alias"):
        CompilerEvidenceBundle.from_dict(alias_tamper)


def test_fixture_c_rejects_conflicting_turn_restrictions_deterministically() -> None:
    first = compile_network(fixture_c_source(), overrides=fixture_a_overrides())
    second = compile_network(fixture_c_source(), overrides=fixture_a_overrides())

    assert not first.is_executable
    assert first.disposition == CompilationDisposition.UNRESOLVED
    assert first.diagnostics == second.diagnostics
    assert first.evidence_bundle.complete_result_hash == second.evidence_bundle.complete_result_hash
    assert any(item.code == "UC.MOVEMENT.CONFLICTING_RESTRICTIONS" for item in first.diagnostics)


def test_fixture_d_override_repairs_conflict_and_retains_prior_values() -> None:
    before = compile_network(fixture_d_source(), overrides=fixture_a_overrides())
    after = compile_network(fixture_d_source(), overrides=fixture_d_overrides())

    assert not before.is_executable
    assert any(
        item.artifact_id == "link:U2"
        and item.field_path == "lane_count"
        and item.classification == ProvenanceClass.UNRESOLVED
        for item in before.provenance
    )
    assert after.is_executable
    repair = next(
        item
        for item in after.provenance
        if item.artifact_id == "link:U2" and item.field_path == "lane_count"
    )
    assert repair.classification == ProvenanceClass.OVERRIDDEN
    assert json.loads(repair.prior_value_json) == [1, 2]
    assert set(repair.evidence_refs)
    assert any(item.code == "UC.OVERRIDE.REPAIRED_CONFLICT" for item in after.diagnostics)


def test_fixture_e_is_order_independent_for_every_semantic_evidence_identity() -> None:
    a = _compile_a()
    e = compile_network(fixture_e_source(), overrides=tuple(reversed(fixture_a_overrides())))

    assert a.source_evidence.evidence_hash == e.source_evidence.evidence_hash
    assert a.normalized_graph.normalized_hash == e.normalized_graph.normalized_hash
    assert a.resolved_graph.semantic_hash == e.resolved_graph.semantic_hash
    assert a.is_executable and e.is_executable
    assert a.require_executable().topology.topology_hash == e.require_executable().topology.topology_hash
    assert a.require_executable().signal_plan.to_dict() == e.require_executable().signal_plan.to_dict()
    assert a.require_executable().lane_group_config == e.require_executable().lane_group_config
    assert a.evidence_bundle.provenance_bundle_hash == e.evidence_bundle.provenance_bundle_hash
    assert a.evidence_bundle.diagnostics_bundle_hash == e.evidence_bundle.diagnostics_bundle_hash
    assert a.evidence_bundle.complete_result_hash == e.evidence_bundle.complete_result_hash
    assert (
        a.evidence_bundle.executable_semantic_hash
        == e.evidence_bundle.executable_semantic_hash
    )
    assert (
        a.evidence_bundle.compilation_identity_hash
        == e.evidence_bundle.compilation_identity_hash
    )
    assert a.evidence_bundle.evidence_bundle_hash == e.evidence_bundle.evidence_bundle_hash


def test_numeric_and_textual_numbers_share_executable_semantics_not_audit_identity() -> None:
    numeric = _compile_a()
    textual_payload = deepcopy(fixture_a_payload())
    for record in textual_payload["records"]:
        if record.get("id") == "U1":
            record["fields"]["speed_mps"] = "10"
    textual = compile_network(
        adapt_osm_like(textual_payload), overrides=fixture_a_overrides()
    )

    assert numeric.require_executable().loading_links() == textual.require_executable().loading_links()
    assert (
        numeric.evidence_bundle.executable_semantic_hash
        == textual.evidence_bundle.executable_semantic_hash
    )
    assert (
        numeric.evidence_bundle.compilation_identity_hash
        != textual.evidence_bundle.compilation_identity_hash
    )


def test_unused_configuration_changes_compilation_identity_only() -> None:
    baseline = _compile_a()
    configured = compile_network(
        fixture_a_source(),
        config=CompilerConfig(allow_default_signal_plans=True),
        overrides=fixture_a_overrides(),
    )
    assert (
        baseline.evidence_bundle.executable_semantic_hash
        == configured.evidence_bundle.executable_semantic_hash
    )
    assert (
        baseline.evidence_bundle.compilation_identity_hash
        != configured.evidence_bundle.compilation_identity_hash
    )


def test_used_default_and_value_changing_override_change_both_hash_domains() -> None:
    baseline = _compile_a()
    changed_default = compile_network(
        fixture_a_source(),
        config=CompilerConfig(jam_density_veh_per_km_per_lane_default=175.0),
        overrides=fixture_a_overrides(),
    )
    changed_override = CompilerOverride.create(
        override_id="override:O1:speed",
        target_artifact_id="link:O1",
        target_field="free_flow_speed_mps",
        replacement_value=9.0,
        actor="fixture-author",
        source="fixture-a-review",
        reason="different reviewed speed",
        precedence=100,
    )
    overridden = compile_network(fixture_a_source(), overrides=(changed_override,))

    for changed in (changed_default, overridden):
        assert (
            baseline.evidence_bundle.executable_semantic_hash
            != changed.evidence_bundle.executable_semantic_hash
        )
        assert (
            baseline.evidence_bundle.compilation_identity_hash
            != changed.evidence_bundle.compilation_identity_hash
        )


def test_audit_only_override_metadata_changes_compilation_identity_only() -> None:
    baseline = _compile_a()
    original = fixture_a_overrides()[0]
    audit_variant = CompilerOverride.create(
        override_id=original.override_id,
        target_artifact_id=original.target_artifact_id,
        target_field=original.target_field,
        replacement_value=original.replacement_value,
        actor="second-reviewer",
        source="independent-audit-log",
        reason="same value independently confirmed",
        precedence=original.precedence,
    )
    changed = compile_network(fixture_a_source(), overrides=(audit_variant,))

    assert (
        baseline.evidence_bundle.executable_semantic_hash
        == changed.evidence_bundle.executable_semantic_hash
    )
    assert (
        baseline.evidence_bundle.compilation_identity_hash
        != changed.evidence_bundle.compilation_identity_hash
    )
    assert baseline.require_executable().compatibility_hash == (
        baseline.evidence_bundle.executable_semantic_hash
    )


def test_noop_override_is_audit_identity_not_executable_identity() -> None:
    baseline = _compile_a()
    noop = CompilerOverride.create(
        override_id="override:U1:speed:no-op",
        target_artifact_id="link:U1",
        target_field="free_flow_speed_mps",
        replacement_value=10.0,
        actor="reviewer",
        source="audit",
        reason="confirm the observed value without changing it",
    )
    changed = compile_network(
        fixture_a_source(), overrides=fixture_a_overrides() + (noop,)
    )
    assert (
        baseline.evidence_bundle.executable_semantic_hash
        == changed.evidence_bundle.executable_semantic_hash
    )
    assert (
        baseline.evidence_bundle.compilation_identity_hash
        != changed.evidence_bundle.compilation_identity_hash
    )


def test_evidence_bundle_round_trip_and_tamper_detection_cover_values_and_hashes() -> None:
    bundle = _compile_a().evidence_bundle
    assert CompilerEvidenceBundle.from_json(bundle.to_json()) == bundle

    provenance_tamper = deepcopy(bundle.to_dict())
    provenance_tamper["provenance"][0]["resolved_value"] = "tampered"
    with pytest.raises(EvidenceBundleIntegrityError, match="provenance record hash"):
        CompilerEvidenceBundle.from_dict(provenance_tamper)

    diagnostic_tamper = deepcopy(bundle.to_dict())
    diagnostic_tamper["diagnostics"][0]["message"] = "tampered"
    with pytest.raises(EvidenceBundleIntegrityError, match="diagnostic hash"):
        CompilerEvidenceBundle.from_dict(diagnostic_tamper)

    derivation_tamper = deepcopy(bundle.to_dict())
    derivation_tamper["derivations"][0]["normalized_value"] = 999.0
    with pytest.raises(EvidenceBundleIntegrityError, match="physical derivation hash"):
        CompilerEvidenceBundle.from_dict(derivation_tamper)

    hash_tamper = deepcopy(bundle.to_dict())
    hash_tamper["executable_topology_hash"] = "0" * 64
    with pytest.raises(EvidenceBundleIntegrityError, match="executable_topology_hash"):
        CompilerEvidenceBundle.from_dict(hash_tamper)

    artifact_tamper = deepcopy(bundle.to_dict())
    artifact_tamper["executable_artifacts"]["loading_links"][0]["length_m"] = 999.0
    with pytest.raises(EvidenceBundleIntegrityError, match="loader links"):
        CompilerEvidenceBundle.from_dict(artifact_tamper)

    config_tamper = deepcopy(bundle.to_dict())
    config_tamper["compiler_configuration"]["allow_road_class_defaults"] = False
    with pytest.raises(EvidenceBundleIntegrityError, match="configuration_hash"):
        CompilerEvidenceBundle.from_dict(config_tamper)


def test_malformed_mandatory_value_is_retained_reported_and_never_loaded() -> None:
    payload = {
        "network_id": "malformed",
        "records": [
            {"evidence_id": "n:a", "type": "node", "id": "a"},
            {"evidence_id": "n:b", "type": "node", "id": "b"},
            {
                "evidence_id": "l:x",
                "type": "link",
                "id": "x",
                "fields": {
                    "tail_node_id": "a",
                    "head_node_id": "b",
                    "travel_direction": "forward",
                    "highway": "residential",
                    "length_m": "not-a-length",
                    "lane_count": 1,
                    "speed_mps": 10,
                    "capacity_veh_per_hour_per_lane": 1200,
                },
            },
        ],
    }
    result = compile_network(adapt_osm_like(payload))

    assert not result.is_executable
    assert any(item.code == "UC.SOURCE.MALFORMED_FIELD_RETAINED" for item in result.diagnostics)
    assert any(
        item.artifact_id == "link:x"
        and item.field_path == "length_m"
        and item.classification == ProvenanceClass.UNRESOLVED
        for item in result.provenance
    )
    length = next(
        field
        for record in result.normalized_graph.records
        if record.source_id == "x"
        for field in record.fields
        if field.name == "length_m"
    )
    assert length.raw_value == "not-a-length"
    assert length.parse_status == "malformed"


def test_duplicate_ids_are_structural_errors() -> None:
    payload = {
        "network_id": "duplicates",
        "records": [
            {"evidence_id": "same", "type": "node", "id": "a"},
            {"evidence_id": "same", "type": "node", "id": "a"},
        ],
    }
    result = compile_network(adapt_osm_like(payload))

    assert result.disposition == CompilationDisposition.STRUCTURALLY_INVALID
    assert not result.is_executable
    assert {item.code for item in result.diagnostics} >= {
        "UC.SOURCE.DUPLICATE_EVIDENCE_ID",
        "UC.SOURCE.DUPLICATE_RECORD_ID",
    }


def test_invalid_lane_group_reference_is_a_source_error_not_an_invented_repair() -> None:
    payload = deepcopy(fixture_a_payload())
    for record in payload["records"]:
        if record.get("id") == "partition:J1:U1:shared":
            record["fields"]["allowed_movement_ids"] = ["movement:U1->missing"]
    result = compile_network(adapt_osm_like(payload), overrides=fixture_a_overrides())

    assert not result.is_executable
    assert result.disposition == CompilationDisposition.STRUCTURALLY_INVALID
    assert any(item.code == "UC.LANE_GROUP.INVALID_MOVEMENT_REFERENCE" for item in result.diagnostics)


def test_override_precedence_is_deterministic_and_tied_conflicts_refuse() -> None:
    low = CompilerOverride.create(
        override_id="override:low",
        target_artifact_id="link:O1",
        target_field="free_flow_speed_mps",
        replacement_value=7.0,
        actor="a",
        source="s",
        reason="low",
        precedence=1,
    )
    high = CompilerOverride.create(
        override_id="override:high",
        target_artifact_id="link:O1",
        target_field="free_flow_speed_mps",
        replacement_value=9.0,
        actor="a",
        source="s",
        reason="high",
        precedence=2,
    )
    selected = compile_network(fixture_a_source(), overrides=(low, high))
    assert selected.is_executable
    assert next(item for item in selected.resolved_graph.links if item.link_id == "O1").free_flow_speed_mps == 9.0

    tied = CompilerOverride.create(
        override_id="override:tied",
        target_artifact_id="link:O1",
        target_field="free_flow_speed_mps",
        replacement_value=8.0,
        actor="a",
        source="s",
        reason="tie",
        precedence=2,
    )
    refused = compile_network(fixture_a_source(), overrides=(high, tied))
    assert not refused.is_executable
    assert refused.disposition == CompilationDisposition.STRUCTURALLY_INVALID
    assert any(item.code == "UC.COMPILER.OVERRIDE_CONFLICT" for item in refused.diagnostics)


def test_compiled_network_loads_replays_conserves_and_reruns_exactly() -> None:
    engine, packet_id = _run_a()
    assert engine.packets[packet_id].lifecycle_state == LifecycleState.COMPLETED

    report = validate_loading_kernel(engine, exact_rerun_factory=lambda: _run_a()[0])
    assert report.is_valid
    assert all(item.passed is True for item in report.checks)
    assert engine.fixed_time_signal_evidence
    assert engine.movement_allocator.assigned_lane_group("J1", packet_id) == (
        "partition:J1:U1:shared"
    )


def test_result_hash_changes_with_configuration_that_changes_resolution() -> None:
    from urban_cybernetics.compiler import CompilerConfig

    baseline = _compile_a()
    changed = compile_network(
        fixture_a_source(),
        config=CompilerConfig(jam_density_veh_per_km_per_lane_default=175.0),
        overrides=fixture_a_overrides(),
    )
    assert baseline.evidence_bundle.compiler_configuration_hash != changed.evidence_bundle.compiler_configuration_hash
    assert baseline.evidence_bundle.complete_result_hash != changed.evidence_bundle.complete_result_hash
    assert next(item for item in baseline.resolved_graph.links if item.link_id == "U2").jam_density_veh_per_km_per_lane == 150.0
    assert next(item for item in changed.resolved_graph.links if item.link_id == "U2").jam_density_veh_per_km_per_lane == 175.0


def test_complete_lane_index_evidence_enables_deterministic_inferred_groups() -> None:
    records = [
        {"evidence_id": f"n:{node}", "type": "node", "id": node}
        for node in ("A", "J", "B", "C")
    ]
    for link_id, tail, head, lanes in (
        ("U", "A", "J", 2),
        ("L", "J", "B", 1),
        ("R", "J", "C", 1),
    ):
        records.append(
            {
                "evidence_id": f"l:{link_id}",
                "type": "link",
                "id": link_id,
                "fields": {
                    "tail_node_id": tail,
                    "head_node_id": head,
                    "travel_direction": "forward",
                    "highway": "residential",
                    "length_m": 10,
                    "lane_count": lanes,
                    "speed_mps": 10,
                    "capacity_veh_per_hour_per_lane": 1200,
                },
            }
        )
    for downstream, lane_index in (("L", 1), ("R", 2)):
        records.append(
            {
                "evidence_id": f"turn:U-{downstream}",
                "type": "turn",
                "id": f"U-{downstream}",
                "fields": {
                    "upstream_link_id": "U",
                    "downstream_link_id": downstream,
                    "permission": "allow",
                    "lane_indices": [lane_index],
                },
            }
        )
    result = compile_network(
        adapt_osm_like({"network_id": "inferred-groups", "records": records})
    )

    assert result.is_executable
    groups = result.require_executable().lane_group_config.lane_groups
    assert {item.lane_group_id for item in groups} == {
        "inferred:J:U:lane:1",
        "inferred:J:U:lane:2",
    }
    assert all(item.provenance.status == "inferred" for item in groups)
    assert all(
        item.classification == ProvenanceClass.INFERRED
        for item in result.provenance
        if item.artifact_id.startswith("lane-group:inferred:")
    )


def test_signal_default_requires_explicit_configuration_permission() -> None:
    from urban_cybernetics.compiler import CompilerConfig

    refused = compile_network(fixture_b_source(), overrides=fixture_a_overrides())
    permitted = compile_network(
        fixture_b_source(),
        config=CompilerConfig(allow_default_signal_plans=True),
        overrides=fixture_a_overrides(),
    )

    assert not refused.is_executable
    assert permitted.is_executable
    controller = permitted.require_executable().signal_plan.controllers[0]
    assert controller.cycle_ticks == 4
    assert len(controller.stages) == 1
    assert controller.stages[0].stage_id == "default:controller:J1:all-green"
    assert any(
        item.artifact_id == "controller:J1"
        and item.field_path == "stages"
        and item.classification == ProvenanceClass.DEFAULTED
        for item in permitted.provenance
    )


def test_disabling_shared_lane_fallback_refuses_unsafe_detail_invention() -> None:
    from urban_cybernetics.compiler import CompilerConfig

    result = compile_network(
        fixture_a_source(),
        config=CompilerConfig(allow_conservative_shared_lane_fallback=False),
        overrides=fixture_a_overrides(),
    )

    assert not result.is_executable
    assert result.disposition == CompilationDisposition.UNRESOLVED
    assert any(item.code == "UC.LANE_GROUP.UNRESOLVED_PARTITION" for item in result.diagnostics)


def test_unknown_turn_links_and_multiple_signal_owners_are_structural_refusals() -> None:
    unknown_payload = deepcopy(fixture_a_payload())
    unknown_payload["records"].append(
        {
            "evidence_id": "turn:unknown",
            "type": "turn",
            "id": "unknown",
            "fields": {
                "upstream_link_id": "missing",
                "downstream_link_id": "M",
                "permission": "allow",
            },
        }
    )
    unknown = compile_network(
        adapt_osm_like(unknown_payload), overrides=fixture_a_overrides()
    )
    assert unknown.disposition == CompilationDisposition.STRUCTURALLY_INVALID
    assert any(item.code == "UC.MOVEMENT.UNKNOWN_LINK_REFERENCE" for item in unknown.diagnostics)

    owner_payload = deepcopy(fixture_a_payload())
    owner_payload["records"].extend(
        [
            {
                "evidence_id": "controller:duplicate:evidence",
                "type": "signal_controller",
                "id": "controller:J1:duplicate",
                "fields": {
                    "node_id": "J1",
                    "signalized": True,
                    "controlled_movement_ids": ["movement:U1->M"],
                    "stage_ids": ["stage:J1:duplicate"],
                    "cycle_ticks": 3,
                    "offset_ticks": 0,
                },
            },
            {
                "evidence_id": "stage:duplicate:evidence",
                "type": "signal_stage",
                "id": "stage:J1:duplicate",
                "fields": {
                    "controller_id": "controller:J1:duplicate",
                    "duration_ticks": 3,
                    "permitted_movement_ids": ["movement:U1->M"],
                },
            },
        ]
    )
    ownership = compile_network(
        adapt_osm_like(owner_payload), overrides=fixture_a_overrides()
    )
    assert ownership.disposition == CompilationDisposition.STRUCTURALLY_INVALID
    assert not ownership.is_executable
    assert any(item.code == "UC.SIGNAL.MULTIPLE_CONTROLLER_OWNERS" for item in ownership.diagnostics)
