"""Every FFFF profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.codec import ff_frame as codec
from custom_components.adjustable_bed.const import BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import ff_frame as profiles
from custom_components.adjustable_bed.profiles.ff_frame import SolaceCommands as C
from tests.ff_frame_vectors import ANOMALIES, FROZEN_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

_AXIS_FRAMES = {
    "back": (C.MOTOR_BACK_UP, C.MOTOR_BACK_DOWN),
    "legs": (C.MOTOR_LEGS_UP, C.MOTOR_LEGS_DOWN),
    "head": (C.MOTOR_HEAD_UP, C.MOTOR_HEAD_DOWN),
    "hip": (C.MOTOR_HIP_UP, C.MOTOR_HIP_DOWN),
    "lumbar": (C.MOTOR_HIP_UP, C.MOTOR_HIP_DOWN),
    "bed_height": (C.MOTOR_LIFT_UP, C.MOTOR_LIFT_DOWN),
    "tilt": (C.MOTOR_TILT_UP, C.MOTOR_TILT_DOWN),
}


def _rebuild(data: bytes) -> bytes:
    """Encode the literal's fields again with the codec."""
    kind = data[4]
    if kind == 0x05 and len(data) == 11:
        return codec.control(data[8], arg=data[7], group=data[6])
    if kind == 0x03 and len(data) == 11:
        return codec.query(data[6], data[8])
    if kind in (0x01, 0x02):
        if data[7] == len(data):
            return codec.summed(kind, data[6], data[8:-2])
        # Builders with a fixed length byte over a variable payload.
        return codec.with_sum(data[:-2])
    return codec.with_crc(data[:-2])


def _solace_census(profile: profiles.SolaceProfile) -> set[bytes]:
    """Every fixed frame a Solace route exposes, from its profile data."""
    frames = {codec.STOP}
    for axis in profile.axes:
        frames.update(_AXIS_FRAMES[axis])
    if profile.presets:
        frames |= {profile.flat, C.PRESET_TV, C.PRESET_TV_SELECTED, C.PRESET_ZERO_G}
        frames |= {C.PRESET_ZERO_G_SELECTED, C.PRESET_ANTI_SNORE, C.PRESET_ANTI_SNORE_SELECTED}
        recalls = (C.PRESET_MEMORY_1, C.PRESET_MEMORY_2)[: profile.memory_slots]
        programs = (
            (C.PROGRAM_MEMORY_1, C.PROGRAM_MEMORY_1_SELECTED),
            (C.PROGRAM_MEMORY_2, C.PROGRAM_MEMORY_2_SELECTED),
        )[: profile.memory_slots]
        frames |= set(recalls) | {frame for pair in programs for frame in pair}
    if profile.relaxing_bedtime:
        frames.add(C.PRESET_RELAXING_BEDTIME)
    if profile.massage:
        frames |= {C.MASSAGE_HEAD_UP, C.MASSAGE_HEAD_DOWN, C.MASSAGE_FOOT_UP, C.MASSAGE_FOOT_DOWN}
        frames |= {C.MASSAGE_STOP, C.MASSAGE_TIMER_10_MIN, C.MASSAGE_TIMER_20_MIN}
        frames.add(C.MASSAGE_TIMER_30_MIN)
        if profile.key != "woosa":
            frames |= {C.MASSAGE_FREQUENCY_UP, C.MASSAGE_FREQUENCY_DOWN}
    if profile.circulation:
        frames |= {C.MASSAGE_CIRCULATION_FULL_BODY, C.MASSAGE_CIRCULATION_HEAD}
        frames |= {C.MASSAGE_CIRCULATION_LEG, C.MASSAGE_CIRCULATION_HIP}
    if profile.light_levels:
        frames |= set(C.LIGHT_LEVELS) | {C.LIGHT_STATUS_QUERY}
    if profile.light_timer:
        frames |= {C.LIGHT_TIMER_10_MIN, C.LIGHT_TIMER_8_HOURS, C.LIGHT_TIMER_10_HOURS}
    if profile.audio:
        frames |= {C.MUSIC_TOGGLE, C.MUSIC_OFF, C.AUDIO_VOLUME_QUERY}
        frames |= {
            codec.summed(0x01, 0x13, bytes((track | flag,)))
            for track in range(1, 6)
            for flag in (0, 0x80)
        }
        frames |= {codec.summed(0x01, 0x14, bytes((level,))) for level in range(1, 6)}
    if profile.queries in ("q1", "home_k2"):
        frames |= set(C.QUERY_Q1)
    if profile.queries in ("q2", "home_k2"):
        frames |= set(C.QUERY_Q2)
    if profile.key == "woosa":
        # Woosa's leg-down arrow is Flat; it saves without the selected branches.
        frames -= {C.MOTOR_LEGS_DOWN, C.PROGRAM_MEMORY_1_SELECTED}
        frames |= set(profiles.WOOSA_SAVES.values()) | set(profiles.WOOSA_PRESET_QUERIES)
        frames |= {profiles.WOOSA_INIT, profiles.WOOSA_ALARM_QUERY, profiles.WOOSA_LIGHT_OFF}
        frames |= {profiles.WOOSA_MODE_STEP, *profiles.WOOSA_HEAD_LEVELS}
        frames |= {*profiles.WOOSA_FOOT_LEVELS, *profiles.WOOSA_MODES}
    return frames


def _census(key: str) -> set[str]:
    if key == "bedsense":
        frames = {action.frame for action in profiles.BEDSENSE.actions.values()}
    elif key == "motion_bed":
        frames = {*profiles.MOTION_BED.commands.values(), profiles.MOTION_BED.stop}
    else:
        frames = _solace_census(profiles.SOLACE_PROFILES[key])
    return {frame.hex() for frame in frames}


@pytest.mark.parametrize(
    ("profile", "literal"),
    [
        (profile, literal)
        for profile, frames in FROZEN_FRAMES.items()
        for literal in sorted(frames - ANOMALIES.get(profile, frozenset()))
    ],
)
def test_frozen_frame_round_trips_through_codec(profile: str, literal: str) -> None:
    data = bytes.fromhex(literal)
    assert _rebuild(data) == data


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in ANOMALIES.items() for literal in sorted(frames)],
)
def test_anomalies_are_frozen_verbatim_frames(profile: str, literal: str) -> None:
    data = bytes.fromhex(literal)
    assert literal in FROZEN_FRAMES[profile]
    assert _rebuild(data) != data
    assert literal in _census(profile)


@pytest.mark.parametrize("key", sorted(FROZEN_FRAMES))
def test_profile_sends_only_frozen_frames(key: str) -> None:
    census = _census(key)
    assert census <= FROZEN_FRAMES[key]
    if key in ("legacy_s4_y", "unverified", "bedsense"):
        # No report for the first two; BedSense's report is its complete command table.
        assert census == FROZEN_FRAMES[key]


def test_every_solace_route_has_vectors() -> None:
    assert set(profiles.SOLACE_PROFILES) <= set(FROZEN_FRAMES)


async def test_woosa_variant_selects_the_woosa_profile() -> None:
    controller = await create_controller(
        _FactoryCoordinator(), BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA, _make_connected_client()
    )
    assert controller.profile is profiles.SOLACE_PROFILES["woosa"]
