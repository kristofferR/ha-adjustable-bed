"""One Leggett & Platt app-or-remote question, and guided changes between its routes (#676)."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import bed_type_label
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from tests.test_okin_family_flow import OKIN, finish_check, okin_client
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"


def setup_flow(hass, bed_type: str, **data) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_MOTOR_COUNT: 2,
        **data,
    }
    return flow


def entry_for(hass, **data) -> MockConfigEntry:
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


def test_the_okin_label_names_the_apps_that_drive_it():
    label = bed_type_label(const.BED_TYPE_LEGGETT_OKIN)
    for app in ("Prodigy CE", "Prodigy 2", "Prodigy 2L", "U Series", "LP Control"):
        assert app in label


async def test_detected_receiver_asks_the_app_and_keep_pairs_the_detected_route(hass):
    flow = setup_flow(hass, const.BED_TYPE_LEGGETT_OKIN)
    result = await flow.async_step_leggett_family()
    options = result["data_schema"].schema["choice"].config["options"]
    assert options[:4] == ["prodigy_ce", "prodigy2", "prodigy2l", "useries"]
    assert options[-1] == "keep"
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pairing:
        kept = await flow.async_step_leggett_family({"choice": "keep"})
        assert kept["step_id"] == "keep_detected"
        await flow.async_step_keep_continue()
    pairing.assert_awaited_once()
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_LEGGETT_OKIN


async def test_l_and_p_app_with_a_qrrm_remote_uses_the_richmat_profile(hass):
    flow = setup_flow(hass, const.BED_TYPE_LEGGETT_OKIN, leggett_app_profile="useries")
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_leggett_family({"choice": "lp_app_qrrm"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_RICHMAT
    assert saved[const.CONF_RICHMAT_REMOTE] == const.RICHMAT_REMOTE_LP_QRRM
    assert const.CONF_LEGGETT_APP_PROFILE not in saved


async def test_mlrm_base_and_the_legacy_app_keep_their_routes(hass):
    flow = setup_flow(hass, const.BED_TYPE_LEGGETT_OKIN)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_leggett_family({"choice": "lp_app_mlrm"})
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == const.BED_TYPE_LEGGETT_WILINKE

    flow = setup_flow(hass, const.BED_TYPE_LEGGETT_OKIN)
    result = await flow.async_step_leggett_family({"choice": "lp_legacy"})
    assert result["step_id"] == "profile_questions"


async def test_umbrella_entry_keeps_its_saved_id_through_a_bonded_change(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass,
        **{
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_PLATT,
            const.CONF_PROTOCOL_VARIANT: const.LEGGETT_VARIANT_GEN2,
        },
    )
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, okin_client(OKIN))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "leggett_family"
        result = await manager.async_configure(result["flow_id"], {"choice": "prodigy2"})
        # The Okin receiver needs its bond, so the change pairs before review.
        assert result["step_id"] == "manual_pairing"
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LEGGETT_PLATT
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == const.LEGGETT_VARIANT_OKIN
    assert entry.data[const.CONF_LEGGETT_APP_PROFILE] == "prodigy2"
    assert entry.data[const.CONF_MOTOR_COUNT] == 3
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_okin_entry_changes_to_the_mlrm_route_without_a_check(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass,
        **{
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_OKIN,
            const.CONF_LEGGETT_APP_PROFILE: "prodigy4",
        },
    )
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    result = await manager.async_configure(result["flow_id"], {"choice": "lp_app_mlrm"})
    assert result["step_id"] == "migration_confirm"
    result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LEGGETT_WILINKE
    assert const.CONF_LEGGETT_APP_PROFILE not in entry.data


async def test_lp_comfort_connect_change_leaves_its_bond_to_the_first_connection(
    hass, enable_custom_integrations
):
    entry = entry_for(
        hass,
        **{
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_OKIN,
            const.CONF_LEGGETT_APP_PROFILE: "prodigy4",
        },
    )
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    result = await manager.async_configure(result["flow_id"], {"choice": "lp_control_gen2"})
    # The box grants one connection per pairing window, so nothing pairs here.
    assert result["step_id"] == "migration_confirm"
    result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LEGGETT_GEN2
    assert const.CONF_LEGGETT_APP_PROFILE not in entry.data


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(hass, **{const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_GEN2})
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


@pytest.mark.parametrize(
    "data",
    [
        {
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_LP_LEGACY,
            const.CONF_LP_LEGACY_MODEL: "6BRM",
            const.CONF_LP_LEGACY_MODE: "legacy",
            const.CONF_LP_LEGACY_WRITE_UUID: "0000fff2-0000-1000-8000-00805f9b34fb",
        },
        {
            const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT,
            const.CONF_RICHMAT_REMOTE: const.RICHMAT_REMOTE_LP_QRRM,
        },
    ],
    ids=["legacy_app", "qrrm_app"],
)
async def test_an_lp_app_route_on_another_bed_type_changes_through_the_question(
    hass, enable_custom_integrations, data
):
    """The legacy app and the QRRM remote are answers too, so Reconfigure asks them."""
    entry = entry_for(hass, **data)
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    assert result["step_id"] == "leggett_family"
    result = await manager.async_configure(result["flow_id"], {"choice": "lp_app_mlrm"})
    assert result["step_id"] == "migration_confirm"
    result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LEGGETT_WILINKE
    # The previous route's own settings are gone.
    assert not (set(data) - {const.CONF_BED_TYPE}) & set(entry.data)
