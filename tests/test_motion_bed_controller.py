"""Motion Bed exact-client identity, command cleanup and callback lifetime tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.motion_bed.actions import ACTION_BY_KEY
from custom_components.adjustable_bed.beds.motion_bed.controller import (
    CHARACTERISTIC,
    STOP,
    MotionBedController,
    button_actions_for,
)
from custom_components.adjustable_bed.beds.motion_bed.models import select_motion_bed
from custom_components.adjustable_bed.beds.motion_bed.protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.beds.motion_bed.requests import MotionBedWrite
from custom_components.adjustable_bed.beds.motion_bed.state import MotionBedFollowup


def characteristic(handle: int, *, properties: tuple[str, ...] = ("write", "notify")) -> MagicMock:
    char = MagicMock()
    char.uuid = CHARACTERISTIC
    char.handle = handle
    char.properties = list(properties)
    return char


def client_for(*chars: MagicMock) -> MagicMock:
    client = MagicMock()
    client.is_connected = True
    client.services = [MagicMock(characteristics=[char]) for char in chars]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    return client


@dataclass
class Rig:
    controller: MotionBedController
    coordinator: MagicMock
    client: MagicMock
    first: MagicMock
    last: MagicMock

    @property
    def callback(self) -> Callable[[object, bytearray], None]:
        return self.client.start_notify.call_args.args[1]

    @property
    def writes(self) -> list[bytes]:
        return [call.args[1] for call in self.client.write_gatt_char.await_args_list]


def rig_for(name: str = "QMS-IQ", *, stub_startup: bool = True) -> Rig:
    first, last = characteristic(11), characteristic(29)
    client = client_for(first, last)
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:01"
    coordinator.client = client
    coordinator.cancel_command = asyncio.Event()
    coordinator.hass.async_create_task.side_effect = asyncio.create_task
    controller = MotionBedController(coordinator, selection=select_motion_bed(name))
    coordinator.controller = controller
    coordinator._controller = controller
    coordinator._client = client

    async def execute(command: Callable[[BedController], Awaitable[None]], **kwargs: object) -> None:
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    coordinator.async_execute_controller_query = AsyncMock(side_effect=execute)
    if stub_startup:
        controller._startup = AsyncMock()
    return Rig(controller, coordinator, client, first, last)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "properties,response",
    [
        (("write", "notify"), True),
        (("write-without-response", "notify"), False),
        (("write", "write-without-response", "indicate"), True),
    ],
)
async def test_last_ffe1_object_owns_notifications_writes_and_stop(
    properties: tuple[str, ...], response: bool
) -> None:
    rig = rig_for()
    rig.last.properties = list(properties)
    await rig.controller.start_notify()
    assert rig.client.start_notify.await_args.args[0] is rig.last
    await rig.controller.write_command(STOP)
    assert rig.client.write_gatt_char.await_args.args[0] is rig.last
    assert rig.client.write_gatt_char.await_args.kwargs["response"] is response
    await rig.controller.stop_notify()
    assert rig.client.stop_notify.await_args.args[0] is rig.last


@pytest.mark.asyncio
@pytest.mark.parametrize("properties", [("notify",), ("write",), ()])
async def test_invalid_last_duplicate_never_falls_back(properties: tuple[str, ...]) -> None:
    rig = rig_for()
    rig.last.properties = list(properties)
    with pytest.raises(ValueError):
        await rig.controller.start_notify()
    rig.client.start_notify.assert_not_awaited()
    rig.client.write_gatt_char.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_characteristic_and_disconnected_client_fail_before_writes() -> None:
    rig = rig_for()
    rig.client.services = []
    with pytest.raises(ValueError):
        await rig.controller.async_discover_capabilities()
    rig.client.is_connected = False
    with pytest.raises(ConnectionError):
        await rig.controller.async_discover_capabilities()
    rig.client.write_gatt_char.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_sender_identity_and_old_client_callbacks() -> None:
    rig = rig_for()
    await rig.controller.start_notify()
    callback = rig.callback
    callback(rig.first, bytearray.fromhex("FFFFFFFF05000109"))
    assert rig.controller.protocol_diagnostics["brightness"] is None
    callback(characteristic(rig.last.handle), bytearray.fromhex("FFFFFFFF05000109"))
    assert rig.controller.protocol_diagnostics["brightness"] is None
    callback(rig.last, bytearray.fromhex("FFFFFFFF05000109"))
    assert rig.controller.protocol_diagnostics["brightness"] == 9
    new = client_for(characteristic(50))
    rig.coordinator.client = new
    callback(rig.last, bytearray.fromhex("FFFFFFFF05000102"))
    assert rig.controller.protocol_diagnostics["brightness"] == 9
    await rig.controller.async_discover_capabilities()
    assert rig.controller.protocol_diagnostics["brightness"] is None
    callback(rig.last, bytearray.fromhex("FFFFFFFF05000102"))
    assert rig.controller.protocol_diagnostics["brightness"] is None
    await rig.controller.stop_notify()


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", [False, True])
async def test_address_changed_or_disconnected_callback_does_not_mutate_state(
    disconnect: bool,
) -> None:
    rig = rig_for()
    await rig.controller.start_notify()
    if disconnect:
        rig.client.is_connected = False
    else:
        rig.coordinator.address = "AA:BB:CC:DD:EE:02"
    rig.callback(rig.last, bytearray.fromhex("FFFFFFFF05000109"))
    assert rig.controller.protocol_diagnostics["brightness"] is None
    await rig.controller.stop_notify()


@pytest.mark.asyncio
async def test_cancelled_write_is_skipped_and_fresh_stop_still_writes() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    rig.coordinator.cancel_command.set()
    await rig.controller.write_command(bytes.fromhex("FFFFFFFF0500000010D6CC"))
    assert rig.writes == []
    await rig.controller.stop_all()
    assert rig.writes == [STOP]
    with pytest.raises(ValueError, match="starts once"):
        await rig.controller.write_command(STOP, repeat_count=2)
    assert rig.writes == [STOP]


@pytest.mark.asyncio
async def test_held_motion_starts_once_then_fresh_stop_on_cancel() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    started = asyncio.Event()

    async def write(*_args: object, **_kwargs: object) -> None:
        started.set()

    rig.client.write_gatt_char.side_effect = write
    operation = asyncio.create_task(
        rig.controller.async_execute_motion_bed_action("weitiao_w1fragment_back_up", duration=2)
    )
    await started.wait()
    rig.coordinator.cancel_command.set()
    await operation
    action = ACTION_BY_KEY["weitiao_w1fragment_back_up"]
    assert rig.writes == [SOURCE_COMMANDS[action.select(rig.controller._state, False)[0]], STOP]


@pytest.mark.asyncio
async def test_task_cancellation_and_write_error_run_cleanup() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    holding = asyncio.Event()

    async def hold(*_args: object, **_kwargs: object) -> None:
        holding.set()
        await asyncio.Event().wait()

    rig.controller._hold = hold
    operation = asyncio.create_task(
        rig.controller.async_execute_motion_bed_action("weitiao_w1fragment_back_up")
    )
    await holding.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert len(rig.writes) == 2 and rig.writes[-1] == STOP
    rig.client.write_gatt_char.reset_mock()
    rig.client.write_gatt_char.side_effect = [OSError("write failed"), None]
    with pytest.raises(OSError, match="write failed"):
        await rig.controller.async_execute_motion_bed_action("weitiao_w1fragment_back_up")
    assert len(rig.writes) == 2 and rig.writes[-1] == STOP


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,key",
    [
        ("QMS-IQ", "kuaijie_k1fragment_flat"),
        ("QMS-IQ", "alarm_activity_audio_preview_1"),
        ("TL-A", "qinang_fragment_jingbu"),
        ("TL-W", "lengnuan_fragment_thermal_status"),
    ],
)
async def test_presets_accessories_air_and_thermal_do_not_gain_motor_stop(
    name: str, key: str
) -> None:
    rig = rig_for(name)
    await rig.controller.async_discover_capabilities()
    if "audio_preview" in key:
        rig.controller._state = replace(rig.controller._state, audio_available=True)
    await rig.controller.async_execute_motion_bed_action(key)
    assert rig.writes and STOP not in rig.writes


@pytest.mark.asyncio
async def test_modular_motor_surface_has_only_reachable_down_buttons() -> None:
    rig = rig_for("TL-B")
    await rig.controller.async_discover_capabilities()
    assert rig.controller.motor_control_specs == ()
    held = {action.key for action in rig.controller.actions if action.kind == "held"}
    assert held == {"diandong_fragment_back_down", "diandong_fragment_legs_down"}
    for key in held:
        rig.client.write_gatt_char.reset_mock()
        await rig.controller.async_execute_motion_bed_action(key, duration=0.001)
        assert len(rig.writes) == 2 and rig.writes[-1] == STOP
    with pytest.raises(ValueError):
        await rig.controller.move_back_up()


@pytest.mark.asyncio
@pytest.mark.parametrize("sleep_adjust", [False, True])
async def test_old_hold_cleanup_never_writes_to_replacement_target(sleep_adjust: bool) -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    holding, release = asyncio.Event(), asyncio.Event()

    async def hold(*_args: object, **_kwargs: object) -> None:
        holding.set()
        await release.wait()

    rig.controller._hold = hold
    key = "sleep_adjust_activity_adjust_back_up" if sleep_adjust else "weitiao_w1fragment_back_up"
    operation = asyncio.create_task(rig.controller.async_execute_motion_bed_action(key))
    await holding.wait()
    replacement = client_for(characteristic(90))
    rig.coordinator.address = "AA:BB:CC:DD:EE:02"
    rig.coordinator.client = replacement
    await rig.controller.async_discover_capabilities()
    release.set()
    with suppress(ConnectionError):
        await operation
    replacement.write_gatt_char.assert_not_awaited()
    assert rig.writes[-1] == STOP


@pytest.mark.asyncio
async def test_same_client_target_change_resets_state_and_invalidates_old_callback() -> None:
    rig = rig_for()
    await rig.controller.start_notify()
    callback = rig.callback
    callback(rig.last, bytearray.fromhex("FFFFFFFF05000109"))
    rig.coordinator.address = "AA:BB:CC:DD:EE:02"
    await rig.controller.async_discover_capabilities()
    assert rig.controller.protocol_diagnostics["brightness"] is None
    callback(rig.last, bytearray.fromhex("FFFFFFFF05000108"))
    assert rig.controller.protocol_diagnostics["brightness"] is None
    await rig.controller.stop_notify()


@pytest.mark.asyncio
async def test_explicit_query_temporary_context_expires_without_affecting_home() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    data = bytes.fromhex("FFFFFFFF02000F0E01020304")
    rig.controller._handle_notification(data)
    assert rig.controller.protocol_diagnostics["raw_positions"] == "[]"
    await rig.controller.async_execute_motion_bed_action("sleep_adjust_activity_raw_positions")
    rig.controller._handle_notification(data)
    assert rig.controller.protocol_diagnostics["raw_positions"] == "[1, 2, 3, 4]"
    rig.controller._context_expiry["sleep_adjust"] = asyncio.get_running_loop().time() - 1
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF02000F0E09090909"))
    assert rig.controller.protocol_diagnostics["raw_positions"] == "[1, 2, 3, 4]"
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF05000107"))
    assert rig.controller.protocol_diagnostics["brightness"] == 7


@pytest.mark.asyncio
async def test_followup_waiting_for_command_lock_cannot_write_replacement_session() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    queued, release = asyncio.Event(), asyncio.Event()

    async def execute(command: Callable[[BedController], Awaitable[None]], **kwargs: object) -> None:
        queued.set()
        await release.wait()
        await command(rig.controller)

    rig.coordinator.async_execute_controller_query.side_effect = execute
    task = asyncio.create_task(rig.controller._followup(MotionBedFollowup("position_query")))
    await queued.wait()
    replacement = client_for(characteristic(90))
    rig.coordinator.client = replacement
    await rig.controller.async_discover_capabilities()
    release.set()
    with suppress(ConnectionError):
        await task
    replacement.write_gatt_char.assert_not_awaited()


@pytest.mark.asyncio
async def test_hub_modules_are_inactive_until_present_and_then_gated_individually() -> None:
    rig = rig_for("TL-Q")
    await rig.controller.async_discover_capabilities()
    assert not any(action.owner == "QinangFragment" for action in rig.controller.actions)
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFFFF140209010301"))
    assert not rig.controller.protocol_diagnostics["air_full_custom"]
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF01002714000A000000000000"))
    assert any(action.owner == "DiandongFragment" for action in rig.controller.actions)
    assert not any(action.owner == "QinangFragment" for action in rig.controller.actions)
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFFFF140209010301"))
    assert not rig.controller.protocol_diagnostics["air_full_custom"]
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF01002714000A00000B000000"))
    assert any(action.owner == "QinangFragment" for action in rig.controller.actions)
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFFFF140209010301"))
    assert rig.controller.protocol_diagnostics["air_full_custom"]
    await rig.controller.stop_notify()


@pytest.mark.asyncio
async def test_present_hub_thermal_starts_owned_polling_once(monkeypatch) -> None:
    rig = rig_for("TL-Q")
    await rig.controller.async_discover_capabilities()
    rig.controller._spawn = MagicMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", AsyncMock())
    status = bytes.fromhex("FFFFFFFF01002714000000000000000C")
    rig.controller._handle_notification(status)
    await rig.controller._start_present_modules()
    operations = [call.args[0] for call in rig.controller._spawn.call_args_list]
    poll = AsyncMock()
    rig.controller._thermal_poll = poll
    for operation in operations:
        await operation()
    poll.assert_awaited_once_with(module_generation=rig.controller._module_generation)
    first_count = len(operations)
    rig.controller._handle_notification(status)
    await rig.controller._start_present_modules()
    operations = [call.args[0] for call in rig.controller._spawn.call_args_list]
    for operation in operations[first_count:]:
        await operation()
    poll.assert_awaited_once_with(module_generation=rig.controller._module_generation)


@pytest.mark.asyncio
async def test_thermal_poll_intervals_and_disconnect_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = rig_for("TL-W")
    await rig.controller.async_discover_capabilities()
    real_sleep = asyncio.sleep
    delays: list[float] = []
    release = asyncio.Event()

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if delay == 2:
            await release.wait()
        elif delay == 5:
            await asyncio.Event().wait()
        else:
            await real_sleep(0)

    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    rig.controller._spawn(rig.controller._thermal_poll)
    await real_sleep(0)
    assert delays == [2]
    tasks = tuple(rig.controller._tasks)
    try:
        release.set()
        await real_sleep(0)
        await real_sleep(0)
        assert delays == [2, 5]
        assert rig.writes == [SOURCE_COMMANDS["LengnuanFragment:58"]]
    finally:
        await rig.controller.stop_notify()
        results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(result, asyncio.CancelledError) for result in results)
    assert len(rig.writes) == 1 and not rig.controller._tasks


@pytest.mark.asyncio
async def test_duplicate_source_sites_are_not_multiple_immediate_stop_or_query_frames() -> None:
    rig = rig_for("TL-B")
    await rig.controller.async_discover_capabilities()
    await rig.controller.async_execute_motion_bed_action("diandong_fragment_stop")
    assert rig.writes == [STOP]
    home = rig_for()
    await home.controller.async_discover_capabilities()
    await home.controller.async_execute_motion_bed_action("sleep_adjust_activity_raw_positions")
    assert len(home.writes) == 1


@pytest.mark.asyncio
async def test_nullable_boolean_sensor_platform_remains_stable() -> None:
    rig = rig_for("TL-B")
    before_sensor = {spec.key for spec in rig.controller.controller_state_sensor_specs}
    before_binary = {spec.key for spec in rig.controller.controller_state_binary_sensor_specs}
    await rig.controller.async_discover_capabilities()
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF01002A141F00010101"))
    assert {spec.key for spec in rig.controller.controller_state_sensor_specs} == before_sensor
    assert {
        spec.key for spec in rig.controller.controller_state_binary_sensor_specs
    } == before_binary
    assert "motion_bed_thermal_timer_enabled" in before_binary
    # The module light is a switch with the reported state, not a binary sensor.
    assert "motion_bed_motor_light_enabled" not in before_binary
    await rig.controller.stop_notify()


@pytest.mark.asyncio
async def test_failed_startup_cleans_notification_session_and_background_work() -> None:
    rig = rig_for()
    rig.controller._startup.side_effect = OSError("startup write failed")
    with pytest.raises(OSError, match="startup write failed"):
        await rig.controller.start_notify()
    assert not rig.controller._notifying and not rig.controller._tasks
    assert rig.controller._session_client is None
    rig.client.stop_notify.assert_awaited_once_with(rig.last)




@pytest.mark.asyncio
@pytest.mark.parametrize(
    "effect,source",
    [
        (MotionBedFollowup("position_query", 100), "SleepAdjustActivity:255"),
        (MotionBedFollowup("sensor_query", 200), "DiandongFragment:135"),
        (MotionBedFollowup("module_status_query"), "MainMcuActivity:182"),
    ],
)
async def test_followup_packet_and_delay_match_source(
    effect: MotionBedFollowup, source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    await rig.controller._followup(effect)
    sleep.assert_awaited_once_with(effect.delay_ms / 1000)
    assert rig.writes == [SOURCE_COMMANDS[source]]


@pytest.mark.asyncio
async def test_removed_hub_thermal_cannot_receive_queued_startup() -> None:
    rig = rig_for("TL-Q")
    await rig.controller.async_discover_capabilities()
    rig.controller._spawn = MagicMock()
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF01002714000000000000000C"))
    queued, release = asyncio.Event(), asyncio.Event()

    async def execute(command: Callable[[BedController], Awaitable[None]], **kwargs: object) -> None:
        queued.set()
        await release.wait()
        await command(rig.controller)

    rig.coordinator.async_execute_controller_query.side_effect = execute
    task = asyncio.create_task(rig.controller._start_present_modules())
    await queued.wait()
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF010027140000000000000000"))
    release.set()
    await task
    assert rig.writes == []
    assert "thermal" not in rig.controller._started_modules


@pytest.mark.asyncio
async def test_sleep_adjust_release_stops_then_queries_after_100ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    await rig.controller.async_execute_motion_bed_action(
        "sleep_adjust_activity_adjust_back_up", duration=0.001
    )
    expected_start = ACTION_BY_KEY["sleep_adjust_activity_adjust_back_up"].select(
        rig.controller._state, False
    )[0]
    assert rig.writes == [
        SOURCE_COMMANDS[expected_start],
        STOP,
        SOURCE_COMMANDS["SleepAdjustActivity:255"],
    ]
    sleep.assert_awaited_once_with(0.1)


@pytest.mark.asyncio
async def test_new_day_report_request_resets_prior_aggregation_and_retains_other_state() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    rig.controller._activate("day_report")
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF05000107"))
    rig.controller._handle_notification(bytes.fromhex("FFFFFFFF02000414010A1403010203040506"))
    assert rig.controller._state.to_updates()["day_received_segments"] == "[1]"
    request = MotionBedWrite(
        "sleep_report",
        (bytes.fromhex("FFFFFFFF0200130B001C04"),),
        "day_report",
        report_offset=2,
        historical_day=True,
    )
    await rig.controller.async_execute_motion_bed_write(request)
    assert rig.controller._state.to_updates()["day_received_segments"] == "[]"
    assert rig.controller._state.to_updates()["day_slots"] == str([0] * 24)
    assert rig.controller._state.to_updates()["day_total"] is None
    assert rig.controller.protocol_diagnostics["brightness"] == 7
    assert rig.controller._route.historical_day and rig.controller._route.day_window_offset == 2


@pytest.mark.asyncio
async def test_persistent_write_confirmation_and_profile_validation_precede_traffic() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    request = MotionBedWrite("sleep_angles", (STOP,), "sleep_adjust", persistent=True)
    with pytest.raises(ValueError, match="Confirm"):
        await rig.controller.async_execute_motion_bed_write(request)
    rig.client.write_gatt_char.assert_not_awaited()
    unsupported = MotionBedWrite("thermal_schedule", (STOP,), "thermal_schedule")
    with pytest.raises(ValueError, match="does not offer"):
        await rig.controller.async_execute_motion_bed_write(unsupported)
    rig.client.write_gatt_char.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_frame_configuration_cannot_continue_on_replacement_target() -> None:
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    replacement = client_for(characteristic(90))

    async def write(*_args: object, **_kwargs: object) -> None:
        rig.coordinator.client = replacement
        await rig.controller.async_discover_capabilities()

    rig.client.write_gatt_char.side_effect = write
    request = MotionBedWrite("clock", (b"first", b"second"), "home")
    with pytest.raises(ConnectionError):
        await rig.controller.async_execute_motion_bed_write(request)
    assert rig.writes == [b"first"]
    replacement.write_gatt_char.assert_not_awaited()




@pytest.mark.asyncio
async def test_same_client_characteristic_rediscovery_invalidates_old_object_callback() -> None:
    rig = rig_for()
    await rig.controller.start_notify()
    callback = rig.callback
    replacement = characteristic(90)
    rig.client.services = [MagicMock(characteristics=[replacement])]
    await rig.controller.async_discover_capabilities()
    callback(rig.last, bytearray.fromhex("FFFFFFFF05000109"))
    assert rig.controller.protocol_diagnostics["brightness"] is None
    await rig.controller.write_command(STOP)
    assert rig.client.write_gatt_char.await_args.args[0] is replacement
    await rig.controller.stop_notify()


async def test_home_startup_preserves_source_clock_sync_and_fragment_event_delays(monkeypatch):
    rig = rig_for(stub_startup=False)
    delays = []
    async def sleep(delay):
        delays.append(delay)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    clock = bytes.fromhex("FFFFFFFF010203")
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.build_clock", lambda timestamp: clock)
    await rig.controller.async_discover_capabilities()
    await rig.controller.start_notify()
    assert rig.writes[:3] == [SOURCE_COMMANDS["HomeActivity:321"], clock, SOURCE_COMMANDS["HomeActivity:311"]]
    assert rig.writes[3:] == [SOURCE_COMMANDS[f"KuaijieK1Fragment:{line}"] for line in (203,205,207,209,211)]
    assert delays == [0.5,0.5,0.5,0.5,0.2,0.5,0.5,0.5,0.5]
    await rig.controller.stop_notify()


async def test_module_removed_during_startup_delay_never_receives_following_clock(monkeypatch):
    rig = rig_for("TL-Q")
    await rig.controller.async_discover_capabilities()
    rig.controller._state = replace(rig.controller._state, thermal_module_present=True)
    rig.controller._active_module = "thermal"
    count = 0
    async def sleep(delay):
        nonlocal count
        count += 1
        if count == 2:
            rig.controller._state = replace(rig.controller._state, thermal_module_present=False)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.sleep", sleep)
    await rig.controller._module_startup("thermal")
    assert rig.writes == [SOURCE_COMMANDS["LengnuanFragment:183"]]
    await rig.controller.stop_notify()


@pytest.mark.parametrize("cancelled", [False, True])
async def test_calibration_debug_has_ten_two_second_samples_or_cancels_before_first(monkeypatch, cancelled):
    rig = rig_for()
    await rig.controller.async_discover_capabilities()
    intervals = []
    async def wait_for(awaitable, timeout):
        awaitable.close()
        intervals.append(timeout)
        if not cancelled:
            raise TimeoutError
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.wait_for", wait_for)
    key = "sleep_data_entry_activity_capture_debug"
    await rig.controller.async_execute_motion_bed_action(key)
    selected = ACTION_BY_KEY[key].select(rig.controller._state, False)
    frames = list(dict.fromkeys(SOURCE_COMMANDS[source] for source in selected))
    assert rig.writes == ([] if cancelled else frames * 10)
    assert intervals == ([2] if cancelled else [2] * 10)
    await rig.controller.stop_notify()


@pytest.mark.parametrize("cancelled", [False, True])
async def test_pressure_live_quiet_delay_is_bound_to_request_and_cancelled_before_io(monkeypatch, cancelled):
    from custom_components.adjustable_bed.beds.motion_bed.protocol import build_pressure_live
    rig = rig_for("TL-A")
    await rig.controller.async_discover_capabilities()
    intervals = []
    async def wait_for(awaitable, timeout):
        awaitable.close()
        intervals.append(timeout)
        if not cancelled:
            raise TimeoutError
    monkeypatch.setattr("custom_components.adjustable_bed.beds.motion_bed.controller.asyncio.wait_for", wait_for)
    frame = build_pressure_live(11,9)
    request = MotionBedWrite("pressure", (frame,), "pressure_settings", initial_delay_ms=2500)
    await rig.controller.async_execute_motion_bed_write(request)
    assert intervals == [2.5]
    assert rig.writes == ([] if cancelled else [frame])
    await rig.controller.stop_notify()


async def _same_frames(rig: Rig, new: Callable[[], Awaitable[None]], old_key: str) -> list[bytes]:
    """Return the frames ``new`` writes, after checking the old button wrote the same."""
    ctrl = rig.controller
    state = ctrl._state
    rig.client.write_gatt_char.reset_mock()
    await new()
    sent = rig.writes
    ctrl._state = state
    rig.client.write_gatt_char.reset_mock()
    await ctrl.async_execute_motion_bed_action(button_actions_for(ctrl._active_owners())[old_key].key)
    assert rig.writes == sent, old_key
    return sent


@pytest.mark.asyncio
async def test_value_buttons_become_one_control_sending_the_same_frames() -> None:
    rig = rig_for()
    ctrl = rig.controller
    await ctrl.async_discover_capabilities()
    buttons = {spec.key for spec in ctrl.controller_button_specs}
    for replaced in ("motion_bed_10time", "motion_bed_brightness_5", "motion_bed_tv_8xiaoshi"):
        assert replaced not in buttons
    assert ctrl.auto_enable_massage and ctrl.massage_timer_can_turn_off
    assert ctrl.massage_timer_options == [10, 20, 30]
    assert ctrl.light_timer_options == ["10 min", "8 hours", "10 hours"]
    (brightness,) = ctrl.controller_number_specs
    assert (brightness.native_min_value, brightness.native_max_value) == (0, 10)
    assert await _same_frames(rig, lambda: ctrl.set_massage_timer(20), "motion_bed_20time")
    await _same_frames(rig, lambda: brightness.set_fn(ctrl, 7), "motion_bed_brightness_7")
    await _same_frames(rig, lambda: ctrl.set_light_timer("8 hours"), "motion_bed_tv_8xiaoshi")
    # A timer set here shows without a report, as the home screen may send none.
    assert ctrl._shown_massage_timer == 20
    # Without a report, Off presses the chosen timer's key as the app's screen shows it.
    rig.client.write_gatt_char.reset_mock()
    await ctrl.set_massage_timer(0)
    home_off = list(rig.writes)
    assert ctrl._shown_massage_timer is None
    # Off presses the reported timer's key, which the app turns into its deselect frame.
    ctrl._state = replace(ctrl._state, massage_timer=20)
    ctrl._publish()
    off = await _same_frames(rig, lambda: ctrl.set_massage_timer(0), "motion_bed_20time")
    assert off == home_off
    assert ctrl._shown_massage_timer is None
    assert off != await _same_frames(rig, lambda: ctrl.set_massage_timer(10), "motion_bed_10time")
    # Choosing the reported, shown timer keeps it instead of toggling it off.
    ctrl._state = replace(ctrl._state, massage_timer=10)
    ctrl._publish()
    rig.client.write_gatt_char.reset_mock()
    await ctrl.set_massage_timer(10)
    assert rig.writes == []
    # A reported timer cleared here cannot be chosen again until the bed reports.
    await ctrl.set_massage_timer(0)
    with pytest.raises(ValueError, match="not reported"):
        await ctrl.set_massage_timer(10)


@pytest.mark.asyncio
async def test_toggles_and_module_pairs_are_switches_with_reported_state() -> None:
    rig = rig_for()
    ctrl = rig.controller
    await ctrl.async_discover_capabilities()
    switches = {spec.key: spec for spec in ctrl.controller_switch_specs}
    assert {"motion_bed_night_light_enabled", "motion_bed_sleep_enabled"} <= switches.keys()
    buttons = {spec.key for spec in ctrl.controller_button_specs}
    assert not {"motion_bed_night_light", "motion_bed_sleepmian"} & buttons
    night = switches["motion_bed_night_light_enabled"]
    with pytest.raises(ValueError):
        await night.set_fn(ctrl, False)  # Unknown: the toggle would turn it on.
    ctrl._state = replace(ctrl._state, night_light_enabled=False)
    await _same_frames(rig, lambda: night.set_fn(ctrl, True), "motion_bed_night_light")
    rig.client.write_gatt_char.reset_mock()
    await night.set_fn(ctrl, False)
    assert rig.writes == []

    hub = rig_for("TL-Q")
    await hub.controller.async_discover_capabilities()
    assert not hub.controller.controller_switch_specs
    hub.controller._handle_notification(bytes.fromhex("FFFFFFFF01002714000A000000000000"))
    module = {spec.key: spec for spec in hub.controller.controller_switch_specs}
    assert {"motion_bed_motor_light_enabled", "motion_bed_motor_massage_enabled"} <= module.keys()
    light = module["motion_bed_motor_light_enabled"]
    await _same_frames(hub, lambda: light.set_fn(hub.controller, True), "motion_bed_light_enabled_on")
    await _same_frames(hub, lambda: light.set_fn(hub.controller, False), "motion_bed_light_enabled_off")
    assert ("switch", "controller_switch_motion_bed_motor_light_enabled") in (
        hub.controller.retained_entity_keys
    )
    await hub.controller.stop_notify()
    await rig.controller.stop_notify()
