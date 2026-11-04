"""Limoss guide checks beyond the generic ones in ``tests/test_codec_docs.py``."""

from __future__ import annotations

from pathlib import Path

from tests.codec_families.limoss import FAMILY

ROOT = Path(__file__).resolve().parents[1]


def test_limoss_guide_spells_wire_frames_and_plaintext_blocks() -> None:
    assert FAMILY.guide is not None
    spelled = FAMILY.guide.spelled((ROOT / FAMILY.guide.path).read_text(encoding="utf-8"))
    assert {frame[:2] for frame in spelled} == {"dd", "aa"}
