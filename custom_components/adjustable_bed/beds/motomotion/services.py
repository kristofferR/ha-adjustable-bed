"""Validated MotoMotion user measurements and raw Hall target actions."""

from __future__ import annotations

from math import isfinite

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...codec.motomotion import Position
from ...const import DOMAIN
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute
from .requests import Request


def finite(value: object) -> float:
    if not isinstance(value, (float, int)) or isinstance(value, bool) or not isfinite(value):
        raise vol.Invalid("Measurements must be finite centimetres")
    return float(value)


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
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
    from .controller import MotoMotionController

    request = Request(
        operation=call.data["operation"],
        user=call.data.get("user"),
        dimensions=call.data.get("dimensions"),
        posture=call.data["posture"],
        targets=Position(**call.data["targets"]) if "targets" in call.data else None,
    )
    await _preflight_and_execute(
        _call_targets(call),
        MotoMotionController,
        "MotoMotion users",
        lambda controller: controller.async_execute_motomotion_request(request),
        supported=lambda controller: controller.supports_motomotion_users,
        validate=lambda controller: controller.validate_motomotion_request(request),
        cancel_running=True,
    )


def async_register_motomotion_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "motomotion", handle, schema=SCHEMA)
