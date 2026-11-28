"""Shared single-record Nordic UART sessions and held N-frame delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..codec import okin_nframe as codec
from ..command_scheduler import (
    command_frames_counted,
    current_command_context,
    note_frame_skipped,
    note_frame_written,
)
from ..const import NORDIC_UART_WRITE_CHAR_UUID
from ..errors import BedNotConnectedError
from .base import CONTROLLER_GESTURE_RELEASE
from .okin_nframe import OkinNFrameController
from .uart_roles import gatt_roles

if TYPE_CHECKING:
    from ..command_scheduler import CommandContext
    from ..coordinator import AdjustableBedCoordinator
    from .lifecycle import ControllerSession


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class _HoldEnded(Exception):
    """The hold deadline passed while waiting for the write lock."""


async def _wait(cancel: asyncio.Event, seconds: float) -> bool:
    """True if cancellation ended the delay."""
    if cancel.is_set():
        return True
    if seconds <= 0:
        return False
    try:
        async with asyncio.timeout(seconds):
            await cancel.wait()
    except TimeoutError:
        return False
    return True


class OkinUartController(OkinNFrameController):
    """Capture physical handles and keep releases on their originating link.

    Apps provide their own timing, STOP frame and notification interpretation.
    """

    settle_writes = False
    refresh_ms = 300
    release_ms = 100
    notify_retry_ms = 1000
    stop_frame = codec.frame40(0)
    gatt_error_key = "sleeptime_gatt"

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._write_with_response = False
        self._link: Link | None = None
        self._pending_stop: Link | None = None
        self._cleanup_stop: tuple[Link, CommandContext] | None = None
        self._parser: codec.SingleRecordParser | None = None
        self._subscribed = False

    async def async_validate_linked_readiness(self) -> None:
        self._live()

    def _receive(self, report: codec.MassageReport | codec.ShortAlarmReport | None) -> None:
        """Let the app profile interpret a complete record."""

    @property
    def control_characteristic_uuid(self) -> str:
        return NORDIC_UART_WRITE_CHAR_UUID

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
    def stop_on_active_sequential_link(self) -> bool:
        return True

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or (expected is not None and link is not expected)
            or self.client is not link.client
            or not link.client.is_connected
        ):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        roles = gatt_roles(client.services)
        if roles is None:
            raise BedNotConnectedError(self.gatt_error_key)
        self._link = Link(client, *roles)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed:
            return
        for attempt in range(2):
            parser = codec.SingleRecordParser()
            self._parser = parser

            def receive(
                _sender: BleakGATTCharacteristic,
                data: bytearray,
                parser: codec.SingleRecordParser = parser,
            ) -> None:
                if (
                    self._link is link
                    and self._parser is parser
                    and self.client is link.client
                    and link.client.is_connected
                ):
                    raw = bytes(data)
                    self.forward_raw_notification(link.notify.uuid, raw)
                    self._receive(parser.feed(raw))

            try:
                async with self._ble_lock:
                    self._live(link)
                    await link.client.start_notify(link.notify, receive)
                self._live(link)
            except BleakError, TimeoutError:
                if self._parser is parser:
                    self._parser = None
                if attempt:
                    raise
                await asyncio.sleep(self.notify_retry_ms / 1000)
            else:
                self._subscribed = True
                return

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self._parser = None
        self._subscribed = False
        if link is not None and subscribed and link.client.is_connected:
            async with self._ble_lock:
                if self._link is link and self.client is link.client and link.client.is_connected:
                    await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = self._pending_stop = None
        self._cleanup_stop = None
        self._parser = None
        self._subscribed = False
        super().on_disconnect()

    async def _write(
        self,
        link: Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        deadline: float | None = None,
        track: bool = True,
        before_send: Callable[[], None] | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        def validate() -> None:
            self._live(link)
            if deadline is not None and asyncio.get_running_loop().time() + 1e-9 >= deadline:
                raise _HoldEnded
            if before_send is not None:
                before_send()

        await self._write_gatt_with_retry(
            link.write.uuid,
            frame,
            cancel_event=cancel,
            response=False,
            characteristic=link.write,
            expected_client=link.client,
            before_write=validate,
            track_command_write=track,
            on_write=on_write,
            settle_write=self.settle_writes,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and await _wait(cancel, repeat_delay_ms / 1000):
                return
            await self._write(link, command, cancel)

    async def _stop_link(self, link: Link, *, track: bool) -> None:
        await asyncio.sleep(self.release_ms / 1000)
        await self._write(link, self.stop_frame, asyncio.Event(), track=track)
        if self._pending_stop is link:
            self._pending_stop = None

    async def _release(self, link: Link) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        try:
            await self._stop_link(link, track=False)
        except BedNotConnectedError:
            # The link can drop during the release delay.
            if self._link is link and self.client is link.client and link.client.is_connected:
                raise
            return
        if self._link is link and (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True
            self._cleanup_stop = (link, context)

    async def _send_stop(self) -> None:
        link, context = self._live(), current_command_context()
        if self._cleanup_stop is not None and context is not None:
            released_link, owner = self._cleanup_stop
            if (
                released_link is link
                and owner.cleanup_stop_sent
                and any(owner is previous for previous in context.preempted_contexts)
            ):
                owner.cleanup_stop_sent = False
                self._cleanup_stop = None
                note_frame_written(context.cancel_event)
                return
        if not CONTROLLER_GESTURE_RELEASE.get() or self._pending_stop is link:
            self._cleanup_stop = None
            with command_frames_counted():
                await self._stop_link(link, track=True)

    async def stop_all(self) -> None:
        await self._send_stop()

    async def _held(self, frame: bytes, duration_ms: int) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        # After a failed release, clear the same live receiver before moving again.
        if self._pending_stop is link and not cancel.is_set():
            await self._stop_link(link, track=False)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        attempted = False

        def mark_attempt() -> None:
            nonlocal attempted
            attempted = True
            self._pending_stop = link
            self._cleanup_stop = None

        async def release() -> None:
            if attempted:
                await self._release(link)

        async with self.releasing(release):
            while not cancel.is_set() and (started := loop.time()) + 1e-9 < deadline:
                try:
                    await self._write(
                        link, frame, cancel, deadline=deadline, before_send=mark_attempt
                    )
                except _HoldEnded:
                    note_frame_skipped()
                    return
                if await _wait(
                    cancel, min(deadline, started + self.refresh_ms / 1000) - loop.time()
                ):
                    return
