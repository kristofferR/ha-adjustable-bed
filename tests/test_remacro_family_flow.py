"""One app question for Remacro beds: Slumberland, The Brick or Jerome's (#676)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _bed_type_selector,
)
from custom_components.adjustable_bed.detection import bed_type_label, get_bed_type_options

ADDRESS = "11:22:33:44:55:66"
_HISTORY = "homeassistant.components.bluetooth.async_last_service_info"


def setup_flow(hass, manufacturer_data: dict[int, bytes]) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    info = MagicMock()
    info.manufacturer_data = manufacturer_data
    flow._discovery_info = info
    # What the generic form collected for the Remacro row.
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: const.BED_TYPE_REMACRO,
        const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO,
        const.CONF_MOTOR_PULSE_COUNT: 37,
        const.CONF_MOTOR_PULSE_USER_SET: True,
    }
    return flow


def choices(result) -> list[str]:
    return list(result["data_schema"].schema["choice"].config["options"])


def test_one_row_names_the_three_store_apps():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    for app in ("Slumberland", "The Brick", "Jerome's"):
        assert app in rows[const.BED_TYPE_REMACRO]
    assert not {"remacro:the_brick", "remacro:jeromes"} & set(rows)
    # A saved entry keeps its own app's label.
    assert bed_type_label(const.BED_TYPE_REMACRO) == "Slumberland app (Remacro)"


@pytest.mark.parametrize(
    ("manufacturer_data", "model", "apps"),
    [
        ({}, "none seen yet", ["slumberland", "the_brick", "jeromes"]),
        ({50: b""}, "CS-B300M", ["slumberland", "the_brick", "jeromes"]),
        # Jerome's lists company IDs 45 to 53 only.
        ({54: b""}, "CS-B300M(ASI)", ["slumberland", "the_brick"]),
        # No app lists it, so every app runs the fallback controls.
        ({99: b""}, "company ID 99", ["slumberland", "the_brick", "jeromes"]),
    ],
)
async def test_the_question_offers_the_apps_that_list_the_model(
    hass, manufacturer_data, model, apps
):
    with patch(_HISTORY, return_value=None):
        result = await setup_flow(hass, manufacturer_data).async_step_remacro_family()
    assert result["description_placeholders"]["model"] == model
    assert choices(result) == apps


async def test_the_answer_sets_the_app_and_keeps_the_forms_settings(hass):
    flow = setup_flow(hass, {50: b""})
    with (
        patch(_HISTORY, return_value=None),
        patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish,
    ):
        await flow.async_step_remacro_family({"choice": "the_brick"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == const.REMACRO_VARIANT_THE_BRICK
    assert (saved[const.CONF_MOTOR_PULSE_COUNT], saved[const.CONF_MOTOR_PULSE_USER_SET]) == (
        37,
        True,
    )
    # The advertised model is remembered, as the generic form did.
    assert saved[const.CONF_REMACRO_MODEL] == 50


async def test_slumberland_keeps_the_automatic_route(hass):
    flow = setup_flow(hass, {50: b""})
    with (
        patch(_HISTORY, return_value=None),
        patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish,
    ):
        await flow.async_step_remacro_family({"choice": "slumberland"})
    assert finish.call_args.args[0][const.CONF_PROTOCOL_VARIANT] == const.VARIANT_AUTO


def test_configure_accepts_the_hidden_apps_a_repair_submits():
    selector = _bed_type_selector(const.BED_TYPE_REMACRO, show_saved_id=True)
    for choice in ("remacro:the_brick", "remacro:jeromes"):
        assert selector(choice) == choice
