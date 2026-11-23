"""Finite GM Control direct BLE operations with all-target admission."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, get_args

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from ...errors import rejected
from .requests import GmmotorActions, Operation, Request

if TYPE_CHECKING:
    from homeassistant.helpers.typing import VolSchemaType

# The bed clock belongs to the shared Set bed clock action.
OPERATIONS = tuple(op for op in get_args(Operation.__value__) if op != "clock_sync")
# A sleep report's side and period, sent as 1 and 2 in this order.
_REPORT_SIDES = ("left", "right")
_REPORT_PERIODS = ("day", "month")


def _integer(value: object) -> int:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    if type(value) is not int:
        raise vol.Invalid("Expected an integer")
    return value


async def handle(call: ServiceCall) -> None:
    from ...services import _call_targets, _preflight_and_execute

    data = call.data
    try:
        request = Request(
            data["operation"],
            value=data["value"],
            mode=data["mode"],
            slot=data["slot"],
            hour=data["hour"],
            minute=data["minute"],
            enabled=data["enabled"],
            rgb=tuple(data["rgb_color"]),
            part=_REPORT_SIDES.index(data["part"]) + 1,
            report_type=_REPORT_PERIODS.index(data["report_type"]) + 1,
            report_date=data.get("report_date"),
            height=data["height"],
            unit=data["unit"],
        )
    except ValueError as err:
        raise rejected(err) from err
    # A sleep stop clears polling/assembly locally; it has no wire STOP.
    # Serialize it with the current GATT operation instead of cancelling a
    # partially sent SDK frame.
    await _preflight_and_execute(
        _call_targets(call),
        GmmotorActions,
        lambda controller: controller.async_execute_gmmotor_request(request),
        validate=lambda controller: controller.validate_gmmotor_request(request),
    )


def async_register_gmmotor_services(hass: HomeAssistant) -> None:
    from ...services import DEVICE_IDS, SIDE_FIELD

    def integer(maximum: int) -> vol.All:
        return vol.All(_integer, vol.Range(min=0, max=maximum))

    schema = vol.Schema(
        {
            vol.Required("device_id"): DEVICE_IDS,
            **SIDE_FIELD,
            vol.Required("operation"): vol.In(OPERATIONS),
            vol.Optional("value", default=0): integer(65535),
            vol.Optional("mode", default=""): str,
            vol.Optional("slot", default=1): integer(255),
            vol.Optional("hour", default=0): integer(23),
            vol.Optional("minute", default=0): integer(59),
            vol.Optional("enabled", default=True): cv.boolean,
            vol.Optional("rgb_color", default=[0, 0, 0]): vol.ExactSequence((integer(255),) * 3),
            vol.Optional("part", default="left"): vol.In(_REPORT_SIDES),
            vol.Optional("report_type", default="day"): vol.In(_REPORT_PERIODS),
            vol.Optional("report_date"): cv.date,
            vol.Optional("height", default=60.0): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=2559.999)
            ),
            vol.Optional("unit", default="cm"): vol.In(("cm", "inch")),
        }
    )
    hass.services.async_register(DOMAIN, "gmmotor", handle, schema=cast("VolSchemaType", schema))
