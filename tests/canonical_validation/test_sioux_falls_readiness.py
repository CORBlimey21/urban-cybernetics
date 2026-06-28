"""Sioux Falls canonical parity-readiness checks."""

from __future__ import annotations

from urban_cybernetics.canonical_validation.sioux_falls_readiness import (
    build_sioux_falls_parity_readiness_report,
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
    assert gates["parity_profile_full_topology_initialization"].status == "fail"
    assert "multi-input/multi-output nodes require a later node model" in (
        gates["parity_profile_full_topology_initialization"].details[0]
    )
    assert gates["parity_commodity_evidence"].status == "not_run"
    assert gates["parity_spillback_evidence"].status == "not_run"
    assert gates["legacy_profile_readiness_stress_run"].status == "pass"
    assert report.failed_gate_ids == (
        "physical_metadata",
        "parity_profile_full_topology_initialization",
    )
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
        "parity_profile_full_topology_initialization",
    )
    assert payload["not_run_gate_ids"] == (
        "parity_commodity_evidence",
        "parity_spillback_evidence",
    )
