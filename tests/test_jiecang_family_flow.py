"""One Jiecang app-or-remote question, and guided changes between its routes (#676)."""

from contextlib import ExitStack
from dataclasses import astuple
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.jiecang_app import require_app_transport
from custom_components.adjustable_bed.codec.jiecang import TRANSPORTS
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import bed_type_label
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from tests.test_jiecang_app_controller import _Services
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"


def jiecang_client(*transports: str) -> SimpleNamespace:
    """A connected link exposing exactly the given app transports."""
    services = {}
    for key in transports:
        service_uuid, *roles = astuple(TRANSPORTS[key])
        members = {
            uuid: SimpleNamespace(uuid=uuid, properties=["write", "notify"])
            for uuid in roles
            if uuid
        }
        services[service_uuid] = SimpleNamespace(
            uuid=service_uuid,
            characteristics=list(members.values()),
            get_characteristic=members.get,
        )
    client = SimpleNamespace(
        is_connected=True,
        address=ADDRESS,
        services=_Services(services, get_service=services.get),
        pair=AsyncMock(),
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client


def entry_for(hass, data) -> MockConfigEntry:
    data = {CONF_ADDRESS: ADDRESS, const.CONF_PREFERRED_ADAPTER: "auto", **data}
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        version=5,
        data={**data, const.CONF_PROFILE_ID: resolve_profile_id(data)},
    )
    entry.add_to_hass(hass)
    return entry


def setup_flow(hass, bed_type: str) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {CONF_ADDRESS: ADDRESS, CONF_NAME: "Bed", const.CONF_BED_TYPE: bed_type}
    return flow


async def reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_detected_legacy_route_can_be_kept_without_a_new_question(hass):
    flow = setup_flow(hass, const.BED_TYPE_COMFORT_MOTION)
    result = await flow.async_step_jiecang_family()
    options = result["data_schema"].schema["choice"].config["options"]
    assert options[-1] == "keep"
    assert result["description_placeholders"]["current"] == bed_type_label(
        const.BED_TYPE_COMFORT_MOTION
    )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        kept = await flow.async_step_jiecang_family({"choice": "keep"})
        assert kept["step_id"] == "keep_detected"
        await flow.async_step_keep_continue()
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == const.BED_TYPE_COMFORT_MOTION


async def test_remote_chosen_from_the_app_row_asks_its_motor_count(hass):
    flow = setup_flow(hass, const.BED_TYPE_JIECANG_APP)
    flow._manual_data[const.CONF_MOTOR_PULSE_COUNT] = 99
    result = await flow.async_step_jiecang_family({"choice": "legacy_jiecang"})
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_MOTOR_COUNT: "3"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_JIECANG
    assert saved[const.CONF_MOTOR_COUNT] == 3
    # The legacy route's own cadence replaces whatever the app row carried.
    assert saved[const.CONF_MOTOR_PULSE_COUNT] != 99
    assert saved[const.CONF_MOTOR_PULSE_USER_SET] is False


async def test_legacy_entry_changes_to_an_app_after_checking_its_transport(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_JIECANG, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, jiecang_client("g1"))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "jiecang_family"
        assert "keep" in result["data_schema"].schema["choice"].config["options"]
        result = await manager.async_configure(result["flow_id"], {"choice": "dreamotion"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_JIECANG_APP_LAYOUT: "standard_2"}
        )
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["step_id"] == "migration_confirm"
        assert entry.data == before
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_JIECANG_APP
    assert entry.data[const.CONF_JIECANG_APP_PROFILE] == "dreamotion"
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)
    assert entry.data[const.CONF_PROFILE_ID] != before[const.CONF_PROFILE_ID]


async def test_app_change_is_refused_when_the_link_lacks_its_transport(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_JIECANG, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, jiecang_client())
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "dreamotion"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_JIECANG_APP_LAYOUT: "standard_2"}
        )
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["step_id"] == "migration_check_failed"
        manager.async_abort(result["flow_id"])
    assert entry.data == before


@pytest.mark.parametrize(
    ("choice", "bed_type"),
    [("legacy_jiecang", const.BED_TYPE_JIECANG), ("legacy_lierda", const.BED_TYPE_COMFORT_MOTION)],
)
async def test_app_entry_changes_to_a_remote_route_without_a_transport_check(
    hass, enable_custom_integrations, choice, bed_type
):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_JIECANG_APP,
            const.CONF_JIECANG_APP_PROFILE: "dreamask",
            const.CONF_JIECANG_APP_LAYOUT: "standard_2",
            const.CONF_JIECANG_APP_TRANSPORT: "auto",
            const.CONF_MOTOR_COUNT: 2,
        },
    )
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    result = await manager.async_configure(result["flow_id"], {"choice": choice})
    # The app's layout set the motors; the legacy route asks its own count.
    assert result["step_id"] == "profile_questions"
    result = await manager.async_configure(result["flow_id"], {const.CONF_MOTOR_COUNT: 4})
    assert result["step_id"] == "migration_confirm"
    result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == bed_type
    assert entry.data[const.CONF_MOTOR_COUNT] == 4
    assert not any(
        key in entry.data for key in (const.CONF_JIECANG_APP_PROFILE, const.CONF_JIECANG_APP_LAYOUT)
    )
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_JIECANG, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


def test_transport_check_is_the_controllers_own_selection():
    data = {
        const.CONF_JIECANG_APP_PROFILE: "comfort_motion",
        const.CONF_JIECANG_APP_LAYOUT: "standard_2",
    }
    with pytest.raises(ConnectionError):
        require_app_transport(jiecang_client(), data)  # type: ignore[arg-type]
