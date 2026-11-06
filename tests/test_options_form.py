"""Options forms must offer values the selected profile can save."""

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CST,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
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
    if variant != OKIN_CST_VARIANT_NECTAR_MOVE:
        marker = fields[CONF_MOTOR_COUNT]
        assert marker.default() == str(expected_count)
        validator = form["data_schema"].schema[marker]
        assert validator.validators[-1].container == [str(expected_count)]
    else:
        assert CONF_MOTOR_COUNT not in fields

    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], user_input={}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MOTOR_COUNT] == expected_count
    assert entry.data[CONF_PROTOCOL_VARIANT] == variant
    await hass.async_block_till_done()
