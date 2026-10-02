# SPDX-License-Identifier: MPL-2.0
"""Focused checks for the public-history verifier's Git-only translation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "public_loading_kernel_verifier",
    ROOT / "scripts/verify_public_loading_kernel_freeze.py",
)
assert SPEC is not None and SPEC.loader is not None
public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public)


def test_real_frozen_commits_resolve_without_mutating_manifest() -> None:
    manifest = public.frozen.load_manifest()
    original_bytes = json.dumps(manifest, sort_keys=True)
    mapping = public.load_commit_map()

    resolutions = public.verify_commits(manifest)

    assert set(resolutions) == set(public.COMMIT_FIELDS)
    for field, pair in resolutions.items():
        original = manifest["git"][field]
        assert pair == {"original_sha": original, "public_sha": mapping[original]}
        assert pair["original_sha"] != pair["public_sha"]
    assert json.dumps(manifest, sort_keys=True) == original_bytes


def test_report_keeps_original_ids_and_other_hashes(monkeypatch) -> None:
    manifest = public.frozen.load_manifest()
    original_report = {
        "kernel_evidence_commit": manifest["git"]["kernel_evidence_commit"],
        "artifact_sha256": manifest["artifacts"]["kernel_source_files"][0]["sha256"],
    }
    checker = public.frozen.verify_commits

    def run_original(*args, **kwargs):
        public.frozen.verify_commits(manifest)
        return original_report

    monkeypatch.setattr(public, "_ORIGINAL_VERIFY", run_original)
    report = public.verify(run_regeneration=False, run_tests=False)

    assert {key: report[key] for key in original_report} == original_report
    assert report["commit_resolution"]["kernel_evidence_commit"]["original_sha"] == (
        report["kernel_evidence_commit"]
    )
    assert public.frozen.verify_commits is checker


@pytest.mark.parametrize("contents", [
    "old\tnew\n",
    "original_sha\tpublic_sha\nshort\tshort\n",
    "original_sha\tpublic_sha\n" + ("a" * 40 + "\t" + "b" * 40 + "\n") * 2,
    "original_sha\tpublic_sha\n" + "a" * 40 + "\t" + "b" * 40 + "\textra\n",
])
def test_malformed_or_duplicate_map_is_rejected(tmp_path, contents) -> None:
    path = tmp_path / "map.tsv"
    path.write_text(contents)

    with pytest.raises(ValueError):
        public.load_commit_map(path)


def test_missing_mapping_is_an_error(tmp_path) -> None:
    path = tmp_path / "map.tsv"
    path.write_text("original_sha\tpublic_sha\n")

    with pytest.raises(ValueError, match="no public commit mapping"):
        public.verify_commits(public.frozen.load_manifest(), path)


def test_missing_map_file_is_an_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        public.verify_commits(public.frozen.load_manifest(), tmp_path / "absent.tsv")


def test_nonexistent_mapped_commit_is_rejected(tmp_path) -> None:
    manifest = public.frozen.load_manifest()
    mapping = public.load_commit_map()
    original = manifest["git"]["semantic_change_commit"]
    mapping[original] = "0" * 40
    path = tmp_path / "map.tsv"
    path.write_text("original_sha\tpublic_sha\n" + "".join(
        f"{old}\t{new}\n" for old, new in mapping.items()
    ))

    with pytest.raises(subprocess.CalledProcessError):
        public.verify_commits(manifest, path)


def test_full_verification_still_rejects_missing_frozen_inputs() -> None:
    checker = public.frozen.verify_commits

    with pytest.raises(AssertionError, match="missing frozen artifact:.*digitised"):
        public.verify(run_regeneration=False, run_tests=False)

    assert public.frozen.verify_commits is checker
