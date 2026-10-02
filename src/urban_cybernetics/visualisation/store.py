# SPDX-License-Identifier: MPL-2.0
"""Validated on-disk run-bundle registry for the local V application."""

from __future__ import annotations

from pathlib import Path

from .contract import VRunBundle
from .export import load_run_bundle


class RunNotFoundError(KeyError):
    """Raised when a requested persisted run is not registered."""


class RunStore:
    """Read-only registry; JSON artifacts remain the reloadable source."""

    def __init__(self, artifact_directory: Path) -> None:
        self.artifact_directory = artifact_directory
        self._paths_by_run_id: dict[str, Path] = {}
        self._bundles_by_run_id: dict[str, VRunBundle] = {}
        self.refresh()

    def refresh(self) -> None:
        paths_by_run_id: dict[str, Path] = {}
        for path in sorted(self.artifact_directory.glob("*.json")):
            bundle = load_run_bundle(path)
            if bundle.run.run_id in paths_by_run_id:
                raise ValueError(f"duplicate visualisation run_id: {bundle.run.run_id}")
            paths_by_run_id[bundle.run.run_id] = path
        self._paths_by_run_id = paths_by_run_id
        self._bundles_by_run_id.clear()

    def list_bundles(self) -> tuple[VRunBundle, ...]:
        return tuple(self.get(run_id) for run_id in sorted(self._paths_by_run_id))

    def get(self, run_id: str) -> VRunBundle:
        try:
            path = self._paths_by_run_id[run_id]
        except KeyError as exc:
            raise RunNotFoundError(run_id) from exc
        bundle = self._bundles_by_run_id.get(run_id)
        if bundle is None:
            bundle = load_run_bundle(path)
            self._bundles_by_run_id[run_id] = bundle
        return bundle
