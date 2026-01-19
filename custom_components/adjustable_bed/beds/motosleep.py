"""MotoSleep bed controller implementation.

MotoSleep beds (HHC controllers) use simple 2-byte ASCII commands: [0x24, ASCII_CHAR]
The 0x24 is the '$' character followed by a command letter.

Device names start with "HHC" followed by hexadecimal characters (e.g., HHC3611243CDEF).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import MOTOSLEEP_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class MotoSleepCommands:
    """MotoSleep command constants (ASCII characters)."""

    # Presets
    PRESET_HOME = ord('O')
    PRESET_MEMORY_1 = ord('U')
    PRESET_MEMORY_2 = ord('V')
    PRESET_ANTI_SNORE = ord('R')
    PRESET_TV = ord('S')
    PRESET_ZERO_G = ord('T')

    # Programming
    PROGRAM_MEMORY_1 = ord('Z')
    PROGRAM_MEMORY_2 = ord('a')
    PROGRAM_ANTI_SNORE = ord('W')
    PROGRAM_TV = ord('X')
    PROGRAM_ZERO_G = ord('Y')

    # Motors
    MOTOR_HEAD_UP = ord('K')
    MOTOR_HEAD_DOWN = ord('L')
    MOTOR_FEET_UP = ord('M')
    MOTOR_FEET_DOWN = ord('N')
    MOTOR_NECK_UP = ord('P')
    MOTOR_NECK_DOWN = ord('Q')
    MOTOR_LUMBAR_UP = ord('p')  # lowercase for some models
    MOTOR_LUMBAR_DOWN = ord('q')

    # Massage
    MASSAGE_HEAD_STEP = ord('C')
    MASSAGE_FOOT_STEP = ord('B')
    MASSAGE_STOP = ord('D')
    MASSAGE_HEAD_UP = ord('G')
    MASSAGE_HEAD_DOWN = ord('H')
    MASSAGE_FOOT_UP = ord('E')
    MASSAGE_FOOT_DOWN = ord('F')
    MASSAGE_HEAD_OFF = ord('J')
    MASSAGE_FOOT_OFF = ord('I')

    # Lighting
    LIGHTS_TOGGLE = ord('A')


class MotoSleepController(BedController):
    """Controller for MotoSleep beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the MotoSleep controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("MotoSleepController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return MOTOSLEEP_CHAR_UUID

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
    def supports_lights(self) -> bool:
        """Return True - MotoSleep beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - MotoSleep only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - MotoSleep beds support memory presets (slots 1-2)."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 2 - MotoSleep beds support memory slots 1-2."""
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - MotoSleep beds support programming memory positions."""
        return True

    def _build_command(self, char_code: int) -> bytes:
        """Build a 2-byte command: [0x24, char_code]."""
        return bytes([0x24, char_code])

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to MotoSleep bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            MOTOSLEEP_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=True,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("MotoSleep beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    async def _move_motor(self, command_char: int) -> None:
        """Execute a movement command.

        MotoSleep motors stop automatically when commands stop being sent,
        similar to releasing a button on a physical remote. No explicit stop
        command is needed or available for motors.
        """
        await self.write_command(
            self._build_command(command_char),
            repeat_count=30,
            repeat_delay_ms=50,
        )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor(MotoSleepCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor(MotoSleepCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        # MotoSleep doesn't have a dedicated stop - releasing the button stops
        pass

    async def move_back_up(self) -> None:
        """Move back up (same as head for MotoSleep)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for MotoSleep)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        pass

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for MotoSleep)."""
        await self._move_motor(MotoSleepCommands.MOTOR_FEET_UP)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for MotoSleep)."""
        await self._move_motor(MotoSleepCommands.MOTOR_FEET_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        pass

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor(MotoSleepCommands.MOTOR_FEET_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor(MotoSleepCommands.MOTOR_FEET_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        pass

    async def stop_all(self) -> None:
        """Stop all motors.

        MotoSleep has no universal stop command. Motors stop automatically
        when movement commands stop being sent. This method signals cancellation
        to interrupt any ongoing command sequences.
        """
        self._coordinator.cancel_command.set()

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat/home position."""
        await self.write_command(
            self._build_command(MotoSleepCommands.PRESET_HOME),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: MotoSleepCommands.PRESET_MEMORY_1,
            2: MotoSleepCommands.PRESET_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=150,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: MotoSleepCommands.PROGRAM_MEMORY_1,
            2: MotoSleepCommands.PROGRAM_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights (MotoSleep only supports toggle)."""
        await self.write_command(self._build_command(MotoSleepCommands.LIGHTS_TOGGLE))

    async def lights_off(self) -> None:
        """Turn off under-bed lights (MotoSleep only supports toggle)."""
        await self.write_command(self._build_command(MotoSleepCommands.LIGHTS_TOGGLE))

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(MotoSleepCommands.LIGHTS_TOGGLE))

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_STOP))

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_HEAD_STEP))

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_FOOT_STEP))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(MotoSleepCommands.MASSAGE_FOOT_DOWN))

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            self._build_command(MotoSleepCommands.PRESET_ZERO_G),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            self._build_command(MotoSleepCommands.PRESET_ANTI_SNORE),
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(
            self._build_command(MotoSleepCommands.PRESET_TV),
            repeat_count=100,
            repeat_delay_ms=150,
        )
