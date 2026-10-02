"""Row054 Adjustable bed (Lumbar) app: artifact vectors, table selection and timing."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.adjustable_lumbar import (
    SAVE_HOLD_MS,
    AdjustableLumbarController,
    check_massage_frame,
    control_frame,
    resolve_branch,
    star_table,
)

NUS = (
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
)
OKIN = (
    "62741523-52f9-8864-b1ab-3b3a8d65950b",
    "62741525-52f9-8864-b1ab-3b3a8d65950b",
    "62741625-52f9-8864-b1ab-3b3a8d65950b",
)
INFO = ("0000180a-0000-1000-8000-00805f9b34fb", "00002a29-0000-1000-8000-00805f9b34fb")

# Every frame in the accepted report's command tables (UI and voice rows).
# 25_42_02 and 36_33_04a carry identical bytes.
LONG_ROWS = {
    "head_up": "08 02 00 00 00 01 00 00 00 00",
    "head_down": "08 02 00 00 00 02 00 00 00 00",
    "feet_up": "08 02 00 00 00 04 00 00 00 00",
    "feet_down": "08 02 00 00 00 08 00 00 00 00",
    "lumbar_up": "08 02 00 00 00 10 00 00 00 00",
    "lumbar_down": "08 02 00 00 00 20 00 00 00 00",
    "stop": "08 02 00 00 00 00 00 00 00 00",
    "flat": "08 02 08 00 00 00 00 00 00 00",
    "anti_snore": "08 02 00 00 80 00 00 00 00 00",
    "lounge": "08 02 00 00 20 00 00 00 00 00",
    "incline": "08 02 00 00 40 00 00 00 00 00",
    "zero_g": "08 02 00 00 10 00 00 00 00 00",
    "save_anti_snore": "08 02 08 00 80 00 00 00 00 00",
    "save_lounge": "08 02 08 00 20 00 00 00 00 00",
    "save_incline": "08 02 08 00 40 00 00 00 00 00",
    "save_zero_g": "08 02 08 00 10 00 00 00 00 00",
    "light": "08 02 00 02 00 00 00 00 00 00",
    "wave_1": "08 02 00 00 00 00 00 08 00 00",
    "wave_2": "08 02 00 00 00 00 00 10 00 00",
    "wave_3": "08 02 00 00 00 00 00 20 00 00",
    "massage_stop": "08 02 02 00 00 00 00 00 00 00",
    "massage_up": "08 02 00 00 0C 00 00 00 00 00",
    "massage_down": "08 02 01 80 00 00 00 00 00 00",
    "massage_on": "08 02 00 00 01 00 00 00 00 00",
    "voice_stop": "08 02 00 00 00 00 00 00 00 00",
}
STAR_ROWS = {
    "head_up": "5A 01 03 10 30 00 A5",
    "head_down": "5A 01 03 10 30 01 A5",
    "feet_up": "5A 01 03 10 30 02 A5",
    "feet_down": "5A 01 03 10 30 03 A5",
    "lumbar_up": "5A 01 03 10 30 06 A5",
    "lumbar_down": "5A 01 03 10 30 07 A5",
    "stop": "5A 01 03 10 30 0F A5",
    "flat": "5A 01 03 10 30 10 A5",
    "anti_snore": "5A 01 03 10 30 16 A5",
    "lounge": "5A 01 03 10 30 12 A5",
    "incline": "5A 01 03 10 30 11 A5",
    "zero_g": "5A 01 03 10 30 13 A5",
    "save_anti_snore": "5A 01 03 10 30 93 A5",
    "save_lounge": "5A 01 03 10 30 91 A5",
    "save_incline": "5A 01 03 10 30 92 A5",
    "save_zero_g": "5A 01 03 10 30 90 A5",
    "light": "5A 01 03 10 30 71 A5",
    "wave_1": "5A 01 03 10 30 52 A5",
    "wave_2": "5A 01 03 10 30 53 A5",
    "wave_3": "5A 01 03 10 30 54 A5",
    "massage_stop": "5A 01 03 10 30 6F A5",
    "massage_up": "5A 01 03 10 40 60 A5",
    "massage_down": "5A 01 03 10 40 61 A5",
    "massage_on": "5A 01 03 10 30 52 A5",
    "voice_stop": "5A 01 03 10 30 1F A5",
}


def _char(uuid: str, *properties: str) -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid.upper(), properties=list(properties), handle=hash(uuid) % 97)


def _service(uuid: str, *chars: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid.upper(), characteristics=list(chars))


def nus_services(*, info: bool = True, manufacturer: bool = True) -> list[SimpleNamespace]:
    services = [
        _service(
            NUS[0], _char(NUS[1], "write-without-response", "write"), _char(NUS[2], "notify")
        )
    ]
    if info:
        services.append(_service(INFO[0], *([_char(INFO[1], "read")] if manufacturer else [])))
    return services


def okin_services(*, manufacturer: bool = True) -> list[SimpleNamespace]:
    return [
        _service(OKIN[0], _char(OKIN[1], "write"), _char(OKIN[2], "notify")),
        _service(INFO[0], *([_char(INFO[1], "read")] if manufacturer else [])),
    ]


def make_controller(
    name: str | None = "OKIN-123456",
    *,
    variant: str | None = None,
    services: list[SimpleNamespace] | None = None,
    manufacturer: bytes | Exception = b"OKIN",
    stored_name: str | None = None,
) -> AdjustableLumbarController:
    coordinator = MagicMock()
    coordinator.entry = SimpleNamespace(
        data={"ble_device_name": stored_name} if stored_name else {}
    )
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_count = 3
    branch = resolve_branch(name) or resolve_branch(stored_name)
    default_services = nus_services() if branch == "star" else okin_services()
    coordinator.client = MagicMock(
        is_connected=True, services=services if services is not None else default_services
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    if isinstance(manufacturer, Exception):
        coordinator.client.read_gatt_char = AsyncMock(side_effect=manufacturer)
    else:
        coordinator.client.read_gatt_char = AsyncMock(return_value=bytearray(manufacturer))
    return AdjustableLumbarController(coordinator, protocol_variant=variant, device_name=name)


async def connected(name: str = "OKIN-123456", **kwargs: object) -> AdjustableLumbarController:
    controller = make_controller(name, **kwargs)  # type: ignore[arg-type]
    await controller.async_discover_capabilities()
    return controller


def written(controller: AdjustableLumbarController) -> list[str]:
    return [
        call.args[1].hex(" ").upper() for call in controller.client.write_gatt_char.call_args_list
    ]


@pytest.mark.parametrize(
    ("table", "rows"), [("25_42_02", LONG_ROWS), ("36_33_04a", LONG_ROWS), ("35_22_01", STAR_ROWS)]
)
def test_every_command_row_is_byte_exact(table, rows):
    for action, expected in rows.items():
        assert control_frame(table, action).hex(" ").upper() == expected, action


def test_massage_query_is_raw_without_table_framing():
    assert check_massage_frame("25_42_02") == bytes.fromhex("02 04")
    assert check_massage_frame("36_33_04a") == bytes.fromhex("02 04")
    assert check_massage_frame("35_22_01") == bytes.fromhex("5A B0 00 A5")


@pytest.mark.parametrize(
    ("name", "branch"),
    [
        ("OKIN-1234", "okin"),
        ("okinstar", "okin"),  # okin is checked first
        ("Star252201", "star"),
        ("STAR-okin", "star"),
        ("SmartBed-1", None),  # accepted by the app's scan, but no table
        (" OKIN", None),  # no trimming
        (None, None),
    ],
)
def test_name_prefix_rule(name, branch):
    assert resolve_branch(name) == branch


@pytest.mark.parametrize(
    ("reply", "table"),
    [
        (b"STAR", "35_22_01"),
        (b"STAR\x00", "25_42_02"),  # the terminator fails the exact match
        (b"star", "25_42_02"),
        (b"STARCODE", "25_42_02"),
        (None, "25_42_02"),
    ],
)
def test_star_manufacturer_selects_the_table(reply, table):
    assert star_table(reply) == table


async def test_okin_name_uses_the_okin_service_with_response():
    controller = await connected("OKIN-1")
    assert controller.table == "36_33_04a"
    assert controller.control_characteristic_uuid.lower() == OKIN[1]
    # The pair-named manufacturer read happens, but its value is unused.
    controller.client.read_gatt_char.assert_awaited_once()
    await controller.write_command(b"\x01")
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is True


@pytest.mark.parametrize(
    ("reply", "table"),
    [(b"STAR", "35_22_01"), (b"Star", "25_42_02"), (BleakError("read failed"), "25_42_02")],
)
async def test_star_name_reads_the_manufacturer_then_writes_without_response(reply, table):
    controller = await connected("Star25", manufacturer=reply)
    assert controller.table == table
    assert controller.control_characteristic_uuid.lower() == NUS[1]
    await controller.write_command(b"\x01")
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is False


async def test_star_without_the_manufacturer_characteristic_stays_on_25_42_02():
    controller = await connected("Star25", services=nus_services(manufacturer=False))
    assert controller.table == "25_42_02"
    controller.client.read_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    ("name", "services", "match"),
    [
        ("Star25", nus_services(info=False), "Device Information"),
        ("OKIN-1", okin_services(manufacturer=False), "manufacturer characteristic"),
        ("OKIN-1", nus_services(), "write and notify roles"),
        ("Star25", okin_services(), "write and notify roles"),
        (
            "Star25",
            [_service(NUS[0], _char(NUS[1], "write"), _char(NUS[2], "notify"))],
            "write-without-response",
        ),
        ("SmartBed-1", okin_services(), "no command table"),
    ],
)
async def test_missing_app_preconditions_refuse_the_connection(name, services, match):
    with pytest.raises(ValueError, match=match):
        await connected(name, services=services)


async def test_variant_fixes_the_branch_and_address_names_use_the_stored_name():
    assert (await connected("SmartBed-1", variant="adjustable_lumbar_okin")).table == "36_33_04a"
    star = await connected(
        "OKIN-1", variant="adjustable_lumbar_star", services=nus_services(), manufacturer=b"STAR"
    )
    assert star.table == "35_22_01"
    stored = make_controller("AA:BB:CC:DD:EE:FF", stored_name="Star99")
    assert stored.protocol_diagnostics["adjustable_lumbar_branch"] == "star"


async def test_motor_streams_every_100_ms_then_stops_now_and_at_300_ms():
    controller = await connected("OKIN-1")
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.move_lumbar_up()
    assert written(controller) == [LONG_ROWS["lumbar_up"]] * 3 + [LONG_ROWS["stop"]] * 2
    delays = [call.args[0] for call in sleep.call_args_list]
    assert all(0.09 < delay <= 0.1 for delay in delays[:2])
    # Both STOPs share one release origin (mocked sleeps do not advance time).
    assert delays[-1] == pytest.approx(0.3, abs=0.01)
    assert {spec.key for spec in controller.motor_control_specs} == {"head", "feet", "lumbar"}
    assert {spec.scheduler_resource for spec in controller.motor_control_specs} == {"*"}


async def test_release_stops_are_sent_with_fresh_events_after_a_cancel():
    controller = await connected("Star25", manufacturer=b"STAR")
    controller._coordinator.cancel_command.set()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.move_head_down()
    assert written(controller) == [STAR_ROWS["stop"]] * 2


@pytest.mark.parametrize(
    ("press", "action"),
    [
        ("preset_flat", "flat"),
        ("preset_zero_g", "zero_g"),
        ("preset_lounge", "lounge"),
        ("preset_incline", "incline"),
        ("preset_anti_snore", "anti_snore"),
        ("lights_toggle", "light"),
        ("massage_intensity_up", "massage_up"),
        ("massage_intensity_down", "massage_down"),
        ("massage_off", "massage_stop"),
    ],
)
async def test_buttons_are_app_taps(press, action):
    controller = await connected("Star25", manufacturer=b"STAR")
    with patch("asyncio.sleep", new=AsyncMock()):
        await getattr(controller, press)()
    assert written(controller) == [STAR_ROWS[action], STAR_ROWS["stop"], STAR_ROWS["stop"]]


@pytest.mark.parametrize("wave", ["wave_1", "wave_2", "wave_3"])
async def test_wave_buttons_are_taps(wave):
    controller = await connected("OKIN-1")
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.execute_app_action(wave)
    assert written(controller) == [LONG_ROWS[wave], LONG_ROWS["stop"], LONG_ROWS["stop"]]


@pytest.mark.parametrize(
    ("name", "reply", "rows"),
    [("OKIN-1", b"", LONG_ROWS), ("Star25", b"STAR", STAR_ROWS), ("Star25", b"", LONG_ROWS)],
)
async def test_massage_on_follows_the_voice_route(name, reply, rows):
    controller = await connected(name, manufacturer=reply)
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.execute_app_action("massage_on")
    assert written(controller) == [rows["voice_stop"], rows["massage_on"], rows["massage_on"]]
    assert [call.args[0] for call in sleep.call_args_list] == [pytest.approx(0.1, abs=0.01)]


async def test_check_massage_writes_one_raw_query():
    controller = await connected("Star25", manufacturer=b"STAR")
    await controller.execute_app_action("check_massage")
    assert written(controller) == ["5A B0 00 A5"]


async def test_save_buttons_hold_the_chord_frame_for_the_app_report_time():
    controller = await connected("OKIN-1")
    assert SAVE_HOLD_MS == 6000
    with patch.object(controller, "hold_control", new=AsyncMock()) as hold:
        for key in ("save_zero_g", "save_lounge", "save_incline", "save_anti_snore"):
            await controller.execute_app_action(key)
    assert [call.args for call in hold.call_args_list] == [
        (key, 6000) for key in ("save_zero_g", "save_lounge", "save_incline", "save_anti_snore")
    ]


async def test_hold_streams_until_its_deadline_then_releases():
    controller = await connected("OKIN-1")
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control("save_zero_g", 300)
    frames = written(controller)
    assert frames[:-2] == [LONG_ROWS["save_zero_g"]] * 4
    assert frames[-2:] == [LONG_ROWS["stop"]] * 2


@pytest.mark.parametrize(
    ("control", "duration"),
    [("massage_stop", 500), ("massage_on", 500), ("tv", 500), ("flat", 0), ("flat", 60001)],
)
async def test_hold_rejects_unheld_controls_and_bad_durations(control, duration):
    controller = await connected("OKIN-1")
    with pytest.raises(ValueError):
        await controller.hold_control(control, duration)
    controller.client.write_gatt_char.assert_not_awaited()


async def test_notifications_subscribe_the_selected_role_and_are_not_parsed():
    controller = await connected("OKIN-1")
    controller.forward_raw_notification = MagicMock()
    controller.forward_controller_state_updates = MagicMock()
    await controller.start_notify(None)
    char = controller.client.start_notify.call_args.args[0]
    assert char.uuid.lower() == OKIN[2]
    controller._handle_notification(None, bytearray.fromhex("A5 0B 00 00 02 58 03 43"))
    controller.forward_raw_notification.assert_called_once()
    controller.forward_controller_state_updates.assert_not_called()


def test_capabilities_match_the_app_surface():
    controller = make_controller("OKIN-1")
    assert controller.requires_notification_channel
    assert controller.supports_preset_flat and controller.supports_preset_zero_g
    assert controller.supports_preset_lounge and controller.supports_preset_incline
    assert controller.supports_preset_anti_snore and not controller.supports_preset_tv
    assert not controller.supports_memory_presets and not controller.supports_position_feedback
    assert not controller.supports_discrete_light_control
    assert controller.supports_light_toggle_control and controller.supports_massage
    assert controller.supports_massage_off_control
    assert controller.supports_massage_intensity_step_control
    assert not controller.supports_massage_toggle_control
    assert controller.motor_pulse_settings() == (3, 100)
    assert {spec.key for spec in controller.controller_button_specs} == {
        f"adjustable_lumbar_{key}"
        for key in (
            "save_zero_g",
            "save_lounge",
            "save_incline",
            "save_anti_snore",
            "wave_1",
            "wave_2",
            "wave_3",
            "massage_on",
            "check_massage",
        )
    }
