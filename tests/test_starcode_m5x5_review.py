"""Public conversion, queued group dispatch and profile registry boundaries."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    CONF_BLE_DEVICE_NAME,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M5X5_PROFILE,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.pairing_candidates import active_pairing_candidates
from custom_components.adjustable_bed.starcode_accessory_group import _GROUP_DISPATCH, run_group
from tests.test_starcode_accessory_group import group, target


async def test_pair_conversion_rechecks_group_members_without_absorbing_ids(
    hass: HomeAssistant,
) -> None:
    main, *lifts = group(hass)
    free = [target(hass, i, "cb25") for i in (10, 11)]
    for member in (main, *lifts, *free):
        member.entry.mock_state(hass, ConfigEntryState.LOADED)
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    assert {entry.entry_id for entry in active_pairing_candidates(hass)} == {
        member.entry.entry_id for member in free
    }
    # A stale picker submission cannot consume a referenced main or lift.
    for member in (main, *lifts):
        result = await flow.async_step_pair_beds(
            {"left_entry": member.entry.entry_id, "right_entry": free[0].entry.entry_id}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "unknown"}
        assert hass.config_entries.async_get_entry(member.entry.entry_id) is member.entry
    assert list(main.entry.data[CONF_STARCODE_LIFT_ENTRIES]) == [
        lift.entry.entry_id for lift in lifts
    ]
    # Detaching the main's selection makes all standalone identities pairable again.
    hass.config_entries.async_update_entry(
        main.entry, data={**main.entry.data, CONF_STARCODE_LIFT_ENTRIES: []}
    )
    assert {entry.entry_id for entry in active_pairing_candidates(hass)} == {
        member.entry.entry_id for member in (main, *lifts, *free)
    }


async def test_ordinary_queued_intent_leaves_group_context_and_interrupts_retained_flat(
    hass: HomeAssistant,
) -> None:
    main, *lifts = group(hass)
    for member in (main, *lifts):
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()
    flat_entered = asyncio.Event()
    release_flat = asyncio.Event()
    ordinary_started = asyncio.Event()
    observed: list[bool] = []
    workers: list[asyncio.Task[object] | None] = []

    async def write(command, **kwargs):
        if command == bytes.fromhex("5a0103103010a5"):
            flat_entered.set()
            await release_flat.wait()

    main.controller.write_command.side_effect = write

    async def ordinary(controller):
        observed.append(_GROUP_DISPATCH.get())
        workers.append(main._command_scheduler._worker)
        ordinary_started.set()
        await controller.move_head_up()

    retained = asyncio.create_task(run_group(main, "flat"))
    queued = None
    try:
        async with asyncio.timeout(3):
            await flat_entered.wait()
            queued = asyncio.create_task(
                main.async_execute_controller_command(
                    ordinary, cancel_running=False, read_positions_after_operation=False
                )
            )
            while not main._command_scheduler._queue:
                await asyncio.sleep(0)
            worker = main._command_scheduler._worker
            release_flat.set()
            await ordinary_started.wait()
            await queued
            assert workers == [worker]
            assert observed == [False]
            with pytest.raises(asyncio.CancelledError):
                await retained
        assert not any(
            call.args[0] == bytes.fromhex("5a0103103046a5")
            for call in lifts[0].controller.write_command.await_args_list
        )
        assert all(member.async_stop_command.await_count >= 1 for member in (main, *lifts))
        assert _GROUP_DISPATCH.get() is False
    finally:
        release_flat.set()
        for task in (retained, queued):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (retained, queued) if task is not None), return_exceptions=True
        )


@pytest.mark.parametrize("profile", ["cb25", "f23", "kneading"])
async def test_options_reject_an_elevate_name_for_an_app_bed_class(
    hass: HomeAssistant, profile: str
) -> None:
    """ELEVATE lifts use the DewertOkin ELEVATE bed type, never an app bed class."""
    old = target(hass, 1, profile)
    before = dict(old.entry.data)
    flow = AdjustableBedOptionsFlow(old.entry)
    flow.handler = old.entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings(
        {CONF_STARCODE_M5X5_PROFILE: profile, CONF_BLE_DEVICE_NAME: "ELEVATE123456"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_STARCODE_M5X5_PROFILE: "starcode_elevate_bed_type"}
    assert dict(old.entry.data) == before
