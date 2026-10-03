"""Registered held-light controls preserve validated lamp boundaries and intent."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.number import _number_entities_for
from tests.app_state_helpers import stored_app_state, write_app_state
from tests.test_svane import LIGHT, OLD, OLD_CHAR, SvaneCommands, uuid, written
from tests.test_svane_light_timed_host import runtime as imported_runtime

runtime = imported_runtime


def virtual_hold(monkeypatch, controller):
    clock = [0.0]
    local = SimpleNamespace(**vars(asyncio))
    local.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr('custom_components.adjustable_bed.beds.svane.asyncio', local)

    async def wait(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)
        return True

    controller._wait = wait


async def hold(hass, coordinator):
    with patch('custom_components.adjustable_bed.services._resolve_sided_targets',
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, 'svane_hold_control', {
            'device_id': 'bed', 'control': 'light_adjust', 'duration': .201,
        }, blocking=True)


@pytest.mark.parametrize('runtime', ['multi', 'jmc'], indirect=True)
@pytest.mark.parametrize('initial,step,expected', [(5, 5, 10), (5, -5, 10), (100, -5, 95), (100, 5, 95)])
async def test_public_direct_intensity_then_hold_keeps_inward_step_or_reverses_outward(
    hass, runtime, monkeypatch, initial, step, expected
):
    coordinator, controller = runtime
    controller.session.light_step = step
    number = next(n for n in _number_entities_for(hass, coordinator)
                  if n.entity_description.key == 'light_level')
    await number.async_set_native_value(initial)
    controller.client.write_gatt_char.reset_mock()
    virtual_hold(monkeypatch, controller)
    await hold(hass, coordinator)
    assert controller.session.intensity == expected
    assert (await stored_app_state(coordinator))['intensity'] == expected
    assert coordinator.controller_state['svane_intensity'] == expected
    assert coordinator.controller_state['under_bed_lights_on'] is True
    role = (OLD, OLD_CHAR) if controller.profile == 'jmc' else (
        LIGHT, uuid('b5e9' if expected > initial else '3fb2'))
    assert written(controller) == [(*role,
                                    SvaneCommands.light_brightness(expected).hex())]
    await coordinator.async_execute_controller_command(lambda c: c.lights_toggle())
    assert written(controller)[-1][2] == '130200000000'
    assert not controller.session.light_on


@pytest.mark.parametrize('runtime', ['multi', 'jmc'], indirect=True)
@pytest.mark.parametrize('initial', [6, 96, 99])
@pytest.mark.parametrize('step', [-5, 5])
async def test_public_hold_rejects_nonstep_session_before_mutation_or_io(
    hass, runtime, monkeypatch, initial, step
):
    coordinator, controller = runtime
    controller.session.intensity = initial
    controller.session.light_step = step
    controller.session.light_on = True
    before = dict(coordinator.entry.data)
    virtual_hold(monkeypatch, controller)
    with pytest.raises(ServiceValidationError, match='steps of five'):
        await hold(hass, coordinator)
    assert controller.session.intensity == initial and controller.session.light_step == step
    assert coordinator.entry.data == before
    controller.client.write_gatt_char.assert_not_awaited()
    await coordinator.async_execute_controller_command(lambda c: c.set_light_level(95))
    assert controller.session.intensity == 95 and controller.session.light_on
    assert written(controller)[-1][2] == '13025f010064'


@pytest.mark.parametrize('runtime', ['multi', 'jmc'], indirect=True)
@pytest.mark.parametrize('initial,expected', [(5, 10), (100, 95)])
async def test_factory_restored_valid_boundary_adjusts_without_invalid_preferences(
    hass, runtime, monkeypatch, initial, expected
):
    coordinator, previous = runtime
    coordinator._controller = None  # A restart: no earlier controller saves over the record.
    await write_app_state(coordinator, {'intensity': initial}, previous.profile)
    controller = await create_controller(coordinator, BED_TYPE_SVANE,
                                         coordinator.entry.data[CONF_PROTOCOL_VARIANT], None)
    assert isinstance(controller, SvaneController)
    await coordinator._async_restore_app_state(controller)
    assert controller.session.intensity == initial
    assert controller.session.light_step == 5
    coordinator._controller = controller
    await coordinator.async_execute_controller_command(lambda c: c.lights_on())
    controller.client.write_gatt_char.reset_mock()
    virtual_hold(monkeypatch, controller)
    await hold(hass, coordinator)
    assert controller.session.intensity == expected
    assert (await stored_app_state(coordinator))['intensity'] == expected
    assert len(written(controller)) == 1


@pytest.mark.parametrize('runtime', ['multi', 'jmc'], indirect=True)
async def test_public_boundary_hold_caller_cancel_keeps_valid_intent_without_lamp_release(
    hass, runtime
):
    coordinator, controller = runtime
    await coordinator.async_execute_controller_command(lambda c: c.set_light_level(5))
    controller.client.write_gatt_char.reset_mock()
    adjusted = asyncio.Event()

    async def wait(seconds):
        if seconds == .2:
            return True
        adjusted.set()
        await coordinator.cancel_command.wait()
        return False

    controller._wait = wait
    task = asyncio.create_task(hold(hass, coordinator))
    try:
        async with asyncio.timeout(1):
            await adjusted.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert controller.session.intensity == 10 and controller.session.light_on
        assert (await stored_app_state(coordinator))['intensity'] == 10
        assert len(written(controller)) == 1
        assert written(controller)[0][2] == '13020a010064'
        assert not controller.ble_lock.locked() and not coordinator._command_lock.locked()
        await coordinator.async_execute_controller_command(lambda c: c.lights_toggle())
        assert written(controller)[-1][2] == '130200000000'
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
