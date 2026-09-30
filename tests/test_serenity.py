"""Frozen S01 Serenity vectors, parser branches and release lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.serenity import SerenityController


def make_controller(properties=("write",)) -> SerenityController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.motor_count = 4
    coordinator.client = MagicMock(
        is_connected=True,
        services=[
            MagicMock(
                uuid="62741523-52f9-8864-b1ab-3b3a8d65950b",
                characteristics=[
                    MagicMock(
                        uuid="62741525-52f9-8864-b1ab-3b3a8d65950b", properties=properties, handle=1
                    ),
                    MagicMock(
                        uuid="62741625-52f9-8864-b1ab-3b3a8d65950b", properties=["notify"], handle=2
                    ),
                ],
            )
        ],
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock(return_value=b"CST13")
    coordinator.client.services.append(
        MagicMock(
            uuid="0000180a-0000-1000-8000-00805f9b34fb",
            characteristics=[
                MagicMock(
                    uuid="00002a29-0000-1000-8000-00805f9b34fb", properties=["read"], handle=3
                )
            ],
        )
    )
    return SerenityController(coordinator)


def written(controller: SerenityController) -> list[str]:
    return [call.args[1].hex() for call in controller.client.write_gatt_char.call_args_list]


# Each source command row is represented independently, including duplicated
# touch/voice endpoints. CMD32's unsafe head-up-as-stop is excluded explicitly.
ROWS = (
    (1, "head_up", "0c02000000010000000000000000"),
    (2, "head_down", "0c02000000020000000000000000"),
    (3, "foot_up", "0c02000000040000000000000000"),
    (4, "foot_down", "0c02000000080000000000000000"),
    (5, "selector_4_up", "0c02000000100000000000000000"),
    (6, "selector_4_down", "0c02000000200000000000000000"),
    (7, "selector_5_up", "0c02000000400000000000000000"),
    (8, "selector_5_down", "0c02000000800000000000000000"),
    (9, "flat", "0c02080000000000000000000000"),
    (10, "zero_g", "0c02000010000000000000000000"),
    (11, "memory_1", "0c02000100000000000000000000"),
    (12, "tv", "0c02000040000000000000000000"),
    (13, "memory_2", "0c02000400000000000000000000"),
    (14, "save_zero_g", "0c02080010000000000000000000"),
    (15, "save_memory_1", "0c02080100000000000000000000"),
    (16, "save_tv", "0c02080040000000000000000000"),
    (17, "save_memory_2", "0c02080400000000000000000000"),
    (18, "massage_head_cycle", "0c02000008000000000000000000"),
    (19, "massage_foot_cycle", "0c02000004000000000000000000"),
    (20, "massage_mode_cycle", "0c02100000000000000000000000"),
    (21, "massage_timer_cycle", "0c02000002000000000000000000"),
    (22, "massage_toggle", "0c02000001000000000000000000"),
    (23, "light_toggle", "0c02000200000000000000000000"),
    (24, "head_up", "0c02000000010000000000000000"),
    (25, "head_down", "0c02000000020000000000000000"),
    (26, "foot_up", "0c02000000040000000000000000"),
    (27, "foot_down", "0c02000000080000000000000000"),
    (28, "selector_5_up", "0c02000000400000000000000000"),
    (29, "selector_5_down", "0c02000000800000000000000000"),
    (30, "selector_4_up", "0c02000000100000000000000000"),
    (31, "selector_4_down", "0c02000000200000000000000000"),
    (32, None, "0c02000000000000000000000000"),
    (33, "leisure", "0c02000020000000000000000000"),
    (34, "zero_g", "0c02000010000000000000000000"),
    (35, "anti_snore", "0c02000080000000000000000000"),
    (36, "tv", "0c02000040000000000000000000"),
    (37, "flat", "0c02080000000000000000000000"),
    (38, "wave_1", "0c02000000000008000000000000"),
    (39, "wave_2", "0c02000000000010000000000000"),
    (40, "wave_3", "0c02000000000020000000000000"),
    (41, "massage_off", "0c02020000000000000000000000"),
    (42, "light_on", "0c02000000000000004000000000"),
    (43, "light_off", "0c02000000000000008000000000"),
    (44, "light_toggle", "0c02000200000000000000000000"),
    (45, None, "0c02000000000000000000000000"),
)


@pytest.mark.parametrize(("row", "action", "expected"), ROWS)
@pytest.mark.asyncio
async def test_all45_artifact_rows_or_explicit_safe_stop(
    row: int, action: str | None, expected: str
) -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        if action is None:
            await controller.stop_all()
        else:
            await controller.hold_control(action, 250)
    frames = written(controller)
    assert frames[-2:] == ["0c02000000000000000000000000"] * 2
    # Mocked sleeps do not advance the clock: both offsets share one origin.
    assert 0.09 < sleep.call_args_list[-2].args[0] <= 0.1
    assert 0.19 < sleep.call_args_list[-1].args[0] <= 0.2
    if action is None:
        assert frames == [expected] * 2
    else:
        assert frames[:-2] and set(frames[:-2]) == {expected}


def status(code: int, *, alarm: bool = False) -> bytearray:
    payload = bytearray(11)
    payload[1] = 12 if alarm else 99  # Source does not validate header/framing.
    payload[10] = code
    return payload


def test_signed_status_change_only_save_diversion_and_short_input() -> None:
    controller = make_controller()
    controller._handle_notification(None, bytearray(10))
    assert controller.protocol_diagnostics.get("serenity_status_code") is None
    controller._handle_notification(None, status(2))
    assert controller.protocol_diagnostics["serenity_massage_timer_minutes"] == 20
    controller._coordinator.handle_controller_state_updates.reset_mock()
    controller._handle_notification(None, status(2))
    controller._coordinator.handle_controller_state_updates.assert_not_called()
    controller._save_code = 8
    controller._handle_notification(None, status(3))
    assert controller.protocol_diagnostics["serenity_save_event_code"] == 8
    assert controller.protocol_diagnostics["serenity_massage_timer_code"] == 2
    assert controller.protocol_diagnostics["save_pending_code"] == 0
    controller._handle_notification(None, status(128))
    assert controller.protocol_diagnostics["serenity_status_code"] == -128
    assert controller.protocol_diagnostics["serenity_massage_timer_code"] == -128
    assert controller.protocol_diagnostics["serenity_massage_timer_minutes"] is None


@pytest.mark.parametrize(
    ("subtype", "mapped"),
    [(1, 9), (2, 17), (3, 18), (4, 16), (5, 20), (6, 19), (7, 18), (8, 9), (9, 21)],
)
def test_live_alarm_reply_with_dead_alarm_controls(subtype: int, mapped: int) -> None:
    controller = make_controller()
    payload = status(3, alarm=True)
    payload[4:8] = bytes([128, subtype, 129, 255])
    payload[9] = 1
    controller._handle_notification(None, payload)
    assert controller.protocol_diagnostics["serenity_alarm_type"] == mapped
    assert controller.protocol_diagnostics["serenity_alarm_repeat"] == -128
    assert controller.protocol_diagnostics["serenity_alarm_hour"] == -127
    assert controller.protocol_diagnostics["serenity_alarm_minute"] == -1
    assert controller.protocol_diagnostics["serenity_alarm_on"] is True
    payload[5] = 99
    controller._handle_notification(None, payload)
    assert controller.protocol_diagnostics["serenity_alarm_type"] == mapped
    assert not controller.supports_clock_alarm
    assert not controller.supports_clock_sync


def test_exact_capabilities_no_guessed_extra_axes() -> None:
    controller = make_controller()
    assert tuple(spec.key for spec in controller.motor_control_specs) == ("head", "feet")
    assert all(spec.scheduler_resource == "*" for spec in controller.motor_control_specs)
    assert controller.memory_slot_names == ("M1", "M2")
    assert controller.memory_slot_count == 2
    assert controller.supports_preset_tv and controller.supports_preset_lounge
    assert controller.supports_lights and controller.supports_discrete_light_control
    assert controller.requires_notification_channel
    assert not controller.supports_position_feedback
    assert not controller.supports_simultaneous_movement
    assert not controller.has_lumbar_support
    assert not controller.supports_massage_intensity_step_control
    assert not controller.supports_head_massage_intensity_step_control
    assert not controller.supports_foot_massage_intensity_step_control
    assert not controller.supports_preset_incline
    assert not controller.supports_clock_alarm
    assert not controller.supports_clock_sync
    assert not controller.supports_alarm
    assert not controller.supports_light_color_control
    assert not controller.supports_light_level_control
    assert not controller.supports_light_state_feedback
    assert not controller.supports_child_lock
    assert not controller.supports_sync
    assert not controller.supports_device_rename
    assert not controller.supports_factory_reset
    assert not controller.supports_reset_defaults
    assert not controller.supports_control_mode_configuration
    assert not controller.has_tilt_support
    assert not controller.has_neck_support
    assert not controller.has_pillow_support
    assert not controller.supports_direct_position_control
    assert len(controller.held_control_options) == 31


@pytest.mark.parametrize(
    "action",
    ["selector_4_up", "selector_5_down", "save_tv", "save_zero_g", "massage_head_cycle", "wave_3"],
)
@pytest.mark.asyncio
async def test_literal_buttons_bound_callback(action: str) -> None:
    controller = make_controller()
    spec = next(
        spec for spec in controller.controller_button_specs if spec.key == f"serenity_{action}"
    )
    with patch("asyncio.sleep", new=AsyncMock()):
        await spec.press_fn(controller.bind_side("right"))
    assert written(controller)[0] == next(expected for _, key, expected in ROWS if key == action)


@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("preset_memory", (1,), "0c02000100000000000000000000"),
        ("preset_memory", (2,), "0c02000400000000000000000000"),
        ("program_memory", (1,), "0c02080100000000000000000000"),
        ("program_memory", (2,), "0c02080400000000000000000000"),
        ("preset_tv", (), "0c02000040000000000000000000"),
        ("massage_mode_step", (), "0c02100000000000000000000000"),
        ("massage_toggle", (), "0c02000001000000000000000000"),
        ("lights_on", (), "0c02000000000000004000000000"),
        ("lights_off", (), "0c02000000000000008000000000"),
    ],
)
@pytest.mark.asyncio
async def test_public_controller_actions(method: str, args: tuple[int, ...], expected: str) -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()):
        await getattr(controller, method)(*args)
    assert written(controller)[0] == expected


@pytest.mark.asyncio
async def test_real_elapsed_ceiling_and_two_delayed_releases() -> None:
    controller = make_controller()
    timestamps = []
    start = asyncio.get_running_loop().time()

    async def record(*args, **kwargs) -> None:
        timestamps.append(asyncio.get_running_loop().time() - start)

    controller.client.write_gatt_char.side_effect = record
    await controller.hold_control("head_up", 250)
    assert len(timestamps) == 5
    assert all(timestamp < 0.25 for timestamp in timestamps[:-2])
    assert timestamps[-2] >= 0.35 and timestamps[-1] >= 0.45


@pytest.mark.asyncio
async def test_cancelled_task_and_signal_cannot_suppress_two_stop_frames() -> None:
    controller = make_controller()
    started = asyncio.Event()

    async def block(uuid, packet, **kwargs) -> None:
        if packet != bytes.fromhex("0c02000000000000000000000000"):
            started.set()
            await asyncio.Event().wait()

    controller.client.write_gatt_char.side_effect = block
    task = asyncio.create_task(controller.hold_control("head_up", 1000))
    await started.wait()
    controller._coordinator.cancel_command.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(controller)[-2:] == ["0c02000000000000000000000000"] * 2


@pytest.mark.parametrize(
    "error", [BleakError("read failed"), OSError("gone"), TimeoutError("deadline")]
)
@pytest.mark.asyncio
async def test_notification_subscription_required_manufacturer_failure_optional(
    error: Exception,
) -> None:
    controller = make_controller()
    controller.client.read_gatt_char.side_effect = error
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        await controller.start_notify()
    assert sleep.call_args.args == (1,)
    controller.client.start_notify.assert_awaited_once()
    controller.client.read_gatt_char.assert_awaited_once_with(
        "00002a29-0000-1000-8000-00805f9b34fb"
    )
    assert controller.protocol_diagnostics.get("serenity_manufacturer") is None


@pytest.mark.asyncio
async def test_manufacturer_no_capability_selection_or_alarm_enable() -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify()
    assert controller.protocol_diagnostics["serenity_manufacturer"] == "CST13"
    assert not controller.supports_clock_alarm
    assert controller.memory_slot_count == 2


@pytest.mark.parametrize(
    "properties", [("write",), ("write-without-response",), ("write", "write-without-response")]
)
@pytest.mark.asyncio
async def test_property_write_policy(properties: tuple[str, ...]) -> None:
    controller = make_controller(properties)
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.stop_all()
    assert controller.client.write_gatt_char.call_args.kwargs["response"] == ("write" in properties)


@pytest.mark.parametrize("invalid", ["head_up+foot_up", "query_massage", "save_leisure", ""])
@pytest.mark.asyncio
async def test_unsupported_actions_no_write(invalid: str) -> None:
    controller = make_controller()
    with pytest.raises(ValueError):
        await controller.hold_control(invalid, 100)
    assert written(controller) == []


@pytest.mark.parametrize("role", ["write", "notify"])
@pytest.mark.parametrize("invalid", ["wrong_service", "missing", "duplicate", "wrong_property"])
@pytest.mark.asyncio
async def test_exact_gatt_roles_fail_before_subscription(role: str, invalid: str) -> None:
    controller = make_controller()
    service = controller.client.services[0]
    characteristic = service.characteristics[0 if role == "write" else 1]
    if invalid == "wrong_service":
        service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    elif invalid == "missing":
        service.characteristics.remove(characteristic)
    elif invalid == "duplicate":
        service.characteristics.append(characteristic)
    else:
        characteristic.properties = ["read"]
    with pytest.raises(ValueError):
        await controller.start_notify()
    controller.client.start_notify.assert_not_awaited()
    controller.client.read_gatt_char.assert_not_awaited()
    assert written(controller) == []


@pytest.mark.parametrize(
    "invalid",
    ["wrong_service", "missing", "duplicate", "wrong_property", "disconnected", "no_client"],
)
@pytest.mark.asyncio
async def test_manufacturer_exact_optional_role(invalid: str) -> None:
    controller = make_controller()
    client = controller.client
    service = client.services[1]
    if invalid == "wrong_service":
        service.uuid = "62741523-52f9-8864-b1ab-3b3a8d65950b"
    elif invalid == "missing":
        service.characteristics.clear()
    elif invalid == "duplicate":
        service.characteristics.append(service.characteristics[0])
    elif invalid == "wrong_property":
        service.characteristics[0].properties = ["notify"]
    elif invalid == "disconnected":
        client.is_connected = False
    else:
        controller._coordinator.client = None
    await controller.refresh_manufacturer()
    client.read_gatt_char.assert_not_awaited()
    assert "serenity_manufacturer" not in controller.protocol_diagnostics


@pytest.mark.asyncio
async def test_manufacturer_subscription_order_and_explicit_refresh_button() -> None:
    controller = make_controller()
    order: list[object] = []

    async def subscribe(*args) -> None:
        order.append("subscribe")

    async def delay(seconds: float) -> None:
        order.append(seconds)

    async def read(*args) -> bytes:
        order.append("read")
        return b"CST14\xff"

    controller.client.start_notify.side_effect = subscribe
    controller.client.read_gatt_char.side_effect = read
    with patch("asyncio.sleep", new=delay):
        await controller.start_notify()
    assert order == ["subscribe", 1, "read"]
    assert controller.protocol_diagnostics["serenity_manufacturer"] == "CST14\ufffd"
    assert not controller.supports_clock_alarm
    order.clear()
    spec = next(
        spec
        for spec in controller.controller_button_specs
        if spec.key == "serenity_refresh_manufacturer"
    )
    await spec.press_fn(controller.bind_side("left"))
    assert order == ["read"]
    assert written(controller) == []


@pytest.mark.asyncio
async def test_notification_setup_has_only_subscription_and_information_read() -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify()
    assert [call[0] for call in controller.client.method_calls] == [
        "start_notify",
        "read_gatt_char",
    ]
    assert controller.client.start_notify.call_args.args == (
        "62741625-52f9-8864-b1ab-3b3a8d65950b",
        controller._handle_notification,
    )
    assert written(controller) == []


@pytest.mark.parametrize(
    ("action", "pending"),
    [("save_zero_g", 5), ("save_memory_1", 4), ("save_tv", 6), ("save_memory_2", 8)],
)
@pytest.mark.asyncio
async def test_save_pending_survives_release_nonrecall_and_duplicate_status(
    action: str, pending: int
) -> None:
    controller = make_controller()
    controller._handle_notification(None, status(2))
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control(action, 100)
        await controller.stop_all()
        await controller.hold_control("light_toggle", 100)
        await controller.hold_control("head_up", 100)
    assert controller.protocol_diagnostics["save_pending_code"] == pending
    controller._handle_notification(None, status(2))
    assert controller.protocol_diagnostics["save_pending_code"] == pending
    assert "serenity_save_event_code" not in controller.protocol_diagnostics
    controller._handle_notification(None, status(3, alarm=True))
    assert controller.protocol_diagnostics["save_pending_code"] == pending
    controller._handle_notification(None, status(3))
    assert controller.protocol_diagnostics["serenity_save_event_code"] == pending
    assert controller.protocol_diagnostics["save_pending_code"] == 0
    assert controller.protocol_diagnostics["serenity_massage_timer_minutes"] == 20
    controller._handle_notification(None, status(1))
    assert controller.protocol_diagnostics["serenity_massage_timer_minutes"] == 10


@pytest.mark.parametrize(
    "action", ["flat", "zero_g", "memory_1", "tv", "memory_2", "leisure", "anti_snore"]
)
@pytest.mark.asyncio
async def test_recall_clears_prior_save_code(action: str) -> None:
    controller = make_controller()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control("save_memory_1", 100)
        await controller.hold_control(action, 100)
    assert controller.protocol_diagnostics["save_pending_code"] == 0
    controller._handle_notification(None, status(2))
    assert controller.protocol_diagnostics["serenity_massage_timer_minutes"] == 20
    assert "serenity_save_event_code" not in controller.protocol_diagnostics


@pytest.mark.parametrize(
    ("method", "action", "duration"),
    [
        ("preset_flat", "flat", 1500),
        ("preset_zero_g", "zero_g", 500),
        ("preset_anti_snore", "anti_snore", 500),
        ("preset_lounge", "leisure", 500),
        ("preset_tv", "tv", 500),
        ("lights_toggle", "light_toggle", 500),
        ("lights_on", "light_on", 500),
        ("lights_off", "light_off", 500),
        ("massage_off", "massage_off", 500),
        ("massage_toggle", "massage_toggle", 500),
        ("massage_mode_step", "massage_mode_cycle", 500),
    ],
)
@pytest.mark.asyncio
async def test_default_public_action_elapsed_duration(
    method: str, action: str, duration: int
) -> None:
    controller = make_controller()
    with patch.object(controller, "hold_control", new=AsyncMock()) as hold:
        await getattr(controller, method)()
    hold.assert_awaited_once_with(action, duration)


@pytest.mark.asyncio
async def test_inherited_wave_routes_use_reachable_direct_frames() -> None:
    controller = make_controller()
    with patch.object(controller, "hold_control", new=AsyncMock()) as hold:
        await controller.massage_wave_next()
        await controller.massage_wave_next()
        await controller.massage_wave_next()
        await controller.massage_wave_next()
        await controller.massage_wave_previous()
    assert [call.args for call in hold.await_args_list] == [
        ("wave_1", 500),
        ("wave_2", 500),
        ("wave_3", 500),
        ("wave_1", 500),
        ("wave_3", 500),
    ]


@pytest.mark.asyncio
async def test_both_release_attempts_survive_first_write_error() -> None:
    controller = make_controller()
    with (
        patch.object(
            controller,
            "write_command",
            new=AsyncMock(side_effect=[BleakError("first release failed"), None]),
        ) as write,
        patch("asyncio.sleep", new=AsyncMock()) as delay,
        pytest.raises(BleakError, match="first release failed"),
    ):
        await controller.stop_all()
    assert write.await_count == 2
    assert 0.09 < delay.await_args_list[0].args[0] <= 0.1
    assert 0.19 < delay.await_args_list[1].args[0] <= 0.2
    assert all(not call.kwargs["cancel_event"].is_set() for call in write.await_args_list)


@pytest.mark.asyncio
async def test_repeated_task_cancellation_during_release_keeps_both_frames() -> None:
    controller = make_controller()
    first = asyncio.Event()
    proceed = asyncio.Event()

    async def write(*args, **kwargs) -> None:
        first.set()
        await proceed.wait()

    controller.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.stop_all())
    await first.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    proceed.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(controller) == ["0c02000000000000000000000000"] * 2


@pytest.mark.parametrize("first_write_ms", [70, 170])
@pytest.mark.asyncio
async def test_release_deadlines_share_origin_despite_write_latency(first_write_ms: int) -> None:
    controller = make_controller()
    timestamps: list[float] = []
    loop = asyncio.get_running_loop()
    started = loop.time()

    async def write(*args, **kwargs) -> None:
        timestamps.append(loop.time() - started)
        if len(timestamps) == 1:
            await asyncio.sleep(first_write_ms / 1000)

    controller.client.write_gatt_char.side_effect = write
    await controller.stop_all()
    assert len(timestamps) == 2
    assert 0.09 <= timestamps[0] < 0.14
    expected = max(0.2, timestamps[0] + first_write_ms / 1000)
    assert expected <= timestamps[1] < expected + 0.04


@pytest.mark.parametrize("duration", [0, -1, 60001, True, False, 1.5, "100"])
@pytest.mark.asyncio
async def test_invalid_hold_duration_fails_without_write(duration: object) -> None:
    controller = make_controller()
    with pytest.raises(ValueError, match="Duration"):
        await controller.hold_control("head_up", duration)
    assert written(controller) == []


@pytest.mark.parametrize("slot", [0, 3, True, False, -1])
@pytest.mark.parametrize("method", ["preset_memory", "program_memory"])
@pytest.mark.asyncio
async def test_invalid_memory_slot_fails_without_write(method: str, slot: int) -> None:
    controller = make_controller()
    with pytest.raises(ValueError, match="only M1 and M2"):
        await getattr(controller, method)(slot)
    assert written(controller) == []


@pytest.mark.asyncio
async def test_write_timeout_is_not_mistaken_for_elapsed_hold_deadline() -> None:
    controller = make_controller()
    with (
        patch.object(
            controller,
            "write_command",
            new=AsyncMock(side_effect=[TimeoutError("ATT deadline"), None, None]),
        ) as write,
        patch("asyncio.sleep", new=AsyncMock()),
        pytest.raises(TimeoutError, match="ATT deadline"),
    ):
        await controller.hold_control("head_up", 1000)
    assert write.await_count == 3
    assert all(
        call.args[0] == bytes.fromhex("0c02000000000000000000000000")
        for call in write.await_args_list[-2:]
    )


def test_initial_zero_status_and_alarm_off_do_not_invent_state() -> None:
    controller = make_controller()
    controller._handle_notification(None, status(0))
    assert "serenity_status_code" not in controller.protocol_diagnostics
    payload = status(4, alarm=True)
    payload[5] = 99
    payload[9] = 2
    controller._handle_notification(None, payload)
    assert controller.protocol_diagnostics["serenity_alarm_type"] == 0
    assert controller.protocol_diagnostics["serenity_alarm_on"] is False
    assert "serenity_status_code" not in controller.protocol_diagnostics


@pytest.mark.parametrize("aborted", ["failed_write", "already_cancelled"])
async def test_aborted_save_retains_artifact_local_intent_without_storage_ack(aborted):
    controller = make_controller()
    if aborted == "already_cancelled":
        controller._coordinator.cancel_command.set()
    else:

        async def fail_save(_characteristic, payload, **kwargs):
            if payload.hex() == "0c02080100000000000000000000":
                raise ValueError("first save write unavailable")

        controller.client.write_gatt_char.side_effect = fail_save
    with patch("asyncio.sleep", new=AsyncMock()):
        if aborted == "failed_write":
            with pytest.raises(ValueError, match="first save write unavailable"):
                await controller.hold_control("save_memory_1", 100)
        else:
            await controller.hold_control("save_memory_1", 100)
    assert controller.protocol_diagnostics["save_pending_code"] == 4
    assert written(controller)[-2:] == ["0c02000000000000000000000000"] * 2
    controller._handle_notification(None, status(1))
    assert controller.protocol_diagnostics["serenity_save_event_code"] == 4
    assert controller.protocol_diagnostics["save_pending_code"] == 0
    assert "serenity_massage_timer_code" not in controller.protocol_diagnostics


async def test_notification_during_first_save_write_consumes_local_intent():
    controller = make_controller()

    async def notify_before_write_returns(_characteristic, payload, **kwargs):
        if payload.hex() == "0c02080100000000000000000000":
            controller._handle_notification(None, status(1))
            assert controller.protocol_diagnostics["serenity_save_event_code"] == 4

    controller.client.write_gatt_char.side_effect = notify_before_write_returns
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control("save_memory_1", 100)
    assert controller.protocol_diagnostics["save_pending_code"] == 0
    assert "serenity_massage_timer_code" not in controller.protocol_diagnostics


@pytest.mark.parametrize("action", ["save_zero_g", "save_tv", "save_memory_1", "save_memory_2"])
async def test_default_save_gesture_matches_bound_five_second_app_help(action):
    controller = make_controller()
    with patch.object(controller, "hold_control", new=AsyncMock()) as hold:
        if action.startswith("save_memory_"):
            await controller.program_memory(int(action[-1]))
        else:
            spec = next(
                spec
                for spec in controller.controller_button_specs
                if spec.key == f"serenity_{action}"
            )
            await spec.press_fn(controller)
    hold.assert_awaited_once_with(action, 5000)
