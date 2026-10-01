"""Row049 SIMMONS app vectors, routing, release lifecycle and alarm state."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.simmons import (
    CUSTOM_MODE_WARNING,
    PEER_CONFLICT_ERROR,
    SimmonsController,
)
from custom_components.adjustable_bed.beds.simmons_protocol import (
    AlarmSlot,
    NotificationAssembler,
    clock_frame,
    control_frame,
    gain_weekday,
    p1_alarm_frame,
    p2_alarm_frame,
    p2_disable_frame,
    query_frames,
    repeat_mask,
    resolve_protocol,
)

NUS = (
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
)
FFE5 = ("0000ffe5-0000-1000-8000-00805f9b34fb", "0000ffe9-0000-1000-8000-00805f9b34fb")
FFE0 = ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe4-0000-1000-8000-00805f9b34fb")

# All 25 fixed frames from the accepted report (fixed_vectors.json), plus the
# three inclined frames sent under the OKIN response mode.
OKIN_ROWS = {
    "flat": "E6 FE 16 00 00 00 08 00 FD",
    "legs_down": "E6 FE 16 08 00 00 00 00 FD",
    "legs_up": "E6 FE 16 04 00 00 00 00 01",
    "head_down": "E6 FE 16 02 00 00 00 00 03",
    "head_up": "E6 FE 16 01 00 00 00 00 04",
    "memory": "E6 FE 16 00 00 01 00 00 04",
    "anti_snore": "E6 FE 16 00 80 00 00 00 85",
    "tv": "E6 FE 16 00 40 00 00 00 C5",
    "zero_g": "E6 FE 16 00 10 00 00 00 F5",
    "stop": "E6 FE 16 00 00 00 00 00 05",
    "light": "E6 FE 16 00 00 02 00 00 03",
    "inclined_left": "05 02 00 00 00 10 00",
    "inclined_middle": "05 02 00 00 10 00 00",
    "inclined_right": "05 02 00 00 00 20 00",
}
SMARTBED_ROWS = {
    "flat": "05 02 08 00 00 00 00",
    "legs_down": "05 02 00 00 00 08 00",
    "legs_up": "05 02 00 00 00 04 00",
    "head_down": "05 02 00 00 00 02 00",
    "head_up": "05 02 00 00 00 01 00",
    "memory": "05 02 00 01 00 00 00",
    "anti_snore": "05 02 00 00 80 00 00",
    "inclined_left": "05 02 00 00 00 10 00",
    "inclined_middle": "05 02 00 00 10 00 00",
    "inclined_right": "05 02 00 00 00 20 00",
    "tv": "05 02 00 00 40 00 00",
    "zero_g": "05 02 00 00 10 00 00",
    "stop": "05 02 00 00 00 00 00",
    "light": "05 02 00 02 00 00 00",
}


def _service(uuid: str, *chars: str) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=uuid.upper(),
        characteristics=[
            SimpleNamespace(uuid=char.upper(), handle=index) for index, char in enumerate(chars)
        ],
    )


def make_controller(
    variant: str | None = None,
    name: str | None = "OKIN-123456",
    services: list[SimpleNamespace] | None = None,
    state: dict[str, object] | None = None,
    stored_name: str | None = None,
) -> SimmonsController:
    coordinator = MagicMock()
    # The display name must never feed the name rule; only the raw BLE name does.
    coordinator.ble_device_name = "Bedroom"
    coordinator.entry = SimpleNamespace(
        data={"ble_device_name": stored_name} if stored_name else {}
    )
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_count = 2
    coordinator.controller_state = {} if state is None else state
    coordinator.handle_controller_state_updates = coordinator.controller_state.update
    coordinator.client = MagicMock(
        is_connected=True, services=services if services is not None else [_service(*NUS)]
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return SimmonsController(coordinator, protocol_variant=variant, device_name=name)


def written(controller: SimmonsController) -> list[str]:
    return [
        call.args[1].hex(" ").upper() for call in controller.client.write_gatt_char.call_args_list
    ]


def notify(controller: SimmonsController, hex_bytes: str) -> None:
    controller._handle_notification(None, bytearray.fromhex(hex_bytes))


@pytest.mark.parametrize(("protocol", "rows"), [("okin", OKIN_ROWS), ("smartbed", SMARTBED_ROWS)])
def test_every_control_row_is_byte_exact(protocol, rows):
    for action, expected in rows.items():
        assert control_frame(protocol, action).hex(" ").upper() == expected, action


def test_clock_query_and_alarm_vectors():
    now = datetime(2026, 10, 1, 7, 30, 45)
    assert clock_frame("okin", now).hex(" ").upper() == "E7 80 01 7E 09 01 07 1E 2D BD"
    assert clock_frame("smartbed", now).hex(" ").upper() == "07 04 7E 09 01 07 1E 2D 04"
    # Year bytes wrap modulo 256 (T28-T31).
    assert (
        clock_frame("okin", now.replace(year=2200)).hex(" ").upper()
        == "E7 80 01 2C 09 01 07 1E 2D 0F"
    )
    # The report's vectors fix weekday=4; here it is the real day (Wednesday).
    assert (
        clock_frame("smartbed", now.replace(year=1800)).hex(" ").upper()
        == "07 04 9C 09 01 07 1E 2D 03"
    )
    assert [frame.hex(" ").upper() for frame in query_frames("okin")] == ["E1 80 03 9B"]
    assert [frame.hex(" ").upper() for frame in query_frames("smartbed")] == ["00 C0", "00 D0"]
    assert (
        p1_alarm_frame([7, 30, 130, 17], [8, 45, 132, 28]).hex(" ").upper()
        == "ED 80 03 07 1E 82 11 08 2D 84 1C 00 00 00 00 02"
    )
    assert p2_alarm_frame(1, 130, 5, 7, 30).hex(" ").upper() == "07 05 82 05 07 1E 00 01 01"
    assert p2_alarm_frame(2, 130, 5, 7, 30).hex(" ").upper() == "07 06 82 05 07 1E 00 01 01"
    assert p2_disable_frame(1).hex(" ").upper() == "07 05 00 00 00 00 00 00 00"
    assert p2_disable_frame(2).hex(" ").upper() == "07 06 00 00 00 00 00 00 00"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("OKIN-123", "okin"),
        ("okinbed", "okin"),
        ("SmartBed1234", "smartbed"),
        ("smartbed-okin", "smartbed"),
        (" OKIN", "smartbed"),  # No trimming; unmatched names alias SmartBed.
        ("Simmons", "smartbed"),
        (None, "smartbed"),
    ],
)
def test_name_prefix_selects_the_packet_format(name, expected):
    assert resolve_protocol(name) == expected


def test_variant_fixes_protocol_and_layout_independently():
    regular = make_controller(name="SmartBed99")
    assert regular.protocol == "smartbed" and not regular.inclined_layout
    assert (
        regular.supports_preset_zero_g
        and regular.supports_preset_tv
        and regular.supports_preset_anti_snore
    )
    inclined = make_controller("simmons_inclined_okin", name="SmartBed99")
    assert inclined.protocol == "okin" and inclined.inclined_layout
    assert not (
        inclined.supports_preset_zero_g
        or inclined.supports_preset_tv
        or inclined.supports_preset_anti_snore
    )
    assert {spec.key for spec in inclined.controller_button_specs} >= {
        "simmons_inclined_left",
        "simmons_inclined_middle",
        "simmons_inclined_right",
    }
    assert (
        "zero_g" not in inclined.held_control_options
        and "inclined_left" in inclined.held_control_options
    )
    assert inclined.alarm_mode_options == ("custom_mode", "flat")
    assert regular.memory_slot_count == 1 and regular.memory_slot_names == ("Custom Mode",)
    assert not regular.supports_massage and not regular.supports_position_feedback


@pytest.mark.parametrize(
    ("services", "write", "notify"),
    [
        ([_service(*NUS)], NUS[1], NUS[2]),
        ([_service(*FFE5), _service(*FFE0)], FFE5[1], FFE0[1]),
        # Enumeration continues; the last match of each role wins.
        ([_service(*NUS), _service(*FFE5)], FFE5[1], NUS[2]),
        ([_service(*FFE0), _service(*NUS)], NUS[1], NUS[2]),
    ],
)
async def test_gatt_roles_follow_discovery_order(services, write, notify):
    controller = make_controller(services=services)
    await controller.async_discover_capabilities()
    assert controller.control_characteristic_uuid.lower() == write
    assert controller.protocol_diagnostics["simmons_notify_characteristic"].lower() == notify


async def test_missing_role_refuses_the_connection():
    with pytest.raises(ValueError, match="requires"):
        await make_controller(services=[_service(*FFE5)]).async_discover_capabilities()


@pytest.mark.parametrize(("name", "response"), [("OKIN-1", True), ("SmartBed1", False)])
async def test_write_mode_follows_the_protocol(name, response):
    controller = make_controller(name=name, services=[_service(*FFE5), _service(*FFE0)])
    await controller.async_discover_capabilities()
    await controller.write_command(b"\x01")
    call = controller.client.write_gatt_char.call_args
    assert call.kwargs["response"] is response
    assert call.args[0].uuid.lower() == FFE5[1]  # The exact discovered instance.


async def test_inclined_controls_send_smartbed_frames_with_okin_response_mode():
    controller = make_controller("simmons_inclined_okin")
    await controller.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.execute_simmons_action("inclined_left")
    frames = written(controller)
    assert frames[0] == "05 02 00 00 00 10 00"
    assert frames[-2:] == [OKIN_ROWS["stop"]] * 2
    assert all(call.kwargs["response"] for call in controller.client.write_gatt_char.call_args_list)


async def test_movement_repeats_every_300_ms_then_two_delayed_stops():
    controller = make_controller()
    await controller.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.move_back_up()
    assert written(controller) == [OKIN_ROWS["head_up"]] * 3 + [OKIN_ROWS["stop"]] * 2
    delays = [call.args[0] for call in sleep.call_args_list]
    assert all(0.29 < delay <= 0.3 for delay in delays[:2])
    # Mocked sleeps do not advance the clock: both STOPs share one release origin.
    assert 0.09 < delays[-2] <= 0.1 and 0.39 < delays[-1] <= 0.4


async def test_release_attempts_both_stops_with_fresh_events_after_cancel():
    controller = make_controller()
    await controller.async_discover_capabilities()
    controller._coordinator.cancel_command.set()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.move_legs_down()
    # The cancelled stream writes nothing, but cleanup still sends both STOPs.
    assert written(controller) == [OKIN_ROWS["stop"]] * 2


async def test_program_memory_holds_the_recall_frame_for_the_app_toast_time():
    controller = make_controller(name="SmartBed1")
    await controller.async_discover_capabilities()
    with patch.object(controller, "hold_control", new=AsyncMock()) as hold:
        await controller.program_memory(1)
    assert [call.args for call in hold.call_args_list] == [("memory", 5500)]
    with pytest.raises(ValueError):
        await controller.preset_memory(2)


@pytest.mark.parametrize(
    ("press", "action"),
    [
        ("preset_flat", "flat"),
        ("preset_zero_g", "zero_g"),
        ("preset_tv", "tv"),
        ("preset_anti_snore", "anti_snore"),
        ("lights_toggle", "light"),
    ],
)
async def test_buttons_are_app_taps_one_frame_then_release_stops(press, action):
    controller = make_controller(name="SmartBed1")
    await controller.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await getattr(controller, press)()
    assert written(controller) == [
        SMARTBED_ROWS[action],
        SMARTBED_ROWS["stop"],
        SMARTBED_ROWS["stop"],
    ]
    delays = [call.args[0] for call in sleep.call_args_list]
    assert len(delays) == 2 and 0.09 < delays[0] <= 0.1 and 0.39 < delays[1] <= 0.4


async def test_memory_recall_and_inclined_buttons_are_taps():
    controller = make_controller("simmons_inclined")
    await controller.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.preset_memory(1)
        await controller.execute_simmons_action("inclined_right")
    stop = OKIN_ROWS["stop"]
    assert written(controller) == [
        OKIN_ROWS["memory"],
        stop,
        stop,
        OKIN_ROWS["inclined_right"],
        stop,
        stop,
    ]


async def test_hold_control_rejects_controls_outside_the_layout():
    controller = make_controller()
    with pytest.raises(ValueError, match="layout"):
        await controller.hold_control("inclined_left", 500)


def test_notification_assembler_joins_fe16_fragments():
    assembler = NotificationAssembler()
    first = bytes([0, 0xFE, 0x16]) + bytes(17)
    assert assembler.feed(first) is None
    assert assembler.feed(b"\x01\x02") is None  # Short input is ignored, fragment kept.
    assert assembler.feed(b"\xed\x80\x03") == first + b"\xed\x80\x03"
    assert assembler.feed(b"\xa5\x0c\x0e") == b"\xa5\x0c\x0e"


@pytest.mark.parametrize(
    ("mask", "delta_us", "expected"),
    [(0, -1, 16), (0, 999, 16), (0, 1000, 32), (128, 1000, 32), (130, 1000, 130), (255, -1, 255)],
)
def test_once_weekday_truncates_to_whole_milliseconds(mask, delta_us, expected):
    now = datetime(2026, 10, 1, 7, 30) + timedelta(microseconds=delta_us)
    assert gain_weekday(mask, 7, 30, now) == expected


def test_once_weekday_adds_absolute_24_hours_across_dst():
    oslo = ZoneInfo("Europe/Oslo")
    # Saturday 2026-03-28 02:30 local; target 02:00 is past, so +24 h lands on
    # Sunday (the DST transition day) at 03:00 local.
    assert gain_weekday(0, 2, 0, datetime(2026, 3, 28, 2, 30, tzinfo=oslo)) == 1 << 0
    assert repeat_mask([]) == 128
    assert repeat_mask([0, 6]) == 128 | 0b10 | 0b1  # Monday bit 1, Sunday bit 0.


async def test_okin_reply_overlay_pending_ack_and_state():
    controller = make_controller()
    await controller.async_discover_capabilities()
    notify(controller, "ED 80 03 07 1E 82 11 08 2D 80 1C")
    state = controller._coordinator.controller_state
    assert state["simmons_alarm_1"] == "07:30" and state["simmons_alarm_1_enabled"] is True
    assert state["simmons_alarm_1_mode"] == "custom_mode"
    assert state["simmons_alarm_2_enabled"] is False and state["simmons_alarm_2_mode"] == "flat"
    controller._slots[0] = AlarmSlot(7, 30, 130, 17, True)
    controller._pending_record = bytes.fromhex("07 1E 02 11 08 2D 80 1C")
    controller._awaiting = [True, True]
    notify(controller, "ED 80 03 07 1E 02 11 08 2D 80 1C")
    # Enabled records keep the local weekday; a full 8-byte match clears pending.
    assert state["simmons_alarm_1_weekday_mask"] == 130
    assert controller._pending_record is None and state["simmons_alarm_1_awaiting_reply"] is False
    controller._pending_record = bytes(8)
    notify(controller, "ED 80 03 07 1E 02 11 08 2D 80 1C")
    assert controller._pending_record == bytes(8)  # Mismatch keeps it pending.
    notify(controller, "ED 80 03 07 1E 82")  # Truncated: rejected whole.
    assert state["simmons_alarm_1"] == "07:30"


async def test_smartbed_reply_overlay_and_all_zero_open_record():
    controller = make_controller(name="SmartBed1")
    controller._slots[1] = AlarmSlot(6, 15, 132, 9, True)
    controller._awaiting = [False, True]
    notify(controller, "A5 0D 0E 00 02 09 08 1E 00 00")
    state = controller._coordinator.controller_state
    # Disabled: local hour/minute/weekday kept, received type kept.
    assert state["simmons_alarm_2"] == "06:15" and state["simmons_alarm_2_weekday_mask"] == 132
    assert state["simmons_alarm_2_enabled"] is False
    assert state["simmons_alarm_2_awaiting_reply"] is False  # Any slot reply clears it.
    notify(controller, "A5 0C 0E 00 00 00 00 00 00 01")
    assert state["simmons_alarm_1_enabled"] is False and state["simmons_alarm_1_wire_type"] == 0
    notify(controller, "A5 0C 0E 00 82 05 07 1E 00 02")
    assert state["simmons_alarm_1"] == "07:30" and state["simmons_alarm_1_enabled"] is True


def test_alarm_records_survive_controller_recreation():
    state: dict[str, object] = {}
    first = make_controller(state=state)
    notify(first, "ED 80 03 07 1E 82 11 08 2D 80 1C")
    second = make_controller(state=state)
    assert second._slots[0] == AlarmSlot(7, 30, 130, 17, True)


def _known(controller: SimmonsController, first: AlarmSlot, second: AlarmSlot) -> None:
    """A linked session: clock already synced and both records reported."""
    controller._slots = [first, second]
    controller._clock_synced = True


async def test_okin_program_preserves_the_peer_record_then_queries():
    controller = make_controller()
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(6, 0, 0, 0, False), AlarmSlot(8, 45, 132, 28, True))
    now = datetime(2026, 10, 1, 6, 0)
    with (
        patch("asyncio.sleep", new=AsyncMock()) as sleep,
        patch("custom_components.adjustable_bed.beds.simmons.dt_util.now", return_value=now),
    ):
        await controller.configure_simmons_alarm(
            slot=1,
            enabled=True,
            hour=7,
            minute=30,
            weekdays=[0],
            mode="custom_mode",
            confirm_custom_mode=True,
        )
    assert written(controller) == [
        "ED 80 03 07 1E 82 11 08 2D 84 1C 00 00 00 00 02",
        "E1 80 03 9B",
    ]
    assert sleep.call_args.args == (0.3,)
    assert controller._pending_record == bytes.fromhex("07 1E 82 11 08 2D 84 1C")
    assert controller._coordinator.controller_state["simmons_alarm_1_awaiting_reply"] is True


@pytest.mark.parametrize(
    ("slot", "expected"),
    [
        (1, "ED 80 03 07 1E 00 00 08 2D 84 1C 00 00 00 00 95"),
        (2, "ED 80 03 07 1E 82 11 08 2D 00 00 00 00 00 00 A2"),
    ],
)
async def test_okin_disable_clears_selected_weekday_and_type(slot, expected):
    controller = make_controller()
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(7, 30, 130, 17, True), AlarmSlot(8, 45, 132, 28, True))
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.configure_simmons_alarm(slot=slot, enabled=False)
    assert written(controller)[0] == expected
    assert controller._slots[slot - 1].enabled is False


async def test_okin_disable_sends_a_disabled_peer_weekday_as_zero():
    controller = make_controller()
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(7, 30, 130, 17, True), AlarmSlot(8, 45, 132, 28, False))
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.configure_simmons_alarm(slot=1, enabled=False)
    assert written(controller)[0] == p1_alarm_frame([7, 30, 0, 0], [8, 45, 0, 28]).hex(" ").upper()


async def test_smartbed_program_and_disable_use_per_slot_frames():
    controller = make_controller(name="SmartBed1")
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(0, 0, 0, 0, False), AlarmSlot(0, 0, 0, 0, False))
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.configure_simmons_alarm(
            slot=2, enabled=True, hour=7, minute=30, weekdays=[0], mode="anti_snore"
        )
        await controller.configure_simmons_alarm(slot=1, enabled=False)
    assert written(controller) == [
        "07 06 82 04 07 1E 00 01 01",
        "00 C0",
        "00 D0",
        "07 05 00 00 00 00 00 00 00",
        "00 C0",
        "00 D0",
    ]
    assert all(
        call.kwargs["response"] is False
        for call in controller.client.write_gatt_char.call_args_list
    )


@pytest.mark.parametrize(("hour", "minute", "mode"), [(8, 45, "custom_mode"), (6, 0, "flat")])
async def test_enabled_peer_with_same_time_or_mode_is_rejected(hour, minute, mode):
    controller = make_controller()
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(6, 0, 0, 0, False), AlarmSlot(8, 45, 132, 28, True))
    with pytest.raises(ValueError, match="same alarm timing"):
        await controller.configure_simmons_alarm(
            slot=1, enabled=True, hour=hour, minute=minute, mode=mode, confirm_custom_mode=True
        )
    assert written(controller) == []
    assert PEER_CONFLICT_ERROR


def test_custom_mode_needs_confirmation_and_anti_snore_needs_regular_layout():
    controller = make_controller()
    with pytest.raises(ValueError) as error:
        controller.validate_simmons_alarm(
            slot=1, enabled=True, mode="custom_mode", confirm_custom_mode=False
        )
    assert str(error.value) == CUSTOM_MODE_WARNING
    controller.validate_simmons_alarm(
        slot=1, enabled=True, mode="custom_mode", confirm_custom_mode=True
    )
    controller.validate_simmons_alarm(slot=2, enabled=False, mode=None, confirm_custom_mode=False)
    with pytest.raises(ValueError, match="Alarm mode"):
        make_controller("simmons_inclined").validate_simmons_alarm(
            slot=1, enabled=True, mode="anti_snore", confirm_custom_mode=False
        )


async def test_unknown_alarm_state_is_queried_before_programming():
    controller = make_controller()
    await controller.async_discover_capabilities()
    controller._clock_synced = True

    async def reply(_char: object, data: bytes, response: bool) -> None:
        if data == bytes.fromhex("E1 80 03 9B"):
            notify(controller, "ED 80 03 06 00 00 00 08 2D 84 10")

    controller.client.write_gatt_char.side_effect = reply
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.configure_simmons_alarm(
            slot=1, enabled=True, hour=7, minute=30, weekdays=[0], mode="flat"
        )
    assert written(controller)[:2] == [
        "E1 80 03 9B",
        p1_alarm_frame([7, 30, 130, 28], [8, 45, 132, 16]).hex(" ").upper(),
    ]


async def test_alarm_state_must_be_reported_before_writing():
    controller = make_controller()
    await controller.async_discover_capabilities()
    controller._clock_synced = True
    with (
        patch("custom_components.adjustable_bed.beds.simmons.ALARM_REPLY_TIMEOUT_S", 0),
        pytest.raises(ValueError, match="did not report"),
    ):
        await controller.configure_simmons_alarm(slot=1, enabled=False)
    assert written(controller) == ["E1 80 03 9B"]


async def test_connection_setup_syncs_clock_then_runs_the_alarm_page_queries():
    controller = make_controller(name="SmartBed1")
    await controller.async_discover_capabilities()
    now = datetime(2026, 10, 1, 7, 30, 45)
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch("custom_components.adjustable_bed.beds.simmons.dt_util.now", return_value=now),
    ):
        await controller.start_notify(None)
    assert written(controller) == ["07 04 7E 09 01 07 1E 2D 04"] + ["00 C0", "00 D0"] * 3
    assert controller._clock_synced


async def test_failed_session_clock_is_synced_before_an_alarm_write():
    controller = make_controller()
    await controller.async_discover_capabilities()
    controller.client.write_gatt_char.side_effect = [BleakError("busy"), None, None, None]
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify(None)  # Setup still succeeds.
        assert not controller._clock_synced
        controller._slots = [AlarmSlot(6, 0, 0, 0, False), AlarmSlot(8, 45, 132, 28, False)]
        await controller.configure_simmons_alarm(slot=1, enabled=False)
    frames = written(controller)
    assert frames[1].startswith("E7 80 01") and frames[2].startswith("ED 80 03")
    assert controller._clock_synced


async def test_notifications_subscribe_to_the_selected_role():
    controller = make_controller(services=[_service(*FFE5), _service(*FFE0)])
    await controller.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify(None)
    assert controller.requires_notification_channel
    assert controller.client.start_notify.call_args.args[0].uuid.lower() == FFE0[1]


@pytest.mark.parametrize(
    ("live", "stored", "expected"),
    [
        ("AA:BB:CC:DD:EE:FF", "SmartBed123", "smartbed"),
        ("AA-BB-CC-DD-EE-FF", "OKIN-1", "okin"),
        (None, "OKIN-1", "okin"),
        ("OKIN-2", "SmartBed123", "okin"),
        ("AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66", "smartbed"),
    ],
)
def test_address_like_live_name_falls_back_to_the_stored_name(live, stored, expected):
    assert make_controller(name=live, stored_name=stored).protocol == expected


async def test_configuration_writes_are_not_skipped_by_a_movement_stop():
    controller = make_controller()
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(6, 0, 0, 0, False), AlarmSlot(8, 45, 132, 28, False))
    controller._coordinator.cancel_command.set()  # A STOP is in flight.
    with (
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.simmons.dt_util.now",
            return_value=datetime(2026, 10, 1, 7, 30, 45),
        ),
    ):
        await controller.sync_clock()
        await controller.configure_simmons_alarm(
            slot=1, enabled=True, hour=7, minute=30, mode="flat"
        )
    assert written(controller) == [
        "E7 80 01 7E 09 01 07 1E 2D BD",
        # 07:30:00 has passed at 07:30:45, so the one-off lands on Friday (bit 5).
        p1_alarm_frame([7, 30, 32, 28], [8, 45, 0, 28]).hex(" ").upper(),
        "E1 80 03 9B",
    ]
    assert controller._slots[0] == AlarmSlot(7, 30, 128, 28, True)


async def test_failed_alarm_write_leaves_local_state_unchanged():
    controller = make_controller()
    await controller.async_discover_capabilities()
    before = [AlarmSlot(6, 0, 0, 0, False), AlarmSlot(8, 45, 132, 28, True)]
    _known(controller, *before)
    controller.client.write_gatt_char.side_effect = BleakError("write failed")
    with pytest.raises(BleakError):
        await controller.configure_simmons_alarm(
            slot=1, enabled=True, hour=7, minute=30, mode="anti_snore"
        )
    assert controller._slots == before and controller._awaiting == [False, False]


async def test_disabled_other_alarm_may_share_time_and_mode():
    controller = make_controller()
    await controller.async_discover_capabilities()
    _known(controller, AlarmSlot(6, 0, 0, 0, False), AlarmSlot(8, 45, 132, 28, False))
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.configure_simmons_alarm(
            slot=1, enabled=True, hour=8, minute=45, weekdays=[0], mode="flat"
        )
    assert (
        written(controller)[0] == p1_alarm_frame([8, 45, 130, 28], [8, 45, 0, 28]).hex(" ").upper()
    )


async def test_alarm_page_queries_run_at_0_300_and_600_ms():
    controller = make_controller()
    await controller.async_discover_capabilities()
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.refresh_alarms()
    assert written(controller) == ["E1 80 03 9B"] * 3
    # Mocked sleeps do not advance the clock: each offset is from one origin.
    delays = [call.args[0] for call in sleep.call_args_list]
    assert delays[0] == 0 and 0.29 < delays[1] <= 0.3 and 0.59 < delays[2] <= 0.6


async def test_hold_ends_at_its_deadline_then_releases():
    controller = make_controller()
    await controller.async_discover_capabilities()
    stalled = asyncio.Event()

    async def write(_char: object, data: bytes, response: bool) -> None:
        if data != bytes.fromhex("E6 FE 16 00 00 00 00 00 05"):
            await stalled.wait()  # The held frame outlives the 1 ms deadline.

    controller.client.write_gatt_char.side_effect = write
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control("flat", 1)
    assert written(controller) == [OKIN_ROWS["flat"], OKIN_ROWS["stop"], OKIN_ROWS["stop"]]


async def test_cancelled_release_reraises_cancellation_after_a_stop_failure():
    controller = make_controller()
    await controller.async_discover_capabilities()
    gate = asyncio.Event()

    async def fail(*_args: object, **_kwargs: object) -> None:
        await gate.wait()
        raise BleakError("stop failed")

    controller.client.write_gatt_char.side_effect = fail
    real_sleep = asyncio.sleep
    with patch("asyncio.sleep", new=lambda _delay, *args: real_sleep(0, *args)):
        task = asyncio.create_task(controller.stop_all())
        for _ in range(5):
            await real_sleep(0)
        task.cancel()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert len(written(controller)) == 2  # Both STOPs were still attempted.


def test_session_end_publishes_cleared_awaiting_flags():
    controller = make_controller()
    _known(controller, AlarmSlot(7, 30, 130, 17, True), AlarmSlot(8, 45, 132, 28, True))
    controller._awaiting = [True, True]
    controller._publish_slots()
    controller.invalidate_diagnostics()
    state = controller._coordinator.controller_state
    assert state["simmons_alarm_1_awaiting_reply"] is False
    assert state["simmons_alarm_2_awaiting_reply"] is False
