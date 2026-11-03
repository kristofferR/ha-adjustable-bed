"""Typed Casper Base bed and sleep sensor actions with all-target preflight."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .casper_base_protocol import ALARM_MODES, Request
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.typing import VolSchemaType

    from .beds.base import BedController, SideBoundController

OPERATIONS = (
    "remote_find",
    "light_rgb",
    "light_seconds",
    "light_off",
    "rgb_power",
    "rgb_color",
    "rgb_timer",
    "rgb_mode",
    "rgb_groove",
    "rgb_breathe",
    "alarm",
    "alarm_cancel",
    "repeat_alarm",
    "repeat_delete",
    "repeat_query",
    "time_sync",
    "snore_detector",
    "sensor_time",
    "sensor_info",
    "sensor_part",
    "sensor_query_part",
    "sensor_live",
    "sensor_report",
    "sensor_stop",
    "sleep_name",
)


def integer(value: object) -> int:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    if type(value) is not int:
        raise vol.Invalid("Expected an integer")
    return value


def weekday(value: object) -> int:
    days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    if isinstance(value, str) and value in days:
        return days.index(value)
    day = integer(value)
    if day not in range(7):
        raise vol.Invalid("Expected a weekday")
    return day


async def handle(call: ServiceCall) -> None:
    from .services import (
        _execute_sided,
        _missing_device_error,
        _preflight_capability,
        _release_preflighted,
        _resolve_sided_targets,
    )

    data = call.data
    request = Request(
        data["operation"],
        value=data["value"],
        rgb=tuple(data["rgb_color"]),
        enabled=data["enabled"],
        hour=data["hour"],
        minute=data["minute"],
        mode=ALARM_MODES.get(data["mode"], ""),
        slot=data["slot"],
        days=tuple(data["days"]),
        part=data["part"],
        report_type=data["report_type"],
        year=data["year"],
        month=data["month"],
        day=data["day"],
        source=data["source"],
    )
    if request.operation == "sensor_report":
        try:
            date(request.year, request.month, request.day)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
    targets, missing = _resolve_sided_targets(call.hass, data["device_id"], data.get("side"))
    if missing:
        raise _missing_device_error(missing[0])

    def validate(controller: BedController | SideBoundController) -> None:
        controller.validate_casper_base_request(request)

    async def execute(controller: BedController) -> None:
        await controller.async_execute_casper_base_request(request)

    try:
        preflighted = await _preflight_capability(
            targets, "supports_casper_base_controls", "Casper Base controls", validate
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                execute,
                cancel_running=request.operation == "sensor_stop"
                or (request.operation in ("sensor_live", "snore_detector") and not request.enabled),
                resource="configuration",
            )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def async_register_casper_base_services(hass: HomeAssistant) -> None:
    from .services import SIDE_FIELD

    schema = vol.Schema(
        {
            vol.Required("device_id"): vol.All(cv.ensure_list, vol.Length(min=1)),
            **SIDE_FIELD,
            vol.Required("operation"): vol.In(OPERATIONS),
            vol.Optional("value", default=0): vol.All(integer, vol.Range(min=0, max=65535)),
            vol.Optional("rgb_color", default=[0, 0, 0]): vol.ExactSequence(
                (vol.All(integer, vol.Range(min=0, max=255)),) * 3
            ),
            vol.Optional("enabled", default=True): cv.boolean,
            vol.Optional("hour", default=0): vol.All(integer, vol.Range(min=0, max=23)),
            vol.Optional("minute", default=0): vol.All(integer, vol.Range(min=0, max=59)),
            vol.Optional("mode", default=""): vol.In(("", *ALARM_MODES)),
            vol.Optional("slot", default=1): vol.All(integer, vol.Range(min=0, max=255)),
            vol.Optional("days", default=[]): [weekday],
            vol.Optional("part", default=1): vol.All(integer, vol.In((1, 2, 11, 12, 13))),
            vol.Optional("report_type", default=1): vol.All(integer, vol.In((1, 2))),
            vol.Optional("year", default=2026): vol.All(integer, vol.Range(min=1970, max=2225)),
            vol.Optional("month", default=1): vol.All(integer, vol.Range(min=1, max=12)),
            vol.Optional("day", default=1): vol.All(integer, vol.Range(min=1, max=31)),
            vol.Optional("source", default=""): str,
        }
    )
    hass.services.async_register(
        DOMAIN, "casper_base", handle, schema=cast("VolSchemaType", schema)
    )
