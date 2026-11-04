"""Shared glue for Okin N-frame controllers that write one frame per pulse."""

from __future__ import annotations

import asyncio
import logging

from bleak.exc import BleakError

from ..codec import okin_nframe as codec
from ..profiles.okin_nframe import Tap
from .base import BedController

_LOGGER = logging.getLogger(__name__)


class OkinNFrameController(BedController):
    """Write loop and STOP handling for the Okimat and DewertOkin routes.

    Each pulse is one locked GATT write to the Okin write characteristic,
    followed by the repeat delay. A set cancel event ends the loop before the
    next write.
    """

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the Okin write characteristic UUID."""
        return codec.WRITE_UUID

    def _build_command(self, command_value: int) -> bytes:
        """Frame one command word through the codec."""
        return codec.frame(command_value)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command
        _LOGGER.debug(
            "Writing Okin command to %s: %s (repeat: %d, delay: %dms, response=%s)",
            self.control_characteristic_uuid,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
            self._write_with_response,
        )
        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return
            try:
                # The lock keeps writes and position reads from interleaving.
                async with self._ble_lock:
                    await self.client.write_gatt_char(
                        self.control_characteristic_uuid,
                        command,
                        response=self._write_with_response,
                    )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise
            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def _send_stop(self) -> None:
        """Send STOP with a fresh cancel event so a stop request cannot suppress it."""
        await self.write_command(self._build_command(0), cancel_event=asyncio.Event())

    async def _tap_then_stop(self, command_value: int, tap: Tap, context: str) -> None:
        """Send a fixed burst, then its STOP even if the burst is cancelled or fails."""
        try:
            await self.write_command(
                self._build_command(command_value),
                repeat_count=tap.repeats,
                repeat_delay_ms=tap.repeat_ms,
            )
        finally:
            if tap.releases:
                try:
                    await self._send_stop()
                except TimeoutError, BleakError:
                    _LOGGER.debug("Failed to send STOP after %s", context, exc_info=True)
