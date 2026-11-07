"""Product-gated Good Vibe Sleep configuration and sleep queries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from . import goodvibe_protocol as p
from .beds.base import BedController, SideBoundController
from .codec import richmat as codec
from .const import DOMAIN
from .goodvibe_catalog import ACTIONS
from .services import (
    SIDE_FIELD,
    _execute_sided,
    _missing_device_error,
    _preflight_capability,
    _release_preflighted,
    _resolve_sided_targets,
)

if TYPE_CHECKING:
    from .beds.goodvibe import GoodVibeController

OPERATIONS = (
    "single",
    "cancel_single",
    "repeat",
    "delete",
    "alarms",
    "sync",
    "light_color",
    "light_duration",
    "light_off",
    "massage_timer",
    "snore_switch",
    "snore_count",
    "snore_time",
    "snore_query",
    "part",
    "time",
    "realtime",
    "report",
    "anti_snore",
    "sensitivity",
)


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    action: str | None = None
    when: datetime | None = None
    alarm_id: int | None = None
    weekdays: tuple[int, ...] = ()
    enabled: bool | None = None
    seconds: int | None = None
    rgb: tuple[int, int, int] | None = None
    value: int | None = None
    part: int | None = None
    date: date | None = None
    report_type: int = 1

    def validate(self, controller: GoodVibeController) -> None:
        if self.operation not in OPERATIONS:
            raise ValueError("Unknown Good Vibe Sleep action")
        product = controller.product
        if product is None:
            if self.operation not in (
                "sync",
                "part",
                "time",
                "realtime",
                "report",
                "report_allow",
                "anti_snore",
                "sensitivity",
            ):
                raise ValueError("This is a sleep-sensor profile")
            if controller.kind == 2 and self.operation in ("time", "anti_snore", "sensitivity"):
                raise ValueError("This action has no type 1 packet")
            admitted_parts = (
                (1, 2)
                if self.operation in ("report", "report_allow") or controller.kind == 2
                else (11, 12, 13)
            )
            if self.part is not None and self.part not in admitted_parts:
                raise ValueError("Select an admitted sleep part")
            if (
                self.operation == "report"
                or self.operation == "report_allow"
                and controller.kind == 2
            ):
                if self.date is None or self.part is None or self.report_type not in (1, 2):
                    raise ValueError("Report requires date, part and day/month type")
            if (
                self.operation == "report_allow"
                and controller._sleep is not None
                and not 0 < controller._sleep.report_size <= 2**20
            ):
                raise ValueError("Query report metadata before requesting its contents")
            return
        if self.operation in (
            "part",
            "time",
            "realtime",
            "report",
            "report_allow",
            "anti_snore",
            "sensitivity",
        ):
            raise ValueError("Add the independent sleep device with an RM- or HJ- profile")
        if self.operation in ("light_color", "light_duration", "light_off") and not product.light:
            raise ValueError("The selected product has no light menu")
        if self.operation == "massage_timer" and (
            not product.massage_timer or self.value not in (0, 10, 20, 30)
        ):
            raise ValueError("Choose an admitted massage countdown")
        if self.operation == "light_color" and (
            self.rgb is None or any(type(v) is not int or not 0 <= v <= 255 for v in self.rgb)
        ):
            raise ValueError("Light color requires three byte channels")
        eight_color = product.light_display == "deviceBedLightDisplayCircleEightColorValue"
        if self.operation == "light_color" and eight_color and self.rgb not in p.EIGHT_COLORS:
            raise ValueError("Choose one of this product's eight app colors")
        if self.operation == "light_duration" and self.seconds not in p.light_durations(
            product.label.split(" / ")[0], eight_color
        ):
            raise ValueError("Choose one of this product's app light durations")
        if (
            self.operation in ("single", "cancel_single", "repeat", "delete", "alarms")
            and not product.alarms
        ):
            raise ValueError("The selected product has no alarm menu")
        if self.operation in ("repeat", "delete", "alarms") and not product.repeat_alarm:
            raise ValueError("The selected product does not offer repeat alarms")
        if self.operation in ("single", "repeat"):
            if (
                self.action not in product.alarms
                or self.when is None
                or self.when.utcoffset() is None
            ):
                raise ValueError("Choose an exact alarm action and a timezone-aware date/time")
        if self.alarm_id is not None and not 1 <= self.alarm_id <= 7:
            raise ValueError("Alarm number must be 1–7")
        if self.operation == "delete" and self.alarm_id is None:
            raise ValueError("Choose the alarm to delete")
        if self.operation == "repeat" and self.alarm_id is None:
            self.repeat_slot(controller)
        if any(day not in range(7) for day in self.weekdays):
            raise ValueError("Invalid weekday")
        if self.operation in ("snore_switch", "snore_count", "snore_time", "snore_query") and (
            product.sleep == "deviceSleepMonitoringNone"
            or product.label.split(" / ")[0] in p.SNORE_MENU_EXCLUDED_MODELS
        ):
            raise ValueError("This product does not expose the BLE sleep/snore menu")
        if self.operation == "snore_switch" and self.enabled is None:
            raise ValueError("Choose whether snore intervention is enabled")
        if self.operation == "snore_count" and (self.value is None or not 1 <= self.value <= 30):
            raise ValueError("Snore count must be 1–30")
        if self.operation == "snore_time" and self.value not in (5, 10, 15, 20, 25, 30):
            raise ValueError("Snore time must be 5–30 in steps of five")

    def repeat_slot(self, controller: GoodVibeController) -> int:
        if self.alarm_id is not None:
            return self.alarm_id
        records = controller.choices.events.get("repeat_alarms", {})
        occupied = set(records) if isinstance(records, dict) else set()
        number = next((n for n in range(1, 8) if str(n) not in occupied), None)
        if number is None:
            raise ValueError("All seven observed alarm slots are occupied")
        return number

    def plan(self, controller: GoodVibeController) -> Request:
        """Freeze an automatic allocation while all targets are still in preflight."""
        self.validate(controller)
        if self.operation == "repeat" and self.alarm_id is None:
            return replace(self, alarm_id=self.repeat_slot(controller))
        return self

    def frames(self, controller: GoodVibeController) -> tuple[bytes, ...]:
        op = self.operation
        if op == "sync":
            return p.sync_time(dt_util.now(), dt_util.now())
        if op == "light_color":
            assert self.rgb is not None
            return (codec.rgb(*self.rgb),)
        if op == "light_duration":
            assert self.seconds is not None
            return (p.light_duration(self.seconds),)
        if op in ("light_off", "massage_timer"):
            if op == "light_off":
                code = p.LIGHT_OFF
            else:
                assert self.value is not None
                code = p.MASSAGE_TIMER[self.value]
            return (
                codec.function(code, controller._side(), single=controller._current_link().legacy),
            )
        if op == "snore_switch":
            return (p.snore_switch(bool(self.enabled)),)
        if op in ("snore_count", "snore_time"):
            assert self.value is not None
            return (p.snore_config(op == "snore_count", self.value),)
        if op == "snore_query":
            return (p.QUERIES["snore_config"], p.QUERIES["snore_switch"])
        if op == "alarms":
            return (p.QUERIES["alarms"],)
        if op == "delete":
            assert self.alarm_id is not None
            return (p.delete_alarm(self.alarm_id),)
        if op == "cancel_single":
            return p.clock(0, 0)
        assert self.when is not None and self.action is not None
        code = ACTIONS[self.action].short
        if op == "single":
            now = dt_util.now().replace(second=0, microsecond=0)
            minutes = int(
                (self.when.replace(second=0, microsecond=0).timestamp() - now.timestamp()) / 60
            )
            if minutes <= 0:
                minutes += 1440
            controller._pending_single = {"time": self.when.isoformat(), "action": self.action}
            return p.clock(minutes, code)
        mask = int(self.enabled is not False) + sum(1 << (7 - day) for day in set(self.weekdays))
        number = self.repeat_slot(controller)
        return (p.repeat_alarm(number, self.when.hour, self.when.minute, code, mask),)


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("action"): cv.string,
    vol.Optional("datetime"): cv.datetime,
    vol.Optional("alarm_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    vol.Optional("weekdays", default=[]): vol.All(
        cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=0, max=6))]
    ),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("seconds"): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
    vol.Optional("rgb_color"): vol.All(
        vol.ExactSequence((cv.byte, cv.byte, cv.byte)), vol.Coerce(tuple)
    ),
    vol.Optional("value"): cv.byte,
    vol.Optional("part"): vol.All(vol.Coerce(int), vol.In((1, 2, 11, 12, 13))),
    vol.Optional("date"): cv.date,
    vol.Optional("report_type", default=1): vol.All(vol.Coerce(int), vol.In((1, 2))),
}
FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(FIELDS)


async def handle_goodvibe(call: ServiceCall) -> None:
    from .beds.goodvibe import selected

    request = Request(
        operation=call.data["operation"],
        action=call.data.get("action"),
        when=call.data.get("datetime"),
        alarm_id=call.data.get("alarm_id"),
        weekdays=tuple(call.data["weekdays"]),
        enabled=call.data.get("enabled"),
        seconds=call.data.get("seconds"),
        rgb=call.data.get("rgb_color"),
        value=call.data.get("value"),
        part=call.data.get("part"),
        date=call.data.get("date"),
        report_type=call.data["report_type"],
    )
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get("side")
    )
    if missing:
        raise _missing_device_error(missing[0])

    plans: dict[tuple[str, str], Request] = {}

    def validate(controller: BedController | SideBoundController) -> None:
        target = selected(controller)
        plans[(target._address.upper(), target.product_key)] = request.plan(target)

    preflighted = await _preflight_capability(
        targets, "supports_goodvibe", "Good Vibe Sleep configuration", validate
    )

    async def execute(controller: BedController) -> None:
        target = selected(controller)
        plan = plans.get((target._address.upper(), target.product_key))
        if plan is None:
            raise ServiceValidationError("The Good Vibe Sleep target changed after validation")
        try:
            await controller.async_execute_goodvibe_request(plan)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, execute, cancel_running=False, resource="configuration"
            )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def async_register_goodvibe_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "goodvibe", handle_goodvibe, schema=SCHEMA)
