"""BetterLiving2 session/gesture extension of the shared Keeson runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_HIDDEN, CARD_MASSAGE
from ...command_scheduler import CommandContext, current_command_context
from ...const import CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...profiles import betterliving2 as app
from ...profiles.keeson import BETTERLIVING2, Preset
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .betterliving2_admission import current_selection
from .betterliving2_state import (
    AlarmView,
    alarm_fields,
    consume_p1,
    massage_fields,
    restore_actions,
)
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

ALARM: Final = StateKey[str | None]("betterliving2_alarm_selection")
HOUR: Final = StateKey[int | None]("betterliving2_alarm_hour")
MINUTE: Final = StateKey[int | None]("betterliving2_alarm_minute")
WEEK: Final = StateKey[int | None]("betterliving2_alarm_week")
ACTION: Final = StateKey[str | None]("betterliving2_alarm_action")
LEVELS: Final = {
    zone: StateKey[int | None](f"betterliving2_massage_{zone}")
    for zone in ("head", "feet", "wave", "timer")
}
# HA safety deadlines, not claimed Android timings or hardware measurements.
WRITE_TIMEOUT: Final = 3.0
LOCK_TIMEOUT: Final = 3.0


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    address: str
    variant: str
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    manufacturer: BleakGATTCharacteristic | None = None


@dataclass(frozen=True, slots=True)
class AlarmPlan:
    link: Link | None
    address: str
    variant: str
    layout: str
    frame: bytes
    selected: AlarmView


async def pause(seconds: float, event: asyncio.Event) -> bool:
    if event.is_set():
        return True
    if seconds > 0:
        try:
            await asyncio.wait_for(event.wait(), seconds)
            return True
        except TimeoutError:
            pass
    return event.is_set()


async def drain(task: asyncio.Task[None]) -> None:
    """Complete bounded owned writes even through repeated caller cancellation."""
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
        except Exception:
            break
    task.result()
    if interrupted:
        raise asyncio.CancelledError


class BetterLiving2Controller(KeesonController):
    """Family motor/preset APIs with app-specific, captured-session operations."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, variant: str, layout: str) -> None:
        key = f"{variant}_{layout}"
        if key not in BETTERLIVING2:
            raise ValueError("Choose a BetterLiving2 P1/P2/P3 route and 2/3-motor layout")
        super().__init__(coordinator, variant=BETTERLIVING2[key].key)
        self.wire: app.Protocol = "P1" if variant == "p1" else "P2" if variant == "p2" else "P3"
        self.layout = layout
        self._link: Link | None = None
        self._wire_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()
        self._serial = 0
        self._notify_token: object | None = None
        self._notify_stop: asyncio.Task[None] | None = None
        self._pending_alarm: bytes | None = None
        self._active_cancel: asyncio.Event | None = None
        self._receive_kind = "alarm"
        self._view, self._saved = AlarmView(), AlarmView()
        self._observed_alarm = False
        self._active_recall: str | None = None
        self._has_connected = False
        self._manufacturer_text: str | None = None
        self._manufacturer_hint: app.Protocol | None = None
        self._completed_cleanup: tuple[Link, CommandContext] | None = None

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "betterliving2_wire": self.wire,
            "betterliving2_layout": self.layout,
            "betterliving2_manufacturer_hint": self._manufacturer_hint,
            "betterliving2_automatic_route_selection": False,
            "alarm_selection": asdict(self._view),
            "alarm_preferences": asdict(self._saved),
            "alarm_response_received": self._observed_alarm,
            "massage_settings": {
                zone: self._coordinator.controller_state.get(key) for zone, key in LEVELS.items()
            },
        }

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.wire != "P1"

    @property
    def exposes_discrete_light_as_light(self) -> bool:
        return self.wire == "P1"

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = tuple(
            replace(
                spec,
                scheduler_resource="motor:*",
                hold=ControllerMotorHoldSpec(
                    f"{name}_up",
                    f"{name}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                ),
            )
            for spec, name in zip(super().motor_control_specs, ("back", "feet"), strict=True)
        )
        return (
            *specs,
            MotorControlSpec(
                key="both",
                translation_key="betterliving2_all_sections",
                open_fn=lambda c: require(c).combined(True),
                close_fn=lambda c: require(c).combined(False),
                stop_fn=lambda c: c.stop_all(),
                scheduler_resource="motor:*",
                hold=ControllerMotorHoldSpec(
                    "combined_up",
                    "combined_down",
                    stop_scope="side",
                    press_hold_ms=None,
                ),
            ),
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return ("back_up", "back_down", "feet_up", "feet_down", "combined_up", "combined_down")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = [
            ControllerButtonSpec(
                "betterliving2_program_zero_g",
                "Save Zero Gravity",
                lambda c: require(c).program("zero_g"),
                "mdi:content-save",
                requires_confirmation=True,
            ),
        ]
        if self.wire == "P1":
            buttons.extend(
                (
                    ControllerButtonSpec(
                        "betterliving2_stop_preset",
                        "Stop preset",
                        lambda c: require(c).tap(app.P1_PRESET_STOP),
                    ),
                    ControllerButtonSpec(
                        "betterliving2_massage_off",
                        "Stop massage",
                        lambda c: require(c).massage_pair(0, 0),
                        card=CARD_MASSAGE,
                    ),
                )
            )
        else:
            buttons.extend(
                ControllerButtonSpec(
                    f"betterliving2_massage_{name}",
                    app.MASSAGE_LABELS[name],
                    lambda c, word=word: require(c).massage_step(word),
                    card=CARD_MASSAGE,
                )
                for name, word in app.STEP_MASSAGE.items()
            )
        return tuple(replace(button, translation_key=button.key) for button in buttons)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.wire != "P1":
            return ()
        return tuple(
            ControllerNumberSpec(
                f"betterliving2_massage_{zone}",
                f"betterliving2_massage_{zone}",
                LEVELS[zone],
                0,
                3,
                1,
                lambda c, value, zone=zone: require(c).set_level(zone, value),
                card=CARD_MASSAGE,
            )
            for zone in ("head", "feet", "wave")
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                str(key),
                str(key),
                key,
                "mdi:vibrate",
                entity_registry_enabled_default=zone in {"head", "feet"},
                card=CARD_MASSAGE if zone in {"head", "feet"} else CARD_HIDDEN,
            )
            for zone, key in LEVELS.items()
            if self.wire != "P1"
        )

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"alarm_preferences": asdict(self._saved), "has_connected": self._has_connected}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        connected = state.get("has_connected", False)
        if type(connected) is not bool:
            raise ValueError("Invalid BetterLiving2 startup history")
        self._has_connected = connected
        fields = state.get("alarm_preferences")
        if not isinstance(fields, dict):
            return
        hour, minute = fields.get("hour"), fields.get("minute")
        if not (
            hour is None or type(hour) is int and 0 <= hour <= (24 if self.wire == "P1" else 255)
        ) or not (
            minute is None
            or type(minute) is int
            and 0 <= minute <= (60 if self.wire == "P1" else 255)
        ):
            raise ValueError("Invalid saved BetterLiving2 alarm time")
        massage = fields.get("massage", False)
        a = fields.get("memory_a", False)
        b = fields.get("memory_b", False)
        if not isinstance(massage, bool) or not isinstance(a, bool) or not isinstance(b, bool):
            raise ValueError("Invalid saved BetterLiving2 alarm actions")
        massage, a, b = restore_actions(massage, a, b)
        self._saved = AlarmView(hour=hour, minute=minute, massage=massage, memory_a=a, memory_b=b)
        weeks = fields.get("weeks", [])
        selected = fields.get("switch_selected", False)
        if (
            type(selected) is not bool
            or not isinstance(weeks, (tuple, list))
            or any(type(day) is not int or not 0 <= day <= 6 for day in weeks)
        ):
            raise ValueError("Invalid saved BetterLiving2 alarm selection")
        self._saved = replace(self._saved, switch_selected=selected, weeks=tuple(weeks))
        self._view = replace(self._saved, controls_enabled=not selected)

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        stored = self._coordinator.entry.data
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address.upper() != link.address
            or stored.get(CONF_PROTOCOL_VARIANT) != link.variant
            or str(stored.get(CONF_PRODUCT_TYPE)) != self.layout
        ):
            raise ConnectionError("BetterLiving2 route/session changed or disconnected")
        return link

    @property
    def _cancel(self) -> asyncio.Event:
        context = current_command_context()
        return context.cancel_event if context is not None else self._coordinator.cancel_command

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("BetterLiving2 is disconnected")
        write_service, write_uuid, notify_service, notify_uuid = app.GATT[self.wire]
        services = {service.uuid.lower(): service for service in client.services}
        write = (
            services[write_service].get_characteristic(write_uuid)
            if write_service in services
            else None
        )
        notify = (
            services[notify_service].get_characteristic(notify_uuid)
            if notify_service in services
            else None
        )
        if (
            write is None
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError("BetterLiving2 requires its selected write and notification roles")
        if not {"write", "write-without-response"}.intersection(write.properties):
            raise ValueError("BetterLiving2 characteristic is not writable")
        self._link = Link(
            client,
            self._coordinator.address.upper(),
            self.wire.lower(),
            write,
            notify,
            "write" in write.properties,
            services[app.MANUFACTURER_SERVICE].get_characteristic(app.MANUFACTURER_CHARACTERISTIC)
            if app.MANUFACTURER_SERVICE in services
            else None,
        )

        selection = current_selection()
        if selection is not None:
            selection.connected(self)

    async def _send(
        self,
        link: Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        serial: int | None = None,
        deadline: float | None = None,
        on_write: Callable[[], None] | None = None,
        cleanup: bool = False,
        external_cancel: asyncio.Event | None = None,
    ) -> None:
        async with asyncio.timeout(LOCK_TIMEOUT):
            async with self._wire_lock:
                self._live(link)
                if serial is not None and serial != self._serial:
                    raise ConnectionError("BetterLiving2 command owner changed")
                if cancel.is_set() or external_cancel is not None and external_cancel.is_set():
                    return
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    return
                selection = current_selection()
                if selection is not None and not cleanup:
                    selection.check(self)

                async def write() -> None:
                    self._live(link)
                    if (
                        cancel.is_set()
                        or (external_cancel is not None and external_cancel.is_set())
                        or (deadline is not None and asyncio.get_running_loop().time() >= deadline)
                    ):
                        return
                    if serial is not None and serial != self._serial:
                        raise ConnectionError("BetterLiving2 command owner changed")
                    if selection is not None and not cleanup:
                        selection.check(self)
                    if on_write is not None:
                        on_write()
                    self._record_command_trace(
                        link.write.uuid, frame, response=link.response, characteristic=link.write
                    )
                    await link.client.write_gatt_char(link.write, frame, response=link.response)

                async with asyncio.timeout(WRITE_TIMEOUT):
                    writing = asyncio.create_task(write())
                    interrupted = asyncio.create_task(cancel.wait())
                    try:
                        done, _ = await asyncio.wait(
                            (writing, interrupted), return_when=asyncio.FIRST_COMPLETED
                        )
                        if writing in done:
                            await writing
                    finally:
                        writing.cancel()
                        interrupted.cancel()

                        async def settle() -> None:
                            await asyncio.gather(writing, interrupted, return_exceptions=True)

                        await drain(asyncio.create_task(settle()))
                self._live(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._cancel
        deadline = asyncio.get_running_loop().time() + max(1, repeat_count) * repeat_delay_ms / 1000
        for index in range(repeat_count):
            if cancel.is_set() or index and asyncio.get_running_loop().time() >= deadline:
                return
            await self._send(link, command, cancel)
            if index + 1 < repeat_count and await pause(repeat_delay_ms / 1000, cancel):
                return

    async def _cleanup(
        self, link: Link, count: int, serial: int, context: CommandContext | None = None
    ) -> None:
        async def send() -> None:
            failure: Exception | None = None
            for index in range(count):
                if index:
                    await asyncio.sleep(app.RELEASE_MS / 1000)
                try:
                    await self._send(
                        link,
                        app.command(self.wire, 0),
                        asyncio.Event(),
                        serial=serial,
                        cleanup=True,
                    )
                except Exception as err:
                    failure = failure or err
            if failure:
                raise failure
            if context is not None:
                context.cleanup_stop_sent = True
                self._completed_cleanup = (link, context)

        await drain(asyncio.create_task(send()))

    async def _run(
        self,
        frames: tuple[bytes, ...],
        *,
        duration_ms: int = 0,
        interval_ms: int = 100,
        releases: int = 0,
        recall: bool = False,
        expected: Link | None = None,
        receive_kind: str | None = None,
        cancel_override: asyncio.Event | None = None,
    ) -> None:
        link = self._live(expected)
        external_cancel = self._cancel if cancel_override is None else cancel_override
        cancel = asyncio.Event()
        start = asyncio.get_running_loop().time()
        deadline = start + min(duration_ms, app.MOVEMENT_LIMIT_MS) / 1000 if duration_ms else None
        phase = asyncio.timeout_at(deadline if deadline is not None else start + LOCK_TIMEOUT)
        acquired = admitted = reached_wire = False
        serial = self._serial
        context = current_command_context()
        bridge: asyncio.Task[None] | None = None

        def on_write() -> None:
            nonlocal reached_wire
            reached_wire = True

        async def forward_cancel() -> None:
            await external_cancel.wait()
            cancel.set()

        try:
            async with phase:
                pending = self._notify_stop
                if pending is not None:
                    try:
                        if deadline is None:
                            await drain(pending)
                        else:
                            # This cleanup belongs to the previous observer. An
                            # expired, unadmitted hold neither cancels nor owns it.
                            await asyncio.shield(pending)
                    finally:
                        if pending.done() and self._notify_stop is pending:
                            self._notify_stop = None
                await self._operation_lock.acquire()
                acquired = True
                self._live(link)
                if external_cancel.is_set():
                    return
                self._serial += 1
                serial = self._serial
                admitted = True
                self._active_cancel = cancel
                self._completed_cleanup = None
                bridge = asyncio.create_task(forward_cancel())
                if receive_kind:
                    self._receive_kind = receive_kind
                if deadline is None:
                    phase.reschedule(None)
                for frame in frames:
                    await self._send(
                        link,
                        frame,
                        cancel,
                        serial=serial,
                        deadline=deadline,
                        on_write=on_write,
                        external_cancel=external_cancel,
                    )
                if deadline is not None:
                    while not await pause(
                        min(
                            interval_ms / 1000, max(0, deadline - asyncio.get_running_loop().time())
                        ),
                        cancel,
                    ):
                        if asyncio.get_running_loop().time() >= deadline:
                            break
                        await self._send(
                            link,
                            frames[-1],
                            cancel,
                            serial=serial,
                            deadline=deadline,
                            on_write=on_write,
                            external_cancel=external_cancel,
                        )
                if recall:
                    await pause(app.RECALL_RELEASE_MS / 1000, cancel)
        except TimeoutError:
            if not phase.expired() or deadline is None:
                raise
        finally:
            try:
                if bridge is not None:
                    bridge.cancel()

                    async def settle_bridge(task: asyncio.Task[None]) -> None:
                        await asyncio.gather(task, return_exceptions=True)

                    await drain(asyncio.create_task(settle_bridge(bridge)))
            finally:
                try:
                    if admitted and releases and (reached_wire or not frames):
                        await self._cleanup(link, releases, serial, context)
                finally:
                    if admitted and self._serial == serial:
                        self._active_cancel = None
                    if acquired:
                        self._operation_lock.release()

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
            return
        axes = {"head": "back", "feet": "feet"}
        if motor not in axes:
            raise ValueError("BetterLiving2 has no separately proven third axis")
        interval = app.LAYOUTS[self.layout].refresh_ms
        await self.hold_control(
            f"{axes[motor]}_{'up' if direction else 'down'}",
            self._coordinator.motor_pulse_count * interval,
        )

    async def combined(self, up: bool) -> None:
        interval = app.LAYOUTS[self.layout].refresh_ms
        await self.hold_control(
            f"combined_{'up' if up else 'down'}", self._coordinator.motor_pulse_count * interval
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError("Choose a proven BetterLiving2 control and a 1..60000ms hold")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        name, direction = control.rsplit("_", 1)
        screen = app.LAYOUTS[self.layout]
        words = (
            (screen.combined_up, screen.combined_down) if name == "combined" else app.MOTORS[name]
        )
        await self._run(
            (app.command(self.wire, words[direction == "down"]),),
            duration_ms=self.leased_hold_ms(duration_ms),
            interval_ms=screen.refresh_ms,
            releases=2,
        )

    async def _preset(self, preset: Preset) -> None:
        await self.recall(preset)

    async def recall(self, name: str) -> None:
        if name not in app.PRESETS[self.wire]:
            raise ValueError("Unknown BetterLiving2 preset")
        if self.wire == "P1" and self._active_recall == name:
            self._active_recall = None
            await self.tap(app.P1_PRESET_STOP)
        else:
            await self._run(
                (app.command(self.wire, app.PRESETS[self.wire][name]),), releases=1, recall=True
            )
            self._active_recall = name

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.recall(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.program(f"memory_{memory_num}")

    async def program(self, name: str) -> None:
        if name not in app.PROGRAM[self.wire]:
            raise ValueError("Unknown BetterLiving2 programmable preset")
        await self._run(
            (app.command(self.wire, app.PROGRAM[self.wire][name]),),
            duration_ms=app.PROGRAM_DURATION_MS,
            interval_ms=app.PROGRAM_REFRESH_MS[self.wire],
        )

    async def stop_all(self) -> None:
        # Coordinator preemption already drains the owning movement's cleanup.
        context = current_command_context()
        if context is not None and self._completed_cleanup is not None:
            link, owner = self._completed_cleanup
            if (
                link is self._link
                and owner.cleanup_stop_sent
                and any(owner is old for old in context.preempted_contexts)
            ):
                self._completed_cleanup = None
                self._active_recall = None
                return
        await self._run((), releases=2, cancel_override=asyncio.Event())
        self._active_recall = None

    async def tap(self, word: int) -> None:
        await self._run((app.command(self.wire, word),))

    async def lights_on(self) -> None:
        await self.tap(app.P1_LIGHT[True] if self.wire == "P1" else app.STEP_LIGHT)

    async def lights_off(self) -> None:
        await self.tap(app.P1_LIGHT[False] if self.wire == "P1" else app.STEP_LIGHT)

    async def lights_toggle(self) -> None:
        if self.wire == "P1":
            raise ValueError("Choose BetterLiving2 light on or off explicitly")
        await self.tap(app.STEP_LIGHT)

    async def set_level(self, zone: str, level: float) -> None:
        if (
            self.wire != "P1"
            or zone not in LEVELS
            or isinstance(level, bool)
            or not isinstance(level, (int, float))
            or int(level) != level
        ):
            raise ValueError("Choose a P1 massage field and integer level")
        value = int(level)
        if zone == "timer":
            if value not in app.P1_TIMER_INPUTS:
                raise ValueError("P1 timer input must be -1, 0, 1 or 2")
            word = app.P1_TIMER_BASE + value
        else:
            if not 0 <= value <= 3:
                raise ValueError("P1 massage level must be 0..3")
            word = app.P1_MASSAGE_BASES[zone] + value
        await self.tap(word)
        if not self._cancel.is_set():
            self.forward_controller_state_updates(LEVELS[zone](value))

    async def massage_pair(self, head: int, feet: int) -> None:
        if self.wire != "P1" or any(type(v) is not int or not 0 <= v <= 3 for v in (head, feet)):
            raise ValueError("P1 head and feet massage levels must be 0..3")
        link = self._live()
        for index, (zone, value) in enumerate((("head", head), ("feet", feet))):
            self._live(link)
            frame = app.command(self.wire, app.P1_MASSAGE_BASES[zone] + value)
            await self._run((frame, frame), expected=link)
            if index == 0 and await pause(app.MASSAGE_ZONE_GAP_MS / 1000, self._cancel):
                return
            self.forward_controller_state_updates(LEVELS[zone](value))

    async def massage_step(self, word: int) -> None:
        if self.wire == "P1" or word not in app.STEP_MASSAGE.values():
            raise ValueError("Unknown BetterLiving2 step control")
        link = self._live()
        await self._run((app.command(self.wire, word),), expected=link)
        if self.wire == "P3" and not await pause(app.P3_MASSAGE_QUERY_MS / 1000, self._cancel):
            await self._run((app.massage_query(self.wire),), expected=link, receive_kind="massage")

    async def sync_clock(self) -> None:
        await self._run((app.current_time(self.wire, app.Calendar.from_datetime(dt_util.now())),))

    async def query_alarm(self) -> None:
        await self._run(
            (app.alarm_query(self.wire, app.Calendar.from_datetime(dt_util.now())),),
            receive_kind="alarm",
        )

    async def query_massage(self) -> None:
        await self._run((app.massage_query(self.wire),), receive_kind="massage")

    def prepare_alarm(
        self, *, enabled: bool, hour: int, minute: int, weekdays: frozenset[int], action: str
    ) -> AlarmPlan:
        if action not in app.ALARM_KINDS[self.wire]:
            raise ValueError("Choose memory_1, memory_2 or massage")
        now = dt_util.now()
        week = app.weekday_mask(weekdays, hour, minute, now)
        frame = app.alarm(
            self.wire,
            hour=hour,
            minute=minute,
            week=week,
            massage=17 if action == "massage" else 0,
            kind=app.ALARM_KINDS[self.wire][action],
            now=app.Calendar.from_datetime(now),
            enabled=enabled,
        )
        selected = AlarmView(
            enabled,
            not enabled,
            hour,
            minute,
            action == "massage",
            action == "memory_1",
            action == "memory_2",
            tuple(sorted(weekdays)),
        )
        return AlarmPlan(
            self._live() if self._link is not None else None,
            self._coordinator.address.upper(),
            self.wire.lower(),
            self.layout,
            frame,
            selected,
        )

    async def set_alarm(self, plan: AlarmPlan) -> None:
        if (
            plan.address != self._coordinator.address.upper()
            or plan.variant != self.wire.lower()
            or plan.layout != self.layout
        ):
            raise ValueError("BetterLiving2 physical owner/profile changed after validation")
        link = self._live(plan.link)
        started = asyncio.get_running_loop().time()
        await self._run((plan.frame, plan.frame), expected=link, receive_kind="alarm")
        if await pause(app.ALARM_SYNC_DELAY_MS / 1000, self._cancel):
            return
        self._live(link)
        await self.sync_clock()
        if self._cancel.is_set():
            return
        self._view = self._saved = plan.selected
        self._publish_alarm()
        if not await pause(
            max(0, started + app.ALARM_QUERY_DELAY_MS / 1000 - asyncio.get_running_loop().time()),
            self._cancel,
        ):
            self._live(link)
            await self.query_alarm()

    def _publish_alarm(self) -> None:
        view = self._view
        action = (
            "massage"
            if view.massage
            else "memory_1"
            if view.memory_a
            else "memory_2"
            if view.memory_b
            else "none"
        )
        self.forward_controller_state_updates(
            ALARM(
                ("selected" if view.switch_selected else "unselected")
                if self._observed_alarm
                else None
            ),
            HOUR(view.hour),
            MINUTE(view.minute),
            WEEK(sum(1 << d for d in view.weeks)),
            ACTION(action),
        )

    def _consume_alarm(self, raw: bytes) -> None:
        fields = alarm_fields(self.wire, raw)
        if fields is None:
            return
        if self.wire == "P1":
            self._view, self._saved = consume_p1(raw, self._view, self._saved)
        else:
            self._view = self._saved = AlarmView(
                fields.enabled,
                not fields.enabled,
                fields.hour,
                fields.minute,
                fields.massage,
                fields.memory == 1,
                fields.memory == 2,
                tuple(d for d in range(7) if fields.week & 128 and fields.week & (1 << d)),
            )
        self._observed_alarm = True
        self._publish_alarm()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        token = self._notify_token = object()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._notify_token is not token
                or self._link is not link
                or sender.handle != link.notify.handle
                or sender.uuid.lower() != link.notify.uuid.lower()
            ):
                return
            try:
                self._live(link)
            except ConnectionError:
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            raw = bytes(data)
            if (
                self._receive_kind == "alarm"
                or self.wire == "P2"
                and raw[:3] == b"\xed\x80\x03"
                or self.wire == "P3"
                and raw[:2] == b"\xa5\x0c"
            ):
                if self.wire == "P1":
                    self._consume_alarm(raw)
                else:
                    header = b"\xed\x80\x03" if self.wire == "P2" else b"\xa5\x0c"
                    if not raw.startswith(header):
                        return
                    # The app attempts STOP before parsing, even for a short
                    # record. Retire only this captured operation, then drain
                    # its release before consuming the latest notification.
                    self._pending_alarm = raw
                    if self._active_cancel is not None:
                        self._active_cancel.set()
                    serial = self._serial

                    async def stop_observed() -> None:
                        async with asyncio.timeout(12):
                            async with self._operation_lock:
                                if self._serial == serial and self._link is link:
                                    await self._cleanup(link, 1, serial)
                                    latest, self._pending_alarm = self._pending_alarm, None
                                    if latest is not None and self._notify_token is token:
                                        self._live(link)
                                        self._consume_alarm(latest)

                    if self._notify_stop is None or self._notify_stop.done():
                        self._notify_stop = asyncio.create_task(stop_observed())
                        self._notify_stop.add_done_callback(
                            lambda task: task.exception() if not task.cancelled() else None
                        )
            else:
                fields = massage_fields(self.wire, raw)
                if fields is not None:
                    self.forward_controller_state_updates(
                        LEVELS["head"](fields.head_level),
                        LEVELS["feet"](fields.foot_level),
                        LEVELS["wave"](fields.wave),
                        LEVELS["timer"](fields.timer_level),
                    )

        async with asyncio.timeout(WRITE_TIMEOUT):
            await link.client.start_notify(link.notify, receive)
        self._live(link)

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            async with asyncio.timeout(WRITE_TIMEOUT):
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        if self._active_cancel is not None:
            self._active_cancel.set()
        self._link = None
        self._notify_token = None
        self._serial += 1
        self._active_recall = None
        self._completed_cleanup = None
        self._pending_alarm = None
        self._active_cancel = None
        self._observed_alarm = False
        self.forward_controller_state_updates(
            ALARM(None),
            HOUR(None),
            MINUTE(None),
            WEEK(None),
            ACTION(None),
            *(key(None) for key in LEVELS.values()),
        )

    def on_connection_release(self, reason: str) -> None:
        selection = current_selection()
        if selection is not None:
            selection.releasing(self, reason)

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        self._manufacturer_text = None
        self._manufacturer_hint = None
        if link.manufacturer is not None:
            try:
                async with asyncio.timeout(WRITE_TIMEOUT):
                    value = await link.client.read_gatt_char(link.manufacturer)
                self._live(link)
                self._manufacturer_hint = app.manufacturer_route(bytes(value))
                self._manufacturer_text = (
                    bytes(value).decode("utf-8", errors="replace").replace("\0", "").strip()
                )
            except BleakError, TimeoutError:
                # Explicit route/endpoint validation does not inherit Android's
                # missing manufacturer callback readiness stall or rebinding race.
                self._live(link)
        session.store_device_info(self._manufacturer_text, None)
        await self.sync_clock()
        delay_ms = 0 if self._has_connected else app.SETUP_QUERY_DELAY_MS
        if not await pause(delay_ms / 1000, self._cancel):
            self._live(link)
            await self.query_alarm()
            self._has_connected = True
            self._publish_alarm()


def require(controller: BedController) -> BetterLiving2Controller:
    if not isinstance(controller, BetterLiving2Controller):
        raise TypeError("This action requires BetterLiving2")
    return controller


async def build_controller(ctx: BuildContext) -> BetterLiving2Controller:
    return BetterLiving2Controller(
        ctx.coordinator, variant=ctx.variant or "", layout=str(ctx.data.get(CONF_PRODUCT_TYPE, ""))
    )
