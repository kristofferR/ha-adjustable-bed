"""BERUN's native app controls over a captured physical BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...const import CONF_PROTOCOL_VARIANT
from ...profiles import berun as app
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..keeson.layout_app import AppController
from ..lifecycle import ControllerSession
from . import state

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


class BerunController(AppController):
    """Shared app entity shapes; BERUN owns its timing, release, replies and alarm."""

    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.BerunProfile) -> None:
        super().__init__(coordinator, profile)
        self.berun = profile
        self._link: Link | None = None
        self._notifying = False
        self._replies = state.Replies()

    @property
    def control_characteristic_uuid(self) -> str:
        return (
            self._link.write.uuid
            if self._link
            else app.ROLES[{6: 0, 7: 1, 8: 2, 9: 2}[self.berun.version]][1]
        )

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("BERUN physical BLE session changed or disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("BERUN is disconnected")
        writes = {(s, w) for s, w, _, _ in app.ROLES}
        notifies = {(s, n) for _, _, s, n in app.ROLES}
        write = notify = None
        # Roles are independent of advertisement version. Multiple matches were
        # callback-order dependent in Android; HA uses stable GATT enumeration.
        for service in client.services:
            for char in service.characteristics:
                role = service.uuid.lower(), char.uuid.lower()
                if role in writes:
                    write = char
                if role in notifies:
                    notify = char
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError("BERUN requires both its known write and notification GATT roles")
        self._link = Link(client, write, notify, "write" in write.properties)

    async def _write(
        self, link: Link, frame: bytes, cancel: asyncio.Event, deadline: float | None = None
    ) -> None:
        async with self.ble_lock:
            self._live(link)
            if (
                cancel.is_set()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline - 1e-9
            ):
                note_frame_skipped()
                return

            async def deliver() -> None:
                self._record_command_trace(
                    link.write.uuid, frame, response=link.response, characteristic=link.write
                )
                await link.client.write_gatt_char(link.write, frame, response=link.response)
                note_frame_written(cancel)

            await settled(deliver())
            self._live(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command if cancel_event is None else cancel_event
        for index in range(repeat_count):
            if index and await self._pause(repeat_delay_ms / 1000, cancel):
                note_frame_skipped()
                return
            await self._write(link, command, cancel)

    @staticmethod
    async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
        try:
            async with asyncio.timeout(max(0, seconds)):
                await cancel.wait()
            return True
        except TimeoutError:
            return False

    async def _release_link(self, link: Link) -> None:
        async def release() -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            await self._write(link, self.berun.frame(0), asyncio.Event())
            if (context := current_command_context()) is not None:
                context.cleanup_stop_sent = True

        await settled(release())

    async def _release(self) -> None:
        await self._release_link(self._live())

    async def stop_all(self) -> None:
        context = current_command_context()
        if context is not None:
            if context.cleanup_stop_sent:
                return
            for previous in context.preempted_contexts:
                if previous.cleanup_stop_sent:
                    previous.cleanup_stop_sent = False
                    return
        await self._release()

    def _frame(self, mask: int) -> bytes:
        return self.berun.frame(mask)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        frame = self._frame(self._action(control).mask)
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.leased_hold_ms(duration_ms) / 1000
        try:
            while not cancel.is_set() and loop.time() < deadline - 1e-9:
                start = loop.time()
                await self._write(link, frame, cancel, deadline)
                interval = self.berun.refresh_ms / 1000
                next_tick = start + (int((loop.time() - start) / interval) + 1) * interval
                if await self._pause(min(next_tick, deadline) - loop.time(), cancel):
                    break
        finally:
            await self._release_link(link)

    async def _run_action(self, key: str) -> None:
        action = self._action(key)  # Broken/absent actions fail before any write.
        if action.mode == "held":
            await self.hold_control(
                key, min(60000, max(1, self._coordinator.motor_pulse_count) * self.berun.refresh_ms)
            )
            return
        link, cancel = self._live(), self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        await self._write(link, self._frame(action.mask), cancel)
        if key.startswith("massage_") and self.berun.version >= 8:
            remaining = started + self.berun.massage_query_ms / 1000 - loop.time()
            if not await self._pause(remaining, cancel):
                await self._write(link, self.berun.query(), cancel)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                scheduler_resource="*",
                hold=replace(spec.hold, press_is_native=True) if spec.hold else None,
            )
            for spec in super().motor_control_specs
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return unique_buttons(
            (
                *(
                    catalog_button(
                        spec.key, spec.name, spec.press_fn, kind=Kind.PRESET, hold=spec.hold
                    )
                    if spec.key == "memory"
                    else spec
                    for spec in super().controller_button_specs
                ),
                catalog_button(
                    "berun_refresh_massage",
                    "Refresh massage",
                    lambda c: require(c).refresh_massage(),
                    diagnostic=True,
                ),
                catalog_button(
                    "berun_refresh_alarm",
                    "Refresh alarm",
                    lambda c: require(c).refresh_alarm(),
                    diagnostic=True,
                ),
            )
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if key == "preset_flat":
            return ControllerHoldSpec("flat")
        return super().standard_button_hold_spec(key)

    async def refresh_massage(self) -> None:
        await self.write_command(self.berun.query())

    async def refresh_alarm(self) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(2):
            await self._write(link, self.berun.query(alarm=True), cancel)
            remaining = started + (index + 1) * self.berun.alarm_repeat_ms / 1000 - loop.time()
            if await self._pause(remaining, cancel):
                return

    async def sync_clock(self) -> None:
        await self.write_command(self.berun.clock_frame(dt_util.now()))

    @property
    def alarm_capability(self) -> AlarmCapability:
        # The visible UI always schedules all seven days and has no day picker.
        # Memory is a named preset, not a numbered memory slot.
        return AlarmCapability(wake_actions=("massage", "memory_1"), resource="*")

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if (
            alarm.enabled
            and alarm.wake_action not in self.alarm_capability.wake_actions
            or alarm.weekdays
            or alarm.slot != 1
            or not 0 <= alarm.hour <= 23
            or not 0 <= alarm.minute <= 59
        ):
            raise ValueError("BERUN accepts a daily massage or Memory alarm and a valid time")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, cancel = self._live(), self._coordinator.cancel_command
        kind = (
            (9 if alarm.wake_action == "massage" else 17)
            if self.berun.version < 8
            else (8 if alarm.wake_action == "massage" else 5)
        )
        frame = (
            self.berun.alarm_frame(alarm.hour, alarm.minute, 255, kind)
            if alarm.enabled
            else self.berun.alarm_frame(0, 0, 0, 0)
        )
        # Source switchAlarm starts both loops together: SET,Q at 0 and 300ms,
        # then SET at 600ms; both loops retain their final 300ms wait.
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(3):
            await self._write(link, frame, cancel)
            if index < 2:
                await self._write(link, self.berun.query(alarm=True), cancel)
            remaining = started + (index + 1) * self.berun.alarm_repeat_ms / 1000 - loop.time()
            if await self._pause(remaining, cancel):
                return

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            reply = self._replies.feed(self.berun.version, bytes(data))
            if isinstance(reply, state.Massage):
                self.forward_controller_state_updates(
                    state.HEAD(reply.head),
                    state.FOOT(reply.foot),
                    state.TIMER(reply.time),
                    state.MODE(reply.mode),
                    state.MASSAGE(reply.isOn),
                )
            elif isinstance(reply, state.Alarm):
                self.forward_controller_state_updates(
                    state.ALARM(f"{reply.hour:02}:{reply.minute:02}"),
                    state.ALARM_DETAIL(reply.detail()),
                    state.ALARM_ON(reply.on),
                )

        async with self.ble_lock:
            self._live(link)
            await settled(link.client.start_notify(link.notify, receive))
        self._live(link)
        self._notifying = True

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if link is not None and notifying and link.client.is_connected:
            async with self.ble_lock:
                await settled(link.client.stop_notify(link.notify))

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._replies = state.Replies()
        super().on_disconnect()
        self.forward_controller_state_updates(
            *(
                key(None)
                for key in (
                    state.HEAD,
                    state.FOOT,
                    state.TIMER,
                    state.MODE,
                    state.MASSAGE,
                    state.ALARM,
                    state.ALARM_DETAIL,
                    state.ALARM_ON,
                )
            )
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                str(key),
                str(key),
                key,
                icon,
                attribute_keys=(state.ALARM_DETAIL,) if key is state.ALARM else (),
                entity_registry_enabled_default=True,
                entity_category=None,
            )
            for key, name, icon in (
                (state.HEAD, "Head massage level", "mdi:vibrate"),
                (state.FOOT, "Foot massage level", "mdi:vibrate"),
                (state.TIMER, "Massage timer index", "mdi:timer-outline"),
                (state.MODE, "Massage mode", "mdi:vibrate"),
                (state.ALARM, "Alarm", "mdi:alarm"),
            )
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                str(key),
                str(key),
                key,
                icon,
                entity_registry_enabled_default=True,
                entity_category=None,
            )
            for key, name, icon in (
                (state.MASSAGE, "Massage", "mdi:vibrate"),
                (state.ALARM_ON, "Alarm enabled", "mdi:alarm"),
            )
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()

    async def async_after_connect(self, session: ControllerSession) -> None:
        if session is not None and not session.is_current():
            return
        await self.sync_clock()


def require(controller: BedController) -> BerunController:
    if not isinstance(controller, BerunController):
        raise TypeError("BERUN controller required")
    return controller


async def build_controller(ctx: BuildContext) -> BedController:
    variant = ctx.variant or ctx.data.get(CONF_PROTOCOL_VARIANT)
    if variant not in app.PROFILES:
        raise ValueError("Choose a BERUN version during setup")
    return BerunController(ctx.coordinator, app.PROFILES[variant])
