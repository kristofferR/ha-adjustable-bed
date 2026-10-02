"""Actual public light intent and task-local timed movement boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.simmons import SimmonsController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_SIMMONS,
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.switch import _switch_entities_for
from tests.test_svane import make_controller, written


@pytest.fixture
async def runtime(hass, request):
    profile = request.param
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC if profile == "jmc" else SVANE_VARIANT_MULTI,
        CONF_DISCONNECT_AFTER_COMMAND: False,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller(profile)
    coordinator._client = controller.client
    coordinator._controller = controller
    controller._coordinator = coordinator
    await async_register_services(hass)
    try:
        yield coordinator, controller
    finally:
        coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
async def test_actual_action_number_and_switch_publish_commanded_lamp_intent(hass, runtime):
    coordinator, controller = runtime
    lamp = next(s for s in _switch_entities_for(hass, coordinator)
                if s.entity_description.key == "under_bed_lights")
    toggle = next(b for b in _button_entities_for(hass, coordinator)
                  if getattr(b, "_spec", None) and b._spec.key == "svane_light_toggle")
    intensity = next(n for n in _number_entities_for(hass, coordinator)
                     if getattr(n, "_spec", None) and n._spec.key == "svane_intensity")
    lamp.async_write_ha_state = MagicMock()
    unregister = coordinator.register_controller_state_callback(lamp._handle_controller_state_update)
    try:
        assert lamp.is_on is None and lamp.assumed_state
        await toggle.async_press()
        assert lamp.is_on is True and controller.session.light_on
        await toggle.async_press()
        assert lamp.is_on is False and not controller.session.light_on
        await intensity.async_set_native_value(95)
        assert intensity.native_value == 95
        assert lamp.is_on is True and controller.session.light_on
        await toggle.async_press()
        assert lamp.is_on is False and not controller.session.light_on
        assert [payload for _, _, payload in written(controller)] == [
            "13025a010064", "130200000000", "13025f010064", "130200000000",
        ]
    finally:
        unregister()


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("duration,motor", [(2000, "back"), (600, "legs")])
async def test_registered_timed_move_uses_active_plan_without_changing_wire_cadence(
    hass, runtime, monkeypatch, duration, motor
):
    coordinator, controller = runtime
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio)
    movement_times = []
    stop = bytes.fromhex("100000000000" if controller.profile == "jmc" else "0000")

    async def write(role, payload, **kwargs):
        if bytes(payload) != stop:
            movement_times.append(clock[0])

    async def advance(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)

    controller.client.write_gatt_char.side_effect = write
    controller._motor_wait = advance
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": "bed", "motor": motor, "direction": "up", "duration_ms": duration,
        }, blocking=True)
    assert clock[0] == pytest.approx(duration / 1000)
    assert movement_times[-1] > duration / 1000 - .201
    assert movement_times[0] == pytest.approx(0 if motor == "back" else .1)
    expected_gap = .1 if motor == "back" else .2
    assert all(b - a == pytest.approx(expected_gap) for a, b in zip(movement_times, movement_times[1:], strict=False))
    assert written(controller)[-1][2] == stop.hex()
    assert not controller._started and not controller.ble_lock.locked()
    assert not coordinator._command_lock.locked()


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
async def test_registered_timed_move_public_stop_cancels_long_plan_and_releases(runtime, hass):
    coordinator, controller = runtime
    moving = asyncio.Event()

    async def wait(seconds):
        moving.set()
        await coordinator.cancel_command.wait()

    controller._motor_wait = wait
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        task = asyncio.create_task(hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 2000,
        }, blocking=True))
        try:
            async with asyncio.timeout(1):
                await moving.wait()
                await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True)
                await asyncio.gather(task, return_exceptions=True)
            assert written(controller)[-1][2] == (
                "100000000000" if controller.profile == "jmc" else "0000"
            )
            assert not controller._started and not controller.ble_lock.locked()
            assert not coordinator._command_lock.locked()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("failure", ["ble", "cancel"])
async def test_failed_intensity_preserves_source_commanded_on_intent(runtime, failure):
    coordinator, controller = runtime
    controller.session.light_on = False
    error = BleakError("write failed") if failure == "ble" else asyncio.CancelledError()
    controller.client.write_gatt_char.side_effect = error
    with pytest.raises(type(error)):
        await controller.set_light_level(95)
    assert controller.session.light_on and controller.session.intensity == 95
    assert coordinator.controller_state["under_bed_lights_on"] is True
    assert coordinator.controller_state["svane_light_intent"] is True
    controller.client.write_gatt_char.side_effect = None
    await controller.lights_toggle()
    assert written(controller)[-1][2] == "130200000000"
    assert not controller.session.light_on


@pytest.mark.parametrize("runtime", ["multi", "jmc"], indirect=True)
async def test_actual_mixed_pair_rejects_late_svane_feet_minimum_before_any_write(hass, runtime):
    child, controller = runtime
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_NAME: "Simmons", CONF_BED_TYPE: BED_TYPE_SIMMONS,
        CONF_DISCONNECT_AFTER_COMMAND: False,
    })
    entry.add_to_hass(hass)
    first = AdjustableBedCoordinator(hass, entry)
    first._client = MagicMock(is_connected=True)
    first._client.write_gatt_char = AsyncMock()
    first._controller = SimmonsController(first, protocol_variant="simmons_okin")
    parent = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "mixed", CONF_NAME: "Pair"})
    parent.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, parent, {SIDE_LEFT: first, SIDE_RIGHT: child})
    try:
        with (
            patch("custom_components.adjustable_bed.services._resolve_sided_targets",
                  return_value=([(pair, SIDE_BOTH)], [])),
            pytest.raises(ServiceValidationError, match="longer than 100 ms"),
        ):
            await hass.services.async_call(DOMAIN, "timed_move", {
                "device_id": "pair", "motor": "legs", "direction": "up", "duration_ms": 100,
            }, blocking=True)
        first._client.write_gatt_char.assert_not_awaited()
        controller.client.write_gatt_char.assert_not_awaited()
        first._controller.validate_timed_movement("legs", "up", 100)
    finally:
        first._cancel_disconnect_timer()
