"""Native lighting queues behind motion; existing named actions still preempt."""

from __future__ import annotations

import asyncio
from dataclasses import fields
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.base import ControllerButtonSpec, ProductButtonSpec
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    entity_runtimes,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.test_starcode_abm5_4 import make_controller

LIGHT_FRAMES = {
    "light_plus": "04e000040000",
    "light_minus": "04e000020000",
    "light_on": "04e001010000",
    "light_off": "04e001000000",
}


def physical_target(hass: HomeAssistant, address: str, transport: str = "BOX1220"):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Native app",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX25",
            const.CONF_STARCODE_UI_SELECTOR: "BOX25",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller(device=transport)
    client = controller.client

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    controller._coordinator = coordinator
    controller._owner_address = coordinator.address
    coordinator._client, coordinator._controller = client, controller
    coordinator.async_ensure_connected = AsyncMock(return_value=True)
    controller._ready = True
    controller._light_on, controller._level = True, 3
    return coordinator, controller


@pytest.mark.parametrize("side", ["standalone", "left", "right", "both"])
@pytest.mark.parametrize("movement", ["held", "timed", "save"])
@pytest.mark.parametrize("action", list(LIGHT_FRAMES))
async def test_public_light_button_queues_after_native_movement_release(
    hass: HomeAssistant, side: str, movement: str, action: str
) -> None:
    await async_register_services(hass)
    transport = "BOX3633" if action in ("light_on", "light_off") else "BOX1220"
    first, first_controller = physical_target(hass, "AA:BB:CC:DD:EE:01", transport)
    children = {"left": first}
    controllers = {"left": first_controller}
    if side == "standalone":
        target, runtime = first, first
        active_sides = ("left",)
        service_side = const.SIDE_BOTH
        button_side = "left"
    else:
        second, second_controller = physical_target(hass, "AA:BB:CC:DD:EE:02", transport)
        children["right"], controllers["right"] = second, second_controller
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                const.CONF_PAIR_ID: "native-buttons",
                CONF_NAME: "Pair",
            },
        )
        entry.add_to_hass(hass)
        target = PairedBedCoordinator(hass, entry, children)
        dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **target.device_info)
        views = {view.entity_side: view for view in entity_runtimes(target)}
        button_side = "left" if side == "both" else side
        runtime = views[button_side]
        active_sides = ("left", "right") if side == "both" else (side,)
        service_side = side
    controller = controllers[button_side]
    spec = next(s for s in controller.controller_button_specs if s.key.endswith(action))
    button = ControllerActionButton(runtime, spec)
    entered = {key: asyncio.Event() for key in active_sides}
    captured: dict[str, asyncio.Event] = {}
    finish, queued = asyncio.Event(), asyncio.Event()

    def pause(key):
        async def wait(_seconds, event):
            captured[key] = event
            entered[key].set()
            await finish.wait()
            return False

        return wait

    real_execute = target.async_execute_controller_command

    async def observe_admission(command, **kwargs):
        queued.set()
        await real_execute(command, **kwargs)

    async def move():
        if movement == "timed":
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {
                    "device_id": ["native"],
                    "motor": "back",
                    "direction": "up",
                    "duration_ms": 1000,
                },
                blocking=True,
            )
        else:
            await hass.services.async_call(
                const.DOMAIN,
                "starcode_abm5_4_hold_control",
                {
                    "device_id": ["native"],
                    "control": "save_memory_1" if movement == "save" else "head_up",
                    "duration": 1,
                },
                blocking=True,
            )

    tasks = []
    try:
        from contextlib import ExitStack

        with ExitStack() as stack:
            for key in active_sides:
                stack.enter_context(patch.object(controllers[key], "_wait", pause(key)))
            stack.enter_context(
                patch(
                    "custom_components.adjustable_bed.services._resolve_sided_targets",
                    return_value=([(target, service_side)], []),
                )
            )
            tasks.append(asyncio.create_task(move()))
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 2)
            stack.enter_context(
                patch.object(target, "async_execute_controller_command", observe_admission)
            )
            tasks.append(asyncio.create_task(button.async_press()))
            await asyncio.wait_for(queued.wait(), 2)
            await asyncio.sleep(0)
            assert all(not event.is_set() for event in captured.values())
            assert all(not task.done() for task in tasks)
            first_frame = "05020001000000" if movement == "save" else "05020000000100"
            for key in active_sides:
                assert [
                    c.args[1].hex() for c in controllers[key].client.write_gatt_char.await_args_list
                ] == [first_frame]
            finish.set()
            await asyncio.wait_for(asyncio.gather(*tasks), 2)
        for key, current in controllers.items():
            expected = []
            if key in active_sides:
                expected = [first_frame, "05020000000000"]
                if movement == "timed":
                    expected.append("05020000000000")
            if key == button_side:
                expected.append(LIGHT_FRAMES[action])
            assert [
                c.args[1].hex() for c in current.client.write_gatt_char.await_args_list
            ] == expected
        assert children[button_side]._command_scheduler.recent_records[-1].resources == (
            "lighting",
        )
        assert all(
            record.outcome == "completed"
            for child in children.values()
            for record in child._command_scheduler.recent_records
        )
    finally:
        finish.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await target.async_shutdown()


async def test_default_named_motor_button_still_replaces_held_movement(hass: HomeAssistant):
    coordinator, controller = physical_target(hass, "AA:BB:CC:DD:EE:01")
    entered = asyncio.Event()
    captured = []

    async def wait(_seconds, event):
        if not entered.is_set():
            captured.append(event)
            entered.set()
            await event.wait()
        return False

    async def move(current):
        await current.hold_control("head_up", 1000)

    spec = next(s for s in controller.controller_button_specs if s.key.endswith("union_down"))
    task = None
    try:
        with patch.object(controller, "_wait", wait):
            task = asyncio.create_task(coordinator.async_execute_controller_command(move))
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(ControllerActionButton(coordinator, spec).async_press(), 2)
            await asyncio.wait_for(task, 2)
        assert captured[0].is_set()
        assert [c.args[1].hex() for c in controller.client.write_gatt_char.await_args_list] == [
            "05020000000100",
            "05020000000000",
            "05020000000a00",
            "05020000000000",
        ]
        records = coordinator._command_scheduler.recent_records
        assert records[0].outcome == "replaced"
        assert records[-1].resources == ("*",)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await coordinator.async_shutdown()


def test_named_button_metadata_preserves_product_positional_constructor():
    press = AsyncMock()
    spec = ProductButtonSpec("legacy", "Legacy", press, "mdi:bed", "legacy_key", True)
    assert spec.entity_registry_enabled_default is True
    assert spec.cancel_movement is True and spec.scheduler_resource is None
    assert all(
        field.kw_only
        for field in fields(ControllerButtonSpec)
        if field.name in ("cancel_movement", "scheduler_resource")
    )
