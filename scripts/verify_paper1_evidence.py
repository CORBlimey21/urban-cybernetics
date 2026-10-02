#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Verify Paper 1 tracked, retained-output, and pinned-source identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "docs/paper1/evidence_manifest_v1.json"


def _identity(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size


def _check_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    results = []
    for entry in entries:
        path = PROJECT_ROOT / str(entry["path"])
        if not path.is_file():
            raise SystemExit(f"missing evidence artifact: {path}")
        actual_hash, actual_size = _identity(path)
        if actual_hash != entry["sha256"]:
            raise SystemExit(f"SHA-256 mismatch: {path}: {actual_hash}")
        expected_size = entry.get("size_bytes")
        if expected_size is not None and actual_size != expected_size:
            raise SystemExit(f"size mismatch: {path}: {actual_size}")
        results.append(
            {"path": str(path.relative_to(PROJECT_ROOT)), "status": "passed"}
        )
    return results


def _check_cork_source(manifest: dict[str, object], explicit: Path | None) -> dict[str, object]:
    sources = manifest["external_pinned_sources"]
    assert isinstance(sources, list)
    entry = next(item for item in sources if item["role"] == "cork_full_drive_graphml")
    configured = explicit or (
        Path(os.environ["UC_CORK_GRAPHML"])
        if os.environ.get("UC_CORK_GRAPHML")
        else None
    )
    if configured is None:
        return {"role": entry["role"], "status": "not_requested"}
    actual_hash, actual_size = _identity(configured.expanduser())
    if actual_hash != entry["sha256"] or actual_size != entry["size_bytes"]:
        raise SystemExit(
            f"Cork GraphML identity mismatch: sha256={actual_hash} bytes={actual_size}"
        )
    return {"role": entry["role"], "status": "passed", "path": str(configured)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--include-ignored", action="store_true")
    parser.add_argument("--cork-graphml", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    tracked = _check_entries(manifest["tracked_artifacts"])
    ignored = (
        _check_entries(manifest["ignored_generated_outputs"])
        if args.include_ignored
        else []
    )
    result = {
        "schema_version": "uc.paper1-evidence-verification.v1",
        "status": "passed",
        "tracked_artifact_count": len(tracked),
        "ignored_artifact_count": len(ignored),
        "ignored_outputs_checked": args.include_ignored,
        "external_cork_source": _check_cork_source(
            manifest, args.cork_graphml
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
