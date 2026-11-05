"""The app-first start screen and app question (#676 direction A, screens A1 and A2)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
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
    """Answer the app question, then enter an address with the form's defaults."""
    result = await app_question(hass)
    label = next(label for label, row in app_rows(result).items() if row == choice)
    with patch(PATCH_DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {const.CONF_BED_TYPE: label}
        )
    # No Bluetooth device is in range, so the address is typed.
    assert result["step_id"] == "manual_entry"
    assert suggested(result, const.CONF_BED_TYPE) == label
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        return await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ADDRESS: ADDRESS,
                const.CONF_BED_TYPE: label,
                CONF_NAME: "Bed",
                const.CONF_DISCONNECT_AFTER_COMMAND: False,
            },
        )


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
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_setup",
        new=AsyncMock(return_value=True),
    ):
        result = await _app_then_address(hass, "keeson:heal_every_night")
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
    assert result["step_id"] == "manual_config"
    assert suggested(result, const.CONF_BED_TYPE) == label


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
    assert suggested(result, const.CONF_BED_TYPE) == label


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
    # An app's own row and a protocol row stay in the app question's full list.
    assert "keeson:heal_every_night" not in choices
    assert const.BED_TYPE_OKIN_HANDLE not in choices
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
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ADDRESS: ADDRESS,
                const.CONF_BED_TYPE: label,
                CONF_NAME: "Bed",
                const.CONF_DISCONNECT_AFTER_COMMAND: False,
            },
        )
    assert result["step_id"] == "okin_family"


async def test_a_detected_route_survives_the_brand_list(
    hass, enable_custom_integrations, mock_bluetooth_service_info
):
    """A device picked first keeps its detected route under its family's row."""
    from unittest.mock import MagicMock

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    flow._discovery_info = mock_bluetooth_service_info
    flow._app_after_device = "manual_config"
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
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_BED_TYPE] == const.BED_TYPE_BEDJET_POWERLAYER
