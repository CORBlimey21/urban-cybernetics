"""Regression boundary for the versioned loading-kernel freeze manifest."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/validation/loading_kernel_freeze_manifest_v1.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_freeze_manifest_is_canonical_and_pins_the_reviewed_boundary() -> None:
    manifest = _manifest()

    assert MANIFEST.read_text(encoding="utf-8") == (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    assert manifest["freeze_version"] == "loading-kernel-v1.0.1"
    assert manifest["kernel_profile"] == "parity_ltm_v1"
    assert manifest["git"]["kernel_evidence_commit"] == (
        "6fb834c7ace57421e0816f2894cc5f53e1f898c0"
    )
    assert manifest["git"]["documentation_boundary_commit"] == (
        "08d9668ce4e0cc2939fbf4e9e1c2f75bc6285964"
    )
    assert manifest["git"]["hardening_commit"] == (
        "1fd8884c69c82e6d53ed1b4801a9d1672f38e6ef"
    )


def test_freeze_manifest_pins_all_required_external_evidence_labels() -> None:
    manifest = _manifest()
    labels = {item["label"] for item in manifest["external_evidence"]}

    assert labels == {
        "de_souza_figure5_lane_drop",
        "de_souza_figure7_deterministic_diverge",
        "de_souza_figure8_stochastic_diverge_ensemble",
        "de_souza_figure9_equal_priority_merge",
        "de_souza_figure9_asymmetric_priority_merge",
    }
    asymmetric = next(
        item for item in manifest["external_evidence"]
        if item["label"] == "de_souza_figure9_asymmetric_priority_merge"
    )
    assert asymmetric["priority_interpretation"] == {
        "alpha_1": 0.75,
        "sequence": [0, 0, 0, 1],
    }


def test_freeze_manifest_covers_semantic_sources_and_exact_regression_commands() -> None:
    manifest = _manifest()
    source_paths = {
        item["path"] for item in manifest["artifacts"]["kernel_source_files"]
    }

    assert {
        "src/urban_cybernetics/core/event.py",
        "src/urban_cybernetics/loading/cumulative_counts.py",
        "src/urban_cybernetics/loading/engine.py",
        "src/urban_cybernetics/loading/receiving.py",
        "src/urban_cybernetics/loading/sending.py",
        "src/urban_cybernetics/loading/transfer_policy.py",
    }.issubset(source_paths)
    focused = manifest["test_commands"]["focused_freeze"]
    assert len(focused) == 1
    argv = focused[0]["argv"]
    assert "tests/test_ltm_parity_node_family.py" in argv
    assert "tests/test_kernel_hardening.py" in argv
    assert "tests/external_validation/test_m8_desouza_figure9_asymmetric.py" in argv


def test_metadata_verifier_checks_hashes_labels_replay_and_local_paths() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/verify_loading_kernel_freeze.py", "--metadata-only"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["status"] == "passed"
    assert report["recorded_file_count"] >= 40
    assert report["parsed_summary_count"] == 4
    assert report["text_artifact_scan_count"] >= 40
    assert report["regeneration_command_count"] == 0
    assert report["focused_test_command_count"] == 0
