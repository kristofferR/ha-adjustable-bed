"""Validated SleepEase alarm, anti-snore, sensitivity and report actions."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .beds.base import BedController
from .const import DOMAIN
from .doublesleep_protocol import ALARM_PRESETS, PRESETS, SAVE, alarm_days

type Action = Literal[
    "alarm",
    "anti_snore",
    "anti_snore_demo",
    "sensitivities",
    "report",
    "save_preset",
    "capabilities",
]


@dataclass(frozen=True)
class Request:
    action: Action
    values: tuple[int, ...] = ()


def integer(
    data: Mapping[str, object], key: str, low: int, high: int, default: int | None = None
) -> int:
    value = data.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{key} must be an integer from {low} to {high}")
    return value


def build_request(data: Mapping[str, object]) -> Request:
    action = data.get("action")
    fields = {
        "alarm": {"hour", "minute", "weekdays", "alarm_preset", "alarm_massage"},
        "anti_snore": {"mode", "pwm", "timer"},
        "anti_snore_demo": {"mode", "pwm", "timer"},
        "sensitivities": {"sensor_side", "left_sensitivity", "right_sensitivity"},
        "report": {"report_side", "report_kind", "date"},
        "save_preset": {"preset"},
        "capabilities": {"capability_page"},
    }
    if not isinstance(action, str) or action not in fields:
        raise ValueError("Unknown SleepEase action")
    if set(data) - fields[action] - {"action", "device_id", "side"}:
        raise ValueError("A supplied field does not belong to this SleepEase action")
    if action == "alarm":
        preset = data.get("alarm_preset")
        if not isinstance(preset, str) or preset not in ALARM_PRESETS:
            raise ValueError("Choose an app alarm preset")
        weekdays = data.get("weekdays", [])
        if not isinstance(weekdays, list) or any(not isinstance(day, str) for day in weekdays):
            raise ValueError("Alarm weekdays must be a list")
        hour, minute = integer(data, "hour", 0, 23), integer(data, "minute", 0, 59)
        vibration = data.get("alarm_massage", False)
        if type(vibration) is not bool:
            raise ValueError("Alarm massage must be a boolean")
        return Request(
            "alarm",
            (
                hour,
                minute,
                alarm_days(dt_util.now(), hour, minute, weekdays),
                ALARM_PRESETS[preset],
                int(vibration),
            ),
        )
    if action in ("anti_snore", "anti_snore_demo"):
        return Request(
            action,
            (
                2 if action == "anti_snore_demo" else 1,
                integer(data, "mode", 1, 3),
                integer(data, "pwm", 0, 255) if "pwm" in data else -1,
                integer(data, "timer", 0, 255) if "timer" in data else -1,
            ),
        )
    if action == "sensitivities":
        levels: list[int] = []
        for key in ("left_sensitivity", "right_sensitivity"):
            value = data.get(key)
            if isinstance(value, str) and value in ("1", "2", "3"):
                value = int(value)
            levels.append(integer({key: value}, key, 1, 3) if key in data else -1)
        return Request(
            "sensitivities",
            (integer(data, "sensor_side", 1, 3) if "sensor_side" in data else -1, *levels),
        )
    if action == "report":
        side, kind = data.get("report_side"), data.get("report_kind")
        if side not in ("left", "right") or kind not in ("day", "month"):
            raise ValueError("Choose a report side and day or month")
        stamp = data.get("date")
        if not isinstance(stamp, str):
            raise ValueError("Report date must be YYYY-MM-DD")
        parsed = date.fromisoformat(stamp)
        return Request(
            "report",
            (int(side == "right"), int(kind == "month"), parsed.year, parsed.month, parsed.day),
        )
    if action == "save_preset":
        preset = data.get("preset")
        if not isinstance(preset, str) or preset not in PRESETS or PRESETS[preset] not in SAVE:
            raise ValueError("Choose a programmable SleepEase preset")
        return Request("save_preset", (SAVE[PRESETS[preset]],))
    if action == "capabilities":
        return Request("capabilities", (integer(data, "capability_page", 0, 255, 0),))
    raise ValueError("Unknown SleepEase action")


async def handle_doublesleep(call: ServiceCall) -> None:
    from .beds.doublesleep import selected
    from .services import (
        ATTR_SIDE,
        CONF_DEVICE_ID,
        _execute_sided,
        _missing_device_error,
        _preflight_capability,
        _release_preflighted,
        _resolve_sided_targets,
    )

    try:
        request = build_request(call.data)
    except (ValueError, KeyError) as err:
        raise ServiceValidationError(str(err)) from err
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])

    def validate(controller: BedController) -> None:
        # Shared preflight supplies a BedController (possibly side-bound).
        selected(controller).validate_request(request)

    async def execute(controller: BedController) -> None:
        await selected(controller).request(request)

    try:
        preflighted = await _preflight_capability(
            targets, "supports_doublesleep_controls", "OKIN SleepEase controls", validate
        )
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, execute, resource="*")
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


def async_register_doublesleep_services(hass: HomeAssistant) -> None:
    from .services import CONF_DEVICE_ID, SIDE_FIELD

    fields = (
        "hour",
        "minute",
        "weekdays",
        "alarm_preset",
        "alarm_massage",
        "mode",
        "pwm",
        "timer",
        "sensor_side",
        "left_sensitivity",
        "right_sensitivity",
        "date",
        "report_side",
        "report_kind",
        "preset",
        "capability_page",
    )
    schema = {
        vol.Required(CONF_DEVICE_ID): cv.ensure_list,
        **SIDE_FIELD,
        vol.Required("action"): vol.In(
            (
                "alarm",
                "anti_snore",
                "anti_snore_demo",
                "sensitivities",
                "report",
                "save_preset",
                "capabilities",
            )
        ),
        **{vol.Optional(key): object for key in fields},
    }
    hass.services.async_register(
        DOMAIN, "doublesleep_configure", handle_doublesleep, schema=vol.Schema(schema)
    )
