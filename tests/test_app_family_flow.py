"""One app question each for Customatic, Jordan's and the StarCode apps (#676)."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec.okin_nframe import SERVICE_UUID, WRITE_UUID
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.detection import bed_type_label, get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profile_migration import SLEEPYS_FAMILY
from tests.form_helpers import finish_new_bed, start_new_bed
from tests.test_sleepys_family_flow import finish_check, gatt_client, reconfigure
from tests.test_vibradorm_family_flow import bluetooth_patches

ADDRESS = "11:22:33:44:55:66"
CUSTOMATIC = (SERVICE_UUID, WRITE_UUID)
# The OKIN bedding apps' exact command and notification roles.
BEDDING = (
    const.OKIMAT_SERVICE_UUID,
    const.OKIMAT_WRITE_CHAR_UUID,
    "62741625-52f9-8864-b1ab-3b3a8d65950b",
)


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])


def setup_flow(hass, bed_type: str, variant: str | None = None) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_MOTOR_COUNT: 2,
        **({const.CONF_PROTOCOL_VARIANT: variant} if variant else {}),
    }
    return flow


def entry_for(hass, data) -> MockConfigEntry:
    data = {
        CONF_ADDRESS: ADDRESS,
        const.CONF_PREFERRED_ADAPTER: "auto",
        const.CONF_MOTOR_COUNT: 2,
        **data,
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


def test_each_family_has_one_row_naming_its_apps():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    for row, apps in (
        (
            const.BED_TYPE_CUSTOMATIC_CLARITY,
            # The accepted reports name two of the apps Rize Clarity and Rize Remedy.
            ("Clarity", "Rize Clarity", "Jerome's C", "Rize Remedy", "Z-Series"),
        ),
        (const.BED_TYPE_SERENITY, ("Serenity", "Tranquil")),
        (const.BED_TYPE_STARCODE_ABM5_4, ("AdjustableM5X4", "AdjustableM5X5", "M1X12")),
    ):
        assert all(app in rows[row] for app in apps), rows[row]
    assert not {
        const.BED_TYPE_CUSTOMATIC_JEROMES,
        const.BED_TYPE_CUSTOMATIC_REMEDY,
        "customatic_zseries:z230",
        "customatic_zseries:z280",
        const.BED_TYPE_TRANQUIL,
        const.BED_TYPE_STARCODE_M5X5,
        const.BED_TYPE_STARCODE_M1X12,
    } & set(rows)
    # Adjustable bed (Lumbar) and the ELEVATE lifts stay their own rows.
    assert {const.BED_TYPE_ADJUSTABLE_LUMBAR, const.BED_TYPE_STAR_ELEVATE} <= set(rows)


async def test_the_customatic_row_asks_the_app_and_the_z_series_model(hass):
    flow = setup_flow(hass, const.BED_TYPE_CUSTOMATIC_CLARITY)
    result = await flow.async_step_customatic_family()
    assert choices(result) == ["clarity", "jeromes", "remedy", "zseries_z230", "zseries_z280"]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_customatic_family({"choice": "zseries_z280"})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_ZSERIES,
        const.ZSERIES_VARIANT_Z280,
    )


async def test_the_jordans_row_asks_serenity_or_tranquil(hass):
    flow = setup_flow(hass, const.BED_TYPE_SERENITY)
    result = await flow.async_step_jordans_family()
    assert choices(result) == ["serenity", "tranquil"]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_jordans_family({"choice": "tranquil"})
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == const.BED_TYPE_TRANQUIL


async def test_the_starcode_row_hands_each_app_to_its_own_step(hass):
    flow = setup_flow(hass, const.BED_TYPE_STARCODE_ABM5_4)
    result = await flow.async_step_starcode_family()
    assert choices(result) == ["m5x4", "m5x5", "m1x12"]
    result = await flow.async_step_starcode_family({"choice": "m5x5"})
    assert result["step_id"] == "starcode_m5x5"
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_STARCODE_M5X5


@pytest.mark.parametrize(
    ("bed_type", "step", "choice"),
    [
        (const.BED_TYPE_CUSTOMATIC_CLARITY, "customatic_family", "clarity"),
        (const.BED_TYPE_SERENITY, "jordans_family", "serenity"),
    ],
)
async def test_choosing_the_rows_own_app_keeps_the_settings_the_form_collected(
    hass, bed_type, step, choice
):
    # Fresh setup stages the automatic route and the user's pulse settings.
    flow = setup_flow(hass, bed_type, const.VARIANT_AUTO)
    assert flow._manual_data is not None
    flow._manual_data.update(
        {const.CONF_MOTOR_PULSE_COUNT: 37, const.CONF_MOTOR_PULSE_USER_SET: True}
    )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await getattr(flow, f"async_step_{step}")({"choice": choice})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_MOTOR_PULSE_COUNT], saved[const.CONF_MOTOR_PULSE_USER_SET]) == (
        37,
        True,
    )


@pytest.mark.parametrize(
    ("bed_type", "step"),
    [
        (const.BED_TYPE_CUSTOMATIC_JEROMES, "customatic_family"),
        (const.BED_TYPE_TRANQUIL, "jordans_family"),
    ],
)
async def test_an_app_already_chosen_is_not_asked_again(hass, bed_type, step):
    # An app other than the family row's own arrives as the app itself.
    flow = setup_flow(hass, bed_type)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await getattr(flow, f"async_step_{step}")()
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == bed_type


async def test_the_jordans_row_asks_which_jordans_app(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = ADDRESS
    info.service_uuids = [const.OKIMAT_SERVICE_UUID]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    result = await start_new_bed(flow, "picked", const.BED_TYPE_SERENITY)
    assert result["step_id"] == "jordans_family"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await finish_new_bed(
            flow, await flow.async_step_jordans_family({"choice": "tranquil"}), {CONF_NAME: "Bed"}
        )
    assert finish.call_args.args[0][const.CONF_BED_TYPE] == const.BED_TYPE_TRANQUIL


async def test_another_familys_guided_change_never_offers_keep_here(hass):
    flow = setup_flow(hass, const.BED_TYPE_STARCODE_ABM5_4)
    flow._migration = object()  # type: ignore[assignment]
    flow._migration_family = SLEEPYS_FAMILY
    result = await flow.async_step_starcode_family()
    assert "keep" not in choices(result)


def test_configure_accepts_the_hidden_apps_a_repair_submits():
    selector = _bed_type_selector(const.BED_TYPE_OKIN_CST, show_saved_id=True)
    for choice in (const.BED_TYPE_TRANQUIL, "customatic_zseries:z230"):
        assert selector(choice) == choice


async def test_clarity_entry_changes_to_remedy_after_checking_its_command_endpoint(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_CUSTOMATIC_CLARITY})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, gatt_client(CUSTOMATIC))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "customatic_family"
        assert choices(result)[-1] == "keep"
        result = await manager.async_configure(result["flow_id"], {"choice": "remedy"})
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        assert entry.data == before
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_CUSTOMATIC_REMEDY
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_z_series_change_is_refused_without_the_apps_roles(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_CUSTOMATIC_CLARITY})
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        # The Customatic command endpoint alone lacks the bedding app's notifications.
        bluetooth_patches(stack, gatt_client(CUSTOMATIC))
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "zseries_z230"})
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_check_failed"
        manager.async_abort(result["flow_id"])
    assert entry.data == before


async def test_serenity_entry_changes_to_tranquil_after_checking_its_roles(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_SERENITY})
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, gatt_client(BEDDING))
        result = await reconfigure(hass, entry)
        assert result["step_id"] == "jordans_family"
        result = await manager.async_configure(result["flow_id"], {"choice": "tranquil"})
        result = await finish_check(hass, result)
        assert result["step_id"] == "migration_confirm"
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_TRANQUIL


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_TRANQUIL})
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_sends_an_app_change_to_the_guided_change(hass):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_SERENITY})
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form(
        {const.CONF_BED_TYPE: const.BED_TYPE_TRANQUIL}, step_id="settings"
    )
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_SERENITY


async def test_configure_corrects_an_m5x4_entry_to_m5x5(hass):
    name = "STAR252201000001"
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_BLE_DEVICE_NAME: name,
        },
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    picker = next(
        validator
        for marker, validator in form["data_schema"].schema.items()
        if marker.schema == const.CONF_BED_TYPE
    )
    # The StarCode apps have no guided change, so Configure lists each by its label.
    shown = {option["label"] for option in picker.config["options"]}
    for app in (
        const.BED_TYPE_STARCODE_ABM5_4,
        const.BED_TYPE_STARCODE_M5X5,
        const.BED_TYPE_STARCODE_M1X12,
    ):
        assert bed_type_label(app) in shown
        assert picker(bed_type_label(app)) == app
    form = await flow._async_options_form(
        {const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_M5X5}, step_id="settings"
    )
    assert const.CONF_STARCODE_M5X5_PROFILE in {
        marker.schema for marker in form["data_schema"].schema
    }
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form(
            {const.CONF_STARCODE_M5X5_PROFILE: "cb25", const.CONF_BLE_DEVICE_NAME: name},
            step_id="settings",
        )
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_STARCODE_M5X5
    assert entry.data[const.CONF_STARCODE_M5X5_PROFILE] == "cb25"

