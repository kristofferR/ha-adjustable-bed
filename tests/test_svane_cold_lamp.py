"""Real HA switch registration preserves unknown until explicit local intent."""

import asyncio
import logging

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME, STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.app_state_helpers import restart_app_state, write_app_state
from tests.test_svane import make_controller


@pytest.fixture
async def lamp_runtime(hass, request):
    variant = SVANE_VARIANT_JMC if request.param == "jmc" else SVANE_VARIANT_MULTI
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: variant, CONF_DISCONNECT_AFTER_COMMAND: False,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await write_app_state(
        coordinator, {"intensity": 55, "slots": ["81388113", "82738204"]}, request.param
    )
    coordinator._client = make_controller(request.param).client
    controller = await create_controller(coordinator, BED_TYPE_SVANE, variant, coordinator.client)
    assert isinstance(controller, SvaneController)
    coordinator._controller = controller
    await coordinator._async_restore_app_state(controller)
    lamp = next(e for e in _switch_entities_for(hass, coordinator)
                if e.entity_description.key == "under_bed_lights")
    lamp.entity_id = "switch.svane_lamp"
    component = EntityComponent(logging.getLogger(__name__), "switch", hass)
    component._platforms["switch"].config_entry = entry
    await component.async_add_entities([lamp])
    try:
        yield coordinator, controller, lamp, component
    finally:
        await component.async_remove_entity(lamp.entity_id)
        coordinator._cancel_disconnect_timer()
        await coordinator._command_scheduler.async_shutdown()


@pytest.mark.parametrize("lamp_runtime", ["multi", "jmc"], indirect=True)
async def test_registered_cold_switch_is_unknown_despite_restored_preferences(hass, lamp_runtime):
    coordinator, controller, lamp, _ = lamp_runtime
    assert lamp.is_on is None and lamp.assumed_state
    assert hass.states.get(lamp.entity_id).state == STATE_UNKNOWN
    assert controller.session.intensity == 55
    assert coordinator.controller_state["svane_light_intent"] is False
    assert "under_bed_lights_on" not in coordinator.controller_state
    controller.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("lamp_runtime", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("command", ["on", "off", "intensity"])
@pytest.mark.parametrize("failure", [None, "ble", "cancel"])
async def test_registered_switch_receives_explicit_attempted_intent(hass, lamp_runtime, command, failure):
    coordinator, controller, lamp, _ = lamp_runtime
    client = controller.client
    attempted = asyncio.Event()

    async def cancel_during_write(*args, **kwargs):
        attempted.set()
        await asyncio.Event().wait()

    if failure == "ble":
        client.write_gatt_char.side_effect = BleakError("lamp delivery failed")
    elif failure == "cancel":
        client.write_gatt_char.side_effect = cancel_during_write

    async def execute(ctrl):
        if command == "on":
            await ctrl.lights_on()
        elif command == "off":
            await ctrl.lights_off()
        else:
            await ctrl.set_light_level(95)

    if failure is None:
        await coordinator.async_execute_controller_command(execute)
    elif failure == "ble":
        with pytest.raises(BleakError):
            await coordinator.async_execute_controller_command(execute)
    else:
        task = asyncio.create_task(coordinator.async_execute_controller_command(execute))
        try:
            async with asyncio.timeout(1):
                await attempted.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    await hass.async_block_till_done()
    expected = command != "off"
    assert controller.session.light_intent_known
    assert lamp.is_on is expected and lamp.assumed_state
    assert hass.states.get(lamp.entity_id).state == (STATE_ON if expected else STATE_OFF)
    assert coordinator.controller_state["under_bed_lights_on"] is expected
    assert controller.session.preferences().keys() == {"intensity", "slots"}
    assert bytes(client.write_gatt_char.call_args.args[1]).hex() == (
        "130200000000" if command == "off" else "13025f010064" if command == "intensity" else "130237010064"
    )


@pytest.mark.parametrize("lamp_runtime", ["multi", "jmc"], indirect=True)
async def test_warm_reload_retains_intent_but_profile_or_cold_session_does_not(hass, lamp_runtime):
    coordinator, controller, lamp, component = lamp_runtime
    await lamp.async_turn_on()
    known_session = controller.session
    await component.async_remove_entity(lamp.entity_id)
    entry = MockConfigEntry(domain=DOMAIN, data=dict(coordinator.entry.data))
    entry.add_to_hass(hass)
    rebuilt = AdjustableBedCoordinator(hass, entry)
    variant = entry.data[CONF_PROTOCOL_VARIANT]
    warm = await create_controller(rebuilt, BED_TYPE_SVANE, variant, None)
    assert isinstance(warm, SvaneController) and warm.session is known_session
    rebuilt._controller = warm
    restored_lamp = next(e for e in _switch_entities_for(hass, rebuilt)
                         if e.entity_description.key == "under_bed_lights")
    restored_lamp.entity_id = "switch.svane_reloaded_lamp"
    await component.async_add_entities([restored_lamp])
    try:
        assert restored_lamp.is_on is True and restored_lamp.assumed_state
        assert hass.states.get(restored_lamp.entity_id).state == STATE_ON
        await component.async_remove_entity(restored_lamp.entity_id)
        other_variant = SVANE_VARIANT_MULTI if controller.profile == "jmc" else SVANE_VARIANT_JMC
        changed_entry = MockConfigEntry(domain=DOMAIN, data={
            **coordinator.entry.data, CONF_PROTOCOL_VARIANT: other_variant,
        })
        changed_entry.add_to_hass(hass)
        changed_runtime = AdjustableBedCoordinator(hass, changed_entry)
        changed = await create_controller(changed_runtime, BED_TYPE_SVANE, other_variant, None)
        assert isinstance(changed, SvaneController)
        assert changed.session is not known_session and not changed.session.light_intent_known
        changed_runtime._controller = changed
        changed_lamp = next(e for e in _switch_entities_for(hass, changed_runtime)
                            if e.entity_description.key == "under_bed_lights")
        changed_lamp.entity_id = "switch.svane_changed_profile"
        await component.async_add_entities([changed_lamp])
        try:
            assert changed_lamp.is_on is None
            assert hass.states.get(changed_lamp.entity_id).state == STATE_UNKNOWN
        finally:
            await component.async_remove_entity(changed_lamp.entity_id)
            changed_runtime._cancel_disconnect_timer()
            await changed_runtime._command_scheduler.async_shutdown()
        # A new process has no process-local session. Only persisted preferences remain.
        await restart_app_state(hass, coordinator.address)
        cold_entry = MockConfigEntry(domain=DOMAIN, data=dict(coordinator.entry.data))
        cold_entry.add_to_hass(hass)
        cold = AdjustableBedCoordinator(hass, cold_entry)
        fresh = await create_controller(cold, BED_TYPE_SVANE, variant, None)
        assert isinstance(fresh, SvaneController)
        await cold._async_restore_app_state(fresh)
        assert not fresh.session.light_intent_known
        assert "under_bed_lights_on" not in cold.controller_state
        assert fresh.session.intensity == known_session.intensity
        await cold._command_scheduler.async_shutdown()
    finally:
        await component.async_remove_entity(restored_lamp.entity_id)
        rebuilt._cancel_disconnect_timer()
        await rebuilt._command_scheduler.async_shutdown()


@pytest.mark.parametrize("lamp_runtime", ["multi", "jmc"], indirect=True)
async def test_memory_and_metadata_do_not_establish_lamp_intent(hass, lamp_runtime):
    coordinator, controller, lamp, _ = lamp_runtime
    await coordinator.async_execute_controller_command(lambda ctrl: ctrl.program_memory(1))
    controller._remember()
    await controller.hold_control("light_adjust", 300)
    await hass.async_block_till_done()
    assert controller.session.preferences()["intensity"] == 55
    assert not controller.session.light_intent_known
    assert lamp.is_on is None and hass.states.get(lamp.entity_id).state == STATE_UNKNOWN
    assert "under_bed_lights_on" not in coordinator.controller_state
