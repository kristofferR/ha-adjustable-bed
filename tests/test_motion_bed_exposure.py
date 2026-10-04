"""Motion Bed explicit setup and late hub controls use stable HA identities."""
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.button import (
    ControllerActionButton,
    _async_follow_motion_bed_module_actions,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_MOTION_BED_MOVEMENT,
    CONF_MOTION_BED_PRESET,
    CONF_MOTION_BED_RESTORED,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed


@pytest.mark.parametrize("input_data,valid", [
    ({CONF_BLE_DEVICE_NAME: "QMS-IQ"}, True),
    ({CONF_BLE_DEVICE_NAME: "qms-iq"}, False),
    ({CONF_BLE_DEVICE_NAME: "unknown"}, False),
    ({CONF_BLE_DEVICE_NAME: "unknown", CONF_MOTION_BED_RESTORED: True}, True),
    ({CONF_BLE_DEVICE_NAME: "TL-Q", CONF_MOTION_BED_PRESET: "K1"}, False),
    ({CONF_BLE_DEVICE_NAME: "QMS-IQ", CONF_MOTION_BED_MOVEMENT: "modular"}, False),
    ({CONF_BLE_DEVICE_NAME: "QMS-IQ", CONF_MOTION_BED_PRESET: "auto", CONF_MOTION_BED_MOVEMENT: "auto"}, True),
])
async def test_explicit_app_step_checks_identity_and_retained_layout_before_connection(hass, input_data, valid):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bed", CONF_BED_TYPE: BED_TYPE_MOTION_BED}
    flow._finish_with_verify = AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY})
    result = await flow.async_step_motion_bed(input_data)
    if valid:
        flow._finish_with_verify.assert_awaited_once()
        data = flow._finish_with_verify.call_args.args[0]
        assert data[CONF_BLE_DEVICE_NAME] == input_data[CONF_BLE_DEVICE_NAME]
        assert data.get(CONF_MOTION_BED_PRESET) != "auto"
        assert data.get(CONF_MOTION_BED_MOVEMENT) != "auto"
    else:
        flow._finish_with_verify.assert_not_awaited()
        assert result["errors"] == {"base": "motion_bed_profile"}


async def test_new_hub_modules_add_buttons_once_disable_removed_modules_and_unsubscribe(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_BLE_DEVICE_NAME: "TL-Q"})
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    controller = MotionBedController(coord, selection=select_motion_bed("TL-Q"))
    coord._controller = controller
    additions = []
    initial = [ControllerActionButton(coord, spec) for spec in controller.controller_button_specs]
    _async_follow_motion_bed_module_actions(hass, entry, coord, additions.extend, initial)
    callbacks = tuple(coord._controller_state_callbacks)
    assert len(callbacks) == 1
    controller._state = replace(controller._state, air_module_present=True)
    controller._publish()
    assert additions
    assert len({entity.unique_id for entity in initial + additions}) == len(initial + additions)
    air_buttons = [entity for entity in additions if "_motion_bed_air_" in entity.unique_id]
    assert air_buttons and all(entity.available for entity in air_buttons)
    before = len(additions)
    controller._publish()
    assert len(additions) == before
    controller._state = replace(controller._state, air_module_present=False)
    controller._publish()
    assert all(not entity.available for entity in air_buttons)
    await entry._async_process_on_unload(hass)
    assert not coord._controller_state_callbacks


async def test_hub_surface_select_requires_present_module_and_changes_only_thermal_poll_focus(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_BLE_DEVICE_NAME: "TL-Q"})
    coord = AdjustableBedCoordinator(hass, entry)
    controller = MotionBedController(coord, selection=select_motion_bed("TL-Q"))
    controller._spawn = MagicMock()
    spec, = controller.controller_select_specs
    assert spec.options == ("motor", "air", "thermal")
    with pytest.raises(ValueError, match="not reported"):
        await spec.select_fn(controller, "thermal")
    controller._state = replace(controller._state, motor_module_present=True, thermal_module_present=True)
    controller._active_module = "motor"
    await spec.select_fn(controller, "thermal")
    assert controller.protocol_diagnostics["active_module"] == "thermal"
    assert controller._module_is_active("thermal")
    assert not controller._module_is_active("motor")
