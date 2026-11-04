"""FFFF guide checks beyond the generic ones in ``tests/test_codec_docs.py``."""

from __future__ import annotations

from pathlib import Path

from tests.codec_families.ff_frame import FAMILY

ROOT = Path(__file__).resolve().parents[1]


def test_ff_frame_guide_spells_its_frames() -> None:
    """The trailer filter recognises the guide's frames rather than dropping them."""
    assert FAMILY.guide is not None
    text = (ROOT / FAMILY.guide.path).read_text(encoding="utf-8")
    assert len(FAMILY.guide.spelled(text)) > 100
