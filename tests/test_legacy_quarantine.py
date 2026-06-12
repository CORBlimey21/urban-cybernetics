"""Guardrails that keep legacy reference code out of active imports."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


CANONICAL_MODULES = (
    "urban_cybernetics.config",
    "urban_cybernetics.core",
    "urban_cybernetics.behaviour",
    "urban_cybernetics.governance",
    "urban_cybernetics.loading",
    "urban_cybernetics.network",
    "urban_cybernetics.nodes",
    "urban_cybernetics.observability",
    "urban_cybernetics.packets",
    "urban_cybernetics.provenance",
    "urban_cybernetics.routing",
    "urban_cybernetics.topology",
    "urban_cybernetics.validation",
)

LEGACY_MARKERS = (
    "legacy",
    "bpr_reference",
    "static_assignment",
    "network_costs",
)


class LegacyQuarantineTest(unittest.TestCase):
    def test_canonical_imports_do_not_load_legacy_reference_modules(self) -> None:
        before = set(sys.modules)
        for module_name in CANONICAL_MODULES:
            with self.subTest(module_name=module_name):
                importlib.import_module(module_name)

        imported = set(sys.modules) - before
        contaminated = [
            module_name
            for module_name in sorted(imported)
            if any(marker in module_name for marker in LEGACY_MARKERS)
        ]
        self.assertEqual(contaminated, [])


if __name__ == "__main__":
    unittest.main()
