"""Shared GATT roles and session-bound writes for the M Line wire routes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...codec import mline as codec
from ...command_scheduler import note_frame_skipped, note_frame_written, note_write_not_counted
from ..base import BedController
from ..cancellation import settled


@dataclass(frozen=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    firmware: BleakGATTCharacteristic | None
    protocol: BleakGATTCharacteristic | None


class MLineTransportController(BedController):
    _link: Link | None = None

    def _link_error(self, reason: Literal["disconnected", "roles"]) -> Exception:
        if reason == "roles":
            return ValueError(
                "M Line requires its writable no-response and notification GATT roles"
            )
        return ConnectionError("M Line BLE session changed or disconnected")

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else codec.NORDIC_WRITE

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise self._link_error("disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise self._link_error("disconnected")
        write = notify = firmware = protocol = None
        # Iterate actual GATT order, preserving independent later-role overwrite.
        for service in client.services:
            for char in service.characteristics:
                role = (service.uuid.lower(), char.uuid.lower())
                if role in (
                    (codec.NORDIC_SERVICE, codec.NORDIC_WRITE),
                    (codec.FFE_SERVICE, codec.FFE_WRITE),
                ):
                    write = char
                if role in (
                    (codec.NORDIC_SERVICE, codec.NORDIC_NOTIFY),
                    (codec.FFE_NOTIFY_SERVICE, codec.FFE_NOTIFY),
                ):
                    notify = char
                if role == (codec.INFO_SERVICE, codec.FIRMWARE):
                    firmware = char
                if role == (codec.INFO_SERVICE, codec.PROTOCOL_STRING):
                    protocol = char
        if (
            write is None
            or notify is None
            or "write-without-response" not in write.properties
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise self._link_error("roles")
        self._link = Link(client, write, notify, firmware, protocol)

    async def _write(
        self,
        link: Link,
        data: bytes,
        cancel: asyncio.Event,
        deadline: float | None = None,
        *,
        track: bool = True,
    ) -> None:
        async with self._ble_lock:
            self._live(link)
            if (
                cancel.is_set()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline - 1e-9
            ):
                if track:
                    note_frame_skipped()
                return
            self._record_command_trace(
                link.write.uuid, data, response=False, characteristic=link.write
            )
            await settled(link.client.write_gatt_char(link.write, data, response=False))
            if track:
                note_frame_written(cancel)
            else:
                note_write_not_counted()
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
            await self._write(link, bytes(command), cancel)

    @staticmethod
    async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
        try:
            async with asyncio.timeout(seconds):
                await cancel.wait()
            return True
        except TimeoutError:
            return False
