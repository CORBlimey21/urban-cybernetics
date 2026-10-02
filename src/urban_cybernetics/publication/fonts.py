# SPDX-License-Identifier: MPL-2.0
"""Deterministic publication font selection without platform-specific paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


PUBLICATION_ARIAL_DIRECTORY_ENV = "UC_PUBLICATION_ARIAL_DIR"


def load_publication_font(image_font: Any, size: int, *, bold: bool = False) -> Any:
    """Load embedded Pillow Aileron, or explicitly configured archival Arial.

    Pillow >=10.1 embeds Aileron Regular for ``load_default(size=...)``. This is
    the portable deterministic release default. Set ``UC_PUBLICATION_ARIAL_DIR``
    to a directory containing ``Arial.ttf`` and ``Arial Bold.ttf`` only when
    reproducing the typography of the historical macOS-rendered PNG files.
    """

    configured = os.environ.get(PUBLICATION_ARIAL_DIRECTORY_ENV)
    if configured:
        filename = "Arial Bold.ttf" if bold else "Arial.ttf"
        path = Path(configured).expanduser() / filename
        if not path.is_file():
            raise FileNotFoundError(
                f"{PUBLICATION_ARIAL_DIRECTORY_ENV} does not contain {filename}: {path}"
            )
        return image_font.truetype(str(path), size)
    return image_font.load_default(size=size)
