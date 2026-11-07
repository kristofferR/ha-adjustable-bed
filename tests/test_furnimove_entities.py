"""Layout replacement keeps matching identities and removes retired controls."""

import pytest

from custom_components.adjustable_bed.beds.okin_rf_eco_bt import OkinRfEcoBtController
from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_RF_ECO_BT,
    CONF_HAS_MASSAGE,
)
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from tests.test_furnimove import generic, make_controller
from tests.test_malouf_app_entities import configure_entity_runtime


async def test_initial_off_feedback_changes_reported_sensors_from_unknown_to_off(hass):
    controller = make_controller()
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    runtime.controller_state = controller._coordinator.controller_state
    sensors = [
        sensor for sensor in _binary_sensor_entities_for(hass, runtime)
        if sensor.unique_id in {
            "bed_furnimove_ubl_left", "bed_furnimove_sync_left", "bed_furnimove_child_lock_left",
        }
    ]
    assert len(sensors) == 3
    assert all(sensor.is_on is None for sensor in sensors)
    controller._parse_feedback(generic(0))
    assert all(sensor.is_on is False for sensor in sensors)


@pytest.mark.parametrize(
    ("handset", "wave"),
    [("90167", False), ("91983", False), ("93558", False), ("12234", True)],
)
async def test_wave_intensity_number_follows_massager3_row(hass, handset, wave):
    controller = make_controller(handset)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    hass.config_entries.async_update_entry(
        runtime.entry, data={**runtime.entry.data, CONF_HAS_MASSAGE: True}
    )
    numbers = _number_entities_for(hass, runtime)
    assert any(entity.unique_id == "bed_massage_wave_intensity_left" for entity in numbers) is wave


@pytest.mark.parametrize(("handset", "massage"), [("00000", False), ("12234", True)])
async def test_local_massage_sensors_follow_selected_handset(hass, handset, massage):
    controller = make_controller(handset)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    sensors = _sensor_entities_for(hass, runtime) + _binary_sensor_entities_for(hass, runtime)
    massage_entities = {
        entity.unique_id for entity in sensors if "furnimove_massage_" in entity.unique_id
    }
    assert len(massage_entities) == (5 if massage else 0)


async def test_replacing_stair_cover_keeps_matching_bed_motor_ids(hass):
    controller = make_controller("00000")
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    covers = _cover_entities_for(hass, runtime)
    assert {entity.unique_id for entity in covers} == {"bed_back_left", "bed_legs_left"}


async def test_shorter_profile_builds_only_its_actions(hass):
    controller = make_controller("00000")
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_FURNIMOVE)
    buttons = {entity.unique_id for entity in _button_entities_for(hass, runtime)}
    assert "bed_furnimove_action_4_left" in buttons
    assert "bed_furnimove_action_50_left" not in buttons


async def test_confirming_staircase_drops_furnimove_state(hass):
    previous = make_controller()
    controller = OkinRfEcoBtController(previous._coordinator)
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_OKIN_RF_ECO_BT)
    built = {
        entity.unique_id
        for entity in (*_sensor_entities_for(hass, runtime), *_binary_sensor_entities_for(hass, runtime))
    }
    assert not {"bed_furnimove_model_left", "bed_furnimove_sync_left"} & built
