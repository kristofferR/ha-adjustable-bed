"""Shared serial/PID family physical-session fences and settled cleanup."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ..codec import cheerssleep as codec
from .base import BedController


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class SynDataController(BedController):
    """One captured client and characteristic per operation, never a replacement link."""

    _link: Link | None = None
    write_response: bool = True
    settle_writes: bool = False

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or self._coordinator.controller is not self
            or (link is not None and current is not link)
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("Serial/PID physical session changed")
        return current

    async def _send(self, frame: bytes, link: Link, *, cleanup: bool = False) -> None:
        self._live(link)

        def verify() -> None:
            self._live(link)

        await self._write_gatt_with_retry(
            codec.WRITE,
            frame,
            1,
            0,
            asyncio.Event() if cleanup else self._coordinator.cancel_command,
            response=self.write_response,
            characteristic=link.write,
            expected_client=link.client,
            before_write=verify,
            settle_write=self.settle_writes,
            track_command_write=True,
        )

    async def _release(self, link: Link, frame: bytes, delay_ms: int = 0) -> None:
        async def release() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if (
                self._coordinator.controller is self
                and self._link is link
                and self.client is link.client
                and link.client.is_connected
            ):
                await self._send(frame, link, cleanup=True)

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError
