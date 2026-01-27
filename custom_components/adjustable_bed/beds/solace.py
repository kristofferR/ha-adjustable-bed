"""Solace bed controller implementation.

Reverse engineering by Bonopaws and Richard Hopton (smartbed-mqtt).

Solace beds use 11-byte command packets with pre-defined command arrays.
These are typically hospital/care beds.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import SOLACE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SolaceCommands:
    """Solace command constants (11-byte arrays)."""

    # Presets
    PRESET_TV = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x05, 0x17, 0x03])
    PRESET_ZERO_G = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x09, 0x17, 0x06])
    PRESET_ANTI_SNORE = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0F, 0x97, 0x04])
    PRESET_YOGA = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x4E, 0x57, 0x34])
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

    # Program memory
    PROGRAM_MEMORY_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xA0, 0x0A, 0x2F, 0x07])
    PROGRAM_MEMORY_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0xB0, 0x0B, 0xE3, 0x07])
    PROGRAM_MEMORY_3 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x50, 0x05, 0x2B, 0x03])
    PROGRAM_MEMORY_4 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x90, 0x09, 0x7B, 0x06])

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

    # Hip motor
    MOTOR_HIP_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0D, 0x16, 0xC5])
    MOTOR_HIP_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x0E, 0x56, 0xC4])

    # Massage controls
    MASSAGE_HEAD_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x10, 0xD6, 0xCC])
    MASSAGE_HEAD_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x11, 0x17, 0x0C])
    MASSAGE_FOOT_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x12, 0x57, 0x0D])
    MASSAGE_FOOT_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x13, 0x96, 0xCD])
    MASSAGE_FREQUENCY_UP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x14, 0xD7, 0x0F])
    MASSAGE_FREQUENCY_DOWN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x15, 0x16, 0xCF])
    MASSAGE_STOP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x1C, 0xD6, 0xC9])

    # Circulation/Loop massage modes
    MASSAGE_CIRCULATION_FULL_BODY = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE4, 0xC7, 0x4A])
    MASSAGE_CIRCULATION_HEAD = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE3, 0x86, 0x88])
    MASSAGE_CIRCULATION_LEG = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE5, 0x06, 0x8A])
    MASSAGE_CIRCULATION_HIP = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x05, 0x00, 0xE6, 0x46, 0x8B])

    # Light levels (0-10)
    LIGHT_LEVEL_0 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x23, 0x96, 0xD9])
    LIGHT_LEVEL_1 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x01, 0x23, 0x97, 0x49])
    LIGHT_LEVEL_2 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x02, 0x23, 0x97, 0xB9])
    LIGHT_LEVEL_3 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x03, 0x23, 0x96, 0x29])
    LIGHT_LEVEL_4 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x04, 0x23, 0x94, 0x19])
    LIGHT_LEVEL_5 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x05, 0x23, 0x95, 0x89])
    LIGHT_LEVEL_6 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x06, 0x23, 0x95, 0x79])
    LIGHT_LEVEL_7 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x07, 0x23, 0x94, 0xE9])
    LIGHT_LEVEL_8 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x08, 0x23, 0x91, 0x19])
    LIGHT_LEVEL_9 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x09, 0x23, 0x90, 0x89])
    LIGHT_LEVEL_10 = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x0A, 0x23, 0x90, 0x79])

    # Light timers
    LIGHT_TIMER_10_MIN = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x19, 0x16, 0xCA])
    LIGHT_TIMER_8_HOURS = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x1A, 0x56, 0xCB])
    LIGHT_TIMER_10_HOURS = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x05, 0x00, 0x00, 0x00, 0x1B, 0x97, 0x0B])


class SolaceController(BedController):
    """Controller for Solace beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Solace controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("SolaceController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return SOLACE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_yoga(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Solace beds support memory presets (slots 1-4)."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Solace beds support memory slots 1-4."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Solace beds support programming memory positions."""
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
            "Writing command to Solace bed (%s): %s (repeat: %d, delay: %dms, response=True)",
            SOLACE_CHAR_UUID,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                await self.client.write_gatt_char(SOLACE_CHAR_UUID, command, response=True)
            except BleakError:
                _LOGGER.exception("Failed to write command")
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
            try:
                await self.write_command(
                    SolaceCommands.MOTOR_STOP,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

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
        }
        if command := commands.get(memory_num):
            await self.write_command(command, repeat_count=100, repeat_delay_ms=300)
        else:
            _LOGGER.warning("Invalid memory preset number: %d (valid: 1-4)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: SolaceCommands.PROGRAM_MEMORY_1,
            2: SolaceCommands.PROGRAM_MEMORY_2,
            3: SolaceCommands.PROGRAM_MEMORY_3,
            4: SolaceCommands.PROGRAM_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)
        else:
            _LOGGER.warning("Invalid memory program number: %d (valid: 1-4)", memory_num)

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

    async def preset_yoga(self) -> None:
        """Go to yoga position."""
        await self.write_command(
            SolaceCommands.PRESET_YOGA,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    # Massage methods
    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_FOOT_DOWN)

    async def massage_intensity_up(self) -> None:
        """Increase massage frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_DOWN)

    async def massage_off(self) -> None:
        """Stop all massage."""
        await self.write_command(SolaceCommands.MASSAGE_STOP)

    # Hip motor support
    @property
    def has_hip_support(self) -> bool:
        """Return True - Solace beds have hip motor."""
        return True

    async def move_hip_up(self) -> None:
        """Move hip motor up."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_UP)

    async def move_hip_down(self) -> None:
        """Move hip motor down."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_DOWN)

    async def move_hip_stop(self) -> None:
        """Stop hip motor."""
        await self.move_head_stop()

    # Light level control
    @property
    def supports_light_level_control(self) -> bool:
        """Return True - Solace beds support light level control."""
        return True

    @property
    def light_level_max(self) -> int:
        """Return maximum light level (10)."""
        return 10

    async def set_light_level(self, level: int) -> None:
        """Set light level (0-10)."""
        commands = [
            SolaceCommands.LIGHT_LEVEL_0,
            SolaceCommands.LIGHT_LEVEL_1,
            SolaceCommands.LIGHT_LEVEL_2,
            SolaceCommands.LIGHT_LEVEL_3,
            SolaceCommands.LIGHT_LEVEL_4,
            SolaceCommands.LIGHT_LEVEL_5,
            SolaceCommands.LIGHT_LEVEL_6,
            SolaceCommands.LIGHT_LEVEL_7,
            SolaceCommands.LIGHT_LEVEL_8,
            SolaceCommands.LIGHT_LEVEL_9,
            SolaceCommands.LIGHT_LEVEL_10,
        ]
        if 0 <= level <= 10:
            await self.write_command(commands[level])
        else:
            _LOGGER.warning("Invalid light level: %d (valid: 0-10)", level)

    # Light timer control
    @property
    def supports_light_timer(self) -> bool:
        """Return True - Solace beds support light timer."""
        return True

    @property
    def light_timer_options(self) -> list[str]:
        """Return available light timer options."""
        return ["Off", "10 min", "8 hours", "10 hours"]

    async def set_light_timer(self, timer_option: str) -> None:
        """Set light timer.

        Args:
            timer_option: One of "Off", "10 min", "8 hours", "10 hours"
        """
        commands = {
            "Off": SolaceCommands.LIGHT_LEVEL_0,  # Turn off light
            "10 min": SolaceCommands.LIGHT_TIMER_10_MIN,
            "8 hours": SolaceCommands.LIGHT_TIMER_8_HOURS,
            "10 hours": SolaceCommands.LIGHT_TIMER_10_HOURS,
        }
        if cmd := commands.get(timer_option):
            await self.write_command(cmd)
        else:
            _LOGGER.warning("Invalid light timer option: %s", timer_option)

    # Circulation massage support
    @property
    def supports_circulation_massage(self) -> bool:
        """Return True - Solace beds support circulation massage modes."""
        return True

    async def massage_circulation_full_body(self) -> None:
        """Start full body circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_FULL_BODY)

    async def massage_circulation_head(self) -> None:
        """Start head circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_HEAD)

    async def massage_circulation_leg(self) -> None:
        """Start leg circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_LEG)

    async def massage_circulation_hip(self) -> None:
        """Start hip circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_HIP)
