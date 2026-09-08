"""Frozen cluster-004 vectors and reachable-layout boundaries."""

from datetime import datetime

import pytest

from custom_components.adjustable_bed import jiecang_app_protocol as protocol


@pytest.mark.parametrize(
    ("axis", "up", "standard", "bilateral"),
    [
        ("back", True, "f1f1010101037e", "f1f101020000037e"),
        ("back", False, "f1f1020101047e", "f1f102020000047e"),
        ("legs", True, "f1f1030101057e", "f1f103020000057e"),
        ("legs", False, "f1f1040101067e", "f1f104020000067e"),
        ("right_back", True, "f1f1200101227e", "f1f120020000227e"),
        ("right_back", False, "f1f1210101237e", "f1f121020000237e"),
        ("both_backs", True, "f1f1230101257e", "f1f123020000257e"),
        ("both_backs", False, "f1f1240101267e", "f1f124020000267e"),
    ],
)
def test_standard_bilateral_and_mixed_motion(axis, up, standard, bilateral):
    assert protocol.motion_command("split_series", axis, up).hex() == standard
    assert protocol.motion_command("split_after_bilateral", axis, up).hex() == standard
    assert protocol.motion_command("standard_4_bilateral", axis, up).hex() == bilateral


@pytest.mark.parametrize(
    ("layout", "axis", "up", "expected"),
    [
        ("standard_2", "both", True, "f1f1050101077e"),
        ("standard_2", "both", False, "f1f1060101087e"),
        ("standard_3_neck", "head", True, "f1f11901011b7e"),
        ("standard_3_neck", "head", False, "f1f11a01011c7e"),
        ("standard_3_hi_low", "bed_height", True, "f1f11901011b7e"),
        ("standard_3_hi_low", "bed_height", False, "f1f11a01011c7e"),
        ("standard_3_lumbar", "lumbar", True, "f1f11b01011d7e"),
        ("standard_3_lumbar", "lumbar", False, "f1f11c01011e7e"),
        ("standard_4_legacy", "head", True, "f1f11901011b7e"),
        ("standard_4_legacy", "lumbar", False, "f1f11c01011e7e"),
        ("standard_3_split_upper", "right_back", True, "f1f1200101227e"),
        ("standard_4_bilateral", "right_legs", True, "f1f12a0200002c7e"),
        ("standard_4_bilateral", "right_legs", False, "f1f12b0200002d7e"),
        ("standard_4_bilateral", "both_legs", True, "f1f12c0200002e7e"),
        ("standard_4_bilateral", "both_legs", False, "f1f12d0200002f7e"),
    ],
)
def test_auxiliary_and_bilateral_axis_vectors(layout, axis, up, expected):
    assert protocol.motion_command(layout, axis, up).hex() == expected


def test_unavailable_axis_is_not_inferred_from_motor_count():
    with pytest.raises(ValueError, match="unavailable"):
        protocol.motion_command("standard_3_lumbar", "head", True)


@pytest.mark.parametrize(
    ("preset", "standard", "bilateral"),
    [
        ("zero_g", "f1f1070101097e", "f1f107020000097e"),
        ("flat", "f1f10801010a7e", "f1f1080200000a7e"),
        ("anti_snore", "f1f10901010b7e", "f1f1090200000b7e"),
        ("yoga", "f1f1280200002a7e", "f1f1280200002a7e"),
    ],
)
def test_mixed_layout_keeps_bilateral_global_controls(preset, standard, bilateral):
    assert protocol.preset_command("split_series", preset).hex() == standard
    assert protocol.preset_command("split_after_bilateral", preset).hex() == bilateral
    assert protocol.preset_command("standard_4_bilateral", preset).hex() == bilateral


@pytest.mark.parametrize(
    ("slot", "save", "expected"),
    [
        (1, True, "f1f10a0200000c7e"),
        (1, False, "f1f10b0200000d7e"),
        (2, True, "f1f10c0200000e7e"),
        (2, False, "f1f10d0200000f7e"),
    ],
)
def test_memory_vectors(slot, save, expected):
    assert protocol.memory_command(slot, save).hex() == expected


def test_memory_c_is_not_reachable():
    with pytest.raises(ValueError, match="memory slot"):
        protocol.memory_command(3)


@pytest.mark.parametrize(
    ("layout", "zone", "expected"),
    [
        ("standard_2", "back", "f1f112020804207e"),
        ("standard_2", "legs", "f1f114020804227e"),
        ("split_series", "right", "f1f122020804307e"),
        ("standard_4_bilateral", "back", "f1f112020004187e"),
        ("split_after_bilateral", "right", "f1f122020004287e"),
    ],
)
def test_maximum_reachable_massage_level(layout, zone, expected):
    assert protocol.massage_command(layout, zone, 3).hex() == expected


def test_massage_low_is_wire_two_and_invalid_levels_are_rejected():
    assert protocol.massage_command("standard_2", "back", 1).hex() == "f1f1120208021e7e"
    assert protocol.massage_command("standard_2", "back", 0).hex() == "f1f1120208001c7e"
    with pytest.raises(ValueError, match="massage level"):
        protocol.massage_command("standard_2", "back", 4)
    with pytest.raises(ValueError, match="unavailable"):
        protocol.massage_command("standard_4_bilateral", "legs", 2)
    assert protocol.massage_mode_command("standard_2").hex() == "f1f116010a217e"
    assert protocol.massage_close_command("standard_2").hex() == "f1f11101081a7e"
    assert protocol.massage_mode_command("split_after_bilateral").hex() == "f1f116020000187e"
    assert protocol.massage_close_command("split_after_bilateral").hex() == "f1f111020000137e"


def test_dynamic_and_auxiliary_packet_vectors():
    assert protocol.rgb_command(17, 34, 51, 100, 300, True).hex() == "f1f1520733221164012c01517e"
    assert (
        protocol.alarm_command(
            True, (True, False, True, False, True, False, False), 6, 30, "memory_1", 2, 3
        ).hex()
        == "f1f1510801012a061e030203b17e"
    )
    assert (
        protocol.clock_command(datetime(2026, 8, 27, 12, 34, 56)).hex()
        == "f1f1500738081b040c22381c7e"
    )
    assert protocol.rename_command("Bed1", True, True) == b"Bed1"
    assert protocol.rename_command("Bed1", False, True).hex() == "01fc070442656431"
    assert protocol.LIGHT_TOGGLE.hex() == "f1f10f020000117e"
    assert protocol.AUTOMATIC_LIGHT_TOGGLE.hex() == "f1f1290200002b7e"
    assert [data.hex() for _, data in protocol.BOOTSTRAP_SCHEDULE[::2]] == [
        "f1f100024000427e",
        "f1f100020100037e",
        "f1f1000150517e",
        "f1f1000140417e",
        "f1f1000108097e",
        "f1f1000110117e",
        "f1f100024000427e",
    ]
    assert [offset for offset, _ in protocol.BOOTSTRAP_SCHEDULE] == [
        0,
        100,
        800,
        900,
        1000,
        1100,
        1200,
        1300,
        1400,
        1500,
        1600,
        1700,
        1800,
        1900,
    ]


@pytest.mark.parametrize("name", ["", "Bed 1", "Béd", "A" * 21])
def test_rename_ui_validation(name):
    with pytest.raises(ValueError, match="ASCII"):
        protocol.rename_command(name, True, False)


def test_light_ui_limits_not_unreachable_formula_limits():
    with pytest.raises(ValueError, match="brightness"):
        protocol.rgb_command(0, 0, 0, 101, 0, False)
    with pytest.raises(ValueError, match="timeout"):
        protocol.rgb_command(0, 0, 0, 100, 65535, True)


def test_profile_specific_release_schedules():
    assert [(t, b.hex()) for t, b in protocol.movement_releases("dreamask")] == [
        (50, "f1f14e020000507e"),
        (150, "f1f14e020000507e"),
    ]
    assert [(t, b.hex()) for t, b in protocol.movement_releases("dreamotion")] == [
        (100, "f1f14e004e7e"),
        (800, "f1f14e020000507e"),
    ]


def test_split_wake_massage_uses_standard_payload_and_exact_schedules():
    schedule = protocol.wake_schedule("split_after_bilateral", "flat", 3, 2)
    assert [(t, b.hex()) for t, b in schedule if b[2] == 0x22] == [
        (180, "f1f122020804307e"),
        (210, "f1f122020804307e"),
        (240, "f1f122020804307e"),
    ]
    assert [t for t, b in schedule if b == protocol.SHORT_RELEASE] == [
        90,
        120,
        150,
        270,
        300,
        330,
        590,
        620,
        650,
    ]
    assert [t for t, b in schedule if b[2] == 0x08] == [800, 830, 860, 890, 920]
    assert [t for t, b in schedule if b == protocol.LONG_RELEASE] == [1690, 1720]
    standard = protocol.wake_schedule("standard_4_bilateral", "memory_2", 2, 1)
    assert [t for t, b in standard if b == protocol.LONG_RELEASE] == [1600, 1690, 1720]
    assert [t for t, b in standard if b[2] == 0x14] == [300, 330, 360]
    with pytest.raises(ValueError, match="Yoga"):
        protocol.wake_schedule("standard_2", "yoga")


def test_notification_fields_and_partial_alarm():
    def parse(hex_value):
        return protocol.parse_notification(bytes.fromhex(hex_value))

    assert parse("f2f250000000").clock_requested
    assert parse("f2f20e00070000").capabilities == protocol.Capabilities(True, True)
    assert parse("f2f20f00000000").reapply_layout
    assert parse("f2f25100000000") == protocol.Notification(alarm_visible=True)
    alarm = parse("f2f2510801012a061e030203b17e").alarm
    assert alarm == protocol.AlarmState(
        True, (True, False, True, False, True, False, False), 6, 30, "memory_1", 2, 3
    )
    assert parse("f2f25300000000").automatic_light is True
    assert parse("f2f25300ff0000").automatic_light is False
    assert parse("f2f2520733221164012c01517e").rgb == protocol.RGBState(17, 34, 51, 100, 300, True)
    # The artifact has no checksum/trailer check, including these valid field values.
    assert parse("f2f2520733221164012c01ffff").rgb == protocol.RGBState(17, 34, 51, 100, 300, True)
    assert parse("aaaa06000400030040") == protocol.Notification(
        massage_back=4,
        massage_legs=3,
        legacy_light=True,
    )
    assert parse("123405000000000040") == protocol.Notification(legacy_light=True)


def test_truncated_notifications_never_read_fields_out_of_bounds():
    for sample, minimum in [
        ("f2f250000000", 6),
        ("f2f20e00070000", 7),
        ("f2f2520733221164012c01517e", 13),
        ("aaaa06000400030040", 9),
    ]:
        data = bytes.fromhex(sample)
        for length in range(minimum):
            assert protocol.parse_notification(data[:length]) is None
    assert protocol.parse_notification(bytes.fromhex("f2f25207332211ff012c01517e")) is None


@pytest.mark.parametrize("length", range(7, 14))
def test_partial_alarm_never_overwrites_configuration(length):
    data = bytes.fromhex("f2f2510801012a061e030203b17e")[:length]
    assert protocol.parse_notification(data) == protocol.Notification(alarm_visible=True)


def test_split_alarm_right_is_derived_from_back_not_an_independent_channel():
    schedule = protocol.wake_schedule("split_series", "flat", 2, 0)
    assert [command.hex() for _, command in schedule if command[2] == 0x22] == [
        "f1f1220208032f7e",
    ] * 3
    with pytest.raises(ValueError, match="match the back"):
        protocol.wake_schedule("split_series", "flat", 2, 0, 3)
