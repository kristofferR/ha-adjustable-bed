"""MOTIONrelax cluster-006 literal vectors and phone/tablet divergences."""

from datetime import datetime

import pytest

from custom_components.adjustable_bed.codec import jiecang as codec
from custom_components.adjustable_bed.profiles import logicdata as profiles
from custom_components.adjustable_bed.profiles.logicdata import PHONE, TABLET

P1_RELEASE = codec.SHORT_RELEASE


@pytest.mark.parametrize(
    ("layout", "axis", "up", "expected"),
    [
        ("standard_3_neck", "head", True, "f1f11901011b7e"),
        ("standard_3_neck", "head", False, "f1f11a01011c7e"),
        ("standard_3_lumbar", "lumbar", True, "f1f11b01011d7e"),
        ("standard_3_lumbar", "lumbar", False, "f1f11c01011e7e"),
        ("standard_3_hi_low", "bed_height", True, "f1f11901011b7e"),
        ("standard_3_hi_low", "bed_height", False, "f1f11a01011c7e"),
        ("split_series", "right_back", True, "f1f1200101227e"),
        ("split_series", "right_back", False, "f1f1210101237e"),
        ("standard_3_split_upper", "both_backs", True, "f1f1230101257e"),
        ("standard_3_split_upper", "both_backs", False, "f1f1240101267e"),
        ("standard_4", "head", True, "f1f11901011b7e"),
        ("standard_4", "lumbar", False, "f1f11c01011e7e"),
    ],
)


def test_p1_motion_vectors(layout, axis, up, expected):
    assert profiles.motion_command(PHONE, "p1", layout, axis, up).hex() == expected


@pytest.mark.parametrize(
    ("family", "layout", "axis"),
    [
        ("p2", "split_series", "back"),
        ("p1", "middle", "back"),
        ("p2", "middle", "both"),
        ("p1", "standard_3_lumbar", "head"),
    ],
)


def test_wrong_family_or_layout_axis_cannot_emit_commands(family, layout, axis):
    with pytest.raises(ValueError):
        profiles.validate_setup(PHONE, family, layout)
        profiles.motion_command(PHONE, family, layout, axis, True)


@pytest.mark.parametrize("preset", ["zero_g", "anti_snore"])
def test_p2_does_not_expose_p1_presets(preset):
    with pytest.raises(ValueError, match="only the flat"):
        profiles.preset_command(PHONE, "p2", preset)


def test_no_dead_memory_c_or_unreachable_intensity():
    with pytest.raises(ValueError, match="memory slot"):
        profiles.memory_command(PHONE, "p1", 3)
    with pytest.raises(ValueError, match="memory slot"):
        profiles.memory_save_schedule(PHONE, "p1", 3)
    with pytest.raises(ValueError, match="massage level"):
        profiles.massage_command("back", 4)


@pytest.mark.parametrize(
    ("zone", "low", "high"),
    [
        ("right", "f1f1220208022e7e", "f1f122020804307e"),
    ],
)


def test_ui_massage_level_mapping(zone, low, high):
    assert profiles.massage_command(zone, 1).hex() == low
    assert profiles.massage_command(zone, 3).hex() == high


def test_massage_and_light_cleanup_are_not_the_dreamotion_schedule():
    assert codec.massage_mode().hex() == "f1f116010a217e"
    assert codec.massage_stop().hex() == "f1f11101081a7e"
    assert TABLET.massage_mode_releases == ()
    assert [(t, b.hex()) for t, b in PHONE.massage_mode_releases] == [
        (1000, "f1f14e020000507e"),
        (1100, "f1f14e004e7e"),
    ]
    assert profiles.light_command(PHONE, "p1").hex() == "f1f10f000f7e"
    assert profiles.light_command(PHONE, "p2").hex() == "f1f10f020000117e"
    for profile in profiles.APP_PROFILES.values():
        assert [(t, b.hex()) for t, b in profile.light_releases] == [
            (80, "f1f14e004e7e"),
            (80, "f1f14e020000507e"),
            (100, "f1f14e004e7e"),
        ]
        # Android omits click cleanup; HA retains the proven P2 held-flat release.
        assert profile.touch_release == ((100, P1_RELEASE),)


def test_phone_clock_and_alarm_frozen_vectors():
    assert codec.clock(datetime(2026, 8, 27, 16, 17, 18)).hex() == "f1f1500738081b04101112e97e"
    assert (
        codec.alarm(
            True, (True, False, True, False, True, False, False), 6, 30, "memory_1", 2, 3
        ).hex()
        == "f1f1510801012a061e030203b17e"
    )
    with pytest.raises(ValueError, match="Weekdays"):
        codec.alarm(True, (True,), 6, 30, "flat", 0, 0)
    with pytest.raises(ValueError, match="hour"):
        codec.alarm(True, (False,) * 7, 24, 0, "flat", 0, 0)


def test_rename_profiles_and_safe_ascii_subset():
    assert profiles.rename_schedule(PHONE, "t3", "BED") == ((0, bytes.fromhex("01fc0703424544")),)
    assert profiles.rename_schedule(TABLET, "t3", "BED") == (
        (0, bytes.fromhex("01fc0703424544")),
        (500, bytes.fromhex("01fc0703424544")),
    )
    assert profiles.rename_schedule(TABLET, "t1", "BED") == ((0, b"BED"), (500, b"BED"))
    assert profiles.rename_schedule(PHONE, "t1", "Bedroom 1") == ((0, b"Bedroom 1"),)
    for name in ("", "Béd", "\x01BED", "A" * 256):
        with pytest.raises(ValueError, match="printable ASCII"):
            profiles.rename_schedule(TABLET, "t3", name)
    with pytest.raises(ValueError, match="no rename"):
        profiles.rename_schedule(PHONE, "t2", "BED")


@pytest.mark.parametrize("profile", [PHONE, TABLET])
def test_selector_and_status_parser_without_speculative_checksum(profile):
    parse = profiles.parse_notification
    assert parse(profile, bytes.fromhex("f2f2110001")) == profiles.Notification(middle=True)
    assert parse(profile, bytes.fromhex("f2f21100ff")) == profiles.Notification(middle=False)
    assert parse(profile, bytes.fromhex("aaaa06000400030040")) == profiles.Notification(
        massage_back=4,
        massage_legs=3,
        light_on=True,
    )
    assert parse(profile, bytes.fromhex("aaaa05000000000000")) == profiles.Notification(
        light_on=False
    )
    for sample, minimum in [("f2f2110001", 5), ("aaaa06000400030040", 9)]:
        for length in range(minimum):
            assert parse(profile, bytes.fromhex(sample)[:length]) is None


def test_tablet_has_no_clock_or_alarm_parser_and_phone_requires_full_alarm():
    clock = bytes.fromhex("f2f250000000")
    alarm = bytes.fromhex("f2f2510801012a061e030203b17e")
    for sample in (clock, alarm):
        result = profiles.parse_notification(TABLET, sample)
        assert result is None or result == profiles.Notification()
    assert profiles.parse_notification(PHONE, clock).clock_requested
    assert profiles.parse_notification(PHONE, alarm).alarm == codec.AlarmState(
        True,
        (True, False, True, False, True, False, False),
        6,
        30,
        "memory_1",
        2,
        3,
    )
    for length in range(14):
        result = profiles.parse_notification(PHONE, alarm[:length])
        assert result is None or result.alarm is None
    assert profiles.parse_notification(PHONE, alarm[:-2] + b"\xff\x00").alarm is not None
    # The apps define no wake for code 6 (the codec's yoga).
    yoga = bytes.fromhex("f2f2510801012a061e060203b17e")
    assert profiles.parse_notification(PHONE, yoga).alarm.wake is None


def test_transports_keep_their_uuids():
    assert {
        key: tuple(vars(transport).values()) for key, transport in profiles.TRANSPORTS.items()
    } == {
        "t1": (
            "0000ff12-0000-1000-8000-00805f9b34fb",
            "0000ff01-0000-1000-8000-00805f9b34fb",
            "0000ff02-0000-1000-8000-00805f9b34fb",
            "0000ff06-0000-1000-8000-00805f9b34fb",
        ),
        "t2": (
            "88121427-11e2-52a2-4615-ff00dec16800",
            "88121427-11e2-52a2-4615-ff00dec16801",
            "88121427-11e2-52a2-4615-ff00dec16801",
            None,
        ),
        "t3": (
            "0000fe60-0000-1000-8000-00805f9b34fb",
            "0000fe61-0000-1000-8000-00805f9b34fb",
            "0000fe62-0000-1000-8000-00805f9b34fb",
            "0000fe63-0000-1000-8000-00805f9b34fb",
        ),
    }
