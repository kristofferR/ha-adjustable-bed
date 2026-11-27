"""One app question for Richmat beds: RMControl, the MH and classic apps, or a remote (#676)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.detection import bed_type_label, get_bed_type_options
from tests.form_helpers import finish_new_bed

ADDRESS = "11:22:33:44:55:66"
APPS = [
    "richmat_420",
    "atlas_lift",
    "jerome_adjustable_base",
    "rmcontrol",
    "luuna",
    "luniosmart",
    "sleep_evolution",
    "wsilver_legacy",
    "sonicsleep",
    "super_colchones",
    "mlily",
    "majestichome",
    "okimiki",
    "mlily_remote",
    "revive",
    "best_mattress",
    "blvd_home",
    "harmony",
    "idealbed",
    "ruf",
    "wsilver2",
    "americanstar",
    "bailey2",
    "tx",
    "nisco",
    "mlily_supreme",
    "bedtech_classic",
    "avocadoecobase",
    "coastersleep",
    "fortywinks",
    "milemont",
    "superior",
    "luunarise2",
    "powercool",
    "sleepfunction",
    "lp2",
    "bedsmart",
    "jerome2",
    "lady_americana",
    "acaa",
    "sta2",
    "zerogravity",
    "baseremote",
    "maxprime",
    "homezone",
    "dreamlab2",
    "enso2",
    "remote",
]


def setup_flow(hass, name: str = "BURM0001", **data) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    info = MagicMock()
    info.name = name
    flow._discovery_info = info
    # What the generic form collected for the Richmat row.
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT,
        const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO,
        const.CONF_MOTOR_COUNT: 3,
        **data,
    }
    return flow


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])


def fields(result) -> dict:
    return {str(marker): marker for marker in result["data_schema"].schema}


async def answer(flow, choice: str):
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        result = await flow.async_step_richmat_family({"choice": choice})
    return result, finish


async def test_generic_richmat_switch_requires_a_majestic_product(hass):
    flow = setup_flow(hass)
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "majestichome"})
        assert result["step_id"] == "profile_questions"
        assert const.CONF_PROTOCOL_VARIANT not in flow._manual_data
        schema = result["data_schema"]
        assert schema is not None
        with pytest.raises(vol.Invalid):
            schema({})
        answer = schema({const.CONF_PROTOCOL_VARIANT: "JGRN"})
        chosen = await flow.async_step_profile_questions(answer)
    assert chosen["type"] is FlowResultType.CREATE_ENTRY
    assert chosen["data"][const.CONF_BED_TYPE] == "majestichome"
    assert chosen["data"][const.CONF_PROTOCOL_VARIANT] == "JGRN"
    assert flow._manual_data[const.CONF_PROTOCOL_VARIANT] == "JGRN"


def test_every_app_has_a_searchable_row_and_the_family_row_stays_short():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    for app in ("RMControl", "SVEN & SON", "Richmat remotes"):
        assert app in rows[const.BED_TYPE_RICHMAT]
    assert len(rows[const.BED_TYPE_RICHMAT]) < 100
    # Each other app is found by its own name and selects its own route.
    assert rows[const.BED_TYPE_RICHMAT_REVIVE] == "Revive Control app"
    assert rows["richmat_classic_apps:fortywinks"] == "Forty Winks app"
    assert rows["richmat_classic_apps:sleepfunction"] == "SleepFunction Bed Control app"
    assert rows[const.BED_TYPE_MLILY] == "MLILY Control app"
    assert rows[const.BED_TYPE_JEROME_ADJUSTABLE_BASE] == "Jerome's Adjustable Base app"
    assert bed_type_label(const.BED_TYPE_RICHMAT_REVIVE) == "Revive Control app"


async def test_jerome_model_picker_requires_one_of_the_four_products(hass):
    flow = setup_flow(hass, "BED-Test")
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "jerome_adjustable_base"})
        assert result["step_id"] == "profile_questions"
        schema = result["data_schema"]
        assert schema is not None
        for unsupported in ("auto", "QRRM", "58"):
            with pytest.raises(vol.Invalid):
                schema({const.CONF_PROTOCOL_VARIANT: unsupported})
        chosen = await flow.async_step_profile_questions(
            schema({const.CONF_PROTOCOL_VARIANT: "JERN"})
        )
    assert chosen["type"] is FlowResultType.CREATE_ENTRY
    assert chosen["data"][const.CONF_BED_TYPE] == const.BED_TYPE_JEROME_ADJUSTABLE_BASE
    assert chosen["data"][const.CONF_PROTOCOL_VARIANT] == "JERN"


def test_configure_accepts_the_hidden_apps_by_id():
    selector = _bed_type_selector(const.BED_TYPE_RICHMAT, show_saved_id=True)
    for choice in (const.BED_TYPE_RICHMAT_REVIVE, "richmat_classic_apps:superior"):
        assert selector(choice) == choice


def test_configure_lists_each_mh_app_by_its_own_label():
    selector = _bed_type_selector(const.BED_TYPE_RICHMAT, show_saved_id=True)
    rows = selector.rows()
    for bed_type in const.RICHMAT_MH_BED_TYPES:
        # Each names its family, the Richmat question it is an answer of.
        label = f"{bed_type_label(bed_type).removesuffix(' (Richmat)')} · Richmat"
        assert rows[label] == bed_type
        assert selector(label) == bed_type


async def test_the_richmat_row_asks_the_app(hass):
    result = await setup_flow(hass).async_step_richmat_family()
    assert result["step_id"] == "richmat_family"
    assert sorted(choices(result)) == sorted(APPS)


async def test_rmcontrol_asks_its_product_and_side(hass):
    flow = setup_flow(hass)
    result, _finish = await answer(flow, "rmcontrol")
    assert result["step_id"] == "profile_questions"
    shown = fields(result)
    # The product has no default: the app's exact code is required.
    assert isinstance(shown[const.CONF_RMCONTROL_PRODUCT], vol.Required)
    assert flow._manual_data[const.CONF_RMCONTROL_PRODUCT] is None
    assert shown[const.CONF_RMCONTROL_SIDE].visible == {
        "field": const.CONF_RMCONTROL_PRODUCT,
        "operator": "exists",
    }
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions(
            {const.CONF_RMCONTROL_PRODUCT: "A3RM", const.CONF_RMCONTROL_SIDE: "right"}
        )
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_RMCONTROL_PRODUCT], saved[const.CONF_RMCONTROL_SIDE]) == (
        "A3RM",
        "right",
    )
    # The form's own settings stay.
    assert saved[const.CONF_MOTOR_COUNT] == 3


@pytest.mark.parametrize(
    ("name", "remote", "label"),
    [
        # A listed code the name carries is the default.
        ("BURM0001", "BURM", None),
        # An unlisted code is kept as detected.
        ("ZZRM0001", "zzrm", "ZZRM (detected code)"),
        ("Bed", const.RICHMAT_REMOTE_AUTO, None),
    ],
)
async def test_the_remote_asks_its_code_from_the_name(hass, name, remote, label):
    flow = setup_flow(hass, name)
    result, _finish = await answer(flow, "remote")
    shown = fields(result)
    assert shown[const.CONF_RICHMAT_REMOTE].default() == remote
    assert shown[const.CONF_RICHMAT_REMOTE].visible == {
        "field": const.CONF_RMCONTROL_PRODUCT,
        "operator": "not_exists",
    }
    if label is not None:
        assert (
            result["data_schema"].schema[shown[const.CONF_RICHMAT_REMOTE]].container[remote]
            == label
        )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_RMCONTROL_PRODUCT: ""})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_RICHMAT_REMOTE] == remote
    assert saved[const.CONF_RMCONTROL_PRODUCT] == ""


async def test_an_mh_app_asks_the_model_from_the_raw_name(hass):
    flow = setup_flow(hass, "QRRM0001")
    result, _finish = await answer(flow, "revive")
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_RICHMAT_REVIVE
    assert flow._manual_data[const.CONF_BLE_DEVICE_NAME] == "QRRM0001"
    assert const.CONF_RICHMAT_REMOTE not in flow._manual_data
    assert result["step_id"] == "profile_questions"
    # The app asks the model for a QRRM name, so Auto is refused.
    result = await flow.async_step_profile_questions(
        {const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO}
    )
    assert result["errors"] == {const.CONF_PROTOCOL_VARIANT: "richmat_mh_choose_model"}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "model_vorm"})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == "model_vorm"


@pytest.mark.parametrize(
    ("app", "bed_type", "model"),
    [
        ("ruf", "ruf_betten", "model_bqrm"),
        ("wsilver2", "wsilver_products", "model_6brm_mattress"),
        ("americanstar", "richmat_americanstar", "model_2i"),
        ("bailey2", "bailey_bed_control", "model_2i"),
        ("tx", "richmat_tx", "model_3i"),
    ],
)
async def test_a_ruf_richmat_app_asks_its_model(hass, app, bed_type, model):
    flow = setup_flow(hass, "QRRM0001")
    result, _finish = await answer(flow, app)
    assert flow._manual_data[const.CONF_BED_TYPE] == bed_type
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: model})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == model


async def test_a_classic_app_asks_its_layout(hass):
    flow = setup_flow(hass)
    result, _finish = await answer(flow, "fortywinks")
    assert (
        flow._manual_data[const.CONF_BED_TYPE],
        flow._manual_data[const.CONF_PROTOCOL_VARIANT],
    ) == (
        const.BED_TYPE_RICHMAT_CLASSIC_APPS,
        "fortywinks",
    )
    assert result["step_id"] == "profile_questions"
    assert const.CONF_PRODUCT_TYPE in fields(result)


async def test_an_app_picked_from_the_brand_list_already_answered(hass):
    flow = setup_flow(hass, "7IRM0001", **{const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_HARMONY})
    result = await flow.async_step_richmat_family()
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data[const.CONF_BLE_DEVICE_NAME] == "7IRM0001"


def entry_for(hass, **data) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Bed",
            const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT,
            const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO,
            const.CONF_MOTOR_COUNT: 2,
            **data,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def configure(hass, entry, user_input=None):
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    with patch.object(hass.config_entries, "async_schedule_reload"):
        return await flow.async_step_settings(user_input)


async def test_configure_opts_a_remote_entry_in_to_rmcontrol(hass):
    entry = entry_for(hass, **{const.CONF_RMCONTROL_PRODUCT: "", const.CONF_RICHMAT_REMOTE: "zzrm"})
    form = await configure(hass, entry)
    shown = fields(form)
    assert shown[const.CONF_RMCONTROL_PRODUCT].default() == ""
    # A saved code the list lacks stays this entry's choice.
    assert shown[const.CONF_RICHMAT_REMOTE].default() == "zzrm"
    result = await configure(
        hass, entry, {const.CONF_RMCONTROL_PRODUCT: "A0RM", const.CONF_RMCONTROL_SIDE: "both"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (entry.data[const.CONF_RMCONTROL_PRODUCT], entry.data[const.CONF_RMCONTROL_SIDE]) == (
        "A0RM",
        "both",
    )


async def test_configure_returns_an_rmcontrol_entry_to_the_remote(hass):
    entry = entry_for(
        hass, **{const.CONF_RMCONTROL_PRODUCT: "A0RM", const.CONF_RMCONTROL_SIDE: "left"}
    )
    form = await configure(hass, entry)
    assert fields(form)[const.CONF_RMCONTROL_PRODUCT].default() == "A0RM"
    result = await configure(hass, entry, {const.CONF_RMCONTROL_PRODUCT: ""})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_RMCONTROL_PRODUCT] == ""


async def test_each_receiver_of_a_pair_answers_for_itself(hass, enable_custom_integrations):
    from tests.test_paired_receiver_questions import child, pair_entry, receiver_form
    from tests.test_paired_receiver_questions import fields as receiver_fields

    remote = {const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT, const.CONF_RMCONTROL_PRODUCT: ""}
    revive = {
        const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT_REVIVE,
        const.CONF_PROTOCOL_VARIANT: "model_vorm",
        const.CONF_BLE_DEVICE_NAME: "VORM0001",
    }
    entry = pair_entry(hass, remote, revive)
    left = await receiver_form(hass, entry, "left")
    assert const.CONF_RMCONTROL_PRODUCT in receiver_fields(left)
    result = await hass.config_entries.options.async_configure(
        left["flow_id"],
        {
            **left["data_schema"]({}),
            const.CONF_RMCONTROL_PRODUCT: "A0RM",
            const.CONF_RMCONTROL_SIDE: "right",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert child(entry, "left")[const.CONF_RMCONTROL_SIDE] == "right"
    right = await receiver_form(hass, entry, "right")
    # The model picks the route, which changes in Reconfigure.
    assert const.CONF_PROTOCOL_VARIANT not in receiver_fields(right)
    hass.config_entries.options.async_abort(right["flow_id"])
    assert child(entry, "right")[const.CONF_PROTOCOL_VARIANT] == "model_vorm"


async def test_an_mh_app_from_the_app_question_reaches_its_model_question(
    hass, enable_custom_integrations
):
    """A typed address knows no name, so the app's question asks the model."""
    from homeassistant.config_entries import SOURCE_USER

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    flow._selected_bed_type = const.BED_TYPE_RICHMAT_REVIVE
    with patch("homeassistant.components.bluetooth.async_last_service_info", return_value=None):
        result = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
        assert result["step_id"] == "profile_questions"
        result = await flow.async_step_profile_questions(
            {const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO}
        )
        assert result["errors"] == {const.CONF_PROTOCOL_VARIANT: "richmat_mh_no_name"}
        with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
            await finish_new_bed(
                flow,
                await flow.async_step_profile_questions(
                    {const.CONF_PROTOCOL_VARIANT: "model_vorm"}
                ),
            )
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_RICHMAT_REVIVE,
        "model_vorm",
    )


async def test_luuna_asks_explicit_product_and_derives_its_controls(hass):
    flow = setup_flow(hass, "QRRM0001")
    result, _finish = await answer(flow, "luuna")
    assert result["step_id"] == "profile_questions"
    from tests.form_helpers import options_of

    shown = fields(result)

    choices = options_of(result["data_schema"].schema[shown[const.CONF_PROTOCOL_VARIANT]])
    assert set(choices) == {"rise", "risepro", "riseprolight"}

    assert flow._manual_data[const.CONF_BED_TYPE] == "luuna"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "riseprolight"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == "riseprolight"
    assert saved[const.CONF_MOTOR_COUNT] == 4
    assert saved[const.CONF_HAS_MASSAGE] is True
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(
    ("label", "route"),
    [
        ("Revive Control app · Richmat", const.BED_TYPE_RICHMAT_REVIVE),
        ("Forty Winks app · Richmat", const.BED_TYPE_RICHMAT_CLASSIC_APPS),
        ("BedSmart / X-Series app · Richmat", const.BED_TYPE_RICHMAT_CLASSIC_APPS),
        ("MLILY Control app · Richmat", const.BED_TYPE_MLILY),
        ("Majestic Home app · Richmat", "majestichome"),
        ("Atlas Lift app (Cama Lift) · Richmat", const.BED_TYPE_ATLAS_LIFT),
        ("MLILY Remote app · Richmat", const.BED_TYPE_MLILY_REMOTE),
    ],
)
async def test_an_app_found_by_its_own_row_skips_the_richmat_question(hass, label, route):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._app_after_device = "manual_entry"
    form = await flow.async_step_select_app()
    picker = next(value for key, value in form["data_schema"].schema.items() if key == const.CONF_BED_TYPE)
    assert label in picker.rows()
    result = await flow.async_step_select_app({const.CONF_BED_TYPE: label})
    assert result["step_id"] == "manual_entry"
    result = await flow.async_step_manual_entry({CONF_ADDRESS: "AA:BB:CC:DD:EE:36"})
    assert result["step_id"] != "richmat_family"
    assert flow._manual_data[const.CONF_BED_TYPE] == route


async def test_the_long_app_question_reads_alphabetically(hass):
    """Richmat's many apps are sorted by their shown name; Keep would stay last."""
    import json
    from pathlib import Path

    result = await setup_flow(hass).async_step_richmat_family()
    keys = result["data_schema"].schema["choice"].config["options"]
    labels = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
    )["selector"]["richmat_family_choice"]["options"]
    shown = [labels[key].casefold() for key in keys if key not in ("keep", "another")]
    assert shown == sorted(shown)
