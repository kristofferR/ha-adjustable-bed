"""One app question for Limoss receivers, and guided changes between their routes (#676)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from tests.test_jiecang_app_controller import _Services
from tests.test_sleepys_family_flow import finish_check, reconfigure
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"


def limoss_client(*properties: str) -> SimpleNamespace:
    """A link with the Limoss service and its command characteristic."""
    char = SimpleNamespace(uuid=const.LIMOSS_CHAR_UUID, properties=list(properties))
    service = SimpleNamespace(
        uuid=const.LIMOSS_SERVICE_UUID,
        characteristics=[char],
        get_characteristic={const.LIMOSS_CHAR_UUID: char}.get,
    )
    services = {const.LIMOSS_SERVICE_UUID: service}
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


def setup_flow(hass, bed_type: str) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_MOTOR_COUNT: 2,
    }
    return flow


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


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])


def test_one_row_names_both_apps_and_the_generic_controls():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    label = rows[const.BED_TYPE_LIMOSS]
    for name in ("Limoss Remote", "FSM Relax", "Stawett"):
        assert name in label
    assert not {const.BED_TYPE_LIMOSS_REMOTE, const.BED_TYPE_FSM_RELAX} & set(rows)


async def test_the_row_asks_the_app_and_keeps_the_generic_controls_one_answer_away(hass):
    flow = setup_flow(hass, const.BED_TYPE_LIMOSS)
    result = await flow.async_step_limoss_family()
    assert choices(result) == ["limoss_remote", "fsm_relax", "generic"]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_limoss_family({"choice": "generic"})
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == const.BED_TYPE_LIMOSS

    flow = setup_flow(hass, const.BED_TYPE_LIMOSS)
    result = await flow.async_step_limoss_family({"choice": "limoss_remote"})
    assert result["step_id"] == "profile_questions"
    result = await setup_flow(hass, const.BED_TYPE_LIMOSS).async_step_limoss_family(
        {"choice": "fsm_relax"}
    )
    assert result["step_id"] == "fsm_relax"


async def test_generic_entry_changes_to_remote_after_checking_its_characteristic(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS, const.CONF_MOTOR_COUNT: 2})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, limoss_client("write", "notify"))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "limoss_family"
        assert choices(result)[-1] == "keep"
        result = await manager.async_configure(result["flow_id"], {"choice": "limoss_remote"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_PRODUCT_TYPE: "chair"}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        assert entry.data == before
        result = await manager.async_configure(result["flow_id"], {"confirm": True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LIMOSS_REMOTE
    assert entry.data[const.CONF_PRODUCT_TYPE] == "chair"
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_remote_change_is_refused_without_the_notifying_characteristic(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS, const.CONF_MOTOR_COUNT: 2})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, limoss_client("write"))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "limoss_remote"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_PRODUCT_TYPE: "bed"}
        )
        result = await finish_check(hass, result)
        assert result["step_id"] != "migration_confirm"
        assert result.get("errors")
        manager.async_abort(result["flow_id"])
    assert entry.data == before


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX})
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_sends_an_app_change_to_the_guided_change(hass):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS, const.CONF_MOTOR_COUNT: 2})
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form(
        {const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS_REMOTE}, step_id="settings"
    )
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LIMOSS
