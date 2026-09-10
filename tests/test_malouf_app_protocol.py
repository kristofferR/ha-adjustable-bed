"""Frozen cluster-007 frame, exact model-route, and signed parser vectors."""

from datetime import datetime

import pytest

from custom_components.adjustable_bed.malouf_app_protocol import (
    MODEL_PROFILES,
    TRANSPORT_PROFILES,
    NotificationState,
    encode_alarm,
    encode_command,
    encode_time,
    get_profile,
    parse_notification,
    query_after,
)


@pytest.mark.parametrize(
    ("transport", "action", "expected"),
    [
        ("opcode_legacy", "headUp", "24"),
        ("opcode_legacy", "stopDriver", "6e"),
        ("opcode_framed", "headUp", "6e01002493"),
        ("opcode_framed", "stopDriver", "6e01006edd"),
        ("command32_legacy", "headUp", "e6fe16010000000004"),
        ("command32_legacy", "allFlat", "e6fe160000000800fd"),
        ("command32_middle", "headUp", "04020000000100000000"),
        ("command32_middle", "allFlat", "04020800000000000000"),
        ("command32_new", "headUp", "0502000000010000"),
        ("command32_new", "allFlat", "0502080000000000"),
    ],
)
def test_accepted_final_frame_vectors(transport, action, expected):
    assert encode_command(action, transport).hex() == expected


@pytest.mark.parametrize(
    ("action", "opcode"),
    [
        ("headUp", 0x24),
        ("headDown", 0x25),
        ("footUp", 0x26),
        ("footDown", 0x27),
        ("dualUp", 0x29),
        ("dualDown", 0x2A),
        ("allUp", 0x29),
        ("allDown", 0x2A),
        ("setMemory1", 0x2B),
        ("setMemory2", 0x2C),
        ("memory1", 0x2E),
        ("memory2", 0x2F),
        ("allFlat", 0x31),
        ("lightSwitch", 0x3C),
        ("fullTiltUp", 0x3F),
        ("fullTiltDown", 0x40),
        ("headTiltUp", 0x3F),
        ("headTiltDown", 0x40),
        ("tiltHeadUp", 0x41),
        ("tiltHeadDown", 0x42),
        ("lumbarUp", 0x41),
        ("lumbarDown", 0x42),
        ("zeroG", 0x45),
        ("antiSnore", 0x46),
        ("massageOff", 0x47),
        ("massageWave", 0x48),
        ("massageHead", 0x4C),
        ("massageFoot", 0x4E),
        ("tvRead", 0x58),
        ("lounge", 0x59),
        ("massage10", 0x5F),
        ("massage30", 0x61),
        ("massage20", 0x63),
        ("stopDriver", 0x6E),
    ],
)
def test_complete_reachable_opcode_catalogue_and_side_gates(action, opcode):
    assert encode_command(action, "opcode_legacy") == bytes((opcode,))
    primary = encode_command(action, "opcode_framed")
    secondary = encode_command(action, "opcode_framed", False)
    side_actions = {"headUp", "headDown", "massageHead", "allFlat", "zeroG", "antiSnore"}
    assert secondary[2] == int(action in side_actions)
    assert primary[3] == secondary[3] == opcode
    assert secondary[4] == (0x6F + secondary[2] + opcode) & 0xFF


@pytest.mark.parametrize(
    ("action", "command"),
    [
        ("headUp", 1),
        ("headDown", 2),
        ("footUp", 4),
        ("footDown", 8),
        ("dualUp", 5),
        ("dualDown", 10),
        ("headTiltUp", 0x10),
        ("headTiltDown", 0x20),
        ("lumbarUp", 0x40),
        ("lumbarDown", 0x80),
        ("massageTimer", 0x200),
        ("massageFoot", 0x400),
        ("massageHead", 0x800),
        ("zeroG", 0x1000),
        ("lounge", 0x2000),
        ("read", 0x2000),
        ("tvRead", 0x4000),
        ("antiSnore", 0x8000),
        ("memory1", 0x10000),
        ("memory2", 0x40000),
        ("setMemory1", 0x10000),
        ("setMemory2", 0x80040000),
        ("lightSwitch", 0x20000),
        ("allFlat", 0x8000000),
        ("massageWave", 0x10000000),
        ("stopDriver", 0),
    ],
)
def test_complete_reachable_command32_catalogue(action, command):
    legacy = encode_command(action, "command32_legacy")
    assert int.from_bytes(legacy[3:7], "little") == command
    assert sum(legacy) & 255 == 255
    assert encode_command(action, "command32_middle")[2:6] == command.to_bytes(4, "big")
    assert encode_command(action, "command32_new")[2:6] == command.to_bytes(4, "big")
    assert encode_command(action, "command32_new", False) == encode_command(action, "command32_new")


@pytest.mark.parametrize("transport", ["command32_legacy", "command32_middle", "command32_new"])
def test_smartbed238_only_changes_first_save(transport):
    value = encode_command("setMemory1", transport, device_name="OKIN SmartBed238-A")
    assert (
        int.from_bytes(value[3:7], "little")
        if transport.endswith("legacy")
        else int.from_bytes(value[2:6], "big")
    ) == 0x80010000
    assert encode_command("setMemory2", transport, device_name="Smartbed238") == encode_command(
        "setMemory2", transport
    )


@pytest.mark.parametrize(
    ("transport", "alarm", "clock"),
    [
        ("command32_legacy", "ed8003071e800d0000000000000000dd", "e780017e060e071e2db3"),
        ("command32_middle", "ed8003071e800d0000000000000000dd", "e780017e060e071e2db3"),
        ("command32_new", "07050101071e000100", "0704ea070e02071e2d"),
    ],
)
def test_alarm_and_clock_frozen_vectors(transport, alarm, clock):
    assert encode_alarm(transport, 7, 30, 13, 0x80).hex() == alarm
    assert encode_time(transport, datetime(2026, 7, 14, 7, 30, 45)).hex() == clock
    clear = encode_alarm(transport, 0, 0, 0, 0)
    if transport.endswith("new"):
        assert clear.hex() == "070500f40000000000"
    else:
        assert clear.hex() == "ed80030000000000000000000000008f"


def test_weekday_bits_and_sunday_clock():
    assert encode_alarm("command32_new", 23, 59, 18, 0xFE)[2:4] == bytes((0x7F, 6))
    assert encode_time("command32_new", datetime(2026, 7, 12))[5] == 0


@pytest.mark.parametrize(
    ("transport", "data", "expected"),
    [
        ("command32_legacy", "00000000000000400200", NotificationState(20, 1)),
        ("command32_legacy", "000000000000004002", None),
        ("command32_legacy", "", None),
        ("command32_legacy", "00000000000000800300", NotificationState(30, -2)),
        ("command32_middle", "0000000000000000000002", NotificationState(20, 0)),
        ("command32_middle", "00000000000000000000ff", NotificationState(-10, 0)),
        ("command32_middle", "", NotificationState(0, 0)),
        ("command32_new", "000b0000030000000001", NotificationState(20, 1)),
        ("command32_new", "000a0000030000000001", None),
        ("command32_new", "00", None),
        ("command32_new", "000b0000", NotificationState(0, 0)),
        ("command32_new", "000b0000030000000002", NotificationState(20, 0)),
        ("command32_new", "000b0000ff000000000000000001", NotificationState(0, 1)),
    ],
)
def test_bounds_signed_bytes_and_exact_light_equality(transport, data, expected):
    assert parse_notification(transport, bytes.fromhex(data)) == expected


@pytest.mark.parametrize(
    "length,massage_index,light_index", [(10, 8, 7), (16, 14, 13), (20, 19, 18)]
)
def test_each_legacy_notification_layout(length, massage_index, light_index):
    data = bytearray(length)
    data[massage_index] = 0xF2
    data[light_index] = 0x40
    assert parse_notification("command32_legacy", data) == NotificationState(20, 1)


def test_profile_inventory_and_premium_app_distinction():
    assert len(MODEL_PROFILES) == 16
    for transport in TRANSPORT_PROFILES:
        assert "read" not in get_profile("malouf", "premium", transport).presets
        assert (
            "read" in get_profile("lucid", "premium", transport).presets
        ) == transport.startswith("command32_")
    assert get_profile("malouf", "s750", "command32_new").manual == (
        "headUp",
        "headDown",
        "footUp",
        "footDown",
        "headTiltUp",
        "headTiltDown",
        "lumbarUp",
        "lumbarDown",
    )
    assert get_profile("malouf", "altitude", "opcode_framed").manual[-4:] == (
        "tiltHeadUp",
        "tiltHeadDown",
        "fullTiltUp",
        "fullTiltDown",
    )
    assert get_profile("lucid", "forte", "opcode_legacy").other == (
        "massageHead",
        "massageWave",
        "massageOff",
    )
    assert [MODEL_PROFILES[key].memory_slots for key in MODEL_PROFILES] == [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0,
        1,
        1,
        2,
        2,
        2,
        2,
    ]


@pytest.mark.parametrize("transport", list(TRANSPORT_PROFILES))
def test_queries_only_for_the_five_new_transport_actions(transport):
    for action in ("massageHead", "massageFoot", "massageWave", "massageTimer", "lightSwitch"):
        assert query_after(action, transport) == (transport == "command32_new")
    assert not query_after("allFlat", transport)


@pytest.mark.parametrize(
    "action",
    [
        "memory3",
        "setMemory3",
        "massageAll",
        "intensityOne",
        "massageHeadMinus",
        "massageFootMinus",
        "massageOff",
        "stopCommand",
    ],
)
def test_unreachable_command32_constants_are_not_exposed(action):
    with pytest.raises(ValueError):
        encode_command(action, "command32_new")


@pytest.mark.parametrize(
    "fields",
    [(True, 0, 13, 128), (24, 0, 13, 128), (0, 60, 13, 128), (0, 0, -1, 128), (0, 0, 13, 256)],
)
def test_invalid_alarm_fields_fail_before_building(fields):
    with pytest.raises(ValueError):
        encode_alarm("command32_new", *fields)


def test_invalid_profiles_and_opcode_alarm_rejected():
    with pytest.raises(ValueError):
        get_profile("unrecognized", "s750", "command32_new")
    with pytest.raises(ValueError):
        get_profile("malouf", "unknown", "command32_new")
    with pytest.raises(ValueError):
        encode_alarm("opcode_framed", 7, 30, 13, 128)
    with pytest.raises(ValueError):
        encode_command("headUp", "auto")


@pytest.mark.parametrize("app", ["malouf", "lucid"])
@pytest.mark.parametrize("model", ["forte", "m455", "m555", "l600", "s750"])
def test_off_and_timer_labels_follow_the_actual_shared_click_handler(app, model):
    # The accepted Lucid synthetic action table overstates command32 OFF.
    # Layout onclick=massageTimer; activity remaps only canSetMassageTimer.
    words = get_profile(app, model, "command32_new")
    opcodes = get_profile(app, model, "opcode_framed")
    assert "massageTimer" in words.other
    assert "massageOff" not in words.other
    assert "massageOff" in opcodes.other
    assert "massageTimer" not in opcodes.other
    assert encode_command("massageTimer", "command32_new").hex() == "0502000002000000"
    assert encode_command("massageOff", "opcode_framed").hex() == "6e010047b6"
    assert ("massageTimerSet" in opcodes.other) == (model in ("m455", "m555"))
    assert "massageTimerSet" not in words.other


@pytest.mark.parametrize("app", ["malouf", "lucid"])
@pytest.mark.parametrize("bed_type", ["single_bed", "split_bed", "split_head"])
@pytest.mark.parametrize("configuration", ["standard", "split_base", "dual_base"])
def test_route_configuration_matrix_for_inactive_child(app, bed_type, configuration):
    from custom_components.adjustable_bed.malouf_app_protocol import (
        RoutedAction,
        route_child_action,
    )

    kwargs = {
        "bed_type": bed_type,
        "configuration": configuration,
        "active_side": "left",
        "child_side": "right",
    }
    native = bed_type == "split_head" and configuration == "split_base"
    dual = bed_type == "split_head" and configuration == "dual_base"
    assert route_child_action(app, "headUp", **kwargs) == (
        RoutedAction("headUp", True) if native else None
    )
    assert route_child_action(app, "dualUp", **kwargs) == (
        RoutedAction("dualUp", True) if native else RoutedAction("footUp", True) if dual else None
    )
    assert route_child_action(app, "memory1", **kwargs) == (
        RoutedAction("memory1", True) if dual else None
    )
    assert route_child_action(app, "setMemory1", **kwargs) is None


@pytest.mark.parametrize("app", ["malouf", "lucid"])
@pytest.mark.parametrize(
    "action",
    [
        "dualUp",
        "dualDown",
        "footUp",
        "footDown",
        "allUp",
        "allDown",
        "stopDriver",
        "headUp",
        "headDown",
        "massageHead",
        "massageFoot",
    ],
)
def test_inactive_split_head_dual_action_matrix(app, action):
    from custom_components.adjustable_bed.malouf_app_protocol import (
        RoutedAction,
        route_child_action,
    )

    expected = None
    if action.startswith("dual"):
        expected = action.replace("dual", "foot")
    elif action.startswith("foot") or action == "stopDriver":
        expected = action
    elif action.startswith("all") and app == "lucid":
        expected = action.replace("all", "foot")
    # Matching is case-sensitive: massageFoot does not contain lowercase foot.
    actual = route_child_action(
        app,
        action,
        bed_type="split_head",
        configuration="dual_base",
        active_side="right",
        child_side="left",
    )
    assert actual == (RoutedAction(expected, True) if expected else None)


@pytest.mark.parametrize("active_side", ["none", "left", "right", "all"])
@pytest.mark.parametrize("child_side", ["none", "left", "right", "all"])
def test_exact_active_side_predicate(active_side, child_side):
    from custom_components.adjustable_bed.malouf_app_protocol import (
        RoutedAction,
        route_child_action,
    )

    expected = active_side == "all" or active_side == child_side or child_side == "none"
    assert route_child_action(
        "malouf", "headUp", active_side=active_side, child_side=child_side
    ) == (RoutedAction("headUp", True) if expected else None)


@pytest.mark.parametrize(
    "active_side,swapped,primary",
    [
        ("left", False, True),
        ("left", True, False),
        ("right", False, False),
        ("right", True, True),
        ("all", False, False),
        ("all", True, False),
        ("none", False, False),
        ("none", True, False),
    ],
)
def test_native_split_selector_and_unconditional_manual_route(active_side, swapped, primary):
    from custom_components.adjustable_bed.malouf_app_protocol import (
        RoutedAction,
        route_child_action,
    )

    kwargs = {
        "bed_type": "split_head",
        "configuration": "split_base",
        "active_side": active_side,
        "child_side": "right",
        "motor_swapped": swapped,
    }
    assert route_child_action("lucid", "headUp", **kwargs) == RoutedAction("headUp", primary)
    active = active_side in ("right", "all")
    assert route_child_action("lucid", "memory1", **kwargs) == (
        RoutedAction("memory1", primary) if active else None
    )
    assert route_child_action("lucid", "setMemory1", **kwargs) == (
        RoutedAction("setMemory1", True) if active else None
    )


def test_route_rejects_unknown_input_before_dispatch():
    from custom_components.adjustable_bed.malouf_app_protocol import route_child_action

    for kwargs in (
        {"bed_type": "unknown"},
        {"configuration": "unknown"},
        {"active_side": "both"},
        {"child_side": "unknown"},
        {"motor_swapped": 1},
    ):
        with pytest.raises(ValueError):
            route_child_action("malouf", "headUp", **kwargs)
    with pytest.raises(ValueError):
        route_child_action("malouf", "stopCommand")


@pytest.mark.parametrize(
    "model", ["good_life_base", "good_life_premier_base", "good_life_pro_base"]
)
@pytest.mark.parametrize("transport", list(TRANSPORT_PROFILES))
def test_lucid_oz_alias_and_long_hold_fallback(model, transport):
    lucid = get_profile("lucid", model, transport)
    malouf = get_profile("malouf", model, transport)
    assert lucid.memory_slots == malouf.memory_slots == 0
    assert lucid.programming_slots == (2,)
    assert malouf.programming_slots == ()
    for action in ("zeroG", "antiSnore"):
        assert (action in lucid.presets) == transport.startswith("opcode_")
        assert action in malouf.presets
    assert "tvRead" in lucid.presets and "lounge" in lucid.presets


def test_ordinary_programming_slots_remain_distinct_from_oz_fallback():
    assert get_profile("lucid", "s750", "command32_new").programming_slots == (1, 2)
    assert get_profile("malouf", "l600", "command32_new").programming_slots == (1,)
    assert get_profile("malouf", "premium", "opcode_framed").programming_slots == (1, 2)
