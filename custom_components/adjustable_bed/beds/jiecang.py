"""Jiecang bed controller implementation.

Jiecang beds (Glide beds, Dream Motion app) use simple hex command packets.
Commands are sent to characteristic UUID 0000ff01-0000-1000-8000-00805f9b34fb.

Note: This controller only supports preset positions - no motor movement commands
are available for Jiecang beds.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import JIECANG_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class JiecangCommands:
    """Jiecang command constants (pre-built byte arrays)."""

    MEMORY_1 = bytes.fromhex("f1f10b01010d7e")
    MEMORY_2 = bytes.fromhex("f1f10d01010f7e")
    FLAT = bytes.fromhex("f1f10801010a7e")
    ZERO_G = bytes.fromhex("f1f1070101097e")


class JiecangController(BedController):
    """Controller for Jiecang beds.

    Note: Jiecang beds only support preset positions, not direct motor control.
    Motor movement commands will log a warning and do nothing.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Jiecang controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("JiecangController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return JIECANG_CHAR_UUID

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
            "Writing command to Jiecang bed: %s (repeat: %d, delay: %dms)",
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
                    JIECANG_CHAR_UUID, command, response=False
                )
            except BleakError as err:
                _LOGGER.error("Failed to write command: %s", err)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Jiecang beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    def _warn_preset_only(self, action: str) -> None:
        """Log warning that Jiecang only supports presets."""
        _LOGGER.warning(
            "Jiecang beds only support preset positions. "
            "Cannot %s - use preset_flat, preset_zero_g, or preset_memory instead.",
            action,
        )

    # Motor control methods - not supported, use presets instead
    async def move_head_up(self) -> None:
        """Move head up (not supported)."""
        self._warn_preset_only("move head up")

    async def move_head_down(self) -> None:
        """Move head down (not supported)."""
        self._warn_preset_only("move head down")

    async def move_head_stop(self) -> None:
        """Stop head motor (not supported)."""
        pass

    async def move_back_up(self) -> None:
        """Move back up (not supported)."""
        self._warn_preset_only("move back up")

    async def move_back_down(self) -> None:
        """Move back down (not supported)."""
        self._warn_preset_only("move back down")

    async def move_back_stop(self) -> None:
        """Stop back motor (not supported)."""
        pass

    async def move_legs_up(self) -> None:
        """Move legs up (not supported)."""
        self._warn_preset_only("move legs up")

    async def move_legs_down(self) -> None:
        """Move legs down (not supported)."""
        self._warn_preset_only("move legs down")

    async def move_legs_stop(self) -> None:
        """Stop legs motor (not supported)."""
        pass

    async def move_feet_up(self) -> None:
        """Move feet up (not supported)."""
        self._warn_preset_only("move feet up")

    async def move_feet_down(self) -> None:
        """Move feet down (not supported)."""
        self._warn_preset_only("move feet down")

    async def move_feet_stop(self) -> None:
        """Stop feet motor (not supported)."""
        pass

    async def stop_all(self) -> None:
        """Stop all motors (not supported)."""
        pass

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            JiecangCommands.FLAT,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: JiecangCommands.MEMORY_1,
            2: JiecangCommands.MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(command, repeat_count=3, repeat_delay_ms=100)
        else:
            _LOGGER.warning("Jiecang beds only support memory presets 1 and 2")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("Jiecang beds don't support programming memory presets via BLE")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            JiecangCommands.ZERO_G,
            repeat_count=3,
            repeat_delay_ms=100,
        )
