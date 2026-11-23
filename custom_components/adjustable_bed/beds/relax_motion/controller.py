"""Relax Motion's dynamically discovered GATT session and cancellable actions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory

from ...card import CARD_MASSAGE
from ...codec import relax_motion as codec
from ...command_scheduler import (
    Delivery,
    delivered,
    note_frame_skipped,
    note_frame_written,
)
from ...const import CONF_BED_TYPE, CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateUpdate
from ...errors import failed, invalid
from ...profiles import relax_motion as app
from ...state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_ON, massage_intensity
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateBinarySensorSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from . import state_keys as state

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notifications: tuple[BleakGATTCharacteristic, ...]
    response: bool
    protocol: str


class RelaxMotionController(ProfileExecution[app.RelaxMotionProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.route = app.route_name(coordinator.entry.data.get(CONF_PROTOCOL_VARIANT))
        raw = coordinator.entry.data.get(CONF_PRODUCT_TYPE)
        self.number = app.model_number(raw)
        self.model = app.model(self.number, self.route) if self.number is not None else None
        self.profile = app.PROFILES[
            "p2"
            if self.number is not None and self.number > 450 and self.route == "relax"
            else "p1"
        ]
        self._link: Link | None = None
        self._notifying: list[BleakGATTCharacteristic] = []
        self._serial = 0
        self._epoch = 0
        self._snore_ready = False
        self._rhythm: bool | None = False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else codec.SERVICE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        return (() if self._snore_ready else ("controller_number_relax_motion_snore_interval",)) + (
            tuple(f"controller_number_relax_motion_{zone}_intensity" for zone in ("head", "foot"))
            if self._rhythm is None
            else ()
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            tuple(
                MotorControlSpec(
                    axis,
                    axis,
                    _move_call(axis, True),
                    _move_call(axis, False),
                    lambda c: c.stop_all(),
                    scheduler_resource="*",
                    stop_scope="side",
                    hold=ControllerMotorHoldSpec(
                        f"{axis}_up",
                        f"{axis}_down",
                        stop_scope="side",
                        press_hold_ms=1000,
                        press_is_native=True,
                    ),
                )
                for axis in app.axes(self.model)
            )
            if self.model
            else ()
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{spec.key}_{direction}"
            for spec in self.motor_control_specs
            for direction in ("up", "down")
        )

    @property
    def supports_preset_flat(self) -> bool:
        return self.model is not None

    @property
    def supports_preset_zero_g(self) -> bool:
        return bool(
            self.model
            and (self.model.presets or self.model.base and self.route.startswith("cheers_"))
        )

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.supports_preset_zero_g

    @property
    def supports_preset_tv(self) -> bool:
        return bool(self.model and self.model.presets)

    @property
    def memory_slot_count(self) -> int:
        if not self.model or not self.model.initial_memory or self.route == "cheers_en":
            return 0
        return 1 if self.profile.key == "p2" else 5

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    @property
    def supports_massage_off_control(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return bool(self.model and self.model.light and self.profile.key == "p1")

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_level_control(self) -> bool:
        return self.supports_lights

    @property
    def light_level_max(self) -> int:
        return 255

    @property
    def light_intensity(self) -> int | None:
        value = self._coordinator.controller_state.get(LIGHT_LEVEL)
        return value if isinstance(value, int) else None

    def _admit(self) -> None:
        if self.model is None or self.route not in app.ROUTES:
            raise invalid("relax_motion_model")
        data = self._coordinator.entry.data
        if (
            data.get(CONF_BED_TYPE) != "relax_motion"
            or app.model_number(data.get(CONF_PRODUCT_TYPE)) != self.number
            or app.route_name(data.get(CONF_PROTOCOL_VARIANT)) != self.route
        ):
            raise failed("relax_motion_session")

    def _physical_current(self, link: Link) -> bool:
        return (
            self._link is link
            and self._coordinator.controller is self
            and self.client is link.client
            and link.client.is_connected
        )

    def _live(self, link: Link | None = None) -> Link:
        self._admit()
        current = self._link
        if (
            current is None
            or not self._physical_current(current)
            or link is not None
            and current is not link
        ):
            raise failed("relax_motion_session")
        return current

    def _assume(self, link: Link, *updates: StateUpdate) -> AbstractContextManager[None]:
        def show(delivery: Delivery) -> None:
            if not self._physical_current(link):
                return
            if delivery is Delivery.SENT:
                self.forward_controller_state_updates(*updates)
            elif delivery is Delivery.PARTIAL:
                self.forward_controller_state_updates(
                    *(StateUpdate(update.key, None) for update in updates)
                )

        return delivered(show)

    def _p1(self, command: int, parameter: int = 0, pid: int = 1) -> bytes:
        self._serial += 1
        return codec.p1(self._serial, pid, command, parameter)

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        self._admit()
        client = self.client
        if client is None or not client.is_connected:
            raise failed("relax_motion_session")
        services = list(client.services)
        if not services:
            raise failed("relax_motion_gatt")
        if self.number is not None and self.number > 450:
            service = next((s for s in services if s.uuid.lower() == codec.SERVICE), services[0])
        else:
            # BlueZ/Bleak exposes primary services only; preserve their returned
            # order. Optional is_primary lets other backends supply that fact.
            primary = [s for s in services if getattr(s, "is_primary", True) is True]
            service = services[-1] if services[-1] in primary else (primary or services)[0]
        writes = [
            c
            for c in service.characteristics
            if {"write", "write-without-response"}.intersection(c.properties)
        ]
        notifications = tuple(
            c for c in service.characteristics if {"notify", "indicate"}.intersection(c.properties)
        )
        if not writes or not notifications:
            raise failed("relax_motion_gatt")
        write = writes[-1]
        self._link = Link(
            client, write, notifications, "write" in write.properties, self.profile.key
        )

    async def _send(
        self,
        link: Link,
        frame: bytes,
        epoch: int,
        *,
        cleanup: bool = False,
        cancel_event: asyncio.Event | None = None,
        deadline: float | None = None,
    ) -> bool:
        async with self._ble_lock:
            owner = asyncio.current_task()
            cancel = (
                asyncio.Event()
                if cleanup
                else (
                    cancel_event if cancel_event is not None else self._coordinator.cancel_command
                )
            )

            async def write() -> bool:
                if cleanup:
                    if not self._physical_current(link):
                        return False
                else:
                    self._live(link)
                    if (
                        epoch != self._epoch
                        or cancel.is_set()
                        or owner is not None
                        and owner.cancelling()
                    ):
                        note_frame_skipped()
                        raise asyncio.CancelledError
                    if deadline is not None and monotonic() >= deadline:
                        return False
                self._record_command_trace(
                    link.write.uuid, frame, response=link.response, characteristic=link.write
                )
                await link.client.write_gatt_char(link.write, frame, response=link.response)
                note_frame_written(cancel)
                return True

            written = await settled(write())
            if not cleanup:
                self._live(link)
            return written

    async def _pause(self, seconds: float, epoch: int) -> None:
        await cancellable(asyncio.sleep(seconds), self._coordinator.cancel_command)
        if epoch != self._epoch:
            raise asyncio.CancelledError

    async def _release(self, link: Link) -> None:
        async def release() -> None:
            if not self._physical_current(link):
                return
            if link.protocol == "p1":
                await self._send(link, self._p1(1), self._epoch, cleanup=True)
            else:
                started = monotonic()
                error: Exception | None = None
                for offset in self.profile.release_ms:
                    await asyncio.sleep(max(0, offset / 1000 - (monotonic() - started)))
                    try:
                        await self._send(link, codec.P2_RELEASE, self._epoch, cleanup=True)
                    except Exception as err:
                        if error is None:
                            error = err
                if error is not None:
                    raise error

        await settled(release())

    async def stop_all(self) -> None:
        self._epoch += 1
        link = self._link
        if link is None or not self._physical_current(link):
            raise failed("relax_motion_session")
        await self._release(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link, epoch = self._live(), self._epoch
        for index in range(repeat_count):
            if index:
                await cancellable(
                    asyncio.sleep(repeat_delay_ms / 1000),
                    cancel_event or self._coordinator.cancel_command,
                )
            await self._send(link, command, epoch, cancel_event=cancel_event)

    def _motor(self, axis: str, up: bool) -> bytes:
        if not self.model or axis not in app.axes(self.model):
            raise invalid("relax_motion_control")
        if self.profile.key == "p2":
            return codec.normal(app.P2_AXES[axis][0 if up else 1])
        if axis == "all_motors":
            return self._p1(0x110 if up else 0x111)
        return self._p1(app.P1_AXES[axis], 10000 if up else 0)

    async def _move(self, axis: str, up: bool) -> None:
        await self.hold_control(f"{axis}_{'up' if up else 'down'}", 1000)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid("relax_motion_control")
        minimum = (
            self.profile.dispatch_ms
            if self.profile.key == "p1"
            else self.profile.release_ms[-1] + self.profile.refresh_ms
        )
        if duration_ms <= minimum:
            raise invalid("relax_motion_hold", minimum=minimum)

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        self.validate_hold_control(f"{motor}_{direction}", duration_ms)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        link, epoch = self._live(), self._epoch
        deadline = monotonic() + self.leased_hold_ms(duration_ms) / 1000
        pending = True
        sent = False
        try:
            await self._release(link)
            delay = (
                self.profile.dispatch_ms if self.profile.key == "p1" else self.profile.refresh_ms
            )
            await self._pause(delay / 1000, epoch)
            frame = self._motor(axis, direction == "up")
            while monotonic() < deadline:
                pending = False
                if not await self._send(link, frame, epoch, deadline=deadline):
                    break
                sent = True
                remaining = max(0, deadline - monotonic())
                await self._pause(
                    remaining if self.profile.key == "p1" else min(0.1, remaining), epoch
                )
            if not sent:
                note_frame_skipped()
                pending = False
                raise invalid("relax_motion_hold", minimum=duration_ms)
        except BaseException:
            if pending:
                note_frame_skipped()
            raise
        finally:
            await self._release(link)

    async def _burst(self, frame: bytes, *, prepare: bool = True) -> None:
        link, epoch = self._live(), self._epoch
        pending = True
        try:
            if prepare:
                await self._release(link)
                await self._pause(
                    0.1 if self.profile.key == "p2" else self.profile.dispatch_ms / 1000, epoch
                )
            if self.profile.key == "p1":
                pending = False
                await self._send(link, frame, epoch)
                return
            for index in range(3):
                if index:
                    await self._pause(0.1, epoch)
                pending = False
                await self._send(link, frame, epoch)
                pending = index < 2
            pending = False
        except BaseException:
            if pending:
                note_frame_skipped()
            raise
        finally:
            if self.profile.key == "p2":
                # Burst at 0/100/200, then release at 400/500 ms.
                async def finish() -> None:
                    await asyncio.sleep(0.1)
                    await self._release(link)

                await settled(finish())

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def _preset(self, name: str) -> None:
        if name != "flat" and not getattr(self, f"supports_preset_{name}"):
            raise invalid("relax_motion_control")
        await self._burst(
            codec.normal(0x08000000) if self.profile.key == "p2" else self._p1(app.PRESETS[name])
        )

    async def preset_memory(self, memory_num: int) -> None:
        self._memory(memory_num)
        await self._burst(
            codec.normal(0x10000)
            if self.profile.key == "p2"
            else self._p1(app.MEMORY[memory_num][0])
        )

    def _memory(self, slot: int) -> None:
        if isinstance(slot, bool) or not 1 <= slot <= self.memory_slot_count:
            raise invalid("relax_motion_memory")

    async def program_memory(self, memory_num: int) -> None:
        self._memory(memory_num)
        await self._burst(
            codec.extra(6, 0x050000)
            if self.profile.key == "p2"
            else self._p1(app.MEMORY[memory_num][1]),
            prepare=False,
        )

    async def editor_stop(self, axis: str) -> None:
        if (
            self.profile.key != "p1"
            or not self.model
            or axis not in app.axes(self.model)
            or axis not in app.EDITOR_STOPS
            or not self.memory_slot_count
        ):
            raise invalid("relax_motion_control")
        self._epoch += 1
        await self._send(self._live(), self._p1(app.EDITOR_STOPS[axis]), self._epoch, cleanup=True)

    async def massage(self, zone: str, level: int) -> None:
        self._admit()
        if (
            self.model is None
            or self.profile.key != "p1"
            or self.route == "cheers_en"
            or zone not in ("head", "foot")
            or not getattr(self.model, f"{zone}_massage")
            or level not in range(4)
        ):
            raise invalid("relax_motion_control")
        if self._rhythm is None or self._rhythm and not level:
            raise invalid("relax_motion_control")
        if not level:
            command = app.MASSAGE[zone][0] if self.model.separate_massage_stop else 0x200
        elif self._rhythm:
            command = app.STRENGTH[zone][level - 1]
        else:
            command = app.MASSAGE[zone][level]
        link, epoch = self._live(), self._epoch
        await self._release(link)
        await self._pause(self.profile.dispatch_ms / 1000, epoch)

        def show(delivery: Delivery) -> None:
            if not self._physical_current(link):
                return
            if command == 0x200:
                if delivery is Delivery.SENT:
                    self._set_rhythm(False)
                elif delivery is Delivery.PARTIAL:
                    self._set_rhythm(None)
            if delivery is Delivery.SENT:
                self.forward_controller_state_updates(massage_intensity(zone)(level or None))
            elif delivery is Delivery.PARTIAL:
                self.forward_controller_state_updates(massage_intensity(zone)(None))

        with delivered(show):
            await self._send(link, self._p1(command), epoch)

    async def massage_off(self) -> None:
        if not self.model or not (self.model.head_massage or self.model.foot_massage):
            raise invalid("relax_motion_control")
        if self.route == "cheers_zh" and self.model.rhythm:
            await self.rhythm(0)
        else:
            link = self._live()
            with self._assume(
                link, massage_intensity("head")(None), massage_intensity("foot")(None)
            ):
                await self._burst(self._p1(0x200))

    def _set_rhythm(self, value: bool | None) -> None:
        self._rhythm = value
        self.forward_controller_state_updates(
            state.RHYTHM(value),
            massage_intensity("head")(None),
            massage_intensity("foot")(None),
        )

    async def rhythm(self, mode: int) -> None:
        if (
            self.route != "cheers_zh"
            or not self.model
            or not self.model.rhythm
            or mode not in (0, 1, 2)
        ):
            raise invalid("relax_motion_control")

        def show(delivery: Delivery) -> None:
            if not self._physical_current(link):
                return
            if delivery is Delivery.SENT:
                self._set_rhythm(bool(mode))
            elif delivery is Delivery.PARTIAL:
                self._set_rhythm(None)

        # Preparation STOP must not make the rhythm command look delivered.
        link, epoch = self._live(), self._epoch
        await self._release(link)
        await self._pause(self.profile.dispatch_ms / 1000, epoch)
        with delivered(show):
            await self._send(link, self._p1(app.RHYTHM[mode]), epoch)

    async def cosy(self, enabled: bool) -> None:
        if not self.route.startswith("cheers_") or not self.model or not self.model.cosy:
            raise invalid("relax_motion_control")
        if enabled:
            await self._burst(self._p1(0x601))
        else:
            await self.stop_all()

    async def lights_on(self) -> None:
        await self.set_light_level(255)

    async def lights_off(self) -> None:
        if not self.supports_lights:
            raise invalid("relax_motion_control")
        link, epoch = self._live(), self._epoch
        await self._release(link)
        await self._pause(self.profile.dispatch_ms / 1000, epoch)
        with self._assume(link, UNDER_BED_LIGHTS_ON(False), LIGHT_LEVEL(0)):
            await self._send(link, self._p1(0x500), epoch)

    async def set_light_level(self, level: int) -> None:
        if not self.supports_lights or isinstance(level, bool) or not 0 <= level <= 255:
            raise invalid("relax_motion_control")
        # STOP is preparation, outside the setting's delivery window.
        link, epoch = self._live(), self._epoch
        await self._release(link)
        await self._pause(self.profile.dispatch_ms / 1000, epoch)
        with self._assume(link, UNDER_BED_LIGHTS_ON(True), LIGHT_LEVEL(level)):
            await self._send(link, self._p1(0x501, 0xFFFFFF00 + level), epoch)

    async def setting(self, key: str, value: float | bool) -> None:
        if self.profile.key != "p1" or key != "light_time" and not self._snore_ready:
            raise invalid("relax_motion_control")
        if key == "light_time" and (not 10 <= value <= 6000 or value % 10):
            raise invalid("relax_motion_control")
        if key == "interval" and (not 0 <= value <= 120 or value % 1):
            raise invalid("relax_motion_control")
        command, parameter, update = {
            "light_time": (app.SETTINGS["light_time"], int(value), state.LIGHT_TIME(int(value))),
            "interval": (app.SETTINGS["interval"], int(value) * 60, state.INTERVAL(int(value))),
            "snore": (app.SETTINGS["snore"], int(bool(value)), state.SNORE(bool(value))),
        }[key]
        link, epoch = self._live(), self._epoch
        pending = True
        with self._assume(link, update):
            try:
                await self._pause(self.profile.dispatch_ms / 1000, epoch)
                pending = False
                await self._send(link, self._p1(command, parameter, 3), epoch)
            finally:
                if pending:
                    note_frame_skipped()

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.profile.key != "p1" or not self.model:
            return ()
        return (
            ControllerNumberSpec(
                "relax_motion_light_time",
                "relax_motion_light_time",
                state.LIGHT_TIME,
                10,
                6000,
                10,
                lambda c, v: _bed(c).setting("light_time", v),
                "s",
                entity_category=EntityCategory.CONFIG,
                entity_registry_enabled_default=False,
            ),
            ControllerNumberSpec(
                "relax_motion_snore_interval",
                "relax_motion_snore_interval",
                state.INTERVAL,
                0,
                120,
                1,
                lambda c, v: _bed(c).setting("interval", v),
                "min",
                entity_category=EntityCategory.CONFIG,
                entity_registry_enabled_default=False,
            ),
        ) + tuple(
            ControllerNumberSpec(
                f"relax_motion_{zone}_intensity",
                f"massage_{zone}_intensity",
                massage_intensity(zone),
                1,
                3,
                1,
                _massage_level_call(zone),
                card=CARD_MASSAGE,
            )
            for zone in ("head", "foot")
            if getattr(self.model, f"{zone}_massage") and self.route != "cheers_en"
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            (
                ControllerSwitchSpec(
                    "relax_motion_snore",
                    "relax_motion_snore",
                    lambda c, v: _bed(c).setting("snore", v),
                    state.SNORE,
                    assumed_state=True,
                    available_fn=lambda c: _bed(c)._snore_ready,
                ),
            )
            if self.profile.key == "p1" and self.model
            else ()
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            (
                ControllerStateBinarySensorSpec(
                    "relax_motion_sleep",
                    "relax_motion_sleep",
                    state.SLEEP,
                    "mdi:sleep",
                    entity_registry_enabled_default=True,
                ),
            )
            if self.profile.key == "p1" and self.model
            else ()
        )

    def controller_button_available(self, key: str) -> bool:
        if key in ("relax_motion_head_massage_0", "relax_motion_foot_massage_0"):
            return self._rhythm is False
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec] = []
        if self.model is None or self.profile.key != "p1":
            return ()
        for zone in ("head", "foot"):
            if getattr(self.model, f"{zone}_massage") and self.route != "cheers_en":
                for level in () if self._rhythm else (0,):
                    spec = catalog_button(
                        f"relax_motion_{zone}_massage_{level}",
                        f"{zone.title()} massage {'off' if level == 0 else level}",
                        _massage_call(zone, level),
                        kind=Kind.MASSAGE,
                    )
                    if spec:
                        specs.append(spec)
        if self.model.head_massage or self.model.foot_massage:
            spec = catalog_button(
                "relax_motion_massage_off",
                "Stop massage",
                lambda c: _bed(c).massage_off(),
                kind=Kind.MASSAGE,
            )
            if spec:
                specs.append(spec)
        if self.route == "cheers_zh" and self.model.rhythm:
            for mode in range(3):
                spec = catalog_button(
                    f"relax_motion_rhythm_{mode}",
                    f"Variable-frequency massage {mode}"
                    if mode
                    else "Variable-frequency massage off",
                    _rhythm_call(mode),
                    kind=Kind.MASSAGE,
                )
                if spec:
                    specs.append(spec)
        if self.route.startswith("cheers_") and self.model.cosy:
            for enabled in (True, False):
                spec = catalog_button(
                    f"relax_motion_cosy_{int(enabled)}",
                    f"Comfort sleep {'on' if enabled else 'off'}",
                    _cosy_call(enabled),
                    kind=Kind.PRESET,
                )
                if spec:
                    specs.append(spec)
        for axis in app.axes(self.model):
            if axis in app.EDITOR_STOPS and self.memory_slot_count:
                spec = catalog_button(
                    f"relax_motion_editor_stop_{axis}",
                    f"Stop {axis} in memory editor",
                    _editor_call(axis),
                    kind=Kind.EXTRA,
                )
                if spec:
                    specs.append(spec)
        return tuple(specs)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return
        try:
            for char in link.notifications:
                await link.client.start_notify(char, self._notify_callback_for(link, char.uuid))
                self._notifying.append(char)
        except BaseException:
            await self.stop_notify()
            raise

    def _notify_callback_for(
        self, link: Link, uuid: str
    ) -> Callable[[BleakGATTCharacteristic, bytearray], None]:
        def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            self._notification(link, bytes(data), uuid)

        return receive

    def _notification(self, link: Link, data: bytes, uuid: str) -> None:
        if (
            self._link is not link
            or self._coordinator.controller is not self
            or self.client is not link.client
            or not link.client.is_connected
            or self.profile.key != "p1"
        ):
            return
        self.forward_raw_notification(uuid, data)
        result = codec.sleep_state(data)
        if result is not None:
            self._snore_ready |= result
            self.forward_controller_state_updates(
                state.SLEEP(result), state.SNORE_READY(self._snore_ready)
            )

    async def stop_notify(self) -> None:
        link = self._link
        chars, self._notifying = self._notifying, []
        if link and link.client.is_connected:
            for char in chars:
                await link.client.stop_notify(char)

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()
        if self.profile.key == "p1":
            epoch = self._epoch
            await self._pause(
                1.5 if self.route.startswith("cheers_") else self.profile.dispatch_ms / 1000, epoch
            )
            for _char in self._notifying:
                await self._send(self._live(), self._p1(0x1201, pid=2), epoch)

    def on_disconnect(self) -> None:
        self._epoch += 1
        self._link = None
        self._notifying.clear()
        self._snore_ready = False
        self._rhythm = False
        self.forward_controller_state_updates(
            state.RHYTHM(None),
            state.SLEEP(None),
            state.SNORE_READY(None),
            state.SNORE(None),
            state.INTERVAL(None),
            state.LIGHT_TIME(None),
            massage_intensity("head")(None),
            massage_intensity("foot")(None),
            UNDER_BED_LIGHTS_ON(None),
            LIGHT_LEVEL(None),
        )

    async def move_back_up(self) -> None:
        await self._move("back", True)

    async def move_back_down(self) -> None:
        await self._move("back", False)

    async def move_legs_up(self) -> None:
        await self._move("legs", True)

    async def move_legs_down(self) -> None:
        await self._move("legs", False)

    move_head_up = move_back_up
    move_head_down = move_back_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all


def _bed(controller: BedController) -> RelaxMotionController:
    if not isinstance(controller, RelaxMotionController):
        raise invalid("relax_motion_control")
    return controller


async def build_controller(ctx: BuildContext) -> RelaxMotionController:
    return RelaxMotionController(ctx.coordinator)


def _move_call(axis: str, up: bool) -> MotorCommandCallable:
    async def move(controller: BedController) -> None:
        await _bed(controller)._move(axis, up)

    return move


def _massage_call(zone: str, level: int) -> MotorCommandCallable:
    async def action(controller: BedController) -> None:
        await _bed(controller).massage(zone, level)

    return action


def _massage_level_call(zone: str) -> Callable[[BedController, float], Awaitable[None]]:
    async def action(controller: BedController, level: float) -> None:
        if isinstance(level, bool) or level not in (1, 2, 3):
            raise invalid("relax_motion_control")
        await _bed(controller).massage(zone, int(level))

    return action


def _rhythm_call(mode: int) -> MotorCommandCallable:
    async def action(controller: BedController) -> None:
        await _bed(controller).rhythm(mode)

    return action


def _cosy_call(enabled: bool) -> MotorCommandCallable:
    async def action(controller: BedController) -> None:
        await _bed(controller).cosy(enabled)

    return action


def _editor_call(axis: str) -> MotorCommandCallable:
    async def action(controller: BedController) -> None:
        await _bed(controller).editor_stop(axis)

    return action
