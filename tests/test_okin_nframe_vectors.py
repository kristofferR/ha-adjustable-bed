"""Every Okin N-frame profile's frozen frames pass through the shared codec."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.eshine_okin import protocol as eshine
from custom_components.adjustable_bed.beds.okin_uuid.controller import (
    OKIN_UUID_REMOTES,
    OkinUuidComplexCommand,
)
from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.profiles import okin_nframe as profiles
from custom_components.adjustable_bed.profiles.comfort_enhancement3 import PROFILES as APEX_PROFILES
from tests.okin_nframe_vectors import (
    COMPOSED_FRAMES,
    FIELD_FRAMES,
    FROZEN_FRAMES,
    GATEWAY_FRAMES,
    SETTING_FRAMES,
    SETUP_FRAMES,
)

PROFILES: dict[str, profiles.OkinNFrameProfile] = {
    profile.key: profile
    for profile in (
        *APEX_PROFILES.values(),
        profiles.OKIMAT,
        profiles.RESIDENT,
        profiles.OKIN_MOTIONBED,
        profiles.DEWERTOKIN,
        profiles.RF_ECO_BT,
        *profiles.CUSTOMATIC_PROFILES.values(),
        *profiles.LEGGETT_PROFILES.values(),
        profiles.OKIN_DOT,
        profiles.OKIN_CB24,
        *profiles.SIMMONS_PROFILES.values(),
        profiles.DOUBLESLEEP,
        profiles.SLEEPYS_BOX25_LEGACY,
        *profiles.STARCODE_ABM5_4_PROFILES.values(),
        *profiles.CST_PROFILES.values(),
        *profiles.BEDDING_PROFILES.values(),
        *profiles.OKIN_64BIT_PROFILES.values(),
        *profiles.ADJUSTABLE_LUMBAR_PROFILES.values(),
        *profiles.ESHINE_PROFILES.values(),
    )
}
# Routes without a report on disk: their census must equal the pre-v5 frames.
LEGACY = {
    "okimat",
    "dewertokin",
    "okin_rf_eco_bt",
    "okin_dot",
    "okin_cb24",
    "sleepys_box25",
    "okin_64bit_nordic",
    "okin_64bit_custom",
    *(p.key for p in profiles.STARCODE_ABM5_4_PROFILES.values()),
}


def _remote_words(*, dot: bool = False) -> set[int]:
    """Every key word an Okimat (or only the DOT) handset table can send."""
    words: set[int] = set()
    for remote in OKIN_UUID_REMOTES.values():
        if dot and not remote.dot:
            continue
        for item in fields(remote):
            value = getattr(remote, item.name)
            if item.name == "quiet_sleep" and remote.anti_snore is not None:
                continue  # only the anti-snore fallback sends it
            if isinstance(value, OkinUuidComplexCommand):
                value = value.data
            if isinstance(value, dict):
                words.update(value.values())
            elif isinstance(value, int) and not isinstance(value, bool):
                words.add(value)
    return words


def _census(profile: profiles.OkinNFrameProfile) -> set[str]:
    """Every fixed single-key frame the profile can send, plus its STOP.

    Held motors and Customatic memory chords send the sum of their keys; those
    composite words are the same frame of a different word and are not listed.
    """
    words = set(profile.keys.values()) or _remote_words(dot=profile.key == "okin_dot")
    if profile.hold.releases or profile.recall and profile.recall.releases:
        words.add(0)
    if profile.width == 5:
        frames = {codec.frame40(word, s).hex() for word in words for s in profile.selectors}
    elif profile.width in (8, 12):
        frames = {codec.frame(word, profile.width).hex() for word in words}
    else:
        frames = {codec.frame(word).hex() for word in words}
    frames |= {codec.frame(word, 8).hex() for word in profile.long_keys.values()}
    if profile.envelope == "gateway":
        frames = {codec.gateway_frame(word).hex() for word in words}
    if profile.envelope == "revision_selector":
        frames |= {codec.gateway_frame(word).hex() for word in words}
    if profile.envelope == "keeson_e6":
        plain = {profile.keys[action] for action in profile.plain_keys}
        wrapped = {0} | {w for a, w in profile.keys.items() if a not in profile.plain_keys}
        frames = {codec.frame40(word).hex() for word in plain} | {
            keeson.frame(word, header=0xE6, side=0).hex() for word in wrapped
        }
    return frames


@pytest.mark.parametrize(
    ("profile", "literal"),
    [
        (profile, literal)
        for profile, frames in FROZEN_FRAMES.items()
        for literal in sorted(
            frames | FIELD_FRAMES.get(profile, frozenset()) | COMPOSED_FRAMES.get(profile, frozenset())
        )
    ],
)
def test_frozen_frame_round_trips_through_codec(profile, literal):
    data = bytes.fromhex(literal)
    if data[:3] == codec.GATEWAY_HEADER:
        assert codec.gateway_frame(int.from_bytes(data[3:7], "big")) == data
    elif data[:3] == b"\xe6\xfe\x16":
        word = int.from_bytes(data[3:7], "little")
        assert keeson.frame(word, header=0xE6, side=data[7]) == data
    else:
        assert codec.frame(int.from_bytes(data[2:], "big"), data[0]) == data


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_only_frozen_frames(key):
    census = _census(PROFILES[key])
    assert census <= FROZEN_FRAMES[key] | FIELD_FRAMES.get(key, frozenset())
    if key in LEGACY:
        assert census == FROZEN_FRAMES[key]


def _rebuild(data: bytes) -> bytes | None:
    """Re-encode a request, word, clock or alarm literal through the codec."""
    if len(data) == 2 and data[0] == 0:
        return codec.request(data[1])
    if data[0] != len(data) - 2:
        return None
    if data[1] == 0x02:
        return codec.frame(int.from_bytes(data[2:], "big"), data[0])
    if data[1] == 0x04:
        return codec.clock(data[2:])
    if data[1] in (0x05, 0x06):
        return codec.alarm(data[2:], data[1] - 0x04)
    return None


def test_alarm_slots() -> None:
    """SIMMONS SmartBed sets and clears both slots; single-alarm apps use slot 1."""
    assert codec.alarm(bytes.fromhex("8205071e000101")).hex() == "07058205071e000101"
    assert codec.alarm(bytes.fromhex("8205071e000101"), 2).hex() == "07068205071e000101"
    assert codec.alarm(bytes(7), 2).hex() == "070600000000000000"
    with pytest.raises(ValueError):
        codec.alarm(bytes(7), 3)


@pytest.mark.parametrize(
    ("profile", "literal"),
    [
        (profile, literal)
        for profile, frames in SETTING_FRAMES.items()
        for literal in sorted(frames)
    ],
)
def test_setting_frame_round_trips_through_codec(profile, literal):
    assert _rebuild(bytes.fromhex(literal)) == bytes.fromhex(literal)


@pytest.mark.parametrize("key", sorted(profiles.ESHINE_PROFILES))
def test_eshine_sends_only_frozen_frames(key):
    """The app's command table, clock and alarm frames are the profile's frozen literals."""
    frozen = FROZEN_FRAMES[key] | SETTING_FRAMES[key]
    now = datetime.fromisoformat("2026-11-03T14:47:09+01:00")
    sent = {
        *eshine.COMMANDS.values(),
        eshine.clock_frame(now),
        eshine.clock_frame(now.replace(year=1999)),
        eshine.alarm_frame(now, 16, 30, "zero_g"),
        eshine.alarm_frame(now, 12, 0, "flat"),
        eshine.alarm_frame(now.replace(day=7), 12, 0, "massage"),
    }
    assert {frame.hex() for frame in sent} == frozen


def test_adjustamattress_nframes_round_trip_through_codec():
    """AdjustaMattress's lifts and P3/P4 frames (row067 fixture) are Okin N-frames.

    Only the P4 anti-snore (``05 0B``) and sleep (``01 B5``) frames have no builder.
    """
    rows = json.loads(
        (Path(__file__).parent / "fixtures/adjustamattress/commands.json").read_text()
    )
    literals = {
        bytes.fromhex(row["expected_bytes"])
        for row in rows
        if row["expected_bytes"] != "NO WRITE" and row["expected_bytes"][0] in "0"
    }
    rebuilt = {data for data in literals if _rebuild(data) == data}
    assert {data[:2].hex() for data in literals - rebuilt} == {"050b", "01b5"}
    shapes = {"0502", "0602", "0704", "0705", "0805", "00b0", "00c0"}
    assert {data[:2].hex() for data in rebuilt} == shapes


def test_gateway_routes_wrap_every_legacy_word():
    words = {
        codec.word_of(bytes.fromhex(f)) for k in ("okimat", "dewertokin") for f in FROZEN_FRAMES[k]
    }
    assert {codec.gateway_frame(word).hex() for word in words} == GATEWAY_FRAMES


@pytest.mark.parametrize("key", sorted(profiles.LEGGETT_PROFILES))
def test_settings_initialization_is_frozen(key):
    profile = profiles.LEGGETT_PROFILES[key]
    expected = {codec.SETTINGS_INIT.hex()} if profile.control_mode else set()
    assert set(SETUP_FRAMES.get(key, ())) == expected


@pytest.mark.parametrize(
    ("key", "minutes", "action", "frame"),
    [
        ("prodigy2l", 30, 3, "0402ff02001e"),
        ("prodigy4", 90, 1, "0402ff00005a"),
        ("prodigy4", 90, 4, "0402ff03005a"),
    ],
)
def test_prodigy_sleep_timer_is_a_frozen_plain_frame(key, minutes, action, frame):
    word, plain = profiles.leggett_sleep_timer(profiles.LEGGETT_PROFILES[key], minutes, action)
    assert plain
    assert codec.frame(word).hex() == frame
    assert frame in FROZEN_FRAMES[key]


def test_40_bit_frames_carry_the_key_then_the_selector():
    assert codec.frame40(0x08000000, 0xAA).hex() == "050208000000aa"
    for key, selector in ((1 << 32, 0), (-1, 0), (True, 0), (1, 0x100)):
        with pytest.raises(ValueError):
            codec.frame40(key, selector)


def test_96_bit_frames_carry_two_fields_then_zero_padding():
    assert codec.frame96(0x1, 0x40).hex() == "0c02" + "00000001" + "00000040" + "00000000"
    assert codec.frame96(0x1) == codec.frame(profiles.cst_word(0x1), 12)
    for primary, secondary in ((1 << 32, 0), (0, -1), (True, 0)):
        with pytest.raises(ValueError):
            codec.frame96(primary, secondary)


def test_frame_widths_and_word_ranges():
    assert codec.frame(1, 5).hex() == "05020000000001"
    assert codec.frame(1, 12).hex() == "0c02" + "00" * 11 + "01"
    for word, width in ((1 << 32, 4), (-1, 4), (True, 4), (1, 7)):
        with pytest.raises(ValueError):
            codec.frame(word, width)
    with pytest.raises(ValueError):
        codec.word_of(bytes.fromhex("05020000000001"))


HOLD_PROFILES = sorted(key for key, profile in PROFILES.items() if profile.execution.hold)


def test_hold_declarations_follow_the_evidence_matrix():
    """Stream-supported rows only; DewertOkin, CB24, DOT, 64-bit and SleepEase are blocked."""
    assert set(HOLD_PROFILES) == {
        profiles.OKIN_MOTIONBED.key,
        *APEX_PROFILES,
        profiles.RESIDENT.key,
        *profiles.LEGGETT_PROFILES,
        *profiles.CUSTOMATIC_PROFILES,
        *(p.key for p in profiles.CST_PROFILES.values()),
        *(p.key for p in profiles.BEDDING_PROFILES.values()),
        *(p.key for p in profiles.SIMMONS_PROFILES.values()),
        *(p.key for p in profiles.STARCODE_ABM5_4_PROFILES.values()),
        *(p.key for p in profiles.ADJUSTABLE_LUMBAR_PROFILES.values()),
        *profiles.ESHINE_PROFILES,
    }


@pytest.mark.parametrize("key", HOLD_PROFILES)
def test_held_and_release_frames_are_frozen(key):
    """A renewable hold streams only frozen key frames, then the frozen release."""
    profile = PROFILES[key]
    frozen = FROZEN_FRAMES[key] | FIELD_FRAMES.get(key, frozenset())
    # Every key, motors included, framed as this route frames it, and the zero
    # release word wherever the profile releases with STOP frames.
    assert _census(profile) <= frozen
    if profile.envelope == "revision_selector":
        words = {profile.keys[f"{a}_{d}"] for a in profile.axes for d in ("up", "down")} | {0}
        assert {codec.gateway_frame(word).hex() for word in words} <= frozen


def test_composed_chords_partial_release_and_zero_are_frozen():
    """#516: each concurrent profile's representative composed, reduced and release frames."""
    prodigy = profiles.LEGGETT_PROFILES["prodigy4"]
    chord = prodigy.keys["head_up"] | prodigy.keys["feet_up"]
    assert {codec.frame(chord).hex(), codec.gateway_frame(chord).hex()} <= COMPOSED_FRAMES[
        "prodigy4"
    ]
    for key in ("prodigy4", "useries"):
        profile = profiles.LEGGETT_PROFILES[key]
        assert codec.frame(profile.keys["head_up"]).hex() in FROZEN_FRAMES[key]
        assert codec.STOP.hex() in FROZEN_FRAMES[key]
    # Customatic's reports freeze the back-and-legs chord (and Remedy's with
    # lumbar) as literals; a reduced mask is a frozen single key.
    for key, customatic in profiles.CUSTOMATIC_PROFILES.items():
        keys = customatic.keys
        chord = 0
        for axis in customatic.axes:
            chord |= keys[f"{axis}_up"]
            assert codec.frame(keys[f"{axis}_up"]).hex() in FROZEN_FRAMES[key]
        assert {
            codec.frame(keys["back_up"] | keys["legs_up"]).hex(),
            codec.frame(chord).hex(),
            codec.STOP.hex(),
        } <= FROZEN_FRAMES[key]
    assert {key for key, profile in PROFILES.items() if profile.execution.concurrent} == {
        "prodigy4",
        "useries",
        *profiles.CUSTOMATIC_PROFILES,
    }
