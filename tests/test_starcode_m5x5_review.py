"""Public conversion, queued group dispatch and profile registry boundaries."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.beds.starcode_m5x5 import StarcodeM5X5Controller
from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M5X5_PROFILE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.pairing_candidates import active_pairing_candidates
from custom_components.adjustable_bed.sensor import _sensor_entities_for
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
async def test_options_elevate_reload_removes_all_old_position_and_telemetry_rows(
    hass: HomeAssistant, profile: str
) -> None:
    old = target(hass, 1, profile)
    old._disable_angle_sensing = False
    registry = er.async_get(hass)
    removed_ids: set[str] = set()
    for domain, entities in (
        ("number", _number_entities_for(hass, old)),
        ("sensor", _sensor_entities_for(hass, old)),
        ("binary_sensor", _binary_sensor_entities_for(hass, old)),
    ):
        for entity in entities:
            unique_id = entity.unique_id
            assert isinstance(unique_id, str)
            row = registry.async_get_or_create(domain, DOMAIN, unique_id, config_entry=old.entry)
            if (
                unique_id.endswith(("back_position", "legs_position", "lumbar_position"))
                or "_starcode_" in unique_id
            ):
                removed_ids.add(row.entity_id)
    assert any("firmware" in row for row in removed_ids)
    assert (
        len([row for row in removed_ids if row.startswith("number.")]) == 4
    )  # three positions and brightness
    connection_id = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, old.entity_unique_id("ble_connection")
    )
    # Submit the real public options transition, then reconstruct its runtime as on reload.
    flow = AdjustableBedOptionsFlow(old.entry)
    flow.handler = old.entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings(
        {CONF_STARCODE_M5X5_PROFILE: "elevate", CONF_BLE_DEVICE_NAME: "ELEVATE123456"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert old.entry.data[CONF_DISABLE_ANGLE_SENSING] is True
    current = AdjustableBedCoordinator(hass, old.entry)
    current._client = MagicMock(is_connected=True)
    controller = StarcodeM5X5Controller(current, profile="elevate")
    controller._ready = True
    current._controller = controller
    _number_entities_for(hass, current)
    _sensor_entities_for(hass, current)
    _binary_sensor_entities_for(hass, current)
    remaining = [entity_id for entity_id in removed_ids if registry.async_get(entity_id) is not None]
    assert remaining == []
    if connection_id is not None:
        assert registry.async_get(connection_id) is not None
