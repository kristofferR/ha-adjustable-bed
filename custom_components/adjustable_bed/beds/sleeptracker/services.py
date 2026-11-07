"""Typed Sleeptracker local bed actions with shared paired-target preflight."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ...const import DOMAIN
from .protocol import FREQUENCIES, PRESETS, FanSide, Request

if TYPE_CHECKING:
    from homeassistant.helpers.typing import VolSchemaType


def build_request(service: str, data: Mapping[str, object]) -> Request:
    """Schemas provide defaults; reject coercion that could change an action."""
    if service == "sleeptracker_preset":
        return Request("preset", preset=str(data["preset"]), save=data.get("save") is True)
    if service == "sleeptracker_climate":
        level = data["level"]
        if type(level) is not int or level not in range(4):
            raise ValueError("Climate level must be an integer from 0 to 3")
        return Request(
            "climate",
            fan_side=cast(FanSide, data["fan_side"]),
            level=level,
            heating=data["mode"] == "heat",
            constant=data["constant"] is True,
        )
    if service == "sleeptracker_wave":
        frequency, minutes = data["frequency"], data["minutes"]
        if (
            type(frequency) is not int
            or frequency not in FREQUENCIES
            or type(minutes) is not int
            or minutes not in range(5, 106, 5)
        ):
            raise ValueError("Choose a supported frequency and duration")
        return Request("wave", frequency=frequency, minutes=minutes)
    if service == "sleeptracker_massage":
        action = data["action"]
        if action not in ("head", "foot", "pattern", "28Hz", "40Hz", "off"):
            raise ValueError("Unknown Sleeptracker massage action")
        return Request(
            "massage",
            massage_action=cast(
                "Literal['head', 'foot', 'pattern', '28Hz', '40Hz', 'off']", action
            ),
        )
    if service == "sleeptracker_relaxation":
        action = data["action"]
        if action == "wind_down_1":
            return Request("wind_down", mode=1)
        if action == "wind_down_2":
            return Request("wind_down", mode=2)
        if action == "local_animation":
            return Request("local_animation")
    raise ValueError("Unknown Sleeptracker service action")


async def handle_sleeptracker(call: ServiceCall) -> None:
    from ...services import _call_targets, _preflight_and_execute
    from .controller import SleeptrackerController

    try:
        request = build_request(call.service, call.data)
    except (ValueError, KeyError) as err:
        raise ServiceValidationError(str(err)) from err
    await _preflight_and_execute(
        _call_targets(call),
        SleeptrackerController,
        "Sleeptracker processor controls",
        lambda controller: controller.async_execute_sleeptracker_request(request),
        validate=lambda controller: controller.validate_sleeptracker_request(request),
        cancel_running=True,
        resource="*",
    )


def _integer(value: object) -> int:
    if type(value) is not int:
        raise vol.Invalid("Expected an integer")
    return value


def _frequency(value: object) -> int:
    # HA select selectors emit strings; YAML automations may use integers.
    if isinstance(value, str) and value in tuple(str(hz) for hz in FREQUENCIES):
        return int(value)
    return _integer(value)


def async_register_sleeptracker_services(hass: HomeAssistant) -> None:
    from ...services import CONF_DEVICE_ID, SIDE_FIELD

    common = {vol.Required(CONF_DEVICE_ID): cv.ensure_list, **SIDE_FIELD}
    schemas = {
        "sleeptracker_preset": {
            vol.Required("preset"): vol.In(PRESETS),
            vol.Optional("save", default=False): bool,
        },
        "sleeptracker_climate": {
            vol.Optional("fan_side", default="both"): vol.In(("left", "right", "both")),
            vol.Required("mode"): vol.In(("heat", "cool")),
            vol.Required("level"): vol.All(_integer, vol.Range(min=0, max=3)),
            vol.Optional("constant", default=True): bool,
        },
        "sleeptracker_wave": {
            vol.Required("frequency"): vol.All(_frequency, vol.In(FREQUENCIES)),
            vol.Optional("minutes", default=30): vol.All(_integer, vol.In(range(5, 106, 5))),
        },
        "sleeptracker_massage": {
            vol.Required("action"): vol.In(("head", "foot", "pattern", "28Hz", "40Hz", "off"))
        },
        "sleeptracker_relaxation": {
            vol.Required("action"): vol.In(("wind_down_1", "wind_down_2", "local_animation"))
        },
    }
    for name, schema in schemas.items():
        hass.services.async_register(
            DOMAIN,
            name,
            handle_sleeptracker,
            schema=cast("VolSchemaType", vol.Schema({**common, **schema})),
        )
