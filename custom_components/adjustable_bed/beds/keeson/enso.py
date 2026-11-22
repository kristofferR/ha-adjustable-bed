"""Enso's dynamic GATT roles, page actions and connection-owned release."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...command_scheduler import CommandContext, current_command_context, note_frame_skipped
from ...const import CONF_PRODUCT_TYPE
from ...errors import failed, invalid
from ...profiles import enso as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    address: str
    response: bool


class EnsoController(KeesonController):
    """Share the family's entity APIs, with only Enso-proven controls."""

    def __init__(self, coordinator: AdjustableBedCoordinator, layout: str = "2") -> None:
        if layout not in app.PROFILES:
            raise invalid("enso_control_invalid")
        super().__init__(coordinator, char_uuid=app.WRITE_UUID)
        self.profile: app.EnsoProfile = app.PROFILES[layout]
        self._link: _Link | None = None
        self._subscribed: _Link | None = None
        self._subscription_token: object | None = None
        self._cleanup: tuple[_Link, CommandContext] | None = None

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_device_rename(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "layout": self.profile.key,
            "service_selection": "runtime",
            "write_mode": "runtime properties",
            "notification_setup": "Bleak subscription",
        }

    @property
    def motor_translation_keys(self) -> dict[str, str]:
        return {"head": "keeson_back", "feet": "feet", "tilt": "waist", "lumbar": "lumbar"}

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # The selected layout owns the axes even before a live connection.
        names = {"back": "head", "foot": "feet", "waist": "tilt", "lumbar": "lumbar"}
        specs = []
        for motor in self.profile.motors:
            if motor == "combined":
                continue
            key = names[motor]
            specs.append(
                MotorControlSpec(
                    key,
                    self.motor_translation_keys[key],
                    lambda c, key=key: cast(EnsoController, c)._move_motor(key, True),
                    lambda c, key=key: cast(EnsoController, c)._move_motor(key, False),
                    lambda c: c.stop_all(),
                )
            )
        if "combined" in self.profile.motors:
            specs.append(
                MotorControlSpec(
                    "both",
                    "back_legs",
                    lambda c: cast(EnsoController, c)._move_motor("both", True),
                    lambda c: cast(EnsoController, c)._move_motor("both", False),
                    lambda c: c.stop_all(),
                    scheduler_resource="motor:*",
                )
            )
        return tuple(
            MotorControlSpec(
                s.key,
                s.translation_key,
                s.open_fn,
                s.close_fn,
                s.stop_fn,
                position_key=s.position_key,
                max_angle=s.max_angle,
                scheduler_resource="motor:*",
                hold=ControllerMotorHoldSpec(
                    f"{s.key}_up", f"{s.key}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for s in specs
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *(
                f"{s.key}_{direction}"
                for s in self.motor_control_specs
                for direction in ("up", "down")
            ),
            "memory_A",
            "memory_B",
            "timer_memory_page",
            *(
                ("massage_mode",)
                if "lumbar" in self.profile.motors and "waist" not in self.profile.motors
                else ()
            ),
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {"preset_memory_1": "memory_A", "preset_memory_2": "memory_B"}.get(key)
        return ControllerHoldSpec(control) if control else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        labels = {
            "head_massage_increase": "Increase head massage",
            "head_massage_decrease": "Decrease head massage",
            "foot_massage_increase": "Increase foot massage",
            "foot_massage_decrease": "Decrease foot massage",
            "massage_level": "Cycle massage intensity",
            "timer_massage_page": "Cycle massage timer",
            "massage_mode": "Cycle massage mode",
        }
        keys = list(app.MASSAGE_WORDS)
        if "massage_mode" in self.held_control_options:
            keys.append("massage_mode")
        return tuple(
            ControllerButtonSpec(
                f"enso_{key}",
                labels[key],
                lambda c, key=key: cast(EnsoController, c).action(key),
                translation_key=f"enso_{key}",
                card=CARD_MASSAGE,
                hold=ControllerHoldSpec(key) if key in app.HELD_WORDS else None,
            )
            for key in keys
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            massage_timer_sensor_spec(
                "enso_massage_timer",
                "enso_massage_timer",
                MASSAGE_TIMER_MINUTES,
                card=CARD_MASSAGE_TIMER,
            ),
        )

    @property
    def supports_light_state_feedback(self) -> bool:
        """Every status notification reports the light."""
        return self.supports_light_toggle_control

    def _live(self, link: _Link | None = None) -> _Link:
        selected = self._link
        if (
            selected is None
            or link is not None
            and selected is not link
            or self.client is not selected.client
            or not selected.client.is_connected
            or self._coordinator.address.upper() != selected.address
        ):
            raise failed("enso_session_changed")
        return selected

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise failed("enso_session_changed")
        write = notify = None
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.lower() == app.WRITE_UUID:
                    write = char
                if char.uuid.lower() == app.NOTIFY_UUID:
                    notify = char
        if write is None or notify is None:
            raise failed("enso_gatt_missing")
        if not {"write", "write-without-response"}.intersection(write.properties):
            raise failed("enso_gatt_missing")
        # App leaves Android's runtime writeType untouched. Prefer acknowledged
        # writes when available; this is a transport choice, not a device claim.
        self._link = _Link(
            client, write, notify, self._coordinator.address.upper(), "write" in write.properties
        )

    async def _send(
        self, link: _Link, frame: bytes, cancel: asyncio.Event, *, cleanup: bool = False
    ) -> None:
        def check() -> None:
            self._live(link)

        try:
            self._live(link)
            if not cleanup and self._subscribed is not link:
                await self.start_notify()
            await self._write_gatt_with_retry(
                link.write.uuid,
                frame,
                cancel_event=cancel,
                response=link.response,
                characteristic=link.write,
                expected_client=link.client,
                before_write=check,
                track_command_write=not cleanup,
            )
        except ConnectionError as err:
            raise failed("enso_session_changed") from err

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                note_frame_skipped()
                return
            if index:
                try:
                    await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)
                except asyncio.CancelledError:
                    note_frame_skipped()
                    if not cancel.is_set():
                        raise
                    return
            await self._send(link, command, cancel)

    async def _release(self, link: _Link, *, acknowledge: CommandContext | None = None) -> None:
        async def send() -> None:
            await self._send(link, self._build_command(0), asyncio.Event(), cleanup=True)
            if acknowledge is not None:
                acknowledge.cleanup_stop_sent = True
                self._cleanup = (link, acknowledge)

        await settled(send())

    async def _run(
        self,
        word: int,
        *,
        held: bool = False,
        release: bool = False,
        duration_ms: int | None = None,
    ) -> None:
        link = self._live()
        if self._coordinator.cancel_command.is_set():
            note_frame_skipped()
            return
        cancel = self._coordinator.cancel_command
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = False
        self._cleanup = None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.leased_hold_ms(duration_ms or 1000) / 1000
        try:
            while True:
                if cancel.is_set():
                    note_frame_skipped()
                    return
                started = loop.time()
                await self._send(link, self._build_command(word), cancel)
                if not held:
                    return
                remaining = min(deadline, started + app.REFRESH_MS / 1000) - loop.time()
                if remaining > 0:
                    try:
                        await cancellable(asyncio.sleep(remaining), cancel)
                    except asyncio.CancelledError:
                        # The final wait only holds the release deadline; no
                        # refresh is missing once the last planned frame went out.
                        if started + app.REFRESH_MS / 1000 + 1e-6 < deadline:
                            note_frame_skipped()
                        if not cancel.is_set():
                            raise
                        return
                if loop.time() + 1e-6 >= deadline:
                    return
        finally:
            if release or held:
                await self._release(link, acknowledge=context)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
            return
        if motor not in {s.key for s in self.motor_control_specs}:
            raise invalid("enso_control_invalid")
        count, _ = self.motor_pulse_settings()
        await self._run(
            app.MOTOR_WORDS[motor][0 if direction else 1],
            held=True,
            duration_ms=max(1, count) * app.REFRESH_MS,
        )

    async def _write_single_shot(self, command: bytes) -> None:
        await self._run(int.from_bytes(command[3:7], "little"), release=True)

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._run(self.profile.memory[memory_num], held=True)

    async def lights_toggle(self) -> None:
        await self._run(0x20000)

    async def action(self, key: str) -> None:
        if key in app.MASSAGE_WORDS:
            await self._run(app.MASSAGE_WORDS[key])
        elif key in self.held_control_options:
            await self._run(app.HELD_WORDS[key], held=True)
        else:
            raise invalid("enso_control_invalid")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid("enso_control_invalid")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("enso_duration_invalid")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control in app.HELD_WORDS:
            word = app.HELD_WORDS[control]
        else:
            motor, direction = control.rsplit("_", 1)
            word = app.MOTOR_WORDS[motor][0 if direction == "up" else 1]
        await self._run(word, held=True, duration_ms=self.leased_hold_ms(duration_ms))

    async def stop_all(self) -> None:
        link, context = self._live(), current_command_context()
        if self._cleanup is not None and context is not None:
            owner_link, owner = self._cleanup
            if (
                owner_link is link
                and owner.scheduler_token is context.scheduler_token
                and any(owner is previous for previous in context.preempted_contexts)
                and owner.cleanup_stop_sent
            ):
                self._cleanup = None
                owner.cleanup_stop_sent = False
                return
        self._cleanup = None
        await self._release(link)

    def validate_device_rename(self, name: str) -> None:
        name = app.trim_name(name)
        if not name or len(name.encode("utf-16-le")) // 2 > 14:
            raise invalid("enso_name_invalid")

    async def rename_device(self, name: str) -> None:
        self.validate_device_rename(name)
        await self.write_command(app.rename(name))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed is link:
            return

        token = self._subscription_token = object()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._subscription_token is not token
                or self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
                or self._coordinator.address.upper() != link.address
                or sender.handle != link.notify.handle
                or sender.uuid.lower() != app.NOTIFY_UUID
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            status = app.parse_status(bytes(data))
            if status is not None:
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(status.light))
                if status.timer_minutes is not None:
                    self.forward_controller_state_updates(
                        MASSAGE_TIMER_MINUTES(status.timer_minutes)
                    )

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
            if self._subscription_token is token:
                self._subscribed = link
        except BaseException:
            if self._subscription_token is token:
                self._subscription_token = None
            raise

    async def stop_notify(self) -> None:
        link, self._subscribed = self._subscribed, None
        self._subscription_token = None
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None), MASSAGE_TIMER_MINUTES(None))
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = self._subscribed = None
        self._subscription_token = None
        self._cleanup = None
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None), MASSAGE_TIMER_MINUTES(None))


async def build_controller(ctx: BuildContext) -> BedController:
    return EnsoController(ctx.coordinator, str(ctx.data.get(CONF_PRODUCT_TYPE, "2")))
