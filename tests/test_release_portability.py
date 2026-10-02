# SPDX-License-Identifier: MPL-2.0
"""Release portability checks for fonts and external-data installation."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import ImageFont

from urban_cybernetics.publication.fonts import (
    PUBLICATION_ARIAL_DIRECTORY_ENV,
    load_publication_font,
)


def test_publication_font_has_portable_pillow_fallback(monkeypatch) -> None:
    monkeypatch.delenv(PUBLICATION_ARIAL_DIRECTORY_ENV, raising=False)

    font = load_publication_font(ImageFont, 23)

    assert font.getbbox("Urban Cybernetics")[2] > 0


def test_explicit_archival_arial_directory_must_be_complete(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv(PUBLICATION_ARIAL_DIRECTORY_ENV, str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Arial.ttf"):
        load_publication_font(ImageFont, 23)
