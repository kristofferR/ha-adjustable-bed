"""AVEK's fixed firmness panel and connection-owned identity exchange."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from functools import partial
from typing import TYPE_CHECKING
from uuid import uuid4

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..card import CARD_HIDDEN
from ..codec import avek as codec
from ..command_scheduler import note_frame_skipped
from ..errors import BedNotConnectedError, invalid
from ..profiles.avek import AVEK
from .base import BedController, ProfileExecution, require_controller
from .cancellation import cancellable
from .catalog_buttons import Kind, catalog_button, unique_buttons
from .entity_specs import ControllerButtonSpec, ControllerHoldSpec, MotorControlSpec
from .lifecycle import ControllerSession

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    identity_changed: asyncio.Event = field(default_factory=asyncio.Event)


class _Ended(Exception):
    """The admitted refresh expired before reaching the wire."""


async def _press(key: str, controller: BedController) -> None:
    await require_controller(controller, AvekController).press(key)


class AvekController(ProfileExecution, BedController):
    """Ending refresh is the only proven release, including explicit STOP."""

    profile = AVEK

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._link: _Link | None = None
        self._notifying = False
        self._recognized = False
        self._counts: list[int | None] = [None, None, None]
        self._app_id = uuid4().bytes[-6:]
        self._epoch = 0
        self._identity_tasks: set[asyncio.Task[None]] = set()

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE_UUID

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def memory_slot_count(self) -> int:
        # SAVE is a standalone command, with no proven slot programming sequence.
        return 0

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def persisted_app_state(self) -> dict[str, str]:
        return {"app_id": self._app_id.hex()}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        value = state.get("app_id")
        if isinstance(value, str):
            try:
                app_id = bytes.fromhex(value)
            except ValueError:
                return
            if len(app_id) == 6:
                self._app_id = app_id

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "identity_reply_sent": self._recognized,
            "raw_counts": list(self._counts),
            "app_display_levels": [
                codec.display_level(count) if count is not None else None
                for count in self._counts[:2]
            ],
        }

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object] | None:
        if command[:3] == b"\xb1\x07\x00":
            return {"redacted": True, "length": len(command)}
        return super()._format_command_trace_payload(command)

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
        ):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is not None and client.is_connected:
            for service in client.services:
                if service.uuid.lower() != codec.SERVICE_UUID:
                    continue
                write = service.get_characteristic(codec.WRITE_UUID)
                notify = service.get_characteristic(codec.NOTIFY_UUID)
                if (
                    write is not None
                    and notify is not None
                    and {"write", "write-without-response"}.intersection(write.properties)
                    and "notify" in notify.properties
                ):
                    # Android's default prefers NO_RESPONSE when advertised.
                    self._link = _Link(
                        client, write, notify, "write-without-response" not in write.properties
                    )
                    return
        raise BedNotConnectedError()

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return
        link = replace(link, identity_changed=asyncio.Event())
        self._link = link
        await link.client.start_notify(
            link.notify, lambda _sender, data: self._notification(link, bytes(data))
        )
        self._live(link)
        self._notifying = True

    def _notification(self, link: _Link, data: bytes) -> None:
        try:
            self._live(link)
        except BedNotConnectedError:
            return
        if self._raw_notify_callback is not None:
            self._raw_notify_callback(codec.NOTIFY_UUID, data)
        if data == codec.IDENTITY_REQUEST:
            task = self._coordinator.hass.async_create_task(self._reply_identity(link))
            self._identity_tasks.add(task)
            task.add_done_callback(self._identity_tasks.discard)
        elif (count := codec.parse_count(data)) is not None:
            self._counts[count.index] = count.value

    async def _reply_identity(self, link: _Link) -> None:
        try:
            await self._frame(link, codec.identity(self._app_id), asyncio.Event(), startup=True)
            self._live(link)
        except ConnectionError, TimeoutError, BleakError:
            if self._link is link:
                self._recognized = False
            return
        self._recognized = True
        link.identity_changed.set()

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        # Diagnostic capture can resume notifications on this same connection.
        self._notifying = False
        self.on_gesture_release()
        self._recognized = False
        self._counts = [None, None, None]
        for task in self._identity_tasks:
            task.cancel()
        self._identity_tasks.clear()
        if link is not None:
            self._link = replace(link, identity_changed=asyncio.Event())
        if link is not None and notifying and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self.on_gesture_release()
        self._link = None
        self._notifying = self._recognized = False
        self._counts = [None, None, None]
        for task in self._identity_tasks:
            task.cancel()
        self._identity_tasks.clear()

    def on_app_state_replaced(self) -> None:
        self.on_disconnect()

    def on_gesture_release(self) -> None:
        self._epoch += 1
        if self._link is not None:
            self._link.identity_changed.set()

    def on_connection_release(self, reason: str) -> None:
        self.on_gesture_release()

    async def _frame(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        epoch: int | None = None,
        deadline: float | None = None,
        startup: bool = False,
    ) -> float | None:
        dispatched_at: float | None = None

        def check() -> None:
            nonlocal dispatched_at
            self._live(link)
            if (
                epoch is not None
                and epoch != self._epoch
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
            ):
                note_frame_skipped()
                raise _Ended
            dispatched_at = asyncio.get_running_loop().time()

        await self._write_gatt_with_retry(
            codec.WRITE_UUID,
            frame,
            cancel_event=cancel,
            response=link.response,
            characteristic=link.write,
            expected_client=link.client,
            before_write=check,
            settle_write=True,
            write_timeout=10,
            track_command_write=not startup,
        )
        return dispatched_at

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 90,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link, epoch = self._live(), self._epoch
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for tick in range(repeat_count):
            if cancel.is_set() or tick and await self._pause(cancel, repeat_delay_ms / 1000):
                return
            try:
                await self._frame(link, command, cancel, epoch=epoch)
            except _Ended:
                return

    @staticmethod
    async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), max(0, seconds))
        except TimeoutError:
            return cancel.is_set()
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(a.key for a in AVEK.actions if a.key in (AVEK.execution.hold_controls or ()))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid(
                "held_control_not_supported",
                device_name=self._coordinator.name,
                control=control,
                valid_controls=", ".join(self.held_control_options),
            )
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise invalid("avek_hold_duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._refresh(control, self.leased_hold_ms(duration_ms))

    async def press(self, key: str) -> None:
        if key == "initial":
            if await self._wait_identity():
                await self._refresh(key, AVEK.initial_limit_ms, initial=True)
        else:
            # A tap is a bounded press, without inventing a fixed app repeat count.
            await self._refresh(key, self._coordinator.motor_pulse_count * AVEK.refresh_ms)

    async def _wait_identity(self) -> bool:
        link, epoch, cancel = self._live(), self._epoch, self._coordinator.cancel_command
        try:
            async with asyncio.timeout(AVEK.identity_timeout_s):
                while True:
                    self._live(link)
                    if cancel.is_set() or epoch != self._epoch:
                        return False
                    if self._recognized:
                        return True
                    link.identity_changed.clear()
                    await cancellable(link.identity_changed.wait(), cancel)
        except TimeoutError:
            raise BedNotConnectedError("avek_identity_required") from None

    async def _refresh(self, key: str, duration_ms: int, *, initial: bool = False) -> None:
        action = AVEK.action(key)
        link, epoch, cancel = self._live(), self._epoch, self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start = loop.time()
        end = start + duration_ms / 1000
        interval = AVEK.refresh_ms / 1000
        tick = 0
        try:
            while loop.time() < end and not cancel.is_set():
                if epoch != self._epoch:
                    return
                if initial and tick and self._counts[:2] == [AVEK.initial_endpoint] * 2:
                    return
                sent_at = await self._frame(link, action.frame, cancel, epoch=epoch, deadline=end)
                if sent_at is None:
                    return
                tick += 1
                if await self._pause(cancel, min(end, sent_at + interval) - loop.time()):
                    return
        except _Ended:
            return
        finally:
            # This scope owns refresh. All exits end it; there is no wire release.
            if self._epoch == epoch:
                self._epoch += 1

    async def stop_all(self) -> None:
        self.on_gesture_release()

    async def _unsupported(self, memory_num: int = 0) -> None:
        raise NotImplementedError("AVEK has no articulation or slot-programming route")

    move_head_up = move_head_down = move_back_up = move_back_down = _unsupported
    move_legs_up = move_legs_down = move_feet_up = move_feet_down = _unsupported
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all
    preset_flat = preset_memory = program_memory = _unsupported

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *unique_buttons(
                catalog_button(
                    action.key,
                    action.label,
                    partial(_press, action.key),
                    kind=Kind.PRESET
                    if action.key in {"a", "b", "c", "d"}
                    else Kind.MOTOR
                    if action.key in self.held_control_options
                    else Kind.EXTRA,
                    hold=ControllerHoldSpec(action.key, release_button_key="avek_release")
                    if action.key in self.held_control_options
                    else None,
                    requires_confirmation=action.key == "save",
                )
                for action in AVEK.actions
            ),
            ControllerButtonSpec(
                "avek_release",
                "Release",
                lambda c: c.stop_all(),
                release_only=True,
                translation_key="avek_release",
                card=CARD_HIDDEN,
            ),
        )
