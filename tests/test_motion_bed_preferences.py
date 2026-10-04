"""Per-target app audio preferences remain distinct from live feedback."""
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.const import (
    BED_TYPE_MOTION_BED,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_MOTION_BED_PRESET,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from tests.app_state_helpers import restart_app_state, stored_app_state


def coordinator(hass, *, address="AA:BB:CC:DD:EE:FF", preset=None):
    data = {CONF_ADDRESS: address, CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_BLE_DEVICE_NAME: "QMS-IQ"}
    if preset:
        data[CONF_MOTION_BED_PRESET] = preset
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    result = AdjustableBedCoordinator(hass, entry)
    result._controller = MotionBedController(
        result, selection=select_motion_bed("QMS-IQ", preset_override=preset)
    )
    return result


async def test_reported_audio_preference_survives_reconnect_and_restart_without_live_claim(hass):
    ctrl = coordinator(hass)
    await ctrl._async_restore_app_state(ctrl.controller)
    controller = ctrl.controller
    key = controller.persisted_app_state_key
    controller._state = replace(controller._state, audio_available=True)
    controller._handle_notification(b"unrelated")
    assert await stored_app_state(ctrl, key) == {"audio_available": True}
    await restart_app_state(hass, ctrl.address)
    for target in (ctrl, coordinator(hass)):
        target._controller = MotionBedController(target, selection=select_motion_bed("QMS-IQ"))
        await target._async_restore_app_state(target.controller)
        assert target.controller._state.audio_available is None
        assert target.controller.protocol_diagnostics["remembered_audio_available"] is True
        target.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")
        target.controller._state = replace(target.controller._state, audio_available=False)
        target.controller._handle_notification(b"unrelated")
        with pytest.raises(ValueError, match="audio support"):
            target.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")
        assert await stored_app_state(target, key) == {"audio_available": False}


@pytest.mark.parametrize("change", [{"address": "AA:BB:CC:DD:EE:00"}, {"preset": "K2M"}])
async def test_audio_preference_isolated_by_physical_target_and_explicit_profile(hass, change):
    original = coordinator(hass)
    await original._async_restore_app_state(original.controller)
    original.controller._state = replace(original.controller._state, audio_available=True)
    original.controller._handle_notification(b"unrelated")
    other = coordinator(hass, **change)
    await other._async_restore_app_state(other.controller)
    assert other.controller.persisted_app_state == {"audio_available": False}
    with pytest.raises(ValueError, match="audio support"):
        other.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")


@pytest.mark.parametrize("stored", [{"audio_available": 1}, {"audio_available": "true"}, {"unexpected": True}, []])
async def test_invalid_preference_does_not_block_controller_startup(hass, stored):
    ctrl = coordinator(hass)
    key = ctrl.controller.persisted_app_state_key
    ctrl._app_state_store._store.async_load = AsyncMock(
        return_value={f"{BED_TYPE_MOTION_BED}:auto:{key}": stored}
    )
    await ctrl._async_restore_app_state(ctrl.controller)
    assert ctrl.controller.persisted_app_state == {"audio_available": False}
    assert ctrl.controller._state.audio_available is None
