"""One Keeson app-or-remote question, and guided changes between its routes (#676)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id

ADDRESS = "11:22:33:44:55:66"


def setup_flow(hass, bed_type: str, variant: str = const.VARIANT_AUTO) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_PROTOCOL_VARIANT: variant,
        const.CONF_MOTOR_COUNT: 2,
    }
    return flow


def options(result, key: str = "choice") -> list[str]:
    return [
        option if isinstance(option, str) else option["value"]
        for option in result["data_schema"].schema[key].config["options"]
    ]


def entry_for(hass, data) -> MockConfigEntry:
    data = {CONF_ADDRESS: ADDRESS, const.CONF_MOTOR_COUNT: 2, **data}
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        version=5,
        data={**data, const.CONF_PROFILE_ID: resolve_profile_id(data)},
    )
    entry.add_to_hass(hass)
    return entry


async def reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_generic_row_asks_the_app_and_keep_saves_the_detected_route(hass):
    flow = setup_flow(hass, const.BED_TYPE_KEESON)
    result = await flow.async_step_keeson_family()
    assert result["step_id"] == "keeson_family"
    assert options(result)[-1] == "keep"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_keeson_family({"choice": "keep"})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_KEESON,
        const.VARIANT_AUTO,
    )


async def test_ore_app_asks_its_screen_for_the_motor_count(hass):
    flow = setup_flow(hass, const.BED_TYPE_KEESON)
    result = await flow.async_step_keeson_family({"choice": "ore_apps"})
    assert result["step_id"] == "keeson_app"
    assert len(options(result)) == 6
    result = await flow.async_step_keeson_app({"choice": "keeson:avanti_bases"})
    assert result["step_id"] == "keeson_screen"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_keeson_screen({const.CONF_MOTOR_COUNT: "4"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_AVANTI_BASES
    assert saved[const.CONF_MOTOR_COUNT] == 4
    assert saved[const.CONF_MOTOR_PULSE_USER_SET] is False


async def test_one_restonic_row_asks_the_apps_remote_style(hass):
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    assert rows["keeson:restonic_a"] == "Restonic BT app (Keeson)"
    assert "keeson:restonic_b" not in rows
    # Choosing the row is an app answer, so the style follows directly.
    flow = setup_flow(hass, const.BED_TYPE_KEESON, const.KEESON_VARIANT_RESTONIC_A)
    result = await flow.async_step_keeson_family()
    assert result["step_id"] == "keeson_restonic"
    assert options(result, const.CONF_PROTOCOL_VARIANT) == ["restonic_a", "restonic_b"]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_keeson_restonic({const.CONF_PROTOCOL_VARIANT: "restonic_b"})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == "restonic_b"


async def test_an_app_row_skips_the_question(hass):
    flow = setup_flow(hass, const.BED_TYPE_KEESON, const.KEESON_VARIANT_SIMON_LI)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_keeson_family()
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_SIMON_LI


@pytest.mark.parametrize(
    ("choice", "variant"),
    [
        ("keeson:purple", const.KEESON_VARIANT_PURPLE),
        ("keeson:base", const.KEESON_VARIANT_BASE),
        ("keeson:json", const.KEESON_VARIANT_JSON),
    ],
)
async def test_each_purple_base_or_json_answer_selects_its_route(hass, choice, variant):
    flow = setup_flow(hass, const.BED_TYPE_KEESON)
    result = await flow.async_step_keeson_family({"choice": "purple_base_json"})
    assert options(result) == ["keeson:purple", "keeson:base", "keeson:json"]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_keeson_app({"choice": choice})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == variant


async def test_ergomotion_apps_continue_in_their_own_app_step(hass):
    flow = setup_flow(hass, const.BED_TYPE_KEESON)
    await flow.async_step_keeson_family({"choice": "ergomotion_apps"})
    result = await flow.async_step_keeson_app({"choice": const.BED_TYPE_ERGOMOTION_4})
    assert result["step_id"] == "cluster033_app"
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_ERGOMOTION_4


async def test_an_older_remote_route_stays_reachable(hass):
    flow = setup_flow(hass, const.BED_TYPE_COOLBASE)
    result = await flow.async_step_keeson_family({"choice": "other_route"})
    assert result["step_id"] == "keeson_route"
    assert const.KEESON_VARIANT_KSBT_CR in options(result, const.CONF_PROTOCOL_VARIANT)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_keeson_route(
            {const.CONF_PROTOCOL_VARIANT: const.KEESON_VARIANT_KSBT_CR, const.CONF_MOTOR_COUNT: 3}
        )
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_KEESON,
        const.KEESON_VARIANT_KSBT_CR,
    )
    assert saved[const.CONF_MOTOR_COUNT] == 3


async def test_cool_base_entry_changes_to_restonic_through_the_guided_change(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_COOLBASE})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    assert result["step_id"] == "keeson_family"
    result = await manager.async_configure(result["flow_id"], {"choice": "restonic"})
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "restonic_b"}
    )
    assert result["step_id"] == "migration_confirm"
    assert entry.data == before
    result = await manager.async_configure(result["flow_id"], {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert (entry.data[const.CONF_BED_TYPE], entry.data[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_KEESON,
        "restonic_b",
    )
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)
    assert entry.data[const.CONF_PROFILE_ID] != before[const.CONF_PROFILE_ID]


async def test_a_route_change_takes_configures_route_defaults(hass, enable_custom_integrations):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
            const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO,
            const.CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    result = await manager.async_configure(result["flow_id"], {"choice": "other_route"})
    result = await manager.async_configure(
        result["flow_id"],
        {const.CONF_PROTOCOL_VARIANT: const.KEESON_VARIANT_ERGOMOTION, const.CONF_MOTOR_COUNT: 2},
    )
    result = await manager.async_configure(result["flow_id"], {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_ERGOMOTION
    # The Ergomotion route reports positions, so angle sensing turns on.
    assert entry.data[const.CONF_DISABLE_ANGLE_SENSING] is False


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(
        hass,
        {const.CONF_BED_TYPE: const.BED_TYPE_SERTA},
    )
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before
