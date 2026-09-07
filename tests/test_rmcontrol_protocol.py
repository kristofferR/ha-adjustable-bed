"""Independent RMControl vectors transcribed from source byte operations."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.adjustable_bed.rmcontrol_protocol import (
    Notification,
    NotificationBuffer,
    RepeatAlarm,
    build_action,
    build_alarm_time_sync,
    build_anti_snore_config,
    build_anti_snore_switch,
    build_light_color,
    build_light_timer,
    build_repeat_alarm,
    build_single_alarm,
    decode_notification,
    delete_repeat_alarm,
    query_anti_snore_config,
    query_anti_snore_switch,
    query_repeat_alarms,
    query_sleep_advertisement,
)


@pytest.mark.parametrize(
    ("side", "expected"), [(0, "6e0100107f"), (1, "6e01011080"), (2, "6e01021081")]
)
def test_action_side_precedes_command(side: int, expected: str) -> None:
    assert build_action(16, side=side) == bytes.fromhex(expected)
    assert build_action(16, side=side, nordic=True) == b"\x10"


def test_special_prefix_ignores_side() -> None:
    assert build_action(1, side=2, action="deviceFunctionItemCheckClock") == bytes.fromhex(
        "6e08010178"
    )
    assert build_action(1, action="deviceFunctionItemCheckMattress") == bytes.fromhex("5e1a000179")


def test_rgb_and_timer_vectors() -> None:
    assert build_light_color((18, 52, 86)) == bytes.fromhex("6e0cff128b6e0d345605")
    assert build_light_timer(0) == bytes.fromhex("6e0bffff77")
    assert build_light_timer(300) == bytes.fromhex("6e0b012ca6")


def test_single_alarm_is_countdown_not_wall_clock() -> None:
    assert build_single_alarm(300, 16) == (bytes.fromhex("6e052c009f"), bytes.fromhex("6e06011085"))
    assert build_single_alarm(0, 0) == (bytes.fromhex("6e05000073"), bytes.fromhex("6e06000074"))


def test_repeat_alarm_crud_vectors() -> None:
    alarm = RepeatAlarm(3, 7, 30, 16, 0x83)
    assert build_repeat_alarm(alarm) == bytes.fromhex("6e0d200501010300071e10835d")
    assert delete_repeat_alarm(3) == bytes.fromhex("6e082005020103a1")
    assert query_repeat_alarms() == bytes.fromhex("6e0820050100009c")


def test_time_sync_both_frames_and_whole_hour_zone() -> None:
    assert build_alarm_time_sync(datetime(1970, 1, 1, tzinfo=UTC)) == (
        bytes.fromhex("6e0c200802010000000000a5"),
        bytes.fromhex("6e0d20080301000101000000a9"),
    )
    local = datetime(1970, 1, 2, tzinfo=timezone(timedelta(hours=-3, minutes=-30)))
    unix, calendar = build_alarm_time_sync(local)
    assert unix == bytes.fromhex("6e0c20080201000182b8fddd")
    assert calendar == bytes.fromhex("6e0d20080301000102000000aa")


def test_anti_snore_mode_not_boolean() -> None:
    assert build_anti_snore_config("count", 4) == bytes.fromhex("6e0a20060501010004a9")
    assert build_anti_snore_config("time", 20) == bytes.fromhex("6e0a20060501020014ba")
    assert build_anti_snore_switch(True) == bytes.fromhex("6e09200601010001a0")
    assert build_anti_snore_switch(False) == bytes.fromhex("6e092006010100009f")
    assert query_anti_snore_config() == bytes.fromhex("6e09200605000000a2")
    assert query_anti_snore_switch() == bytes.fromhex("6e0820060100009d")
    assert query_sleep_advertisement() == bytes.fromhex("6e0820060300009f")


@pytest.mark.parametrize("value", [-1, 65536, True, 1.5])
def test_invalid_timer_input(value: int) -> None:
    with pytest.raises(ValueError):
        build_light_timer(value)


def test_invalid_alarm_fields_and_naive_clock() -> None:
    with pytest.raises(ValueError):
        RepeatAlarm(0, 1, 2, 3, 4)
    with pytest.raises(ValueError):
        RepeatAlarm(1, 24, 2, 3, 4)
    with pytest.raises(ValueError):
        build_alarm_time_sync(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        build_anti_snore_switch(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("frame", "kind", "values"),
    [
        ("6e09010078", "capability", {"alarm": True}),
        ("6e0e00037f", "capability", {"light": True}),
        ("6e2100008f", "capability", {"anti_snore": True}),
        ("6e07010278", "single_alarm", {"result": "cancelled"}),
        ("6e23018416", "lock", {"locked": True}),
        ("6e90120010", "bed_mode", {"mode": 2}),
        ("6e90352457", "motor", {"motor": 1, "status": 1, "angle": 36}),
        (
            "6e90b1e08f",
            "music",
            {"usb_source": True, "playing": True, "shake": True, "bluetooth_enabled": True},
        ),
        ("6e200b040103001234563d", "rgb", {"rgb": (18, 52, 86)}),
        ("6e200a04020200012ccd", "light_timer", {"seconds": 300}),
        ("6e20090601030001a2", "anti_snore", {"enabled": True}),
        ("6e200a060502000214bb", "anti_snore", {"intervention_time": 20}),
        (
            "6e200d0501020300071e10835e",
            "repeat_alarm",
            {
                "alarm_id": 3,
                "record_flag": 0,
                "hour": 7,
                "minute": 30,
                "command": 16,
                "repeat_mask": 131,
            },
        ),
        ("6e200b02010301040202a8", "massage", {"head_strength": 4, "foot_strength": 2}),
        ("6e200a01030301242df1", "motor_angle", {"position": 1, "angle": 45}),
    ],
)
def test_notification_vectors(frame: str, kind: str, values: dict) -> None:
    assert decode_notification(bytes.fromhex(frame)) == Notification(kind, values)


def test_stream_fragmentation_coalescing_and_checksum_resync() -> None:
    stream = NotificationBuffer()
    assert stream.feed(bytes.fromhex("aa006e20")) == ()
    assert stream.feed(bytes.fromhex("0b040103001234")) == ()
    assert stream.feed(bytes.fromhex("563d6e090100786e09010000")) == (
        Notification("rgb", {"rgb": (18, 52, 86)}),
        Notification("capability", {"alarm": True}),
    )
    assert stream.feed(bytes.fromhex("6e2100008f")) == (
        Notification("capability", {"anti_snore": True}),
    )
    assert stream.feed(b"\x6e\x20") == ()
    stream.clear()
    assert stream.feed(bytes.fromhex("6e09010078")) == (
        Notification("capability", {"alarm": True}),
    )


@pytest.mark.parametrize(
    "frame",
    ["", "6e", "6e09010000", "6e20060401009b", "6e2009040102009e", "6e0b20040103001234564d"],
)
def test_malformed_unknown_and_outbound_are_ignored(frame: str) -> None:
    assert decode_notification(bytes.fromhex(frame)) is None


def test_partial_frame_expires_using_source_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = 1.0
    monkeypatch.setattr(
        "custom_components.adjustable_bed.rmcontrol_protocol.monotonic", lambda: timestamp
    )
    stream = NotificationBuffer()
    assert stream.feed(bytes.fromhex("6e20ff")) == ()
    timestamp = 1.501
    assert stream.feed(bytes.fromhex("6e09010078")) == (
        Notification("capability", {"alarm": True}),
    )


@pytest.mark.parametrize(
    ("domain", "command", "payload", "expected"),
    [
        (3, 1, "0001", Notification("white_light", {"on": True})),
        (4, 3, "0001", Notification("rgb", {"motion_enabled": True})),
        (4, 4, "0000", Notification("rgb", {"on": False})),
        (6, 2, "0001", Notification("anti_snore", {"get_off_bed_enabled": True})),
        (6, 3, "0041ff", Notification("anti_snore", {"sleep_advertisement": (65, 255)})),
        (
            6,
            4,
            "000101",
            Notification("anti_snore", {"in_bed_status": 1, "sleep_status": 1, "stop_music": True}),
        ),
        (7, 2, "0000", Notification("lock", {"locked": False})),
        (9, 2, "0214", Notification("music", {"volume": 20})),
        (9, 2, "0301", Notification("music", {"volume_silent": 1})),
        (10, 4, "aabb", Notification("diagnostic", {"channel": "rgb", "payload": (170, 187)})),
        (11, 2, "0002", Notification("press_mode", {"standard_and_split_control": True})),
        (14, 1, "0003", Notification("fan", {"gear": 3})),
        (16, 2, "00ff1e", Notification("aroma", {"timer_value": 30})),
        (
            17,
            2,
            "02ffff",
            Notification("heating", {"position": 2, "timer_mode": "unlimited", "timer_value": 0}),
        ),
        (17, 3, "01ff28", Notification("heating", {"position": 1, "temperature": 40})),
        (
            1,
            2,
            "0002580134012c",
            Notification(
                "motor_travel", {"height": 60.0, "type": 1, "angle": 52, "monitor_height": 30.0}
            ),
        ),
        (2, 6, "0001", Notification("massage", {"on": True})),
    ],
)
def test_named_domain_updates(
    domain: int, command: int, payload: str, expected: Notification
) -> None:
    # Construct only the envelope here; expected field semantics are independent.
    data = bytes.fromhex(payload)
    body = bytes((0x6E, 0x20, len(data) + 7, domain, command, 3)) + data
    assert decode_notification(body + bytes((sum(body) & 255,))) == expected


def test_checksum_is_not_missing_rgb_payload() -> None:
    body = bytes.fromhex("6e200a040103001234")
    assert decode_notification(body + bytes((sum(body) & 255,))) is None


def test_common_diagnostic_enum_semantics() -> None:
    assert decode_notification(bytes.fromhex("6e90c220e0")) == Notification(
        "detection", {"status": "stop"}
    )
    assert decode_notification(bytes.fromhex("6e90c321e2")) == Notification(
        "diagnostic", {"channel": "motor", "selector": 2, "status": "normal"}
    )
