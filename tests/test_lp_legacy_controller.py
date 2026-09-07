"""Exercise frozen LP app gesture states, mode distinctions, and safe cleanup."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.leggett_lp_legacy import LeggettLpLegacyController
from custom_components.adjustable_bed.lp_legacy_profiles import (
    LP_LEGACY_PROFILE_CODES,
    LpLegacyControl,
    get_lp_legacy_profile,
)

WRITE_UUID = "00000001-0000-0000-0000-000000000000"
READ_UUID = "00000002-0000-0000-0000-000000000000"


@pytest.fixture
def coordinator() -> MagicMock:
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock(return_value=bytearray.fromhex("6E 09 01 00 78"))
    characteristic = MagicMock(uuid=WRITE_UUID, properties=["write"])
    coordinator.client.services.get_characteristic.return_value = characteristic
    return coordinator


def make_controller(
    coordinator: MagicMock, model: str = "6BRM", **kwargs
) -> LeggettLpLegacyController:
    return LeggettLpLegacyController(coordinator, model=model, write_uuid=WRITE_UUID, **kwargs)


def find_control(press_state: int, release_state: int | None) -> tuple[str, LpLegacyControl]:
    for code in LP_LEGACY_PROFILE_CODES:
        for control in get_lp_legacy_profile(code).controls:
            if (
                control.press.state == press_state
                and (control.release.state if control.release else None) == release_state
                and control.press.legacy
            ):
                return code, control
    raise AssertionError("Frozen profile catalog lacks requested gesture")


def written(coordinator: MagicMock) -> list[bytes]:
    return [call.args[1] for call in coordinator.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize(
    ("mode", "expected", "release"),
    [("legacy", "34", "6e"), ("framed", "6e01002493", "6e01006edd")],
)
async def test_mismatched_token_modes_keep_proven_bytes(coordinator, mode, expected, release):
    controller = make_controller(coordinator, mode=mode)
    control = next(
        item for item in get_lp_legacy_profile("6BRM").controls if item.press.token == "40024"
    )
    with patch.object(controller, "_wait_ticks", new=AsyncMock(return_value=True)) as wait:
        await controller.execute_control(control.key)
    assert written(coordinator) == [bytes.fromhex(expected)] * 2 + [bytes.fromhex(release)]
    assert [call.args for call in wait.call_args_list] == [(1,), (1,)]


async def test_event_cancel_still_releases(coordinator):
    code, control = find_control(1, 2)
    controller = make_controller(coordinator, code)

    async def cancel_on_hold(_ticks, **_kwargs):
        coordinator.cancel_command.set()
        return False

    with patch.object(controller, "_wait_ticks", side_effect=cancel_on_hold):
        await controller.execute_control(control.key)
    assert written(coordinator) == [control.press.legacy, control.release.legacy]


async def test_task_cancel_still_releases(coordinator):
    code, control = find_control(1, 2)
    controller = make_controller(coordinator, code)
    holding = asyncio.Event()

    async def hold(_ticks, **_kwargs):
        holding.set()
        await asyncio.Event().wait()

    with patch.object(controller, "_wait_ticks", side_effect=hold):
        task = asyncio.create_task(controller.execute_control(control.key))
        await holding.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert written(coordinator) == [control.press.legacy, control.release.legacy]


async def test_hold_cadence_absorbs_write_latency_and_never_waits_negative(coordinator):
    controller = make_controller(coordinator)
    control = get_lp_legacy_profile("6BRM").controls[0]
    # Simulate one 60 ms write and one write that exceeds the 100 ms tick.
    coordinator.cancel_command.wait = AsyncMock(side_effect=TimeoutError)
    with (
        patch(
            "custom_components.adjustable_bed.beds.leggett_lp_legacy.monotonic",
            side_effect=[100.0, 100.06, 200.0, 200.14],
        ),
        patch(
            "custom_components.adjustable_bed.beds.leggett_lp_legacy.asyncio.timeout",
            wraps=asyncio.timeout,
        ) as timeout,
    ):
        await controller.execute_control(control.key)
    assert [call.args[0] for call in timeout.call_args_list] == pytest.approx([0.04, 0.0])
    assert written(coordinator) == [control.press.legacy] * 2 + [control.release.legacy]


@pytest.mark.parametrize(("gesture", "ticks"), [("press", None), ("long_press", 31)])
async def test_short_long_threshold_sends_one_command(coordinator, gesture, ticks):
    code, control = find_control(3, 4)
    controller = make_controller(coordinator, code)
    with patch.object(controller, "_wait_ticks", new=AsyncMock(return_value=True)) as wait:
        await controller.execute_control(control.key, gesture)
    assert written(coordinator) == [control.press.legacy if ticks else control.release.legacy]
    assert [call.args for call in wait.call_args_list] == ([(31,)] if ticks else [])


async def test_cancel_long_press_does_not_turn_into_short_command(coordinator):
    code, control = find_control(3, 4)
    controller = make_controller(coordinator, code)
    with patch.object(controller, "_wait_ticks", new=AsyncMock(return_value=False)):
        await controller.execute_control(control.key, "long_press")
    assert written(coordinator) == []


@pytest.mark.parametrize("pulse_count", [30, 31])
async def test_held_state_four_release_only_within_short_window(coordinator, pulse_count):
    code, control = find_control(1, 4)
    controller = make_controller(coordinator, code)
    coordinator.motor_pulse_count = pulse_count
    with patch.object(controller, "_wait_ticks", new=AsyncMock(return_value=True)):
        await controller.execute_control(control.key)
    expected = [control.press.legacy] * pulse_count
    if pulse_count == 30:
        expected.append(control.release.legacy)
    assert written(coordinator) == expected


async def test_one_shot_keeps_explicit_release(coordinator):
    code, control = find_control(5, 2)
    controller = make_controller(coordinator, code)
    await controller.execute_control(control.key)
    assert written(coordinator) == [control.press.legacy, control.release.legacy]


async def test_undefined_mode_unknown_controls_and_gestures_do_not_write(coordinator):
    code, control = find_control(5, 2)
    controller = make_controller(coordinator, code)
    for key, gesture in [("missing-control", "press"), (control.key, "invalid-gesture")]:
        with pytest.raises(ValueError):
            await controller.execute_control(key, gesture)
    legacy_only = next(
        (code, item)
        for code in LP_LEGACY_PROFILE_CODES
        for item in get_lp_legacy_profile(code).controls
        if item.press.framed is None
    )
    controller = make_controller(coordinator, legacy_only[0], mode="framed")
    with pytest.raises(ValueError):
        await controller.execute_control(legacy_only[1].key)
    assert written(coordinator) == []


async def test_preexisting_cancellation_never_dispatches(coordinator):
    code, control = find_control(1, 2)
    controller = make_controller(coordinator, code)
    coordinator.cancel_command.set()
    await controller.execute_control(control.key)
    assert written(coordinator) == []


async def test_selected_gatt_endpoint_requires_write_property(coordinator):
    controller = make_controller(coordinator)
    coordinator.client.services.get_characteristic.return_value.properties = ["read"]
    with pytest.raises(ValueError, match="not writable"):
        await controller.write_command(b"4")
    assert written(coordinator) == []
    coordinator.client.services.get_characteristic.return_value.properties = [
        "write-without-response"
    ]
    await controller.write_command(b"4")
    coordinator.client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, b"4", response=False)


async def test_explicit_read_endpoint_and_exact_diagnostic_frames(coordinator):
    controller = make_controller(coordinator, read_uuid=READ_UUID)
    assert controller.requires_notification_channel
    characteristic = MagicMock(uuid=READ_UUID, properties=["notify"])
    coordinator.client.services.get_characteristic.return_value = characteristic
    await controller.start_notify()
    coordinator.client.start_notify.assert_awaited_once_with(
        READ_UUID, controller._notification_handler
    )
    for packet, effect in [
        ("6E 09 01 00 78", "app_status_5"),
        ("6E 07 01 01 77", "alarm_routine_1"),
        ("6E 07 01 02 78", "alarm_routine_2"),
    ]:
        controller._notification_handler(characteristic, bytearray.fromhex(packet))
        coordinator.handle_controller_state_updates.assert_called_with(
            {"lp_legacy_notification": packet, "lp_legacy_notification_effect": effect}
        )
    coordinator.handle_controller_state_updates.reset_mock()
    for packet in ["6E 09 01 00 79", "6E 09 01 00 78 00", "6E 09 01"]:
        controller._notification_handler(characteristic, bytearray.fromhex(packet))
    coordinator.handle_controller_state_updates.assert_not_called()
    await controller.stop_notify()
    coordinator.client.stop_notify.assert_awaited_once_with(READ_UUID)


def test_no_guessed_standard_entities(coordinator):
    controller = make_controller(coordinator)
    assert not controller.supports_motor_control
    assert not controller.supports_preset_flat
    assert controller.supports_stop_all
    assert not controller.supports_position_feedback
    assert not controller.requires_notification_channel
    assert not controller.supports_massage
    assert controller.memory_slot_count == 0
    specs = controller.controller_button_specs
    assert specs
    assert len({spec.key for spec in specs}) == len(specs)
    assert len({spec.name for spec in specs}) == len(specs)


async def test_button_callback_uses_current_controller(coordinator):
    original = make_controller(coordinator)
    current = make_controller(coordinator)
    with (
        patch.object(original, "execute_control", new=AsyncMock()) as stale,
        patch.object(current, "execute_control", new=AsyncMock()) as active,
    ):
        await original.controller_button_specs[0].press_fn(current)
    stale.assert_not_awaited()
    active.assert_awaited_once()


async def test_stop_adds_no_global_packet(coordinator):
    controller = make_controller(coordinator)
    await controller.stop_all()
    assert written(coordinator) == []


@pytest.mark.parametrize("mode", ["legacy", "framed"])
async def test_empty_token_keeps_mode_specific_write_behavior(coordinator, mode):
    code, control = next(
        (code, item)
        for code in LP_LEGACY_PROFILE_CODES
        for item in get_lp_legacy_profile(code).controls
        if item.press.token == "" and item.press.state == 5
    )
    controller = make_controller(coordinator, code, mode=mode)
    with patch.object(controller, "_wait_ticks", new=AsyncMock(return_value=True)):
        await controller.execute_control(control.key)
    expected = [bytes.fromhex("6e0100006f")] if mode == "framed" else []
    expected.append(control.release.framed if mode == "framed" else control.release.legacy)
    assert written(coordinator) == expected
