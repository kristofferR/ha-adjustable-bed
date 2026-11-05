"""The guided change's check, review, failure and applied screens, and Keep on a new bed (#676)."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profile_migration import ControlChanges, async_control_changes
from custom_components.adjustable_bed.profile_review import route_label
from tests.test_limoss_family_flow import entry_for, limoss_client
from tests.test_okin_family_flow import entry_for as okin_entry_for
from tests.test_okin_family_flow import okin_client, setup_flow
from tests.test_sleepys_family_flow import reconfigure
from tests.test_vibradorm_family_flow import bluetooth_patches

GENERIC = {const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS, const.CONF_MOTOR_COUNT: 2}
REMOTE = route_label({const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS_REMOTE})


async def stage_remote(hass, entry):
    """Choose Limoss Remote in Reconfigure and return its running check."""
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    result = await manager.async_configure(result["flow_id"], {"choice": "limoss_remote"})
    return await manager.async_configure(result["flow_id"], {const.CONF_PRODUCT_TYPE: "bed"})


async def test_a_passed_check_goes_to_the_review_and_ends_on_the_applied_screen(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, GENERIC)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, limoss_client("write", "notify"))
        result = await stage_remote(hass, entry)
        # The checklist names the staged route; nothing is saved yet.
        assert result["type"] == FlowResultType.SHOW_PROGRESS
        assert result["step_id"] == "migration_check"
        assert result["description_placeholders"]["selection"] == REMOTE
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["step_id"] == "migration_confirm"
        assert result["data_schema"].schema["action"].config["options"] == ["apply", "keep"]
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert result["description_placeholders"] == {
        "name": "Bedroom",
        "selection": REMOTE,
        "current": route_label(GENERIC),
    }
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LIMOSS_REMOTE


async def test_a_failed_check_changes_nothing_and_offers_try_again_or_keep(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, GENERIC)
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        connect = bluetooth_patches(stack, limoss_client("write"))
        result = await stage_remote(hass, entry)
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["step_id"] == "migration_check_failed"
        assert result["data_schema"].schema["action"].config["options"] == ["retry", "keep"]
        assert (
            f"**Bedroom** works with **{REMOTE}**" in result["description_placeholders"]["detail"]
        )
        assert entry.data == before

        # Try again checks the bed again: now it offers what the app needs.
        connect.return_value = limoss_client("write", "notify")
        result = await manager.async_configure(result["flow_id"], {"action": "retry"})
        assert result["step_id"] == "migration_check"
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["step_id"] == "migration_confirm"
        manager.async_abort(result["flow_id"])

        connect.return_value = limoss_client("write")
        result = await stage_remote(hass, entry)
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        result = await manager.async_configure(result["flow_id"], {"action": "keep"})
    assert result["reason"] == "migration_kept"
    assert {key: entry.data[key] for key in before} == before


async def test_a_failed_pairing_check_changes_nothing_and_keep_keeps_the_setup(
    hass, enable_custom_integrations
):
    entry = okin_entry_for(
        hass, {const.CONF_BED_TYPE: const.BED_TYPE_OKIMAT, const.CONF_MOTOR_COUNT: 2}
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    with ExitStack() as stack:
        # The link lacks the route's command endpoint, so the bonded check fails.
        bluetooth_patches(stack, okin_client())
        result = await reconfigure(hass, entry)
        result = await manager.async_configure(result["flow_id"], {"choice": "okin_uuid"})
        result = await manager.async_configure(
            result["flow_id"], {const.CONF_PROTOCOL_VARIANT: "62612", const.CONF_MOTOR_COUNT: 2}
        )
        assert result["step_id"] == "manual_pairing"
        result = await manager.async_configure(result["flow_id"], {"action": "pair_now"})
        # The pairing check has the guided change's own checklist.
        assert result["step_id"] == "migration_pairing"
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["step_id"] == "migration_check_failed"
        result = await manager.async_configure(result["flow_id"], {"action": "keep"})
    assert result["reason"] == "migration_kept"
    assert {key: entry.data[key] for key in before} == before


async def test_the_review_lists_reinterpreted_controls_and_keep_is_an_equal_answer(
    hass, enable_custom_integrations
):
    entry = entry_for(hass, GENERIC)
    before = dict(entry.data)
    manager = hass.config_entries.flow
    changes = ControlChanges(added=("Light",), reinterpreted=(("Memory 1", "Flat"),), unchanged=3)
    with (
        ExitStack() as stack,
        patch(
            "custom_components.adjustable_bed.config_flow.async_control_changes",
            new=AsyncMock(return_value=changes),
        ),
    ):
        bluetooth_patches(stack, limoss_client("write", "notify"))
        result = await stage_remote(hass, entry)
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        summary = result["description_placeholders"]["summary"]
        assert "**Changes meaning:**\n- Memory 1 becomes Flat" in summary
        assert "**Unchanged:** 3 controls" in summary
        result = await manager.async_configure(result["flow_id"], {"action": "keep"})
    assert result["reason"] == "migration_kept"
    assert {key: entry.data[key] for key in before} == before


async def test_a_kept_entity_with_another_name_is_reinterpreted(hass):
    entry = entry_for(hass, GENERIC)
    current = {
        "a_flat": ("button", "Memory 1"),
        "a_back": ("cover", "Back"),
        "a_massage": ("switch", "Massage"),
    }
    target = {
        "a_flat": ("button", "Flat"),
        "a_back": ("cover", "Back"),
        "a_light": ("light", "Light"),
    }
    prefix = "custom_components.adjustable_bed.profile_migration."
    with (
        patch(prefix + "_async_preview_labels", new=AsyncMock(return_value=target)),
        patch(prefix + "_async_current_labels", new=AsyncMock(return_value=current)),
    ):
        changes = await async_control_changes(hass, entry, dict(entry.data))
    assert changes.added == ("Light",)
    assert changes.removed == ("Massage",)
    assert changes.reinterpreted == (("Memory 1", "Flat"),)
    assert changes.unchanged == 1


async def test_keep_on_a_new_bed_explains_its_controls_and_can_go_back(hass):
    flow = setup_flow(hass, const.BED_TYPE_OKIN_UUID)
    result = await flow.async_step_okin_family({"choice": "keep"})
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "keep_detected"
    assert result["menu_options"] == ["keep_back", "keep_continue"]
    # The Okin UUID route pairs, so the screen says so.
    assert result["description_placeholders"]["pairing"] == " It requires Bluetooth pairing."

    result = await flow.async_step_keep_back()
    assert result["step_id"] == "okin_family"
    result = await flow.async_step_okin_family({"choice": "keep"})
    result = await flow.async_step_keep_continue()
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data is not None
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_OKIN_UUID


async def test_keep_on_a_new_bed_without_pairing_says_nothing_about_it(hass):
    flow = setup_flow(hass, const.BED_TYPE_KEESON)
    result = await flow.async_step_keeson_family({"choice": "keep"})
    assert result["step_id"] == "keep_detected"
    assert result["description_placeholders"]["pairing"] == ""
