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


def test_okin_nframe_guide_frames_are_frozen_vectors() -> None:
    """Every fully spelled 32-bit frame or envelope in the guide is a frozen one."""
    from tests.okin_nframe_vectors import FIELD_FRAMES, FROZEN_FRAMES, GATEWAY_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values(), *FIELD_FRAMES.values(), GATEWAY_FRAMES)
    text = (ROOT / "docs" / "beds" / "okin-nframe.md").read_text(encoding="utf-8")
    frames = re.findall(
        r"`(04 ?02(?: ?[0-9A-F]{2}){4}|E5 ?FE ?16(?: ?[0-9A-F]{2}){5})`", text, re.IGNORECASE
    )
    assert frames
    unknown = sorted(
        {spelled for spelled in frames if spelled.replace(" ", "").lower() not in frozen}
    )
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


async def test_okin_nframe_bed_types_match_the_factory() -> None:
    """Each profile's bed types build a controller over that profile."""
    from custom_components.adjustable_bed.const import (
        CONF_LEGGETT_APP_PROFILE,
        LEGGETT_VARIANT_OKIN,
    )
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

    for profile in _load_generator()._okin_profiles():
        assert profile.bed_types, profile.key
        for bed_type in profile.bed_types:
            coordinator = _FactoryCoordinator()
            coordinator.entry.data[CONF_LEGGETT_APP_PROFILE] = profile.key
            variant = LEGGETT_VARIANT_OKIN if bed_type == "leggett_platt" else None
            controller = await create_controller(
                coordinator, bed_type, variant, _make_connected_client()
            )
            assert getattr(controller, "profile", None) is profile, (profile.key, bed_type)
