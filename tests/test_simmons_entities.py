"""SIMMONS entities follow the stored bed layout and retire on profile change."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import BED_TYPE_DIAGNOSTIC, BED_TYPE_SIMMONS, DOMAIN
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from tests.conftest import make_controller_mock
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_simmons import make_controller

REGULAR = {"preset_zero_g", "preset_tv", "preset_anti_snore"}
INCLINED = {"simmons_inclined_left", "simmons_inclined_middle", "simmons_inclined_right"}


@pytest.mark.parametrize(("variant", "present", "absent"), [(None, REGULAR, INCLINED), ("simmons_inclined", INCLINED, REGULAR)])
async def test_buttons_follow_the_bed_layout(hass, variant, present, absent):
    runtime = configure_entity_runtime(hass, make_controller(variant), BED_TYPE_SIMMONS)
    runtime.has_massage = False
    keys = {entity.unique_id.removeprefix("bed_").removesuffix("_left") for entity in _button_entities_for(hass, runtime)}
    assert present <= keys and not absent & keys
    assert {
        "preset_flat",
        "preset_memory_1",
        "program_memory_1",
        "toggle_light",
        "simmons_sync_clock",
        "simmons_refresh_alarms",
    } <= keys
    assert not {key for key in keys if key.startswith("massage")}
    app_buttons = {
        entity.unique_id: entity.translation_key
        for entity in _button_entities_for(hass, runtime)
        if "simmons_" in entity.unique_id
    }
    # Stable translation keys let the card bucket them (presets / utility).
    assert all(f"bed_{key}_left" == unique for unique, key in app_buttons.items())


@pytest.mark.parametrize("retain", [True, False])
async def test_alarm_sensors_and_app_buttons_retire_with_the_profile(hass, retain):
    controller = (
        make_controller("simmons_inclined")
        if retain
        else make_controller_mock(
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            controller_button_specs=(),
            position_number_specs=(),
        )
    )
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_SIMMONS if retain else BED_TYPE_DIAGNOSTIC)
    registry = er.async_get(hass)
    old = [
        registry.async_get_or_create(domain, DOMAIN, f"bed_{key}_left", config_entry=runtime.entry)
        for domain, key in (
            ("sensor", "simmons_alarm_1"),
            ("sensor", "simmons_alarm_2"),
            ("button", "simmons_inclined_left"),
        )
    ]
    sensors = _sensor_entities_for(hass, runtime)
    _button_entities_for(hass, runtime)
    assert all((registry.async_get(row.entity_id) is not None) is retain for row in old)
    assert {entity.unique_id for entity in sensors if "simmons_" in entity.unique_id} == (
        {"bed_simmons_alarm_1_left", "bed_simmons_alarm_2_left"} if retain else set()
    )
