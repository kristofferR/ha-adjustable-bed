"""Named, validated Richmat 4.2.0 bed and separate sleep-link actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ...command_scheduler import ALL_COMMAND_RESOURCES
from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _execute_preflighted,
    _family_command,
    _preflight_and_execute,
    _preflight_capability,
)
from .protocol import BlanketSleep
from .requests import OPERATIONS, DemoStep, Request

BYTE = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))
SLEEP_SCHEMA = vol.Schema(
    {
        vol.Optional("enabled", default=True): cv.boolean,
        vol.Optional("mode", default=2): vol.In((1, 2)),
        vol.Optional("start_hour", default=23): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
        vol.Optional("start_minute", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
        vol.Optional("end_hour", default=7): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
        vol.Optional("end_minute", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=59)),
        vol.Optional("days", default=[0, 1, 2, 3, 4]): [vol.In(range(8))],
        vol.Optional("after_mode", default=1): vol.In((0, 1)),
        vol.Optional("delay", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        vol.Optional("temperatures", default=[38, 36, 35, 37]): vol.ExactSequence((BYTE,) * 4),
        vol.Optional("automatic", default=False): cv.boolean,
    }
)
FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("value", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
    vol.Optional("mode", default=0): BYTE,
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("rgb_color", default=[255, 255, 255]): vol.ExactSequence((BYTE,) * 3),
    vol.Optional("opacity", default=100): vol.All(vol.Coerce(int), vol.Range(min=10, max=100)),
    vol.Optional("zone", default=1): vol.All(vol.Coerce(int), vol.In((1, 2, 3))),
    vol.Optional("temperature", default=25): vol.All(vol.Coerce(int), vol.Range(min=16, max=55)),
    vol.Optional("flags"): vol.ExactSequence((cv.boolean,) * 6),
    vol.Optional("sleep"): SLEEP_SCHEMA,
    vol.Optional("datetime"): cv.datetime,
    vol.Optional("action", default=""): cv.string,
    vol.Optional("alarm_id", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    vol.Optional("weekdays", default=[]): [vol.In(range(8))],
    vol.Optional("query", default="alarms"): cv.string,
    vol.Optional("steps", default=[]): [
        vol.Schema(
            {
                vol.Required("action"): cv.string,
                vol.Optional("sustain", default=False): cv.boolean,
                vol.Optional("seconds", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=60)
                ),
                vol.Optional("delay", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=600)
                ),
            }
        )
    ],
    vol.Optional("cycle", default=False): cv.boolean,
    vol.Optional("part", default=12): vol.In((11, 12, 13)),
    vol.Optional("report_type", default=1): vol.In((1, 2)),
}
FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(FIELDS)


async def handle(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.richmat_app.controller", "beds.richmat_app.sleep")
    from .controller import RichmatAppController
    from .sleep import SleepController

    data = call.data
    s = data.get("sleep")
    schedule = (
        BlanketSleep(**{**s, "days": tuple(s["days"]), "temperatures": tuple(s["temperatures"])})
        if s is not None
        else None
    )
    request = Request(
        operation=data["operation"],
        value=data["value"],
        mode=data["mode"],
        enabled=data["enabled"],
        rgb=tuple(data["rgb_color"]),
        opacity=data["opacity"],
        zone=data["zone"],
        temperature=data["temperature"],
        flags=tuple(data["flags"]) if "flags" in data else None,
        sleep=schedule,
        when=data.get("datetime"),
        action=data["action"],
        alarm_id=data["alarm_id"],
        weekdays=tuple(data["weekdays"]),
        query=data["query"],
        steps=tuple(DemoStep(**row) for row in data["steps"]),
        cycle=data["cycle"],
        part=data["part"],
        report_type=data["report_type"],
    )
    if request.operation.startswith("sleep_"):
        await _preflight_and_execute(
            _call_targets(call),
            SleepController,
            "Richmat sleep session",
            lambda c: c.execute_request(request),
            validate=lambda c: c.validate_request(request),
        )
    else:
        targets = _call_targets(call)
        resource = None if request.operation == "demo" else "configuration"
        admissions = [
            _capture_command_admission(
                parent, side, ALL_COMMAND_RESOURCES if resource is None else (resource,)
            )
            for parent, side in targets
        ]
        label = "Richmat app controls"
        preflighted = await _preflight_capability(targets, RichmatAppController, label)

        async def validate_live(controller: RichmatAppController) -> None:
            controller.validate_request(request)

        # Offline controllers know the catalog, not this connection's replies.
        # Validate every live target before any target executes the request.
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(RichmatAppController, label, validate_live),
            resource=resource,
            admissions=admissions,
        )
        await _execute_preflighted(
            targets,
            preflighted,
            _family_command(RichmatAppController, label, lambda c: c.execute_request(request)),
            resource=resource,
            admissions=admissions,
        )


def async_register_richmat_app_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "richmat_app", handle, schema=SCHEMA)
