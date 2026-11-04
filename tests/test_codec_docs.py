"""Codec guides keep their generated tables in step with the profile data."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_codec_docs", ROOT / "scripts" / "generate_codec_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_blocks_are_current() -> None:
    generator = _load_generator()
    assert generator.stale_guides() == [], (
        "Run `uv run --no-sync python scripts/generate_codec_docs.py` and commit the guides"
    )


def test_every_block_has_one_marked_region() -> None:
    generator = _load_generator()
    for guide, name in generator.BLOCKS:
        text = (ROOT / guide).read_text(encoding="utf-8")
        assert text.count(f"<!-- generated:{name} -->") == 1, f"{guide} needs one {name} block"


def test_jiecang_guide_frames_match_the_codec() -> None:
    """Every fully spelled frame in the guide is what the codec builds for its fields."""
    from custom_components.adjustable_bed.codec.jiecang import frame

    text = (ROOT / "docs" / "beds" / "jiecang.md").read_text(encoding="utf-8")
    # Frames appear both spaced (`F1 F1 01 ...`) and compact (`F1F101...`).
    frames = re.findall(r"`(F1 ?F1(?: ?[0-9A-F]{2})+ ?7E)`", text, re.IGNORECASE)
    assert frames
    for spelled in frames:
        data = bytes.fromhex(spelled.replace(" ", ""))
        assert data == frame(data[2], data[4:-2]), spelled
