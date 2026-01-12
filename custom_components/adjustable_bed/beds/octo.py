"""Octo bed controller implementation.

Octo beds use a packet-based BLE protocol with the following format:
[0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]

The checksum is calculated as: ((sum_of_bytes XOR 0xff) + 1) & 0xff
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import OCTO_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


# Motor bit masks
OCTO_MOTOR_HEAD = 0x02
OCTO_MOTOR_LEGS = 0x04


class OctoController(BedController):
    """Controller for Octo beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Octo controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("OctoController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OCTO_CHAR_UUID

    def _calculate_checksum(self, packet: list[int]) -> int:
        """Calculate the Octo checksum.

        The checksum is: ((sum_of_bytes XOR 0xff) + 1) & 0xff
        """
        total = sum(packet) & 0xFF
        return ((total ^ 0xFF) + 1) & 0xFF

    def _build_packet(self, command: list[int], data: list[int] | None = None) -> bytes:
        """Build an Octo command packet.

        Format: [0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]
        """
        data = data or []
        data_len = len(data)

        # Build packet without checksum first
        packet = [
            0x40,  # Start byte
            command[0],
            command[1],
            (data_len >> 8) & 0xFF,  # Length high byte
            data_len & 0xFF,  # Length low byte
            0x00,  # Placeholder for checksum
            *data,
            0x40,  # End byte
        ]

        # Calculate and insert checksum at position 5
        packet[5] = self._calculate_checksum(packet)

        return bytes(packet)

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
            "Writing command to Octo bed: %s (repeat: %d, delay: %dms)",
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
                    OCTO_CHAR_UUID, command, response=False
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def _write_octo_command(
        self,
        command: list[int],
        data: list[int] | None = None,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Build and write an Octo command packet."""
        packet = self._build_packet(command, data)
        await self.write_command(packet, repeat_count, repeat_delay_ms, cancel_event)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Octo beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    async def _move_motor(
        self, motor_bits: int, direction: str, cancel_event: asyncio.Event | None = None
    ) -> None:
        """Move a motor in the specified direction.

        Args:
            motor_bits: Bit mask for which motors to move (0x02=head, 0x04=legs)
            direction: "up" or "down"
            cancel_event: Optional event to cancel the command
        """
        # 0x70 = open (up), 0x71 = close (down)
        direction_byte = 0x70 if direction == "up" else 0x71
        await self._write_octo_command(
            command=[0x02, direction_byte],
            data=[motor_bits],
            repeat_count=25,
            repeat_delay_ms=200,
            cancel_event=cancel_event,
        )

    async def _stop_motors(self) -> None:
        """Send stop command to all motors."""
        await self._write_octo_command(
            command=[0x02, 0x73],
            cancel_event=asyncio.Event(),  # Don't cancel stop commands
        )

    async def _move_with_stop(self, motor_bits: int, direction: str) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self._move_motor(motor_bits, direction)
        finally:
            await self._stop_motors()

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head motor up."""
        await self._move_with_stop(OCTO_MOTOR_HEAD, "up")

    async def move_head_down(self) -> None:
        """Move head motor down."""
        await self._move_with_stop(OCTO_MOTOR_HEAD, "down")

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._stop_motors()

    async def move_back_up(self) -> None:
        """Move back up (same as head for Octo)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Octo)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up."""
        await self._move_with_stop(OCTO_MOTOR_LEGS, "up")

    async def move_legs_down(self) -> None:
        """Move legs motor down."""
        await self._move_with_stop(OCTO_MOTOR_LEGS, "down")

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._stop_motors()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Octo)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Octo)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._stop_motors()

    # Preset methods - Octo doesn't have built-in presets
    async def preset_flat(self) -> None:
        """Go to flat position.

        Octo doesn't have a flat preset, so we move both motors down.
        """
        # Move both head and legs down simultaneously
        await self._move_with_stop(OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS, "down")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Octo doesn't support memory presets.
        """
        _LOGGER.warning("Octo beds don't support memory presets")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Octo doesn't support memory presets.
        """
        _LOGGER.warning("Octo beds don't support memory presets")

    # Light control
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self._write_octo_command(
            command=[0x20, 0x72],
            data=[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x01],
        )

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self._write_octo_command(
            command=[0x20, 0x72],
            data=[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x00],
        )

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights.

        Octo tracks state internally, but we don't have access to it.
        This is a best-effort toggle that turns lights on.
        """
        await self.lights_on()
