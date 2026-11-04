"""Every 32-bit Okin N-frame profile's frozen frames pass through the shared codec."""

from __future__ import annotations

from dataclasses import fields

import pytest

from custom_components.adjustable_bed.beds.okin_uuid import (
    OKIN_UUID_REMOTES,
    OkinUuidComplexCommand,
)
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.profiles import okin_nframe as profiles
from tests.okin_nframe_vectors import FIELD_FRAMES, FROZEN_FRAMES, GATEWAY_FRAMES, SETUP_FRAMES

PROFILES: dict[str, profiles.OkinNFrameProfile] = {
    profile.key: profile
    for profile in (
        profiles.OKIMAT,
        profiles.DEWERTOKIN,
        profiles.RF_ECO_BT,
        *profiles.CUSTOMATIC_PROFILES.values(),
        *profiles.LEGGETT_PROFILES.values(),
    )
}
# Routes without a report: their census must equal the pre-v5 frames.
LEGACY = {"okimat", "dewertokin", "okin_rf_eco_bt"}


def _remote_words() -> set[int]:
    """Every key word an Okimat handset table can send."""
    words: set[int] = set()
    for remote in OKIN_UUID_REMOTES.values():
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
    words = set(profile.keys.values()) if profile.keys else _remote_words()
    if profile.hold.releases or profile.recall and profile.recall.releases:
        words.add(0)
    frames = {codec.frame(word).hex() for word in words}
    if profile.envelope == "revision_selector":
        frames |= {codec.gateway_frame(word).hex() for word in words}
    return frames


@pytest.mark.parametrize(
    ("profile", "literal"),
    [
        (profile, literal)
        for profile, frames in FROZEN_FRAMES.items()
        for literal in sorted(frames | FIELD_FRAMES.get(profile, frozenset()))
    ],
)
def test_frozen_frame_round_trips_through_codec(profile, literal):
    data = bytes.fromhex(literal)
    if data[:3] == codec.GATEWAY_HEADER:
        assert codec.gateway_frame(int.from_bytes(data[3:7], "big")) == data
    else:
        assert codec.frame(int.from_bytes(data[2:], "big"), data[0]) == data


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_only_frozen_frames(key):
    census = _census(PROFILES[key])
    assert census <= FROZEN_FRAMES[key] | FIELD_FRAMES.get(key, frozenset())
    if key in LEGACY:
        assert census == FROZEN_FRAMES[key]


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


def test_frame_widths_and_word_ranges():
    assert codec.frame(1, 5).hex() == "05020000000001"
    assert codec.frame(1, 12).hex() == "0c02" + "00" * 11 + "01"
    for word, width in ((1 << 32, 4), (-1, 4), (True, 4), (1, 7)):
        with pytest.raises(ValueError):
            codec.frame(word, width)
    with pytest.raises(ValueError):
        codec.word_of(bytes.fromhex("05020000000001"))
