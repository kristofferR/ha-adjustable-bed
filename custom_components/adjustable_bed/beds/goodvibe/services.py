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

from ...codec import richmat as codec
from ...const import DOMAIN
from ...import_executor import async_import_modules
from ...services import DEVICE_IDS, SIDE_FIELD, _call_targets, _preflight_and_execute
from . import protocol as p

if TYPE_CHECKING:
    from .controller import GoodVibeController

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
    "init",
    "toggle",
)


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    action: str | None = None
    when: datetime | None = None
    alarm_id: int | None = None
    weekdays: tuple[int, ...] | None = None
    enabled: bool | None = None
    seconds: int | None = None
    rgb: tuple[int, int, int] | None = None
    value: int | None = None
    part: int | None = None
    date: date | None = None
    report_type: int = 1
    record: tuple[int, ...] | None = None
    left: int | float | tuple[int | float, ...] | None = None
    right: int | float | tuple[int | float, ...] | None = None
    alarm_fields: tuple[int, ...] = ()

    def validate(self, controller: GoodVibeController, *, reported: bool = True) -> None:
        operations = BED_OPERATIONS if controller.catalog.key == "galaxy" else OPERATIONS
        if self.operation not in operations:
            raise ValueError("Unknown Good Vibe Sleep action")
        if controller.catalog.reply_gated_menus and self.operation.startswith("snore_"):
            raise ValueError("MLILY does not expose the library's bed snore settings page")
        product = controller.product
        if product is None:
            if controller.catalog.reply_gated_menus and self.operation == "anti_snore" and self.enabled is not None and self.left is None and self.right is None:
                raise ValueError("Supply the app's explicit Left/Right anti-snore operands")
            if self.operation not in (
                "sync",
                "part",
                "time",
                "realtime",
                "report",
                "report_allow",
                "anti_snore",
                "sensitivity",
                "init",
            ):
                raise ValueError("This is a sleep-sensor profile")
            if controller.kind == 2 and self.operation in ("time", "anti_snore", "sensitivity", "init"):
                raise ValueError("This action has no type 1 packet")
            admitted_parts = (
                (1, 2)
                if self.operation in ("report", "report_allow") or controller.kind == 2
                else (11, 12, 13)
            )
            if not controller.catalog.reply_gated_menus and self.part is not None and self.part not in admitted_parts:
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
            "init",
        ):
            raise ValueError("Add the independent sleep device with an RM- or HJ- profile")
        if reported and controller.catalog.notification_menus:
            menu = (
                "light"
                if self.operation.startswith("light_")
                else "alarm"
                if self.operation
                in ("single", "cancel_single", "repeat", "delete", "alarms", "enable_alarm")
                else "snore"
                if self.operation.startswith("snore_")
                else None
            )
            if menu is not None and menu not in controller._menus:
                raise ValueError("The connected bed has not advertised this product capability")
        if self.operation in ("light_color", "light_duration", "light_off") and not controller.menu_available("light"):
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
            self.operation in ("single", "cancel_single", "repeat", "delete", "alarms", "toggle", "enable_alarm")
            and not controller.menu_available("alarm")
        ):
            raise ValueError("The selected product has no alarm menu")
        if self.operation in ("repeat", "delete", "alarms", "toggle", "enable_alarm") and not product.repeat_alarm:
            raise ValueError("The selected product does not offer repeat alarms")
        if controller.catalog.reply_gated_menus and product.repeat_alarm and self.operation in ("single", "cancel_single"):
            raise ValueError("This product uses the repeat-alarm page")
        if self.operation in ("single", "repeat"):
            record_edit = controller.catalog.reply_gated_menus and self.operation == "repeat" and self.record is not None
            if (
                (self.action not in product.alarms and not (
                    record_edit and self.action is None
                ))
                or (self.when is None and not record_edit)
                or (self.when is not None and self.when.utcoffset() is None)
            ):
                raise ValueError("Choose an exact alarm action and a timezone-aware date/time")
        if self.alarm_id is not None and not 1 <= self.alarm_id <= 7:
            raise ValueError("Alarm number must be 1–7")
        if self.operation == "enable_alarm":
            if self.enabled is None or self.alarm_id is None:
                raise ValueError("Choose an observed alarm and its enabled state")
            self.observed_alarm(controller)
        if self.operation == "delete" and self.alarm_id is None:
            raise ValueError("Choose the alarm to delete")
        if self.record is not None and (
            len(self.record) != 6 or any(type(v) is not int or not 0 <= v <= 255 for v in self.record)
        ):
            raise ValueError("An alarm record has six byte fields")
        if self.record is not None and self.operation in ("repeat", "toggle"):
            if not 1 <= self.record[0] <= 7 or self.alarm_id not in (None, self.record[0]):
                raise ValueError("An edit must retain a valid observed alarm ID")
        if self.operation == "toggle" and (self.record is None or self.enabled is None):
            raise ValueError("Choose the observed alarm record and its enabled state")
        if self.operation == "repeat" and self.alarm_id is None and self.record is None:
            self.repeat_slot(controller)
        if any(day not in range(7) for day in self.weekdays or ()):
            raise ValueError("Invalid weekday")
        if self.operation == "repeat" and self.record is not None and self.action is None:
            if not any(controller.catalog.actions[key].short == self.record[4] for key in product.alarms):
                raise ValueError("The observed alarm mode is unknown; choose a mode explicitly")
        if self.operation in ("snore_switch", "snore_count", "snore_time", "snore_query") and (
            not controller.snore_available
        ):
            raise ValueError("This product does not expose the BLE sleep/snore menu")
        if self.operation == "snore_switch" and self.enabled is None:
            raise ValueError("Choose whether snore intervention is enabled")
        if self.operation == "snore_count" and (self.value is None or not 1 <= self.value <= 30):
            raise ValueError("Snore count must be 1–30")
        if self.operation == "snore_time" and self.value not in (5, 10, 15, 20, 25, 30):
            raise ValueError("Snore time must be 5–30 in steps of five")

    def observed_alarm(self, controller: GoodVibeController) -> tuple[int, ...]:
        if self.alarm_fields:
            return self.alarm_fields
        records = controller.choices.events.get("repeat_alarms")
        value = records.get(str(self.alarm_id)) if isinstance(records, dict) else None
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 6
            or any(type(v) is not int or not 0 <= v <= 255 for v in value)
        ):
            raise ValueError("Query the current alarm list before changing its enabled state")
        return tuple(value)

    def repeat_slot(self, controller: GoodVibeController) -> int:
        if self.alarm_id is not None:
            return self.alarm_id
        if self.record is not None:
            if not 1 <= self.record[0] <= 7:
                raise ValueError("The observed alarm has an invalid slot")
            return self.record[0]
        if controller.catalog.reply_gated_menus:
            # MLILY reports individual records without a list-completion marker.
            # An empty or partially received cache cannot prove a slot is unused.
            raise ValueError("Choose alarm_id or alarm_record; the alarm list may be incomplete")
        records = controller.choices.events.get("repeat_alarms", {})
        occupied = set(records) if isinstance(records, dict) else set()
        number = next((n for n in range(1, 8) if str(n) not in occupied), None)
        if number is None:
            raise ValueError("All seven observed alarm slots are occupied")
        return number

    def plan(self, controller: GoodVibeController) -> Request:
        """Freeze an automatic allocation while all targets are still in preflight."""
        client = controller.client
        self.validate(controller, reported=client is not None and client.is_connected)
        if self.operation == "enable_alarm":
            return replace(self, alarm_fields=self.observed_alarm(controller))
        if self.operation == "repeat" and self.alarm_id is None:
            return replace(self, alarm_id=self.repeat_slot(controller))
        return self

    def frames(self, controller: GoodVibeController) -> tuple[bytes, ...]:
        op = self.operation
        if op == "enable_alarm":
            fields = self.observed_alarm(controller)
            return (
                controller.record(
                    5, 1, 1, (*fields[:-1], fields[-1] & 0xFE | int(self.enabled is True))
                ),
            )
        if op == "sync":
            return p.sync_time(dt_util.now(), dt_util.now(), build=controller.record)
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
                code = 0x8B if controller.profile.key == "mlily" and controller.product is not None and controller.product.label == "D9RM" and self.value == 0 else controller.catalog.timer_codes.get(controller.product_key, p.MASSAGE_TIMER)[self.value]
            return (
                codec.function(code, 0 if controller.catalog.reply_gated_menus else controller._side(), single=controller._current_link().legacy),
            )
        if op == "snore_switch":
            return (p.snore_switch(bool(self.enabled), build=controller.record),)
        if op in ("snore_count", "snore_time"):
            assert self.value is not None
            return (p.snore_config(op == "snore_count", self.value, build=controller.record),)
        if op == "snore_query":
            return (controller.queries["snore_config"], controller.queries["snore_switch"])
        if op == "alarms":
            return (controller.queries["alarms"],)
        if op == "delete":
            assert self.alarm_id is not None
            return (p.delete_alarm(self.alarm_id, build=controller.record),)
        if op == "toggle":
            assert self.record is not None
            row = (*self.record[:5], (self.record[5] & 0xFE) | int(bool(self.enabled)))
            return (codec.record_20_len(5, 1, 1, row),)
        if op == "cancel_single":
            return p.clock(0, 0)
        if self.action is None and self.record is not None and controller.product is not None:
            action = next(controller.catalog.actions[key] for key in reversed(controller.product.alarms)
                          if controller.catalog.actions[key].short == self.record[4])
            code = action.recovered_short if action.recovered_short is not None else action.short
        else:
            assert self.action is not None
            code = controller.catalog.actions[self.action].short
        if op == "single":
            assert self.when is not None
            now = dt_util.now().replace(second=0, microsecond=0)
            minutes = int(
                (self.when.replace(second=0, microsecond=0).timestamp() - now.timestamp()) / 60
            )
            if minutes <= 0:
                minutes += 1440
            controller._pending_single = {"time": self.when.isoformat(), "action": self.action}
            return p.clock(minutes, code)
        mask = (self.record[5] & 0xFE) if self.weekdays is None and self.record else sum(1 << (7 - day) for day in set(self.weekdays or ()))
        mask |= (self.record[5] & 1) if self.enabled is None and self.record else int(self.enabled is not False)
        number = self.repeat_slot(controller)
        hour = self.when.hour if self.when is not None else self.record[2] if self.record else 0
        minute = self.when.minute if self.when is not None else self.record[3] if self.record else 0
        return (p.repeat_alarm(number, hour, minute, code, mask, build=controller.record),)


def _sleep_operand(value: object) -> int | float | tuple[int | float, ...]:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple)) and all(type(v) in (int, float) for v in value):
        return tuple(value)
    raise vol.Invalid("Choose a number or a list of numbers")


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): vol.In(OPERATIONS),
    vol.Optional("action"): cv.string,
    vol.Optional("datetime"): cv.datetime,
    vol.Optional("alarm_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
    vol.Optional("weekdays"): vol.All(
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
    vol.Optional("alarm_record"): vol.All(vol.ExactSequence((cv.byte,) * 6), vol.Coerce(tuple)),
    vol.Optional("left"): _sleep_operand,
    vol.Optional("right"): _sleep_operand,
}
FIELDS.update(SIDE_FIELD.items())
SCHEMA = vol.Schema(FIELDS)
MLILY_SCHEMA = SCHEMA.extend({vol.Optional("part"): vol.Coerce(int)})
BED_OPERATIONS = (*OPERATIONS[:14], "enable_alarm")
GALAXY_SCHEMA = SCHEMA.extend({vol.Required("operation"): vol.In(BED_OPERATIONS)})


async def handle_goodvibe(call: ServiceCall) -> None:
    await async_import_modules(call.hass, "beds.goodvibe.controller")
    from .controller import GoodVibeController

    request = Request(
        operation=call.data["operation"],
        action=call.data.get("action"),
        when=call.data.get("datetime"),
        alarm_id=call.data.get("alarm_id"),
        weekdays=tuple(call.data["weekdays"]) if "weekdays" in call.data else None,
        enabled=call.data.get("enabled"),
        seconds=call.data.get("seconds"),
        rgb=call.data.get("rgb_color"),
        value=call.data.get("value"),
        part=call.data.get("part"),
        date=call.data.get("date"),
        report_type=call.data["report_type"],
        record=call.data.get("alarm_record"),
        left=call.data.get("left"),
        right=call.data.get("right"),
    )
    plans: dict[tuple[str, str], Request] = {}

    def validate(target: GoodVibeController) -> None:
        if target.profile.key != call.service:
            raise ServiceValidationError("Choose the configuration action for the selected app")
        if target.catalog.key != call.service:
            raise ServiceValidationError("Choose the action for the target's app")
        plans[(target._address.upper(), target.product_key)] = request.plan(target)

    async def execute(target: GoodVibeController) -> None:
        plan = plans.get((target._address.upper(), target.product_key))
        if plan is None:
            raise ServiceValidationError("The Good Vibe Sleep target changed after validation")
        await target.async_execute_goodvibe_request(plan)

    await _preflight_and_execute(
        _call_targets(call),
        GoodVibeController,
        "Good Vibe Sleep configuration",
        execute,
        validate=validate,
    )


def async_register_goodvibe_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "goodvibe", handle_goodvibe, schema=SCHEMA)
    hass.services.async_register(DOMAIN, "mlily", handle_goodvibe, schema=MLILY_SCHEMA)
    hass.services.async_register(DOMAIN, "galaxy", handle_goodvibe, schema=GALAXY_SCHEMA)
