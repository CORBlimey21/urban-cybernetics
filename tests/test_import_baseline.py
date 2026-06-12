"""Import and path smoke tests for the migrated package."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


ACTIVE_MODULES = (
    "urban_cybernetics",
    "urban_cybernetics.config",
    "urban_cybernetics.core",
    "urban_cybernetics.core.demand",
    "urban_cybernetics.core.event",
    "urban_cybernetics.core.lifecycle",
    "urban_cybernetics.core.link",
    "urban_cybernetics.core.packet",
    "urban_cybernetics.behaviour",
    "urban_cybernetics.benchmarks",
    "urban_cybernetics.benchmarks.sioux_falls",
    "urban_cybernetics.benchmarks.tntp_parser",
    "urban_cybernetics.governance",
    "urban_cybernetics.loading",
    "urban_cybernetics.network",
    "urban_cybernetics.network.graph_pipeline",
    "urban_cybernetics.nodes",
    "urban_cybernetics.observability",
    "urban_cybernetics.observability.snapshot_buffer",
    "urban_cybernetics.packets",
    "urban_cybernetics.packets.demand",
    "urban_cybernetics.packets.scenario_manifest",
    "urban_cybernetics.provenance",
    "urban_cybernetics.routing",
    "urban_cybernetics.topology",
    "urban_cybernetics.topology.canonical",
    "urban_cybernetics.topology.routes",
    "urban_cybernetics.topology.sioux_falls",
    "urban_cybernetics.validation",
)


class ImportBaselineTest(unittest.TestCase):
    def test_active_modules_import_cleanly(self) -> None:
        for module_name in ACTIVE_MODULES:
            with self.subTest(module_name=module_name):
                importlib.import_module(module_name)

    def test_committed_benchmark_paths_resolve(self) -> None:
        from urban_cybernetics.benchmarks.sioux_falls import (
            SIOUX_FALLS_NET_PATH,
            SIOUX_FALLS_TRIPS_PATH,
        )

        self.assertTrue(SIOUX_FALLS_NET_PATH.exists())
        self.assertTrue(SIOUX_FALLS_TRIPS_PATH.exists())

    def test_canonical_manifest_path_resolves(self) -> None:
        from urban_cybernetics.packets.scenario_manifest import canonical_selfish_manifest_path

        self.assertTrue(canonical_selfish_manifest_path().exists())


if __name__ == "__main__":
    unittest.main()
