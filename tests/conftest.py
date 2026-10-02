# SPDX-License-Identifier: MPL-2.0
"""Explicit skips for tests requiring separately acquired third-party inputs."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SIOUX = (
    "data/benchmarks/sioux_falls/SiouxFalls_net.tntp",
    "data/benchmarks/sioux_falls/SiouxFalls_trips.tntp",
)
ANAHEIM = (
    "data/benchmarks/anaheim/Anaheim_net.tntp",
    "data/benchmarks/anaheim/Anaheim_trips.tntp",
)
FIGURE7 = (
    "data/validation/desouza_figure7a_dt1_Gu_digitised_v1.csv",
    "data/validation/desouza_figure7a_dt1_F1_digitised_v1.csv",
    "data/validation/desouza_figure7a_dt1_F2_digitised_v1.csv",
)
FROZEN_REFERENCES = tuple(sorted({
    path
    for evidence in json.loads(
        (ROOT / "data/validation/loading_kernel_freeze_manifest_v1.json").read_text()
    )["external_evidence"]
    for path in evidence.get("reference_files", [])
}))

# A None value means every test in the module uses that external input. Mixed
# modules name only their data-dependent cases, keeping synthetic tests active.
EXTERNAL_CASES: dict[str, tuple[tuple[str, ...], set[str] | None]] = {
    "tests/canonical_validation/test_anaheim_benchmark.py": (ANAHEIM, None),
    "tests/canonical_validation/test_sioux_falls_readiness.py": (SIOUX, None),
    "tests/parity_torture/test_sioux_falls_regression.py": (SIOUX, None),
    "tests/test_sioux_falls_benchmark_loading.py": (SIOUX, None),
    "tests/external_validation/test_m8_desouza_figure7_comparison.py": (FIGURE7, None),
    "tests/canonical_validation/test_sioux_falls_physical_profile.py": (
        SIOUX,
        {
            "test_uc_default_profile_generation_is_deterministic",
            "test_uc_default_profile_records_provenance_and_derivations",
            "test_uc_default_profile_retains_topology_hash_without_mutating_topology",
            "test_uc_default_profile_loading_links_are_triangular_fd_consistent",
            "test_uc_default_profile_summary_is_reproducible",
            "test_full_topology_assumption_profile_run_reports_validation_status",
            "test_fuller_assumption_profile_run_passes_fifo_validation",
            "test_assumption_profile_run_reports_requested_and_unresolved_packets",
            "test_assumption_profile_scale_ladder_stops_after_first_failure",
            "test_assumption_profile_scale_ladder_payload_is_json_ready",
            "test_full_demand_timeout_preserves_requested_packet_count",
            "test_assumption_profile_determinism_comparison_matches_small_case",
            "test_replay_policy_allows_internal_validation_with_skipped_replay",
            "test_scale_ladder_reports_policy_skipped_replay_without_blocking_scale",
            "test_scale_ladder_classifies_replay_mismatch",
        },
    ),
    "tests/test_canonical_sioux_falls_topology.py": (
        SIOUX,
        {
            "test_sioux_falls_source_file_exists",
            "test_loader_parses_real_sioux_falls_topology",
            "test_canonical_ids_are_deterministic_and_external_ids_are_provenance",
            "test_directed_connectivity_is_preserved",
            "test_topology_hash_is_deterministic",
            "test_topology_hash_changes_when_static_link_metadata_changes",
            "test_topology_hash_changes_when_interpretation_assumptions_change",
            "test_topology_records_are_immutable",
            "test_topology_records_do_not_expose_dynamic_fields",
            "test_l1_loading_link_mapping_preserves_static_metadata",
        },
    ),
    "tests/test_demand_manifest.py": (
        SIOUX,
        {
            "test_global_uniform_schedule_uses_full_manifest_window",
            "test_global_uniform_schedule_balances_departure_counts",
            "test_declaration_uniform_schedule_remains_per_declaration",
            "test_sioux_falls_od_loader_parses_real_or_fixture_matrix",
            "test_route_resolution_keeps_routes_separate_from_raw_demand",
            "test_scheduled_loading_realises_small_sioux_falls_demand",
            "test_origin_blocked_demand_remains_pending_until_loading_admits_it",
            "test_topology_records_do_not_contain_demand_fields",
            "test_raw_demand_does_not_create_packet_ids",
        },
    ),
    "tests/test_import_baseline.py": (SIOUX, {"test_committed_benchmark_paths_resolve"}),
    "tests/visualisation/test_layouts.py": (
        SIOUX,
        {
            "test_sioux_falls_layouts_are_complete_unique_and_prefer_published_schematic",
            "test_generated_layout_is_deterministic_and_declares_nonphysical_semantics",
        },
    ),
    "tests/validation/test_loading_kernel_freeze_manifest.py": (
        FROZEN_REFERENCES,
        {"test_metadata_verifier_checks_hashes_labels_replay_and_local_paths"},
    ),
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        relative = item.path.relative_to(ROOT).as_posix()
        rule = EXTERNAL_CASES.get(relative)
        if rule is None:
            continue
        paths, names = rule
        if names is not None and item.name not in names:
            continue
        missing = [path for path in paths if not (ROOT / path).is_file()]
        if missing:
            item.add_marker(pytest.mark.skip(
                reason="external third-party input unavailable; see benchmark README or "
                "THIRD_PARTY.md: " + ", ".join(missing)
            ))
