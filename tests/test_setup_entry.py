"""The app-first new-bed journey (#676 direction A, screens A1 to A4 and A6)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from tests.form_helpers import select_options, suggested

PATCH_DISCOVERED = "custom_components.adjustable_bed.config_flow.get_discovered_service_info"
ADDRESS = "11:22:33:44:55:66"
_STRINGS = json.loads(
    (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
)


async def start(hass, devices=()):
    with patch(PATCH_DISCOVERED, return_value=list(devices)):
        return await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )


async def app_question(hass):
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "select_by_app"}
    )
    assert result["step_id"] == "select_app"
    return result


def app_rows(result) -> dict[str, str]:
    """The app question's rows, label to choice."""
    return result["data_schema"].schema[const.CONF_BED_TYPE].rows()


async def test_the_start_screen_offers_the_app_first_routes(hass, enable_custom_integrations):
    result = await start(hass)
    options = select_options(result, CONF_ADDRESS)
    assert list(options) == ["select_by_app", "scan", "manual", "diagnostic"]
    # Translated through the selector, never hard-coded English.
    marker = next(iter(result["data_schema"].schema))
    assert result["data_schema"].schema[marker].config["translation_key"] == "setup_start"
    labels = _STRINGS["selector"]["setup_start"]["options"]
    assert labels["select_by_app"] == "Set up by app or remote"
    assert labels["manual"] == "Pick any Bluetooth device"
    assert set(options) | {"pair_beds"} == set(labels)


async def test_a_discovered_bed_is_named_with_its_family(
    hass, enable_custom_integrations, mock_bluetooth_service_info
):
    result = await start(hass, [mock_bluetooth_service_info])
    label = select_options(result, CONF_ADDRESS)[mock_bluetooth_service_info.address]
    name = mock_bluetooth_service_info.name
    assert label == f"{name} ({mock_bluetooth_service_info.address}) · Linak"


@pytest.mark.parametrize(
    ("detected", "family"),
    [
        (const.BED_TYPE_OKIN_UUID, "Okin"),
        (const.BED_TYPE_MALOUF_NEW_OKIN, "Malouf / Lucid"),
        (const.BED_TYPE_SLEEPYS_BOX25, "Sleepy's Elite"),
        (const.BED_TYPE_OCTO, "OCTO Smart Control"),
    ],
)
def test_a_family_route_is_named_by_its_family_row(detected, family):
    from custom_components.adjustable_bed.config_flow import _family_name

    with patch(
        "custom_components.adjustable_bed.config_flow.detect_bed_type", return_value=detected
    ):
        assert _family_name(object()) == family  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "app", ["Sleep Harmony", "RMControl", "Power Bob", "Woosa", "Lucid Base", "Serenity", "HARMONY"]
)
async def test_the_app_question_finds_each_app_by_name(hass, enable_custom_integrations, app):
    result = await app_question(hass)
    assert any(app in label for label in app_rows(result))


async def test_the_app_question_ends_with_the_brand_list(hass, enable_custom_integrations):
    result = await app_question(hass)
    labels = list(app_rows(result))
    assert labels[-1] == _STRINGS["config"]["step"]["select_app"]["data"]["not_listed"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: labels[-1]}
    )
    assert result["step_id"] == "select_family"


async def _app_then_address(hass, choice: str):
    """Answer the app question, then type the address of a bed not in range."""
    result = await app_question(hass)
    label = next(label for label, row in app_rows(result).items() if row == choice)
    with patch(PATCH_DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_BED_TYPE: label}
        )
    # No Bluetooth device is in range, so the address is typed.
    assert result["step_id"] == "manual_entry"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})


@pytest.mark.parametrize(
    ("choice", "step"),
    [
        # An app row answers its family question.
        ("solace:woosa", "solace_woosa"),
        (const.BED_TYPE_SERENITY, None),
        # A family row asks it.
        (const.BED_TYPE_MALOUF_APP, "malouf_family"),
        (const.BED_TYPE_SVANE, "jensen_family"),
    ],
)
async def test_each_app_lands_in_its_familys_journey(
    hass, enable_custom_integrations, choice, step
):
    result = await _app_then_address(hass, choice)
    if step is None:
        # Jordan's family row is its first app, the Serenity app.
        assert result["step_id"] == "jordans_family"
    else:
        assert result["step_id"] == step


async def test_an_app_row_with_no_more_questions_finishes(hass, enable_custom_integrations):
    result = await _app_then_address(hass, "keeson:heal_every_night")
    assert result["step_id"] == "finish_settings"
    with (
        patch("homeassistant.config_entries.ConfigEntries.async_setup", new=AsyncMock(return_value=True)),
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Bed", const.CONF_DISCONNECT_AFTER_COMMAND: False}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert (result["data"][const.CONF_BED_TYPE], result["data"][const.CONF_PROTOCOL_VARIANT]) == (
        const.BED_TYPE_KEESON,
        const.KEESON_VARIANT_HEAL_EVERY_NIGHT,
    )


async def test_pick_any_bluetooth_device_asks_the_app_after_the_device(
    hass, enable_custom_integrations, mock_bluetooth_service_info_unknown
):
    device = mock_bluetooth_service_info_unknown
    result = await start(hass)
    with patch(PATCH_DISCOVERED, return_value=[device]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: device.address}
        )
    assert result["step_id"] == "select_app"
    # Nothing identifies an unknown device, so nothing is suggested.
    assert suggested(result, const.CONF_BED_TYPE) is None
    label = next(label for label, row in app_rows(result).items() if row == const.BED_TYPE_LINAK)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: label}
    )
    # Linak asks nothing more, so its final settings follow.
    assert result["step_id"] == "finish_settings"
    assert result["description_placeholders"]["address"] == device.address.upper()


async def test_typing_an_address_asks_the_app_first(
    hass, enable_custom_integrations, mock_bluetooth_service_info_unknown
):
    result = await start(hass)
    with patch(PATCH_DISCOVERED, return_value=[mock_bluetooth_service_info_unknown]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual_entry"}
        )
    assert result["step_id"] == "select_app"
    label = next(label for label, row in app_rows(result).items() if row == const.BED_TYPE_LINAK)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: label}
    )
    assert result["step_id"] == "manual_entry"
    assert {marker.schema for marker in result["data_schema"].schema} == {CONF_ADDRESS}


async def brand_list(hass):
    result = await app_question(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: "not_listed"}
    )
    assert result["step_id"] == "select_family"
    return result


async def test_the_brand_list_names_families_and_their_apps(hass, enable_custom_integrations):
    rows = app_rows(await brand_list(hass))
    choices = set(rows.values())
    # Family rows that ask their question, and brands without one.
    assert {
        const.BED_TYPE_FURNIMOVE,
        const.BED_TYPE_KEESON,
        const.BED_TYPE_MALOUF_APP,
        const.BED_TYPE_SVANE,
        const.BED_TYPE_LINAK,
    } <= choices
    # An app's own row stays in the app question's full list.
    assert "keeson:heal_every_night" not in choices
    # A protocol-named route is off the app question, so the brand list keeps it.
    from custom_components.adjustable_bed.detection import PROTOCOL_ROUTES

    assert choices >= PROTOCOL_ROUTES
    # Each family row names its brand first.
    okin = next(label for label, choice in rows.items() if choice == const.BED_TYPE_FURNIMOVE)
    assert okin.startswith("Okin: ")
    assert list(rows)[-1] == _STRINGS["config"]["step"]["select_family"]["data"]["not_sure"]


async def test_not_sure_runs_diagnostics(hass, enable_custom_integrations):
    result = await brand_list(hass)
    with patch(PATCH_DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_BED_TYPE: "not_sure"}
        )
    # With nothing in range, diagnostics asks for the address to browse.
    assert result["step_id"] == "diagnostic_manual"


async def test_a_brand_opens_its_familys_question(hass, enable_custom_integrations):
    result = await brand_list(hass)
    label = next(label for label, row in app_rows(result).items() if row == const.BED_TYPE_FURNIMOVE)
    with patch(PATCH_DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_BED_TYPE: label}
        )
    assert result["step_id"] == "manual_entry"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["step_id"] == "okin_family"


async def test_a_detected_route_survives_the_brand_list(
    hass, enable_custom_integrations, mock_bluetooth_service_info
):
    """A device picked first keeps its detected route under its family's row."""
    from unittest.mock import MagicMock

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    flow._discovery_info = mock_bluetooth_service_info
    flow._app_after_device = "device"
    with patch(
        "custom_components.adjustable_bed.config_flow.detect_bed_type_detailed",
        return_value=MagicMock(),
    ), patch(
        "custom_components.adjustable_bed.config_flow._confident_auto_detect",
        return_value=const.BED_TYPE_OKIN_UUID,
    ):
        result = await flow.async_step_select_family()
    assert const.BED_TYPE_OKIN_UUID in app_rows(result).values()
    assert const.BED_TYPE_FURNIMOVE not in app_rows(result).values()


async def discovered(hass, info):
    return await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )


async def test_a_discovered_bed_lists_its_own_rows_and_every_other_app(
    hass, enable_custom_integrations, mock_bluetooth_service_info
):
    """A3: a route with no family question offers its rows, then every app."""
    result = await discovered(hass, mock_bluetooth_service_info)
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"]["family"] == "Linak"
    options = select_options(result, const.CONF_BED_TYPE)
    assert list(options) == [const.BED_TYPE_LINAK, "another"]
    assert options["another"] == _STRINGS["config"]["step"]["bluetooth_confirm"]["data"]["another"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: "another"}
    )
    assert result["step_id"] == "select_app"
    # The device is known, so the chosen app's journey starts for it.
    label = next(label for label, row in app_rows(result).items() if row == "keeson:heal_every_night")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: label}
    )
    assert result["step_id"] == "finish_settings"
    assert result["description_placeholders"]["address"] == mock_bluetooth_service_info.address


async def test_a_discovered_family_asks_its_question_with_another_app_and_keep(
    hass, enable_custom_integrations, mock_bluetooth_service_info_okimat
):
    """A3: the detected family's question is the first one, never a guessed app."""
    result = await discovered(hass, mock_bluetooth_service_info_okimat)
    assert result["step_id"] == "okin_family"
    choices = list(select_options(result, "choice"))
    assert choices[-2:] == ["another", "keep"]
    for selector in ("okin_family_choice", "jensen_family_choice", "remacro_family_choice"):
        assert _STRINGS["selector"][selector]["options"]["another"]
    # Keep explains what it sets up; Back returns to the same question.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    assert result["step_id"] == "keep_detected"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "keep_back"}
    )
    assert result["step_id"] == "okin_family"
    assert list(select_options(result, "choice"))[-2:] == ["another", "keep"]
    # Keep saves the detected route, then its own questions and settings follow.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"choice": "keep"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "keep_continue"}
    )
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_OKIMAT
    assert result["step_id"] == "profile_questions"
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_another_app_restarts_the_journey_for_the_same_bed(
    hass, enable_custom_integrations, mock_bluetooth_service_info_okimat
):
    result = await discovered(hass, mock_bluetooth_service_info_okimat)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"choice": "another"}
    )
    assert result["step_id"] == "select_app"
    label = next(label for label, row in app_rows(result).items() if row == const.BED_TYPE_LINAK)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: label}
    )
    assert result["step_id"] == "finish_settings"
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_LINAK
    # The Okin question's own state is gone, so nothing of it is kept.
    assert "okin_family" not in flow._family_incoming
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_a_route_the_receiver_settles_is_confirmed_before_its_questions(
    hass, enable_custom_integrations, mock_bluetooth_service_info_reverie
):
    """A family that takes its route from the receiver asks nothing, so A3 confirms it."""
    result = await discovered(hass, mock_bluetooth_service_info_reverie)
    assert result["step_id"] == "bluetooth_confirm"
    route = suggested(result, const.CONF_BED_TYPE)
    assert "another" in select_options(result, const.CONF_BED_TYPE)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: route}
    )
    # Its own questions follow the confirmation.
    assert result["step_id"] == "profile_questions"
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_the_final_settings_come_after_the_apps_questions(hass, enable_custom_integrations):
    """A6: Restonic BT asks its remote style, then only the bed's own settings remain."""
    result = await _app_then_address(hass, "keeson:restonic_a")
    assert result["step_id"] == "keeson_restonic"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {const.CONF_PROTOCOL_VARIANT: const.KEESON_VARIANT_RESTONIC_B}
    )
    assert result["step_id"] == "finish_settings"
    top = {marker.schema for marker in result["data_schema"].schema}
    assert {CONF_NAME, const.CONF_PREFERRED_ADAPTER, const.CONF_DISCONNECT_AFTER_COMMAND} <= top
    # What the app sets is not asked, its route least of all; timing is
    # collapsed under Advanced connection and timing.
    from custom_components.adjustable_bed.app_profiles import hidden_generic_fields

    owned = hidden_generic_fields(const.BED_TYPE_KEESON, const.KEESON_VARIANT_RESTONIC_B)
    assert not (owned | {const.CONF_PROTOCOL_VARIANT, "advanced"}) & top
    timing = result["data_schema"].schema[
        next(marker for marker in result["data_schema"].schema if marker == "timing")
    ]
    assert timing.options == {"collapsed": True}
    assert {marker.schema for marker in timing.schema.schema} >= {
        const.CONF_MOTOR_PULSE_COUNT,
        const.CONF_IDLE_DISCONNECT_SECONDS,
    }
    sections = _STRINGS["config"]["step"]["finish_settings"]["sections"]
    assert sections["timing"]["name"] == "Advanced connection and timing"
    with (
        patch("homeassistant.config_entries.ConfigEntries.async_setup", new=AsyncMock(return_value=True)),
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Bedroom bed", "timing": {const.CONF_MOTOR_PULSE_COUNT: "7"}}
        )
    assert result["title"] == "Bedroom bed"
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == const.KEESON_VARIANT_RESTONIC_B
    assert result["data"][const.CONF_MOTOR_PULSE_COUNT] == 7
    assert result["data"][const.CONF_MOTOR_PULSE_USER_SET] is True


async def test_the_vibradorm_question_offers_another_app(hass, mock_bluetooth_service_info):
    """Vibradorm's question answers on its own field, and still searches every app."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    flow._disambiguated_bed_type = const.BED_TYPE_VIBRADORM
    result = await flow.async_step_bluetooth_confirm()
    assert result["step_id"] == "vibradorm"
    assert list(select_options(result, "app"))[-1] == "another"
    result = await flow.async_step_vibradorm({"app": "another"})
    assert result["step_id"] == "select_app"


@pytest.mark.parametrize("bed_type", sorted(const.VARIANT_REQUIRED_BED_TYPES))
async def test_a_bed_type_that_runs_only_as_an_app_offers_its_apps(
    hass, mock_bluetooth_service_info, bed_type
):
    """A discovered bed of such a type is never offered a route it cannot save."""
    from custom_components.adjustable_bed.config_flow import _default_setup_route
    from custom_components.adjustable_bed.detection import PRODUCT_QUESTION_BED_TYPES
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    # A row that asks its product starts on none; another starts on a saveable route.
    assert is_valid_variant_for_bed_type(bed_type, _default_setup_route(bed_type)) is (
        bed_type not in PRODUCT_QUESTION_BED_TYPES
    )
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    flow._disambiguated_bed_type = bed_type
    result = await flow.async_step_bluetooth_confirm()
    if result["step_id"] != "bluetooth_confirm":
        return  # Its family asks the question.
    marker = next(marker for marker in result["data_schema"].schema if marker == const.CONF_BED_TYPE)
    picker = result["data_schema"].schema[marker]
    choices = set(picker.rows().values()) if hasattr(picker, "rows") else {
        option["value"] for option in picker.config["options"]
    }
    if len(choices) > 2:
        # Its apps are its rows, and none is guessed.
        assert bed_type not in choices
        assert suggested(result, const.CONF_BED_TYPE) is None


async def test_untouched_timing_follows_a_route_chosen_under_advanced(hass):
    """The form is drawn for the staged route; another route takes its own timing."""
    from custom_components.adjustable_bed.const import get_motor_pulse_defaults
    from tests.form_helpers import form_answers

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._selected_bed_type = const.BED_TYPE_LINAK
    form = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
    answers = form_answers(form)
    answers["advanced"] = {const.CONF_PROTOCOL_VARIANT: const.LINAK_VARIANT_PERFORMANCE}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings(answers)
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_MOTOR_PULSE_COUNT], saved[const.CONF_MOTOR_PULSE_DELAY_MS]) == (
        get_motor_pulse_defaults(const.BED_TYPE_LINAK, const.LINAK_VARIANT_PERFORMANCE)
    )
    assert get_motor_pulse_defaults(const.BED_TYPE_LINAK, const.LINAK_VARIANT_PERFORMANCE) != (
        get_motor_pulse_defaults(const.BED_TYPE_LINAK, const.VARIANT_AUTO)
    )


@pytest.mark.parametrize(
    ("choice", "app"),
    [
        (const.BED_TYPE_MOTOMOTION, "MotoMotion"),
        (const.BED_TYPE_BEDJET_POWERLAYER, "BedJet PowerLayer"),
    ],
)
async def test_the_beds_from_main_are_in_the_app_question(
    hass, enable_custom_integrations, choice, app
):
    result = await app_question(hass)
    assert any(row == choice and app in label for label, row in app_rows(result).items())


async def test_motomotion_from_the_app_question_asks_its_exact_name(
    hass, enable_custom_integrations
):
    result = await _app_then_address(hass, const.BED_TYPE_MOTOMOTION)
    assert result["step_id"] == "profile_questions"
    assert const.CONF_BLE_DEVICE_NAME in {str(marker) for marker in result["data_schema"].schema}


async def test_bedjet_powerlayer_from_the_app_question_finishes(hass, enable_custom_integrations):
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_setup",
        new=AsyncMock(return_value=True),
    ):
        result = await _app_then_address(hass, const.BED_TYPE_BEDJET_POWERLAYER)
        assert result["step_id"] == "finish_settings"
        with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_NAME: "BedJet"}
            )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_BEDJET_POWERLAYER
