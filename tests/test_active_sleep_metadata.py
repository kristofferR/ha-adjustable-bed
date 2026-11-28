"""Active Sleep uses the shared native controls without exposing protocol state."""

from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed.beds.active_sleep.controller import (
    BUSY,
    FAIL,
    HEART,
    MODE,
    RAW,
    RESPIRATION,
    ZONE_KEYS,
)
from custom_components.adjustable_bed.card import (
    CARD_PRESET_SAVE,
    CARD_PRESETS,
    CARD_UTILITY,
    CardRole,
    motor_card,
)
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
)
from custom_components.adjustable_bed.redaction import redact_data
from tests.test_active_sleep import Bed
from tests.test_options_form import _settings_form


async def test_catalog_buttons_keep_their_actions_and_safe_shared_shapes() -> None:
    bed = Bed()
    controller = await bed.connect()
    controller._spec = replace(controller._spec, model=5)
    buttons = {spec.key: spec for spec in controller.controller_button_specs}

    for slot in range(1, 11):
        spec = buttons[f"active_sleep_template_{slot}"]
        assert (spec.translation_key, spec.card) == ("catalog_preset", CARD_PRESETS)
        assert spec.translation_placeholders == {"action": f"Position {slot}"}
        assert spec.hold is not None and spec.hold.control == f"template_{slot}"
    for direction, role in (("up", CardRole.UP), ("down", CardRole.DOWN)):
        spec = buttons[f"active_sleep_combination_{direction}"]
        assert (spec.translation_key, spec.card) == (
            f"head_feet_{direction}",
            motor_card("head_feet", role),
        )
        assert spec.hold is not None and spec.hold.control == f"combination_{direction}"
    for kind, count in (("bed", 10), ("mattress", 5)):
        for slot in range(1, count + 1):
            for operation in ("save", "reset"):
                spec = buttons[f"active_sleep_{operation}_{kind}_{slot}"]
                assert spec.requires_confirmation and spec.hold is None
                assert not spec.entity_registry_enabled_default
                assert spec.card == (CARD_PRESET_SAVE if operation == "save" else CARD_UTILITY)

    assert "multi_button" in controller.held_control_options
    assert "active_sleep_multi_button" not in buttons
    assert buttons["active_sleep_refresh"].diagnostic
    assert not buttons["active_sleep_refresh"].cancel_movement
    acknowledgement = buttons["active_sleep_height_ack"]
    assert acknowledgement.requires_confirmation and acknowledgement.hold is None
    assert acknowledgement.entity_registry_enabled_default

    controller.press = AsyncMock()
    for key, spec in buttons.items():
        await spec.press_fn(controller)
        expected = {"refresh": "refresh", "height_ack": "acknowledge"}.get(
            key.removeprefix("active_sleep_"), key.removeprefix("active_sleep_")
        )
        controller.press.assert_awaited_with(expected)
        assert spec.scheduler_resource is None
    controller._spec = replace(controller._spec, model=3)
    assert "active_sleep_template_10" not in {
        spec.key for spec in controller.controller_button_specs
    }


async def test_sleep_rates_are_shared_measurements_and_protocol_codes_stay_diagnostic() -> None:
    bed = Bed()
    controller = await bed.connect()
    specs = {spec.key: spec for spec in controller.controller_state_sensor_specs}
    for key, translation, unit in (
        (HEART, "heart_rate", "bpm"),
        (RESPIRATION, "breathing_rate", "breaths/min"),
    ):
        spec = specs[str(key)]
        assert spec.state_key == key
        assert (spec.translation_key, spec.native_unit_of_measurement) == (translation, unit)
        assert spec.state_class is SensorStateClass.MEASUREMENT
        assert spec.entity_category is None and spec.entity_registry_enabled_default
        assert spec.card == CARD_UTILITY
    diagnostic_keys = (RAW, MODE, BUSY, FAIL, *ZONE_KEYS.values())
    assert not set(map(str, diagnostic_keys)) & specs.keys()
    updates = {key: index for index, key in enumerate(diagnostic_keys[1:], 1)}
    bed.coordinator.controller_state.update(updates.items())
    bed.coordinator.controller_state.update(((RAW, "sensitive sleep readings"),))
    diagnostics = controller.protocol_diagnostics
    assert diagnostics == {
        str(RAW): "sensitive sleep readings",
        **{str(key): value for key, value in updates.items()},
    }
    assert redact_data(diagnostics)[str(RAW)] == "<str>"
    assert "0123456789ABCDEF" not in str(diagnostics)
    controller._spec = replace(controller._spec, analyzer=False)
    assert not {str(HEART), str(RESPIRATION)} & {
        spec.key for spec in controller.controller_state_sensor_specs
    }


@pytest.mark.parametrize("read_positions", [True, False])
async def test_native_configure_exposes_and_saves_read_bed_position(
    hass: HomeAssistant, enable_custom_integrations: object, read_positions: bool
) -> None:
    del enable_custom_integrations
    entry, form = await _settings_form(
        hass, {CONF_BED_TYPE: "active_sleep", "active_sleep_auth_id": "0123456789ABCDEF"}
    )
    fields = {marker.schema for marker in form["data_schema"].schema}
    assert "read_positions" in fields and CONF_DISABLE_ANGLE_SENSING not in fields
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={"read_positions": read_positions}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data.get(CONF_DISABLE_ANGLE_SENSING, False) is not read_positions
    assert "read_positions" not in entry.data
    assert entry.data["active_sleep_auth_id"] == "0123456789ABCDEF"
