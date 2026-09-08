"""Profile-specific BLE behavior from the four accepted cluster-005 reports."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.leggett_okin import LeggettOkinController
from custom_components.adjustable_bed.const import (
    LEGGETT_OKIN_CHAR_UUID,
    LEGGETT_OKIN_NOTIFY_CHAR_UUID,
    LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID,
    LEGGETT_OKIN_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
)


def make_controller(profile: str = "prodigy4", revision: int = 1) -> LeggettOkinController:
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.motor_pulse_delay_ms = 100
    uuids = [LEGGETT_OKIN_CHAR_UUID, LEGGETT_OKIN_NOTIFY_CHAR_UUID]
    if revision:
        uuids.append(LEGGETT_OKIN_REVISION_SELECTOR_CHAR_UUID)
    coordinator.client = SimpleNamespace(
        is_connected=True,
        services=[
            SimpleNamespace(
                uuid=LEGGETT_OKIN_SERVICE_UUID,
                characteristics=[SimpleNamespace(uuid=uuid) for uuid in uuids],
            )
        ],
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        read_gatt_char=AsyncMock(),
    )
    controller = LeggettOkinController(coordinator, app_profile=profile)
    controller.write_command = AsyncMock()
    controller._wait_hold_deadline = AsyncMock()
    return controller


@pytest.mark.parametrize(
    ("profile", "axes", "memories", "settings"),
    [
        ("prodigy2l", {"head", "feet", "lumbar"}, 4, True),
        ("prodigy2", {"head", "feet", "pillow"}, 4, True),
        ("prodigy4", {"head", "feet", "pillow", "lumbar"}, 4, True),
        ("useries", {"head", "feet", "pillow"}, 2, False),
    ],
)
def test_profile_capabilities_do_not_inherit_unreachable_controls(
    profile, axes, memories, settings
):
    controller = make_controller(profile)
    assert {spec.key for spec in controller.motor_control_specs} == axes
    assert controller.memory_slot_count == memories
    assert controller.supports_control_mode_configuration is settings
    assert controller.supports_memory_programming is settings
    assert controller.supports_massage
    assert ("store" in controller.held_control_options) is (profile == "useries")


async def test_unavailable_axes_and_useries_settings_never_write():
    no_pillow = make_controller("prodigy2l")
    with pytest.raises(NotImplementedError, match="pillow"):
        await no_pillow.move_pillow_up()
    no_pillow.write_command.assert_not_awaited()
    useries = make_controller("useries")
    with pytest.raises(NotImplementedError, match="lumbar"):
        await useries.move_lumbar_up()
    with pytest.raises(NotImplementedError, match="settings"):
        await useries.set_control_mode_press_and_hold()
    await useries.program_memory(1)
    await useries.preset_memory(3)
    useries.write_command.assert_not_awaited()


@pytest.mark.parametrize("profile", ["prodigy2l", "prodigy2", "prodigy4"])
async def test_prodigy_sleep_remains_compact_on_revision_zero(profile):
    controller = make_controller(profile, revision=0)
    await controller.set_sleep_timer(90, 3)
    controller.write_command.assert_awaited_once_with(
        bytes.fromhex("0402ff02005a"), repeat_count=10, repeat_delay_ms=100
    )


@pytest.mark.parametrize(
    ("revision", "sleep", "alarm_stop"),
    [(0, "e5fe16ff10000fe8", "e5fe16fd00000009"), (1, "0402ff10000f", "0402fd000000")],
)
async def test_useries_timers_use_live_revision_builder_and_alarm_stop(revision, sleep, alarm_stop):
    controller = make_controller("useries", revision)
    await controller.set_sleep_timer(15, 0)
    await controller.cancel_alarm_timer()
    assert [item.args[0].hex() for item in controller.write_command.await_args_list] == [
        sleep,
        alarm_stop,
    ]
    assert all(
        item.kwargs["repeat_count"] == 10 for item in controller.write_command.await_args_list
    )


async def test_useries_memory_and_store_are_held_not_prodigy_favorite_sequences():
    controller = make_controller("useries")
    await controller.hold_control("memory_1", 1000)
    press, release = controller.write_command.await_args_list
    assert press.args[0] == bytes.fromhex("040200001000")
    assert {key: value for key, value in press.kwargs.items() if key != "deadline"} == {
        "repeat_count": 10,
        "repeat_delay_ms": 100,
    }
    assert release.args[0] == bytes.fromhex("040200000000")
    assert release.kwargs["repeat_count"] == 4
    controller.write_command.reset_mock()
    await controller.hold_control("store", 500)
    press, release = controller.write_command.await_args_list
    assert press.args[0] == bytes.fromhex("040200010000")
    assert press.kwargs["repeat_count"] == 5
    assert release.kwargs["repeat_count"] == 4


async def test_prodigy_snore_has_distinct_recall_and_held_paths():
    controller = make_controller()
    await controller.preset_anti_snore()
    controller.write_command.assert_awaited_once_with(
        bytes.fromhex("040200004000"), repeat_count=10, repeat_delay_ms=100
    )
    controller.write_command.reset_mock()
    await controller.hold_control("snore", 500)
    press, release = controller.write_command.await_args_list
    assert press.args[0] == bytes.fromhex("040200004000")
    assert press.kwargs["repeat_count"] == 5
    assert release.kwargs["repeat_count"] == 4


@pytest.mark.parametrize("interruption", ["cancel_event", "task_cancel", "write_failure"])
async def test_interrupted_recall_sends_proven_release_with_fresh_event(interruption):
    controller = make_controller()

    async def interrupt(packet, **kwargs):
        if packet == bytes.fromhex("040200001000"):
            if interruption == "cancel_event":
                controller._coordinator.cancel_command.set()
            elif interruption == "task_cancel":
                raise asyncio.CancelledError
            else:
                raise BleakError("recall failed")

    controller.write_command = AsyncMock(side_effect=interrupt)
    if interruption == "cancel_event":
        await controller.preset_memory(1)
    else:
        with pytest.raises(asyncio.CancelledError if interruption == "task_cancel" else BleakError):
            await controller.preset_memory(1)
    release = controller.write_command.await_args_list[-1]
    assert release.args[0] == bytes.fromhex("040200000000")
    assert release.kwargs["repeat_count"] == 4
    assert not release.kwargs["cancel_event"].is_set()


async def test_invalid_held_controls_and_durations_never_write():
    controller = make_controller()
    for action, duration in [("store", 500), ("snore", 99), ("flat", 60001), ("flat", True)]:
        with pytest.raises(ValueError):
            await controller.hold_control(action, duration)
    controller.write_command.assert_not_awaited()


@pytest.mark.parametrize("profile", ["prodigy2l", "prodigy2", "prodigy4", "useries"])
async def test_notify_bootstrap_and_serial_device_information(profile):
    controller = make_controller(profile)
    client = controller.client
    fields = ["2a29", "2a24", "2a25", "2a27", "2a26", "2a28"]
    info_uuids = [f"0000{field}-0000-1000-8000-00805f9b34fb" for field in fields]
    client.services[0].characteristics += [
        SimpleNamespace(uuid=uuid)
        for uuid in [
            OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID,
            OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
            *info_uuids,
        ]
    ]
    client.read_gatt_char.side_effect = [b"maker", b"model", b"serial", b"hw", b"fw", b"sw"]
    controller._write_gatt_with_retry = AsyncMock()
    await controller.start_notify()
    subscribed = [item.args[0] for item in client.start_notify.await_args_list]
    assert subscribed == (
        [LEGGETT_OKIN_NOTIFY_CHAR_UUID]
        if profile == "useries"
        else [LEGGETT_OKIN_NOTIFY_CHAR_UUID, OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID]
    )
    if profile == "useries":
        controller._write_gatt_with_retry.assert_not_awaited()
    else:
        controller._write_gatt_with_retry.assert_awaited_once_with(
            OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID, b"\x01\x02", response=True, log_errors=False
        )
    assert [item.args[0] for item in client.read_gatt_char.await_args_list] == info_uuids
    assert controller.protocol_diagnostics["device_information"] == {
        "manufacturer": "maker",
        "model": "model",
        "serial": "serial",
        "hardware": "hw",
        "firmware": "fw",
        "software": "sw",
    }
    await controller.start_notify()
    assert client.read_gatt_char.await_count == 6
    controller._handle_notification(
        LEGGETT_OKIN_NOTIFY_CHAR_UUID, bytearray.fromhex("0600060000017f0002")
    )
    controller._coordinator.handle_controller_state_updates.assert_called_with(
        {
            "leggett_led_mask": 0x077F0003,
            "leggett_status": 127,
            "leggett_alarm_indicator": False,
            "leggett_sleep_timer_indicator": False,
        }
    )


@pytest.mark.parametrize("duration_ms", [100, 200])
async def test_hold_waits_until_requested_release_time(duration_ms):
    controller = make_controller()
    controller._wait_hold_deadline = LeggettOkinController._wait_hold_deadline.__get__(controller)
    times = []

    async def record_write(*args, **kwargs):
        times.append(asyncio.get_running_loop().time())

    controller.write_command = AsyncMock(side_effect=record_write)
    started = asyncio.get_running_loop().time()
    await controller.hold_control("snore", duration_ms)
    assert times[-1] - started >= duration_ms / 1000 - 0.01
    assert len(times) == 2


async def test_hold_deadline_is_cancellable():
    controller = make_controller()
    controller._wait_hold_deadline = LeggettOkinController._wait_hold_deadline.__get__(controller)
    controller._coordinator.cancel_command.set()
    async with asyncio.timeout(0.2):
        await controller.hold_control("snore", 60000)
    assert not controller.write_command.await_args_list[-1].kwargs["cancel_event"].is_set()


async def test_cancelled_settings_initialization_is_retried_after_cancellation_clears():
    controller = make_controller()
    client = controller.client
    client.services[0].characteristics += [
        SimpleNamespace(uuid=uuid)
        for uuid in (OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID, OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID)
    ]
    controller._write_gatt_with_retry = AsyncMock()
    controller._coordinator.cancel_command.set()
    await controller.start_notify()
    assert not controller.protocol_diagnostics["settings_initialized"]
    controller._write_gatt_with_retry.assert_not_awaited()
    controller._coordinator.cancel_command.clear()
    await controller.start_notify()
    assert controller.protocol_diagnostics["settings_initialized"]
    assert controller._write_gatt_with_retry.await_count == 1


async def test_reconnect_rechecks_revision_selector_and_unknown_target_never_defaults_r1():
    controller = make_controller(revision=1)
    assert controller._build_command(1).hex() == "040200000001"
    await controller.stop_notify()
    controller.client.services[0].characteristics = [SimpleNamespace(uuid=LEGGETT_OKIN_CHAR_UUID)]
    await controller.start_notify()
    assert controller._build_command(1).hex() == "e5fe160000000105"
    await controller.stop_notify()
    controller.client.services = []
    with pytest.raises(ConnectionError, match="not resolved"):
        controller._build_command(1)


@pytest.mark.parametrize("profile", ["prodigy4", "useries"])
def test_indicator_mask_obeys_useries_display_filter_without_losing_raw_bits(profile):
    controller = make_controller(profile)
    controller._handle_notification(
        LEGGETT_OKIN_NOTIFY_CHAR_UUID, bytearray.fromhex("06000000c001000000")
    )
    updates = controller._coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["leggett_led_mask"] == 0xC001
    assert updates["leggett_alarm_indicator"] is (profile == "prodigy4")
    assert updates["leggett_sleep_timer_indicator"] is (profile == "prodigy4")
    assert controller.protocol_diagnostics["alarm_armed"] is (profile == "prodigy4")
    controller._handle_notification(
        LEGGETT_OKIN_NOTIFY_CHAR_UUID, bytearray.fromhex("06000000c000000000")
    )
    updates = controller._coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["leggett_alarm_indicator"] is True
    assert updates["leggett_sleep_timer_indicator"] is True


async def test_slow_transport_does_not_extend_held_refresh_past_deadline():
    controller = make_controller()
    controller.write_command = LeggettOkinController.write_command.__get__(controller)
    controller._wait_hold_deadline = LeggettOkinController._wait_hold_deadline.__get__(controller)
    timestamps = []

    async def delayed_write(uuid, packet, **kwargs):
        if packet == bytes.fromhex("040200004000"):
            timestamps.append(asyncio.get_running_loop().time())
            await asyncio.sleep(0.2)

    controller._write_gatt_with_retry = AsyncMock(side_effect=delayed_write)
    started = asyncio.get_running_loop().time()
    await controller.hold_control("snore", 300)
    assert len(timestamps) == 2
    assert all(instant < started + 0.3 for instant in timestamps)
    release = controller._write_gatt_with_retry.await_args_list[-1]
    assert release.args[1] == bytes.fromhex("040200000000")
    assert release.kwargs["repeat_count"] == 4


async def test_control_mode_zero_waits_for_the_next_tick_after_55_attempts():
    controller = make_controller()
    started = asyncio.get_running_loop().time()
    await controller.set_control_mode_press_and_hold()
    deadline = controller._wait_hold_deadline.await_args.args[0]
    assert 5.49 <= deadline - started <= 5.51
    mode, release = controller.write_command.await_args_list
    assert mode.kwargs == {"repeat_count": 55, "repeat_delay_ms": 100}
    assert release.kwargs["repeat_count"] == 1
    assert not release.kwargs["cancel_event"].is_set()


@pytest.mark.parametrize("error", [BleakError("movement failed"), asyncio.CancelledError()])
async def test_disconnect_cleanup_preserves_movement_error(error):
    controller = make_controller()

    async def disconnect(*args, **kwargs):
        controller.client.is_connected = False
        controller.client.services = None
        await controller.stop_notify()
        raise error

    controller.write_command.side_effect = disconnect
    with pytest.raises(type(error)) as raised:
        await controller.move_head_up()
    assert raised.value is error


async def test_explicit_release_reports_unresolved_revision():
    controller = make_controller()
    controller.client.is_connected = False
    controller.client.services = None
    await controller.stop_notify()
    with pytest.raises(ConnectionError):
        await controller._send_release_frames("stop", raise_on_error=True)


async def test_device_information_timeout_continues_to_next_field():
    controller = make_controller()
    manufacturer = "00002a29-0000-1000-8000-00805f9b34fb"
    model = "00002a24-0000-1000-8000-00805f9b34fb"

    async def read(uuid):
        if uuid == manufacturer:
            await asyncio.Event().wait()
        return b"model"

    controller.client.read_gatt_char.side_effect = read
    with patch(
        "custom_components.adjustable_bed.beds.leggett_okin.DEVICE_INFO_READ_TIMEOUT",
        0.01,
    ):
        await controller._read_device_information(frozenset({manufacturer, model}))
    assert controller.protocol_diagnostics["device_information"] == {"model": "model"}
    assert manufacturer not in controller._device_information_read
    assert model in controller._device_information_read


async def test_useries_one_shot_presets_require_explicit_hold():
    controller = make_controller("useries")
    with pytest.raises(NotImplementedError, match="leggett_hold_control"):
        await controller.preset_memory(1)
    with pytest.raises(NotImplementedError, match="leggett_hold_control"):
        await controller.preset_anti_snore()
    controller.write_command.assert_not_awaited()
