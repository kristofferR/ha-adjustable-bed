"""Ronco Motion: serialized app actions on one physical BLE link."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_LIGHT_TOGGLE, CARD_PRESET_SAVE
from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped, note_frame_written, note_write_not_counted
from ...errors import invalid
from ...profiles.ronco_motion import (
    END,
    MOTORS,
    PROFILES,
    SHORT,
    STARTUP,
    TRANSPORTS,
    RoncoMotionProfile,
)
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec, MotorControlSpec
from .protocol import parse_notification
from .state import ALARM

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


@dataclass(frozen=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


async def button(controller: BedController, action: str) -> None:
    await cast(RoncoMotionController, controller).short(action)


async def motor(controller: BedController, key: str, up: bool) -> None:
    await cast(RoncoMotionController, controller).move(key, up)


class RoncoMotionController(ProfileExecution[RoncoMotionProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, profile: RoncoMotionProfile) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._link: Link | None = None
        self._received: dict[str, int | str] = {}

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def auto_stops_on_idle(self) -> bool:
        # No held-release frame exists in the selected app flow.
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True  # Cancels refresh through HA's scheduler; sends no packet.

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                key,
                partial(motor, key=key, up=True),
                partial(motor, key=key, up=False),
                lambda ctrl: ctrl.stop_all(),
            )
            for key in self.profile.motors
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                key,
                label,
                partial(button, action=key),
                translation_key=f"ronco_motion_{key}",
                card=CARD_PRESET_SAVE,
                requires_confirmation=True,
            )
            for key, label in (
                ("save_zero_g", "Save zero gravity"),
                ("save_anti_snore", "Save anti-snore"),
            )
        ]
        if self.profile.light:
            specs.append(
                ControllerButtonSpec(
                    "ronco_motion_light",
                    "Toggle under-bed light",
                    partial(button, action="light_toggle"),
                    translation_key="lights_toggle",
                    card=CARD_LIGHT_TOGGLE,
                )
            )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "ronco_motion_alarm", "ronco_motion_alarm", ALARM, "mdi:alarm-check"
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"layout": self.profile.key, "received": dict(self._received)}

    def on_disconnect(self) -> None:
        self._link = None
        self._received.clear()
        self.forward_controller_state_updates(ALARM(None))

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else TRANSPORTS[0].write_uuid

    def _resolve_link(self) -> Link:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Ronco Motion is disconnected")
        if self._link is not None and self._link.client is client:
            return self._link
        services = list(client.services)
        for transport in TRANSPORTS:
            service = next((s for s in services if s.uuid.lower() == transport.service_uuid), None)
            if service is None:
                continue
            write = next(
                (
                    c
                    for c in service.characteristics
                    if c.uuid.lower() == transport.write_uuid
                    and set(c.properties) & {"write", "write-without-response"}
                ),
                None,
            )
            notify = next(
                (
                    c
                    for c in service.characteristics
                    if c.uuid.lower() == transport.notify_uuid
                    and set(c.properties) & {"notify", "indicate"}
                ),
                None,
            )
            if write is not None and notify is not None:
                self._link = Link(client, write, notify)
                return self._link
            break
        # App fallback: first non-GAP/GATT service, last write-capable role;
        # combined write+notify roles are not notification candidates.
        service = next(
            (s for s in services if not s.uuid.lower().startswith(("00001800", "00001801"))), None
        )
        if service is not None:
            writes = [
                c
                for c in service.characteristics
                if set(c.properties) & {"write", "write-without-response"}
            ]
            notifications = [
                c
                for c in service.characteristics
                if not set(c.properties) & {"write", "write-without-response"}
                and set(c.properties) & {"notify", "indicate"}
            ]
            if writes and notifications:
                self._link = Link(client, writes[-1], notifications[-1])
                return self._link
        raise ConnectionError("Ronco Motion GATT roles are incomplete")

    def _live(self, link: Link) -> bool:
        return self.client is link.client and link.client.is_connected and self._link is link

    async def _settle_write(
        self, link: Link, data: bytes, event: asyncio.Event | None = None
    ) -> None:
        response = True  # Android leaves WRITE_TYPE_DEFAULT unchanged.
        self._record_command_trace(
            link.write.uuid, data, response=response, characteristic=link.write
        )
        task = asyncio.create_task(link.client.write_gatt_char(link.write, data, response=response))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if event is None:
            note_write_not_counted()
        else:
            note_frame_written(event)
        if cancelled:
            raise asyncio.CancelledError

    async def _write(self, link: Link, data: bytes, event: asyncio.Event) -> bool:
        async with self._ble_lock:
            if event.is_set() or not self._live(link):
                note_frame_skipped()
                return False
            await self._settle_write(link, data, event)
            return not event.is_set() and self._live(link)

    async def _pause(self, milliseconds: float, event: asyncio.Event, link: Link) -> bool:
        if event.is_set() or not self._live(link):
            return False
        try:
            await asyncio.wait_for(event.wait(), max(0, milliseconds) / 1000)
        except TimeoutError:
            return not event.is_set() and self._live(link)
        return False

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._resolve_link()
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and not await self._pause(repeat_delay_ms, event, link):
                break
            if not await self._write(link, command, event):
                break

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._resolve_link()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._live(link):
                self._receive(sender, data)

        await link.client.start_notify(link.notify, receive)

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    async def read_positions(self, motor_count: int = 2) -> None:
        return None

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self._resolve_link()
        await session.async_start_notify()
        if not self._live(link):
            return
        event = self._coordinator.cancel_command
        for command in STARTUP:
            if not await self._write(link, command, event):
                return
            if not await self._pause(self.profile.startup_ms, event, link):
                return

    def _receive(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(self._link.notify.uuid if self._link else "", bytes(data))
        for parsed in parse_notification(bytes(data)):
            alarm = parsed.get("alarm")
            if isinstance(alarm, str):
                self.forward_controller_state_updates(ALARM(alarm))
            self._received.update(parsed)

    async def short(self, action: str) -> None:
        if action not in SHORT or (action == "light_toggle" and not self.profile.light):
            raise invalid("ronco_motion_request")
        link = self._resolve_link()
        event = self._coordinator.cancel_command
        if event.is_set():
            return
        async with self._ble_lock:
            if event.is_set() or not self._live(link):
                return
            try:
                await self._settle_write(link, codec.command(SHORT[action]), event)
            finally:
                # Drain SHORT's trailer before releasing ownership. It is not
                # a movement STOP and cannot target a replacement connection.
                async def finish() -> None:
                    await asyncio.sleep(self.profile.short_ms / 1000)
                    if self._live(link):
                        await self._settle_write(link, END)

                task = asyncio.create_task(finish())
                cancelled = False
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        cancelled = True
                task.result()
                if cancelled:
                    raise asyncio.CancelledError

    async def move(self, key: str, up: bool) -> None:
        if key not in self.profile.motors:
            raise invalid("ronco_motion_request")
        # Ending this cancellable refresh is the entire held-release behavior.
        await self.write_command(
            codec.command(MOTORS[key][0 if up else 1]),
            repeat_count=self.leased_hold_refreshes(self.profile.refresh_ms)
            or self._coordinator.motor_pulse_count,
            repeat_delay_ms=self.profile.refresh_ms,
        )

    async def stop_all(self) -> None:
        return None

    async def move_head_up(self) -> None:
        await self.move("head", True)

    async def move_head_down(self) -> None:
        await self.move("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.move("legs", True)

    async def move_legs_down(self) -> None:
        await self.move("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self.short("flat")

    async def preset_zero_g(self) -> None:
        await self.short("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.short("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise invalid("ronco_motion_request")
        await self.short("memory")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise invalid("ronco_motion_request")
        await self.short("save_memory")

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=("zero_g", "anti_snore", "memory_1"), requires_wake_action=True
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        actions = {"zero_g": "zero_g", "anti_snore": "anti_snore", "memory_1": "memory"}
        if alarm.enabled and alarm.wake_action not in actions:
            raise invalid("ronco_motion_request")
        minutes = alarm.minutes_until(dt_util.now()) if alarm.enabled else 0
        frames = codec.countdown(minutes, SHORT[actions[alarm.wake_action]] if alarm.enabled else 0)
        link = self._resolve_link()
        event = self._coordinator.cancel_command
        for index, command in enumerate(frames):
            if not await self._write(link, command, event):
                return
            if not await self._pause(self.profile.alarm_ms, event, link):
                if index + 1 < len(frames):
                    note_frame_skipped()
                return


async def build_controller(ctx: BuildContext) -> RoncoMotionController:
    # Client-free contract inspection may precede setup; actual setup requires a layout.
    return RoncoMotionController(
        ctx.coordinator, PROFILES[ctx.variant if ctx.variant in PROFILES else "economy"]
    )
