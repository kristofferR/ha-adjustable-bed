"""Every Jiecang profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.codec import jiecang as codec
from custom_components.adjustable_bed.profiles import jiecang as profiles
from tests.jiecang_vectors import FROZEN_FRAMES

PROFILES = {"legacy": profiles.LEGACY, **profiles.APP_PROFILES}


def _census(profile: profiles.JiecangProfile) -> set[str]:
    """Every fixed frame the profile can send through the codec."""
    frames = {release.hex() for _, release in profile.hold.releases + profile.bootstrap}
    if profile.recall.release is not None:
        frames.add(profile.recall.release.hex())
    for slot in range(1, profile.memory_slots + 1):
        for save in (False, True):
            frames.add(profiles.memory_command(profile, slot, save=save).hex())
    if profile is profiles.LEGACY:
        frames |= {
            codec.motion(axis, up).hex() for axis in ("back", "legs") for up in (True, False)
        }
        frames |= {profiles.preset_command(None, p).hex() for p in ("flat", "zero_g", "anti_snore")}
        frames |= {
            codec.massage(zone, level).hex() for zone in ("back", "legs") for level in range(11)
        }
        frames |= {
            codec.light_toggle().hex(),
            codec.massage_start().hex(),
            codec.massage_stop().hex(),
            codec.massage_mode().hex(),
        }
        return frames
    presets = ("flat", "zero_g", "anti_snore")
    if profile is not profiles.COMFORT_MOTION:
        presets += ("yoga",)
    for layout, axes in profile.layouts.items():
        bilateral = profiles.is_bilateral(layout)
        for axis in axes:
            for up in (True, False):
                frames.add(profiles.motion_command(profile, layout, axis, up).hex())
        frames |= {profiles.preset_command(layout, preset).hex() for preset in presets}
        for zone in profiles.massage_zones(layout):
            for level in range(len(profile.massage_levels)):
                frames.add(profiles.massage_command(profile, layout, zone, level).hex())
        frames.add(codec.massage_stop(bilateral=bilateral).hex())
        frames.add(codec.massage_mode(bilateral=bilateral).hex())
    return frames


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(profile, literal):
    data = bytes.fromhex(literal)
    opcode, length = data[2], data[3]
    assert codec.frame(opcode, data[4 : 4 + length]) == data


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_only_frozen_frames(key):
    census = _census(PROFILES[key])
    assert census <= FROZEN_FRAMES[key]
    if key == "legacy":
        # Without a report, the pre-v5 controller's frames are the complete vector set.
        assert census == FROZEN_FRAMES[key]
