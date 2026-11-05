"""Each receiver of a two-address pair answers its own profile's questions (#779)."""

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.pairing import build_pair_entry_data, get_child

LEFT = "11:22:33:44:55:66"
RIGHT = "11:22:33:44:55:77"


def pair_entry(hass, left: dict, right: dict) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data=build_pair_entry_data(
            {CONF_ADDRESS: LEFT, CONF_NAME: "Left", **left},
            {CONF_ADDRESS: RIGHT, CONF_NAME: "Right", **right},
            name="Pair",
        ),
    )
    entry.add_to_hass(hass)
    return entry


async def receiver_form(hass, entry, side: str):
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": f"{side}_settings"}
    )
    assert form["step_id"] == f"{side}_settings"
    return form


def fields(form) -> dict:
    return {str(marker): marker for marker in form["data_schema"].schema}


def child(entry, side: str) -> dict:
    return dict(get_child(entry.data, side) or {})


async def test_a_mixed_pair_asks_each_receiver_its_own_profile(hass, enable_custom_integrations):
    entry = pair_entry(
        hass,
        {const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX15, const.CONF_MOTOR_COUNT: 2},
        {const.CONF_BED_TYPE: const.BED_TYPE_LINAK, const.CONF_MOTOR_COUNT: 2},
    )
    right = await receiver_form(hass, entry, "right")
    assert const.CONF_MOTOR_COUNT not in fields(right)
    hass.config_entries.options.async_abort(right["flow_id"])

    left = await receiver_form(hass, entry, "left")
    assert fields(left)[const.CONF_MOTOR_COUNT].default() == 2
    result = await hass.config_entries.options.async_configure(
        left["flow_id"], {**left["data_schema"]({}), const.CONF_MOTOR_COUNT: 3}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert child(entry, "left")[const.CONF_MOTOR_COUNT] == 3
    assert child(entry, "right")[const.CONF_MOTOR_COUNT] == 2


async def test_a_same_family_pair_keeps_each_receivers_answers(hass, enable_custom_integrations):
    box25 = {const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX25, const.CONF_HAS_MASSAGE: False}
    entry = pair_entry(hass, box25, {**box25, const.CONF_HAS_MASSAGE: True})
    left = await receiver_form(hass, entry, "left")
    # Each receiver's form shows its own saved answer.
    assert fields(left)[const.CONF_HAS_MASSAGE].default() is False
    result = await hass.config_entries.options.async_configure(
        left["flow_id"], {**left["data_schema"]({}), const.CONF_HAS_MASSAGE: True}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    right = await receiver_form(hass, entry, "right")
    assert fields(right)[const.CONF_HAS_MASSAGE].default() is True
    result = await hass.config_entries.options.async_configure(
        right["flow_id"], {**right["data_schema"]({}), const.CONF_HAS_MASSAGE: False}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert child(entry, "left")[const.CONF_HAS_MASSAGE] is True
    assert child(entry, "right")[const.CONF_HAS_MASSAGE] is False


async def test_a_conditional_question_is_a_native_conditional_field(
    hass, enable_custom_integrations
):
    caresse = {
        const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "caresse",
        const.CONF_VIBRADORM_CONTROL_TYPE: "2",
        const.CONF_VIBRADORM_RESTORED: False,
    }
    entry = pair_entry(hass, caresse, caresse)
    left = fields(await receiver_form(hass, entry, "left"))
    assert left[const.CONF_VIBRADORM_RESTORED].visible is None
    assert left[const.CONF_VIBRADORM_FLOOR_LIGHT].visible is not None


def test_every_declared_question_has_a_receiver_label():
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES

    keys = {question.key for profile in SETUP_PROFILES.values() for question in profile.questions}
    for path in ("strings.json", "translations/en.json"):
        steps = json.loads((Path("custom_components/adjustable_bed") / path).read_text())
        for side in ("left_settings", "right_settings"):
            assert keys <= set(steps["options"]["step"][side]["data"]), (path, side)


ISLEEP = {
    const.CONF_BED_TYPE: const.BED_TYPE_ISLEEP,
    const.CONF_PRODUCT_TYPE: 129,
    const.CONF_KAIDI_ROOM_ID: 10000,
    const.CONF_KAIDI_SOFA_ACU_NO: 2,
}
OUT_OF_RANGE_ROOM = 2**31


async def test_a_receiver_rejects_an_out_of_range_room(hass, enable_custom_integrations):
    import pytest
    from homeassistant.data_entry_flow import InvalidData

    entry = pair_entry(hass, ISLEEP, ISLEEP)
    left = await receiver_form(hass, entry, "left")
    with pytest.raises(InvalidData) as error:
        await hass.config_entries.options.async_configure(
            left["flow_id"],
            {**left["data_schema"]({}), const.CONF_KAIDI_ROOM_ID: OUT_OF_RANGE_ROOM},
        )
    assert const.CONF_KAIDI_ROOM_ID in error.value.schema_errors
    assert child(entry, "left")[const.CONF_KAIDI_ROOM_ID] == 10000


async def test_a_receiver_shows_a_failed_check_without_settling_it(
    hass, enable_custom_integrations
):
    """An answer the form did not check still gets the profile's error, not a crash."""
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow

    entry = pair_entry(hass, ISLEEP, ISLEEP)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow.async_step_left_settings({const.CONF_KAIDI_ROOM_ID: OUT_OF_RANGE_ROOM})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "isleep_profile"}
    assert child(entry, "left")[const.CONF_KAIDI_ROOM_ID] == 10000
