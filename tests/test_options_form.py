"""Options forms must offer values the selected profile can save."""

from typing import Any

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.bed_traits import default_connection_mode
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_OKIN_CST,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_CB24_BED_SELECTION,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OKIN_CST_VARIANT_CAREFREE,
    OKIN_CST_VARIANT_MF900,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    VARIANT_AUTO,
)


@pytest.mark.parametrize(
    ("variant", "stored_count", "expected_count"),
    [
        (VARIANT_AUTO, 2, 3),
        (OKIN_CST_VARIANT_MF900, 3, 3),
        (OKIN_CST_VARIANT_CAREFREE, 3, 2),
        (OKIN_CST_VARIANT_NECTAR_MOVE, 3, 2),
    ],
)
async def test_cst_options_only_offer_the_selected_profiles_motor_count(
    hass: HomeAssistant,
    enable_custom_integrations,
    mock_coordinator_connected,
    variant: str,
    stored_count: int,
    expected_count: int,
) -> None:
    """A fixed layout must not offer another profile's count or keep a stale one."""
    del enable_custom_integrations, mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:94",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: stored_count,
        },
    )
    entry.add_to_hass(hass)
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], user_input={"next_step_id": "settings"}
    )
    fields = {marker.schema: marker for marker in form["data_schema"].schema}
    # A count with one choice is not asked; the profile's own is saved.
    assert CONF_MOTOR_COUNT not in fields

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MOTOR_COUNT] == expected_count
    assert entry.data[CONF_PROTOCOL_VARIANT] == variant
    await hass.async_block_till_done()


async def _settings_form(hass: HomeAssistant, data: dict) -> tuple[MockConfigEntry, Any]:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:96", **data})
    entry.add_to_hass(hass)
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], user_input={"next_step_id": "settings"}
    )
    return entry, form


def _defaults(form: Any) -> dict:
    return {
        marker.schema: marker.default()
        for marker in form["data_schema"].schema
        if callable(marker.default)
    }


async def test_configure_shows_the_beds_own_connection_mode_default(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """An entry without a saved choice shows the per-bed default, as setup does."""
    del enable_custom_integrations
    _entry, form = await _settings_form(hass, {CONF_BED_TYPE: BED_TYPE_LINAK})

    assert _defaults(form)[CONF_CONNECTION_MODE] == default_connection_mode(
        BED_TYPE_LINAK, VARIANT_AUTO
    )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (CONF_BACK_MAX_ANGLE, "200", "invalid_angle"),
        (CONF_BACK_MAX_ANGLE, "steep", "invalid_angle"),
    ],
)
async def test_configure_reports_a_bad_angle_on_its_field(
    hass: HomeAssistant, enable_custom_integrations, field: str, value: str, error: str
) -> None:
    del enable_custom_integrations
    entry, form = await _settings_form(
        hass, {CONF_BED_TYPE: BED_TYPE_LINAK, CONF_DISABLE_ANGLE_SENSING: False}
    )

    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={field: value}
    )

    assert result["errors"] == {field: error}
    assert field not in entry.data


async def test_configure_saves_movement_per_tap_within_its_range(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Movement per tap is the only timing shown, and its range is enforced (#510)."""
    del enable_custom_integrations
    entry, form = await _settings_form(hass, {CONF_BED_TYPE: BED_TYPE_LINAK})
    fields = {marker.schema for marker in form["data_schema"].schema}
    assert CONF_MOTOR_PULSE_COUNT in fields
    assert CONF_MOTOR_PULSE_DELAY_MS not in fields
    with pytest.raises(vol.Invalid):
        form["data_schema"]({CONF_MOTOR_PULSE_COUNT: 101})

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={CONF_MOTOR_PULSE_COUNT: 4}
    )

    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MOTOR_PULSE_COUNT] == 4


@pytest.mark.parametrize(
    ("bed_type", "hidden"),
    [
        # No massage commands.
        ("customatic_clarity", "has_massage"),
        ("sleepys_box24", "has_massage"),
        # Fixed travel replaces both maximum angles.
        ("serta_mp_remote", CONF_BACK_MAX_ANGLE),
        ("sbi", CONF_BACK_MAX_ANGLE),
        # Taps that never repeat the command by that count.
        ("paramount", CONF_MOTOR_PULSE_COUNT),
        ("reverie", CONF_MOTOR_PULSE_COUNT),
    ],
)
async def test_configure_hides_settings_the_bed_ignores(
    hass: HomeAssistant, enable_custom_integrations, bed_type: str, hidden: str
) -> None:
    del enable_custom_integrations
    _entry, form = await _settings_form(
        hass, {CONF_BED_TYPE: bed_type, CONF_DISABLE_ANGLE_SENSING: False}
    )

    assert hidden not in {marker.schema for marker in form["data_schema"].schema}


async def test_cb24ab_side_is_a_declared_question(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    del enable_custom_integrations
    entry, form = await _settings_form(
        hass, {CONF_BED_TYPE: "smartbed", CONF_PROTOCOL_VARIANT: "cb24_ab"}
    )
    assert _defaults(form)[CONF_CB24_BED_SELECTION] == CB24_BED_SELECTION_DEFAULT

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={CONF_CB24_BED_SELECTION: str(CB24_BED_SELECTION_B)}
    )

    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_CB24_BED_SELECTION] == CB24_BED_SELECTION_B


async def test_configure_never_changes_the_route(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """A product that picks the route is changed in Reconfigure, which reviews it."""
    del enable_custom_integrations
    entry, form = await _settings_form(
        hass, {CONF_BED_TYPE: "rize_home", CONF_PROTOCOL_VARIANT: "remedy_iii"}
    )
    assert CONF_PROTOCOL_VARIANT not in {marker.schema for marker in form["data_schema"].schema}

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={}
    )

    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PROTOCOL_VARIANT] == "remedy_iii"


async def test_configure_keeps_an_automatic_route_unsaved(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Saving Configure must not pin a route the advertisement chooses at runtime."""
    del enable_custom_integrations
    entry, form = await _settings_form(hass, {CONF_BED_TYPE: "smart_sleep"})

    saved = await hass.config_entries.options.async_configure(form["flow_id"], user_input={})

    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_PROTOCOL_VARIANT not in entry.data


async def test_configure_asks_a_profiles_angle_question_as_read_bed_position(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """A profile that asks about angle sensing shows the positive toggle; the stored key stays."""
    del enable_custom_integrations
    entry, form = await _settings_form(hass, {CONF_BED_TYPE: "sleep_number"})
    fields = {marker.schema for marker in form["data_schema"].schema}
    assert "read_positions" in fields
    assert CONF_DISABLE_ANGLE_SENSING not in fields

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={"read_positions": False}
    )

    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True
    assert "read_positions" not in entry.data


async def test_verified_auto_smartbed_ab_pair_can_save_unchanged_settings(hass, enable_custom_integrations):
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    del enable_custom_integrations
    data = build_single_address_pair_entry_data({
        CONF_ADDRESS: "AA:BB:CC:DD:EE:95", CONF_BED_TYPE: "smartbed",
        CONF_PROTOCOL_VARIANT: "auto", "capabilities": {"smartbed": {"profile": "cb24_ab"}},
    }, name="Bed")
    entry, form = await _settings_form(hass, data)
    saved = await hass.config_entries.options.async_configure(form["flow_id"], user_input={})
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PROTOCOL_VARIANT] == "auto"
