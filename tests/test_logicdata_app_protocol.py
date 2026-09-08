"""MOTIONrelax cluster-006 literal vectors and phone/tablet divergences."""

from datetime import datetime

import pytest

from custom_components.adjustable_bed import logicdata_app_protocol as protocol


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
    assert protocol.motion_command("p1", layout, axis, up).hex() == expected


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
    assert protocol.motion_command("p2", "middle", axis, up).hex() == expected
    assert protocol.release_schedule("movement", "p2", "phone") == (
        (100, bytes.fromhex("f1f14e004e7e")),
    )


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
        protocol.motion_command(family, layout, axis, True)


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
    assert protocol.preset_command(family, preset).hex() == expected


@pytest.mark.parametrize("preset", ["zero_g", "anti_snore"])
def test_p2_does_not_expose_p1_presets(preset):
    with pytest.raises(ValueError, match="only the flat"):
        protocol.preset_command("p2", preset)


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
    assert protocol.memory_command("p1", slot, save).hex() == p1
    assert protocol.memory_command("p2", slot, save).hex() == p2


def test_no_dead_memory_c_or_unreachable_intensity():
    with pytest.raises(ValueError, match="memory slot"):
        protocol.memory_command("p1", 3)
    with pytest.raises(ValueError, match="massage level"):
        protocol.massage_command("back", 4)


@pytest.mark.parametrize(
    ("zone", "low", "high"),
    [
        ("back", "f1f1120208021e7e", "f1f112020804207e"),
        ("right", "f1f1220208022e7e", "f1f122020804307e"),
        ("legs", "f1f114020802207e", "f1f114020804227e"),
    ],
)
def test_ui_massage_level_mapping(zone, low, high):
    assert protocol.massage_command(zone, 1).hex() == low
    assert protocol.massage_command(zone, 3).hex() == high


def test_profile_specific_startup_queries():
    for family, hardware in [("p1", "f1f1000140417e"), ("p2", "f1f100024000427e")]:
        for profile, actuator in [("phone", "f1f1000150517e"), ("tablet", "f1f1000101027e")]:
            assert [(t, data.hex()) for t, data in protocol.startup_schedule(profile, family)] == [
                (1000, actuator),
                (1100, actuator),
                (1200, hardware),
                (1300, hardware),
                (1400, "f1f1000108097e"),
                (1500, "f1f1000108097e"),
            ]


def test_massage_and_light_cleanup_are_not_the_dreamotion_schedule():
    assert protocol.MASSAGE_MODE.hex() == "f1f116010a217e"
    assert protocol.MASSAGE_STOP.hex() == "f1f11101081a7e"
    assert protocol.release_schedule("massage_mode", "p1", "tablet") == ()
    assert [(t, b.hex()) for t, b in protocol.release_schedule("massage_mode", "p1", "phone")] == [
        (1000, "f1f14e020000507e"),
        (1100, "f1f14e004e7e"),
    ]
    assert protocol.light_command("p1").hex() == "f1f10f000f7e"
    assert protocol.light_command("p2").hex() == "f1f10f020000117e"
    for profile in protocol.APP_PROFILES:
        assert [(t, b.hex()) for t, b in protocol.release_schedule("light", "p2", profile)] == [
            (80, "f1f14e004e7e"),
            (80, "f1f14e020000507e"),
            (100, "f1f14e004e7e"),
        ]
        # Android omits click cleanup; HA retains the proven P2 held-flat release.
        assert protocol.release_schedule("flat", "p2", profile) == ((100, protocol.P1_RELEASE),)
        assert protocol.release_schedule("memory", "p2", profile) == ((100, protocol.P1_RELEASE),)


def test_phone_clock_and_alarm_frozen_vectors():
    assert (
        protocol.clock_command(datetime(2026, 8, 27, 16, 17, 18)).hex()
        == "f1f1500738081b04101112e97e"
    )
    assert (
        protocol.alarm_command(
            True, (True, False, True, False, True, False, False), 6, 30, "memory_1", 2, 3
        ).hex()
        == "f1f1510801012a061e030203b17e"
    )
    with pytest.raises(ValueError, match="Weekdays"):
        protocol.alarm_command(True, (True,), 6, 30, "flat", 0, 0)
    with pytest.raises(ValueError, match="hour"):
        protocol.alarm_command(True, (False,) * 7, 24, 0, "flat", 0, 0)


def test_rename_profiles_and_safe_ascii_subset():
    assert protocol.rename_schedule("phone", "t3", "BED") == ((0, bytes.fromhex("01fc0703424544")),)
    assert protocol.rename_schedule("tablet", "t3", "BED") == (
        (0, bytes.fromhex("01fc0703424544")),
        (500, bytes.fromhex("01fc0703424544")),
    )
    assert protocol.rename_schedule("tablet", "t1", "BED") == ((0, b"BED"), (500, b"BED"))
    assert protocol.rename_command("phone", "t1", "Bedroom 1") == b"Bedroom 1"
    for name in ("", "Béd", "\x01BED", "A" * 256):
        with pytest.raises(ValueError, match="printable ASCII"):
            protocol.rename_command("tablet", "t3", name)
    with pytest.raises(ValueError, match="no rename"):
        protocol.rename_command("phone", "t2", "BED")


@pytest.mark.parametrize("profile", protocol.APP_PROFILES)
def test_selector_and_status_parser_without_speculative_checksum(profile):
    assert protocol.parse_notification(
        profile, bytes.fromhex("f2f2110001")
    ) == protocol.Notification(middle=True)
    assert protocol.parse_notification(
        profile, bytes.fromhex("f2f21100ff")
    ) == protocol.Notification(middle=False)
    assert protocol.parse_notification(profile, bytes.fromhex("f2f20f00000000")).hardware_ack
    assert protocol.parse_notification(
        profile, bytes.fromhex("aaaa06000400030040")
    ) == protocol.Notification(
        massage_back=4,
        massage_legs=3,
        light_on=True,
    )
    assert protocol.parse_notification(
        profile, bytes.fromhex("aaaa05000000000000")
    ) == protocol.Notification(light_on=False)
    for sample, minimum in [("f2f2110001", 5), ("f2f20f00000000", 7), ("aaaa06000400030040", 9)]:
        for length in range(minimum):
            assert protocol.parse_notification(profile, bytes.fromhex(sample)[:length]) is None


def test_tablet_has_no_clock_or_alarm_parser_and_phone_requires_full_alarm():
    clock = bytes.fromhex("f2f250000000")
    alarm = bytes.fromhex("f2f2510801012a061e030203b17e")
    assert protocol.parse_notification("tablet", clock) is None
    assert protocol.parse_notification("tablet", alarm) is None
    assert protocol.parse_notification("phone", clock).clock_requested
    assert protocol.parse_notification("phone", alarm).alarm == protocol.AlarmState(
        True,
        (True, False, True, False, True, False, False),
        6,
        30,
        "memory_1",
        2,
        3,
    )
    for length in range(14):
        assert protocol.parse_notification("phone", alarm[:length]) is None
    assert protocol.parse_notification("phone", alarm[:-2] + b"\xff\x00").alarm is not None
