"""Sleep Number logical-side feedback through the real command lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sleep_number import SleepNumberController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_PAIR_ID,
    DOMAIN,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator


@pytest.fixture
def feedback_pair(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Paired Sleep Number",
            CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_PAIR_ID: "sleep_number_feedback",
        },
    )
    entry.add_to_hass(hass)
    inner = AdjustableBedCoordinator(hass, entry)
    return SingleAddressPairedCoordinator(hass, entry, inner)


@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_RIGHT])
@pytest.mark.parametrize("connected", [False, True])
@pytest.mark.parametrize(
    "action",
    [
        "snore",
        "zero_g",
        "target",
        "hold",
        "service_target",
        "service_micro",
        "service_preset",
        "service_timed_preset",
    ],
)
async def test_movement_after_reconnect_refreshes_selected_side(
    hass, mock_coordinator_connected, mock_bleak_client, feedback_pair, side, connected, action
):
    """Every movement entry point must publish intermediate and final feedback."""
    pair = feedback_pair
    inner = pair._single_inner
    updates: dict[str, list[dict[str, float]]] = {SIDE_LEFT: [], SIDE_RIGHT: []}
    for logical_side, child in pair.children.items():
        child.register_position_callback(updates[logical_side].append)
    writes: list[tuple[str, ...]] = []
    positions = {SIDE_LEFT: {"head": 45, "foot": 70}, SIDE_RIGHT: {"head": 8, "foot": 3}}
    preset = "snore" if action == "snore" else "zero_g"
    is_target = action in {"target", "hold", "service_target", "service_micro"}
    target = (
        {"head": 100 if action == "hold" else 61, "foot": positions[side]["foot"]}
        if is_target
        else {"head": 16, "foot": 0}
        if preset == "snore"
        else {"head": 46, "foot": 76}
    )
    preset_checks = 0
    intermediate = {"head": 30, "foot": positions[side]["foot"] if is_target else 40}

    async def control(controller):
        if action == "target":
            await controller.set_motor_position("back", 61)
        elif action == "hold":
            await controller.move_back_up()
        elif action in {"service_target", "service_micro"}:
            await controller.async_execute_sleep_number_command(
                "set_actuator_target_position"
                + ("_with_timer" if action == "service_micro" else ""),
                {"side": side, "actuator": "head", "target_actuator_position": 61},
            )
        elif action == "service_preset":
            await controller.async_execute_sleep_number_command(
                "set_target_preset_without_timer",
                {"side": side, "target_preset": preset},
            )
        elif action == "service_timed_preset":
            await controller.async_execute_sleep_number_command(
                "set_target_preset_with_timer",
                {"side": side, "target_preset_with_timer": preset, "timer": 15},
            )
        elif preset == "snore":
            await controller.preset_anti_snore()
        else:
            await controller.preset_zero_g()

    async def start_notify(controller, callback):
        controller._notify_callback = callback

    async def send(controller, command, *args, **kwargs):
        nonlocal preset_checks
        if controller._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        writes.append((command, *args))
        await asyncio.sleep(0.001)
        if command == "ACTG":
            return [str(positions[args[0]][args[1]])]
        if command in {"AGCP", "ACTM"}:
            assert args == (() if is_target else (side,))
            preset_checks += 1
            if preset_checks == 2:
                positions[side] = intermediate
            elif preset_checks >= 3:
                positions[side] = target
            if is_target:
                # Other-side and other-axis motion must not prolong this target.
                state = ["1"] * 4
                state[0 if side == SIDE_RIGHT else 2] = "1" if preset_checks == 2 else "0"
                return state
            return [
                "flat" if preset_checks == 1 else "in_progress" if preset_checks == 2 else preset
            ]
        return []

    with (
        patch.object(SleepNumberController, "start_notify", start_notify),
        patch.object(SleepNumberController, "query_config", AsyncMock()),
        patch.object(SleepNumberController, "_send_bamkey_command", send),
        patch(
            "custom_components.adjustable_bed.beds.sleep_number._MOVEMENT_POLL_INTERVAL_SECONDS",
            0.001,
        ),
        patch.object(inner, "_async_record_verified_bond", AsyncMock(return_value=True)),
        patch.object(inner, "_should_refresh_readable_light_state", return_value=False),
    ):
        try:
            async with asyncio.timeout(5):
                if connected:
                    await pair.async_connect()
                    if pair._single_position_hydration_task is not None:
                        await pair._single_position_hydration_task
                await pair.async_execute_controller_command(control, side=side)
                expected = {"back": float(target["head"]), "legs": float(target["foot"])}
                assert pair.children[side].position_data == expected
                assert updates[side][-1] == expected
                await hass.async_block_till_done()
                hydration = pair._single_position_hydration_task
                if hydration is not None:
                    await hydration
                background = inner._background_read_task
                if background is not None:
                    await background
            expected_command = (
                ("ASTM" if action == "service_micro" else "ACTS", side, "head", str(target["head"]))
                if is_target
                else ("ASTP", side, preset)
                if action == "service_preset"
                else ("ACSP", side, preset, "15" if action == "service_timed_preset" else "0")
            )
            assert [write for write in writes if write[0] in {"ACTS", "ASTM", "ACSP", "ASTP"}] == [
                expected_command
            ]
            assert pair.children[side].position_data == expected
            assert {"back": 30.0, "legs": float(intermediate["foot"])} in updates[side]
            assert preset_checks == 3
            other_side = SIDE_RIGHT if side == SIDE_LEFT else SIDE_LEFT
            expected_other = (
                {"back": 8.0, "legs": 3.0} if side == SIDE_LEFT else {"back": 45.0, "legs": 70.0}
            )
            assert pair.children[other_side].position_data == expected_other
        finally:
            await pair.async_shutdown()


@pytest.mark.parametrize("outcome", ["complete", "cancel", "timeout", "read_error", "disabled"])
async def test_standalone_preset_feedback_lifecycle(outcome, monkeypatch):
    """Polling is bounded, cancellable, optional, and publishes measured values."""
    coordinator = MagicMock()
    coordinator.disable_angle_sensing = outcome == "disabled"
    coordinator.cancel_command = asyncio.Event()
    controller = SleepNumberController(coordinator)
    callback = MagicMock()
    controller._notify_callback = callback
    checks = 0

    async def send(command, *args, **kwargs):
        nonlocal checks
        if command == "AGCP":
            checks += 1
            if outcome == "read_error":
                raise ConnectionError("Lost feedback")
            if outcome == "cancel":
                asyncio.get_running_loop().call_soon(coordinator.cancel_command.set)
            return ["zero_g" if outcome == "complete" else "in_progress"]
        if command == "ACTG":
            return ["44" if args[1] == "head" else "73"]
        return []

    controller._send_bamkey_command = AsyncMock(side_effect=send)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._MOVEMENT_POLL_INTERVAL_SECONDS",
        0.001,
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._MOVEMENT_FEEDBACK_TIMEOUT_SECONDS",
        0.05,
    )
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await controller.preset_zero_g()
        assert checks == 1
    elif outcome == "timeout":
        with pytest.raises(TimeoutError):
            await controller.preset_zero_g()
        assert checks > 1
    elif outcome == "read_error":
        with pytest.raises(ConnectionError, match="Lost feedback"):
            await controller.preset_zero_g()
    else:
        await controller.preset_zero_g()
        assert checks == (0 if outcome == "disabled" else 1)

    if outcome == "disabled":
        callback.assert_not_called()
    else:
        callback.assert_has_calls([call("back", 44.0), call("legs", 73.0)])
    assert controller._send_bamkey_command.await_args_list[0] == call(
        "ACSP", "left", "zero_g", "0", expected_args=0
    )
    if outcome in {"cancel", "timeout", "read_error"}:
        halt = next(
            entry
            for entry in controller._send_bamkey_command.await_args_list
            if entry.args[0] == "ACHA"
        )
        assert not halt.kwargs["cancel_event"].is_set()


@pytest.mark.parametrize("interrupt", ["stop", "replace", "shutdown"])
async def test_held_motion_cleanup_precedes_replacement(
    hass, mock_coordinator_connected, mock_bleak_client, feedback_pair, interrupt, monkeypatch
):
    """Real scheduler cancellation halts before releasing the queue and refreshes both sides."""
    pair = feedback_pair
    inner = pair._single_inner
    observed_motion = asyncio.Event()
    positions = {"left": {"head": 35, "foot": 20}, "right": {"head": 12, "foot": 4}}
    writes = []
    moving = False

    async def start_notify(controller, callback):
        controller._notify_callback = callback

    async def send(controller, command, *args, **kwargs):
        nonlocal moving
        cancel = kwargs.get("cancel_event") or controller._coordinator.cancel_command
        if cancel.is_set():
            raise asyncio.CancelledError
        writes.append((command, *args))
        await asyncio.sleep(0)
        if command == "ACTS":
            moving = args[1] == "head"
            if not moving:
                positions["left"]["foot"] = int(args[2])
        elif command == "ACTM":
            if moving:
                observed_motion.set()
            return ["0", "0", "1" if moving else "0", "0"]
        elif command == "ACHA":
            moving = False
            positions["left"]["head"] = 37
        elif command == "ACTG":
            return [str(positions[args[0]][args[1]])]
        return []

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._MOVEMENT_POLL_INTERVAL_SECONDS", 0.001
    )
    with (
        patch.object(SleepNumberController, "start_notify", start_notify),
        patch.object(SleepNumberController, "query_config", AsyncMock()),
        patch.object(SleepNumberController, "_send_bamkey_command", send),
        patch.object(inner, "_async_record_verified_bond", AsyncMock(return_value=True)),
        patch.object(inner, "_should_refresh_readable_light_state", return_value=False),
    ):
        movement = asyncio.create_task(
            pair.async_execute_controller_command(
                lambda controller: controller.move_back_up(), side="left"
            )
        )
        try:
            async with asyncio.timeout(5):
                await observed_motion.wait()
                if interrupt == "stop":
                    await pair.children["left"].async_stop_command()
                elif interrupt == "replace":
                    await pair.async_execute_controller_command(
                        lambda controller: controller.set_motor_position("legs", 62), side="left"
                    )
                else:
                    await pair.async_shutdown()
                await movement
            halt_index = writes.index(("ACHA",))
            assert ("ACTG", "left", "head") in writes[halt_index + 1 :]
            assert ("ACTG", "right", "head") in writes[halt_index + 1 :]
            assert inner.position_data["left_back"] == 37
            assert inner.position_data["right_back"] == 12
            if interrupt != "shutdown":
                assert pair.children["left"].position_data["back"] == 37
                assert pair.children["right"].position_data == {"back": 12.0, "legs": 4.0}
            if interrupt == "replace":
                assert halt_index < writes.index(("ACTS", "left", "foot", "62"))
                assert pair.children["left"].position_data["legs"] == 62
        finally:
            movement.cancel()
            await asyncio.gather(movement, return_exceptions=True)
            await pair.async_shutdown()


@pytest.mark.parametrize("final_state", ["done", "error", "required"])
async def test_homing_tracks_status_and_refreshes_both_sides(final_state, monkeypatch):
    """The global homing service waits for its own status, with measured final readback."""
    coordinator = MagicMock()
    coordinator.disable_angle_sensing = False
    coordinator.cancel_command = asyncio.Event()
    controller = SleepNumberController(coordinator)
    callback = MagicMock()
    controller._notify_callback = callback
    statuses = iter(["in_progress", final_state])

    async def send(command, *args, **kwargs):
        if command == "ACHG":
            return [next(statuses)]
        if command == "ACTG":
            return ["2" if args[0] == "left" else "3"]
        return []

    controller._send_bamkey_command = AsyncMock(side_effect=send)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._MOVEMENT_POLL_INTERVAL_SECONDS", 0.001
    )
    if final_state == "done":
        await controller.async_execute_sleep_number_command("starts_actuator_homing", {})
    else:
        with pytest.raises(ValueError, match=final_state):
            await controller.async_execute_sleep_number_command("starts_actuator_homing", {})
    callback.assert_has_calls(
        [call("back", 2.0), call("legs", 2.0), call("right_back", 3.0), call("right_legs", 3.0)]
    )
    assert [entry.args[0] for entry in controller._send_bamkey_command.await_args_list[:3]] == [
        "ACHS",
        "ACHG",
        "ACHG",
    ]


async def test_unbound_service_does_not_publish_other_side_as_default(monkeypatch):
    """An explicit right-side service cannot overwrite a left standalone display."""
    coordinator = MagicMock()
    coordinator.disable_angle_sensing = False
    coordinator.cancel_command = asyncio.Event()
    controller = SleepNumberController(coordinator)
    callback = MagicMock()
    controller._notify_callback = callback
    controller._system_config = {
        "articulation_enable_flag": "yes",
        "thermal_control_enabled_flag": "none",
        "right_head_actuator": "no",
        "right_foot_actuator": "yes",
    }

    async def send(command, *args, **kwargs):
        if command == "ACTM":
            return ["0", "0", "1", "1"]
        if command == "ACTG":
            assert args == ("right", "foot")
            return ["42"]
        return []

    controller._send_bamkey_command = AsyncMock(side_effect=send)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._MOVEMENT_POLL_INTERVAL_SECONDS", 0.001
    )
    await controller.async_execute_sleep_number_command(
        "set_actuator_target_position",
        {"side": "right", "actuator": "foot", "target_actuator_position": 42},
    )
    callback.assert_called_once_with("right_legs", 42.0)
    assert controller.command_side is None
    assert controller._side == "left"
