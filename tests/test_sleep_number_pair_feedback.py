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


@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_RIGHT])
@pytest.mark.parametrize("connected", [False, True])
@pytest.mark.parametrize("preset", ["snore", "zero_g"])
async def test_preset_after_reconnect_refreshes_selected_side(
    hass, mock_coordinator_connected, mock_bleak_client, side, connected, preset
):
    """A first press must execute and publish its own side's fresh feedback."""
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
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    updates: dict[str, list[dict[str, float]]] = {SIDE_LEFT: [], SIDE_RIGHT: []}
    for logical_side, child in pair.children.items():
        child.register_position_callback(updates[logical_side].append)
    writes: list[tuple[str, ...]] = []
    positions = {SIDE_LEFT: {"head": 45, "foot": 70}, SIDE_RIGHT: {"head": 8, "foot": 3}}
    target = {"head": 16, "foot": 0} if preset == "snore" else {"head": 46, "foot": 76}
    preset_checks = 0
    intermediate = {"head": 30, "foot": 40}

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
        if command == "AGCP":
            assert args == (side,)
            preset_checks += 1
            if preset_checks == 1:
                # Acceptance can precede both motion and the status change.
                return ["flat"]
            if preset_checks == 2:
                positions[side] = intermediate
                return ["in_progress"]
            positions[side] = target
            return [preset]
        return []

    with (
        patch.object(SleepNumberController, "start_notify", start_notify),
        patch.object(SleepNumberController, "query_config", AsyncMock()),
        patch.object(SleepNumberController, "_send_bamkey_command", send),
        patch(
            "custom_components.adjustable_bed.beds.sleep_number._PRESET_POLL_INTERVAL_SECONDS",
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
                await pair.async_execute_controller_command(
                    lambda controller: (
                        controller.preset_anti_snore()
                        if preset == "snore"
                        else controller.preset_zero_g()
                    ),
                    side=side,
                )
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
            assert [write for write in writes if write[0] == "ACSP"] == [
                ("ACSP", side, preset, "0")
            ]
            assert pair.children[side].position_data == expected
            assert {"back": 30.0, "legs": 40.0} in updates[side]
            assert preset_checks == 3
            other_side = SIDE_RIGHT if side == SIDE_LEFT else SIDE_LEFT
            expected_other = (
                {"back": 8.0, "legs": 3.0} if side == SIDE_LEFT else {"back": 45.0, "legs": 70.0}
            )
            assert pair.children[other_side].position_data == expected_other
        finally:
            await pair.async_shutdown()


@pytest.mark.parametrize("outcome", ["complete", "cancel", "timeout", "disabled"])
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
            if outcome == "cancel":
                asyncio.get_running_loop().call_soon(coordinator.cancel_command.set)
            return ["zero_g" if outcome == "complete" else "in_progress"]
        if command == "ACTG":
            return ["44" if args[1] == "head" else "73"]
        return []

    controller._send_bamkey_command = AsyncMock(side_effect=send)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._PRESET_POLL_INTERVAL_SECONDS",
        0.001,
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.sleep_number._PRESET_FEEDBACK_TIMEOUT_SECONDS",
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
    else:
        await controller.preset_zero_g()
        assert checks == (0 if outcome == "disabled" else 1)

    if outcome == "disabled":
        callback.assert_not_called()
    else:
        callback.assert_has_calls([call("back", 44.0), call("legs", 73.0)])
    assert controller._send_bamkey_command.await_args_list[0] == call("ACSP", "left", "zero_g", "0")
