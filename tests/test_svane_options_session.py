"""Effective-profile options preserve aliases and reset only changed targets."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SVANE_VARIANT_JENSEN_LINON,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.svane_state import get_svane_session
from tests.app_state_helpers import stored_app_state, write_app_state
from tests.test_svane import make_controller, written


async def apply_options(hass, entry, changes):
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form(dict(changes), step_id="settings")
    if result["type"] == "form" and not result.get("errors"):
        result = await flow._async_options_form(dict(changes), step_id="settings")
    assert result["type"] == "create_entry", result


async def controller_for_entry(hass, entry):
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = make_controller().client
    controller = await create_controller(
        coordinator, BED_TYPE_SVANE, entry.data.get(CONF_PROTOCOL_VARIANT), None
    )
    assert isinstance(controller, SvaneController)
    coordinator._controller = controller
    await coordinator._async_restore_app_state(controller)
    controller._wait = AsyncMock(return_value=True)
    return controller


@pytest.mark.parametrize("old,new", [
    (None, SVANE_VARIANT_MULTI),
    (VARIANT_AUTO, SVANE_VARIANT_MULTI),
    (SVANE_VARIANT_MULTI, VARIANT_AUTO),
])
async def test_effective_p1_alias_options_preserve_saved_slots_and_recall(hass, old, new):
    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE}
    if old is not None:
        data[CONF_PROTOCOL_VARIANT] = old
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    controller = await controller_for_entry(hass, entry)
    for slot in (1, 2):
        await controller.program_memory(slot)
    session = controller.session
    session.light_on = True
    peer = get_svane_session(hass, "AA:BB:CC:DD:EE:02", "jmc")
    peer.intensity = 95
    saved = dict(session.multi_slots)

    await apply_options(hass, entry, {CONF_PROTOCOL_VARIANT: new})
    rebuilt = await controller_for_entry(hass, entry)
    assert rebuilt.profile == "multi" and rebuilt.session is session
    assert rebuilt.session.multi_slots == saved and rebuilt.session.light_on
    assert get_svane_session(hass, "AA:BB:CC:DD:EE:02", "jmc") is peer
    assert peer.intensity == 95
    for slot in (1, 2):
        rebuilt.validate_memory_recall(slot)
        await rebuilt.preset_memory(slot)
    assert [packet for _, _, packet in written(rebuilt)] == [
        raw.hex() for slot in (1, 2) for raw in saved[slot]
    ]


@pytest.mark.parametrize("old,new", [
    (SVANE_VARIANT_JMC, SVANE_VARIANT_MULTI),
    (SVANE_VARIANT_JMC, SVANE_VARIANT_JENSEN_LINON),
    (SVANE_VARIANT_MULTI, SVANE_VARIANT_JMC),
])
async def test_profile_change_keeps_each_profiles_preferences(hass, old, new):
    preferences = {"intensity": 95, "slots": ["00112233", "44556677"]}
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: old,
    })
    entry.add_to_hass(hass)
    old_profile = "jmc" if old == SVANE_VARIANT_JMC else "multi"
    await write_app_state(AdjustableBedCoordinator(hass, entry), preferences, old_profile)
    original = await controller_for_entry(hass, entry)
    assert original.session.preferences() == preferences
    peer = get_svane_session(hass, "AA:BB:CC:DD:EE:02", "jmc")
    peer.restore(preferences)

    await apply_options(hass, entry, {CONF_PROTOCOL_VARIANT: new})
    # The old profile keeps its slot, so changing back restores it.
    assert await stored_app_state(original._coordinator, old_profile) == preferences
    await apply_options(hass, entry, {CONF_PROTOCOL_VARIANT: old})
    rebuilt = await controller_for_entry(hass, entry)
    assert rebuilt.session.preferences() == preferences
    assert get_svane_session(hass, "AA:BB:CC:DD:EE:02", "jmc") is peer
    assert peer.preferences() == preferences


async def test_ordinary_jmc_options_retain_preferences_and_same_session(hass):
    preferences = {"intensity": 95, "slots": ["00112233", "44556677"]}
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC,
    })
    entry.add_to_hass(hass)
    await write_app_state(AdjustableBedCoordinator(hass, entry), preferences, "jmc")
    original = await controller_for_entry(hass, entry)
    await apply_options(hass, entry, {CONF_IDLE_DISCONNECT_SECONDS: 60})
    rebuilt = await controller_for_entry(hass, entry)
    assert rebuilt.session is original.session
    assert await stored_app_state(rebuilt._coordinator, "jmc") == preferences
    await rebuilt.preset_memory(2)
    assert [packet for _, _, packet in written(rebuilt)] == ["100444556677"]
