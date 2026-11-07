"""Every family question, driven from its declaration (``app_families.py``)."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_families import (
    APP_FAMILIES,
    REMOVED,
    AppFamily,
    Form,
    keep_always,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

ADDRESS = "11:22:33:44:55:66"
_STAGED = {"type": "staged"}


def _flow(hass, family: AppFamily) -> AdjustableBedConfigFlow:
    """A new bed staged on the family's row, as the row's setup stages it."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._manual_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: family.row,
        const.CONF_MOTOR_COUNT: 2,
    }
    # Stop where the route is staged: its questions, its own step or the finish.
    flow._async_finish_family_route = AsyncMock(return_value=_STAGED)  # type: ignore[method-assign]
    flow.async_step_profile_questions = AsyncMock(return_value=_STAGED)  # type: ignore[method-assign]
    return flow


def _offered(result: Any, family: AppFamily) -> list[str]:
    options = result["data_schema"].schema["choice"].config["options"]
    return [option if isinstance(option, str) else option["value"] for option in options]


@pytest.fixture(autouse=True)
def _no_advertisement():
    with patch(
        "homeassistant.components.bluetooth.async_last_service_info", return_value=None
    ):
        yield


@pytest.mark.parametrize("family", APP_FAMILIES, ids=lambda family: family.step)
async def test_each_family_row_asks_its_declared_answers(hass, family: AppFamily):
    flow = _flow(hass, family)
    result = await getattr(flow, f"async_step_{family.step}")()
    assert result["step_id"] == family.step
    # Only a family that always offers Keep offers it on the bare row.
    keep = ["keep"] if family.offers_keep is keep_always else []
    assert _offered(result, family) == [*family.answers, *keep]
    config = result["data_schema"].schema["choice"].config
    if family.form is Form.DROPDOWN:
        assert "translation_key" not in config
    else:
        assert config["translation_key"] == f"{family.step}_choice"


@pytest.mark.parametrize(
    ("family", "key"),
    [(family, key) for family in APP_FAMILIES for key in family.answers],
    ids=lambda value: value.step if isinstance(value, AppFamily) else value,
)
async def test_each_answer_stages_its_route_and_settings(hass, family: AppFamily, key: str):
    flow = _flow(hass, family)
    step = getattr(flow, f"async_step_{family.step}")
    await step()
    answer = family.answers[key]
    result = await step({"choice": key})
    if answer.step is not None:
        # A narrowing step asks first; each of its answers is a route of its own.
        assert result["step_id"] == answer.step
        return
    if answer.ask is not None:
        # The answer's own questions are asked on the generic step before the route is final.
        assert flow._asking is not None and flow._asking[0] is answer.ask
    else:
        assert result is _STAGED
    staged = flow._manual_data
    assert staged is not None
    assert staged[const.CONF_BED_TYPE] == answer.bed_type
    if answer.variant is not None:
        assert staged[const.CONF_PROTOCOL_VARIANT] == answer.variant
    for setting, value in answer.data.items():
        if value is REMOVED:
            assert setting not in staged
        else:
            assert staged[setting] == value
