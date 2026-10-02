# SPDX-License-Identifier: MPL-2.0
"""Sioux Falls canonical parity-readiness checks."""

from __future__ import annotations

from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    build_sioux_falls_parity_readiness_report,
    build_sioux_falls_supported_subnetwork_readiness_report,
)
from urban_cybernetics.config import ACADEMIC_LTM_PARITY_PROFILE_ID


def test_sioux_falls_readiness_report_rejects_true_parity_label_for_now() -> None:
    report = build_sioux_falls_parity_readiness_report()

    assert report.requested_model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID
    assert report.evidence_label == "sioux_falls_readiness_stress_only"
    assert not report.can_run_as_parity_ltm_v1
    assert not report.kernel_bug_found
    assert report.topology_node_count == 24
    assert report.topology_link_count == 76
    assert report.od_pair_count == 3
    assert report.scheduled_departure_count > 0
    assert report.instantiated_packet_count > 0
    assert report.event_count > 0


def test_sioux_falls_readiness_report_names_current_failing_gates() -> None:
    report = build_sioux_falls_parity_readiness_report()
    gates = {gate.gate_id: gate for gate in report.gates}

    assert gates["benchmark_loader"].status == "pass"
    assert gates["physical_metadata"].status == "fail"
    assert gates["physical_metadata"].detail_count == 152
    assert "missing_physical_metadata:backward_wave_speed_mps" in (
        gates["physical_metadata"].details[0]
    )
    assert gates["junction_semantics_metadata"].status == "fail"
    assert gates["junction_semantics_metadata"].detail_count > 0
    assert gates["allocator_capability"].status == "pass"
    assert gates["parity_commodity_evidence"].status == "not_run"
    assert "physical or junction metadata" in gates["parity_commodity_evidence"].reason
    assert gates["parity_spillback_evidence"].status == "not_run"
    assert "physical or junction metadata" in gates["parity_spillback_evidence"].reason
    assert gates["legacy_profile_readiness_stress_run"].status == "pass"
    assert report.failed_gate_ids == ("physical_metadata", "junction_semantics_metadata")
    assert report.not_run_gate_ids == (
        "parity_commodity_evidence",
        "parity_spillback_evidence",
    )


def test_sioux_falls_readiness_status_payload_is_json_ready() -> None:
    report = build_sioux_falls_parity_readiness_report()
    payload = report.status_payload()

    assert payload["benchmark_id"] == "sioux_falls_tntp_v1"
    assert payload["failed_gate_ids"] == (
        "physical_metadata",
        "junction_semantics_metadata",
    )
    assert payload["not_run_gate_ids"] == (
        "parity_commodity_evidence",
        "parity_spillback_evidence",
    )


def test_supported_sioux_falls_subnetwork_passes_parity_readiness_gates() -> None:
    report = build_sioux_falls_supported_subnetwork_readiness_report()
    gates = {gate.gate_id: gate for gate in report.gates}

    assert report.requested_model_profile_id == ACADEMIC_LTM_PARITY_PROFILE_ID
    assert report.evidence_label == "sioux_falls_supported_movement_subnetwork_parity_ready"
    assert report.is_ready_for_parity_validation
    assert not report.kernel_bug_found
    assert report.selected_source_nodes == ("1", "2", "3", "4", "5", "6", "8")
    assert report.selected_source_links == (
        "1->2",
        "1->3",
        "2->1",
        "2->6",
        "3->4",
        "4->5",
        "5->6",
        "6->8",
    )
    assert set(report.adapted_supported_node_ids) == {
        "N002",
        "N003",
        "N004",
        "N005",
        "N006",
    }
    assert report.unsupported_advanced_full_network_node_ids == ()
    assert report.instantiated_packet_count == 6
    assert report.completed_packet_count == 6
    assert report.failed_gate_ids == ()
    assert all(gate.status == "pass" for gate in report.gates)
    assert gates["physical_metadata"].status == "pass"
    assert gates["parity_profile_initialization"].status == "pass"
    assert gates["parity_commodity_evidence"].status == "pass"
    assert gates["parity_spillback_evidence"].status == "pass"
    assert gates["packet_conservation"].status == "pass"
    assert gates["deterministic_replay"].status == "pass"


def test_supported_subnetwork_documents_benchmark_assumptions_not_calibration() -> None:
    report = build_sioux_falls_supported_subnetwork_readiness_report()
    assumptions = {
        assumption.field_name: assumption
        for assumption in report.metadata_assumptions
    }

    assert assumptions["backward_wave_speed_mps"].value == "5.0"
    assert (
        assumptions["backward_wave_speed_mps"].provenance_label
        == "benchmark_assumption_not_empirical_calibration"
    )
    assert (
        assumptions["declared_storage_capacity_packets"].provenance_label
        == "benchmark_assumption_not_legacy_storage_override"
    )
