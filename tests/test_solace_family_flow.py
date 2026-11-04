"""One app question for QMS-named beds, and guided changes between Solace routes (#676)."""

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.profile_id import resolve_profile_id

ADDRESS = "11:22:33:44:55:66"


def setup_flow(hass, variant: str = const.VARIANT_AUTO) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "QMS-MQ",
        const.CONF_BED_TYPE: const.BED_TYPE_SOLACE,
        const.CONF_PROTOCOL_VARIANT: variant,
        const.CONF_MOTOR_COUNT: 2,
    }
    return flow


def entry_for(hass, variant: str) -> MockConfigEntry:
    data = {
        CONF_ADDRESS: ADDRESS,
        const.CONF_BED_TYPE: const.BED_TYPE_SOLACE,
        const.CONF_PROTOCOL_VARIANT: variant,
        const.CONF_MOTOR_COUNT: 2,
    }
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        version=5,
        data={**data, const.CONF_PROFILE_ID: resolve_profile_id(data)},
    )
    entry.add_to_hass(hass)
    return entry


async def test_qms_bed_asks_the_app_and_keep_saves_the_name_route(hass):
    flow = setup_flow(hass)
    result = await flow.async_step_solace_family()
    options = result["data_schema"].schema["choice"].config["options"]
    assert options == ["name_route", "woosa", "motion_bed", "bedsense", "keep"]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_solace_family({"choice": "keep"})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == const.VARIANT_AUTO


async def test_woosa_shows_its_own_controls_before_choosing_it(hass):
    flow = setup_flow(hass)
    result = await flow.async_step_solace_family({"choice": "woosa"})
    assert result["step_id"] == "solace_woosa"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_solace_woosa({})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == const.SOLACE_VARIANT_WOOSA


async def test_motion_bed_and_bedsense_stay_their_own_bed_types(hass):
    flow = setup_flow(hass)
    result = await flow.async_step_solace_family({"choice": "motion_bed"})
    assert result["step_id"] == "motion_bed"
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_MOTION_BED

    flow = setup_flow(hass)
    result = await flow.async_step_solace_family({"choice": "bedsense"})
    assert result["step_id"] == "solace_bedsense"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_solace_bedsense({const.CONF_PROTOCOL_VARIANT: "bedsense_7"})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_BEDSENSE,
        "bedsense_7",
    )


async def test_woosa_entry_changes_back_to_the_name_route(hass, enable_custom_integrations):
    entry = entry_for(hass, const.SOLACE_VARIANT_WOOSA)
    before = dict(entry.data)
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "solace_family"
    result = await manager.async_configure(result["flow_id"], {"choice": "name_route"})
    assert result["step_id"] == "migration_confirm"
    assert entry.data == before
    result = await manager.async_configure(result["flow_id"], {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == const.VARIANT_AUTO
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(hass, const.VARIANT_AUTO)
    before = dict(entry.data)
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await manager.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before
