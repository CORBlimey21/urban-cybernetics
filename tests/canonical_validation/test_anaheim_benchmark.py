"""Anaheim TNTP ingestion and UC-default profile tests."""

from __future__ import annotations

from math import floor, isclose

from urban_cybernetics.benchmarks.anaheim import load_anaheim
from urban_cybernetics.canonical_validation.anaheim_physical_profile import (
    ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS,
    ANAHEIM_UC_DEFAULT_PROFILE_ID,
    build_anaheim_uc_default_physical_profile,
)
from urban_cybernetics.canonical_validation.anaheim_readiness import (
    build_anaheim_assumption_profile_run_report,
    build_anaheim_assumption_profile_scale_ladder_report,
    build_anaheim_readiness_report,
)
from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    REPLAY_PASSED_EXACT,
    SiouxFallsReplayPolicy,
)
from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID
from urban_cybernetics.demand.anaheim import load_anaheim_demand_manifest
from urban_cybernetics.topology.anaheim import FEET_TO_METRES, load_anaheim_topology
from urban_cybernetics.validation import assess_physical_parameter_eligibility


def test_anaheim_tntp_parser_loads_network_and_demand_dimensions() -> None:
    benchmark = load_anaheim()

    assert len(benchmark.nodes) == 416
    assert len(benchmark.directed_links) == 914
    assert len(benchmark.od_demand) == 1406
    assert isclose(benchmark.total_od_demand, 104_694.4)
    assert benchmark.directed_links[0].tail == 1
    assert benchmark.directed_links[0].head == 117


def test_anaheim_topology_converts_source_units_without_losing_provenance() -> None:
    topology = load_anaheim_topology()
    first = next(link for link in topology.links if link.source_link_id == "1->117")

    assert topology.topology_id == "anaheim_tntp_v1"
    assert len(topology.nodes) == 416
    assert len(topology.links) == 914
    assert first.source_length_unit == "foot"
    assert first.source_free_flow_time_unit == "minute"
    assert first.source_capacity_unit == "vehicle_per_hour"
    assert first.length_m is not None
    assert isclose(first.length_m, 5280.0 * FEET_TO_METRES)
    assert first.free_flow_speed_mps is not None
    assert isclose(first.free_flow_speed_mps, first.length_m / (1.090458488 * 60.0))


def test_anaheim_demand_manifest_maps_zones_to_canonical_nodes() -> None:
    topology = load_anaheim_topology()
    manifest = load_anaheim_demand_manifest(
        topology=topology,
        max_total_quantity_packets=1_000,
    )

    assert manifest.manifest_id == "anaheim_od_demand_v1"
    assert manifest.total_declared_quantity_packets == 1_000
    assert manifest.declarations[0].origin_node_id == "N001"
    assert manifest.declarations[0].destination_node_id == "N002"
    assert manifest.source_metadata is not None
    assert manifest.source_metadata.source_file_sha256 is not None


def test_anaheim_uc_default_profile_generation_is_deterministic() -> None:
    first = build_anaheim_uc_default_physical_profile()
    second = build_anaheim_uc_default_physical_profile()

    assert first.profile_id == ANAHEIM_UC_DEFAULT_PROFILE_ID
    assert first.profile_hash == second.profile_hash
    assert first.status_payload() == second.status_payload()
    assert len(first.derived_links) == 914


def test_anaheim_uc_default_profile_derives_physical_metadata() -> None:
    topology = load_anaheim_topology()
    profile = build_anaheim_uc_default_physical_profile(topology=topology)
    first = next(link for link in profile.derived_links if link.source_link_id == "1->117")

    expected_storage = floor(
        (first.length_m / 1000.0)
        * first.lane_count
        * first.jam_density_veh_per_km_per_lane
    )
    assert first.backward_wave_speed_mps == ANAHEIM_UC_DEFAULT_BACKWARD_WAVE_SPEED_MPS
    assert first.declared_storage_capacity_packets == max(1, expected_storage)
    assert all(
        link.backward_wave_speed_mps is None
        and link.jam_density_veh_per_km_per_lane is None
        for link in topology.links
    )


def test_anaheim_uc_default_profile_loading_links_are_parity_eligible() -> None:
    profile = build_anaheim_uc_default_physical_profile()
    links = profile.as_loading_links(tick_duration_seconds=2.0)
    report = assess_physical_parameter_eligibility(
        links.values(),
        model_profile_id=ACADEMIC_LTM_PARITY_PROFILE_ID,
    )

    assert report.is_parity_eligible
    assert all(
        link_report.fd_report is not None
        and link_report.fd_report.is_consistent
        for link_report in report.link_reports
    )


def test_small_anaheim_parity_smoke_run_passes_internal_validation() -> None:
    report = build_anaheim_assumption_profile_run_report(
        max_total_quantity_packets=10,
        tick_limit=600,
    )

    assert report.benchmark_id == "anaheim_tntp_v1"
    assert report.requested_model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID
    assert report.physical_profile_id == ANAHEIM_UC_DEFAULT_PROFILE_ID
    assert report.topology_node_count == 416
    assert report.topology_link_count == 914
    assert report.run_completed
    assert report.internal_validation_status == "passed"
    assert report.replay_status == REPLAY_PASSED_EXACT
    assert report.deterministic_replay_passed
    assert report.setup_runtime_seconds > 0
    assert not report.failures


def test_anaheim_readiness_report_structure() -> None:
    report = build_anaheim_readiness_report()
    payload = report.status_payload()

    assert payload["benchmark_id"] == "anaheim_tntp_v1"
    assert payload["topology_load_status"]["status"] == "pass"
    assert payload["demand_load_status"]["status"] == "pass"
    assert payload["physical_metadata_status"]["status"] == "pass"
    assert payload["parity_initialization_status"]["status"] == "pass"
    assert payload["topology_node_count"] == 416
    assert payload["topology_link_count"] == 914
    assert len(payload["source_file_hashes"]) == 3
    assert "engineering_assumption_profile_not_empirical_calibration" in (
        payload["assumption_profile_warnings"]
    )


def test_anaheim_scale_ladder_payload_is_json_ready() -> None:
    report = build_anaheim_assumption_profile_scale_ladder_report(
        bounded_packet_rungs=(10,),
        tick_limit=600,
        include_full_demand_run=False,
        replay_policy=SiouxFallsReplayPolicy(exact_replay_packet_limit=10),
    )
    payload = report.status_payload()

    assert payload["benchmark_id"] == "anaheim_tntp_v1"
    assert payload["bounded_packet_rungs"] == (10,)
    assert payload["rung_reports"][0]["requested_packet_count"] == 10
    assert payload["rung_reports"][0]["internal_validation_status"] == "passed"
    assert payload["rung_reports"][0]["setup_runtime_seconds"] > 0
