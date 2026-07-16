"""Tests for the SleepSpa S9000AI SLEEPSTAR protocol."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.sleepstar import (
    SleepStarCommands,
    SleepStarController,
    build_anti_snore_config,
    build_cb37_config_query,
    build_cb37_time,
    build_daily_report_query,
    build_environment_address_query,
    build_environment_duration_query,
    build_environment_register_query,
    build_monthly_report_query,
    build_sensor_version_query,
    build_sleep_query_config,
    build_sleep_zone_config,
    build_wrapped_star_time,
    crc16_modbus,
    resolve_sleepstar_variant,
    star_extended,
    star_motor_position,
    star_normal,
    star_query,
    wrap_control_box,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEPSTAR,
    NORDIC_UART_READ_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller


@pytest.fixture
def sleepstar_controller() -> tuple[SleepStarController, MagicMock, MagicMock]:
    """Return a connected controller with a minimal coordinator."""
    client = MagicMock()
    client.is_connected = True
    client.services = []
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()

    coordinator = MagicMock()
    coordinator.client = client
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 1
    coordinator.motor_pulse_delay_ms = 100
    coordinator.address = "AA:BB:CC:DD:EE:47"
    coordinator.handle_controller_state_update = MagicMock()
    coordinator.handle_controller_state_updates = MagicMock()
    coordinator.record_command_trace = MagicMock()
    return SleepStarController(coordinator), coordinator, client


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (star_normal(0x03103001), "5A0103103001A5"),
        (star_extended(13, 9, 1), "5AE0040D090100A5"),
        (star_motor_position(7, 0), "5AF003070000A5"),
        (star_query(0xD0), "5AD000A5"),
        (SleepStarCommands.STOP, "AA00000902075A010310300FA5"),
        (build_sleep_query_config(), "2A0000078100"),
        (build_sensor_version_query(), "2A0000088100"),
        (build_environment_duration_query(), "2A000009810101"),
        (
            build_anti_snore_config(enabled=True, sensitivity=2, motor=3, duration=4),
            "AA00000701080204010300000000",
        ),
        (
            build_sleep_zone_config(zone_type=1, left=2, right=3),
            "AA0000070403030102",
        ),
        (
            build_monthly_report_query(side=0, year=2026, month=7),
            "2A00000786021A07",
        ),
        (
            build_daily_report_query(side=1, year=2026, month=7, day=16),
            "2A00000785031A0710",
        ),
        (build_cb37_config_query(2), "2A000005810902FFFF00002225124B"),
        (build_environment_address_query(), "AA0000090308000200000001B81B"),
        (build_environment_register_query(1), "AA0000090308010300020007A5C8"),
    ],
)
def test_frozen_clean_room_vectors(actual: bytes, expected: str) -> None:
    """Production builders must preserve the frozen Phase 4 packet oracles."""
    assert actual.hex().upper() == expected


def test_time_calibration_frames() -> None:
    """Both CB37 and tunneled Star date/time frames use local wall-clock fields."""
    local = datetime(2026, 7, 16, 13, 45, 30, tzinfo=timezone(timedelta(hours=2)))
    assert build_cb37_time(local).hex().upper() == "AA00000301081A07100D2D1E0402"
    assert build_wrapped_star_time(local).hex().upper() == "AA000009020B5A14071A07100D2D1E04A5"


def test_environment_crc_is_inner_modbus_only() -> None:
    """The environment route uses low-byte-first MODBUS CRC inside the wrapper."""
    assert crc16_modbus(bytes.fromhex("000200000001")) == 0x1BB8


@pytest.mark.parametrize(
    ("manufacturer_data", "expected"),
    [
        ({0xB2: b"\0\0\0\0\0\0\x88"}, "single"),
        ({0xB2: b"\0\0\0\0\0\0\x86"}, "dual"),
        ({0xB2: b"\0\0\0\0\0\0\x99"}, "dual_fallback"),
        ({}, "dual_fallback"),
    ],
)
def test_sleep_monitor_variant_selection(
    manufacturer_data: dict[int, bytes], expected: str
) -> None:
    """Subtype selection exactly follows the SleepSpa S9000AI factory."""
    assert resolve_sleepstar_variant(manufacturer_data) == expected


async def test_factory_builds_distinct_controller() -> None:
    """The new protocol must never pass through the direct BOX25 controller."""
    coordinator = MagicMock()
    controller = await create_controller(
        coordinator,
        BED_TYPE_SLEEPSTAR,
        None,
        None,
        manufacturer_data={0xB2: b"\0\0\0\0\0\0\x88"},
    )
    assert isinstance(controller, SleepStarController)
    assert controller.sleep_monitor_variant == "single"
    assert [spec.key for spec in controller.motor_control_specs] == [
        "head",
        "feet",
        "lumbar",
        "sleepstar_part4",
        "sleepstar_part5",
    ]


async def test_session_subscribes_then_sends_complete_startup_sequence(
    sleepstar_controller: tuple[SleepStarController, MagicMock, MagicMock],
) -> None:
    """Session setup preserves the app's notification-first 100 ms ordering."""
    controller, _coordinator, client = sleepstar_controller
    with patch(
        "custom_components.adjustable_bed.beds.sleepstar._SENDER_CADENCE_SECONDS",
        0,
    ):
        await controller.start_notify()

    client.start_notify.assert_awaited_once()
    assert client.start_notify.await_args.args[0] == NORDIC_UART_READ_CHAR_UUID
    writes = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert writes[0] == build_cb37_config_query(1)
    assert writes[1].startswith(bytes.fromhex("AA0000030108"))
    assert writes[2].startswith(bytes.fromhex("AA000009020B5A1407"))
    assert writes[3:] == [
        build_sensor_version_query(),
        SleepStarCommands.QUERY_MOTORS,
        SleepStarCommands.QUERY_LIGHT,
        build_sleep_query_config(),
        build_environment_duration_query(),
        build_environment_address_query(),
    ]
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.await_args_list)
    await controller.stop_notify()


async def test_movement_preset_and_memory_cadence(
    sleepstar_controller: tuple[SleepStarController, MagicMock, MagicMock],
) -> None:
    """Movement and recall guarantee STOP while store uses the app's 55 writes."""
    controller, _coordinator, _client = sleepstar_controller
    controller._session_initialized = True
    controller._notify_started = True
    with (
        patch.object(controller, "write_command", AsyncMock()) as write,
        patch(
            "custom_components.adjustable_bed.beds.sleepstar._SENDER_CADENCE_SECONDS",
            0,
        ),
    ):
        await controller.move_head_up()
        await controller.preset_zero_g()
        await controller.program_memory(2)

    assert write.await_args_list[0].args == (SleepStarCommands.HEAD_UP,)
    assert write.await_args_list[0].kwargs == {
        "repeat_count": 1,
        "repeat_delay_ms": 100,
    }
    assert write.await_args_list[1].args == (SleepStarCommands.STOP,)
    assert write.await_args_list[2].args == (SleepStarCommands.PRESET_ZERO_G,)
    assert write.await_args_list[2].kwargs["repeat_count"] == 3
    assert write.await_args_list[3].args == (SleepStarCommands.STOP,)
    assert write.await_args_list[4].args == (SleepStarCommands.STORE_MEMORY_2,)
    assert write.await_args_list[4].kwargs["repeat_count"] == 55


async def test_sonic_intensity_and_timer_use_two_writes_then_stop(
    sleepstar_controller: tuple[SleepStarController, MagicMock, MagicMock],
) -> None:
    """Sonic controls retain the S9000AI repeat and release behavior."""
    controller, _coordinator, _client = sleepstar_controller
    with (
        patch.object(controller, "write_command", AsyncMock()) as write,
        patch(
            "custom_components.adjustable_bed.beds.sleepstar._SENDER_CADENCE_SECONDS",
            0,
        ),
    ):
        await controller.set_massage_intensity("all", 6)
        await controller.set_massage_timer(20)

    assert write.await_args_list[0].args[0] == wrap_control_box(star_extended(0x11, 6, 6))
    assert write.await_args_list[0].kwargs["repeat_count"] == 2
    assert write.await_args_list[1].args == (SleepStarCommands.STOP,)
    assert write.await_args_list[2].args[0] == wrap_control_box(star_extended(0x0B, 2))
    assert write.await_args_list[3].args == (SleepStarCommands.STOP,)


async def test_direct_and_wrapped_motor_notifications_are_parsed(
    sleepstar_controller: tuple[SleepStarController, MagicMock, MagicMock],
) -> None:
    """Both notification routes map all six proven position bytes."""
    controller, coordinator, _client = sleepstar_controller
    callback = MagicMock()
    controller._notify_callback = callback
    inner = bytes.fromhex("A5000D000A141E28323C46")

    controller._on_notification(1, bytearray(inner))
    controller._on_notification(1, bytearray(wrap_control_box(inner)))

    expected = {
        "head": 10.0,
        "feet": 30.0,
        "lumbar": 50.0,
        "sleepstar_part4": 70.0,
        "sleepstar_part5": 20.0,
    }
    assert controller._positions == expected
    assert callback.call_count == 10
    updates = coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates == {
        "sleepstar_part6_position": 40,
        "sleepstar_positions": {key: int(value) for key, value in expected.items()},
    }


async def test_config_bitmap_requests_only_missing_pages(
    sleepstar_controller: tuple[SleepStarController, MagicMock, MagicMock],
) -> None:
    """Page 1 capability bitmap fans out to each advertised config page once."""
    controller, coordinator, _client = sleepstar_controller
    page1 = bytes([0x2A, 0, 0, 5, 0x81, 9, 0b00001011, 1, 0x1F, 2, 3, 4, 5]) + bytes(7)
    with (
        patch.object(controller, "_write_frame", AsyncMock()) as write,
        patch(
            "custom_components.adjustable_bed.beds.sleepstar._SENDER_CADENCE_SECONDS",
            0,
        ),
    ):
        controller._on_notification(1, bytearray(page1))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert [call.args[0] for call in write.await_args_list] == [
        build_cb37_config_query(2),
        build_cb37_config_query(4),
    ]
    updates = coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["sleepstar_motor_mask"] == 0x1F
    assert updates["sleepstar_config_loaded"] is False
    await controller.stop_keepalive()


def test_short_transparent_wrapper_is_rejected(
    sleepstar_controller: tuple[SleepStarController, MagicMock, MagicMock],
) -> None:
    """The declared transparent payload length must be present before parsing."""
    controller, coordinator, _client = sleepstar_controller
    truncated = bytes.fromhex("AA000009020BA5000D000A")
    controller._on_notification(1, bytearray(truncated))
    coordinator.handle_controller_state_updates.assert_not_called()


def test_control_box_wrapper_rejects_oversized_payload() -> None:
    """The one-byte wrapper length cannot encode payloads larger than 255 bytes."""
    with pytest.raises(ValueError, match="too long"):
        wrap_control_box(bytes(256))
