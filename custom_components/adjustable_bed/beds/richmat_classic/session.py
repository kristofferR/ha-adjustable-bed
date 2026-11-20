"""Captured Richmat sessions and cancellation-drained writes and cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...command_scheduler import note_frame_skipped, note_frame_written
from ..base import BedController
from ..cancellation import settled
from .controller import RichmatClassicController
from .protocol import release
from .transport import Transport

_SCOPE: ContextVar[tuple[BedController, Transport] | None] = ContextVar(
    "richmat_catalog_session", default=None
)


class SessionController(RichmatClassicController):
    """An admitted command never borrows a replacement connection."""

    @contextmanager
    def _transaction(self):
        session = self._session
        if session is None:
            raise ConnectionError("The bed has no current BLE session")
        token = _SCOPE.set((self, session))
        try:
            yield session
        finally:
            _SCOPE.reset(token)

    def _captured_session(self) -> Transport | None:
        scope = _SCOPE.get()
        return scope[1] if scope is not None and scope[0] is self else self._session

    async def _send(self, packet: bytes, cancel: asyncio.Event | None = None) -> None:
        await self._send_at(packet, cancel=cancel)

    async def _send_at(
        self,
        packet: bytes,
        *,
        characteristic: BleakGATTCharacteristic | None = None,
        cancel: asyncio.Event | None = None,
        before_write: Callable[[], bool] | None = None,
    ) -> None:
        session = self._captured_session()
        if (
            session is None
            or self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            raise ConnectionError("The captured bed session has ended")
        destination = characteristic if characteristic is not None else session.write
        response = "write" in destination.properties

        async def write() -> None:
            if (
                self._session is not session
                or self.client is not session.client
                or not session.client.is_connected
            ):
                raise ConnectionError("The captured bed session has ended")
            if cancel is not None and cancel.is_set():
                note_frame_skipped()
                return
            if before_write is not None and not before_write():
                note_frame_skipped()
                return
            self._record_command_trace(
                destination.uuid, packet, response=response, characteristic=destination
            )
            await session.client.write_gatt_char(destination, packet, response=response)
            note_frame_written(cancel)

        await settled(write())

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        session = self._captured_session()
        if session is None or self._session is not session or not session.client.is_connected:
            return

        async def cleanup() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            # Cleanup is owned by the admitted session, never a reconnect.
            if self._session is session:
                await self._send(release(session.wire, 0 if mode is None else mode))

        await settled(cleanup())
