"""Serta Motion Perfect III bed controller implementation.

Serta beds use handle-based writes with a specific command format.
Commands are 8 bytes written to handle 0x0020.
All commands have the prefix e5fe16.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import SERTA_WRITE_HANDLE
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SertaCommands:
    """Serta Motion Perfect III command constants (8-byte arrays)."""

    # Presets
    FLAT = bytes.fromhex("e5fe1600000008fe")
    ZERO_G = bytes.fromhex("e5fe1600100000f6")
    TV = bytes.fromhex("e5fe1600400000c6")
    HEAD_UP_PRESET = bytes.fromhex("e5fe160080000086")
    LOUNGE = bytes.fromhex("e5fe1600200000e6")

    # Motor controls
    HEAD_UP = bytes.fromhex("e5fe160100000005")
    HEAD_DOWN = bytes.fromhex("e5fe160200000004")
    FOOT_UP = bytes.fromhex("e5fe160400000002")
    FOOT_DOWN = bytes.fromhex("e5fe1608000000fe")

    # Massage
    MASSAGE_HEAD_ADD = bytes.fromhex("e5fe1600080000fe")
    MASSAGE_HEAD_MIN = bytes.fromhex("e5fe160000800086")
    MASSAGE_FOOT_ADD = bytes.fromhex("e5fe160004000002")
    MASSAGE_FOOT_MIN = bytes.fromhex("e5fe160000000105")
    MASSAGE_HEAD_FOOT_ON = bytes.fromhex("e5fe160001000005")
    MASSAGE_TIMER = bytes.fromhex("e5fe160002000004")

    # Stop (zero command)
    STOP = bytes.fromhex("e5fe160000000006")


class SertaController(BedController):
    """Controller for Serta Motion Perfect III beds.

    Serta beds use handle-based writes to handle 0x0020.
    They support motor control, presets, and massage.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Serta controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("SertaController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return placeholder - this controller uses handle-based writes."""
        return f"handle-0x{SERTA_WRITE_HANDLE:04x}"

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed using handle 0x0020."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing command to Serta bed (handle 0x%04x): %s (repeat: %d, delay: %dms)",
            SERTA_WRITE_HANDLE,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                # Write to handle directly (Bleak supports integer handles)
                await self.client.write_gatt_char(
                    SERTA_WRITE_HANDLE, command, response=False
                )
            except BleakError as err:
                _LOGGER.error("Failed to write command: %s", err)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Serta beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    async def _move_with_stop(self, command: bytes) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            pulse_count = self._coordinator._motor_pulse_count
            pulse_delay = self._coordinator._motor_pulse_delay_ms
            await self.write_command(
                command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay
            )
        finally:
            await self.write_command(
                SertaCommands.STOP,
                cancel_event=asyncio.Event(),
            )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(SertaCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(SertaCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            SertaCommands.STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self._move_with_stop(SertaCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self._move_with_stop(SertaCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(SertaCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(SertaCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            SertaCommands.STOP,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            SertaCommands.FLAT,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (not supported)."""
        _LOGGER.warning("Serta beds don't support memory presets")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("Serta beds don't support programming memory presets via BLE")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            SertaCommands.ZERO_G,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(
            SertaCommands.TV,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_anti_snore(self) -> None:
        """Go to lounge/anti-snore position."""
        await self.write_command(
            SertaCommands.LOUNGE,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle head and foot massage on."""
        await self.write_command(SertaCommands.MASSAGE_HEAD_FOOT_ON)

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(SertaCommands.MASSAGE_HEAD_ADD)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(SertaCommands.MASSAGE_HEAD_MIN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(SertaCommands.MASSAGE_FOOT_ADD)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(SertaCommands.MASSAGE_FOOT_MIN)

    async def massage_mode_step(self) -> None:
        """Step through massage timer."""
        await self.write_command(SertaCommands.MASSAGE_TIMER)
