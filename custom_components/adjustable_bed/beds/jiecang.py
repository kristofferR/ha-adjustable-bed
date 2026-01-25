"""Jiecang bed controller implementation.

Reverse engineering by Richard Hopton (smartbed-mqtt).
Extended with full Comfort Motion protocol from BluetoothLeService.java and MainActivity.java.

Jiecang beds (Glide beds, Dream Motion app) use hex command packets.
Commands are sent to characteristic UUID 0000ff01-0000-1000-8000-00805f9b34fb.

Command format: F1F1 + data bytes + checksum + 7E
Checksum = SUM of data bytes
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import JIECANG_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class JiecangCommands:
    """Jiecang command constants (pre-built byte arrays).

    Verified from MainActivity.java - Command format: F1F1 + data + checksum + 7E
    """

    # Motor control
    HEAD_UP = bytes.fromhex("f1f1010101037e")
    HEAD_DOWN = bytes.fromhex("f1f1020101047e")
    LEG_UP = bytes.fromhex("f1f1030101057e")
    LEG_DOWN = bytes.fromhex("f1f1040101067e")
    BOTH_UP = bytes.fromhex("f1f1050101077e")
    BOTH_DOWN = bytes.fromhex("f1f1060101087e")

    # 4-motor variants (head and waist separate from back)
    HEAD_UP_ALT = bytes.fromhex("f1f11901011b7e")
    HEAD_DOWN_ALT = bytes.fromhex("f1f11a01011c7e")
    WAIST_UP = bytes.fromhex("f1f11b01011d7e")
    WAIST_DOWN = bytes.fromhex("f1f11c01011e7e")

    # Presets
    ZERO_G = bytes.fromhex("f1f1070101097e")
    FLAT = bytes.fromhex("f1f10801010a7e")
    ANTI_SNORE = bytes.fromhex("f1f10901010b7e")

    # Memory presets - Go to position
    MEMORY_1 = bytes.fromhex("f1f10b01010d7e")  # Memory A
    MEMORY_2 = bytes.fromhex("f1f10d01010f7e")  # Memory B
    MEMORY_3 = bytes.fromhex("f1f11801011a7e")  # Memory C

    # Memory presets - Set/Program position
    MEMORY_1_SET = bytes.fromhex("f1f10a01010c7e")  # Set Memory A
    MEMORY_2_SET = bytes.fromhex("f1f10c01010e7e")  # Set Memory B
    MEMORY_3_SET = bytes.fromhex("f1f1170101197e")  # Set Memory C

    # Other features
    LIGHT_TOGGLE = bytes.fromhex("f1f10f000f7e")
    TIMER = bytes.fromhex("f1f10e000e7e")
    BUTTON_RELEASE = bytes.fromhex("f1f14e004e7e")  # STOP command

    # Massage - Back (data format: 0x12, 0x02, 0x08, level, checksum)
    BACK_MASSAGE_OFF = bytes.fromhex("f1f1120208001c7e")

    # Massage - Leg (data format: 0x14, 0x02, 0x08, level, checksum)
    LEG_MASSAGE_OFF = bytes.fromhex("f1f1140208001e7e")

    @staticmethod
    def back_massage(level: int) -> bytes:
        """Create back massage command for level 0-10."""
        level = max(0, min(10, level))
        # Command bytes: 0x12, 0x02, 0x08, level
        data = [0x12, 0x02, 0x08, level]
        checksum = sum(data) & 0xFF
        return bytes([0xF1, 0xF1] + data + [checksum, 0x7E])

    @staticmethod
    def leg_massage(level: int) -> bytes:
        """Create leg massage command for level 0-10."""
        level = max(0, min(10, level))
        # Command bytes: 0x14, 0x02, 0x08, level
        data = [0x14, 0x02, 0x08, level]
        checksum = sum(data) & 0xFF
        return bytes([0xF1, 0xF1] + data + [checksum, 0x7E])


class JiecangController(BedController):
    """Controller for Jiecang beds.

    Full Comfort Motion protocol with motor control, presets, massage, and lights.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Jiecang controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._massage_back_level = 0
        self._massage_leg_level = 0
        _LOGGER.debug("JiecangController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return JIECANG_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        """Jiecang beds support motor control (full Comfort Motion protocol)."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Jiecang beds support memory presets (slots 1-3)."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 3 - Jiecang beds support memory slots 1-3 (A, B, C)."""
        return 3

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Jiecang beds support programming memory positions via BLE."""
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - Jiecang beds support under-bed lighting."""
        return True

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
                await self.client.write_gatt_char(JIECANG_CHAR_UUID, command, response=True)
            except BleakError:
                _LOGGER.exception("Failed to write command")
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

    async def _move_motor(self, command: bytes, repeat_count: int = 25) -> None:
        """Move a motor with the given command, then send stop."""
        try:
            await self.write_command(command, repeat_count=repeat_count, repeat_delay_ms=50)
        finally:
            # Always send BUTTON_RELEASE (stop) with fresh event
            await self.write_command(
                JiecangCommands.BUTTON_RELEASE, cancel_event=asyncio.Event()
            )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head/back up."""
        await self._move_motor(JiecangCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head/back down."""
        await self._move_motor(JiecangCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            JiecangCommands.BUTTON_RELEASE, cancel_event=asyncio.Event()
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
        """Move legs up."""
        await self._move_motor(JiecangCommands.LEG_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor(JiecangCommands.LEG_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.write_command(
            JiecangCommands.BUTTON_RELEASE, cancel_event=asyncio.Event()
        )

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors using BUTTON_RELEASE command."""
        await self.write_command(
            JiecangCommands.BUTTON_RELEASE, cancel_event=asyncio.Event()
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            JiecangCommands.FLAT,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            JiecangCommands.ZERO_G,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            JiecangCommands.ANTI_SNORE,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (1-3)."""
        commands = {
            1: JiecangCommands.MEMORY_1,
            2: JiecangCommands.MEMORY_2,
            3: JiecangCommands.MEMORY_3,
        }
        if command := commands.get(memory_num):
            await self.write_command(command, repeat_count=3, repeat_delay_ms=100)
        else:
            _LOGGER.warning("Jiecang beds support memory presets 1-3 only")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (1-3)."""
        commands = {
            1: JiecangCommands.MEMORY_1_SET,
            2: JiecangCommands.MEMORY_2_SET,
            3: JiecangCommands.MEMORY_3_SET,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)
        else:
            _LOGGER.warning("Jiecang beds support memory presets 1-3 only")

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(JiecangCommands.LIGHT_TOGGLE)

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        self._massage_back_level = 0
        self._massage_leg_level = 0
        await self.write_command(JiecangCommands.BACK_MASSAGE_OFF)
        await self.write_command(JiecangCommands.LEG_MASSAGE_OFF)

    async def massage_head_up(self) -> None:
        """Increase back massage intensity (0-10)."""
        self._massage_back_level = min(10, self._massage_back_level + 1)
        await self.write_command(JiecangCommands.back_massage(self._massage_back_level))

    async def massage_head_down(self) -> None:
        """Decrease back massage intensity (0-10)."""
        self._massage_back_level = max(0, self._massage_back_level - 1)
        await self.write_command(JiecangCommands.back_massage(self._massage_back_level))

    async def massage_foot_up(self) -> None:
        """Increase leg massage intensity (0-10)."""
        self._massage_leg_level = min(10, self._massage_leg_level + 1)
        await self.write_command(JiecangCommands.leg_massage(self._massage_leg_level))

    async def massage_foot_down(self) -> None:
        """Decrease leg massage intensity (0-10)."""
        self._massage_leg_level = max(0, self._massage_leg_level - 1)
        await self.write_command(JiecangCommands.leg_massage(self._massage_leg_level))
