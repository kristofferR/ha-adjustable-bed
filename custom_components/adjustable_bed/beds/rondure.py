"""Rondure / 1500 Tilt Base bed controller implementation.

Reverse engineered from com.sfd.rondure_hump APK (1500 Tilt Base Remote 1.1.3).

These beds use the FurniBus protocol with 8-byte (both sides) or 9-byte
(single side) command packets. The protocol supports split-king beds with
independent control of each side.

Packet format:
- Both sides (8 bytes): [0xE5, 0xFE, 0x16, cmd[0], cmd[1], cmd[2], cmd[3], checksum]
- Single side (9 bytes): [0xE6, 0xFE, 0x16, cmd[0], cmd[1], cmd[2], cmd[3], side, checksum]

Command bytes are 32-bit values in little-endian order.
Checksum is bitwise NOT of sum of all preceding bytes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import (
    RONDURE_VARIANT_BOTH,
    RONDURE_VARIANT_SIDE_A,
    RONDURE_VARIANT_SIDE_B,
    RONDURE_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class RondureCommands:
    """Rondure command constants (32-bit values)."""

    # Motor control (hold to move)
    HEAD_UP = 0x00000001
    HEAD_DOWN = 0x00000002
    FOOT_UP = 0x00000004
    FOOT_DOWN = 0x00000008
    TILT_UP = 0x00000010
    TILT_DOWN = 0x00000020
    LUMBAR_UP = 0x00000040
    LUMBAR_DOWN = 0x00000080

    # Presets (single press)
    TIMER_LEVEL = 0x00000100  # Timer/Level toggle
    ZERO_G = 0x00001000
    READ_PRESET = 0x00002000  # Reading position preset
    MUSIC_MEMORY = 0x00004000  # Music/Memory preset
    TV_ANTI_SNORE = 0x00008000  # TV or Anti-snore preset
    FLAT = 0x08000000

    # Massage control
    MASSAGE_FOOT = 0x00000400
    MASSAGE_HEAD = 0x00000800
    MASSAGE_LUMBAR = 0x00400000
    MASSAGE_MODE_1 = 0x00100000
    MASSAGE_MODE_2 = 0x00200000
    MASSAGE_MODE_3 = 0x00080000

    # Light
    LIGHT = 0x00020000

    # Stop
    STOP = 0x00000000


class RondureController(BedController):
    """Controller for Rondure / 1500 Tilt Base beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = RONDURE_VARIANT_BOTH,
    ) -> None:
        """Initialize the Rondure controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance.
            variant: Side selection - "both", "side_a", or "side_b".
        """
        super().__init__(coordinator)
        self._variant = variant
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("RondureController initialized with variant: %s", variant)

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return RONDURE_WRITE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_light(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        """Return True - Rondure beds support lumbar control."""
        return True

    @property
    def has_tilt_support(self) -> bool:
        """Return True - Rondure beds support tilt control."""
        return True

    def _calculate_checksum(self, data: bytes) -> int:
        """Calculate checksum (bitwise NOT of sum of all bytes)."""
        return (~sum(data)) & 0xFF

    def _build_packet(self, command: int) -> bytes:
        """Build a command packet for the bed.

        Args:
            command: 32-bit command value.

        Returns:
            8-byte packet for "both" mode, 9-byte for single side mode.
        """
        # Split command into little-endian bytes
        cmd_bytes = [
            command & 0xFF,
            (command >> 8) & 0xFF,
            (command >> 16) & 0xFF,
            (command >> 24) & 0xFF,
        ]

        if self._variant == RONDURE_VARIANT_BOTH:
            # 8-byte packet: [0xE5, 0xFE, 0x16, cmd[0-3], checksum]
            packet = bytes([0xE5, 0xFE, 0x16] + cmd_bytes)
            checksum = self._calculate_checksum(packet)
            return packet + bytes([checksum])
        else:
            # 9-byte packet: [0xE6, 0xFE, 0x16, cmd[0-3], side, checksum]
            side = 0x01 if self._variant == RONDURE_VARIANT_SIDE_A else 0x02
            packet = bytes([0xE6, 0xFE, 0x16] + cmd_bytes + [side])
            checksum = self._calculate_checksum(packet)
            return packet + bytes([checksum])

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
            "Writing command to Rondure bed (%s): %s (repeat: %d, delay: %dms)",
            RONDURE_WRITE_CHAR_UUID,
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
                    RONDURE_WRITE_CHAR_UUID, command, response=False
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Rondure position notifications not yet implemented")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""

    async def _send_command(self, command: int, repeat_count: int = 1) -> None:
        """Build and send a command packet."""
        packet = self._build_packet(command)
        await self.write_command(packet, repeat_count=repeat_count)

    async def _move_with_stop(self, command: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            packet = self._build_packet(command)
            await self.write_command(packet, repeat_count=25, repeat_delay_ms=50)
        finally:
            try:
                stop_packet = self._build_packet(RondureCommands.STOP)
                await self.write_command(
                    stop_packet,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(RondureCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(RondureCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._send_command(RondureCommands.STOP)

    async def move_back_up(self) -> None:
        """Move back up (alias for head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (alias for head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs/feet up."""
        await self._move_with_stop(RondureCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs/feet down."""
        await self._move_with_stop(RondureCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._send_command(RondureCommands.STOP)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._send_command(RondureCommands.STOP)

    # Tilt control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_with_stop(RondureCommands.TILT_UP)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_with_stop(RondureCommands.TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        await self._send_command(RondureCommands.STOP)

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(RondureCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(RondureCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._send_command(RondureCommands.STOP)

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_command(RondureCommands.FLAT)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._send_command(RondureCommands.ZERO_G)

    async def preset_tv(self) -> None:
        """Go to TV/anti-snore position."""
        await self._send_command(RondureCommands.TV_ANTI_SNORE)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (same as TV on this bed)."""
        await self.preset_tv()

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (not supported on Rondure beds)."""
        _LOGGER.warning(
            "Memory presets are not supported on Rondure beds (requested: M%d)",
            memory_num,
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on Rondure beds)."""
        _LOGGER.warning(
            "Memory programming is not supported on Rondure beds (requested: M%d)",
            memory_num,
        )

    # Massage methods
    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self._send_command(RondureCommands.MASSAGE_HEAD)

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self._send_command(RondureCommands.MASSAGE_FOOT)

    async def massage_lumbar_toggle(self) -> None:
        """Toggle lumbar massage."""
        await self._send_command(RondureCommands.MASSAGE_LUMBAR)

    async def massage_toggle(self) -> None:
        """Toggle massage (mode 1)."""
        await self._send_command(RondureCommands.MASSAGE_MODE_1)

    async def massage_mode_2(self) -> None:
        """Set massage mode 2."""
        await self._send_command(RondureCommands.MASSAGE_MODE_2)

    async def massage_mode_3(self) -> None:
        """Set massage mode 3."""
        await self._send_command(RondureCommands.MASSAGE_MODE_3)

    # Light control
    async def lights_toggle(self) -> None:
        """Toggle under-bed light."""
        await self._send_command(RondureCommands.LIGHT)

    async def lights_on(self) -> None:
        """Turn on under-bed light (toggle, no discrete on)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off under-bed light (toggle, no discrete off)."""
        await self.lights_toggle()
