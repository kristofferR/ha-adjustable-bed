"""Nerum profile execution with physical-session ownership of every deferred effect."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...card import CARD_UTILITY
from ...command_scheduler import current_command_context
from ...const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT
from ...profiles import nerum as app
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from . import state
from .state import ALARM_1, ALARM_2, ALARM_3

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


async def settled[T](operation: Coroutine[object, object, T]) -> T:
    """Drain submitted radio work before cancellation can give the lane to STOP."""
    task = asyncio.create_task(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


class NerumController(ProfileExecution[app.NerumProfile], BedController):
    def __init__(
        self, coordinator: AdjustableBedCoordinator, protocol: app.Protocol = "p2"
    ) -> None:
        super().__init__(coordinator)
        self.profile = app.PROFILES[protocol]
        self.layout = str(coordinator.entry.data.get(CONF_PRODUCT_TYPE, "nerum"))
        if self.layout not in app.LAYOUTS:
            raise ValueError("Choose a Nerum motor layout")
        self._link: Link | None = None
        self._notifying = False
        self._replies = state.Replies()

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.write

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("Nerum physical BLE session changed or disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Nerum is disconnected")
        write = notify = None
        for service in client.services:
            for char in service.characteristics:
                role = service.uuid.lower(), char.uuid.lower()
                if role == (self.profile.service, self.profile.write):
                    write = char
                if role == (self.profile.notify_service, self.profile.notify):
                    notify = char
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError(
                "Nerum requires the selected protocol's exact write and notify GATT roles"
            )
        # Android leaves the discovered/framework write type alone. Prefer the
        # characteristic's acknowledged default when both properties exist.
        self._link = Link(client, write, notify, "write" in write.properties)

    async def _write(
        self, link: Link, command: bytes, cancel: asyncio.Event, deadline: float | None = None
    ) -> None:
        async with self._ble_lock:
            self._live(link)
            if (
                not command
                or cancel.is_set()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline - 1e-9
            ):
                return
            self._record_command_trace(
                link.write.uuid, command, response=link.response, characteristic=link.write
            )
            await settled(link.client.write_gatt_char(link.write, command, response=link.response))
            self._live(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command if cancel_event is None else cancel_event
        for index in range(repeat_count):
            if index and await self._pause(repeat_delay_ms / 1000, cancel):
                return
            await self._write(link, command, cancel)

    @staticmethod
    async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
        try:
            async with asyncio.timeout(seconds):
                await cancel.wait()
            return True
        except TimeoutError:
            return False

    async def _release(self, link: Link, *, motor: bool = False) -> None:
        async def release() -> None:
            loop = asyncio.get_running_loop()
            started = loop.time()
            # One motorStop on Nerum; the generic 2/3/4 pages dispatch it twice.
            for offset in self.profile.release_ms:
                await asyncio.sleep(max(0, started + offset / 1000 - loop.time()))
                if (
                    self._link is not link
                    or self.client is not link.client
                    or not link.client.is_connected
                ):
                    return
                for _ in range(2 if motor and self.layout != "nerum" else 1):
                    await self._write(link, app.build(self.profile.key, 6), asyncio.Event())
            if (context := current_command_context()) is not None:
                context.cleanup_stop_sent = True

        await settled(release())

    def _held(self) -> dict[str, tuple[int, int]]:
        return {
            **{
                f"{axis}_{direction}": (app.AXES[axis], 1 if direction == "up" else 2)
                for axis in app.LAYOUTS[self.layout]
                for direction in ("up", "down")
            },
            **{
                name: (function, 0)
                for name, function in app.PRESETS.items()
                if (name != "memory_2" or self.profile.key != "p1")
                and (name != "tv" or self.layout != "nerum")
            },
            "light": (14, 0),
        }

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._held())

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self._held() or not 1 <= duration_ms <= 60000:
            raise ValueError("Choose an available Nerum control and a hold of 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        command = app.build(self.profile.key, *self._held()[control])
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.leased_hold_ms(duration_ms) / 1000
        try:
            while not cancel.is_set() and loop.time() < deadline - 1e-9:
                started = loop.time()
                await self._write(link, command, cancel, deadline)
                interval = self.profile.refresh_ms / 1000
                next_tick = started + (int((loop.time() - started) / interval) + 1) * interval
                if loop.time() >= deadline - 1e-9 or await self._pause(
                    min(next_tick, deadline) - loop.time(), cancel
                ):
                    break
        finally:
            await self._release(link, motor=self._held()[control][0] <= 5)

    async def _press(self, control: str) -> None:
        if control not in self._held():
            raise NotImplementedError("This Nerum layout has no such control")
        await self.hold_control(
            control, max(1, self._coordinator.motor_pulse_count) * self.profile.refresh_ms
        )

    async def move_back_up(self) -> None:
        await self._press("back_up")

    async def move_back_down(self) -> None:
        await self._press("back_down")

    async def move_head_up(self) -> None:
        await self._press("head_up")

    async def move_head_down(self) -> None:
        await self._press("head_down")

    async def move_legs_up(self) -> None:
        await self._press("legs_up")

    async def move_legs_down(self) -> None:
        await self._press("legs_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def move_lumbar_up(self) -> None:
        await self._press("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self._press("lumbar_down")

    async def stop_all(self) -> None:
        context = current_command_context()
        if context is not None:
            if context.cleanup_stop_sent:
                return
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await self._release(self._live())

    move_back_stop = stop_all
    move_head_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
    move_lumbar_stop = stop_all

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                "neck" if axis == "head" else axis,
                lambda c, axis=axis: require(c)._press(f"{axis}_up"),
                lambda c, axis=axis: require(c)._press(f"{axis}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_is_native=True
                ),
            )
            for axis in app.LAYOUTS[self.layout]
        )

    async def preset_flat(self) -> None:
        await self._press("flat")

    async def preset_zero_g(self) -> None:
        await self._press("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._press("anti_snore")

    async def preset_lounge(self) -> None:
        await self._press("lounge")

    async def preset_tv(self) -> None:
        await self._press("tv")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._press(f"memory_{memory_num}")

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        await self.hold_control(f"memory_{slot}", hold_ms)

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError(
            "Nerum has repeated recall and local feedback, no proven SAVE command"
        )

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1 if self.profile.key == "p1" else 2

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return self.layout != "nerum"

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = key.removeprefix("preset_")
        return ControllerHoldSpec(control) if control in self._held() else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "nerum_light",
                "Light",
                lambda c: require(c)._press("light"),
                hold=ControllerHoldSpec("light"),
                translation_key="nerum_light",
                card=CARD_UTILITY,
            )
        ]
        if self.profile.key != "p1":
            specs.append(
                ControllerButtonSpec(
                    "nerum_alarm_refresh",
                    "Refresh alarms",
                    lambda c: require(c).refresh_alarms(),
                    translation_key="nerum_alarm_refresh",
                )
            )
        return tuple(specs)

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.key != "p1"

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise ValueError("Nerum P1 has no clock output")
        await self.write_command(app.clock(self.profile.key, dt_util.now()))

    def validate_alarm_bank(self, bank: tuple[app.Alarm, app.Alarm, app.Alarm]) -> None:
        if self.profile.key == "p1" or len(bank) != 3:
            raise ValueError("Nerum P2/P3 requires exactly three alarm records")
        if any(
            not 0 <= a.hour <= 23
            or not 0 <= a.minute <= 59
            or not 0 <= a.repeat <= 255
            or a.kind not in app.WAKE.values()
            for a in bank
        ):
            raise ValueError("Invalid Nerum alarm fields")

    async def set_alarms(self, bank: tuple[app.Alarm, app.Alarm, app.Alarm]) -> None:
        self.validate_alarm_bank(bank)
        link = self._live()
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        await self._write(link, app.clock(self.profile.key, dt_util.now()), cancel)
        frames = app.alarms(self.profile.key, bank)
        for index, frame in enumerate(frames, 1):
            offset = 0.3 if self.profile.key == "p2" else index * 0.1
            if await self._pause(max(0, started + offset - loop.time()), cancel):
                return
            await self._write(link, frame, cancel)
        if self.profile.key == "p3":
            if await self._pause(max(0, started + 0.4 - loop.time()), cancel):
                return
            await self._query_alarms(link)

    async def _query_alarms(self, link: Link) -> None:
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for slot in range(1, 2 if self.profile.key == "p2" else 4):
            if slot > 1 and await self._pause(
                max(0, started + (slot - 1) * 0.2 - loop.time()), cancel
            ):
                return
            await self._write(link, app.query(self.profile.key, slot), cancel)

    async def refresh_alarms(self) -> None:
        if self.profile.key == "p1":
            raise ValueError("Nerum P1 has no alarm query")
        await self._query_alarms(self._live())

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if not self._notifying:
            await link.client.start_notify(
                link.notify, lambda sender, data: self._receive(link, sender, bytes(data))
            )
            self._live(link)
            self._notifying = True

    def _receive(self, link: Link, sender: BleakGATTCharacteristic, data: bytes) -> None:
        if (
            self._link is not link
            or self.client is not link.client
            or not link.client.is_connected
            or sender.handle != link.notify.handle
        ):
            return
        self.forward_raw_notification(sender.uuid, data)
        reply = self._replies.feed(self.profile.key, data)
        if isinstance(reply, state.Status):
            if reply.head is not None:
                self.forward_controller_state_updates(state.HEAD(reply.head))
            if reply.foot is not None:
                self.forward_controller_state_updates(state.FOOT(reply.foot))
            if reply.minutes is not None:
                self.forward_controller_state_updates(state.MINUTES(reply.minutes))
            if reply.wave is not None:
                self.forward_controller_state_updates(state.WAVE(reply.wave))
            if reply.massage is not None:
                self.forward_controller_state_updates(state.MASSAGE(reply.massage))
            if reply.light is not None:
                self.forward_controller_state_updates(state.LIGHT(reply.light))
        elif isinstance(reply, state.Operation):
            self.forward_controller_state_updates(state.OPERATE(reply.value))
        elif reply is not None:
            for slot, alarm in reply:
                value = (
                    f"{alarm.hour:02}:{alarm.minute:02};{alarm.repeat};{alarm.kind};{int(alarm.on)}"
                )
                if slot == 1:
                    self.forward_controller_state_updates(ALARM_1(value))
                elif slot == 2:
                    self.forward_controller_state_updates(ALARM_2(value))
                else:
                    self.forward_controller_state_updates(ALARM_3(value))

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = (
            [
                ControllerStateSensorSpec(str(key), str(key), key, "mdi:information-outline")
                for key in (state.HEAD, state.FOOT, state.MINUTES, state.WAVE)
            ]
            if self.profile.key != "p3"
            else []
        )
        if self.profile.key == "p1":
            specs.append(
                ControllerStateSensorSpec(
                    str(state.OPERATE), str(state.OPERATE), state.OPERATE, "mdi:information-outline"
                )
            )
        if self.profile.key != "p1":
            specs.extend(
                ControllerStateSensorSpec(str(key), str(key), key, "mdi:alarm")
                for key in state.ALARM_KEYS
            )
        return tuple(specs)

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(str(key), str(key), key, "mdi:information-outline")
            for key in (state.MASSAGE, state.LIGHT)
            if self.profile.key == "p1" or self.profile.key == "p2" and key is state.MASSAGE
        )

    async def stop_notify(self) -> None:
        link = self._link
        if (
            link is not None
            and self._notifying
            and self.client is link.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.notify)
        self._notifying = False

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._replies = state.Replies()

    async def read_positions(self, motor_count: int = 2) -> None:
        return

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()

    async def async_after_connect(self, session: ControllerSession) -> None:
        link = self._live()
        await asyncio.sleep(0.2)
        self._live(link)
        if self.supports_clock_sync:
            await self._write(link, app.clock(self.profile.key, dt_util.now()), asyncio.Event())


def require(controller: BedController) -> NerumController:
    if not isinstance(controller, NerumController):
        raise TypeError("Nerum controller required")
    return controller


async def build_controller(ctx: BuildContext) -> BedController:
    variant = ctx.variant or ctx.data.get(CONF_PROTOCOL_VARIANT, "auto")
    if variant not in app.PROFILES:
        found = app.advertisement(str(ctx.data.get(CONF_BLE_DEVICE_NAME, "")))
        variant = found.protocol if found else "p2"
    return NerumController(ctx.coordinator, app.PROFILES[variant].key)
