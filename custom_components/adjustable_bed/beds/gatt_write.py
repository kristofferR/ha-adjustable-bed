"""GATT writes with retry, pacing, cancellation and command tracing."""

from __future__ import annotations

import asyncio
import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.exc import BleakError

from ..diagnostic_payloads import format_payload

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class GattWriter(ABC):
    """Write commands to the live client under the controller's BLE lock."""

    _coordinator: AdjustableBedCoordinator
    _ble_lock: asyncio.Lock

    @property
    @abstractmethod
    def client(self) -> BleakClient | None:
        """Return the BLE client."""

    def _format_command_trace_payload(self, command: bytes) -> dict[str, Any] | None:
        """Return a safe diagnostic representation of a command."""
        return format_payload(command)

    def _record_command_trace(
        self,
        char_uuid: str,
        command: bytes,
        *,
        response: bool,
        repeat_count: int = 1,
        repeat_delay_ms: int = 0,
        command_origin: str | None = None,
        characteristic: BleakGATTCharacteristic | None = None,
    ) -> None:
        """Record a write for support bundles.

        ``_write_gatt_with_retry`` calls this itself. A controller with its own
        write loop calls it once per run of identical writes; the origin then
        defaults to the function that called that write method.
        """
        payload = self._format_command_trace_payload(command)
        if payload is None:
            return
        if command_origin is None:
            frame = inspect.currentframe()
            caller = frame.f_back.f_back if frame and frame.f_back else None
            command_origin = caller.f_code.co_name if caller else None
        handle: int | None = getattr(characteristic, "handle", None)
        client = self.client
        if characteristic is None and client is not None and client.services:
            for service in client.services:
                for discovered in service.characteristics:
                    if discovered.uuid == char_uuid:
                        handle = getattr(discovered, "handle", None)
                        break
                if handle is not None:
                    break
        self._coordinator.record_command_trace(
            payload=payload,
            characteristic_uuid=char_uuid,
            characteristic_handle=handle,
            response=response,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            command_origin=command_origin,
            controller_class=type(self).__name__,
        )

    async def _write_gatt_with_retry(
        self,
        char_uuid: str,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        response: bool = True,
        log_errors: bool = True,
        wall_clock_pacing: bool = False,
        on_write: Callable[[], None] | None = None,
        characteristic: BleakGATTCharacteristic | None = None,
        expected_client: BleakClient | None = None,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        """Write a command to a GATT characteristic with retry support.

        This is a helper method that handles the common pattern of:
        - Checking connection state
        - Writing to a characteristic with optional response
        - Repeating the command with delays
        - Checking for cancellation between writes

        Args:
            char_uuid: The characteristic UUID to write to
            command: The command bytes to send
            repeat_count: Number of times to repeat the command (default: 1)
            repeat_delay_ms: Delay between repeats in milliseconds (default: 100)
            cancel_event: Optional event that signals cancellation. If set,
                         the command loop will exit early.
            response: Whether to wait for a write response from the device.
                     True = write-with-response (more reliable, slower) [default]
                     False = write-without-response (faster, less reliable)
            log_errors: Whether to log BleakError failures at ERROR level.
                     Set to False for callers that recover from expected errors
                     (e.g. Linak's post-connect auth-window probes).
            wall_clock_pacing: Measure the repeat interval from the start of each
                     write, so BLE round-trip time is absorbed into the interval
                     instead of added to it.
            on_write: Called synchronously after each successful GATT write,
                     before any repeat delay or cancellation can interrupt it.
            characteristic: Exact discovered destination when duplicate UUIDs
                     require a particular characteristic instance.
            expected_client: Optional connection identity checked after acquiring
                     the BLE lock, so queued writes cannot migrate on reconnect.
            before_write: Synchronous validation immediately before transmission,
                     under the BLE lock, after all connection and cancellation checks.

        Raises:
            ConnectionError: If not connected to the bed
            BleakError: If the GATT write fails
        """
        client = self.client
        if client is None or not client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command
        payload = self._format_command_trace_payload(command)
        logged_command = str(payload.get("hex", "**REDACTED**")) if payload else "**REDACTED**"

        _LOGGER.debug(
            "GATT write to %s (%s): %s (response=%s, repeat=%d, delay=%dms, wall_clock_pacing=%s)",
            self._coordinator.address,
            char_uuid,
            logged_command,
            response,
            repeat_count,
            repeat_delay_ms,
            wall_clock_pacing,
        )

        caller_frame = inspect.currentframe()
        command_origin = None
        if caller_frame is not None and caller_frame.f_back is not None:
            command_origin = caller_frame.f_back.f_code.co_name

        self._record_command_trace(
            char_uuid,
            command,
            response=response,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            command_origin=command_origin,
            characteristic=characteristic,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.debug("Command cancelled after %d/%d writes", i, repeat_count)
                return

            write_started: float | None = None
            try:
                # Acquire BLE lock for each individual write to prevent conflicts
                # with concurrent position reads during movement
                async with self._ble_lock:
                    # A read may have held this lane while STOP invalidated the
                    # movement. Do not send a stale write or acknowledge a no-op.
                    if effective_cancel is not None and effective_cancel.is_set():
                        return
                    client = self.client
                    if expected_client is not None and client is not expected_client:
                        raise ConnectionError("Command belongs to a previous BLE connection")
                    if client is None or not client.is_connected:
                        _LOGGER.error("Cannot write command: BLE client disconnected during write")
                        raise ConnectionError("Not connected to bed")
                    if wall_clock_pacing:
                        write_started = asyncio.get_running_loop().time()
                    if before_write is not None:
                        before_write()
                    await client.write_gatt_char(
                        characteristic if characteristic is not None else char_uuid,
                        command,
                        response=response,
                    )
                    if on_write is not None:
                        on_write()
            except BleakError:
                if log_errors:
                    _LOGGER.exception(
                        "Failed to write command %s to %s",
                        logged_command,
                        char_uuid,
                    )
                else:
                    _LOGGER.debug(
                        "Suppressed write failure for %s to %s",
                        logged_command,
                        char_uuid,
                        exc_info=True,
                    )
                raise

            if i < repeat_count - 1:
                delay_seconds = repeat_delay_ms / 1000
                if write_started is not None:
                    delay_seconds -= asyncio.get_running_loop().time() - write_started
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
