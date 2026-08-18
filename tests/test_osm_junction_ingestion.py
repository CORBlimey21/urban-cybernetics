"""Pinned real-OSM ingestion and Boreenmanna junction audit tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree

import pytest

from urban_cybernetics.compiler import (
    BOREENMANNA_CORE_WAY_IDS,
    CompilationDisposition,
    CompilationNotExecutableError,
    CorkJunctionEvidencePackage,
    CorkJunctionPackageIntegrityError,
    OSMFileEvidence,
    OSMXMLValidationError,
    ProvenanceClass,
    boreenmanna_extraction_config,
    compile_boreenmanna_milestone,
    extract_operational_junction,
    extraction_to_source_evidence,
    parse_osm_xml,
    reviewed_candidate_config,
    source_strict_config,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "osm"
    / "boreenmanna_south_link_compact.osm"
)
COMPACT_SHA256 = "9eb6a0c8408ebe5e84a33458103867e64fbb4965b3cc1a899a4dee76ee362e64"


@pytest.fixture(scope="module")
def source():
    return parse_osm_xml(FIXTURE)


@pytest.fixture(scope="module")
def extraction(source):
    return extract_operational_junction(source, boreenmanna_extraction_config())


@pytest.fixture(scope="module")
def milestone():
    return compile_boreenmanna_milestone(FIXTURE)


def test_osm_xml_parser_preserves_pinned_identity_inventory_and_metadata(source) -> None:
    assert source.source_filename == "boreenmanna_south_link_compact.osm"
    assert source.source_format == "application/xml; profile=osm-0.6"
    assert source.file_sha256 == COMPACT_SHA256
    assert source.byte_length == 25_357
    assert (len(source.nodes), len(source.ways), len(source.relations)) == (83, 10, 1)
    assert dict(source.root_attributes)["version"] == "0.6"
    assert "openstreetmap-cgimap 2.1.0" in dict(source.root_attributes)["generator"]
    assert source.bounds[0].to_dict() == {
        "min_latitude": 51.891044,
        "min_longitude": -8.463453,
        "max_latitude": 51.893,
        "max_longitude": -8.459065,
    }
    assert source.timestamp_min == "2011-04-03T20:57:43Z"
    assert source.timestamp_max == "2026-07-31T08:33:10Z"
    assert len(source.parsed_content_hash) == 64
    assert len(source.file_evidence_hash) == 64


def test_osm_records_keep_stable_ids_tags_coordinates_and_relation_members(source) -> None:
    signal = source.node_by_id["367554868"]
    assert signal.stable_id == "osm:node:367554868"
    assert signal.latitude == pytest.approx(51.8920403)
    assert dict(signal.tags) == {
        "highway": "traffic_signals",
        "traffic_signals": "signal",
        "traffic_signals:direction": "forward",
    }
    way = source.way_by_id["279054333"]
    assert way.stable_id == "osm:way:279054333"
    assert way.node_refs[0] == "367558805"
    assert way.node_refs[-1] == "322508225"
    assert dict(way.tags)["lanes"] == "2"
    relation = source.relations[0]
    assert relation.stable_id == "osm:relation:17071174"
    assert {(item.member_type, item.role) for item in relation.members} == {
        ("way", "from"),
        ("node", "via"),
        ("way", "to"),
    }


def test_parser_rejects_malformed_way_node_references(tmp_path: Path) -> None:
    malformed = tmp_path / "missing-node.osm"
    malformed.write_text(
        """<?xml version="1.0"?><osm version="0.6" generator="test"><node id="1" lat="51" lon="-8"/><way id="9"><nd ref="1"/><nd ref="2"/><tag k="highway" v="secondary"/></way></osm>""",
        encoding="utf-8",
    )
    with pytest.raises(OSMXMLValidationError, match="missing node references"):
        parse_osm_xml(malformed)


def test_parsed_content_identity_is_independent_of_top_level_record_order(
    source, tmp_path: Path
) -> None:
    root = ElementTree.parse(FIXTURE).getroot()
    children = list(root)
    root[:] = list(reversed(children))
    reordered = tmp_path / "reordered.osm"
    ElementTree.ElementTree(root).write(
        reordered, encoding="UTF-8", xml_declaration=True
    )
    parsed = parse_osm_xml(reordered)
    assert parsed.file_sha256 != source.file_sha256
    assert parsed.parsed_content_hash == source.parsed_content_hash


def test_operational_boundary_is_explicit_and_classifies_every_source_record(
    source, extraction
) -> None:
    assert set(extraction.retained_way_ids) == set(BOREENMANNA_CORE_WAY_IDS)
    assert len(extraction.retained_node_ids) == 83
    assert len(extraction.decisions) == len(source.nodes) + len(source.ways) + len(
        source.relations
    )
    way_decisions = {
        item.osm_id: item for item in extraction.decisions if item.entity_type == "way"
    }
    assert all(
        way_decisions[item].classification == "retained_executable_road_evidence"
        for item in BOREENMANNA_CORE_WAY_IDS
    )
    assert extraction.extraction_config_hash == boreenmanna_extraction_config().config_hash


def test_way_splitting_uses_endpoints_shared_nodes_and_signal_control_points(
    extraction,
) -> None:
    assert len(extraction.segments) == 22
    southbound = [
        item for item in extraction.segments if item.source_way_id == "279050194"
    ]
    assert len(southbound) == 5
    assert any(item.tail_node_id == "10218634802" for item in southbound)
    assert all(item.distance_formula_id == "uc.geometry.haversine-polyline" for item in southbound)
    assert all(item.geometry_simplification.startswith("none") for item in southbound)
    assert all(item.length_metres > 0 for item in extraction.segments)
    assert all(len(item.geometry_derivation_hash) == 64 for item in extraction.segments)


def test_segment_identities_and_hashes_are_order_independent(source, extraction) -> None:
    reordered_source = OSMFileEvidence(
        source_filename=source.source_filename,
        byte_length=source.byte_length,
        file_sha256=source.file_sha256,
        root_attributes=source.root_attributes,
        bounds=source.bounds,
        nodes=tuple(reversed(source.nodes)),
        ways=tuple(reversed(source.ways)),
        relations=tuple(reversed(source.relations)),
        timestamp_min=source.timestamp_min,
        timestamp_max=source.timestamp_max,
    )
    reordered = extract_operational_junction(
        reordered_source, boreenmanna_extraction_config()
    )
    assert [item.to_dict() for item in extraction.segments] == [
        item.to_dict() for item in reordered.segments
    ]
    assert extraction.extraction_hash == reordered.extraction_hash


def test_source_to_segment_traceability_and_directionality(source, extraction) -> None:
    compiler_source, _ = extraction_to_source_evidence(source, extraction)
    links = [item for item in compiler_source.records if item.record_type == "link"]
    assert len(links) == len(extraction.segments)
    forward = next(
        item
        for item in extraction.segments
        if item.source_way_id == "1242275936" and item.direction == "forward"
    )
    reverse = next(
        item
        for item in extraction.segments
        if item.source_way_id == "1242275936" and item.direction == "reverse"
    )
    assert forward.tail_node_id == reverse.head_node_id
    assert forward.head_node_id == reverse.tail_node_id
    record = next(item for item in links if item.source_id == forward.segment_id)
    fields = {item.name: item.raw_value for item in record.fields}
    assert fields["source_way_id"] == "1242275936"
    assert fields["source_segment_hash"] == forward.segment_hash
    assert fields["source_node_refs"] == list(forward.source_node_refs)


def test_lane_speed_access_and_connector_tags_are_preserved(source, extraction) -> None:
    lane_by_way = {item["source_way_id"]: item for item in extraction.lane_evidence}
    assert lane_by_way["279054333"]["lanes"] == "2"
    assert lane_by_way["32670070"]["lanes"] is None
    assert all(item["turn_lanes"] is None for item in extraction.lane_evidence)
    connector_tags = dict(source.way_by_id["96385702"].tags)
    assert {
        key: connector_tags[key]
        for key in ("highway", "oneway", "lanes", "maxspeed", "foot")
    } == {
        "highway": "trunk_link",
        "oneway": "yes",
        "lanes": "1",
        "maxspeed": "60",
        "foot": "no",
    }


def test_incomplete_turn_restriction_is_retained_without_invented_semantics(
    extraction,
) -> None:
    assert len(extraction.restrictions) == 1
    finding = extraction.restrictions[0]
    assert finding.relation_id == "17071174"
    assert finding.restriction == "no_right_turn"
    assert finding.touches_operational_evidence
    assert finding.status == "incomplete_export_member_references"
    assert finding.missing_member_refs == (
        ("way", "1242275930"),
        ("way", "477599183"),
    )
    assert any(
        item.code == "UC.OSM.RESTRICTION.INCOMPLETE_EXPORT"
        for item in extraction.diagnostics
    )


def test_signal_and_crossing_evidence_is_retained_without_timing(extraction) -> None:
    assert extraction.signal_node_ids == (
        "367554868",
        "1116982191",
        "10218634801",
        "10218634802",
        "10218634803",
        "13900917292",
    )
    assert extraction.crossing_node_ids == ("367552448", "13900917293")
    assert any(
        item.code == "UC.OSM.SIGNAL.TIMING_ABSENT"
        for item in extraction.diagnostics
    )
    assert len(extraction.signal_evidence) == 8
    assert all(item["phase_timing"] is None for item in extraction.signal_evidence)


def test_fifo_representation_assessment_does_not_invent_lane_connectivity(
    extraction,
) -> None:
    assessment = {
        item["representation"]: item for item in extraction.representation_assessment
    }
    assert assessment["shared_link_strict_fifo"]["status"] == (
        "conditionally_supportable_after_physical_review"
    )
    assert assessment["movement_partial_fifo"]["status"] == "not_source_supported"
    assert assessment["explicit_lane_group_queues"]["status"] == (
        "not_source_supported"
    )


def test_source_strict_pass_disables_all_physical_and_representation_defaults(
    milestone,
) -> None:
    config = source_strict_config()
    assert not config.allow_road_class_defaults
    assert not config.allow_jam_density_default
    assert not config.allow_backward_wave_speed_default
    assert not config.allow_conservative_shared_lane_fallback
    assert not config.allow_default_signal_plans
    result = milestone.source_strict_result
    assert result.disposition == CompilationDisposition.UNRESOLVED
    assert not result.is_executable
    assert result.evidence_bundle.canonical_topology_artifact_hash is None
    assert result.evidence_bundle.executable_semantic_hash is None
    assert {item.code for item in result.diagnostics} == {
        "UC.MOVEMENT.UTURN_REVIEW_REQUIRED",
        "UC.SEMANTIC.UNRESOLVED_MANDATORY",
    }
    assert len(result.evidence_bundle.unresolved_items) == 69


def test_strict_audit_distinguishes_observed_inferred_and_missing_link_fields(
    milestone,
) -> None:
    result = milestone.source_strict_result
    lengths = [item for item in result.provenance if item.field_path == "length_m"]
    speeds = [
        item for item in result.provenance if item.field_path == "free_flow_speed_mps"
    ]
    capacities = [
        item
        for item in result.provenance
        if item.field_path == "capacity_veh_per_hour_per_lane"
    ]
    assert lengths and all(item.classification == ProvenanceClass.INFERRED for item in lengths)
    assert speeds and all(item.classification == ProvenanceClass.OBSERVED for item in speeds)
    assert capacities and all(
        item.classification == ProvenanceClass.UNRESOLVED for item in capacities
    )
    assert not result.derivations


def test_reviewed_candidate_builds_valid_road_topology_but_refuses_signal_plan(
    milestone,
) -> None:
    result = milestone.reviewed_candidate_result
    assert result.disposition == CompilationDisposition.UNRESOLVED
    assert not result.is_executable
    assert result.evidence_bundle.canonical_topology_artifact_hash == (
        "7e7d925c9028b6d78350fc31a9f9f76b07bdc2ae59fc879c5f4228874ccb8c14"
    )
    assert result.evidence_bundle.executable_semantic_hash is None
    assert {item.code for item in result.diagnostics} >= {
        "UC.SIGNAL.OSM_EVIDENCE_UNRESOLVED",
        "UC.SIGNAL.PLAN_REFUSED",
    }
    assert result.evidence_bundle.unresolved_items == tuple(
        sorted(
            f"signal-observation:{node_id}:{field}"
            for node_id in milestone.package.extraction.signal_node_ids
            for field in (
                "controller_ownership",
                "fixed_time_plan",
                "movement_assignment",
            )
        )
    )


def test_reviewed_candidate_defaults_and_uturn_overrides_are_explicit(milestone) -> None:
    config = reviewed_candidate_config()
    assert dict(config.capacity_per_lane_defaults)["trunk"] == 1800.0
    assert dict(config.capacity_per_lane_defaults)["secondary"] == 1500.0
    assert config.jam_density_veh_per_km_per_lane_default == 150.0
    assert config.backward_wave_speed_mps_default == 5.0
    assert len(milestone.package.reviewed_overrides) == 2
    assert all(item.replacement_value is False for item in milestone.package.reviewed_overrides)
    override_ids = {item.override_id for item in milestone.package.reviewed_overrides}
    assert override_ids <= {
        item.override_id
        for item in milestone.reviewed_candidate_result.provenance
        if item.classification == ProvenanceClass.OVERRIDDEN
    }
    assert not any(
        item.code == "UC.MOVEMENT.UTURN_REVIEW_REQUIRED"
        for item in milestone.reviewed_candidate_result.diagnostics
    )


def test_reviewed_physical_derivations_retain_geometry_and_discretisation(milestone) -> None:
    result = milestone.reviewed_candidate_result
    lengths = [item for item in result.derivations if item.target_field == "length_m"]
    capacities = [
        item
        for item in result.derivations
        if item.target_field == "declared_sending_capacity_per_tick"
    ]
    storage = [
        item
        for item in result.derivations
        if item.target_field == "declared_storage_capacity_packets"
    ]
    assert len(lengths) == len(result.resolved_graph.links)
    assert all(item.formula_id == "uc.geometry.haversine-polyline" for item in lengths)
    assert all(item.source_unit == "wgs84_coordinate_polyline" for item in lengths)
    assert all(item.rounding_policy == "floor_then_minimum_one" for item in capacities)
    assert all(item.absolute_discretization_error is not None for item in capacities)
    assert all(item.absolute_discretization_error is not None for item in storage)
    assert any(item.clamp_activated for item in capacities)


def test_strict_and_reviewed_compilation_identities_are_separate(milestone) -> None:
    strict = milestone.source_strict_result.evidence_bundle
    reviewed = milestone.reviewed_candidate_result.evidence_bundle
    assert strict.input_evidence_hash == reviewed.input_evidence_hash
    assert strict.normalized_evidence_hash == reviewed.normalized_evidence_hash
    assert strict.compiler_configuration_hash != reviewed.compiler_configuration_hash
    assert strict.compilation_identity_hash != reviewed.compilation_identity_hash
    assert strict.evidence_bundle_hash != reviewed.evidence_bundle_hash
    assert strict.executable_semantic_hash is None
    assert reviewed.executable_semantic_hash is None


def test_junction_package_round_trip_and_nested_tamper_detection(milestone) -> None:
    package = milestone.package
    assert CorkJunctionEvidencePackage.from_json(package.to_json()) == package

    source_tamper = deepcopy(package.to_dict())
    source_tamper["source"]["nodes"][0]["latitude"] = 0.0
    with pytest.raises(OSMXMLValidationError, match="parsed_content_hash"):
        CorkJunctionEvidencePackage.from_dict(source_tamper)

    segment_tamper = deepcopy(package.to_dict())
    segment_tamper["extraction"]["segments"][0]["length_metres"] = 999.0
    with pytest.raises(OSMXMLValidationError, match="geometry derivation hash"):
        CorkJunctionEvidencePackage.from_dict(segment_tamper)

    package_tamper = deepcopy(package.to_dict())
    package_tamper["reviewed_assumptions"][0]["reason"] = "tampered"
    with pytest.raises(OSMXMLValidationError, match="reviewed assumption hash mismatch"):
        CorkJunctionEvidencePackage.from_dict(package_tamper)

    for assumption in package.reviewed_assumptions:
        assert assumption.assumption_id
        assert assumption.actor == "milestone-reviewed-policy"
        assert assumption.source
        assert assumption.reason
        assert assumption.assumption_hash


def test_guarded_executable_access_refuses_both_milestone_passes(milestone) -> None:
    for result in (
        milestone.source_strict_result,
        milestone.reviewed_candidate_result,
    ):
        with pytest.raises(CompilationNotExecutableError):
            result.require_executable()


def test_extraction_configuration_changes_are_hash_visible(source) -> None:
    baseline = boreenmanna_extraction_config()
    changed = replace(baseline, minimum_approach_length_metres=75.0)
    assert baseline.config_hash != changed.config_hash
    assert (
        extract_operational_junction(source, baseline).extraction_hash
        != extract_operational_junction(source, changed).extraction_hash
    )
