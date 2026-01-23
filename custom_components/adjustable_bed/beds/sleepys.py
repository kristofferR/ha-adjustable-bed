"""Sleepy's Elite bed controller implementations.

Reverse-engineered from MFRM Sleepy's Elite app v1.1.4 (com.okin.bedding.sleepy).

Sleepy's Elite beds use two distinct protocols:
- BOX15: 9-byte commands with checksum via FFE5 service (lumbar support)
- BOX24: 7-byte commands via OKIN 64-bit service (no lumbar)

The app auto-detects the protocol based on available BLE services.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import KEESON_BASE_WRITE_CHAR_UUID, SLEEPYS_BOX24_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SleepysBox15Commands:
    """BOX15 protocol command values.

    9-byte packets with checksum:
    [0xE6, 0xFE, 0x2C, motor_cmd, byte4, 0x00, byte6, 0x00, checksum]
    """

    HEADER = bytes([0xE6, 0xFE, 0x2C])

    # Motor commands (byte 3)
    STOP = 0x00
    HEAD_UP = 0x02
    HEAD_DOWN = 0x01
    FOOT_UP = 0x08
    FOOT_DOWN = 0x04
    LUMBAR_UP = 0x20
    LUMBAR_DOWN = 0x10

    # Presets (byte 4 + byte 6 combinations)
    FLAT_BYTE4 = 0x00
    FLAT_BYTE6 = 0x10
    ZERO_G_BYTE4 = 0x20
    ZERO_G_BYTE6 = 0x00


class SleepysBox24Commands:
    """BOX24 protocol command values.

    7-byte packets (no checksum):
    [0xA5, 0x5A, 0x00, 0x00, 0x00, 0x40, motor_cmd]
    """

    HEADER = bytes([0xA5, 0x5A, 0x00, 0x00, 0x00, 0x40])

    # Motor commands (byte 6)
    STOP = 0x00
    HEAD_UP = 0x02
    HEAD_DOWN = 0x01
    FOOT_UP = 0x06
    FOOT_DOWN = 0x05

    # Presets (byte 6)
    FLAT = 0xCC
    ZERO_G = 0xC0


def _calculate_box15_checksum(data: bytes) -> int:
    """Calculate BOX15 checksum (inverted 8-bit sum).

    Args:
        data: Bytes to checksum (should be 8 bytes)

    Returns:
        Checksum byte (one's complement of sum)
    """
    return (~sum(data)) & 0xFF


class SleepysBox15Controller(BedController):
    """Controller for Sleepy's Elite beds using BOX15 protocol.

    Protocol characteristics:
    - Service: 0000ffe5-0000-1000-8000-00805f9b34fb
    - Write characteristic: 0000ffe9-0000-1000-8000-00805f9b34fb
    - Command format: 9 bytes with checksum
      [0xE6, 0xFE, 0x2C, motor_cmd, byte4, 0x00, byte6, 0x00, checksum]
    - Checksum: (~sum(bytes[0:8])) & 0xFF
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Sleepy's BOX15 controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("SleepysBox15Controller initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return KEESON_BASE_WRITE_CHAR_UUID

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        """Return True - BOX15 protocol supports lumbar motor."""
        return True

    @property
    def supports_stop_all(self) -> bool:
        """Return True - BOX15 supports explicit stop command."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 0 - no memory presets available."""
        return 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - no memory presets."""
        return False

    def _build_motor_command(self, motor_cmd: int) -> bytes:
        """Build a 9-byte motor command packet.

        Args:
            motor_cmd: Motor command byte (e.g., HEAD_UP=0x02)

        Returns:
            9-byte command packet with checksum
        """
        data = bytearray(8)
        data[0:3] = SleepysBox15Commands.HEADER
        data[3] = motor_cmd
        # bytes 4-7 are zeros for motor commands
        checksum = _calculate_box15_checksum(bytes(data))
        return bytes(data) + bytes([checksum])

    def _build_preset_command(self, byte4: int, byte6: int) -> bytes:
        """Build a 9-byte preset command packet.

        Args:
            byte4: Preset data for byte position 4
            byte6: Preset data for byte position 6

        Returns:
            9-byte command packet with checksum
        """
        data = bytearray(8)
        data[0:3] = SleepysBox15Commands.HEADER
        data[3] = 0x00  # No motor command for presets
        data[4] = byte4
        # data[5] = 0x00
        data[6] = byte6
        # data[7] = 0x00
        checksum = _calculate_box15_checksum(bytes(data))
        return bytes(data) + bytes([checksum])

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Sleepy's BOX15 bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            KEESON_BASE_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Sleepy's BOX15 beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current motor positions - not supported."""

    async def _move_with_stop(self, motor_cmd: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        command = self._build_motor_command(motor_cmd)
        try:
            pulse_count = self._coordinator.motor_pulse_count
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            try:
                await self.write_command(
                    self._build_motor_command(SleepysBox15Commands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(SleepysBox15Commands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(SleepysBox15Commands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(
            self._build_motor_command(SleepysBox15Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(SleepysBox15Commands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(SleepysBox15Commands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(
            self._build_motor_command(SleepysBox15Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(SleepysBox15Commands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(SleepysBox15Commands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(
            self._build_motor_command(SleepysBox15Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(
            self._build_motor_command(SleepysBox15Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        command = self._build_preset_command(
            SleepysBox15Commands.FLAT_BYTE4,
            SleepysBox15Commands.FLAT_BYTE6,
        )
        try:
            await self.write_command(command)
        finally:
            try:
                await self.write_command(
                    self._build_motor_command(SleepysBox15Commands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during preset cleanup", exc_info=True)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        command = self._build_preset_command(
            SleepysBox15Commands.ZERO_G_BYTE4,
            SleepysBox15Commands.ZERO_G_BYTE6,
        )
        try:
            await self.write_command(command)
        finally:
            try:
                await self.write_command(
                    self._build_motor_command(SleepysBox15Commands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during preset cleanup", exc_info=True)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (not supported)."""
        _LOGGER.warning(
            "Sleepy's BOX15 beds don't support memory presets (requested: %d)", memory_num
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "Sleepy's BOX15 beds don't support programming memory presets (requested: %d)",
            memory_num,
        )


class SleepysBox24Controller(BedController):
    """Controller for Sleepy's Elite beds using BOX24 protocol.

    Protocol characteristics:
    - Service: 62741523-52f9-8864-b1ab-3b3a8d65950b (OKIN 64-bit)
    - Write characteristic: 62741625-52f9-8864-b1ab-3b3a8d65950b
    - Command format: 7 bytes (no checksum)
      [0xA5, 0x5A, 0x00, 0x00, 0x00, 0x40, motor_cmd]
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Sleepy's BOX24 controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("SleepysBox24Controller initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return SLEEPYS_BOX24_WRITE_CHAR_UUID

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        """Return False - BOX24 protocol does not support lumbar motor."""
        return False

    @property
    def supports_stop_all(self) -> bool:
        """Return True - BOX24 supports explicit stop command."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 0 - no memory presets available."""
        return 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - no memory presets."""
        return False

    def _build_command(self, motor_cmd: int) -> bytes:
        """Build a 7-byte BOX24 command packet.

        Args:
            motor_cmd: Motor/preset command byte

        Returns:
            7-byte command packet
        """
        return SleepysBox24Commands.HEADER + bytes([motor_cmd])

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Sleepy's BOX24 bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            SLEEPYS_BOX24_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,  # Fire-and-forget for BOX24
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Sleepy's BOX24 beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current motor positions - not supported."""

    async def _move_with_stop(self, motor_cmd: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        command = self._build_command(motor_cmd)
        try:
            pulse_count = self._coordinator.motor_pulse_count
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            try:
                await self.write_command(
                    self._build_command(SleepysBox24Commands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(SleepysBox24Commands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(SleepysBox24Commands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(
            self._build_command(SleepysBox24Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(SleepysBox24Commands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(SleepysBox24Commands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(
            self._build_command(SleepysBox24Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(
            self._build_command(SleepysBox24Commands.STOP),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        try:
            await self.write_command(self._build_command(SleepysBox24Commands.FLAT))
        finally:
            try:
                await self.write_command(
                    self._build_command(SleepysBox24Commands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during preset cleanup", exc_info=True)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        try:
            await self.write_command(self._build_command(SleepysBox24Commands.ZERO_G))
        finally:
            try:
                await self.write_command(
                    self._build_command(SleepysBox24Commands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP command during preset cleanup", exc_info=True)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (not supported)."""
        _LOGGER.warning(
            "Sleepy's BOX24 beds don't support memory presets (requested: %d)", memory_num
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning(
            "Sleepy's BOX24 beds don't support programming memory presets (requested: %d)",
            memory_num,
        )
