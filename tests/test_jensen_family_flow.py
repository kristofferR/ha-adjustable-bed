"""One Jensen / Svane app-and-bed question, and guided changes between its routes (#676)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.actuator_groups import ACTUATOR_GROUPS
from custom_components.adjustable_bed.app_families import _jensen_suggestion
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.detection import bed_type_choice, get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from tests.test_sleepys_family_flow import entry_for, reconfigure

ADDRESS = "11:22:33:44:55:66"
ANSWERS = ["jensen_jmc400", "jensen_linon", "svane_bed", "svane_jmc400"]


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])


def suggested(result) -> str:
    return next(marker for marker in result["data_schema"].schema if marker == "choice").default()


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


def test_one_row_names_both_apps_and_their_beds():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    label = rows[const.BED_TYPE_SVANE]
    for name in ("Jensen Adjustable Sleep", "Svane Remote", "JMC400", "LinOn"):
        assert name in label
    # The JMC400 route and the two app profiles are answers, not rows.
    assert const.BED_TYPE_JENSEN not in rows
    for variant in (const.SVANE_VARIANT_JMC, const.SVANE_VARIANT_JENSEN_LINON):
        assert bed_type_choice(const.BED_TYPE_SVANE, variant) not in rows
    assert ACTUATOR_GROUPS["jensen"] == ((const.BED_TYPE_SVANE, None),)
    # LinON Entry is JMC400 hardware, so the JMC400 route no longer names it.
    from custom_components.adjustable_bed.detection import bed_type_label

    assert "LinON" not in bed_type_label(const.BED_TYPE_JENSEN)


def test_a_detected_jmc400_box_is_shown_as_the_family_row():
    label = _bed_type_selector(const.BED_TYPE_JENSEN).shown(const.BED_TYPE_JENSEN)
    assert label.endswith(" · Jensen / Svane")


@pytest.mark.parametrize(
    ("bed_type", "variant", "name", "answer"),
    [
        (const.BED_TYPE_JENSEN, const.VARIANT_AUTO, "JMC400", "jensen_jmc400"),
        (const.BED_TYPE_SVANE, const.VARIANT_AUTO, "Svane Bed", "svane_bed"),
        (const.BED_TYPE_SVANE, const.VARIANT_AUTO, "Jensen Bed", "jensen_linon"),
        (const.BED_TYPE_SVANE, const.VARIANT_AUTO, "Adjustable Bed", "jensen_linon"),
        (const.BED_TYPE_SVANE, const.VARIANT_AUTO, "JMC400", "svane_jmc400"),
        (const.BED_TYPE_SVANE, const.VARIANT_AUTO, "jmc400", "svane_bed"),
        (const.BED_TYPE_SVANE, const.VARIANT_AUTO, None, "svane_bed"),
        # A saved profile is its own suggestion, whatever the name says.
        (const.BED_TYPE_SVANE, const.SVANE_VARIANT_JMC, "Jensen Bed", "svane_jmc400"),
    ],
)
def test_the_apps_name_rules_suggest_the_answer(bed_type, variant, name, answer):
    assert _jensen_suggestion(bed_type, variant, name) == answer


async def test_a_new_bed_asks_both_apps_and_has_nothing_to_keep(hass):
    result = await setup_flow(hass, const.BED_TYPE_SVANE).async_step_jensen_family()
    assert choices(result) == ANSWERS


async def test_the_jmc400_route_asks_its_pin(hass):
    flow = setup_flow(hass, const.BED_TYPE_SVANE)
    result = await flow.async_step_jensen_family({"choice": "jensen_jmc400"})
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_JENSEN_PIN: "1234"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_JENSEN
    assert saved[const.CONF_JENSEN_PIN] == "1234"
    assert const.CONF_PROTOCOL_VARIANT not in saved


@pytest.mark.parametrize(
    ("answer", "variant"),
    [
        ("jensen_linon", const.SVANE_VARIANT_JENSEN_LINON),
        ("svane_bed", const.VARIANT_AUTO),
        ("svane_jmc400", const.SVANE_VARIANT_JMC),
    ],
)
async def test_each_svane_answer_saves_its_profile(hass, answer, variant):
    flow = setup_flow(hass, const.BED_TYPE_JENSEN)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        result = await flow.async_step_jensen_family({"choice": answer})
        if answer == "jensen_linon":
            # LinOn asks its motor count; the Svane Remote profiles set theirs.
            assert result["step_id"] == "profile_questions"
            await flow.async_step_profile_questions({const.CONF_MOTOR_COUNT: "3"})
    saved = finish.call_args.args[0]
    if answer == "jensen_linon":
        assert saved[const.CONF_MOTOR_COUNT] == 3
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_SVANE,
        variant,
    )


async def test_a_jmc400_entry_changes_to_the_svane_app(hass, enable_custom_integrations):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_JENSEN,
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_JENSEN_PIN: "1234",
        },
    )
    before = dict(entry.data)
    manager = hass.config_entries.flow
    result = await reconfigure(hass, entry)
    assert result["step_id"] == "jensen_family"
    assert choices(result)[-1] == "keep"
    assert suggested(result) == "jensen_jmc400"
    result = await manager.async_configure(result["flow_id"], {"choice": "svane_jmc400"})
    assert result["step_id"] == "migration_confirm"
    assert entry.data == before
    result = await manager.async_configure(result["flow_id"], {"action": "apply"})
    assert result["reason"] == "migration_applied"
    assert (entry.data[const.CONF_BED_TYPE], entry.data[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_SVANE,
        const.SVANE_VARIANT_JMC,
    )
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)


async def test_keep_in_a_guided_change_leaves_the_entry_unchanged(hass, enable_custom_integrations):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_SVANE,
            const.CONF_PROTOCOL_VARIANT: const.SVANE_VARIANT_JENSEN_LINON,
        },
    )
    before = dict(entry.data)
    result = await reconfigure(hass, entry)
    assert suggested(result) == "jensen_linon"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["reason"] == "migration_kept"
    assert {k: v for k, v in entry.data.items() if k in before} == before


async def test_configure_keeps_the_jmc400_pin(hass):
    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: const.BED_TYPE_JENSEN,
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_JENSEN_PIN: "1234",
        },
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    defaults = {marker.schema: marker.default() for marker in form["data_schema"].schema}
    assert defaults[const.CONF_JENSEN_PIN] == "1234"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form({const.CONF_JENSEN_PIN: "5678"}, step_id="settings")
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_JENSEN_PIN] == "5678"


async def test_a_jmc400_pair_asks_each_pin_on_its_own_step(hass, enable_custom_integrations):
    from tests.test_paired_receiver_questions import child, fields, pair_entry, receiver_form

    jensen = {const.CONF_BED_TYPE: const.BED_TYPE_JENSEN, const.CONF_MOTOR_COUNT: 2}
    entry = pair_entry(
        hass, {**jensen, const.CONF_JENSEN_PIN: "1111"}, {**jensen, const.CONF_JENSEN_PIN: "2222"}
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    shared = await flow._async_options_form(None, step_id="settings")
    assert const.CONF_JENSEN_PIN not in {marker.schema for marker in shared["data_schema"].schema}
    right = await receiver_form(hass, entry, "right")
    assert fields(right)[const.CONF_JENSEN_PIN].default() == "2222"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await hass.config_entries.options.async_configure(
            right["flow_id"], {**right["data_schema"]({}), const.CONF_JENSEN_PIN: "3333"}
        )
    assert child(entry, "right")[const.CONF_JENSEN_PIN] == "3333"
    assert child(entry, "left")[const.CONF_JENSEN_PIN] == "1111"


async def test_an_unnamed_advertisement_leaves_the_stored_name_to_suggest(hass):
    from types import SimpleNamespace

    flow = setup_flow(hass, const.BED_TYPE_SVANE)
    flow._manual_data[const.CONF_BLE_DEVICE_NAME] = "Jensen Bed"
    with patch(
        "custom_components.adjustable_bed.config_flow.bluetooth.async_last_service_info",
        return_value=SimpleNamespace(name=ADDRESS),
    ):
        result = await flow.async_step_jensen_family()
    assert suggested(result) == "jensen_linon"


async def test_configure_can_switch_another_bed_type_to_the_jmc400_route(hass):
    entry = entry_for(hass, {const.CONF_BED_TYPE: const.BED_TYPE_LINAK, const.CONF_MOTOR_COUNT: 2})
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    picker = form["data_schema"].schema[
        next(marker for marker in form["data_schema"].schema if marker == const.CONF_BED_TYPE)
    ]
    assert const.BED_TYPE_JENSEN in set(picker.rows().values())
    form = await flow._async_options_form(
        {const.CONF_BED_TYPE: const.BED_TYPE_JENSEN}, step_id="settings"
    )
    assert const.CONF_JENSEN_PIN in {marker.schema for marker in form["data_schema"].schema}
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form({const.CONF_JENSEN_PIN: "1234"}, step_id="settings")
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_JENSEN
    assert entry.data[const.CONF_JENSEN_PIN] == "1234"
