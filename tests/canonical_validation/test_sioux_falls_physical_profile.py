"""Sioux Falls engineering-assumption physical profile tests."""

from __future__ import annotations

from dataclasses import replace
from math import floor, isclose

from urban_cybernetics.canonical_validation.sioux_falls_physical_profile import (
    ENGINEERING_ASSUMPTION_NOT_CALIBRATION,
    JAM_DENSITY_EQUATION,
    SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
    SIOUX_FALLS_UC_DEFAULT_PROFILE_ID,
    STORAGE_CAPACITY_EQUATION,
    build_sioux_falls_uc_default_physical_profile,
    derive_jam_density_veh_per_km_per_lane,
    derive_storage_capacity_packets,
)
from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    REPLAY_FAILED_MISMATCH,
    REPLAY_PASSED_EXACT,
    REPLAY_SKIPPED_AFTER_CERTIFICATION,
    SCALE_FAILED_REPLAY_MISMATCH,
    SCALE_PASSED,
    SiouxFallsReplayPolicy,
    build_sioux_falls_assumption_profile_determinism_report,
    build_sioux_falls_assumption_profile_run_report,
    build_sioux_falls_assumption_profile_scale_ladder_report,
)
from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.topology import load_sioux_falls_topology
from urban_cybernetics.validation import assess_physical_parameter_eligibility


def test_uc_default_profile_derives_jam_density_from_triangular_fd() -> None:
    jam_density = derive_jam_density_veh_per_km_per_lane(
        capacity_veh_per_hour_per_lane=1800.0,
        free_flow_speed_mps=15.0,
        backward_wave_speed_mps=5.0,
    )

    assert isclose(jam_density, 133.33333333333334)


def test_uc_default_profile_derives_storage_from_length_lanes_and_density() -> None:
    storage = derive_storage_capacity_packets(
        length_m=1609.344,
        lane_count=1,
        jam_density_veh_per_km_per_lane=133.33333333333334,
    )

    assert storage == floor(1.609344 * 133.33333333333334)


def test_uc_default_profile_generation_is_deterministic() -> None:
    first = build_sioux_falls_uc_default_physical_profile()
    second = build_sioux_falls_uc_default_physical_profile()

    assert first.profile_id == SIOUX_FALLS_UC_DEFAULT_PROFILE_ID
    assert first.profile_hash == second.profile_hash
    assert first.status_payload() == second.status_payload()
    assert len(first.derived_links) == 76


def test_uc_default_profile_records_provenance_and_derivations() -> None:
    profile = build_sioux_falls_uc_default_physical_profile()
    assumptions = {
        assumption.field_name: assumption for assumption in profile.assumptions
    }

    assert profile.statement.startswith("This is a reproducible UC engineering")
    assert (
        assumptions["backward_wave_speed_mps"].provenance_label
        == ENGINEERING_ASSUMPTION_NOT_CALIBRATION
    )
    assert assumptions["backward_wave_speed_mps"].value == "5.0"
    assert JAM_DENSITY_EQUATION in profile.derivation_equations
    assert STORAGE_CAPACITY_EQUATION in profile.derivation_equations
    assert "declared_storage_capacity_packets" in profile.derived_fields


def test_uc_default_profile_retains_topology_hash_without_mutating_topology() -> None:
    topology = load_sioux_falls_topology()
    profile = build_sioux_falls_uc_default_physical_profile(topology=topology)

    assert profile.topology_hash == topology.topology_hash
    assert all(
        link.backward_wave_speed_mps is None
        and link.jam_density_veh_per_km_per_lane is None
        for link in topology.links
    )
    assert all(
        derived.backward_wave_speed_mps
        == SIOUX_FALLS_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS
        for derived in profile.derived_links
    )


def test_uc_default_profile_loading_links_are_triangular_fd_consistent() -> None:
    profile = build_sioux_falls_uc_default_physical_profile()
    links = profile.as_loading_links(tick_duration_seconds=60.0)
    report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )

    assert report.is_parity_eligible
    assert all(link_report.fd_report is not None for link_report in report.link_reports)
    assert all(
        link_report.fd_report is not None
        and link_report.fd_report.is_consistent
        for link_report in report.link_reports
    )
    assert all(
        links[link_report.link_id].declared_storage_capacity_packets
        == link_report.storage_capacity_packets
        for link_report in report.link_reports
    )


def test_uc_default_profile_summary_is_reproducible() -> None:
    profile = build_sioux_falls_uc_default_physical_profile()
    summary = profile.summary()

    assert summary.link_count == 76
    assert summary.backward_wave_speed_mps == 5.0
    assert summary.min_jam_density_veh_per_km_per_lane > 0
    assert summary.max_storage_capacity_packets >= summary.min_storage_capacity_packets
    assert summary.mean_capacity_veh_per_hour_per_lane > 0


def test_full_topology_assumption_profile_run_reports_validation_status() -> None:
    report = build_sioux_falls_assumption_profile_run_report(
        max_pairs=3,
        max_total_quantity_packets=6,
        tick_limit=300,
    )

    assert report.requested_model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID
    assert report.physical_profile_id == SIOUX_FALLS_UC_DEFAULT_PROFILE_ID
    assert report.topology_node_count == 24
    assert report.topology_link_count == 76
    assert report.run_completed
    assert report.validation_status == "passed"
    assert report.packet_conservation_passed
    assert report.count_consistency_passed
    assert report.fifo_validation_passed
    assert report.spillback_validation_passed
    assert report.commodity_validation_passed
    assert report.node_validation_passed
    assert report.deterministic_replay_passed
    assert report.replay_status == REPLAY_PASSED_EXACT
    assert report.internal_validation_status == "passed"
    assert not report.failures
    assert "engineering_assumption_profile_not_empirical_calibration" in report.warnings
    assert "bounded_demand_slice_not_full_od_demand_validation" in report.warnings


def test_fuller_assumption_profile_run_passes_fifo_validation() -> None:
    report = build_sioux_falls_assumption_profile_run_report(
        max_pairs=12,
        max_total_quantity_packets=24,
        tick_limit=600,
    )

    assert report.run_completed
    assert report.validation_status == "passed"
    assert report.packet_conservation_passed
    assert report.count_consistency_passed
    assert report.fifo_validation_passed
    assert report.spillback_validation_passed
    assert report.commodity_validation_passed
    assert report.node_validation_passed
    assert report.deterministic_replay_passed
    assert report.replay_status == REPLAY_PASSED_EXACT
    assert report.failed_validation_categories == ()
    assert report.failures == ()


def test_assumption_profile_run_reports_requested_and_unresolved_packets() -> None:
    report = build_sioux_falls_assumption_profile_run_report(
        max_pairs=3,
        max_total_quantity_packets=6,
        tick_limit=300,
    )

    assert report.requested_packet_count == 6
    assert report.scheduled_departure_count == 6
    assert report.submitted_departure_count == 6
    assert report.instantiated_packet_count == 6
    assert report.completed_packet_count == 6
    assert report.unresolved_packet_count == 0


def test_assumption_profile_scale_ladder_stops_after_first_failure() -> None:
    report = build_sioux_falls_assumption_profile_scale_ladder_report(
        bounded_packet_rungs=(6, 24),
        tick_limit=1,
        include_full_demand_run=False,
    )

    assert report.rung_reports[0].rung_label == "6"
    assert report.rung_reports[0].validation_status == "failed"
    assert report.rung_reports[0].failure_reason is not None
    assert len(report.rung_reports) == 1
    assert report.stopped_early
    assert report.stop_reason is not None
    assert not report.full_demand_run_attempted


def test_assumption_profile_scale_ladder_payload_is_json_ready() -> None:
    report = build_sioux_falls_assumption_profile_scale_ladder_report(
        bounded_packet_rungs=(6,),
        tick_limit=300,
        include_full_demand_run=False,
    )
    payload = report.status_payload()

    assert payload["benchmark_id"] == "sioux_falls_tntp_v1"
    assert payload["bounded_packet_rungs"] == (6,)
    assert payload["rung_reports"][0]["requested_packet_count"] == 6
    assert payload["rung_reports"][0]["validation_status"] == "passed"
    assert payload["rung_reports"][0]["replay_status"] == REPLAY_PASSED_EXACT
    assert not payload["full_demand_run_attempted"]


def test_assumption_profile_determinism_comparison_matches_small_case() -> None:
    report = build_sioux_falls_assumption_profile_determinism_report(
        max_total_quantity_packets=6,
        tick_limit=300,
    )

    assert report.matches
    assert report.replay_status == REPLAY_PASSED_EXACT
    assert report.first_divergence is None
    assert report.classification is None
    assert report.event_count_first == report.event_count_second
    assert report.event_log_fingerprint_first == report.event_log_fingerprint_second
    assert report.packet_lifecycle_matches
    assert report.conservation_matches
    assert report.validation_summary_matches
    assert report.completed_packet_set_matches


def test_replay_policy_allows_internal_validation_with_skipped_replay() -> None:
    report = build_sioux_falls_assumption_profile_run_report(
        max_pairs=None,
        max_total_quantity_packets=24,
        tick_limit=600,
        replay_policy=SiouxFallsReplayPolicy(
            exact_replay_packet_limit=6,
            determinism_certified_packet_count=24,
        ),
    )

    assert report.internal_validation_status == "passed"
    assert report.validation_status == "passed"
    assert not report.deterministic_replay_passed
    assert report.replay_status == REPLAY_SKIPPED_AFTER_CERTIFICATION
    assert report.failed_validation_categories == ()


def test_scale_ladder_reports_policy_skipped_replay_without_blocking_scale() -> None:
    report = build_sioux_falls_assumption_profile_scale_ladder_report(
        bounded_packet_rungs=(6, 24),
        tick_limit=600,
        include_full_demand_run=False,
        replay_policy=SiouxFallsReplayPolicy(
            exact_replay_packet_limit=6,
            determinism_certified_packet_count=24,
        ),
    )

    first, second = report.rung_reports
    assert first.replay_status == REPLAY_PASSED_EXACT
    assert first.scale_status == SCALE_PASSED
    assert second.internal_validation_status == "passed"
    assert second.replay_status == REPLAY_SKIPPED_AFTER_CERTIFICATION
    assert second.scale_status == SCALE_PASSED
    assert second.failure_reason is None


def test_scale_ladder_classifies_replay_mismatch(monkeypatch) -> None:
    original = build_sioux_falls_assumption_profile_run_report

    def mismatch_report(*args, **kwargs):
        report = original(*args, **kwargs)
        return replace(
            report,
            deterministic_replay_passed=False,
            replay_status=REPLAY_FAILED_MISMATCH,
            validation_status="failed",
            failures=("deterministic_replay:mismatch",),
        )

    monkeypatch.setattr(
        "urban_cybernetics.canonical_validation.sioux_falls_readiness."
        "build_sioux_falls_assumption_profile_run_report",
        mismatch_report,
    )

    report = build_sioux_falls_assumption_profile_scale_ladder_report(
        bounded_packet_rungs=(6,),
        tick_limit=300,
        include_full_demand_run=False,
    )

    rung = report.rung_reports[0]
    assert rung.replay_status == REPLAY_FAILED_MISMATCH
    assert rung.scale_status == SCALE_FAILED_REPLAY_MISMATCH
    assert rung.failure_reason == "deterministic_replay_mismatch"
