"""Product-gated Okimiki actions with all-target admission before lazy imports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...codec import richmat as codec
from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...profiles.okimiki import CONTROLS
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
)
from . import protocol as p

if TYPE_CHECKING:
    from .controller import OkimikiController

OPERATIONS = (
    "press",
    "save",
    "light_color",
    "light_duration",
    "light_off",
    "single",
    "cancel_single",
    "alarms",
    "repeat",
    "enable",
    "delete",
    "sync",
)
MODES = ("lounge", "zero_gravity", "memory_1", "memory_2")


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    control: str | None = None
    duration_ms: int = 1000
    when: datetime | None = None
    alarm_id: int | None = None
    mode: str | None = None
    days: tuple[int, ...] | None = None
    enabled: bool | None = None
    seconds: int | None = None
    rgb: tuple[int, int, int] | None = None
    record: p.Alarm | None = None

    def validate(self, controller: OkimikiController) -> None:
        op = self.operation
        if op not in OPERATIONS:
            raise ValueError("Choose an Okimiki action")
        if op in ("press", "save"):
            if self.control not in controller.control_actions or not 0 <= self.duration_ms <= 60000:
                raise ValueError("Choose a control offered by this product")
            if op == "save" and CONTROLS[self.control].save is None:
                raise ValueError("This control has no save action")
        elif op.startswith("light_"):
            if not controller.menu_available("light"):
                raise ValueError("The connected bed has not reported light support")
            if op == "light_duration" and (
                type(self.seconds) is not int or not 0 <= self.seconds <= 900
            ):
                raise ValueError("Choose 0 to 900 seconds, zero keeps the light on")
            if op == "light_color" and (
                self.rgb is None
                or len(self.rgb) != 3
                or any(type(v) is not int or not 0 <= v <= 255 for v in self.rgb)
            ):
                raise ValueError("Choose three RGB byte channels")
        elif op == "sync":
            if controller.model.alarm == "none":
                raise ValueError("This product has no clock")
        else:
            if not controller.menu_available("alarm"):
                raise ValueError("The connected bed has not reported alarm support")
            if (op in ("single", "cancel_single")) != (controller.model.alarm == "single"):
                raise ValueError("Choose the alarm action for this product")
            if self.mode is not None and (
                self.mode not in MODES
                or controller.model.alarm == "single"
                and self.mode != "lounge"
            ):
                raise ValueError("Choose an alarm mode offered by this product")
            if op == "single" and (self.when is None or self.when.utcoffset() is None):
                raise ValueError("Choose a timezone-aware alarm time")
            if op == "repeat":
                if self.record is None and (self.when is None or self.mode is None):
                    raise ValueError("A new alarm needs a time and mode")
                if self.when is not None and self.when.utcoffset() is None:
                    raise ValueError("Choose a timezone-aware alarm time")
            if self.alarm_id is not None and not 1 <= self.alarm_id <= 7:
                raise ValueError("Choose alarm ID 1 to 7")
            if op in ("enable", "delete") and self.alarm_id is None:
                raise ValueError("Choose an observed alarm ID")
            if op == "enable" and self.enabled is None:
                raise ValueError("Choose whether this alarm is enabled")
            if self.days is not None and any(
                type(day) is not int or day not in range(7) for day in self.days
            ):
                raise ValueError("Choose weekdays Monday 0 to Sunday 6")
            if self.record is not None:
                current = next(
                    (row for row in reversed(controller._alarms) if row.id == self.record.id), None
                )
                if self.record.id in controller._stale_alarm_ids or current != self.record:
                    raise ValueError("Query a fresh record before changing this alarm again")
            if op == "repeat" and self.record is None and controller._stale_alarm_ids:
                raise ValueError("Read back the previous alarm change before allocating another ID")

    def plan(self, controller: OkimikiController) -> Request:
        """Keep the actual returned reserved byte and physical receiver's record."""
        request = self
        if self.alarm_id is not None and self.operation in ("repeat", "enable", "delete"):
            record = next(
                (row for row in reversed(controller._alarms) if row.id == self.alarm_id), None
            )
            if record is None:
                raise ValueError("Query this bed's alarms before editing or deleting one")
            request = replace(self, record=record)
        request.validate(controller)
        return request

    def frames(self, controller: OkimikiController) -> tuple[bytes, ...]:
        op = self.operation
        if op == "sync":
            return p.sync_time(dt_util.now(), dt_util.now())
        if op == "light_color":
            assert self.rgb is not None
            return (codec.rgb(*self.rgb),)
        if op == "light_duration":
            assert self.seconds is not None
            return (p.light_seconds(self.seconds),)
        if op == "light_off":
            return (codec.function(0x75, single=controller._current_link().legacy),)
        if op == "single":
            assert self.when is not None
            return p.countdown(
                p.countdown_minutes(dt_util.now(), self.when), CONTROLS["lounge"].opcode
            )
        if op == "cancel_single":
            return p.countdown(0, 0)
        if op == "alarms":
            return (codec.record(5, 1, 0, (0,)),)
        if op == "delete":
            assert self.alarm_id is not None
            return (codec.record(5, 2, 1, (self.alarm_id,)),)
        if op == "enable":
            assert self.record is not None and self.enabled is not None
            return (
                replace(self.record, mask=(self.record.mask & 0xFE) | int(self.enabled)).frame(),
            )
        if op == "repeat":
            row = self.record
            number = row.id if row else p.next_alarm_id(tuple(controller._alarms))
            reserved = row.reserved if row else 0
            when = dt_util.as_local(self.when) if self.when else None
            hour = when.hour if when else row.hour if row else 0
            minute = when.minute if when else row.minute if row else 0
            opcode = CONTROLS[self.mode].opcode if self.mode else row.opcode if row else 0
            mask = row.mask if row else 1
            if self.days is not None:
                mask = p.repeat_mask(self.days, bool(mask & 1))
            if self.enabled is not None:
                mask = (mask & 0xFE) | int(self.enabled)
            return (p.Alarm(number, reserved, hour, minute, opcode, mask).frame(),)
        raise ValueError("This operation has no settings frames")


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("control"): vol.In(CONTROLS),
    vol.Optional("duration_ms", default=1000): vol.All(cv.positive_int, vol.Range(max=60000)),
    vol.Optional("datetime"): cv.datetime,
    vol.Optional("alarm_id"): vol.All(cv.positive_int, vol.Range(min=1, max=7)),
    vol.Optional("mode"): vol.In(MODES),
    vol.Optional("weekdays"): vol.All(cv.ensure_list, [vol.All(cv.positive_int, vol.Range(max=6))]),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=900)),
    vol.Optional("rgb_color"): vol.All(vol.ExactSequence((cv.byte,) * 3), vol.Coerce(tuple)),
}
FIELDS.update(SIDE_FIELD.items())


async def handle_okimiki(call: ServiceCall) -> None:
    targets = _call_targets(call)
    movement = call.data["operation"] in ("press", "save")
    resource = "movement" if movement else "configuration"
    # Freeze every physical owner's STOP epoch before the very first await.
    admissions = [_capture_command_admission(c, side, (resource,)) for c, side in targets]
    await async_import_modules(call.hass, "beds.okimiki.controller")
    from .controller import OkimikiController

    request = Request(
        call.data["operation"],
        control=call.data.get("control"),
        duration_ms=call.data["duration_ms"],
        when=call.data.get("datetime"),
        alarm_id=call.data.get("alarm_id"),
        mode=call.data.get("mode"),
        days=tuple(call.data["weekdays"]) if "weekdays" in call.data else None,
        enabled=call.data.get("enabled"),
        seconds=call.data.get("seconds"),
        rgb=call.data.get("rgb_color"),
    )
    plans: dict[tuple[str, str], tuple[Request, object | None]] = {}

    def validate(controller: OkimikiController) -> None:
        plans[(controller._address.upper(), controller.product_key)] = (
            request.plan(controller),
            controller._link,
        )

    prepared = await _preflight_capability(targets, OkimikiController, "Okimiki", validate=validate)

    async def execute(controller: OkimikiController) -> None:
        plan = plans.get((controller._address.upper(), controller.product_key))
        if plan is None or plan[1] is not None and controller._link is not plan[1]:
            raise ValueError("The physical Okimiki controller changed after validation")
        await controller.execute_request(plan[0])

    await _execute_preflighted(
        targets,
        prepared,
        _family_command(OkimikiController, "Okimiki", execute),
        cancel_running=movement,
        resource=resource,
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "okimiki", handle_okimiki, schema=vol.Schema(FIELDS))
