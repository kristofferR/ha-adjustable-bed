"""The BedJet PowerLayer profile's frozen frames pass through its codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import bedjet_powerlayer as codec
from custom_components.adjustable_bed.const import VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.bedjet_powerlayer import PROFILES
from tests.bedjet_powerlayer_vectors import FROZEN_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(profile, literal):
    data = bytes.fromhex(literal)
    assert data[0] == codec.BUTTON
    assert codec.command(data[1]) == data


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_only_frozen_frames(key):
    census = {frame.hex() for frame in PROFILES[key].frames.values()}
    assert census == FROZEN_FRAMES[key]


def test_profiles_cover_the_vectors():
    assert set(PROFILES) == set(FROZEN_FRAMES)


def test_status_frame_decodes_head_and_foot_counts():
    frame = bytes(12) + (3362).to_bytes(2, "big") + (1704).to_bytes(2, "big") + bytes(4)
    assert codec.positions(frame) == (3362, 1704)
    assert codec.positions(frame[:19]) is None


async def test_the_route_drives_its_profile():
    controller = await create_controller(
        _FactoryCoordinator(),
        const.BED_TYPE_BEDJET_POWERLAYER,
        VARIANT_AUTO,
        _make_connected_client(),
    )
    assert getattr(controller, "profile", None) is PROFILES["powerlayer"]
