"""Load-only access to canonical scenario manifests.

This module exists to make one rule explicit: benchmark comparison scenarios are committed inputs,
not generated on demand during a simulation run.

Why this file exists:
- to make the canonical manifest path discoverable from one place
- to separate immutable scenario loading from demand-generation helpers
- to reduce the risk of accidentally comparing two experiments that used slightly different inputs

Key design decisions:
- the canonical selfish batch manifest is treated as read-only by the runtime code
- manifest trip requests are converted back into `TripRequest` dataclasses so the rest of the routing code
  can stay typed and simple
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import CANONICAL_SELFISH_MANIFEST_FILENAME, get_project_paths
from .demand import TripRequest


def canonical_selfish_manifest_path() -> Path:
    """Return the repository path to the immutable selfish benchmark manifest.

    Parameters:
    - None.

    Returns:
    - The filesystem path to the canonical 200-trip selfish scenario manifest.
    """

    paths = get_project_paths()
    return paths.scenarios / CANONICAL_SELFISH_MANIFEST_FILENAME


def load_canonical_selfish_manifest() -> dict[str, Any]:
    """Load the canonical selfish benchmark manifest from disk.

    Parameters:
    - None.

    Returns:
    - The parsed JSON manifest as a dictionary.

    Why this approach was chosen:
    - Benchmark comparisons should be driven by a committed artifact, not by rerunning a seeded generator.
    - Loading raw JSON keeps the manifest human-readable and easy to diff in Git.
    """

    path = canonical_selfish_manifest_path()
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest_from_path(manifest_path: str | Path) -> dict[str, Any]:
    """Load any scenario manifest from an explicit filesystem path.

    Parameters:
    - manifest_path: Filesystem path to the manifest JSON file.

    Returns:
    - The parsed JSON manifest as a dictionary.

    Why this approach was chosen:
    - Scaled scenario manifests live at dynamically constructed paths, so the loader must accept
      an explicit path rather than hard-coding the canonical filename.
    """

    path = Path(manifest_path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_trip_requests_from_manifest(manifest: dict[str, Any]) -> list[TripRequest]:
    """Convert manifest trip dictionaries into `TripRequest` dataclasses.

    Parameters:
    - manifest: Parsed scenario manifest loaded from JSON.

    Returns:
    - A list of `TripRequest` dataclasses ready for routing.
    """

    return [TripRequest(**trip_data) for trip_data in manifest["trip_requests"]]
