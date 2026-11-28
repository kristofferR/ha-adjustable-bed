"""Platinum's session, opaque keys and cancellation-safe common release."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from math import ceil
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ..bluetooth_transport import TransportClass, async_path_for_source, client_source
from ..card import CARD_HIDDEN
from ..codec import aminach as codec
from ..command_scheduler import CommandContext, current_command_context, note_frame_skipped
from ..errors import BedNotConnectedError, invalid
from ..profiles import aminach as app
from .base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from .cancellation import settled
from .catalog_buttons import Kind, catalog_button
from .entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    MotorControlSpec,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


@dataclass(eq=False, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    adapter_address: str | None
    recognized: bool = False
    indicator: int | None = None
    response_task: asyncio.Task[None] | None = None


class AminachController(ProfileExecution[app.AminachProfile], BedController):
    """One receiver, with no measured positions or wire side addressing."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = app.PLATINUM
        self._link: _Link | None = None
        self._gesture_context: CommandContext | None = None
        self._release_generation: int | None = None
        count = coordinator.motor_count
        self.axes = app.LAYOUTS[count if count in app.LAYOUTS else self.profile.default_motor_count]

    @property
    def control_characteristic_uuid(self) -> str:
        return app.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                hold=ControllerMotorHoldSpec(
                    f"{spec.key}_up", f"{spec.key}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for spec in super().motor_control_specs
            if spec.key in self.axes
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for action, label, kind in (
            ("sleep", "Sleep", Kind.EXTRA),
            ("light", "Light", Kind.LIGHT),
            ("memo", "Memo", Kind.EXTRA),
        ):

            async def press(controller: BedController, action: str = action) -> None:
                await require_controller(controller, AminachController).press(action)

            spec = catalog_button(
                action,
                label,
                press,
                kind=kind,
                hold=ControllerHoldSpec(action, release_button_key="aminach_release"),
            )
            assert spec is not None
            buttons.append(replace(spec, entity_registry_enabled_default=True))
        buttons.append(
            ControllerButtonSpec(
                "aminach_release",
                "Release held control",
                lambda ctrl: ctrl.stop_all(),
                translation_key="aminach_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return tuple(buttons)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            "sleep",
            "light",
            "memo",
            *(f"{axis}_{direction}" for axis in self.axes for direction in ("up", "down")),
        )

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
            or self._coordinator.controller is not self
        ):
            raise BedNotConnectedError()
        return current

    def _adapter_address(self, client: BleakClient) -> str | None:
        source = client_source(client)
        path = async_path_for_source(self._coordinator.hass, source)
        address = source if path is not None and path.transport is TransportClass.LOCAL else None
        if path is not None and path.source_domain == "esphome":
            # ESPHome's source falls back to its Wi-Fi MAC on older firmware.
            # Only its explicit Bluetooth address is a proven initiator identity.
            info = getattr(getattr(client, "_backend", None), "_device_info", None)
            address = getattr(info, "bluetooth_mac_address", None)
        if not isinstance(address, str):
            return None
        try:
            codec.adapter_response(address)
        except ValueError:
            return None
        return address

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        await super().start_notify(callback)
        if self._link is not None:
            self._live()
            return
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        for service in client.services:
            if service.uuid.lower() != app.SERVICE:
                continue
            write, notify = (
                service.get_characteristic(app.WRITE),
                service.get_characteristic(app.NOTIFY),
            )
            if (
                write is None
                or notify is None
                or not {"write", "write-without-response"}.intersection(write.properties)
                or "notify" not in notify.properties
            ):
                continue
            link = self._link = _Link(
                client,
                write,
                notify,
                "write-without-response" not in write.properties,
                self._adapter_address(client),
            )
            try:
                await client.start_notify(
                    notify, lambda _char, data, link=link: self._notification(link, bytes(data))
                )
                self._live(link)
            except BaseException:
                if self._link is link:
                    self.on_disconnect()
                raise
            return
        raise BedNotConnectedError("bed_missing_service")

    def _format_command_trace_payload(self, command: bytes) -> dict[str, Any] | None:
        if command.startswith(b"\xb1\x07\x00"):
            return {"redacted": True, "length": len(command), "action": "Initiator adapter address"}
        return super()._format_command_trace_payload(command)

    async def _frame(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        command: bool = True,
        deadline: float | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        def check() -> None:
            self._live(link)
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                raise _Expired

        await self._write_gatt_with_retry(
            app.WRITE,
            frame,
            cancel_event=cancel,
            response=link.response,
            characteristic=link.write,
            expected_client=link.client,
            before_write=check,
            track_command_write=command,
            settle_write=True,
            write_timeout=15,
            on_write=on_write,
        )
        self._live(link)

    async def stop_notify(self) -> None:
        await super().stop_notify()
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        link, self._link = self._link, None
        if link is not None and link.response_task is not None:
            link.response_task.cancel()

    def _notification(self, link: _Link, data: bytes) -> None:
        try:
            self._live(link)
        except BedNotConnectedError:
            return
        self.forward_raw_notification(app.NOTIFY, data)
        if link.recognized:
            if (indicator := codec.title_indicator(data)) is not None:
                link.indicator = indicator
        elif (
            data == codec.ADDRESS_REQUEST
            and link.response_task is None
            and link.adapter_address is not None
        ):
            address = link.adapter_address

            async def respond() -> None:
                try:
                    await self._frame(
                        link,
                        codec.adapter_response(address),
                        asyncio.Event(),
                        command=False,
                    )
                    self._live(link)
                    link.recognized = True
                finally:
                    link.response_task = None

            link.response_task = self._coordinator.hass.async_create_task(
                respond(), "AMINACH adapter response"
            )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 170,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and await self._pause(cancel, repeat_delay_ms / 1000):
                note_frame_skipped()
                return
            await self._frame(link, command, cancel)

    @staticmethod
    async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
        if seconds <= 0:
            return cancel.is_set()
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
        except TimeoutError:
            return False
        return True

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid(
                "held_control_not_supported",
                device_name=self._coordinator.name,
                control=control,
                valid_controls=", ".join(self.held_control_options),
            )
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 100 <= duration_ms <= 60000
        ):
            raise invalid("aminach_hold_duration")

    def on_gesture_release(self) -> None:
        context = self._gesture_context
        if context is not None and context.active and not context.cancel_event.is_set():
            # The release button admits one STOP. A later STOP still fences
            # the remainder of Memo's minimum gesture at the BLE lock.
            self._release_generation = context.cancel_generation + 1

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control == "memo":
            duration_ms = max(duration_ms, self.profile.memo_minimum_ms)
        duration_ms = self.leased_hold_ms(duration_ms)
        link, cancel = self._live(), self._coordinator.cancel_command
        context = self._gesture_context = current_command_context()
        self._release_generation = None
        loop = asyncio.get_running_loop()
        start = loop.time()
        end = start + duration_ms / 1000
        interval = self.profile.interval(control) / 1000
        remaining = ceil(duration_ms / self.profile.interval(control))
        next_tick = start
        armed = False

        def arm_gesture() -> None:
            nonlocal armed
            armed = True

        try:
            while remaining > 0 and not cancel.is_set() and loop.time() < end:
                remaining -= 1
                tick = loop.time()
                next_tick = tick + interval
                try:
                    await self._frame(
                        link,
                        self.profile.frame(control),
                        cancel,
                        deadline=end,
                        on_write=arm_gesture,
                    )
                except _Expired:
                    note_frame_skipped()
                    break
                if await self._pause(cancel, min(end, tick + interval) - loop.time()):
                    break
        finally:
            operation_error = sys.exception()
            release_generation, self._release_generation = self._release_generation, None
            self._gesture_context = None

            async def release() -> None:
                nonlocal next_tick
                minimum_end = start + self.profile.memo_minimum_ms / 1000
                try:
                    if (
                        control == "memo"
                        and context is not None
                        and release_generation is not None
                        and context.cancel_generation == release_generation
                        and armed
                    ):
                        followup_cancel = context.cancel_event_after(release_generation)
                        while loop.time() < minimum_end:
                            if await self._pause(
                                followup_cancel, min(next_tick, minimum_end) - loop.time()
                            ):
                                break
                            if loop.time() >= minimum_end:
                                break
                            next_tick = loop.time() + interval
                            try:
                                await self._frame(
                                    link,
                                    self.profile.frame(control),
                                    followup_cancel,
                                    deadline=minimum_end,
                                )
                            except _Expired:
                                note_frame_skipped()
                                break
                finally:
                    primary_error = sys.exception() or operation_error
                    if (
                        self._link is link
                        and self.client is link.client
                        and link.client.is_connected
                    ):
                        try:
                            await self._frame(link, self.profile.frame("release"), asyncio.Event())
                        except Exception:
                            if primary_error is None:
                                raise
                            _LOGGER.debug(
                                "Memo release failed after an earlier operation failure",
                                exc_info=True,
                            )

            await settled(release())

    async def press(self, action: str) -> None:
        await self.hold_control(
            action,
            max(100, self.profile.memo_minimum_ms if action == "memo" else self.profile.refresh_ms),
        )

    async def _move(self, action: str) -> None:
        await self.hold_control(
            action, max(100, self._coordinator.motor_pulse_count * self.profile.refresh_ms)
        )

    async def move_back_up(self) -> None:
        await self._move("back_up")

    async def move_back_down(self) -> None:
        await self._move("back_down")

    async def move_legs_up(self) -> None:
        await self._move("legs_up")

    async def move_legs_down(self) -> None:
        await self._move("legs_down")

    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            # The admitted hold already owns its common release.
            return
        await self.write_command(self.profile.frame("release"), cancel_event=asyncio.Event())

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        raise NotImplementedError

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        link = self._link
        return {
            "recognized": bool(link and link.recognized),
            "initiator_address_available": bool(link and link.adapter_address),
            "title_indicator": link.indicator if link else None,
        }


class _Expired(Exception):
    """A queued refresh outlived its hold."""
