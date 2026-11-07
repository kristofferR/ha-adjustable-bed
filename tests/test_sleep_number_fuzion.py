"""Artifact vectors and encrypted session behavior for Fuzion 5.4.11."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.sleep_number.commands import (
    COMMANDS,
    format_command,
    parse_response,
    validate_temperature_program,
)
from custom_components.adjustable_bed.beds.sleep_number.controller import SleepNumberController
from custom_components.adjustable_bed.const import (
    SLEEP_NUMBER_AUTH_CHAR_UUID,
    SLEEP_NUMBER_BAMKEY_CHAR_UUID,
)

SESSION = bytes.fromhex("123456789abcdef0123456789abcdef0")


def controller_with_client() -> tuple[SleepNumberController, MagicMock]:
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.ble_lock = asyncio.Lock()
    client = coordinator.client
    client.is_connected = True
    client.read_gatt_char = AsyncMock(return_value=SESSION)
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.services.get_characteristic.return_value.max_write_without_response_size = 20
    controller = SleepNumberController(coordinator)
    return controller, client


@pytest.mark.parametrize(
    "raw,reason",
    [(b"", "16-byte"), (bytes(16), "connection limit"), ((1).to_bytes(16, "big"), "rejected")],
)
async def test_invalid_auth_prevents_subscription(raw: bytes, reason: str) -> None:
    controller, client = controller_with_client()
    client.read_gatt_char.return_value = raw
    with pytest.raises(BleakError, match=reason):
        await controller.start_notify()
    client.start_notify.assert_not_awaited()
    assert client.read_gatt_char.await_count == 1


async def test_auth_retries_transport_then_precedes_cccd() -> None:
    controller, client = controller_with_client()
    order: list[str] = []

    async def read(uuid: str) -> bytes:
        assert uuid == SLEEP_NUMBER_AUTH_CHAR_UUID
        order.append("read")
        if len(order) < 3:
            raise BleakError("Insufficient encryption")
        return SESSION

    async def subscribe(uuid: str, callback: object) -> None:
        assert uuid == SLEEP_NUMBER_BAMKEY_CHAR_UUID
        order.append("subscribe")

    client.read_gatt_char.side_effect = read
    client.start_notify.side_effect = subscribe
    await controller.start_notify()
    assert order == ["read", "read", "read", "subscribe"]
    assert controller._session_uuid == SESSION


async def test_session_hint_filter_and_disconnect() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    for raw in (b"hint", bytes.fromhex("ff" * 16), controller._build_bamkey_blob("PASS:ACK")):
        controller._handle_bamkey_notification(None, bytearray(raw))
    assert controller._readback_hint_queue.empty()
    for raw in (SESSION, bytes(16)):
        controller._handle_bamkey_notification(None, bytearray(raw))
        assert controller._readback_hint_queue.get_nowait() is None
    client.is_connected = False
    await controller.stop_notify()
    assert controller._session_uuid is None


async def test_att_slices_once_then_accumulates_read_fragments() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    command = "ACTS left head 10"
    expected = bytes.fromhex("66557a496f4e1f00000041435453206c6566742068656164203130db92c46b")
    written = bytearray()

    async def write(uuid: object, chunk: bytes, *, response: bool) -> None:
        assert not response
        assert len(chunk) <= 20
        written.extend(chunk)
        if len(written) == len(expected):
            controller._handle_bamkey_notification(None, bytearray(SESSION))

    response = controller._build_bamkey_blob("PASS:ACK")
    client.read_gatt_char.side_effect = [response[:3], response[3:10], response[10:]]
    client.write_gatt_char.side_effect = write
    assert await controller._send_bamkey_command("ACTS", "left", "head", "10") == []
    assert bytes(written) == expected
    assert client.write_gatt_char.await_count == 2
    assert controller._parse_bamkey_blob(expected) == command


@pytest.mark.parametrize("chunks", [[b""], [b"invalid preamble"], [b"fUzIoN\x0e\0\0\0xxxxEXTRA"]])
async def test_readback_rejects_invalid_stream(chunks: list[bytes]) -> None:
    controller, client = controller_with_client()
    client.read_gatt_char.side_effect = chunks
    with pytest.raises(ValueError):
        await controller._read_bamkey_response_after_hint(
            remaining_timeout=1, cancel_event=asyncio.Event()
        )


def test_argumentless_halt_vector_has_trailing_space() -> None:
    text = SleepNumberController._format_bamkey_command("ACHA")
    assert text == "ACHA "
    assert (
        SleepNumberController._build_bamkey_blob(text).hex()
        == "66557a496f4e130000004143484120428f7baf"
    )


def test_generated_response_order_is_not_alphabetical() -> None:
    assert parse_response(COMMANDS["get_actuator_movement_status"], ["1", "0", "0", "1"]) == {
        "right_head": "1",
        "right_foot": "0",
        "left_head": "0",
        "left_foot": "1",
    }
    assert parse_response(COMMANDS["get_sleep_number_controls"], ["1", "35", "50"]) == {
        "sleep_number_adjustment_status": "1",
        "ambient_sleep_number": 35,
        "user_sleep_number": 50,
    }


@pytest.mark.parametrize(
    "operation,parameters",
    [
        (
            "set_actuator_target_position",
            {"side": "left", "actuator": "head", "target_actuator_position": True},
        ),
        (
            "set_actuator_target_position",
            {"side": "left", "actuator": "head", "target_actuator_position": 101},
        ),
        ("set_responsive_air_enabled_status", {"side": "left", "responsive_air_enable_flag": "2"}),
        (
            "set_frosty_mode",
            {"side": "left", "frosty_mode_control": "heating_push_low", "cooling_timer_value": 30},
        ),
        ("set_heidi_mode", {"side": "left", "heidi_mode_control": "heater_test_push", "timer": 30}),
        ("set_sleepiq_privacy_state", {"sleepiq_privacy_state": "unknown"}),
        ("halt_all_actuators", {"raw": "SYRS both"}),
    ],
)
def test_service_rejects_unsupported_values_before_writes(
    operation: str, parameters: dict[str, object]
) -> None:
    controller, client = controller_with_client()
    with pytest.raises(ValueError):
        controller.validate_sleep_number_command(operation, parameters)
    client.write_gatt_char.assert_not_called()


def test_auto_light_disable_uses_low_and_bound_side_is_enforced() -> None:
    assert format_command(
        "set_underbed_light_auto_mode",
        {
            "underbed_light_auto_mode_enable_status": "false",
            "underbed_light_auto_mode_intensity_level": "high",
        },
    )[1] == ("false", "low")
    controller, _client = controller_with_client()
    token = controller._command_side.set("left")
    try:
        with pytest.raises(ValueError, match="physical bed side"):
            controller.validate_sleep_number_command("get_current_preset", {"side": "right"})
    finally:
        controller._command_side.reset(token)


def program() -> dict[str, object]:
    return {
        "days": ["Mon", "Fri"],
        "enabled": True,
        "wake_time": "0700",
        "footwarming": "low",
        "id": "synthetic",
        "segments": [
            {
                "core_temperature": "heating_low",
                "end_time": "0700",
                "footwarming": "off",
                "stage": 0,
                "start_time": "2200",
                "type": "fall_asleep",
            }
        ],
        "side": "left",
        "bed_time": "2200",
        "type": "personal",
        "version": 1,
    }


def test_temperature_program_validates_json_specific_modes_and_times() -> None:
    value = program()
    assert validate_temperature_program(value) == value
    spec, args = format_command("create_temperature_program", {"program": value})
    assert spec.key == "TTPC"
    assert '"core_temperature":"heating_low"' in args[0]
    value["wake_time"] = "2460"
    with pytest.raises(ValueError, match="HHmm"):
        validate_temperature_program(value)


async def test_valid_service_returns_typed_fields() -> None:
    controller, _client = controller_with_client()
    controller._send_bamkey_command = AsyncMock(return_value=["1", "35", "50"])
    assert await controller.async_execute_sleep_number_command(
        "get_sleep_number_controls", {"side": "right"}
    ) == {
        "sleep_number_adjustment_status": "1",
        "ambient_sleep_number": 35,
        "user_sleep_number": 50,
    }
    controller._send_bamkey_command.assert_awaited_once_with("SNCG", "right", expected_args=3)


@pytest.mark.parametrize(
    "key,args,expected",
    [
        (
            "ASTM",
            ("right", "foot", "20"),
            "66557a496f4e200000004153544d20726967687420666f6f74203230c927bdd3",
        ),
        (
            "ASTP",
            ("left", "zero_g"),
            "66557a496f4e1e00000041535450206c656674207a65726f5f6779b22e16",
        ),
        (
            "ACPS",
            ("right", "favorite", "30", "15"),
            "66557a496f4e2700000041435053207269676874206661766f72697465203330203135c10f788b",
        ),
        (
            "FWTS",
            ("left", "high", "60"),
            "66557a496f4e1f00000046575453206c65667420686967682036302d805584",
        ),
        (
            "THMS",
            ("right", "heating_push_med", "60"),
            "66557a496f4e2c00000054484d532072696768742068656174696e675f707573685f6d6564203630f8d7585e",
        ),
        ("UBAS", ("false", "low"), "66557a496f4e1c000000554241532066616c7365206c6f77f7f126cb"),
        ("LRAS", ("right", "1"), "66557a496f4e1a0000004c52415320726967687420319d9fb57e"),
        ("SPRS", ("paused",), "66557a496f4e190000005350525320706175736564313bf103"),
    ],
)
def test_frozen_catalog_frame_vectors(key: str, args: tuple[str, ...], expected: str) -> None:
    payload = SleepNumberController._format_bamkey_command(key, *args)
    assert SleepNumberController._build_bamkey_blob(payload).hex() == expected


async def test_configuration_gates_single_chamber_and_thermal_modules() -> None:
    controller, _client = controller_with_client()
    config = [
        "single",
        "yes",
        "yes",
        "no",
        "no",
        "cool",
        "yes",
        "no",
        "no",
        "no",
        "yes",
        "no",
        "no",
        "no",
        "no",
        "no",
    ]
    controller._send_bamkey_command = AsyncMock(
        side_effect=[config, ["0", "35", "50"], ["cooling_pull_low", "60"]]
    )
    controller._ensure_notifications_started = AsyncMock()
    await controller.query_config()
    assert controller._side == "right"
    assert controller.sleep_number_setting_sides == ("right",)
    assert not controller.supports_lights
    assert not controller.supports_memory_programming
    assert not controller.supports_preset_zero_g
    assert controller.thermal_climate_sides == ("right",)
    assert [spec.key for spec in controller.motor_control_specs] == ["back"]
    with pytest.raises(ValueError, match="chamber"):
        controller.validate_sleep_number_command("get_sleep_number_controls", {"side": "left"})
    with pytest.raises(ValueError, match="Core temperature"):
        controller.validate_sleep_number_command("get_heidi_mode", {"side": "right"})


async def test_program_info_and_settings_join_by_id() -> None:
    import json

    controller, _client = controller_with_client()
    complete = program()
    info = {key: value for key, value in complete.items() if key not in {"segments", "footwarming"}}
    settings = {key: complete[key] for key in ("id", "segments", "footwarming")}
    controller._send_bamkey_command = AsyncMock(
        side_effect=[[json.dumps([info])], [json.dumps([settings])]]
    )
    assert await controller.async_execute_sleep_number_command(
        "get_temperature_programs", {"side": "left"}
    ) == {"programs": [complete]}


async def test_cancel_during_readback_releases_transport() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    reading = asyncio.Event()

    async def read(_uuid: str) -> bytes:
        reading.set()
        await asyncio.Event().wait()
        return b""

    async def write(_uuid: str, _chunk: bytes, *, response: bool) -> None:
        controller._handle_bamkey_notification(None, bytearray(SESSION))

    client.write_gatt_char.side_effect = write
    client.read_gatt_char.side_effect = read
    task = asyncio.create_task(controller._send_bamkey_command("ACHA"))
    await asyncio.wait_for(reading.wait(), 1)
    controller._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 1)
    assert not controller.ble_lock.locked()


def test_new_program_omits_nullable_id_and_wake_time_like_gson() -> None:
    import json

    value = program()
    del value["id"]
    del value["wake_time"]
    _spec, args = format_command("create_temperature_program", {"program": value})
    assert "id" not in json.loads(args[0])
    assert "wake_time" not in json.loads(args[0])
    with pytest.raises(ValueError):
        format_command("set_temperature_program", {"program": value})


async def test_missing_optional_program_wake_time_is_normalized() -> None:
    import json

    controller, _client = controller_with_client()
    info = {
        key: value
        for key, value in program().items()
        if key not in {"segments", "footwarming", "wake_time"}
    }
    controller._send_bamkey_command = AsyncMock(side_effect=[[json.dumps([info])], ["[]"]])
    result = await controller.async_execute_sleep_number_command(
        "get_temperature_programs", {"side": "left"}
    )
    programs = result["programs"]
    assert isinstance(programs, list)
    first = programs[0]
    assert isinstance(first, dict)
    assert first["wake_time"] is None
    assert first["footwarming"] == "off"


def test_temperature_segment_stage_matches_artifact_enum_ordinal() -> None:
    value = program()
    segments = value["segments"]
    assert isinstance(segments, list)
    first = segments[0]
    assert isinstance(first, dict)
    first["stage"] = 1
    with pytest.raises(ValueError, match="stage must match"):
        validate_temperature_program(value)


@pytest.mark.parametrize("failure,fallback", [("FAIL:0", True), ("FAIL:2", False)])
async def test_grouped_queries_fall_back_only_for_unknown_command(
    failure: str, fallback: bool
) -> None:
    controller, _client = controller_with_client()
    controller._ensure_bed_presence_channel_primed = AsyncMock()
    controller._send_bamkey_raw_response = AsyncMock(return_value=failure)
    controller._send_bamkey_command = AsyncMock(side_effect=[["in"], ["out"]])
    if fallback:
        assert await controller._read_bed_presence_states() == {"left": "in", "right": "out"}
        assert controller._send_bamkey_command.await_count == 2
    else:
        with pytest.raises(ValueError, match="generic"):
            await controller._read_bed_presence_states()
        controller._send_bamkey_command.assert_not_awaited()


@pytest.mark.parametrize("thermal", ["cool", "heat_cool"])
async def test_optional_state_payload_failure_does_not_abort_hydration(thermal: str) -> None:
    controller, _client = controller_with_client()
    controller._ensure_notifications_started = AsyncMock()
    controller.async_execute_sleep_number_command = AsyncMock(return_value={
        "chamber_type": "dual", "rapid_sleep_setting_enable_flag": "yes",
        "thermal_control_enabled_flag": thermal,
    })
    controller.read_sleep_number_setting_for_side = AsyncMock(side_effect=ValueError("payload"))
    controller.read_footwarming_state_for_side = AsyncMock(side_effect=ValueError("payload"))
    controller.read_frosty_state_for_side = AsyncMock(side_effect=ValueError("payload"))
    controller.read_heidi_state_for_side = AsyncMock(side_effect=ValueError("payload"))
    await controller.query_config()
    assert controller.read_footwarming_state_for_side.await_count == 2
    thermal_read = (controller.read_frosty_state_for_side if thermal == "cool"
                    else controller.read_heidi_state_for_side)
    assert thermal_read.await_count == 2


@pytest.mark.parametrize("error", [BleakError("link"), ConnectionError("link"), TimeoutError()])
async def test_optional_state_transport_failure_still_retries_connection(error: Exception) -> None:
    controller, _client = controller_with_client()
    controller._ensure_notifications_started = AsyncMock()
    controller.async_execute_sleep_number_command = AsyncMock(return_value={
        "chamber_type": "single", "rapid_sleep_setting_enable_flag": "yes",
        "thermal_control_enabled_flag": "none",
    })
    controller.read_sleep_number_setting_for_side = AsyncMock()
    controller.read_footwarming_state_for_side = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await controller.query_config()


@pytest.mark.parametrize("enabled", [True, False])
def test_favorite_recall_and_save_capabilities_agree(enabled: bool) -> None:
    controller, _client = controller_with_client()
    controller._system_config = {"favorite_preset": "yes" if enabled else "no"}
    assert controller.supports_memory_presets is enabled
    assert controller.supports_memory_programming is enabled
    assert controller.memory_slot_count == int(enabled)
