"""Motion hub identities and explicit shared-name onboarding boundaries."""
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.beds.solace import SolaceController
from custom_components.adjustable_bed.button import ControllerActionButton, async_setup_entry
from custom_components.adjustable_bed.config_flow import (
    BED_TYPE_AUTO_DETECT,
    AdjustableBedConfigFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_MOTION_BED_NAME,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from tests.test_detection import _make_service_info
from tests.test_motion_bed_lifecycle import real_coordinator


async def test_hub_reload_keeps_registry_customization_through_inventory_changes(hass):
    coord = await real_coordinator(hass, "TL-Q")
    controller = coord.controller
    assert isinstance(controller, MotionBedController)
    controller._state = replace(controller._state, air_module_present=True)
    spec = next(s for s in controller.controller_button_specs if "qinang_fragment" in s.key)
    controller._state = replace(controller._state, air_module_present=None)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "button", DOMAIN, coord.entity_unique_id(spec.key), config_entry=coord.entry
    )
    customized = registry.async_update_entity(
        existing.entity_id, name="My air stop", disabled_by=er.RegistryEntryDisabler.USER
    )
    hass.data[DOMAIN] = {coord.entry.entry_id: coord}
    added = []
    controller._spawn = MagicMock()
    await controller.start_notify()
    await async_setup_entry(hass, coord.entry, added.extend)
    assert registry.async_get(existing.entity_id) == customized
    receive = coord.client.start_notify.call_args.args[1]
    frame = bytearray.fromhex("FFFFFFFF010027140000000000000000")
    frame[12] = 11
    receive(coord.client.start_notify.call_args.args[0], frame)
    action = next(e for e in added if isinstance(e, ControllerActionButton) and e.unique_id == existing.unique_id)
    assert action.available
    assert registry.async_get(existing.entity_id) == customized
    receive(coord.client.start_notify.call_args.args[0], bytearray.fromhex("FFFFFFFF010027140000000000000000"))
    assert not action.available
    assert registry.async_get(existing.entity_id) == customized
    writes = coord.client.write_gatt_char.await_count
    with pytest.raises(ValueError, match="unavailable"):
        await action.async_press()
    assert coord.client.write_gatt_char.await_count == writes
    # A genuine profile change still removes stale hub-only identities.
    coord._controller = MotionBedController(coord, selection=select_motion_bed("QMS-IQ"))
    await async_setup_entry(hass, coord.entry, lambda entities: None)
    assert registry.async_get(existing.entity_id) is None
    await coord.entry._async_process_on_unload(hass)
    coord._cancel_disconnect_timer()
    await controller.stop_notify()


@pytest.mark.parametrize("name", ["QMS-IQ", "QMS4", "QMS3", "QMS-MQ", "SealyMF", "S4-Y-192-461000AD"])
async def test_shared_name_discovery_requires_choice_before_any_default_next(hass, name):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = _make_service_info(name=name)
    result = await flow.async_step_bluetooth_confirm()
    assert result["step_id"] == "bluetooth_disambiguate"
    assert flow._disambiguation_types == [BED_TYPE_SOLACE, BED_TYPE_MOTION_BED]
    # The focused chooser has no implicit app selection.
    schema = result["data_schema"]
    assert isinstance(schema, vol.Schema)
    with pytest.raises(vol.MultipleInvalid):
        schema({})
    assert (await flow.async_step_bluetooth_disambiguate({}))["step_id"] == "bluetooth_disambiguate"


@pytest.mark.parametrize("name", ["QMS-IQ", "SealyMF"])
async def test_manual_default_auto_detect_cannot_submit_a_shared_app_name(hass, name):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = _make_service_info(name=name)
    result = await flow.async_step_manual_config()
    marker = next(k for k in result["data_schema"].schema if k.schema == CONF_BED_TYPE)
    assert marker.default() == BED_TYPE_AUTO_DETECT
    result = await flow.async_step_manual_config({CONF_BED_TYPE: BED_TYPE_AUTO_DETECT})
    assert result["errors"] == {"base": "auto_detect_failed"}


@pytest.mark.parametrize("app", [BED_TYPE_MOTION_BED, BED_TYPE_SOLACE])
async def test_explicit_discovered_app_choice_reaches_its_real_factory(enable_custom_integrations, hass, app):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = _make_service_info(name="QMS-IQ")
    flow._finish_with_verify = AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY})
    assert (await flow.async_step_bluetooth_confirm())["step_id"] == "bluetooth_disambiguate"
    assert (await flow.async_step_bluetooth_disambiguate({"bed_type_choice": app}))["step_id"] == "bluetooth_confirm"
    result = await flow.async_step_bluetooth_confirm({CONF_BED_TYPE: app, CONF_NAME: "QMS-IQ", CONF_DISCONNECT_AFTER_COMMAND: False})
    if app == BED_TYPE_MOTION_BED:
        assert result["step_id"] == "motion_bed"
        await flow.async_step_motion_bed({CONF_MOTION_BED_NAME: "QMS-IQ"})
    else:
        assert result["type"] == FlowResultType.CREATE_ENTRY
    flow._finish_with_verify.assert_awaited_once()
    data = flow._finish_with_verify.call_args.args[0]
    assert data[CONF_BED_TYPE] == app
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coord, app, "auto", None, device_name="QMS-IQ")
    assert isinstance(controller, MotionBedController if app == BED_TYPE_MOTION_BED else SolaceController)


@pytest.mark.parametrize("name", ["qms-iq", "my qms2 bed", "s4-y-192-461000ad"])
def test_legacy_only_case_sensitive_names_keep_the_existing_route(name):
    result = detect_bed_type_detailed(_make_service_info(name=name))
    assert result.bed_type == BED_TYPE_SOLACE
    assert result.confidence == 0.9
    assert not result.ambiguous_types
