"""Every Keeson profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

from typing import cast

import pytest

from custom_components.adjustable_bed.beds import innova, keeson_okin_apps, ore_comfort_bed
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.const import BED_TYPE_KEESON, KEESON_VARIANTS, VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import keeson as profiles
from custom_components.adjustable_bed.profiles.keeson import KeesonCommands as K
from custom_components.adjustable_bed.profiles.keeson import KeesonProfile
from custom_components.adjustable_bed.profiles.keeson import SinoCommands as S
from tests.keeson_vectors import FROZEN_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

APP_REPORTED = frozenset(
    {
        "adjustable_lite",
        "adjustable_lite_ksbt03c",
        "restonic_a",
        "restonic_b",
        "innova",
        "simon_li",
        "okin_seating",
        "heal_every_night",
        *(app for app in ore_comfort_bed.ORE_COMFORT_BED_APPS),
    }
)
_MOTORS = {"head": (K.MOTOR_HEAD_UP, K.MOTOR_HEAD_DOWN), "feet": (K.MOTOR_FEET_UP, K.MOTOR_FEET_DOWN)}
_STEP_MASSAGE = (K.MASSAGE_HEAD_UP, K.MASSAGE_HEAD_DOWN, K.MASSAGE_FOOT_UP, K.MASSAGE_FOOT_DOWN)


def _decode(data: bytes) -> bytes:
    """Re-encode a literal from its fields through the codec."""
    if data[:3] in (b"\xe5\xfe\x16", b"\xe6\xfe\x16"):
        side = data[7] if len(data) == 9 else None
        return codec.frame(int.from_bytes(data[3:7], "big"), header=data[0], order="big", side=side)
    if data == codec.STATUS_QUERY:
        return codec.STATUS_QUERY
    if data[:2] == b"\xef\x02":
        return codec.rename(data[2:16].rstrip(b"\x00"))
    if data[:1] == b"{":
        return data  # JSON text: covered by the census, which builds it through the codec.
    if len(data) == 6:
        carrier = "p2"
    elif data[0] == 0x05:
        carrier = "p2_side"
    else:
        carrier = "p2_checked" if data[6] == codec.checksum(data[:6]) else "p2_padded"
    return codec.p2(int.from_bytes(data[2:6], "big"), cast(codec.Carrier, carrier))


def _keeson_census(profile: KeesonProfile, *, exposed: bool) -> set[bytes]:
    """Frames ``KeesonController`` can send for a profile; ``exposed`` keeps entity-reachable ones."""
    words: set[int] = set()
    motors = dict(_MOTORS)
    if profile.tilt or not exposed:
        motors["tilt"] = (K.MOTOR_TILT_UP, K.MOTOR_TILT_DOWN)
    if profile.lumbar or not exposed:
        motors["lumbar"] = (K.MOTOR_LUMBAR_UP, K.MOTOR_LUMBAR_DOWN)
    motion = {word for pair in motors.values() for word in pair}
    motion |= {word for word, held in profile.held_controls.values() if held}
    words |= {
        word
        for preset, word in profile.presets.items()
        if not (exposed and preset in profile.unlisted_presets)
    }
    words |= set(profile.memory.values())
    if profile.memory_save is not None:
        words |= set(profile.memory_save.words.values())
    words |= {word for word, _held in profile.held_controls.values()}
    if profile.lights == "toggle" and (profile.lights_listed or not exposed):
        words.add(K.TOGGLE_SAFETY_LIGHTS)
    elif profile.lights == "discrete":
        words |= {S.LIGHT_ON, S.LIGHT_OFF}
    if profile.massage == "absolute":
        words |= {S.MASSAGE_HEAD_INTENSITY_BASE + level for level in range(11)}
        words |= {S.MASSAGE_FOOT_INTENSITY_BASE + level for level in range(11)}
        words |= {S.MASSAGE_HEAD_WAVE_BASE + pattern for pattern in range(1, 11)}
    elif profile.massage == "zone_steps" or not exposed or profile.massage == "step":
        words |= {*_STEP_MASSAGE, K.MASSAGE_TIMER_STEP}
        if profile.massage != "zone_steps" or not exposed:
            words.add(K.MASSAGE_STEP)
    if profile.massage_off is not None:
        words.add(profile.massage_off)
    if profile.wave_controls:
        words |= {
            K.MASSAGE_WAVE_STEP,
            K.MASSAGE_WAVE_PREVIOUS,
            K.MASSAGE_INTENSITY_1,
            K.MASSAGE_INTENSITY_2,
            K.MASSAGE_INTENSITY_3,
        }
    frames = {profiles.encode(profile, word, "Bed") for word in words}
    if profile.carrier == "json":
        frames |= {
            codec.json_command(word, "Bed", ctrm=ctrm, km=3, keykt=1)
            for word in motion
            for ctrm in (0, 1)
        }
    else:
        frames |= {profiles.encode(profile, word) for word in motion}
    frames |= {
        step if isinstance(step, bytes) else profiles.encode(profile, step, "Bed")
        for _wait, step in profile.release.steps
    }
    if profile.status_poll_ms:
        frames.add(codec.STATUS_QUERY)
    return frames


def _app_census(profile: KeesonProfile) -> set[bytes]:
    """Frames the INNOVA, Okin and ORE app controllers send from their key tables."""
    words = {codec.RELEASE}
    if profile is profiles.INNOVA:
        words |= {*innova._COMMON_HELD.values()}
        words |= {word for layout in innova._LAYOUT_HELD.values() for word in layout.values()}
        words |= {*profile.presets.values(), K.TOGGLE_LIGHTS, *_STEP_MASSAGE}
        words |= {innova.COMBINED_UP, innova.COMBINED_DOWN, innova.MASSAGE_LEVEL, innova.MASSAGE_TIMER}
        renames = {innova.innova_rename_frame(name) for name in ("A", "BED")}
        return {profiles.encode(profile, word) for word in words} | renames
    if profile.key in ("simon_li", "okin_seating"):
        table = keeson_okin_apps.SIMON_KEYS if profile is profiles.SIMON_LI else keeson_okin_apps.SEATING_KEYS
        words |= set(table.values())
    elif profile is profiles.HEAL_EVERY_NIGHT:
        apps = keeson_okin_apps
        words |= {*apps.HEAL_MOVEMENT_KEYS, apps.HEAL_PRESET_STOP, *apps.HEAL_PRESETS.values()}
        words |= {*apps.HEAL_MEMORY_SAVE.values(), apps.HEAL_TIMER}
        words |= {apps.HEAL_LIGHT_ON, apps.HEAL_LIGHT_OFF}
        words |= {apps.HEAL_HEAD_MASSAGE + level for level in range(apps.HEAL_ZONE_MAX + 1)}
        words |= {apps.HEAL_FOOT_MASSAGE + level for level in range(apps.HEAL_ZONE_MAX + 1)}
        words |= {apps.HEAL_WAVE + level - 1 for level in range(1, apps.HEAL_WAVE_MAX + 1)}
    else:
        ore = ore_comfort_bed
        words |= {word for axes in ore.LAYOUTS.values() for _k, _t, up, down in axes for word in (up, down)}
        words |= {ore.RECALL_ZERO_G, ore.RECALL_FLAT, *ore.RECALL_MEMORY.values()}
        words |= {ore.SAVE_ZERO_G, ore.SAVE_FLAT, *ore.SAVE_MEMORY.values()}
        words |= {ore.LIGHT_ON, ore.LIGHT_OFF, *ore.MASSAGE_TIMER.values()}
        words |= {
            base + level
            for base in ore.MASSAGE_BASE.values()
            for level in range(ore.MASSAGE_LEVEL_MAX + 1)
        }
    return {profiles.encode(profile, word) for word in words}


def test_every_profile_has_vectors() -> None:
    assert set(FROZEN_FRAMES) == set(profiles.PROFILES)


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(profile: str, literal: str) -> None:
    data = bytes.fromhex(literal)
    assert _decode(data) == data


@pytest.mark.parametrize("key", sorted(profiles.PROFILES))
def test_profile_sends_only_frozen_frames(key: str) -> None:
    profile = profiles.PROFILES[key]
    frozen = {bytes.fromhex(literal) for literal in FROZEN_FRAMES[key]}
    if key in APP_REPORTED:
        app_controller = key in ("innova", "simon_li", "okin_seating", "heal_every_night")
        app_controller |= key in ore_comfort_bed.ORE_COMFORT_BED_APPS
        census = _app_census(profile) if app_controller else _keeson_census(profile, exposed=True)
        assert {frame.hex() for frame in census - frozen} == set()
    else:
        # Without a report, the pre-v5 controller's frames are the complete vector set.
        assert {f.hex() for f in _keeson_census(profile, exposed=False) ^ frozen} == set()


def test_k1_frame_layout() -> None:
    assert codec.frame(0x12345678).hex() == "e5fe1678563412f2"
    assert codec.frame(0x12345678, order="big").hex() == "e5fe1612345678f2"
    assert codec.frame(0, header=0xE6, side=0).hex() == "e6fe16000000000005"
    with pytest.raises(ValueError):
        codec.frame(1 << 32)
    with pytest.raises(ValueError):
        codec.frame(0, header=0xE7)


@pytest.mark.parametrize("variant", sorted(KEESON_VARIANTS))
async def test_every_keeson_variant_route_is_a_profile_over_the_codec(variant: str) -> None:
    coordinator = _FactoryCoordinator()
    controller = await create_controller(
        coordinator, BED_TYPE_KEESON, variant, _make_connected_client()
    )
    profile = getattr(controller, "profile", None)
    assert isinstance(profile, KeesonProfile)
    assert profile.key in FROZEN_FRAMES
    if variant != VARIANT_AUTO:
        assert profile.key == variant
