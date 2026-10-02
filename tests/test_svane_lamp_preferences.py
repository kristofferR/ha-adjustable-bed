"""One guarded preference batch per public lamp hold, including failed writes."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.svane_state import CONF_SVANE_PREFERENCES
from tests.test_svane_light_timed_host import runtime as svane_runtime

runtime = svane_runtime


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("termination", ["success", "ble", "cancel"])
async def test_public_lamp_hold_persists_final_intent_once(hass, runtime, monkeypatch, termination):
    coordinator, controller = runtime
    controller.session.light_on = True
    coordinator.remember_svane_preferences(controller.session.preferences())
    client = controller.client
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio)
    blocked = asyncio.Event()
    steps = []

    async def advance(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)
        return True

    async def write(role, payload, **kwargs):
        steps.append((clock[0], role.uuid, bytes(payload).hex(),
                      coordinator.controller_state["svane_intensity"]))
        if len(steps) == 2:
            if termination == "ble":
                raise BleakError("second brightness write failed")
            if termination == "cancel":
                blocked.set()
                await asyncio.Event().wait()

    controller._wait = advance
    client.write_gatt_char.side_effect = write
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        patch.object(coordinator, "remember_svane_preferences",
                     wraps=coordinator.remember_svane_preferences) as remember,
        patch.object(hass.config_entries, "async_update_entry",
                     wraps=hass.config_entries.async_update_entry) as update,
    ):
        task = asyncio.create_task(hass.services.async_call(DOMAIN, "svane_hold_control", {
            "device_id": "bed", "control": "light_adjust", "duration": .5,
        }, blocking=True))
        try:
            if termination == "cancel":
                await blocked.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            elif termination == "ble":
                with pytest.raises(BleakError):
                    await task
            else:
                await task
            remember.assert_called_once_with(controller.session.preferences())
            preference_updates = [call for call in update.call_args_list
                                  if CONF_SVANE_PREFERENCES in call.kwargs.get("data", {})]
            assert len(preference_updates) == 1
            assert coordinator.entry.data[CONF_SVANE_PREFERENCES] == controller.session.preferences()
            assert [s[2] for s in steps] == (
                ["13025f010064", "130264010064", "13025f010064"]
                if termination == "success" else ["13025f010064", "130264010064"]
            )
            assert [s[0] for s in steps] == pytest.approx(
                [.2, .3, .4] if termination == "success" else [.2, .3]
            )
            assert [s[3] for s in steps] == ([95, 100, 95] if termination == "success" else [95, 100])
            assert controller.session.light_on and not controller._started
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("reason", ["off", "short", "cancelled"])
async def test_unchanged_public_lamp_hold_does_not_persist(hass, runtime, reason):
    coordinator, controller = runtime
    controller.session.light_on = reason != "off"

    async def wait_without_step(seconds):
        if reason == "cancelled":
            coordinator.cancel_command.set()
        return False

    controller._wait = wait_without_step
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        patch.object(coordinator, "remember_svane_preferences") as remember,
    ):
        await hass.services.async_call(DOMAIN, "svane_hold_control", {
            "device_id": "bed", "control": "light_adjust",
            "duration": .2 if reason == "short" else .5,
        }, blocking=True)
    remember.assert_not_called()
    controller.client.write_gatt_char.assert_not_awaited()
    await coordinator._command_scheduler.async_shutdown()
