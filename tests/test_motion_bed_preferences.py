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
    CONF_MOTION_BED_NAME,
    CONF_MOTION_BED_PRESET,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed


def coordinator(hass, *, address="AA:BB:CC:DD:EE:FF", preset=None):
    data = {CONF_ADDRESS: address, CONF_BED_TYPE: BED_TYPE_MOTION_BED, CONF_MOTION_BED_NAME: "QMS-IQ"}
    if preset:
        data[CONF_MOTION_BED_PRESET] = preset
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    result = AdjustableBedCoordinator(hass, entry)
    result._controller = MotionBedController(result, selection=select_motion_bed("QMS-IQ"))
    return result


async def test_reported_audio_preference_survives_reconnect_and_restart_without_live_claim(hass):
    ctrl = coordinator(hass)
    await ctrl._async_restore_motion_bed_local_state()
    controller = ctrl.controller
    controller._state = replace(controller._state, audio_available=True)
    controller._handle_notification(b"unrelated")
    assert ctrl._motion_bed_local_state == {"audio_available": True}
    await ctrl._motion_bed_state_store.async_save(ctrl._motion_bed_local_state)
    for target in (ctrl, coordinator(hass)):
        target._controller = MotionBedController(target, selection=select_motion_bed("QMS-IQ"))
        await target._async_restore_motion_bed_local_state()
        assert target.controller._state.audio_available is None
        assert target.controller.protocol_diagnostics["remembered_audio_available"] is True
        target.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")
        target.controller._state = replace(target.controller._state, audio_available=False)
        target.controller._handle_notification(b"unrelated")
        with pytest.raises(ValueError, match="audio support"):
            target.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")
        assert target._motion_bed_local_state == {"audio_available": False}


@pytest.mark.parametrize("change", [{"address": "AA:BB:CC:DD:EE:00"}, {"preset": "K2M"}])
async def test_audio_preference_isolated_by_physical_target_and_explicit_profile(hass, change):
    original = coordinator(hass)
    await original._motion_bed_state_store.async_save({"audio_available": True})
    other = coordinator(hass, **change)
    await other._async_restore_motion_bed_local_state()
    assert other.controller.motion_bed_local_state == {"audio_available": False}
    with pytest.raises(ValueError, match="audio support"):
        other.controller.validate_motion_bed_action("alarm_activity_audio_preview_1")


@pytest.mark.parametrize("stored", [{"audio_available": 1}, {"audio_available": "true"}, {"unexpected": True}, []])
async def test_invalid_preference_does_not_block_controller_startup(hass, stored):
    ctrl = coordinator(hass)
    ctrl._motion_bed_state_store.async_load = AsyncMock(return_value=stored)
    await ctrl._async_restore_motion_bed_local_state()
    assert ctrl.controller.motion_bed_local_state == {"audio_available": False}
    assert ctrl.controller._state.audio_available is None
