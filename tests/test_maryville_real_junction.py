"""Second pinned real OSM case: Maryville at Blackrock Road."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from urban_cybernetics.compiler import (
    CompilationDisposition,
    MaryvilleJunctionIntegrityError,
    MaryvilleJunctionPackage,
    OSMJunctionExtractionConfig,
    OSMXMLValidationError,
    ProvenanceClass,
    compile_maryville_junction,
    maryville_extraction_config,
    parse_osm_xml,
)
from urban_cybernetics.compiler.osm_xml import (
    boreenmanna_extraction_config,
    extract_operational_junction,
)


FIXTURE = Path(__file__).parent / "fixtures" / "osm" / "maryville_brr_junction.osm"
SOURCE_SHA256 = "c6e23f6b00fbf3abb07eebd97c7afdedf731ac0e50e1fc46bde5b749f659308b"
PARSED_HASH = "da9a43e752d19e9e472abf2c7c31aab73afdd5a6d81a0df78d24e487ff178b27"
BOREENMANNA_CONFIG_HASH = "0cecba801b35f4c6c8ac2e56868c63c911489e5a2949613c9d0e4aeab85f5327"


@pytest.fixture(scope="module")
def run():
    return compile_maryville_junction(FIXTURE)


def test_pinned_real_source_identity_and_inventory() -> None:
    source = parse_osm_xml(FIXTURE)
    assert source.source_filename == "maryville_brr_junction.osm"
    assert source.byte_length == 106_424
    assert source.file_sha256 == SOURCE_SHA256
    assert source.parsed_content_hash == PARSED_HASH
    assert (len(source.nodes), len(source.ways), len(source.relations)) == (387, 31, 3)
    assert source.bounds[0].to_dict() == {
        "min_latitude": 51.895382,
        "min_longitude": -8.434153,
        "max_latitude": 51.895748,
        "max_longitude": -8.433461,
    }


def test_reviewed_way_intervals_retain_only_the_unsignalised_t_junction(run) -> None:
    extraction = run.extraction
    assert extraction.retained_way_ids == ("5317316", "477599192")
    assert len(extraction.retained_node_ids) == 12
    assert len(extraction.segments) == 6
    assert extraction.signal_node_ids == ()
    assert extraction.crossing_node_ids == ()
    assert sorted(round(item.length_metres, 3) for item in extraction.segments) == [
        40.976,
        40.976,
        54.187,
        54.187,
        57.59,
        57.59,
    ]
    excluded_signal_ids = {"13732796971", "8700897883"}
    decisions = {
        item.osm_id: item.classification
        for item in extraction.decisions
        if item.entity_type == "node"
    }
    assert all(decisions[item] == "excluded_outside_operational_boundary" for item in excluded_signal_ids)


def test_interval_configuration_round_trips_without_changing_old_hash_domain() -> None:
    config = maryville_extraction_config()
    assert OSMJunctionExtractionConfig.from_dict(config.to_dict()) == config
    assert config.config_hash == "c3bcf0ee042e2c8a23514c355649eb5d9713265a954f357006b6cb038c8f5f55"
    assert boreenmanna_extraction_config().config_hash == BOREENMANNA_CONFIG_HASH
    assert "explicit_way_node_intervals" not in boreenmanna_extraction_config().to_dict()


def test_invalid_way_interval_is_rejected() -> None:
    source = parse_osm_xml(FIXTURE)
    backwards = replace(
        maryville_extraction_config(),
        explicit_way_node_intervals=(("5317316", "7842268", "10980457806"),),
    )
    with pytest.raises(OSMXMLValidationError, match="source-way order"):
        extract_operational_junction(source, backwards)


def test_source_strict_audit_refuses_only_real_unresolved_model_semantics(run) -> None:
    strict = run.source_strict_result
    assert strict.disposition == CompilationDisposition.UNRESOLVED
    assert not strict.is_executable
    unresolved = strict.evidence_bundle.unresolved_items
    assert any(item.endswith(":capacity_veh_per_hour_per_lane") for item in unresolved)
    assert any(item.endswith(":jam_density_veh_per_km_per_lane") for item in unresolved)
    assert any(item.endswith(":backward_wave_speed_mps") for item in unresolved)
    assert any(item.endswith(":permitted") for item in unresolved)
    assert not any("signal" in item for item in unresolved)
    assert all(item.classification != ProvenanceClass.SYNTHETIC_EXPERIMENT for item in strict.provenance)


def test_reviewed_candidate_uses_observed_geometry_lanes_speed_and_explicit_priors(run) -> None:
    reviewed = run.reviewed_candidate_result
    assert reviewed.disposition == CompilationDisposition.EXECUTABLE_WITH_WARNINGS
    executable = reviewed.require_executable()
    assert executable.executable_semantic_hash == (
        "be77c859070f0096ba526bc38df978d6f207a2dcf2327795d6ba61c2e45a48d7"
    )
    assert len(executable.resolved_links) == 6
    assert all(item.lane_count == 1 for item in executable.resolved_links)
    assert all(item.free_flow_speed_mps == pytest.approx(50.0 / 3.6) for item in executable.resolved_links)
    assert all(item.capacity_veh_per_hour_per_lane == 1500.0 for item in executable.resolved_links)
    assert len(reviewed.evidence_bundle.overrides) == 6
    assert all(
        item.target_field == "permitted"
        for item in reviewed.evidence_bundle.overrides
    )
    assumption_ids = {
        item.assumption_id for item in run.package.audit_package.reviewed_assumptions
    }
    assert assumption_ids == {
        "maryville-review:backward-wave-speed",
        "maryville-review:jam-density",
        "maryville-review:shared-fifo",
        "maryville-review:tertiary-capacity",
        "maryville-review:tick-duration",
    }


def test_smoke_exercises_all_six_legal_t_junction_movements(run) -> None:
    smoke = run.package.to_dict()["smoke_summary"]
    assert smoke["classification"] == "synthetic_demand_on_real_osm_derived_geometry"
    assert smoke["representation"] == "shared_link_fifo"
    assert smoke["demand_count"] == smoke["completed_count"] == 6
    assert len(smoke["permitted_movements"]) == 6
    assert smoke["canonical_event_count"] == 36
    assert smoke["event_log_hash"] == "f23a1d52ba8a8d269f9a8dd89a42a992ff816f9a2ae141267937c625beb3ae96"
    assert smoke["replay_exact"]
    assert smoke["conservation_passed"]
    assert smoke["replay_conservation_passed"]
    assert smoke["event_cache_consistency_passed"]
    assert smoke["count_consistency_passed"]


def test_package_round_trip_determinism_and_tamper_detection(run) -> None:
    serialised = run.package.to_json()
    rebuilt = MaryvilleJunctionPackage.from_json(serialised)
    assert rebuilt.to_json() == serialised
    assert rebuilt.deterministic_hash == (
        "47a59c312b87aaf5675a2777b617731d44374671d04bce5a1482e8054ecb2fb2"
    )
    payload = deepcopy(run.package.to_dict())
    payload["smoke_summary"]["completed_count"] = 5
    with pytest.raises(MaryvilleJunctionIntegrityError, match="hash mismatch"):
        MaryvilleJunctionPackage.from_dict(payload)
