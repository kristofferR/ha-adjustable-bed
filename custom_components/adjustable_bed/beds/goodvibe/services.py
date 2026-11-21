"""Product-gated Good Vibe Sleep configuration and sleep queries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...codec import richmat as codec
from ...const import CONF_PRODUCT_TYPE, CONF_PROFILE_ID, CONF_PROTOCOL_VARIANT, DOMAIN
from ...entity_runtime import controller_side_scope
from ...errors import invalid, rejected
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator, SingleAddressSideCoordinator
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _preflight_and_execute,
)
from ..base import BedController
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
        if controller.catalog.bed is not None and self.operation not in BOB_OPERATIONS:
            raise ValueError("This action is not offered by Power Bob Base")
        if controller.catalog.bed is not None and self.operation == "light_off":
            controller._side()
        operations = BED_OPERATIONS if controller.catalog.key == "galaxy" else OPERATIONS
        if self.operation not in operations:
            raise ValueError("Unknown Good Vibe Sleep action")
        if controller.catalog.reply_gated_menus and self.operation.startswith("snore_"):
            raise ValueError("This bed has no snore settings")
        product = controller.product
        if product is None:
            if controller.catalog.reply_gated_menus and self.operation == "anti_snore" and self.enabled is not None and self.left is None and self.right is None:
                raise ValueError("Enter an anti-snore value for at least one side")
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
                raise ValueError("This sleep sensor does not offer that operation")
            if controller.kind == 2 and self.operation in ("time", "anti_snore", "sensitivity", "init"):
                raise ValueError("This sleep sensor does not offer that operation")
            admitted_parts = (
                (1, 2)
                if self.operation in ("report", "report_allow") or controller.kind == 2
                else (11, 12, 13)
            )
            if not controller.catalog.reply_gated_menus and self.part is not None and self.part not in admitted_parts:
                raise ValueError("Choose a part this sleep sensor offers")
            if (
                self.operation == "report"
                or self.operation == "report_allow"
                and controller.kind == 2
            ):
                if self.date is None or self.part is None or self.report_type not in (1, 2):
                    raise ValueError("Enter a date, a part and a day or month report type")
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
            raise ValueError("Sleep operations run on the separate sleep sensor. Add the sensor as its own device and use them there")
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
                raise ValueError("The bed has not reported that it offers this. Reconnect the bed and try again")
        light_allowed = product.light if controller.catalog.bed is not None and not reported else controller.menu_available("light")
        if self.operation in ("light_color", "light_duration", "light_off") and not light_allowed:
            raise ValueError("This bed model has no light settings")
        if self.operation == "massage_timer" and (
            not product.massage_timer or self.value not in (0, 10, 20, 30)
        ):
            raise ValueError("Choose a massage timer of 0, 10, 20 or 30 minutes on a bed model that has one")
        if self.operation == "light_color" and (
            self.rgb is None or any(type(v) is not int or not 0 <= v <= 255 for v in self.rgb)
        ):
            raise ValueError("Enter a light color as red, green and blue values from 0 to 255")
        eight_color = product.light_display == "deviceBedLightDisplayCircleEightColorValue"
        if self.operation == "light_color" and eight_color and self.rgb not in p.EIGHT_COLORS:
            raise ValueError("Choose one of the eight light colors this bed offers")
        durations = (
            tuple(minute * 60 for minute in controller.catalog.bed.light_minutes)
            if controller.catalog.bed else p.light_durations(product.label.split(" / ")[0], eight_color)
        )
        if self.operation == "light_duration" and self.seconds not in durations:
            raise ValueError("Choose a light duration this bed offers")
        if (
            self.operation in ("single", "cancel_single", "repeat", "delete", "alarms", "toggle", "enable_alarm")
            and not controller.menu_available("alarm")
        ):
            raise ValueError("This bed model has no alarms")
        if self.operation in ("repeat", "delete", "alarms", "toggle", "enable_alarm") and not product.repeat_alarm:
            raise ValueError("This bed model has no repeating alarms")
        if controller.catalog.reply_gated_menus and product.repeat_alarm and self.operation in ("single", "cancel_single"):
            raise ValueError("This bed model sets alarms with the repeating alarm operation")
        if self.operation in ("single", "repeat"):
            record_edit = controller.catalog.reply_gated_menus and self.operation == "repeat" and self.record is not None
            if (
                (self.action not in product.alarms and not (
                    record_edit and self.action is None
                ))
                or (self.when is None and not record_edit)
                or (self.when is not None and self.when.utcoffset() is None)
            ):
                raise ValueError("Choose an alarm action this bed offers and enter the alarm time with its time zone")
        if self.alarm_id is not None and not 1 <= self.alarm_id <= 7:
            raise ValueError("Alarm number must be 1–7")
        if self.operation == "enable_alarm":
            if self.enabled is None or self.alarm_id is None:
                raise ValueError("Choose an alarm number and whether the alarm is on")
            self.observed_alarm(controller)
        if self.operation == "delete" and self.alarm_id is None:
            raise ValueError("Choose the alarm to delete")
        if self.record is not None and (
            len(self.record) != 6 or any(type(v) is not int or not 0 <= v <= 255 for v in self.record)
        ):
            raise ValueError("An alarm record has six byte fields")
        if self.record is not None and self.operation in ("repeat", "toggle"):
            if not 1 <= self.record[0] <= 7 or self.alarm_id not in (None, self.record[0]):
                raise ValueError("Enter an alarm record with an alarm number from 1 to 7. An alarm number entered separately must match it")
        if self.operation == "toggle" and (self.record is None or self.enabled is None):
            raise ValueError("Enter the alarm record from the alarm list and whether the alarm is on")
        if self.operation == "repeat" and self.alarm_id is None and self.record is None and (
            reported or controller.catalog.bed is None
        ):
            self.repeat_slot(controller)
        if any(day not in range(7) for day in self.weekdays or ()):
            raise ValueError("Invalid weekday")
        if self.operation == "repeat" and self.record is not None and self.action is None:
            if not any(controller.catalog.actions[key].short == self.record[4] for key in product.alarms):
                raise ValueError("The alarm record has an unknown alarm action. Choose an action")
        if self.operation in ("snore_switch", "snore_count", "snore_time", "snore_query") and (
            not controller.snore_available
        ):
            raise ValueError("This bed model has no snore settings")
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
            raise ValueError("Read the alarm list first, then turn the alarm on or off")
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
            raise ValueError("Choose an alarm number or enter an alarm record. This bed does not report its full alarm list, so a free alarm cannot be picked for you")
        records = controller.choices.events.get("repeat_alarms", {})
        occupied = set(records) if isinstance(records, dict) else set()
        number = next((n for n in range(1, 8) if str(n) not in occupied), None)
        if number is None:
            raise ValueError("All seven alarms are in use. Delete one, or choose the alarm number to replace")
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
            if controller.catalog.bed is not None:
                return (codec.calendar(dt_util.now(), build=controller.record),)
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


def _actions(operations: tuple[str, ...]) -> vol.In:
    """Operations an action offers; the clock belongs to the shared Set bed clock action."""
    return vol.In(tuple(operation for operation in operations if operation != "sync"))


FIELDS: dict[vol.Marker, object] = {
    vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
    vol.Required("operation"): _actions(OPERATIONS),
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
GALAXY_SCHEMA = SCHEMA.extend({vol.Required("operation"): _actions(BED_OPERATIONS)})
BOB_OPERATIONS = ("repeat", "delete", "alarms", "sync", "light_color", "light_duration", "light_off")
BOB_SCHEMA = vol.Schema({
    key: value for key, value in FIELDS.items()
    if str(key.schema) in (
        CONF_DEVICE_ID, "operation", "action", "datetime", "alarm_id", "weekdays", "enabled",
        "seconds", "rgb_color", "side",
    )
}).extend({vol.Required("operation"): _actions(BOB_OPERATIONS)})


async def handle_goodvibe(call: ServiceCall) -> None:
    targets = _call_targets(call)
    admissions = [_capture_command_admission(parent, side) for parent, side in targets]
    # Freeze every physical ownership token before the first import or preflight.
    physical = [child for parent, side in targets for child in _command_targets(parent, side)]
    sessions = {
        owner: (
            owner.controller, owner.client, owner.connection_generation, owner.cancel_counter,
            (owner.address, owner.bed_type, *(owner.entry.options.get(key, owner.entry.data.get(key))
              for key in (CONF_PROTOCOL_VARIANT, CONF_PRODUCT_TYPE, CONF_PROFILE_ID))),
        )
        for child in physical
        for owner in (child.inner if isinstance(child, SingleAddressSideCoordinator) else child,)
    } if call.service == "bobpowerbase" else {}
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
        report_type=call.data.get("report_type", 1),
        record=call.data.get("alarm_record"),
        left=call.data.get("left"),
        right=call.data.get("right"),
    )
    plans: dict[tuple[str, str], Request] = {}

    def validate(target: GoodVibeController) -> None:
        if target.profile.key != call.service:
            raise invalid("wrong_action_for_bed")
        if target.catalog.key != call.service:
            raise invalid("wrong_action_for_bed")
        plans[(target._address.upper(), target.product_key)] = request.plan(target)

    if call.service == "bobpowerbase":
        def check_admission(*, reported: bool = False) -> bool:
            if any(_capture_command_admission(parent, side) != admission
                   for (parent, side), admission in zip(targets, admissions, strict=True)) or physical != [
                       child for parent, side in targets for child in _command_targets(parent, side)
                   ]:
                raise invalid("action_stopped")
            for owner, (controller, client, generation, command_generation, route) in sessions.items():
                current_route = (owner.address, owner.bed_type, *(owner.entry.options.get(key, owner.entry.data.get(key))
                    for key in (CONF_PROTOCOL_VARIANT, CONF_PRODUCT_TYPE, CONF_PROFILE_ID)))
                if owner.cancel_counter != command_generation or current_route != route:
                    raise invalid("bed_changed")
                # Reconnect may replace the controller and link. Replacement
                # within the same still-live physical generation is stale work.
                if client is not None and client.is_connected and owner.connection_generation == generation and (
                    owner.controller is not controller or owner.client is not client
                ):
                    raise invalid("bed_changed")
            if reported:
                for child in physical:
                    controller = child.controller
                    # A sequential peer can be intentionally disconnected;
                    # its own dispatch must obtain and validate a fresh reply.
                    if controller is not None and controller.client is not None and controller.client.is_connected:
                        if not isinstance(controller, GoodVibeController) or controller.catalog.key != "bobpowerbase":
                            raise invalid("bed_changed")
                        owner = child.inner if isinstance(child, SingleAddressSideCoordinator) else child
                        if controller.product_key != sessions[owner][4][2]:
                            raise invalid("bed_changed")
                        with controller_side_scope(child):
                            controller._current_link()
                            request.validate(controller)
            return True

        def live_plan(controller: BedController) -> Request:
            check_admission()
            if not isinstance(controller, GoodVibeController) or controller.catalog.key != "bobpowerbase":
                raise invalid("action_for_other_beds", beds="Power Bob Base beds")
            route = sessions.get(controller._coordinator)
            if route is None or controller.product_key != route[4][2]:
                raise invalid("bed_changed")
            controller._current_link()
            return request.plan(controller)

        check_admission()
        # Validate every offline product and operand before startup can write.
        for child in physical:
            controller = child.capability_controller
            if not isinstance(controller, GoodVibeController) or controller.catalog.key != "bobpowerbase":
                raise invalid("action_for_other_beds", beds="Power Bob Base beds")
            owner = child.inner if isinstance(child, SingleAddressSideCoordinator) else child
            if controller.product_key != sessions[owner][4][2]:
                raise invalid("bed_changed")
            try:
                with controller_side_scope(child):
                    request.validate(controller, reported=False)
            except ValueError as error:
                raise rejected(error) from error

        # Query through each topology's ordinary connection lane. A sequential
        # pair may release the first link before validating the second.
        for (parent, side), admission in zip(targets, admissions, strict=True):
            for child in _command_targets(parent, side):
                async def inspect(controller: BedController) -> bool:
                    try:
                        check_admission()
                        if isinstance(controller, GoodVibeController):
                            await controller.async_prepare_goodvibe_request(request, admitted=check_admission)
                        live_plan(controller)
                    except ValueError as error:
                        raise rejected(error) from error
                    return True

                async def query(target=child) -> None:
                    if not await target.async_execute_controller_query(inspect, cancel_running=False, run_if=check_admission):
                        raise invalid("action_stopped")

                check_admission()
                if isinstance(parent, PairedBedCoordinator):
                    child_side = next(key for key, target in parent.children.items() if target is child)
                    await parent.async_run_child_operation(
                        "Power Bob Base live preflight", query, side=child_side, cancel_running=False,
                        resources=admission.resources,
                        expected_pair_generations=admission.expected_pair_generations,
                        expected_stop_epochs=admission.expected_stop_epochs,
                    )
                else:
                    await query()

        async def execute_bob(target: GoodVibeController) -> None:
            check_admission()
            await target.async_prepare_goodvibe_request(request, admitted=check_admission)
            plan = live_plan(target)
            owner, link = target._coordinator, target._current_link()
            generation = owner.connection_generation

            def dispatch() -> None:
                check_admission(reported=True)
                if owner.controller is not target or owner.connection_generation != generation or target._current_link() is not link:
                    raise invalid("bed_changed")
                plan.validate(target)

            await target.async_execute_goodvibe_request(plan, dispatch=dispatch)

        await _execute_preflighted(
            targets, [], _family_command(GoodVibeController, execute_bob),
            resource="configuration", admissions=admissions,
        )
        return

    async def execute(target: GoodVibeController) -> None:
        plan = plans.get((target._address.upper(), target.product_key))
        if plan is None:
            raise invalid("bed_changed")
        await target.async_execute_goodvibe_request(plan)

    await _preflight_and_execute(
        targets,
        GoodVibeController,
        execute,
        validate=validate,
        admissions=admissions,
    )


def async_register_goodvibe_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "goodvibe", handle_goodvibe, schema=SCHEMA)
    hass.services.async_register(DOMAIN, "mlily", handle_goodvibe, schema=MLILY_SCHEMA)
    hass.services.async_register(DOMAIN, "galaxy", handle_goodvibe, schema=GALAXY_SCHEMA)
    hass.services.async_register(DOMAIN, "bobpowerbase", handle_goodvibe, schema=BOB_SCHEMA)
