"""Options forms must offer values the selected profile can save."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.bed_traits import disconnect_after_command_default_enabled
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CST,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    CONF_BACK_MAX_ANGLE,
    CONF_BED_TYPE,
    CONF_CB24_BED_SELECTION,
    CONF_DISCONNECT_AFTER_COMMAND,
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
from tests.form_helpers import finish_new_bed, start_new_bed


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
    marker = fields[CONF_MOTOR_COUNT]
    assert marker.default() == expected_count
    validator = form["data_schema"].schema[marker]
    assert validator.validators[-1].container == [expected_count]

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


async def test_configure_shows_the_beds_own_disconnect_default(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """An entry without a saved choice shows the per-bed default, as setup does."""
    del enable_custom_integrations
    _entry, form = await _settings_form(hass, {CONF_BED_TYPE: BED_TYPE_LINAK})

    assert _defaults(form)[CONF_DISCONNECT_AFTER_COMMAND] is (
        disconnect_after_command_default_enabled(BED_TYPE_LINAK, VARIANT_AUTO)
    )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        (CONF_MOTOR_PULSE_COUNT, "many", "invalid_number"),
        (CONF_MOTOR_PULSE_DELAY_MS, "0", "invalid_number"),
        (CONF_BACK_MAX_ANGLE, "200", "invalid_angle"),
    ],
)
async def test_configure_reports_a_bad_number_on_its_field(
    hass: HomeAssistant, enable_custom_integrations, field: str, value: str, error: str
) -> None:
    del enable_custom_integrations
    entry, form = await _settings_form(hass, {CONF_BED_TYPE: BED_TYPE_LINAK})

    result = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={field: value}
    )

    assert result["errors"] == {field: error}
    assert field not in entry.data


async def test_cb24_side_is_a_declared_question(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    del enable_custom_integrations
    entry, form = await _settings_form(hass, {CONF_BED_TYPE: BED_TYPE_OKIN_CB24})
    assert _defaults(form)[CONF_CB24_BED_SELECTION] == CB24_BED_SELECTION_DEFAULT

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={CONF_CB24_BED_SELECTION: str(CB24_BED_SELECTION_B)}
    )

    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_CB24_BED_SELECTION] == CB24_BED_SELECTION_B


async def test_setup_asks_the_cb24_side_in_the_final_settings(hass: HomeAssistant) -> None:
    """A route without an app step asks its declared questions with its final settings."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "typed", BED_TYPE_OKIN_CB24)
    assert result["step_id"] == "finish_settings"
    assert _defaults(result)[CONF_CB24_BED_SELECTION] == CB24_BED_SELECTION_DEFAULT

    await finish_new_bed(flow, result, {CONF_CB24_BED_SELECTION: str(CB24_BED_SELECTION_A)})

    assert flow._finish_with_verify.await_args.args[0][CONF_CB24_BED_SELECTION] == (
        CB24_BED_SELECTION_A
    )
