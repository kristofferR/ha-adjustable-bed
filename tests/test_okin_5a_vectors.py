"""Every Okin 5A profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import okin_5a as codec
from custom_components.adjustable_bed.const import VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.okin_5a import PROFILES
from tests.okin_5a_vectors import FROZEN_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(profile, literal):
    data = bytes.fromhex(literal)
    if data in codec.CONNECTION_FRAMES:
        return
    assert codec.command(data[5], data[4]) == data


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_only_frozen_frames(key):
    profile = PROFILES[key]
    census = {frame.hex() for frame in (*profile.frames.values(), *profile.wake)}
    # Without a report, the pre-v5 controller's frames are the complete vector set.
    assert census == FROZEN_FRAMES[key]


def test_profiles_cover_the_vectors():
    assert set(PROFILES) == set(FROZEN_FRAMES)


ROUTES = [
    (const.BED_TYPE_OKIN_7BYTE, VARIANT_AUTO, "okin_7byte"),
    (const.BED_TYPE_NECTAR, VARIANT_AUTO, "okin_7byte"),
    (const.BED_TYPE_OKIN_NORDIC, VARIANT_AUTO, "okin_nordic"),
    (const.BED_TYPE_MATTRESSFIRM, VARIANT_AUTO, "okin_nordic"),
    (const.BED_TYPE_OKIN_CB35, VARIANT_AUTO, "okin_cb35"),
    (const.BED_TYPE_STAR_ELEVATE, VARIANT_AUTO, "star_elevate"),
    (const.BED_TYPE_STAR_ELEVATE, const.STAR_ELEVATE_VARIANT_M1X12, "star_elevate"),
]


@pytest.mark.parametrize(("bed_type", "variant", "key"), ROUTES)
async def test_every_route_drives_its_profile(bed_type, variant, key):
    controller = await create_controller(
        _FactoryCoordinator(), bed_type, variant, _make_connected_client()
    )
    assert getattr(controller, "profile", None) is PROFILES[key]
