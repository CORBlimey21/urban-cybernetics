#!/usr/bin/env python3
"""Verify the versioned Urban Cybernetics loading-kernel freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/validation/loading_kernel_freeze_manifest_v1.json"
LOCAL_PATH_PATTERN = re.compile(
    b"(?:/" + b"Users/[^/\\s]+|/" + b"home/[^/\\s]+|"
    + b"file" + b"://|[A-Za-z]:\\\\Users\\\\)"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if path.read_text(encoding="utf-8") != canonical:
        raise AssertionError("freeze manifest is not deterministically serialized")
    return data


def recorded_files(manifest: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for category in manifest["artifacts"].values():
        entries.extend(category)
    return entries


def verify_recorded_files(manifest: dict[str, Any]) -> int:
    entries = recorded_files(manifest)
    seen: set[str] = set()
    for entry in entries:
        relative = entry["path"]
        if relative in seen:
            raise AssertionError(f"duplicate manifest path: {relative}")
        seen.add(relative)
        path = ROOT / relative
        if not path.is_file():
            raise AssertionError(f"missing frozen artifact: {relative}")
        actual = sha256(path)
        if actual != entry["sha256"]:
            raise AssertionError(
                f"hash mismatch for {relative}: expected {entry['sha256']}, got {actual}"
            )
    return len(entries)


def verify_json_and_evidence(manifest: dict[str, Any]) -> int:
    parsed: dict[str, Any] = {}
    for relative in manifest["comparison_summary_files"]:
        parsed[relative] = json.loads((ROOT / relative).read_text(encoding="utf-8"))

    figure7 = parsed["data/validation/desouza_figure7_comparison_manifest_v1.json"]
    figure7_cases = {run["case_id"] for run in figure7["runs"]}
    if "M8-PUB-DSOUZA-FIG7-DT1" not in figure7_cases:
        raise AssertionError("Figure 7 DT1 evidence case is absent")
    if not all(
        run["internal_checks"]["deterministic_replay_exact"] == "passed"
        for run in figure7["runs"]
    ):
        raise AssertionError("Figure 7 deterministic replay gate failed")

    figure8 = parsed["data/validation/desouza_figure8_ensemble_summary_v1.json"]
    if figure8["case_id"] != "M8-PUB-DSOUZA-FIG8-DT1":
        raise AssertionError("Figure 8 evidence label is absent")
    if figure8["replication_count"] != 100:
        raise AssertionError("Figure 8 frozen replication count changed")
    if not figure8["validation_gates"]["all_replications_pass"]:
        raise AssertionError("Figure 8 ensemble validation gate failed")
    if figure8["validation_gates"]["replay_pass_count"] != 100:
        raise AssertionError("Figure 8 replay count changed")

    for relative, case_id in (
        (
            "data/validation/desouza_figure9a_equal_comparison_summary_v1.json",
            "M8-PUB-DSOUZA-FIG9-EQUAL-DT1",
        ),
        (
            "data/validation/desouza_figure9d_asymmetric_comparison_summary_v1.json",
            "M8-PUB-DSOUZA-FIG9-ASYMMETRIC-DT1",
        ),
    ):
        summary = parsed[relative]
        if summary["case_id"] != case_id:
            raise AssertionError(f"missing expected case label {case_id}")
        if not all(summary["uc_validation_gates"].values()):
            raise AssertionError(f"failed exact validation gate in {relative}")

    labels = {item["label"] for item in manifest["external_evidence"]}
    expected = {
        "de_souza_figure5_lane_drop",
        "de_souza_figure7_deterministic_diverge",
        "de_souza_figure8_stochastic_diverge_ensemble",
        "de_souza_figure9_equal_priority_merge",
        "de_souza_figure9_asymmetric_priority_merge",
    }
    if labels != expected:
        raise AssertionError(f"external evidence labels differ: {sorted(labels)}")
    return len(parsed)


def verify_no_local_paths(manifest_path: Path, manifest: dict[str, Any]) -> int:
    paths = [manifest_path, *(ROOT / item["path"] for item in recorded_files(manifest))]
    scanned = 0
    for path in paths:
        data = path.read_bytes()
        if b"\x00" in data:
            continue
        scanned += 1
        match = LOCAL_PATH_PATTERN.search(data)
        if match:
            raise AssertionError(
                f"absolute local path in {path.relative_to(ROOT)}: "
                f"{match.group(0).decode('utf-8', errors='replace')}"
            )
    return scanned


def verify_commits(manifest: dict[str, Any]) -> None:
    for key in (
        "semantic_change_commit",
        "kernel_evidence_commit",
        "documentation_boundary_commit",
    ):
        commit = manifest["git"][key]
        subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )


def run_commands(commands: list[dict[str, Any]], *, label: str) -> int:
    for command in commands:
        argv = [sys.executable if item == "{python}" else item for item in command["argv"]]
        subprocess.run(
            argv,
            cwd=ROOT,
            check=True,
            stdout=(subprocess.DEVNULL if label == "regeneration" else None),
        )
    return len(commands)


def verify(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    run_regeneration: bool,
    run_tests: bool,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    verify_commits(manifest)
    file_count = verify_recorded_files(manifest)
    summary_count = verify_json_and_evidence(manifest)
    scanned_count = verify_no_local_paths(manifest_path, manifest)
    regeneration_count = 0
    if run_regeneration:
        regeneration_count = run_commands(
            manifest["regeneration_commands"], label="regeneration"
        )
        verify_recorded_files(manifest)
    test_command_count = 0
    if run_tests:
        test_command_count = run_commands(
            manifest["test_commands"]["focused_freeze"], label="focused tests"
        )
    return {
        "freeze_version": manifest["freeze_version"],
        "status": "passed",
        "recorded_file_count": file_count,
        "parsed_summary_count": summary_count,
        "text_artifact_scan_count": scanned_count,
        "regeneration_command_count": regeneration_count,
        "focused_test_command_count": test_command_count,
        "kernel_evidence_commit": manifest["git"]["kernel_evidence_commit"],
        "documentation_boundary_commit": manifest["git"][
            "documentation_boundary_commit"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="verify hashes, JSON, labels, replay gates, commits, and paths only",
    )
    parser.add_argument("--skip-regeneration", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    report = verify(
        args.manifest.resolve(),
        run_regeneration=not (args.metadata_only or args.skip_regeneration),
        run_tests=not (args.metadata_only or args.skip_tests),
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
