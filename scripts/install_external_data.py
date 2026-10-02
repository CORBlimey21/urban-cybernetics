#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Verify and install user-supplied external data at repository-default paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORK_DESTINATION = PROJECT_ROOT / "external/pinned/cork_full_drive.graphml"
CORK_SHA256 = "cc904d3c9107136fdf6fd24318c19c38958b63dc81c83441e8e5f855f41f5409"
CORK_SIZE_BYTES = 8_346_799


def file_identity(path: Path) -> tuple[str, int]:
    """Return the SHA-256 and byte size of one file."""

    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def install_cork_graphml(source: Path, destination: Path = CORK_DESTINATION) -> dict[str, object]:
    """Validate the frozen Cork GraphML before copying it into the ignored cache."""

    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Cork GraphML source is not a file: {source}")
    source_hash, source_size = file_identity(source)
    if source_hash != CORK_SHA256 or source_size != CORK_SIZE_BYTES:
        raise ValueError(
            "Cork GraphML identity mismatch: "
            f"sha256={source_hash} bytes={source_size}; "
            f"expected sha256={CORK_SHA256} bytes={CORK_SIZE_BYTES}"
        )
    destination = destination.expanduser().resolve()
    if source != destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    installed_hash, installed_size = file_identity(destination)
    if (installed_hash, installed_size) != (CORK_SHA256, CORK_SIZE_BYTES):
        raise RuntimeError("installed Cork GraphML failed its post-copy identity check")
    return {
        "status": "installed",
        "destination": str(destination),
        "sha256": installed_hash,
        "size_bytes": installed_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cork-graphml",
        type=Path,
        required=True,
        help="Existing frozen Cork GraphML supplied by the release author/data archive.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=CORK_DESTINATION,
        help="Ignored install path; defaults to external/pinned/cork_full_drive.graphml.",
    )
    args = parser.parse_args()
    print(json.dumps(install_cork_graphml(args.cork_graphml, args.destination), indent=2))


if __name__ == "__main__":
    main()
