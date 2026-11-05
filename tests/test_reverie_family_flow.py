"""Confirm the Reverie receiver from its advertised service (#676)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.actuator_groups import SINGLE_TYPE_GROUPS
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
    # What the generic form collected.
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: bed_type,
        const.CONF_PROTOCOL_VARIANT: const.VARIANT_AUTO,
        const.CONF_MOTOR_PULSE_COUNT: 37,
        const.CONF_MOTOR_PULSE_USER_SET: True,
    }
    return flow


def test_one_row_for_both_receivers_and_pairlink_keeps_its_own():
    rows = {option["value"]: option["label"] for option in get_bed_type_options()}
    label = rows[const.BED_TYPE_REVERIE_NIGHTSTAND]
    assert all(name in label for name in ("Nightstand", "Protocol 110", "Protocol 108"))
    assert const.BED_TYPE_REVERIE not in rows
    assert const.BED_TYPE_REVERIE_PAIRLINK in rows
    # The brand opens the same question instead of a try-this-first list.
    assert SINGLE_TYPE_GROUPS["reverie"] == const.BED_TYPE_REVERIE_NIGHTSTAND
    # A detected Protocol 108 bed shows the family row; a saved one keeps its label.
    shown = _bed_type_selector(const.BED_TYPE_REVERIE).shown(const.BED_TYPE_REVERIE)
    assert shown == label
    assert bed_type_label(const.BED_TYPE_REVERIE) == "Reverie (Protocol 108)"


@pytest.mark.parametrize(
    ("incoming", "service", "bed_type"),
    [
        (const.BED_TYPE_REVERIE, const.REVERIE_SERVICE_UUID, const.BED_TYPE_REVERIE),
        # The row chose nothing; the advertised service decides.
        (
            const.BED_TYPE_REVERIE_NIGHTSTAND,
            const.REVERIE_SERVICE_UUID,
            const.BED_TYPE_REVERIE,
        ),
        (
            const.BED_TYPE_REVERIE_NIGHTSTAND,
            const.REVERIE_NIGHTSTAND_SERVICE_UUID,
            const.BED_TYPE_REVERIE_NIGHTSTAND,
        ),
    ],
)
async def test_the_advertised_service_confirms_the_receiver_without_asking(
    hass, incoming, service, bed_type
):
    flow = setup_flow(hass, incoming, [service.upper()])
    result = await flow.async_step_reverie_family()
    # The model the app shows comes next.
    assert result["step_id"] == "profile_questions"
    assert const.CONF_PROTOCOL_VARIANT in {marker.schema for marker in result["data_schema"].schema}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "9T"})
    saved = finish.call_args.args[0]
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (bed_type, "9T")
    if bed_type == incoming:
        # Confirming the staged receiver keeps what the form collected.
        assert saved[const.CONF_MOTOR_PULSE_COUNT] == 37


async def test_an_unknown_service_is_asked_and_the_row_has_nothing_to_keep(hass):
    flow = setup_flow(hass, const.BED_TYPE_REVERIE_NIGHTSTAND, None)
    with patch(
        "homeassistant.components.bluetooth.async_last_service_info", return_value=None
    ):
        result = await flow.async_step_reverie_family()
        assert result["step_id"] == "reverie_family"
        options = result["data_schema"].schema["choice"].config["options"]
        assert options == ["protocol_110", "protocol_108"]
        result = await flow.async_step_reverie_family({"choice": "protocol_108"})
    assert result["step_id"] == "profile_questions"
    assert flow._manual_data is not None
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_REVERIE


def test_configure_lists_both_receivers_by_their_own_labels():
    picker = _bed_type_selector(const.BED_TYPE_REVERIE_NIGHTSTAND, show_saved_id=True)
    shown = {option["label"] for option in picker.config["options"]}
    for bed_type in (const.BED_TYPE_REVERIE, const.BED_TYPE_REVERIE_NIGHTSTAND):
        assert bed_type_label(bed_type) in shown
