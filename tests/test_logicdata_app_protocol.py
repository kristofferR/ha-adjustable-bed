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
        ("standard_2", "back", True, "f1f1010101037e"),
        ("standard_2", "back", False, "f1f1020101047e"),
        ("standard_2", "legs", True, "f1f1030101057e"),
        ("standard_2", "legs", False, "f1f1040101067e"),
        ("standard_2", "both", True, "f1f1050101077e"),
        ("standard_2", "both", False, "f1f1060101087e"),
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
    ("axis", "up", "expected"),
    [
        ("back", True, "f1f101020000037e"),
        ("back", False, "f1f102020000047e"),
        ("legs", True, "f1f103020000057e"),
        ("legs", False, "f1f104020000067e"),
    ],
)
def test_p2_motion_still_uses_p1_touch_release(axis, up, expected):
    assert profiles.motion_command(PHONE, "p2", "middle", axis, up).hex() == expected
    assert PHONE.touch_release == ((100, bytes.fromhex("f1f14e004e7e")),)


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


@pytest.mark.parametrize(
    ("family", "preset", "expected"),
    [
        ("p1", "flat", "f1f10801010a7e"),
        ("p1", "zero_g", "f1f1070101097e"),
        ("p1", "anti_snore", "f1f10901010b7e"),
        ("p2", "flat", "f1f1080200000a7e"),
    ],
)
def test_reachable_presets(family, preset, expected):
    assert profiles.preset_command(PHONE, family, preset).hex() == expected


@pytest.mark.parametrize("preset", ["zero_g", "anti_snore"])
def test_p2_does_not_expose_p1_presets(preset):
    with pytest.raises(ValueError, match="only the flat"):
        profiles.preset_command(PHONE, "p2", preset)


@pytest.mark.parametrize(
    ("slot", "save", "p1", "p2"),
    [
        (1, True, "f1f10a01010c7e", "f1f10a0200000c7e"),
        (1, False, "f1f10b01010d7e", "f1f10b0200000d7e"),
        (2, True, "f1f10c01010e7e", "f1f10c0200000e7e"),
        (2, False, "f1f10d01010f7e", "f1f10d0200000f7e"),
    ],
)
def test_memory_family_vectors_including_corrected_tablet_save_rows(slot, save, p1, p2):
    for profile in (PHONE, TABLET):
        for family, expected in (("p1", p1), ("p2", p2)):
            if save:
                schedule = profiles.memory_save_schedule(profile, family, slot)
                assert [(t, c.hex()) for t, c in schedule] == [(t, expected) for t in (0, 30, 60)]
            else:
                assert profiles.memory_command(profile, family, slot).hex() == expected


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
        ("back", "f1f1120208021e7e", "f1f112020804207e"),
        ("right", "f1f1220208022e7e", "f1f122020804307e"),
        ("legs", "f1f114020802207e", "f1f114020804227e"),
    ],
)
def test_ui_massage_level_mapping(zone, low, high):
    assert profiles.massage_command(zone, 1).hex() == low
    assert profiles.massage_command(zone, 3).hex() == high


def test_profile_specific_startup_queries():
    for family, hardware in [("p1", "f1f1000140417e"), ("p2", "f1f100024000427e")]:
        for profile, actuator in [(PHONE, "f1f1000150517e"), (TABLET, "f1f1000101027e")]:
            assert [(t, data.hex()) for t, data in profile.startup[family]] == [
                (1000, actuator),
                (1100, actuator),
                (1200, hardware),
                (1300, hardware),
                (1400, "f1f1000108097e"),
                (1500, "f1f1000108097e"),
            ]


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
