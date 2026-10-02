"""Possible hub registry identities and profile changes."""

from dataclasses import replace

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.button import ControllerActionButton, async_setup_entry
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_MOTION_BED_NAME,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.motion_bed_actions import ACTION_BY_KEY
from tests.test_motion_bed_lifecycle import real_coordinator


async def test_public_home_to_hub_prunes_home_only_registry_control(hass):
    coord = await real_coordinator(hass, "QMS-IQ")
    hass.data[DOMAIN] = {coord.entry.entry_id: coord}
    registry = er.async_get(hass)
    home = []
    await async_setup_entry(hass, coord.entry, home.extend)
    hass.config_entries.async_update_entry(
        coord.entry, data={**coord.entry.data, CONF_MOTION_BED_NAME: "TL-Q"}
    )
    hub = await create_controller(coord, BED_TYPE_MOTION_BED, None, coord.client)
    hub_keys = {spec.key for spec in hub.controller_button_specs}
    home_entity = next(
        e
        for e in home
        if isinstance(e, ControllerActionButton)
        and ACTION_BY_KEY[e._spec.key.removeprefix("motion_bed_")].owner.startswith("Kuaijie")
    )
    assert home_entity._spec.key not in hub_keys
    hub._state = replace(
        hub._state, motor_module_present=True, air_module_present=True, thermal_module_present=True
    )
    assert home_entity._spec.key not in {s.key for s in hub.controller_button_specs}
    hub._state = replace(
        hub._state, motor_module_present=None, air_module_present=None, thermal_module_present=None
    )
    old = registry.async_get_or_create(
        "button",
        DOMAIN,
        home_entity.unique_id,
        config_entry=coord.entry,
        translation_key=home_entity.translation_key,
    )
    coord._controller = hub
    new = []
    try:
        await async_setup_entry(hass, coord.entry, new.extend)
        assert home_entity.translation_key == "remote_action"
        assert old.unique_id not in {e.unique_id for e in new}
        assert registry.async_get(old.entity_id) is None, (
            "Dead home-only control survives actual public hub platform reload"
        )
        coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await coord.entry._async_process_on_unload(hass)
        coord._cancel_disconnect_timer()


async def test_unknown_hub_inventory_preserves_customized_module_and_foreign_controls(hass):
    coord = await real_coordinator(hass, "TL-Q")
    ctrl = coord.controller
    ctrl._state = replace(ctrl._state, air_module_present=True)
    spec = next(s for s in ctrl.controller_button_specs if "qinang_fragment" in s.key)
    ctrl._state = replace(ctrl._state, motor_module_present=True)
    shared_spec = next(
        s
        for s in ctrl.controller_button_specs
        if s.key == "motion_bed_alarm_activity_audio_preview_1"
    )
    ctrl._state = replace(ctrl._state, air_module_present=None, motor_module_present=None)
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "button", DOMAIN, coord.entity_unique_id(spec.key), config_entry=coord.entry
    )
    customized = registry.async_update_entity(
        row.entity_id, name="My air module", disabled_by=er.RegistryEntryDisabler.USER
    )
    shared = registry.async_get_or_create(
        "button", DOMAIN, coord.entity_unique_id(shared_spec.key), config_entry=coord.entry
    )
    shared = registry.async_update_entity(
        shared.entity_id, name="My shared alarm action", disabled_by=er.RegistryEntryDisabler.USER
    )
    other = MockConfigEntry(domain=DOMAIN, data={})
    other.add_to_hass(hass)
    rows = [
        registry.async_get_or_create(
            "button", "other_platform", row.unique_id, config_entry=coord.entry
        ),
        registry.async_get_or_create("switch", DOMAIN, row.unique_id, config_entry=coord.entry),
        registry.async_get_or_create(
            "button", DOMAIN, "other_" + row.unique_id, config_entry=other
        ),
    ]
    hass.data[DOMAIN] = {coord.entry.entry_id: coord}
    try:
        await async_setup_entry(hass, coord.entry, lambda entities: None)
        assert ctrl.protocol_diagnostics["air_module_present"] is None
        assert registry.async_get(customized.entity_id) == customized
        assert registry.async_get(shared.entity_id) == shared
        for foreign in rows:
            assert registry.async_get(foreign.entity_id) == foreign
        coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await coord.entry._async_process_on_unload(hass)
        coord._cancel_disconnect_timer()


async def test_actual_paired_unknown_hub_keeps_both_customized_sides(hass):
    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.const import CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from tests.test_paired_setup import _paired_entry

    old = await real_coordinator(hass, "TL-Q")
    entry = _paired_entry(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, **old.entry.data, CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS}
    )
    coord = AdjustableBedCoordinator(hass, entry)
    coord._client = old.client
    coord._controller = await create_controller(coord, BED_TYPE_MOTION_BED, None, coord.client)
    ctrl = coord.controller
    ctrl._state = replace(ctrl._state, air_module_present=True)
    spec = next(s for s in ctrl.controller_button_specs if "qinang_fragment" in s.key)
    ctrl._state = replace(ctrl._state, air_module_present=None)
    pair = SingleAddressPairedCoordinator(hass, entry, coord)
    _async_ensure_paired_device_registry(hass, entry, pair)
    registry = er.async_get(hass)
    rows = []
    for side in ("left", "right"):
        row = registry.async_get_or_create(
            "button", DOMAIN, pair._children[side].entity_unique_id(spec.key), config_entry=entry
        )
        rows.append(
            registry.async_update_entity(
                row.entity_id,
                name="My " + side + " module",
                disabled_by=er.RegistryEntryDisabler.USER,
            )
        )
    hass.data[DOMAIN] = {entry.entry_id: pair}
    try:
        await async_setup_entry(hass, entry, lambda entities: None)
        assert ctrl.protocol_diagnostics["air_module_present"] is None
        for row in rows:
            assert registry.async_get(row.entity_id) == row
        coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await entry._async_process_on_unload(hass)
        coord._cancel_disconnect_timer()
        old._cancel_disconnect_timer()


@pytest.mark.parametrize("inventory_value", [None, False])
async def test_all_possible_hub_button_identities_survive_unreported_inventory(
    hass, inventory_value
):
    coord = await real_coordinator(hass, "TL-Q")
    ctrl = coord.controller
    ctrl._state = replace(
        ctrl._state, motor_module_present=True, air_module_present=True, thermal_module_present=True
    )
    specs = ctrl.controller_button_specs
    registry = er.async_get(hass)
    rows = [
        registry.async_get_or_create(
            "button", DOMAIN, coord.entity_unique_id(spec.key), config_entry=coord.entry
        )
        for spec in specs
    ]
    ctrl._state = replace(
        ctrl._state,
        motor_module_present=inventory_value,
        air_module_present=inventory_value,
        thermal_module_present=inventory_value,
    )
    hass.data[DOMAIN] = {coord.entry.entry_id: coord}
    try:
        await async_setup_entry(hass, coord.entry, lambda entities: None)
        assert rows and all(registry.async_get(row.entity_id) == row for row in rows)
        coord.client.write_gatt_char.assert_not_awaited()
    finally:
        await coord.entry._async_process_on_unload(hass)
        coord._cancel_disconnect_timer()
