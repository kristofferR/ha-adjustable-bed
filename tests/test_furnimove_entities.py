"""Layout replacement keeps matching identities and removes retired controls."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.beds.okin_rf_eco_bt import OkinRfEcoBtController
from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_RF_ECO_BT,
    DOMAIN,
)
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from tests.test_furnimove import make_controller
from tests.test_malouf_app_entities import configure_entity_runtime


@pytest.mark.parametrize(("handset", "massage"), [("00000", False), ("12234", True)])
async def test_local_massage_sensors_follow_selected_handset(hass, handset, massage):
    controller = make_controller(handset)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    sensors = _sensor_entities_for(hass, runtime) + _binary_sensor_entities_for(hass, runtime)
    massage_entities = {
        entity.unique_id for entity in sensors if "furnimove_massage_" in entity.unique_id
    }
    assert len(massage_entities) == (5 if massage else 0)


async def test_replacing_stair_cover_preserves_matching_bed_motor_ids(hass):
    controller = make_controller("00000")
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    registry = er.async_get(hass)
    stair = registry.async_get_or_create("cover", DOMAIN, "bed_stair_left", config_entry=runtime.entry)
    back = registry.async_get_or_create("cover", DOMAIN, "bed_back_left", config_entry=runtime.entry)
    legs = registry.async_get_or_create("cover", DOMAIN, "bed_legs_left", config_entry=runtime.entry)
    other = registry.async_get_or_create("cover", DOMAIN, "bed_stair_right", config_entry=runtime.entry)
    covers = _cover_entities_for(hass, runtime)
    assert {entity.unique_id for entity in covers} == {back.unique_id, legs.unique_id}
    assert registry.async_get(stair.entity_id) is None
    assert registry.async_get(back.entity_id) is back and registry.async_get(legs.entity_id) is legs
    assert registry.async_get(other.entity_id) is other


async def test_shorter_profile_removes_only_retired_actions_of_current_side(hass):
    controller = make_controller("00000")
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    registry = er.async_get(hass)
    retained = registry.async_get_or_create("button", DOMAIN, "bed_furnimove_action_4_left", config_entry=runtime.entry)
    retired = registry.async_get_or_create("button", DOMAIN, "bed_furnimove_action_50_left", config_entry=runtime.entry)
    other = registry.async_get_or_create("button", DOMAIN, "bed_furnimove_action_50_right", config_entry=runtime.entry)
    buttons = _button_entities_for(hass, runtime)
    assert any(entity.unique_id == retained.unique_id for entity in buttons)
    assert registry.async_get(retained.entity_id) is retained
    assert registry.async_get(retired.entity_id) is None
    assert registry.async_get(other.entity_id) is other


async def test_confirming_staircase_retires_furnimove_state_of_only_selected_side(hass):
    previous = make_controller()
    controller = OkinRfEcoBtController(previous._coordinator)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_OKIN_RF_ECO_BT)
    registry = er.async_get(hass)
    sensors = []
    for domain, key in (("sensor", "furnimove_model"), ("binary_sensor", "furnimove_sync")):
        sensors.append(registry.async_get_or_create(domain, DOMAIN, f"bed_{key}_left", config_entry=runtime.entry))
        registry.async_get_or_create(domain, DOMAIN, f"bed_{key}_right", config_entry=runtime.entry)
    _sensor_entities_for(hass, runtime)
    _binary_sensor_entities_for(hass, runtime)
    for row in sensors:
        assert registry.async_get(row.entity_id) is None
        assert registry.async_get_entity_id(row.domain, DOMAIN, row.unique_id.replace("_left", "_right"))
