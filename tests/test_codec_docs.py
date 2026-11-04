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
    from tests.logicdata_vectors import FROZEN_FRAMES as LOGICDATA_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values(), *LOGICDATA_FRAMES.values())
    text = (ROOT / "docs" / "beds" / "jiecang.md").read_text(encoding="utf-8")
    # Frames appear both spaced (`F1 F1 01 ...`) and compact (`F1F101...`).
    frames = re.findall(r"`(F1 ?F1(?: ?[0-9A-F]{2})+ ?7E)`", text, re.IGNORECASE)
    assert frames
    unknown = sorted(
        {spelled for spelled in frames if spelled.replace(" ", "").lower() not in frozen}
    )
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


def test_ff_frame_guide_frames_are_frozen_vectors() -> None:
    """Every complete FFFF frame spelled in the guide is one a profile was frozen sending.

    A spelled byte string counts as a frame when its trailer is the codec's CRC or
    sum, or it is a listed anomaly; shorter prefixes such as reply patterns do not.
    """
    from custom_components.adjustable_bed.codec.ff_frame import with_crc, with_sum
    from tests.ff_frame_vectors import ANOMALIES, FROZEN_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values())
    anomalies = frozenset().union(*ANOMALIES.values())
    text = (ROOT / "docs" / "beds" / "ff_frame.md").read_text(encoding="utf-8")
    spelled = re.findall(r"`(FF ?FF ?FF ?FF(?: ?[0-9A-F]{2})+)`", text, re.IGNORECASE)
    frames = set()
    for value in spelled:
        data = bytes.fromhex(value.replace(" ", ""))
        body = data[:-2]
        if data.hex() in anomalies or data in (with_crc(body), with_sum(body)):
            frames.add(data.hex())
    assert len(frames) > 100
    unknown = sorted(frames - frozen)
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


def test_okin_5a_guide_frames_are_frozen_vectors() -> None:
    """Every frame spelled in the Okin 5A guide is one a profile was frozen sending."""
    from tests.okin_5a_vectors import FROZEN_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values())
    text = (ROOT / "docs" / "beds" / "okin-5a.md").read_text(encoding="utf-8")
    frames = re.findall(r"`((?:5A|09)(?: [0-9A-F]{2}){3,6})`", text)
    assert frames
    unknown = sorted(
        {spelled for spelled in frames if spelled.replace(" ", "").lower() not in frozen}
    )
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


async def test_okin_5a_bed_types_match_the_factory() -> None:
    """The Okin 5A profile summary's bed types are the ones the factory builds each profile for."""
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.profiles.okin_5a import PROFILES
    from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

    bed_types = _load_generator().okin_5a_bed_types()
    assert bed_types.keys() == PROFILES.keys()
    for key, types in bed_types.items():
        assert types, f"{key} has no bed type"
        for bed_type in types:
            controller = await create_controller(
                _FactoryCoordinator(), bed_type, None, _make_connected_client()
            )
            assert getattr(controller, "profile", None) is PROFILES[key], (key, bed_type)


def test_keeson_guide_frames_are_frozen_vectors() -> None:
    """Every fully spelled K1 or P2 frame in the Keeson guide is a frozen vector."""
    from tests.keeson_vectors import FROZEN_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values())
    text = (ROOT / "docs" / "beds" / "keeson.md").read_text(encoding="utf-8")
    frames = re.findall(r"`((?:E[56] ?FE ?16|0[45] ?02)(?: ?[0-9A-F]{2}){4,})`", text, re.I)
    assert frames
    unknown = sorted(
        {spelled for spelled in frames if spelled.replace(" ", "").lower() not in frozen}
    )
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


def test_keeson_routes_match_the_profiles() -> None:
    """The guide's sub-routes resolve as described, and its aliases are the factory's."""
    from custom_components.adjustable_bed.profiles import keeson as profiles

    generator = _load_generator()
    samples = {
        "ksbt03c": {"device_name": "KSBT03C1234"},
        "sleep_harmony_base_i5": {"device_name": "base-i5.1234"},
        "purple_plus": {"device_name": "KSBT04C1234"},
        "adjustable_lite_ksbt03c": {"device_name": "Bed KSBT03C"},
        "betterliving": {"device_name": None, "betterliving": True},
        "cb1322": {"device_name": None, "cb1322": True},
    }
    assert samples.keys() == generator.KEESON_SUB_ROUTES.keys()
    for key, (variant, _rule) in generator.KEESON_SUB_ROUTES.items():
        assert profiles.resolve(variant, **samples[key]).key == key
    assert generator.keeson_aliases() == {
        "ergomotion": ("ergomotion",),
        "serta": ("serta",),
        "okin": ("okin_ffe",),
    }


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


def _richmat_spelled_frames() -> set[str]:
    """Fully spelled 6E/5E/55/AA/04 frames outside the Notifications sections."""
    text = (ROOT / "docs" / "beds" / "richmat.md").read_text(encoding="utf-8")
    sections = re.split(r"^(#+ .*)$", text, flags=re.M)
    sent = "".join(
        body
        for heading, body in zip(["", *sections[1::2]], sections[0::2], strict=True)
        if "Notifications" not in heading
    )
    spelled = re.findall(r"`((?:6E|5E|55|AA|04)(?: ?[0-9A-F]{2}){4,})`", sent, re.IGNORECASE)
    frames = set()
    for literal in spelled:
        data = bytes.fromhex(literal.replace(" ", ""))
        # One write may carry back-to-back 5-byte frames.
        if len(data) % 5 == 0 and sum(data[:-1]) & 255 != data[-1]:
            frames |= {data[i : i + 5].hex() for i in range(0, len(data), 5)}
        else:
            frames.add(data.hex())
    return frames


def test_richmat_guide_frames_are_frozen_vectors() -> None:
    from tests.richmat_vectors import FROZEN_FRAMES

    frozen = frozenset().union(*FROZEN_FRAMES.values())
    frames = _richmat_spelled_frames()
    assert frames
    assert not sorted(frames - frozen), (
        f"Frames no profile was frozen sending: {sorted(frames - frozen)}"
    )


async def test_richmat_bed_types_match_the_factory() -> None:
    """The profile summary's bed types build controllers over the listed profile."""
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

    variants = {
        "richmat_wilinke": const.RICHMAT_VARIANT_WILINKE,
        "richmat_nordic": const.RICHMAT_VARIANT_NORDIC,
        "richmat_prefix55": const.RICHMAT_VARIANT_PREFIX55,
        "richmat_prefixaa": const.RICHMAT_VARIANT_PREFIXAA,
        "hjbed": "hj_bedbjrn",
    }
    for key, types in _load_generator().richmat_bed_types().items():
        for bed_type in types:
            controller = await create_controller(
                _FactoryCoordinator(), bed_type, variants.get(key), _make_connected_client()
            )
            assert controller.profile.key == key, (key, bed_type)
