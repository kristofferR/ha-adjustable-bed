"""Validated MotoMotion user measurements and raw Hall target actions."""

from __future__ import annotations

from math import isfinite

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .beds.base import BedController, SideBoundController
from .codec.motomotion import Position
from .const import DOMAIN
from .motomotion_requests import Request
from .services import (
    SIDE_FIELD,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)


def finite(value: object) -> float:
    if not isinstance(value, (float, int)) or isinstance(value, bool) or not isfinite(value):
        raise vol.Invalid("Measurements must be finite centimetres")
    return float(value)


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
    vol.Required("operation"): vol.In(
        (
            "save_user",
            "select_user",
            "delete_user",
            "recall",
            "save_posture",
            "reset_posture",
            "fine_tune",
        )
    ),
    vol.Optional("user"): vol.All(cv.string, vol.Length(min=1)),
    vol.Optional("dimensions"): vol.All(
        vol.ExactSequence((finite, finite, finite)), vol.Coerce(tuple)
    ),
    vol.Optional("posture", default="upright"): vol.In(("upright", "recline", "tv", "lay")),
    vol.Optional("targets"): vol.Schema(
        {
            vol.Required(key): vol.All(int, vol.Range(min=0, max=maximum))
            for key, maximum in {
                "head": 863,
                "base": 3174,
                "back": 1454,
                "lumbar": 874,
                "tilt": 629,
            }.items()
        }
    ),
}
FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(FIELDS)


async def handle(call: ServiceCall) -> None:
    request = Request(
        operation=call.data["operation"],
        user=call.data.get("user"),
        dimensions=call.data.get("dimensions"),
        posture=call.data["posture"],
        targets=Position(**call.data["targets"]) if "targets" in call.data else None,
    )
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get("side")
    )
    if missing:
        raise _missing_device_error(missing[0])

    def validate(controller: BedController | SideBoundController) -> None:
        controller.validate_motomotion_request(request)

    preflighted = await _preflight_capability(
        targets, "supports_motomotion_users", "MotoMotion users", validate
    )

    async def execute(controller: BedController) -> None:
        try:
            await controller.async_execute_motomotion_request(request)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, execute, cancel_running=True, resource="configuration"
            )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def async_register_motomotion_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "motomotion", handle, schema=SCHEMA)
