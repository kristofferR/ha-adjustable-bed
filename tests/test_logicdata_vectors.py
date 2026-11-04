"""Every LOGICDATA profile's frozen frames pass through the Jiecang codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.codec import jiecang as codec
from custom_components.adjustable_bed.profiles import logicdata as profiles
from tests.logicdata_vectors import FROZEN_FRAMES


def _census(profile: profiles.LogicdataProfile) -> set[str]:
    """Every fixed frame the profile can send through the codec."""
    schedules = (
        profile.touch_release,
        profile.light_releases,
        profile.massage_mode_releases,
        profile.massage_query,
        *profile.startup.values(),
    )
    frames = {command for schedule in schedules for _, command in schedule}
    frames.add(codec.SHORT_RELEASE)
    if profile.factory_reset:
        frames.add(codec.FACTORY_RESET)
    for family in profiles.FAMILIES:
        for layout, axes in profile.layouts.items():
            try:
                profiles.validate_setup(profile, family, layout)
            except ValueError:
                continue
            frames |= {
                profiles.motion_command(profile, family, layout, axis, up)
                for axis in axes
                for up in (True, False)
            }
        frames |= {profiles.preset_command(profile, family, p) for p in profile.presets[family]}
        frames |= {
            profiles.held_preset_command(profile, family, p) for p in profile.held_presets[family]
        }
        for slot in range(1, profile.memory_slots + 1):
            frames.add(profiles.memory_command(profile, family, slot))
            frames |= {c for _, c in profiles.memory_save_schedule(profile, family, slot)}
        frames.add(profiles.light_command(profile, family))
        if family in profile.massage_families:
            frames |= {
                profiles.massage_command(zone, level)
                for zone in ("back", "legs", "right")
                for level in range(len(profiles.WIRE_MASSAGE_LEVELS))
            }
            frames |= {codec.massage_stop(), codec.massage_mode()}
    return {frame.hex() for frame in frames}


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(profile, literal):
    data = bytes.fromhex(literal)
    opcode, length = data[2], data[3]
    assert codec.frame(opcode, data[4 : 4 + length]) == data


@pytest.mark.parametrize("key", sorted(profiles.APP_PROFILES))
def test_profile_sends_only_frozen_frames(key):
    assert _census(profiles.APP_PROFILES[key]) <= FROZEN_FRAMES[key]

