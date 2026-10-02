# SPDX-License-Identifier: MPL-2.0
"""Portable helpers used by publication artifact exporters."""

from pathlib import Path
from typing import Iterable

from .fonts import load_publication_font


def require_reference_inputs(paths: Iterable[Path]) -> None:
    """Fail before writing outputs if separately supplied reference data are absent."""
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Digitised de Souza reference input is unavailable in this release. "
            "Obtain it separately under its source terms; see THIRD_PARTY.md. "
            "Missing: " + ", ".join(missing)
        )


__all__ = ["load_publication_font", "require_reference_inputs"]
