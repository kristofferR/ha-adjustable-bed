"""The Hush Base report's frozen frames pass through the Casper codec byte for byte."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import casper as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.hush_catalog import ACTIONS as CATALOG_ACTIONS
from custom_components.adjustable_bed.profiles.hush import ACTIONS, CURRENT, PROFILES, HushProfile
from tests.casper_frames import rebuild
from tests.hush_vectors import FROZEN_FRAMES, SHARED_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

ALL_FRAMES = sorted(SHARED_FRAMES.union(*FROZEN_FRAMES.values()))


@pytest.mark.parametrize("literal", ALL_FRAMES)
def test_frozen_frame_round_trips_through_codec(literal):
    frame = bytes.fromhex(literal)
    assert rebuild(frame) == frame


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
        for index in group
        for opcode in ACTIONS[index][1:]
        if opcode is not None and ACTIONS[index][0] != "PhoneLight"
    }
    commands = {codec.control(opcode).hex() for opcode in opcodes}
    assert commands <= FROZEN_FRAMES[key], sorted(commands - FROZEN_FRAMES[key])


def test_the_music_page_sends_frozen_frames():
    """The profile's actions beyond the catalog are the music page's, each frozen."""
    assert ACTIONS[: len(CATALOG_ACTIONS)] == CATALOG_ACTIONS
    music = ACTIONS[len(CATALOG_ACTIONS) :]
    assert music and all(name.startswith("Music") and long is None for name, _, long in music)
    for _, short, _ in music:
        for single in (True, False):
            assert codec.control(short, single=single).hex() in ALL_FRAMES


def test_the_controller_builds_no_frame_of_its_own():
    beds = Path(__file__).parents[1] / "custom_components/adjustable_bed/beds"
    assert not re.search(r"""b["']\\x6e|bytes\(\(0x6E""", (beds / "hush_base.py").read_text(), re.I)


async def test_the_route_drives_its_profile():
    controller = await create_controller(
        _FactoryCoordinator(), const.BED_TYPE_HUSH_BASE, "hushl400", _make_connected_client()
    )
    profile = getattr(controller, "profile", None)
    assert isinstance(profile, HushProfile) and profile is PROFILES["hushl400"]
