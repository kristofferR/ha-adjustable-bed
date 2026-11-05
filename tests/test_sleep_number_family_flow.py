"""Confirm the Sleep Number transport from its advertised service (#676)."""

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


def setup_flow(hass, bed_type: str, services: list[str] | None) -> AdjustableBedConfigFlow:
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    if services is not None:
        info = MagicMock()
        info.service_uuids = services
        flow._discovery_info = info
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO,
    }
    return flow


def test_one_row_names_both_transports_and_their_models():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    label = rows[const.BED_TYPE_SLEEP_NUMBER]
    for name in ("SleepIQ", "Fuzion", "Climate 360", "BAM/MCR", "i8", "360 FlexFit 2"):
        assert name in label
    assert const.BED_TYPE_SLEEP_NUMBER_MCR not in rows
    # A detected BAM/MCR bed shows the family row; saved labels name their transport.
    shown = _bed_type_selector(const.BED_TYPE_SLEEP_NUMBER_MCR).shown(
        const.BED_TYPE_SLEEP_NUMBER_MCR
    )
    assert shown == label
    assert "BAM/MCR" in bed_type_label(const.BED_TYPE_SLEEP_NUMBER_MCR)
    assert "Fuzion" in bed_type_label(const.BED_TYPE_SLEEP_NUMBER)


async def test_a_fuzion_service_is_confirmed_and_asks_the_side(hass):
    flow = setup_flow(hass, const.BED_TYPE_SLEEP_NUMBER, [const.SLEEP_NUMBER_SERVICE_UUID])
    result = await flow.async_step_sleep_number_family()
    assert result["step_id"] == "profile_questions"
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pairing:
        await flow.async_step_profile_questions(
            {const.CONF_PROTOCOL_VARIANT: const.SLEEP_NUMBER_VARIANT_RIGHT}
        )
    # Fuzion keeps its pairing step.
    pairing.assert_awaited_once()
    assert flow._manual_data is not None
    assert flow._manual_data[const.CONF_PROTOCOL_VARIANT] == const.SLEEP_NUMBER_VARIANT_RIGHT


async def test_an_mcr_service_is_confirmed_and_asks_no_side(hass):
    flow = setup_flow(hass, const.BED_TYPE_SLEEP_NUMBER, [const.SLEEP_NUMBER_MCR_SERVICE_UUID])
    result = await flow.async_step_sleep_number_family()
    # Only whether to read its positions, which the row's form drew for Fuzion.
    assert [marker.schema for marker in result["data_schema"].schema] == [
        const.CONF_DISABLE_ANGLE_SENSING
    ]
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_DISABLE_ANGLE_SENSING: True})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_SLEEP_NUMBER_MCR
    assert const.CONF_PROTOCOL_VARIANT not in saved


@pytest.mark.parametrize(
    ("incoming", "options"),
    [
        # The row chose nothing to keep.
        (const.BED_TYPE_SLEEP_NUMBER, ["fuzion", "mcr"]),
        (const.BED_TYPE_SLEEP_NUMBER_MCR, ["fuzion", "mcr", "keep"]),
    ],
)
async def test_an_unknown_service_is_asked(hass, incoming, options):
    flow = setup_flow(hass, incoming, None)
    with patch(
        "homeassistant.components.bluetooth.async_last_service_info", return_value=None
    ):
        result = await flow.async_step_sleep_number_family()
    assert result["step_id"] == "sleep_number_family"
    assert result["data_schema"].schema["choice"].config["options"] == options


def test_configure_lists_both_transports_by_their_own_labels():
    picker = _bed_type_selector(const.BED_TYPE_SLEEP_NUMBER, show_saved_id=True)
    shown = {option["label"] for option in picker.config["options"]}
    for bed_type in (const.BED_TYPE_SLEEP_NUMBER, const.BED_TYPE_SLEEP_NUMBER_MCR):
        assert bed_type_label(bed_type) in shown
