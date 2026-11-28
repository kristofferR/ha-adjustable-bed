"""Dunlopillo's concrete GATT session over shared Keeson control shapes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ...command_scheduler import note_frame_skipped
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import dunlopillo as app
from ..builder import BuildContext
from ..catalog_buttons import catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from ..lifecycle import ControllerSession
from .controller import KeesonController, _wait_unless_cancelled

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

TIMER = StateKey[int | None]("dunlopillo_massage_timer")
# Host cleanup budget, independent of the bed's protocol timing.
_NOTIFY_CLEANUP_TIMEOUT: Final = 1.0


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notifies: tuple[BleakGATTCharacteristic, ...]
    generation: int
    address: str


@dataclass(slots=True)
class _Subscription:
    characteristic: BleakGATTCharacteristic
    active: bool = True


class _HoldExpired(Exception):
    """The finite host hold budget ended before dispatch."""


class DunlopilloController(KeesonController):
    """No name inference, startup command, combined keys or position feedback."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, layout: str) -> None:
        if layout not in app.PROFILES:
            raise invalid("dunlopillo_layout_invalid")
        super().__init__(coordinator, variant="base", char_uuid=app.WRITE_UUID)
        self.layout, self.profile = layout, app.PROFILES[layout]
        self._link: _Link | None = None
        self._subscriptions: dict[int, _Subscription] = {}

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_device_rename(self) -> bool:
        return True

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and expected is not link
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.connection_generation != link.generation
            or self._coordinator.address.upper() != link.address
        ):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        write = None
        notifies: list[BleakGATTCharacteristic] = []
        # Every receive handle is enabled; only the write role is last-match-wins.
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.lower() == app.WRITE_UUID:
                    write = char
                elif char.uuid.lower() == app.NOTIFY_UUID:
                    notifies.append(char)
        if (
            write is None
            or not notifies
            or not {"write", "write-without-response"}.intersection(write.properties)
        ):
            raise BedNotConnectedError()
        self._link = _Link(
            client,
            write,
            tuple(notifies),
            self._coordinator.connection_generation,
            self._coordinator.address.upper(),
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        if self._link is None:
            raise BedNotConnectedError()
        # The coordinator publishes the new generation after capability discovery.
        self._link = replace(self._link, generation=self._coordinator.connection_generation)
        await session.async_start_notify()

    async def _write(
        self,
        link: _Link,
        command: bytes,
        *,
        count: int = 1,
        cancel: asyncio.Event | None = None,
        deadline: float | None = None,
    ) -> None:
        def validate() -> None:
            self._live(link)
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                note_frame_skipped()
                raise _HoldExpired

        validate()
        await self._write_gatt_with_retry(
            link.write.uuid,
            command,
            count,
            app.REFRESH_MS,
            cancel_event=cancel if cancel is not None else self._coordinator.cancel_command,
            characteristic=link.write,
            expected_client=link.client,
            response="write-without-response" not in link.write.properties,
            # Handler.postDelayed starts its interval after the prior dispatch.
            wall_clock_pacing=False,
            before_write=validate,
            settle_write=True,
            track_command_write=True,
        )
        self._live(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write(self._live(), command, count=repeat_count, cancel=cancel_event)

    async def _release(self, link: _Link) -> None:
        # A stale release must never be sent to a replacement connection.
        await self._write(link, app.codec.frame(0), cancel=asyncio.Event())

    async def _held(self, key: str, duration_ms: int | None = None) -> None:
        row = app.CONTROLS[self.layout][key]
        link = self._live()
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            note_frame_skipped()
            return
        count = (
            self._held_cadence()[0] if duration_ms is None else -(-duration_ms // app.REFRESH_MS)
        )
        loop = asyncio.get_running_loop()
        deadline = (
            loop.time()
            + (duration_ms if duration_ms is not None else count * app.REFRESH_MS) / 1000
        )
        try:
            await self._write(
                link, app.codec.frame(row.word), count=count, cancel=cancel, deadline=deadline
            )
            await _wait_unless_cancelled(cancel, max(0, deadline - loop.time()))
        except _HoldExpired:
            pass
        finally:
            await self._release(link)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in app.AXES[self.layout]:
            raise self.not_supported(motor)
        if direction is None:
            await self.stop_all()
        else:
            await self._held(f"{motor}_{'up' if direction else 'down'}")

    async def stop_all(self) -> None:
        await self._release(self._live())

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise self.not_supported(control)
        self.validate_hold_control(control, duration_ms)
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= 60000:
            raise invalid("dunlopillo_hold_duration")
        if self.leased_hold_refreshes(app.REFRESH_MS) is not None:
            await self._held(control)
        else:
            await self._held(control, duration_ms)

    async def _write_single_shot(self, command: bytes) -> None:
        await self._write(self._live(), command)

    async def action(self, control: str) -> None:
        if self._coordinator.cancel_command.is_set():
            note_frame_skipped()
            return
        row = app.CONTROLS[self.layout][control]
        if row.mode == "hold":
            await self._held(control)
            return
        link = self._live()
        if row.mode == "single":
            await self._write(link, self._build_command(row.word))
            return
        try:
            await self._write(link, self._build_command(row.word))
            await _wait_unless_cancelled(
                self._coordinator.cancel_command, app.PULSE_RELEASE_MS / 1000
            )
        finally:
            await self._release(link)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{spec.key}_up", f"{spec.key}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for spec in super().motor_control_specs
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        excluded = {
            "flat",
            "zero_g",
            "light",
            *(f"{axis}_{d}" for axis in app.AXES[self.layout] for d in ("up", "down")),
        }
        specs = []
        for key, row in app.CONTROLS[self.layout].items():
            if key in excluded:
                continue
            spec = catalog_button(
                f"dunlopillo_{key}",
                row.label,
                lambda c, key=key: cast(DunlopilloController, c).action(key),
                scheduler_resource="*",
                requires_confirmation=key == "reset",
                hold=ControllerHoldSpec(key) if row.mode == "hold" and key != "reset" else None,
            )
            if spec is not None:
                specs.append(spec)
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            massage_timer_sensor_spec(
                "dunlopillo_massage_timer", "dunlopillo_massage_timer", TIMER
            ),
        )

    def validate_device_rename(self, name: str) -> None:
        name = app.trim_name(name)
        if not name or len(name.encode("utf-16-le")) // 2 > 14:
            raise invalid("dunlopillo_name_invalid")

    async def rename_device(self, name: str) -> None:
        self.validate_device_rename(name)
        await self.write_command(app.rename(name))

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object] | None:
        if command.startswith(b"\xef\x02"):
            # The entire record contains a name, including its checksum.
            return {"redacted": True, "length": len(command), "command": "rename"}
        return super()._format_command_trace_payload(command)

    def _receive(
        self,
        link: _Link,
        subscription: _Subscription,
        sender: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        char = subscription.characteristic
        if (
            not subscription.active
            or self._subscriptions.get(char.handle) is not subscription
            or sender.handle != char.handle
        ):
            return
        try:
            self._live(link)
        except BedNotConnectedError:
            return
        self.forward_raw_notification(char.uuid, bytes(data))
        minutes = app.timer_minutes(bytes(data))
        if minutes is not None:
            self.forward_controller_state_updates(TIMER(minutes))

    async def _stop_subscription(self, link: _Link, subscription: _Subscription) -> None:
        self._live(link)
        try:
            async with asyncio.timeout(_NOTIFY_CLEANUP_TIMEOUT):
                await link.client.stop_notify(subscription.characteristic)
        except BleakError, TimeoutError:
            # An unsupported or interrupted subscribe may never have registered.
            pass
        self._live(link)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        for char in link.notifies:
            previous = self._subscriptions.get(char.handle)
            if previous is not None:
                if previous.active:
                    continue
                await self._stop_subscription(link, previous)
            subscription = _Subscription(char)
            self._subscriptions[char.handle] = subscription

            def receive(
                sender: BleakGATTCharacteristic,
                data: bytearray,
                subscription: _Subscription = subscription,
            ) -> None:
                self._receive(link, subscription, sender, data)

            try:
                await link.client.start_notify(char, receive)
                self._live(link)
            except BleakError, TimeoutError:
                subscription.active = False
                # Timer subscription is optional only on this exact live link.
                self._live(link)
            except BaseException:
                subscription.active = False
                raise
        self._live(link)

    async def stop_notify(self) -> None:
        link = self._link
        subscriptions = tuple(self._subscriptions.values())
        # Fence every old callback before the first backend await. Keep the GATT
        # binding so the coordinator can restore a failed disconnect's session.
        for subscription in subscriptions:
            subscription.active = False
        if self._coordinator.controller is self:
            self.invalidate_diagnostics()
        if link is None:
            return

        try:
            async with asyncio.timeout(_NOTIFY_CLEANUP_TIMEOUT):
                for subscription in subscriptions:
                    try:
                        self._live(link)
                    except BedNotConnectedError:
                        return
                    await self._stop_subscription(link, subscription)
                    handle = subscription.characteristic.handle
                    if self._subscriptions.get(handle) is subscription:
                        self._subscriptions.pop(handle)
        except TimeoutError:
            # Callbacks remain fenced; a retained link can retry subscription.
            self._live(link)

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(TIMER(None))

    def on_disconnect(self) -> None:
        self._link = None
        self._subscriptions.clear()
        self._motor_state.clear()
        if self._coordinator.controller is self:
            self.invalidate_diagnostics()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"layout": self.layout, "hardware": "UNVERIFIED"}


async def build_controller(ctx: BuildContext) -> DunlopilloController:
    return DunlopilloController(
        ctx.coordinator, layout="b2" if ctx.variant in (None, "auto") else ctx.variant
    )
