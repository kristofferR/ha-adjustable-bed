"""The Hush Base report's frozen frames pass through the Casper codec byte for byte."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import casper as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.hush_catalog import ACTIONS
from custom_components.adjustable_bed.profiles.hush import CURRENT, PROFILES, HushProfile
from tests.hush_vectors import FROZEN_FRAMES, SHARED_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

_QUERIES = {bytes(values[:4]): name for name, values in codec.SPECIAL.items()}


def _rebuild(frame: bytes) -> bytes:
    """Decode one write by its form and encode it again through the codec."""
    if len(frame) == 1:
        return codec.control(frame[0], single=True)
    # The colour write carries two frames, each with its own checksum.
    if frame[0] != 0x6E or (len(frame) != 10 and codec.frame(frame[:-1]) != frame):
        raise AssertionError(f"not a Casper frame: {frame.hex()}")
    kind = frame[1]
    if kind == 0x01:
        return codec.control(frame[3], side=frame[2])
    if (name := _QUERIES.get(frame[:4])) is not None:
        return codec.special(name)
    if kind == 0x0B:
        high, low = frame[2], frame[3]
        return codec.light_seconds(0 if high == low == 0xFF else high << 8 | low)
    if kind == 0x0C:
        return codec.light_rgb((frame[3], frame[7], frame[8]))
    if kind == 0x06:
        return codec.alarm_pair(frame[2] << 8, frame[3])[0]
    if kind == 0x05 and frame[3] == 0:
        return codec.alarm_pair(frame[2], 0)[1]
    if kind == 0x20 and frame[2] == len(frame):
        return codec.extra(frame[3], frame[4], frame[6:-1], operation=frame[5])
    raise AssertionError(f"no Casper builder sends {frame.hex()}")


ALL_FRAMES = sorted(SHARED_FRAMES.union(*FROZEN_FRAMES.values()))


@pytest.mark.parametrize("literal", ALL_FRAMES)
def test_frozen_frame_round_trips_through_codec(literal):
    frame = bytes.fromhex(literal)
    assert _rebuild(frame) == frame


def test_the_vectors_cover_the_apps_own_products():
    assert set(FROZEN_FRAMES) == {key for key, profile in PROFILES.items() if profile.current}
    assert {PROFILES[key].index for key in FROZEN_FRAMES} == set(CURRENT)


@pytest.mark.parametrize("key", sorted(FROZEN_FRAMES))
def test_each_product_sends_its_catalog_opcodes(key):
    """Every short or long opcode of the product's controls is a frozen command."""
    profile = PROFILES[key]
    opcodes = {
        opcode
        for group in (profile.row[1], profile.row[2], profile.row[3], profile.row[5])
        for index in group  # type: ignore[union-attr]
        for opcode in ACTIONS[index][1:]
        if opcode is not None and ACTIONS[index][0] != "PhoneLight"
    }
    commands = {codec.control(opcode).hex() for opcode in opcodes}
    assert commands <= FROZEN_FRAMES[key], sorted(commands - FROZEN_FRAMES[key])


def test_the_controller_builds_no_frame_of_its_own():
    beds = Path(__file__).parents[1] / "custom_components/adjustable_bed/beds"
    for name in ("hush_base.py", "casper_base.py"):
        assert not re.search(r"""b["']\\x6e|bytes\(\(0x6E""", (beds / name).read_text(), re.I)


async def test_the_route_drives_its_profile():
    controller = await create_controller(
        _FactoryCoordinator(), const.BED_TYPE_HUSH_BASE, "hushl400", _make_connected_client()
    )
    profile = getattr(controller, "profile", None)
    assert isinstance(profile, HushProfile) and profile is PROFILES["hushl400"]
