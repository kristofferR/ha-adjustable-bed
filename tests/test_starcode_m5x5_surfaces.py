"""Explicit app setup, public controls and registered four-address action."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _add_starcode_schema_fields,
    _starcode_errors,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_STARCODE_M5X5,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M5X5_PROFILE,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import async_register_services
from tests.test_starcode_accessory_group import group, target


def _entity_strings() -> dict:
    path = Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json"
    return json.loads(path.read_text())["entity"]


async def test_paired_generic_settings_preserve_child_app_profiles(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    left = {**main.entry.data, CONF_STARCODE_LIFT_ENTRIES: []}
    right = dict(lifts[0].entry.data)
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    original = entry.data[CONF_PAIR_CHILDREN]
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: 7})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for before, after in zip(original, entry.data[CONF_PAIR_CHILDREN], strict=True):
        for key in (CONF_STARCODE_M5X5_PROFILE, CONF_BLE_DEVICE_NAME):
            assert before[key] == after[key]


@pytest.mark.parametrize(
    ("profile", "name"),
    [
        ("cb25", "STAR252201123456"),
        ("f23", "STAR254205123456"),
        ("kneading", "STAR255402123456"),
        ("elevate", "ELEVATE123456"),
    ],
)
async def test_explicit_setup_and_factory(hass: HomeAssistant, profile: str, name: str) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.flow_id = "row005_setup"
    flow._manual_data = {
        CONF_ADDRESS: "AA:00:00:00:00:05",
        CONF_NAME: "Friendly name",
        CONF_BED_TYPE: BED_TYPE_STARCODE_M5X5,
    }
    result = await flow.async_step_starcode_m5x5()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "starcode_m5x5"
    with patch.object(
        flow, "_finish_with_verify", AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY})
    ) as finish:
        await flow.async_step_starcode_m5x5(
            {CONF_STARCODE_M5X5_PROFILE: profile, CONF_BLE_DEVICE_NAME: name}
        )
    data = finish.await_args.args[0]
    assert data[CONF_DISABLE_ANGLE_SENSING] == (profile == "elevate")
    assert data[CONF_HAS_MASSAGE] == (profile != "elevate")
    c = target(hass, 10, profile)
    controller = await create_controller(c, BED_TYPE_STARCODE_M5X5, "auto", None)
    assert controller.profile == profile
    assert controller.device_name == name
    assert c.async_ensure_connected.await_count == 0


async def test_name_and_lift_identity_validation(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    assert _starcode_errors(hass, main.entry.data, main.entry.entry_id) == {}
    bad = {**main.entry.data, CONF_BLE_DEVICE_NAME: "star254205123456"}
    assert CONF_STARCODE_M5X5_PROFILE in _starcode_errors(hass, bad)
    bad = {**main.entry.data, CONF_STARCODE_LIFT_ENTRIES: [t.entry.entry_id for t in lifts] * 2}
    assert CONF_STARCODE_LIFT_ENTRIES in _starcode_errors(hass, bad)
    schema = {}
    _add_starcode_schema_fields(schema, main.entry.data, hass, main.entry.entry_id)
    accepted = vol.Schema(schema)(
        {
            CONF_STARCODE_M5X5_PROFILE: "cb25",
            CONF_BLE_DEVICE_NAME: "STAR252201123456",
            CONF_STARCODE_LIFT_ENTRIES: [t.entry.entry_id for t in lifts],
        }
    )
    assert isinstance(accepted, dict)
    accepted_lifts = accepted[CONF_STARCODE_LIFT_ENTRIES]
    assert isinstance(accepted_lifts, list)
    assert len(accepted_lifts) == 3


async def test_controls_state_and_readonly_domains(hass: HomeAssistant) -> None:
    c = target(hass, 1, "kneading")
    buttons = _button_entities_for(hass, c)
    keys = {
        getattr(getattr(b, "entity_description", None), "key", b.translation_key) for b in buttons
    }
    assert {
        "starcode_save_tv",
        "starcode_save_zero_g",
        "starcode_save_lounge",
        "starcode_reset",
        "starcode_light_mode",
        "starcode_light_cycle",
        "starcode_query",
        "program_memory_1",
        "program_memory_2",
    } <= keys
    assert len(_light_entities_for(hass, c)) == 1
    numbers = _number_entities_for(hass, c)
    assert any(n.entity_description.translation_key == "starcode_brightness" for n in numbers)
    selects = _select_entities_for(hass, c)
    color = next(s for s in selects if s.entity_description.translation_key == "starcode_color")
    # The app's light enum names every index: 0 is off, 1 white, 7 purple.
    states = _entity_strings()["select"]["starcode_color"]["state"]
    assert list(states) == color.options
    assert (states["0"], states["1"], states["7"]) == ("Off", "White", "Purple")
    sensors = _sensor_entities_for(hass, c)
    sensor_keys = {s.translation_key for s in sensors}
    assert {
        "starcode_sonic_time_raw",
        "starcode_eq_volume",
        "starcode_kneading_time_raw",
        "starcode_alarm_0",
        "starcode_alarm_1",
    } <= sensor_keys
    c.handle_controller_state_updates(
        {
            "alarm_0": True,
            "alarm_0_details": {"repeat_raw": 255, "hour": 23},
            "light_color_index": 4,
            "light_color_option": "4",
            "light_rgb": [255, 255, 0],
        }
    )
    alarm = next(s for s in sensors if s.translation_key == "starcode_alarm_0")
    assert alarm.native_value is True
    assert alarm.extra_state_attributes["alarm_0_details"] == {"repeat_raw": 255, "hour": 23}
    color = next(s for s in sensors if s.translation_key == "starcode_light_color_index")
    assert color.extra_state_attributes["light_rgb"] == [255, 255, 0]
    assert not any(
        "alarm" in s.key or "sonic" in s.key or "kneading" in s.key
        for s in c.controller.controller_select_specs
    )


async def test_cb25_always_exposes_distinct_sonic_feedback(hass: HomeAssistant) -> None:
    c = target(hass, 1, "cb25")
    assert "sonic_time_raw" in {s.state_key for s in c.controller.controller_state_sensor_specs}
    assert "sonic_active" in {
        s.state_key for s in c.controller.controller_state_binary_sensor_specs
    }
    c.controller.dialect = "legacy"
    assert "alarm_1" not in {s.state_key for s in c.controller.controller_state_sensor_specs}
    c.controller.dialect = "star"
    assert "alarm_1" in {s.state_key for s in c.controller.controller_state_sensor_specs}


async def test_registered_group_service_and_schema(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=main.entry.entry_id, identifiers={(DOMAIN, main.address)}, name=main.name
    )
    main.entry.mock_state(hass, ConfigEntryState.LOADED)
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.starcode_accessory_group.run_group", AsyncMock()
    ) as run:
        await hass.services.async_call(
            DOMAIN,
            "starcode_move_lifts",
            {CONF_DEVICE_ID: device.id, "action": "flat"},
            blocking=True,
        )
    run.assert_awaited_once_with(main, "flat")
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "starcode_move_lifts",
            {CONF_DEVICE_ID: device.id, "action": "program"},
            blocking=True,
        )
