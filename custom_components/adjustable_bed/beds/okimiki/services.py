"""Product-gated Okimiki actions with all-target admission before lazy imports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ...alarm import WEEKDAYS
from ...codec import richmat as codec
from ...const import CONF_PROTOCOL_VARIANT, DOMAIN, PAIR_CONNECTION_MODE_SEQUENTIAL
from ...import_executor import async_import_modules
from ...paired_coordinator import PairedBedCoordinator
from ...profiles.okimiki import CONTROLS
from ...services import (
    DEVICE_IDS,
    SIDE_FIELD,
    _call_targets,
    _capture_command_admission,
    _command_targets,
    _execute_preflighted,
    _family_command,
    _preflight_capability,
    _release_preflighted,
)
from . import protocol as p

if TYPE_CHECKING:
    from ...paired_coordinator import BedChild
    from ..goodvibe.controller import Link
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
# Service response budget, independent of the bed's query/write timing.
CAPABILITY_REPLY_TIMEOUT_S = 3.0


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
                raise ValueError("The bed has not reported light settings. Reconnect the bed and try again")
            if op == "light_duration" and (
                type(self.seconds) is not int or not 0 <= self.seconds <= 900
            ):
                raise ValueError("Choose 0 to 900 seconds, zero keeps the light on")
            if op == "light_color" and (
                self.rgb is None
                or len(self.rgb) != 3
                or any(type(v) is not int or not 0 <= v <= 255 for v in self.rgb)
            ):
                raise ValueError("Enter a light color as red, green and blue values from 0 to 255")
        elif op == "sync":
            if controller.model.alarm == "none":
                raise ValueError("This product has no clock")
        else:
            if not controller.menu_available("alarm"):
                raise ValueError("The bed has not reported alarm settings. Reconnect the bed and try again")
            if (op in ("single", "cancel_single")) != (controller.model.alarm == "single"):
                raise ValueError("Choose the alarm operation this bed model offers")
            if self.mode is not None and (
                self.mode not in MODES
                or controller.model.alarm == "single"
                and self.mode != "lounge"
            ):
                raise ValueError("Choose an alarm mode offered by this product")
            if op == "single" and (self.when is None or self.when.utcoffset() is None):
                raise ValueError("Enter the alarm time with its time zone")
            if op == "repeat":
                if self.alarm_id is None:
                    raise ValueError("Choose an alarm number from 1 to 7")
                if self.record is None and (self.when is None or self.mode is None):
                    raise ValueError("A new alarm needs a time and mode")
                if self.when is not None and self.when.utcoffset() is None:
                    raise ValueError("Enter the alarm time with its time zone")
            if self.alarm_id is not None and not 1 <= self.alarm_id <= 7:
                raise ValueError("Choose an alarm number from 1 to 7")
            if op in ("enable", "delete") and self.alarm_id is None:
                raise ValueError("Choose the number of an alarm in the alarm list")
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
                    raise ValueError("Read the alarm list again before changing this alarm")
            if (
                op == "repeat"
                and self.record is None
                and (
                    self.alarm_id in controller._stale_alarm_ids
                    or any(row.id == self.alarm_id for row in controller._alarms)
                )
            ):
                raise ValueError("Read the alarm list again before changing this alarm")

    def plan(self, controller: OkimikiController) -> Request:
        """Keep the actual returned reserved byte and physical receiver's record."""
        request = self
        if self.alarm_id is not None and self.operation in ("repeat", "enable", "delete"):
            record = next(
                (row for row in reversed(controller._alarms) if row.id == self.alarm_id), None
            )
            if record is None and self.operation != "repeat":
                raise ValueError("Read the bed's alarm list before changing or deleting an alarm")
            if record is not None:
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
            assert self.alarm_id is not None
            number = row.id if row else self.alarm_id
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
    # The clock belongs to the shared Set bed clock action.
    vol.Required("operation"): vol.In(tuple(op for op in OPERATIONS if op != "sync")),
    vol.Optional("control"): vol.In(CONTROLS),
    vol.Optional("duration_ms", default=1000): vol.All(cv.positive_int, vol.Range(max=60000)),
    vol.Optional("datetime"): cv.datetime,
    vol.Optional("alarm_id"): vol.All(cv.positive_int, vol.Range(min=1, max=7)),
    vol.Optional("mode"): vol.In(MODES),
    vol.Optional("weekdays"): vol.All(cv.ensure_list, [vol.In(WEEKDAYS)]),
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("seconds"): vol.All(cv.positive_int, vol.Range(max=900)),
    vol.Optional("rgb_color"): vol.All(vol.ExactSequence((cv.byte,) * 3), vol.Coerce(tuple)),
}
FIELDS.update(SIDE_FIELD.items())


@dataclass(frozen=True, slots=True)
class _PreparedPlan:
    request: Request
    owner: BedChild
    controller: OkimikiController
    link: Link | None


async def handle_okimiki(call: ServiceCall) -> None:
    targets = _call_targets(call)
    movement = call.data["operation"] in ("press", "save")
    resource = "movement" if movement else "configuration"
    physical_routes = [
        (parent, side, child, child.address.upper(), child.entry.data.get(CONF_PROTOCOL_VARIANT))
        for parent, side in targets
        for child in _command_targets(parent, side)
    ]
    physical_targets = [(parent, child) for parent, _, child, _, _ in physical_routes]
    sequential_owners = {
        id(child)
        for parent, side, child, _, _ in physical_routes
        if isinstance(parent, PairedBedCoordinator)
        and parent.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
        and len(_command_targets(parent, side)) > 1
    }
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
        days=(
            tuple(WEEKDAYS.index(day) for day in call.data["weekdays"])
            if "weekdays" in call.data
            else None
        ),
        enabled=call.data.get("enabled"),
        seconds=call.data.get("seconds"),
        rgb=call.data.get("rgb_color"),
    )
    plans: dict[tuple[str, str], _PreparedPlan] = {}
    # An observed slot is a reason to request fresh data, never permission to
    # reuse its old bytes after a reconnect. Explicit new-slot IDs stay required.
    observed_owners = {
        id(child)
        for _, child in physical_targets
        if isinstance(previous := child.capability_controller, OkimikiController)
        and any(row.id == request.alarm_id for row in previous._alarms)
    }

    def check_owner(controller: OkimikiController) -> None:
        # An invalidated second owner must also stop the first concurrent side
        # before its requested mutation, not merely fail its own later callback.
        if any(
            address != child.address.upper()
            or product != child.entry.data.get(CONF_PROTOCOL_VARIANT)
            or not any(current is child for current in _command_targets(parent, side))
            for parent, side, child, address, product in physical_routes
        ) or not any(
            child is controller._coordinator
            and address == child.address.upper() == controller._address.upper()
            and (product is None or product == controller.product_key)
            for _, _, child, address, product in physical_routes
        ):
            raise ValueError("The bed's connection changed while the action was starting. Try again")

    def validate(controller: OkimikiController) -> None:
        check_owner(controller)
        plans[(controller._address.upper(), controller.product_key)] = _PreparedPlan(
            request.plan(controller), controller._coordinator, controller, controller._link
        )

    live_validation = not movement and request.operation != "sync"

    async def wait_for_capability(
        controller: OkimikiController, expected_record: p.Alarm | None = None
    ) -> None:
        check_owner(controller)
        menu = "light" if request.operation.startswith("light_") else "alarm"
        if menu == "alarm" and controller.model.alarm == "none":
            return
        link = controller._current_link()

        def check_session() -> None:
            check_owner(controller)
            if controller._current_link() is not link:
                raise ValueError("The bed's connection changed while the action was starting. Try again")

        def observed_record() -> p.Alarm | None:
            return next(
                (row for row in reversed(controller._alarms) if row.id == request.alarm_id), None
            )

        need_record = (
            expected_record is not None
            or request.operation in ("enable", "delete")
            or (
                request.operation == "repeat"
                and (
                    request.when is None
                    or request.mode is None
                    or id(controller._coordinator) in observed_owners
                )
            )
        )
        try:
            async with asyncio.timeout(CAPABILITY_REPLY_TIMEOUT_S):
                while not controller.menu_available(menu):
                    check_session()
                    controller._menus_changed.clear()
                    await controller._menus_changed.wait()
                if need_record:
                    if observed_record() is None or request.alarm_id in controller._stale_alarm_ids:
                        # Existing proven query, through normal pacing and the
                        # current command admission. Never replay a cached record.
                        await controller.execute_request(Request("alarms"))
                    while (
                        observed_record() is None or request.alarm_id in controller._stale_alarm_ids
                    ):
                        check_session()
                        controller._menus_changed.clear()
                        await controller._menus_changed.wait()
                    if expected_record is not None and observed_record() != expected_record:
                        raise ValueError("The alarm changed on the bed while the action was starting. Read the alarm list and try again")
                check_session()
        except TimeoutError:
            raise ValueError(
                "The bed did not report its settings in time. Try again"
            ) from None

    prepared = await _preflight_capability(
        targets, OkimikiController, validate=None if live_validation else validate
    )
    if live_validation and len(physical_targets) > 1:
        # Session menus and alarm records cannot be validated on an offline controller.
        # Connect through the normal scheduler/pair lane, but finish EVERY plan
        # before sending any requested settings writes.
        prepared.extend(physical_targets)

        async def prepare(controller: OkimikiController) -> None:
            await wait_for_capability(controller)
            validate(controller)

        await _execute_preflighted(
            targets,
            prepared,
            _family_command(OkimikiController, prepare),
            skip_disconnect=True,
            resource=resource,
            admissions=admissions,
        )
        if {address for address, _ in plans} != {
            child.address.upper() for _, child in physical_targets
        }:
            await _release_preflighted(prepared)
            return  # STOP interrupted at least one target's validation.

    # Only the sequential topology's completed validation cycle deliberately
    # released these links. A replacement owner or an unrelated reconnect gets
    # no exemption from the original link fence.
    sequential_handoffs = {
        key
        for key, plan in plans.items()
        if id(plan.owner) in sequential_owners
        and not plan.owner.is_connected
        and plan.controller._link is None
        and plan.link is not None
        and not plan.link.client.is_connected
    }

    async def execute(controller: OkimikiController) -> None:
        check_owner(controller)
        if any(
            other.request.record is not None
            and other_key not in sequential_handoffs
            and (
                other.owner.controller is not other.controller
                or other.controller._link is not other.link
            )
            for other_key, other in plans.items()
        ):
            raise ValueError("The bed's connection changed while the action was starting. Try again")
        key = (controller._address.upper(), controller.product_key)
        plan = plans.get(key)
        if live_validation and len(physical_targets) == 1:
            await wait_for_capability(controller)
            validate(controller)
            plan = plans.get(key)
        if plan is None or plan.owner is not controller._coordinator:
            raise ValueError("The bed's connection changed while the action was starting. Try again")
        changed_link = plan.link is not None and controller._link is not plan.link
        if changed_link and (not live_validation or plan.request.record is not None):
            if key not in sequential_handoffs or plan.request.record is None:
                raise ValueError("The bed's connection changed while the action was starting. Try again")
            await wait_for_capability(controller, plan.request.record)
            # Rebuild only from this live receiver's matching immutable tuple.
            rebuilt = request.plan(controller)
            if rebuilt.record != plan.request.record:
                raise ValueError("The alarm changed on the bed while the action was starting. Read the alarm list and try again")
            await controller.execute_request(rebuilt)
            return
        if live_validation:
            await wait_for_capability(controller)
        if not live_validation and controller._link is not plan.link and plan.link is not None:
            raise ValueError("The bed's connection changed while the action was starting. Try again")
        # Caller-only settings can cross a sequential pair's link switch;
        # execute_request rechecks the new session's menus and alarm slots.
        await controller.execute_request(plan.request)

    await _execute_preflighted(
        targets,
        prepared,
        _family_command(OkimikiController, execute),
        cancel_running=movement,
        resource=resource,
        admissions=admissions,
    )


def register_services(hass: HomeAssistant) -> None:
    hass.services.async_register(DOMAIN, "okimiki", handle_okimiki, schema=vol.Schema(FIELDS))
