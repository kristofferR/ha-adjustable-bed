"""The bed-type list's rows: family labels, protocol routes and product questions (#676)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    _APP_QUESTION_STEPS,
    _APP_SETUP_STEPS,
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
    _family_rows,
)
from custom_components.adjustable_bed.detection import (
    FAMILY_ROWS,
    PROTOCOL_ROUTES,
    bed_type_label,
    get_bed_type_options,
    resolve_bed_type_choice,
)
from tests.form_helpers import form_fields, start_new_bed, suggested
from tests.test_sleepys_family_flow import entry_for

ADDRESS = "11:22:33:44:55:66"


def test_every_family_question_has_one_family_row():
    steps = [_APP_SETUP_STEPS[bed_type] for bed_type in FAMILY_ROWS]
    assert len(steps) == len(set(steps))
    assert set(steps) == _APP_QUESTION_STEPS


@pytest.mark.parametrize("show_saved_id", [False, True], ids=["setup", "configure"])
def test_a_rows_family_is_the_family_its_journey_asks(show_saved_id):
    """Each row of a family's journey reads "<app> · <family>"; other rows name themselves.

    Configure lists more rows by name, such as the Richmat apps, and they follow
    the same rule.
    """
    from custom_components.adjustable_bed.config_flow import _ANSWER_STEPS

    names = {_APP_SETUP_STEPS[bed_type]: family for bed_type, (family, _apps) in FAMILY_ROWS.items()}
    rows = _bed_type_selector(const.BED_TYPE_LINAK, show_saved_id=show_saved_id).rows()
    for label, choice in rows.items():
        bed_type, variant = resolve_bed_type_choice(choice)
        step = _ANSWER_STEPS.get((bed_type, variant)) or _APP_SETUP_STEPS.get(bed_type, "")
        family = names.get(step)
        if family is None:
            assert " · " not in label, label
        else:
            app, separator, named = label.rpartition(" · ")
            assert separator and named == family, label
            # The family is named once, never again inside the app part.
            assert not app.endswith(f"({family})"), label
    assert rows["Heal Every Night app · Keeson"] == "keeson:heal_every_night"
    assert rows["Woosa Sleep app · Solace"] == "solace:woosa"
    if show_saved_id:
        assert rows["Revive Control app · Richmat"] == const.BED_TYPE_RICHMAT_REVIVE


def test_the_brand_list_names_a_detected_routes_family_first():
    """A detected route takes its family row's value, and the row still reads brand first."""
    rows = dict(_family_rows(const.BED_TYPE_OKIN_UUID))
    assert rows[const.BED_TYPE_OKIN_UUID].startswith("Okin: ")
    assert const.BED_TYPE_FURNIMOVE not in rows


def test_protocol_routes_are_off_the_list_but_reachable():
    listed = {option["value"] for option in get_bed_type_options()}
    assert not PROTOCOL_ROUTES & listed
    assert {choice for choice, _label in _family_rows()} >= PROTOCOL_ROUTES
    configure = _bed_type_selector(const.BED_TYPE_LINAK, show_saved_id=True)
    assert set(configure.rows().values()) >= PROTOCOL_ROUTES
    # A detected protocol route is still its own row on a discovered bed's list.
    assert const.BED_TYPE_OKIN_HANDLE in _bed_type_selector(const.BED_TYPE_OKIN_HANDLE).rows().values()


async def test_the_good_vibe_row_asks_its_product_searchably(hass, mock_bluetooth_service_info):
    """One row, then a searchable product question the app's name rule suggests."""
    from custom_components.adjustable_bed.const import GOODVIBE_PROFILES

    rows = {option["value"] for option in get_bed_type_options()}
    assert const.BED_TYPE_GOODVIBE in rows
    assert sum(resolve_bed_type_choice(row)[0] == const.BED_TYPE_GOODVIBE for row in rows) == 1
    mock_bluetooth_service_info.name = "6BRM-1234"
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    result = await start_new_bed(flow, "picked", const.BED_TYPE_GOODVIBE)
    assert result["step_id"] == "profile_questions"
    marker = next(m for m in result["data_schema"].schema if m == const.CONF_PROTOCOL_VARIANT)
    picker = result["data_schema"].schema[marker]
    assert hasattr(picker, "rows") and len(picker.rows()) == len(GOODVIBE_PROFILES)
    # The suggestion is a default the user confirms, shown by its label.
    assert marker.default() == GOODVIBE_PROFILES["selector-0001"]
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "6CRM"})
    assert result["step_id"] == "finish_settings"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings({CONF_NAME: "Bed"})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_GOODVIBE,
        "selector-0002",
    )


async def test_a_typed_hjbed_guesses_no_product(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    result = await start_new_bed(flow, "typed", const.BED_TYPE_HJBED, ADDRESS)
    assert result["step_id"] == "profile_questions"
    # No name to suggest from, so nothing is preselected.
    assert suggested(result, const.CONF_PROTOCOL_VARIANT) is None
    fields = {m.schema for m in form_fields(result["data_schema"])}
    assert fields == {const.CONF_PROTOCOL_VARIANT}


async def test_configure_keeps_a_saved_good_vibe_product(hass):
    entry = entry_for(
        hass,
        {
            CONF_ADDRESS: ADDRESS,
            const.CONF_BED_TYPE: const.BED_TYPE_GOODVIBE,
            const.CONF_PROTOCOL_VARIANT: "selector-0002",
        },
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    marker = next(m for m in form["data_schema"].schema if m == const.CONF_PROTOCOL_VARIANT)
    assert marker.default() == "6CRM"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow._async_options_form({}, step_id="settings")
    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_PROTOCOL_VARIANT] == "selector-0002"
    assert "Good Vibe" in bed_type_label(const.BED_TYPE_GOODVIBE)


@pytest.mark.parametrize(
    ("bed_type", "variant"),
    [(const.BED_TYPE_CASPER_BASE, "caspermax"), (const.BED_TYPE_COMFORT_ENHANCEMENTS, "mc3")],
)
async def test_an_app_whose_route_is_its_product_is_reachable_from_the_app_list(
    hass, bed_type, variant
):
    """Its row is in the app list, and the app's product or layout is asked next."""
    from custom_components.adjustable_bed.validators import get_variants_for_bed_type

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    result = await flow.async_step_select_app()
    assert bed_type in result["data_schema"].schema[const.CONF_BED_TYPE].rows().values()
    result = await start_new_bed(flow, "typed", bed_type, ADDRESS)
    assert result["step_id"] == "profile_questions"
    assert {m.schema for m in form_fields(result["data_schema"])} == {const.CONF_PROTOCOL_VARIANT}
    # Nothing is guessed.
    assert suggested(result, const.CONF_PROTOCOL_VARIANT) is None
    marker = next(m for m in result["data_schema"].schema if m == const.CONF_PROTOCOL_VARIANT)
    picker = result["data_schema"].schema[marker]
    label = get_variants_for_bed_type(bed_type)[variant]
    result = await flow.async_step_profile_questions(
        {const.CONF_PROTOCOL_VARIANT: label if hasattr(picker, "rows") else variant}
    )
    assert result["step_id"] == "finish_settings"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings({CONF_NAME: "Bed"})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (bed_type, variant)
    if variant == "mc3":
        # The answered layout's own profile settles what it owns: MC3 has no massage.
        assert saved[const.CONF_HAS_MASSAGE] is False
