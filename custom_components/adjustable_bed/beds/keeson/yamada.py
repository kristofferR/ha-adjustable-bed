"""アシステック's two explicit BLE routes over the shared Keeson controller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_UTILITY
from ...command_scheduler import CommandContext, current_command_context
from ...controller_state import StateKey
from ...profiles import yamada as app
from ...profiles.keeson import Preset
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .controller import KeesonController
from .yamada_state import AlarmParser

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

ALARM_1: Final = StateKey[str | None]("yamada_alarm_1")
ALARM_2: Final = StateKey[str | None]("yamada_alarm_2")
HOUR_1: Final = StateKey[int | None]("yamada_hour_1")
HOUR_2: Final = StateKey[int | None]("yamada_hour_2")
MINUTE_1: Final = StateKey[int | None]("yamada_minute_1")
MINUTE_2: Final = StateKey[int | None]("yamada_minute_2")
WEEK_1: Final = StateKey[int | None]("yamada_week_1")
WEEK_2: Final = StateKey[int | None]("yamada_week_2")
POSITION_1: Final = StateKey[int | None]("yamada_position_1")
POSITION_2: Final = StateKey[int | None]("yamada_position_2")
_KEYS: Final = (
    (ALARM_1, HOUR_1, MINUTE_1, WEEK_1, POSITION_1),
    (ALARM_2, HOUR_2, MINUTE_2, WEEK_2, POSITION_2),
)


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    address: str
    write: BleakGATTCharacteristic
    response: bool
    notifications: tuple[BleakGATTCharacteristic, ...]


@dataclass(frozen=True, slots=True)
class AlarmPlan:
    """A validated write bound to the exact controller session it inspected."""

    link: _Link
    frame: bytes
    revision: int | None


class YamadaController(KeesonController):
    """Reuse family motor/preset APIs; own this app's session and release."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        version: str,
        manufacturer_hint: str | None = None,
    ) -> None:
        if version not in app.PROFILES:
            raise ValueError("Choose the アシステック P1 or P2 protocol explicitly")
        super().__init__(coordinator, variant=app.PROFILES[version].key)
        self._link: _Link | None = None
        self._notifying: list[BleakGATTCharacteristic] = []
        self._alarms: dict[int, app.Alarm] = {}
        self._alarm_revision = 0
        self._p1_pending_fields: bytes | None = None
        self._cleanup: tuple[_Link, CommandContext] | None = None
        self._manufacturer_hint = manufacturer_hint

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "yamada_profile": self.profile.key,
            "yamada_manufacturer_hint_untrusted": self._manufacturer_hint,
            "yamada_automatic_version_selection": False,
        }

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False  # Ending refresh alone is not a proven hardware STOP.

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                scheduler_resource="motor:*",
                hold=ControllerMotorHoldSpec(
                    f"{prefix}_up",
                    f"{prefix}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                ),
            )
            for spec, prefix in zip(super().motor_control_specs, ("head", "foot"), strict=True)
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in app.WORDS if key != "stop")

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {
            "preset_flat": "flat",
            "preset_zero_g": "zero",
            "preset_tv": "tvpc",
            "preset_anti_snore": "anti_snore",
            "preset_memory_1": "memory_m2",
            "toggle_light": "light",
        }.get(key)
        return ControllerHoldSpec(control) if control else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "yamada_sync_clock",
                "Sync bed clock",
                lambda c: _yamada(c).sync_clock(),
                "mdi:clock-check",
                translation_key="yamada_sync_clock",
                card=CARD_UTILITY,
            ),
            ControllerButtonSpec(
                "yamada_query_alarms",
                "Refresh bed alarms",
                lambda c: _yamada(c).query_alarms(),
                "mdi:alarm-check",
                translation_key="yamada_query_alarms",
                card=CARD_UTILITY,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                str(state),
                str(state),
                state,
                "mdi:alarm",
                attribute_keys=(hour, minute, week, position),
                card=CARD_UTILITY,
            )
            for state, hour, minute, week, position in _KEYS
        )

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address.upper() != link.address
        ):
            raise ConnectionError("アシステック BLE session changed or disconnected")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("アシステック is disconnected")
        write: BleakGATTCharacteristic | None = None
        notifications: list[BleakGATTCharacteristic] = []
        for service in client.services:
            for char in service.characteristics:
                # Independent OR branches, in enumeration order. Never pair UUIDs.
                if (
                    service.uuid.lower() in app.WRITE_SERVICES
                    and char.uuid.lower() in app.WRITE_CHARS
                ):
                    write = char
                if (
                    service.uuid.lower() in app.NOTIFY_SERVICES
                    and char.uuid.lower() in app.NOTIFY_CHARS
                ):
                    notifications.append(char)
        if write is None or not notifications:
            raise ValueError("アシステック requires both write and notification roles")
        if "write" not in write.properties:
            raise ValueError("アシステック requires a write-with-response characteristic")
        if any(not {"notify", "indicate"}.intersection(c.properties) for c in notifications):
            raise ValueError("アシステック notification role cannot notify or indicate")
        self._char_uuid = write.uuid
        self._link = _Link(
            client, self._coordinator.address.upper(), write, True, tuple(notifications)
        )

    async def _write(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        alarm_revision: int | None = None,
    ) -> None:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                return
            if alarm_revision is not None:
                if alarm_revision != self._alarm_revision:
                    raise ValueError(
                        "Bed alarm observations changed after validation; refresh and retry"
                    )
                # A P1 table write consumes its snapshot. Check and invalidate
                # under the wire lock, before notifications or another save
                # can authorize a stale read-modify-write.
                self._alarm_revision += 1
                self._p1_pending_fields = frame[3:11]
                self._alarms = {}
                self._publish_alarms()
            self._record_command_trace(
                link.write.uuid, frame, response=link.response, characteristic=link.write
            )
            await link.client.write_gatt_char(link.write, frame, response=link.response)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set() or index and await _pause(repeat_delay_ms / 1000, cancel):
                return
            await self._write(link, command, cancel)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()

        async def subscribe(char: BleakGATTCharacteristic) -> None:
            if char in self._notifying:
                return
            parser = AlarmParser(self.profile.key == "yamada_p1")

            def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
                if (
                    self._link is not link
                    or self.client is not link.client
                    or not link.client.is_connected
                    or self._coordinator.address.upper() != link.address
                    or sender.handle != char.handle
                    or sender.uuid.lower() != char.uuid.lower()
                ):
                    return
                self.forward_raw_notification(sender.uuid, bytes(data))
                updates = parser.feed(bytes(data), self._alarms)
                if updates:
                    self._alarms.update(updates)
                    self._alarm_revision += 1
                    if (
                        self._p1_pending_fields is not None
                        and bytes(data)[3:11] == self._p1_pending_fields
                    ):
                        self._p1_pending_fields = None
                    self._publish_alarms()

            for attempt in range(2):
                self._live(link)
                try:
                    await link.client.start_notify(char, receive)
                    self._live(link)
                    self._notifying.append(char)
                    return
                except BleakError:
                    if attempt:
                        raise
                    await asyncio.sleep(app.NOTIFY_RETRY_MS / 1000)

        async with asyncio.TaskGroup() as tasks:
            for char in link.notifications:
                tasks.create_task(subscribe(char))

    async def stop_notify(self) -> None:
        link, notifying = self._link, tuple(self._notifying)
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            for char in notifying:
                await link.client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = []
        self._alarms = {}
        self._alarm_revision += 1
        self._p1_pending_fields = None
        self._cleanup = None
        self._notify_callback = None
        self._publish_alarms()

    def _publish_alarms(self) -> None:
        first, second = self._alarms.get(1), self._alarms.get(2)
        self.forward_controller_state_updates(
            ALARM_1(("on" if first.enabled else "off") if first else None),
            HOUR_1(first.hour if first else None),
            MINUTE_1(first.minute if first else None),
            WEEK_1(first.weekday if first else None),
            POSITION_1(first.position if first else None),
            ALARM_2(("on" if second.enabled else "off") if second else None),
            HOUR_2(second.hour if second else None),
            MINUTE_2(second.minute if second else None),
            WEEK_2(second.weekday if second else None),
            POSITION_2(second.position if second else None),
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        # The app clock overlaps asynchronous subscriptions. Both tasks capture
        # this link and are awaited before startup ends; no detached callbacks.
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(session.async_start_notify())
            tasks.create_task(self.sync_clock())

    async def sync_clock(self) -> None:
        link, frame = self._live(), app.clock(self.profile, dt_util.now())
        await self._write(link, frame, self._coordinator.cancel_command)

    async def _release(
        self,
        link: _Link,
        frame: bytes,
        *,
        once: bool = False,
        acknowledge: CommandContext | None = None,
    ) -> None:
        async def send() -> None:
            started = asyncio.get_running_loop().time()
            failure: Exception | None = None
            for at in (100,) if once else (100, 400):
                await asyncio.sleep(max(0, started + at / 1000 - asyncio.get_running_loop().time()))
                try:
                    await self._write(link, frame, asyncio.Event())
                except Exception as err:
                    failure = failure or err
            if failure:
                raise failure

        task = asyncio.create_task(send())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
            except Exception:
                break
        task.result()
        if acknowledge is not None:
            acknowledge.cleanup_stop_sent = True
            self._cleanup = (link, acknowledge)
        if interrupted:
            raise asyncio.CancelledError

    async def _hold(self, word: int, duration_ms: int, interval_ms: int = 300) -> None:
        # Capture every destination and byte before the first await, including
        # cleanup. A reconnect can invalidate this operation, never retarget it.
        link, frame, stop = self._live(), self._build_command(word), self._build_command(0)
        cancel = self._coordinator.cancel_command
        context = current_command_context()
        if cancel.is_set():
            return
        if context is not None:
            context.cleanup_stop_sent = False
        self._cleanup = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        try:
            while not cancel.is_set() and loop.time() < deadline:
                next_at = loop.time() + interval_ms / 1000
                await self._write(link, frame, cancel)
                # Elapsed time bounds fast AND slow ACKs; never catch up with
                # extra frames after the deadline. In-flight ATT writes settle.
                if await _pause(max(0, min(next_at, deadline) - loop.time()), cancel):
                    break
        finally:
            await self._release(link, stop, acknowledge=context)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, self._coordinator.motor_pulse_delay_ms

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in ("head", "feet"):
            raise ValueError("アシステック has only head and foot controls")
        if direction is None:
            await self.stop_all()
            return
        count, interval = self.motor_pulse_settings()
        duration = self.leased_hold_ms(count * interval)
        if self.leased_hold_refreshes(app.REFRESH_MS) is not None:
            interval = app.REFRESH_MS
        await self._hold(
            app.WORDS[f"{'head' if motor == 'head' else 'foot'}_{'up' if direction else 'down'}"],
            duration,
            interval,
        )

    async def _preset(self, preset: Preset) -> None:
        await self._hold(self.profile.presets[preset], app.REFRESH_MS)

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._hold(self.profile.memory[memory_num], app.REFRESH_MS)

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        # Same held M bytes. This is the app's local confirmation threshold,
        # not a separate SAVE opcode or a hardware completion acknowledgement.
        await self._hold(self.profile.memory[memory_num], app.SAVE_CONFIRMATION_MS)

    async def lights_toggle(self) -> None:
        await self._hold(app.WORDS["light"], app.REFRESH_MS)

    async def stop_all(self) -> None:
        link, frame = self._live(), self._build_command(0)
        context = current_command_context()
        if self._cleanup is not None and context is not None:
            owner_link, owner = self._cleanup
            if (
                owner_link is link
                and any(owner is old for old in context.preempted_contexts)
                and owner.cleanup_stop_sent
            ):
                self._cleanup = None
                owner.cleanup_stop_sent = False
                return
        await self._release(link, frame, once=True)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unknown アシステック held control")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError("Hold duration must be 1..60000 milliseconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._hold(app.WORDS[control], self.leased_hold_ms(duration_ms))

    async def _queries(
        self,
        link: _Link,
        rounds: tuple[int, ...],
        *,
        start: float | None = None,
    ) -> None:
        schedule = sorted(
            (outer + delay, frame) for outer in rounds for delay, frame in app.queries(self.profile)
        )
        if start is None:
            start = asyncio.get_running_loop().time()
        cancel = self._coordinator.cancel_command
        for delay, frame in schedule:
            if await _pause(
                max(0, start + delay / 1000 - asyncio.get_running_loop().time()), cancel
            ):
                return
            await self._write(link, frame, cancel)

    async def query_alarms(self) -> None:
        await self._queries(self._live(), app.PAGE_ROUNDS_MS)

    def prepare_alarm(
        self,
        *,
        slot: int,
        enabled: bool,
        hour: int,
        minute: int,
        weekday: int,
        preset: str,
    ) -> AlarmPlan:
        link = self._live()
        if self.profile.key == "yamada_p1" and self._p1_pending_fields is not None:
            raise ValueError(
                "Waiting for the written P1 alarm table to be observed; refresh or reconnect"
            )
        if isinstance(slot, bool) or slot not in (1, 2) or not isinstance(enabled, bool):
            raise ValueError("Choose an explicit alarm slot and enabled state")
        if (
            any(isinstance(v, bool) or not isinstance(v, int) for v in (hour, minute))
            or not 0 <= hour <= 23
            or not 0 <= minute <= 59
        ):
            raise ValueError("Alarm time must be 00:00..23:59")
        positions = app.POSITIONS[self.profile.key]
        if preset not in positions:
            raise ValueError("Choose a supported アシステック alarm preset")
        week = app.alarm_week(weekday, hour, minute, dt_util.now())
        selected = app.Alarm(
            hour,
            minute,
            week if enabled else 0,
            positions[preset] if enabled or self.profile.key == "yamada_p2" else 0,
            enabled,
        )
        return AlarmPlan(
            link,
            app.alarm_frame(self.profile, slot, selected, self._alarms.get(3 - slot)),
            self._alarm_revision if self.profile.key == "yamada_p1" else None,
        )

    async def set_alarm(self, plan: AlarmPlan) -> None:
        self._live(plan.link)
        started = asyncio.get_running_loop().time()
        await self._write(
            plan.link,
            plan.frame,
            self._coordinator.cancel_command,
            alarm_revision=plan.revision,
        )
        # Do not turn an ATT write or the app's local confirmation timer into
        # observed bed state. One delayed manager round, not the page burst.
        await self._queries(plan.link, (app.REFRESH_MS,), start=started)


def _yamada(controller: BedController) -> YamadaController:
    if not isinstance(controller, YamadaController):
        raise TypeError("This action requires アシステック")
    return controller


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    if seconds <= 0:
        return False
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


async def build_controller(ctx: BuildContext) -> YamadaController:
    data = ctx.manufacturer_data
    # Corroboration in diagnostics only, never automatic route selection. Even
    # one HA record does not prove Android's raw AD concatenation layout.
    hint = app.manufacturer_version(next(iter(data.values()))) if data and len(data) == 1 else None
    return YamadaController(ctx.coordinator, version=ctx.variant or "", manufacturer_hint=hint)
