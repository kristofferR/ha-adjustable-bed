"""Solace bed controller implementation.

Solace beds use 11-byte command packets with pre-defined command arrays.
These are typically hospital/care beds.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import SOLACE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import SmartBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SolaceCommands:
    """Solace command constants (11-byte arrays)."""

    # Presets
    PRESET_TV = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x05, 0x17, 0x03])
    PRESET_ZERO_G = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x09, 0x17, 0x06])
    PRESET_ANTI_SNORE = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0F, 0x97, 0x04])
    PRESET_RISE = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x21, 0x17, 0x18])
    PRESET_TILT_FORWARD = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x28, 0xD7, 0x1E])
    PRESET_FLAT_BED = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x08, 0xD6, 0xC6])
    PRESET_DECLINE = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x22, 0x57, 0x19])
    PRESET_TILT_BACKWARD = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x29, 0x16, 0xDE])
    PRESET_ALL_FLAT = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x2A, 0x56, 0xDF])

    # Memory presets (byte 7 contains memory slot)
    PRESET_MEMORY_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xA1, 0x0A, 0x2E, 0x97])
    PRESET_MEMORY_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xB1, 0x0B, 0xE2, 0x97])
    PRESET_MEMORY_3 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x51, 0x05, 0x2A, 0x93])
    PRESET_MEMORY_4 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x91, 0x09, 0x7A, 0x96])
    PRESET_MEMORY_5 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xF1, 0x0F, 0xD2, 0x94])

    # Program memory
    PROGRAM_MEMORY_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xA0, 0x0A, 0x2F, 0x07])
    PROGRAM_MEMORY_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xB0, 0x0B, 0xE3, 0x07])
    PROGRAM_MEMORY_3 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x50, 0x05, 0x2B, 0x03])
    PROGRAM_MEMORY_4 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x90, 0x09, 0x7B, 0x06])
    PROGRAM_MEMORY_5 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xF0, 0x0F, 0xD3, 0x04])

    # Motor controls
    MOTOR_BACK_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x03, 0x97, 0x01])
    MOTOR_BACK_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x04, 0xD6, 0xC3])
    MOTOR_LEGS_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x06, 0x57, 0x02])
    MOTOR_LEGS_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x07, 0x96, 0xC2])
    MOTOR_LIFT_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x21, 0x17, 0x18])
    MOTOR_LIFT_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x22, 0x57, 0x19])
    MOTOR_TILT_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x28, 0xD7, 0x1E])
    MOTOR_TILT_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x29, 0x16, 0xDE])

    MOTOR_STOP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x00, 0xD7, 0x00])


class SolaceController(BedController):
    """Controller for Solace beds."""

    def __init__(self, coordinator: SmartBedCoordinator) -> None:
        """Initialize the Solace controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("SolaceController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return SOLACE_CHAR_UUID

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

        effective_cancel = cancel_event or self._coordinator._cancel_command

        _LOGGER.debug(
            "Writing command to Solace bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                await self.client.write_gatt_char(
                    SOLACE_CHAR_UUID, command, response=False
                )
            except BleakError as err:
                _LOGGER.error("Failed to write command: %s", err)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Solace beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    async def _move_with_stop(self, command: bytes) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self.write_command(command, repeat_count=30, repeat_delay_ms=50)
        finally:
            await self.write_command(
                SolaceCommands.MOTOR_STOP,
                cancel_event=asyncio.Event(),
            )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head/back up."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_UP)

    async def move_head_down(self) -> None:
        """Move head/back down."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            SolaceCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(SolaceCommands.MOTOR_LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(SolaceCommands.MOTOR_LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Solace)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Solace)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            SolaceCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            SolaceCommands.PRESET_ALL_FLAT,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: SolaceCommands.PRESET_MEMORY_1,
            2: SolaceCommands.PRESET_MEMORY_2,
            3: SolaceCommands.PRESET_MEMORY_3,
            4: SolaceCommands.PRESET_MEMORY_4,
            5: SolaceCommands.PRESET_MEMORY_5,
        }
        if command := commands.get(memory_num):
            await self.write_command(command, repeat_count=100, repeat_delay_ms=300)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: SolaceCommands.PROGRAM_MEMORY_1,
            2: SolaceCommands.PROGRAM_MEMORY_2,
            3: SolaceCommands.PROGRAM_MEMORY_3,
            4: SolaceCommands.PROGRAM_MEMORY_4,
            5: SolaceCommands.PROGRAM_MEMORY_5,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            SolaceCommands.PRESET_ZERO_G,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            SolaceCommands.PRESET_ANTI_SNORE,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(
            SolaceCommands.PRESET_TV,
            repeat_count=100,
            repeat_delay_ms=150,
        )
