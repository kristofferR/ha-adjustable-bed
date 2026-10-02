"""Physical hub STOP routing and profile registry retirement."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed.beds.motion_bed import STOP
from custom_components.adjustable_bed.const import BED_TYPE_MOTION_BED, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.motion_bed_protocol import SOURCE_COMMANDS
from custom_components.adjustable_bed.services import async_register_services
from tests.test_motion_bed_controller import characteristic, client_for
from tests.test_motion_bed_lifecycle import real_coordinator


async def cleanup(coord, *controllers):
    for ctrl in controllers:
        tasks = tuple(ctrl._tasks)
        await ctrl.stop_notify()
        await asyncio.gather(*tasks, return_exceptions=True)
    coord._cancel_disconnect_timer()
    await coord._command_scheduler.async_shutdown()


async def call(hass, coord, name, data=None):
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coord, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN, name, {"device_id": "bed", **(data or {})}, blocking=True
        )


async def drain(ctrl):
    for _ in range(10):
        await asyncio.sleep(0)
        tasks = tuple(ctrl._tasks)
        if tasks:
            await asyncio.gather(*tasks)


def inventory(ctrl, client):
    frame = bytearray.fromhex("FFFFFFFF010027140000000000000000")
    frame[9], frame[12] = 10, 11
    client.start_notify.call_args.args[1](client.start_notify.call_args.args[0], frame)




@pytest.mark.parametrize("stage", ["same_session", "pending_inventory", "fresh_inventory"])
async def test_registered_hub_stop_preserves_air_choice_across_factory(hass, stage, monkeypatch):
    coord = await real_coordinator(hass, "TL-Q")
    old = coord.controller
    await old.start_notify()
    await async_register_services(hass)
    inventory(old, coord.client)
    await drain(old)
    await call(
        hass, coord, "motion_bed_air_setting", {"mode": 3, "gear": 8, "timer": 2, "confirmed": True}
    )
    await drain(old)
    assert old.protocol_diagnostics["active_module"] == "air"
    ctrl = old
    history = {"before_disconnect": old.protocol_diagnostics["active_module"]}
    try:
        if stage != "same_session":
            coord.cache_capability_controller()
            oldclient = coord.client
            oldclient.is_connected = False
            coord._on_disconnect(oldclient)
            coord._client = client_for(characteristic(79))
            ctrl = await create_controller(coord, BED_TYPE_MOTION_BED, None, coord.client)
            coord._controller = ctrl
            await ctrl.start_notify()
            history["factory_active"] = ctrl.protocol_diagnostics["active_module"]
            history["inventory_pending"] = ctrl.protocol_diagnostics["air_module_present"] is None
            if stage == "fresh_inventory":
                inventory(ctrl, coord.client)
                await drain(ctrl)
        coord.client.write_gatt_char.reset_mock()
        await call(hass, coord, "stop_all")
        frames = [c.args[1] for c in coord.client.write_gatt_char.await_args_list]
        observed = {
            **history,
            "current_active": ctrl.protocol_diagnostics["active_module"],
            "stop_frames": [f.hex() for f in frames],
            "expected_air_stop": SOURCE_COMMANDS["QinangFragment:302"].hex(),
            "motor_stop": STOP.hex(),
            "physical_address": coord.address,
        }
        assert frames == [SOURCE_COMMANDS["QinangFragment:302"]], observed
    finally:
        await cleanup(coord, *({old, ctrl}))


@pytest.mark.parametrize("platform", ["sensor", "binary_sensor"])
@pytest.mark.parametrize("replacement", ["same_motion", "different_protocol"])
async def test_telemetry_retirement_preserves_active_customization_and_other_runtime(
    hass, platform, replacement
):
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.solace import SolaceController
    from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.sensor import _sensor_entities_for
    from tests.test_paired_setup import _paired_entry

    coord = await real_coordinator(hass, "TL-Q")
    ctrl = coord.controller
    pair = SingleAddressPairedCoordinator(hass, _paired_entry(hass), coord)
    left, right = pair._children["left"], pair._children["right"]
    registry = er.async_get(hass)
    spec = (
        ctrl.controller_state_sensor_specs[0]
        if platform == "sensor"
        else ctrl.controller_state_binary_sensor_specs[0]
    )
    key = spec.key
    active = registry.async_get_or_create(
        platform, DOMAIN, left.entity_unique_id(key), config_entry=coord.entry
    )
    active = registry.async_update_entity(
        active.entity_id, name="My telemetry", disabled_by=er.RegistryEntryDisabler.USER
    )
    opposite = registry.async_get_or_create(
        platform, DOMAIN, right.entity_unique_id(key), config_entry=coord.entry
    )
    retired = registry.async_get_or_create(
        platform, DOMAIN, left.entity_unique_id("motion_bed_retired_test"), config_entry=coord.entry
    )
    other_entry = MockConfigEntry(domain=DOMAIN, data={})
    other_entry.add_to_hass(hass)
    unrelated = registry.async_get_or_create(
        platform, DOMAIN, "other_" + active.unique_id, config_entry=other_entry
    )
    other_platform = registry.async_get_or_create(
        platform, "unrelated", active.unique_id, config_entry=coord.entry
    )
    other_domain = registry.async_get_or_create(
        "switch", DOMAIN, active.unique_id, config_entry=coord.entry
    )
    if replacement == "different_protocol":
        coord._controller = SolaceController(coord)
    build = _sensor_entities_for if platform == "sensor" else _binary_sensor_entities_for
    try:
        entities = build(hass, left)
        assert registry.async_get(retired.entity_id) is None
        if replacement == "same_motion":
            assert active.unique_id in {entity.unique_id for entity in entities}
            assert registry.async_get(active.entity_id) == active
            assert ctrl._state.motor_module_present is None
        else:
            assert registry.async_get(active.entity_id) is None
        for row in (opposite, unrelated, other_platform, other_domain):
            assert registry.async_get(row.entity_id) == row
        coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await cleanup(coord, ctrl)




@pytest.mark.parametrize("change", ["address", "profile", "absent", "unknown"])
async def test_hub_stop_rejects_unvalidated_route_without_any_fallback_write(hass, change):
    from dataclasses import replace

    from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
    from custom_components.adjustable_bed.motion_bed_models import select_motion_bed

    coord = await real_coordinator(hass, "TL-Q")
    old = coord.controller
    old._state = replace(old._state, air_module_present=True)
    await old.set_motion_bed_surface("air")
    await drain(old)
    ctrl = old
    try:
        if change == "address":
            coord._address = "AA:BB:CC:DD:EE:99"
        if change == "profile":
            selection = select_motion_bed("other TL-Q")
        else:
            selection = old.selection
        if change == "unknown":
            old._active_module = None
            old._remembered_module = None
        ctrl = MotionBedController(coord, selection=selection)
        coord._controller = ctrl
        ctrl._startup = AsyncMock()
        await ctrl.async_discover_capabilities()
        if change == "absent":
            ctrl._state = replace(ctrl._state, air_module_present=False)
        coord.client.write_gatt_char.reset_mock()
        with pytest.raises(ValueError):
            await ctrl.stop_all()
        coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await cleanup(coord, *({old, ctrl}))


@pytest.mark.parametrize("fresh_inventory", [False, True])
async def test_registered_thermal_stop_keeps_same_physical_choice_after_reconnect(
    hass, fresh_inventory
):
    from custom_components.adjustable_bed.motion_bed_protocol import build_thermal_gear

    coord = await real_coordinator(hass, "TL-Q")
    old = coord.controller
    old._module_startup = AsyncMock()
    await old.start_notify()
    await async_register_services(hass)

    def report(client):
        frame = bytearray.fromhex("FFFFFFFF01002714000000000000000C")
        frame[9] = 10
        client.start_notify.call_args.args[1](client.start_notify.call_args.args[0], frame)

    report(coord.client)
    await drain(old)
    await coord.async_execute_controller_command(lambda c: c.set_motion_bed_surface("thermal"))
    await drain(old)
    coord.cache_capability_controller()
    oldclient = coord.client
    oldclient.is_connected = False
    coord._on_disconnect(oldclient)
    coord._client = client_for(characteristic(79))
    ctrl = await create_controller(coord, BED_TYPE_MOTION_BED, None, coord.client)
    ctrl._module_startup = AsyncMock()
    coord._controller = ctrl
    try:
        await ctrl.start_notify()
        if fresh_inventory:
            report(coord.client)
            await drain(ctrl)
        coord.client.write_gatt_char.reset_mock()
        await call(hass, coord, "stop_all")
        assert [c.args[1] for c in coord.client.write_gatt_char.await_args_list] == [
            build_thermal_gear(4)
        ]
    finally:
        await cleanup(coord, old, ctrl)


@pytest.mark.parametrize("explicit_motor_choice", [False, True])
async def test_absent_selected_module_does_not_invent_a_default_motor_stop(
    hass, explicit_motor_choice
):
    from dataclasses import replace

    coord = await real_coordinator(hass, "TL-Q")
    ctrl = coord.controller
    ctrl._module_startup = AsyncMock()
    ctrl._state = replace(ctrl._state, air_module_present=True, motor_module_present=True)
    await ctrl.set_motion_bed_surface("air")
    await drain(ctrl)
    ctrl._state = replace(ctrl._state, air_module_present=False)
    await ctrl._start_present_modules()
    assert ctrl._active_module == "motor" and ctrl._remembered_module == "air"
    try:
        coord.client.write_gatt_char.reset_mock()
        if explicit_motor_choice:
            await ctrl.set_motion_bed_surface("motor")
            await ctrl.stop_all()
            assert [c.args[1] for c in coord.client.write_gatt_char.await_args_list] == [STOP]
        else:
            with pytest.raises(ValueError):
                await ctrl.stop_all()
            coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await cleanup(coord, ctrl)


