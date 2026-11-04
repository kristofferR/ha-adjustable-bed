"""Codec guides keep their generated tables in step with the codec and profile data."""

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


def test_jiecang_guide_frames_are_frozen_vectors() -> None:
    """Every fully spelled frame in the guide is one a profile was frozen sending.

    The generated tables build their frames through the codec, so a swapped row
    makes the block stale; this catches frames spelled by hand outside them.
    """
    from tests.jiecang_vectors import FROZEN_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values())
    text = (ROOT / "docs" / "beds" / "jiecang.md").read_text(encoding="utf-8")
    # Frames appear both spaced (`F1 F1 01 ...`) and compact (`F1F101...`).
    frames = re.findall(r"`(F1 ?F1(?: ?[0-9A-F]{2})+ ?7E)`", text, re.IGNORECASE)
    assert frames
    unknown = sorted(
        {spelled for spelled in frames if spelled.replace(" ", "").lower() not in frozen}
    )
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


async def test_jiecang_bed_types_match_the_factory() -> None:
    """The profile summary's bed types are the ones the factory builds each profile for."""
    from custom_components.adjustable_bed.beds.jiecang import JiecangProfileController
    from custom_components.adjustable_bed.const import CONF_JIECANG_APP_PROFILE
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.profiles.jiecang import APP_PROFILES, LEGACY
    from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

    profiles = {"legacy": LEGACY, **APP_PROFILES}
    bed_types = _load_generator().jiecang_bed_types()
    assert bed_types.keys() == profiles.keys()
    for key, types in bed_types.items():
        assert types, f"{key} has no bed type"
        for bed_type in types:
            coordinator = _FactoryCoordinator()
            coordinator.entry.data[CONF_JIECANG_APP_PROFILE] = key
            controller = await create_controller(
                coordinator, bed_type, None, _make_connected_client()
            )
            assert isinstance(controller, JiecangProfileController), bed_type
            assert controller.profile is profiles[key], (key, bed_type)


def test_limoss_guide_frames_are_frozen_vectors() -> None:
    """Every spelled ten-byte frame and plaintext block in the guide is a frozen vector."""
    from custom_components.adjustable_bed.codec.limoss import decrypt
    from tests.limoss_vectors import WIRE_FRAMES

    wires = {wire for rows in WIRE_FRAMES.values() for _, _, wire in rows}
    plains = {decrypt(bytes.fromhex(wire)[1:9]).hex() for wire in wires}
    text = (ROOT / "docs" / "beds" / "limoss.md").read_text(encoding="utf-8")
    frames = re.findall(r"`(DD(?: [0-9A-F]{2}){9})`", text)
    blocks = re.findall(r"`(AA(?: [0-9A-F]{2}){7})`", text)
    assert frames and blocks
    unknown = sorted(
        spelled
        for spelled in frames + blocks
        if spelled.replace(" ", "").lower() not in wires | plains
    )
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


async def test_limoss_bed_types_match_the_factory() -> None:
    """The profile summary's bed types are the ones the factory builds each profile for."""
    from custom_components.adjustable_bed.profiles.limoss import PROFILES
    from tests.test_controller_contract import _create_controller_for_bed_type

    bed_types = _load_generator().LIMOSS_BED_TYPES
    assert bed_types.keys() == PROFILES.keys()
    for key, bed_type in bed_types.items():
        controller = await _create_controller_for_bed_type(bed_type)
        assert getattr(controller, "profile", None) is PROFILES[key], (key, bed_type)
