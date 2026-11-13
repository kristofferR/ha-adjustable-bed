"""M Line actions use generic all-target admission, side routing and serialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util.json import JsonValueType

from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _preflight_and_execute,
)

if TYPE_CHECKING:
    from .controller import MLineController

ACTIONS = (
    "privacy",
    "anti_snore",
    "anti_snore_demo",
    "settings_refresh",
    "alarm_refresh",
    "live_query",
    "history_read",
    "history_ack",
)


async def handle_command(call: ServiceCall) -> ServiceResponse:
    action = call.data["action"]
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.mline.controller")
    from .controller import MLineController

    if action.startswith("history_") and sum(len(_command_targets(p, s)) for p, s in targets) != 1:
        raise ServiceValidationError("Raw M Line history requires exactly one physical bed side")
    results: list[JsonValueType] = []

    def validate(c: MLineController) -> None:
        if action == "privacy":
            c.validate_action("privacy")
        elif action.startswith("anti_snore"):
            c.validate_action("anti_snore")
        elif action.startswith("history_"):
            c.validate_action("history")
            if action == "history_ack":
                c.validate_history_ack(call.data["transfer"])
        elif action == "live_query":
            c.validate_action("live")

    async def execute(c: MLineController) -> None:
        # A sequential pair can recreate the controller after preflight. Validate
        # again on the physical session, without using cached sensor readiness.
        validate(c)
        if action == "privacy":
            await c.configure_privacy(call.data["enabled"])
        elif action in ("anti_snore", "anti_snore_demo"):
            await c.configure_anti_snore(
                call.data["enabled"],
                call.data["angle"],
                call.data["position"],
                demo=action == "anti_snore_demo",
            )
        elif action == "settings_refresh":
            await c.settings_refresh()
        elif action == "alarm_refresh":
            await c.alarm_refresh()
        elif action == "live_query":
            await c.query_live()
        elif action == "history_read":
            results.append(await c.read_history(all_records=call.data["all_records"]))
        elif action == "history_ack":
            await c.acknowledge_history(call.data["transfer"])

    await _preflight_and_execute(
        targets,
        MLineController,
        "M Line actions",
        execute,
        validate=validate,
        resource="*",
        admit=True,
        admissions=admissions,
    )
    return {"transfers": results}


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "mline_set_alarm",
        handle_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("enabled"): cv.boolean,
                vol.Optional("time"): cv.time,
                vol.Optional("weekdays", default=[]): [
                    vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
                ],
                vol.Optional("wake_mode", default="zg"): vol.In(
                    ("zg", "flat", "m1", "m2", "vibration", "antisnore")
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "mline_command",
        handle_command,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required("action"): vol.In(ACTIONS),
                vol.Optional("enabled", default=True): bool,
                vol.Optional("angle", default=1): vol.All(vol.Coerce(int), vol.In((1, 3, 6))),
                vol.Optional("position", default=1): vol.All(vol.Coerce(int), vol.In((1, 2))),
                vol.Optional("all_records", default=False): bool,
                vol.Optional("transfer", default=""): str,
                **SIDE_FIELD,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )


async def handle_alarm(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    await async_import_modules(call.hass, "beds.mline.controller")
    from homeassistant.util import dt as dt_util

    from ...codec import mline as codec
    from .controller import MLineController

    enabled, time = call.data["enabled"], call.data.get("time")
    if enabled and time is None:
        raise ServiceValidationError("Choose an M Line alarm time")
    if time is not None and (time.second or time.microsecond):
        raise ServiceValidationError("M Line alarms use minute precision")
    hour, minute = (time.hour, time.minute) if time else (0, 0)
    weekdays = tuple(call.data["weekdays"])
    preset = call.data["wake_mode"]

    def validate(c: MLineController) -> None:
        c.validate_action("alarm")
        codec.alarm(
            c.profile.key,
            hour,
            minute,
            codec.wake_mask(weekdays, hour, minute, dt_util.now()),
            preset,
        )

    await _preflight_and_execute(
        targets,
        MLineController,
        "M Line alarm",
        lambda c: c.configure_clock_alarm(
            enabled=enabled, weekdays=weekdays, hour=hour, minute=minute, preset=preset
        ),
        validate=validate,
        resource="*",
        admit=True,
        admissions=admissions,
    )
