# SPDX-License-Identifier: MPL-2.0
"""The loading kernel must remain unaware of the V application."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loading_source_does_not_import_visualisation_package() -> None:
    loading_directory = ROOT / "src/urban_cybernetics/loading"
    for path in loading_directory.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any("visualisation" in module for module in imported), path


def test_importing_loading_does_not_load_visualisation_modules() -> None:
    code = (
        "import sys; import urban_cybernetics.loading; "
        "assert not any(name.startswith('urban_cybernetics.visualisation') "
        "for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)
