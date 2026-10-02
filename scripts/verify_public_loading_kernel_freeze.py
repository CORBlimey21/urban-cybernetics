#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Resolve public-history commits without changing the checksum-pinned verifier."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any


_SPEC = importlib.util.spec_from_file_location(
    "frozen_loading_kernel_verifier",
    Path(__file__).with_name("verify_loading_kernel_freeze.py"),
)
assert _SPEC is not None and _SPEC.loader is not None
frozen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(frozen)
_ORIGINAL_VERIFY = frozen.verify
_ORIGINAL_VERIFY_COMMITS = frozen.verify_commits
DEFAULT_COMMIT_MAP = frozen.ROOT / "docs/provenance/public-commit-map.tsv"
COMMIT_FIELDS = (
    "semantic_change_commit",
    "kernel_evidence_commit",
    "documentation_boundary_commit",
    "hardening_commit",
)


def load_commit_map(path: Path = DEFAULT_COMMIT_MAP) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "original_sha\tpublic_sha":
        raise ValueError("commit map must have original_sha/public_sha TSV columns")
    mapping: dict[str, str] = {}
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) != 2 or not all(
            re.fullmatch(r"[0-9a-f]{40}", value) for value in columns
        ):
            raise ValueError("commit map rows must contain two full Git commit IDs")
        original, public = columns
        if original in mapping:
            raise ValueError(f"duplicate original commit ID: {original}")
        mapping[original] = public
    return mapping


def verify_commits(
    manifest: dict[str, Any], commit_map_path: Path = DEFAULT_COMMIT_MAP,
) -> dict[str, dict[str, str]]:
    mapping = load_commit_map(commit_map_path)
    resolutions: dict[str, dict[str, str]] = {}
    mapped_git = dict(manifest["git"])
    for key in COMMIT_FIELDS:
        original = manifest["git"][key]
        if original not in mapping:
            raise ValueError(f"no public commit mapping for {key}: {original}")
        public = mapping[original]
        mapped_git[key] = public
        resolutions[key] = {"original_sha": original, "public_sha": public}
    # Only this temporary Git metadata view is translated; artifact hashes and
    # the manifest object used by all other checks/report fields are unchanged.
    _ORIGINAL_VERIFY_COMMITS({**manifest, "git": mapped_git})
    return resolutions


def verify(*args: Any, **kwargs: Any) -> dict[str, Any]:
    resolutions: dict[str, dict[str, str]] = {}
    original_checker = frozen.verify_commits

    def check_commits(manifest: dict[str, Any]) -> None:
        resolutions.update(verify_commits(manifest))

    frozen.verify_commits = check_commits
    try:
        report = _ORIGINAL_VERIFY(*args, **kwargs)
    finally:
        frozen.verify_commits = original_checker
    return {**report, "commit_resolution": resolutions}


def main() -> None:
    original_verify = frozen.verify
    frozen.verify = verify
    try:
        frozen.main()
    finally:
        frozen.verify = original_verify


if __name__ == "__main__":
    main()
