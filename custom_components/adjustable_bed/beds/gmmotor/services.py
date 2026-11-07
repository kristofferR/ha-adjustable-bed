"""Finite GM Control direct BLE operations with all-target admission."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, get_args

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from .requests import GmmotorActions, Operation, Request

if TYPE_CHECKING:
    from homeassistant.helpers.typing import VolSchemaType

OPERATIONS = get_args(Operation.__value__)


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
            repeat=data["repeat"],
            hour=data["hour"],
            minute=data["minute"],
            status=data["status"],
            enabled=data["enabled"],
            rgb=tuple(data["rgb_color"]),
            part=data["part"],
            report_type=data["report_type"],
            report_date=data.get("report_date"),
            height=data["height"],
            unit=data["unit"],
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    # A sleep stop clears polling/assembly locally; it has no wire STOP.
    # Serialize it with the current GATT operation instead of cancelling a
    # partially sent SDK frame.
    await _preflight_and_execute(
        _call_targets(call),
        GmmotorActions,
        "GM Control actions",
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
            vol.Optional("repeat", default=0): integer(255),
            vol.Optional("hour", default=0): integer(23),
            vol.Optional("minute", default=0): integer(59),
            vol.Optional("status", default=1): integer(255),
            vol.Optional("enabled", default=True): cv.boolean,
            vol.Optional("rgb_color", default=[0, 0, 0]): vol.ExactSequence((integer(255),) * 3),
            vol.Optional("part", default=1): vol.All(_integer, vol.In((1, 2))),
            vol.Optional("report_type", default=1): vol.All(_integer, vol.In((1, 2))),
            vol.Optional("report_date"): cv.date,
            vol.Optional("height", default=60.0): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=2559.999)
            ),
            vol.Optional("unit", default="cm"): vol.In(("cm", "inch")),
        }
    )
    hass.services.async_register(DOMAIN, "gmmotor", handle, schema=cast("VolSchemaType", schema))
