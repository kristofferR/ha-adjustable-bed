"""One LOGICDATA app question, and guided changes between the bed routes (#676)."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.actuator_groups import SINGLE_TYPE_GROUPS
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.controller_factory import require_logicdata_route
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles.logicdata import TRANSPORTS
from tests.test_sleepys_family_flow import (
    entry_for,
    finish_check,
    gatt_client,
    reconfigure,
    setup_flow,
)
from tests.test_vibradorm_family_flow import bluetooth_patches

T1 = (
    TRANSPORTS["t1"].service_uuid,
    TRANSPORTS["t1"].write_uuid,
    TRANSPORTS["t1"].notify_uuid,
    TRANSPORTS["t1"].name_uuid,
)
LOGICLINK = (const.LOGICDATA_SERVICE_UUID, const.LOGICDATA_CHAR_UUID)


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])
APP_KEYS = (
    const.CONF_LOGICDATA_APP_PROFILE,
    const.CONF_LOGICDATA_APP_FAMILY,
    const.CONF_LOGICDATA_APP_LAYOUT,
    const.CONF_LOGICDATA_APP_TRANSPORT,
)
PHONE = {
    const.CONF_BED_TYPE: const.BED_TYPE_LOGICDATA_APP,
    const.CONF_LOGICDATA_APP_PROFILE: "phone",
    const.CONF_LOGICDATA_APP_FAMILY: "p1",
    const.CONF_LOGICDATA_APP_LAYOUT: "standard_2",
    const.CONF_LOGICDATA_APP_TRANSPORT: "auto",
    const.CONF_MOTOR_COUNT: 2,
}


def test_one_row_names_every_app_and_finds_each_by_name():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    label = rows[const.BED_TYPE_LOGICDATA_APP]
    for app in ("SILVERmotion", "MOTIONrelax", "Sleep Smart"):
        assert [value for value, row in rows.items() if app.lower() in row.lower()] == [
            const.BED_TYPE_LOGICDATA_APP
        ], app
    assert label.startswith("LOGICDATA:")
    # SimplicityFrame and the pump are answers of the question, not rows of their own.
    assert not {const.BED_TYPE_LOGICDATA, const.BED_TYPE_LOGICDATA_AIR_PUMP} & set(rows)
    assert SINGLE_TYPE_GROUPS["logicdata"] == const.BED_TYPE_LOGICDATA_APP


def test_a_detected_simplicityframe_is_shown_as_the_family_row():
    from custom_components.adjustable_bed.config_flow import _bed_type_selector

    label = _bed_type_selector(const.BED_TYPE_LOGICDATA).shown(const.BED_TYPE_LOGICDATA)
    assert label.startswith("LOGICDATA:")


async def test_the_family_row_asks_the_app_and_has_nothing_to_keep(hass):
    result = await setup_flow(hass, const.BED_TYPE_LOGICDATA_APP).async_step_logicdata_family()
    assert choices(result) == ["silvermotion", "phone", "tablet", "sleep_smart", "sleep_smart_pump"]


async def test_a_detected_simplicityframe_is_kept_and_still_pairs(hass):
    flow = setup_flow(hass, const.BED_TYPE_LOGICDATA)
    result = await flow.async_step_logicdata_family()
    assert choices(result)[-1] == "keep"
    with patch.object(
        flow, "async_step_manual_pairing", new=AsyncMock(return_value={"step_id": "pair"})
    ) as pairing:
        await flow.async_step_logicdata_family({"choice": "keep"})
    pairing.assert_awaited_once()
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_LOGICDATA
    assert not set(APP_KEYS) & set(flow._manual_data)


async def test_the_pump_is_added_as_its_own_device_without_app_settings(hass):
    flow = setup_flow(hass, const.BED_TYPE_LOGICDATA_APP)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_logicdata_family({"choice": "sleep_smart_pump"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_LOGICDATA_AIR_PUMP
    assert not set(APP_KEYS) & set(saved)


async def test_choosing_another_app_drops_the_previous_apps_layout(hass):
    flow = setup_flow(hass, const.BED_TYPE_LOGICDATA_APP)
    flow._manual_data.update({**PHONE, const.CONF_LOGICDATA_APP_LAYOUT: "standard_4"})
    result = await flow.async_step_logicdata_family({"choice": "sleep_smart"})
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data[const.CONF_LOGICDATA_APP_PROFILE] == "sleep_smart"
    assert const.CONF_LOGICDATA_APP_LAYOUT not in flow._manual_data
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {const.CONF_LOGICDATA_APP_FAMILY: "p2", const.CONF_LOGICDATA_APP_LAYOUT: "split_series"}
        )
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_LOGICDATA_APP_FAMILY], saved[const.CONF_LOGICDATA_APP_LAYOUT]) == (
        "p2",
        "split_series",
    )
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True


async def test_phone_entry_changes_to_the_tablet_after_checking_its_transport(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, PHONE)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, gatt_client(T1))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "logicdata_family"
        # A bed entry never becomes the pump, which is its own device.
        assert "sleep_smart_pump" not in choices(result)
        assert "keep" in choices(result)
        result = await manager.async_configure(result["flow_id"], {"choice": "tablet"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(
            result["flow_id"],
            {const.CONF_LOGICDATA_APP_FAMILY: "p1", const.CONF_LOGICDATA_APP_LAYOUT: "standard_4"},
        )
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        assert entry.data[const.CONF_LOGICDATA_APP_PROFILE] == "phone"
        result = await manager.async_configure(result["flow_id"], {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_LOGICDATA_APP_PROFILE] == "tablet"
    assert entry.data[const.CONF_LOGICDATA_APP_LAYOUT] == "standard_4"
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)
    assert entry.data[const.CONF_PROFILE_ID] == "logicdata_app@tablet"


async def test_app_change_is_refused_when_the_link_lacks_its_transport(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_LOGICDATA, const.CONF_MOTOR_COUNT: 2})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        # SimplicityFrame's LogicLink service has none of the app transports.
        bluetooth_patches(stack, gatt_client(LOGICLINK))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "sleep_smart"})
        result = await manager.async_configure(
            result["flow_id"],
            {const.CONF_LOGICDATA_APP_FAMILY: "p1", const.CONF_LOGICDATA_APP_LAYOUT: "standard_2"},
        )
        result = await finish_check(hass, result)
        assert result["step_id"] != "migration_confirm"
        assert result.get("errors")
        manager.async_abort(result["flow_id"])
    assert entry.data == before


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(hass, PHONE)
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    assert choices(result)[-1] == "keep"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_into_the_app_from_another_family_asks_the_app_and_layout(hass):
    """A repair can hand a Comfort Motion entry to the Sleep Smart app through Configure."""
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_MOTION, const.CONF_MOTOR_COUNT: 2}
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(
        {const.CONF_BED_TYPE: const.BED_TYPE_LOGICDATA_APP}, step_id="settings"
    )
    fields = {marker.schema for marker in form["data_schema"].schema}
    assert {
        const.CONF_LOGICDATA_APP_PROFILE,
        const.CONF_LOGICDATA_APP_FAMILY,
        const.CONF_LOGICDATA_APP_LAYOUT,
    } <= fields
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form(
            {
                const.CONF_LOGICDATA_APP_PROFILE: "sleep_smart",
                const.CONF_LOGICDATA_APP_FAMILY: "p1",
                const.CONF_LOGICDATA_APP_LAYOUT: "standard_2",
            },
            step_id="settings",
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LOGICDATA_APP
    assert entry.data[const.CONF_LOGICDATA_APP_PROFILE] == "sleep_smart"
    assert entry.data[const.CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(
    ("data", "services", "ok"),
    [
        ({const.CONF_BED_TYPE: const.BED_TYPE_LOGICDATA}, (LOGICLINK,), True),
        ({const.CONF_BED_TYPE: const.BED_TYPE_LOGICDATA}, (T1,), False),
        (PHONE, (T1,), True),
        (PHONE, (LOGICLINK,), False),
        ({**PHONE, const.CONF_LOGICDATA_APP_TRANSPORT: "t3"}, (T1,), False),
    ],
)
def test_route_check_matches_what_each_route_needs(data, services, ok):
    client = gatt_client(*services)
    if ok:
        require_logicdata_route(client, {CONF_ADDRESS: "x", **data})  # type: ignore[arg-type]
    else:
        with pytest.raises(ConnectionError):
            require_logicdata_route(client, {CONF_ADDRESS: "x", **data})  # type: ignore[arg-type]
