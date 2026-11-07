"""Every Richmat profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed import cluster018_protocol as classic
from custom_components.adjustable_bed import hjbed_protocol as hj
from custom_components.adjustable_bed.beds import richmat_mh as mh_bed
from custom_components.adjustable_bed.beds import richmat_mh_protocol as mh
from custom_components.adjustable_bed.beds import row061
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.hjbed_catalog import ACTIONS
from custom_components.adjustable_bed.profiles import richmat as profiles
from tests.richmat_vectors import FROZEN_FRAMES

FIXED_ROUTES = {
    **{profile.key: profile for profile in profiles.RICHMAT.values()},
    "bedtech": profiles.BEDTECH,
    "leggett_wilinke": profiles.LEGGETT_WILINKE,
}
PROFILES = {
    **FIXED_ROUTES,
    "hjbed": profiles.HJBED,
    **{profile.key: profile for profile in profiles.RICHMAT_MH.values()},
    **{profile.key: profile for profile in profiles.RICHMAT_CLASSIC.values()},
}


def _decode(data: bytes) -> bytes:
    """Rebuild a literal through the codec encoder its layout names."""
    if len(data) == 1:
        return codec.encode("nordic", data[0])
    if data[0] == 0x04:
        return codec.strip(data[2], data[5:-3])
    if len(data) == 5 and data[1] == 0x01 and data[0] in (0x6E, 0x55, 0xAA):
        return codec.command(data[3], data[2], header=data[0])
    if data[0] == codec.BED and data[1] == len(data) and data[2] == 0x20:
        return codec.record(data[3], data[4], data[5], data[6:-1])
    return codec.frame(*data[:-1])


def _fixed_census(profile: profiles.RichmatProfile) -> set[str]:
    codes = {*(profile.codes or {}).values(), *(c for slot in profile.memory for c in slot)}
    frames = {profile.frame(code).hex() for code in {*codes, profile.stop}}
    if profile is profiles.RICHMAT["wilinke"]:
        # Compatibility STOP, GGRM catalog taps and both light packet families.
        frames |= {
            profile.frame(code).hex() for code in (codec.COMPAT_STOP, *profiles.GGRM_ACTIONS)
        }
        frames |= {codec.strip(0x04, bytes((on,))).hex() for on in (0x00, 0x02)}
        frames |= {codec.strip(0x02, minutes.to_bytes(2, "big")).hex() for minutes in range(31)}
        frames |= {codec.frame(codec.BED, 0x0A, 0x00, 0x01).hex()}
        frames |= {codec.light_timer(*divmod(s, 256)).hex() for s in range(0, 301, 60)}
    return frames


# Row061 session frames beyond the MH queries: the VER2 init, the music query
# and the calendar alarm query, per app as Row061Controller sends them.
_CALENDAR_QUERY = "6e2008050100009c"
_ROW061_QUERIES: dict[str, set[str]] = {
    "ruf": {*row061.INIT_VER2, row061.MUSIC_QUERY},
    "wsilver2": {row061.MUSIC_QUERY, _CALENDAR_QUERY},
    "americanstar": {*row061.INIT_VER2, row061.MUSIC_QUERY, _CALENDAR_QUERY},
    "bailey2": {*row061.INIT_VER2, row061.MUSIC_QUERY, _CALENDAR_QUERY},
    "tx": {_CALENDAR_QUERY},
}


def _mh_census(app: str) -> set[str]:
    queries = {*mh.INIT_VER0, *mh.INIT_VER1, mh.TX_VERSION, mh.TX_SPEECH, *mh.TX_ALARM_CANCEL}
    queries |= _ROW061_QUERIES.get(app, set())
    queries |= {mh.TX_START_DETECTION, mh.TX_STOP_DETECTION}
    codes = {
        mh.BTN_LED_OFF_CODE,
        mh.SMART_SET_LOCK_CODE,
        mh_bed.FLAT_CODE,
        mh_bed.LIGHT_TOGGLE_CODE,
    }
    for model_id in mh_bed.selectable_models(app):
        model = mh_bed.load_model(app, model_id)
        assert model is not None
        codes |= {control.code for control in model.controls}
    return (
        {mh.stop_frame().hex()}
        | {mh.query_frame(query).hex() for query in queries}
        | {mh.control_frame(code).hex() for code in codes}
    )


def _hjbed_census() -> set[str]:
    frames = {hj.control_mode(mode).hex() for mode in (None, 0, 2)}
    frames |= {hj.function("deviceFunctionItemExitLimit", 0, 0, False).hex()}
    frames |= {hj.query_alarms().hex(), *(frame.hex() for frame in hj.clock(0, 0))}
    for enum in ("Clock", "Light", "Music"):
        frames.add(hj.function(f"deviceFunctionItemCheck{enum}", 1, 0, False).hex())
    for side in (0, 1):
        frames.add(hj.function("deviceFunctionItemStop", codec.STOP, side, False).hex())
        for action in ACTIONS.values():
            for code in (action.code, action.save_code):
                if code is not None:
                    frames.add(hj.function(action.enum, code, side, False).hex())
    return frames


def _classic_census() -> set[str]:
    """The classic apps' fixed frames, in mode 0.

    Catalog controls are data: each is ``codec.command(operand, mode)`` for an
    operand and mode its layout ships. The accepted reports freeze 127 of the 206
    operand and mode pairs, so the census covers the frames no catalog selects.
    """
    frames = {classic.release("RAW"), classic.release("FRAMED"), *classic.alarm(0, 0)}
    frames |= {
        classic.INITIALIZE,
        classic.DESK_QUERY,
        classic.ALARM_QUERY,
        classic.LAMP_QUERY,
        classic.AROMA_QUERY,
        classic.lamp_timer(0),
    }
    frames |= {classic.massage_popup(choice) for choice in classic.MASSAGE_POPUP}
    frames |= {classic.desk_unit(inches) for inches in (False, True)}
    frames |= {classic.desk_button(slot) for slot in (1, 2, 3, 4)}
    frames |= {
        classic.massage_timer(layout, progress)
        for layout in ("D1RM", "D9RM")
        for progress in range(6)
    }
    return {frame.hex() for frame in frames}


def _census(key: str) -> set[str]:
    if key == "hjbed":
        return _hjbed_census()
    if key.startswith("richmat_classic_"):
        return _classic_census()
    if key.startswith("richmat_mh_"):
        return _mh_census(key.removeprefix("richmat_mh_"))
    return _fixed_census(PROFILES[key])


@pytest.mark.parametrize(
    ("key", "literal"),
    [(key, literal) for key, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(key: str, literal: str) -> None:
    data = bytes.fromhex(literal)
    assert _decode(data) == data
    if len(data) > 1:
        assert codec.is_valid(data)


def test_every_profile_has_vectors() -> None:
    assert set(PROFILES) == set(FROZEN_FRAMES)
    assert all(profile.key == key for key, profile in PROFILES.items())


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_only_frozen_frames(key: str) -> None:
    census = _census(key)
    assert census <= FROZEN_FRAMES[key]
    if key in FIXED_ROUTES:
        # Without a report, the pre-v5 controller's frames are the complete vector set.
        assert census == FROZEN_FRAMES[key]
