"""Leggett & Platt bed controller implementation.

Leggett & Platt beds have two protocol variants:
- Gen2: ASCII text commands (Richmat-based)
- Okin: Binary commands with 6-byte format (requires BLE pairing)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import (
    LEGGETT_GEN2_WRITE_CHAR_UUID,
    LEGGETT_OKIN_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def int_to_bytes(value: int) -> list[int]:
    """Convert an integer to 4 bytes (big-endian)."""
    return [
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ]


class LeggettPlattGen2Commands:
    """Leggett & Platt Gen2 ASCII commands."""

    # Presets
    PRESET_FLAT = b"MEM 0"
    PRESET_UNWIND = b"MEM 1"
    PRESET_SLEEP = b"MEM 2"
    PRESET_WAKE_UP = b"MEM 3"
    PRESET_RELAX = b"MEM 4"
    PRESET_ANTI_SNORE = b"SNR"

    # Programming
    PROGRAM_UNWIND = b"SMEM 1"
    PROGRAM_SLEEP = b"SMEM 2"
    PROGRAM_WAKE_UP = b"SMEM 3"
    PROGRAM_RELAX = b"SMEM 4"
    PROGRAM_ANTI_SNORE = b"SNPOS 0"

    # Control
    STOP = b"STOP"
    GET_STATE = b"GET STATE"

    # Lighting
    RGB_OFF = b"RGBENABLE 0:0"

    @staticmethod
    def rgb_set(red: int, green: int, blue: int, brightness: int) -> bytes:
        """Create RGB color command."""
        hex_str = f"{red:02X}{green:02X}{blue:02X}{brightness:02X}"
        return f"RGBSET 0:{hex_str}".encode()

    # Massage
    @staticmethod
    def massage_head_strength(strength: int) -> bytes:
        """Set head massage strength (0-10)."""
        return f"MVI 0:{strength}".encode()

    @staticmethod
    def massage_foot_strength(strength: int) -> bytes:
        """Set foot massage strength (0-10)."""
        return f"MVI 1:{strength}".encode()

    MASSAGE_WAVE_ON = b"MMODE 0:0"
    MASSAGE_WAVE_OFF = b"MMODE 0:2"

    @staticmethod
    def massage_wave_level(level: int) -> bytes:
        """Set wave massage level."""
        return f"WSP 0:{level}".encode()


class LeggettPlattOkinCommands:
    """Leggett & Platt Okin command constants (32-bit values)."""

    # Same as Keeson/Okimat since they share the Okin protocol
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000
    PRESET_MEMORY_2 = 0x4000
    PRESET_MEMORY_3 = 0x8000
    PRESET_MEMORY_4 = 0x10000

    MOTOR_HEAD_UP = 0x1
    MOTOR_HEAD_DOWN = 0x2
    MOTOR_FEET_UP = 0x4
    MOTOR_FEET_DOWN = 0x8
    MOTOR_TILT_UP = 0x10
    MOTOR_TILT_DOWN = 0x20
    MOTOR_LUMBAR_UP = 0x40
    MOTOR_LUMBAR_DOWN = 0x80

    MASSAGE_HEAD_UP = 0x800
    MASSAGE_HEAD_DOWN = 0x800000
    MASSAGE_FOOT_UP = 0x400
    MASSAGE_FOOT_DOWN = 0x1000000
    MASSAGE_STEP = 0x100

    TOGGLE_LIGHTS = 0x20000


class LeggettPlattController(BedController):
    """Controller for Leggett & Platt beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = "gen2",
    ) -> None:
        """Initialize the Leggett & Platt controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            variant: Protocol variant ('gen2' or 'okin')
        """
        super().__init__(coordinator)
        self._variant = variant
        self._char_uuid = (
            LEGGETT_GEN2_WRITE_CHAR_UUID if variant == "gen2"
            else LEGGETT_OKIN_CHAR_UUID
        )
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}
        self._massage_head_level = 0
        self._massage_foot_level = 0
        _LOGGER.debug(
            "LeggettPlattController initialized (variant: %s)",
            variant,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    def _build_okin_command(self, command_value: int) -> bytes:
        """Build Okin binary command: [0x04, 0x02, ...int_bytes]."""
        return bytes([0x04, 0x02] + int_to_bytes(command_value))

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
            "Writing command to Leggett & Platt bed: %s (repeat: %d, delay: %dms)",
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
                    self._char_uuid, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Leggett & Platt beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    def _get_okin_move_command(self) -> int:
        """Calculate the combined motor movement command for Okin variant."""
        command = 0
        state = self._motor_state
        if state.get("head") is True:
            command += LeggettPlattOkinCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command += LeggettPlattOkinCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            command += LeggettPlattOkinCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command += LeggettPlattOkinCommands.MOTOR_FEET_DOWN
        return command

    async def _move_okin(self, motor: str, direction: bool | None) -> None:
        """Move a motor using Okin protocol."""
        self._motor_state[motor] = direction
        command = self._get_okin_move_command()

        if command:
            await self.write_command(
                self._build_okin_command(command),
                repeat_count=25,
                repeat_delay_ms=200,
            )
        self._motor_state = {}
        await self.write_command(
            self._build_okin_command(0),
            cancel_event=asyncio.Event(),
        )

    # Motor control methods - Gen2 variant doesn't have motor control via BLE
    # (uses position-based control instead)
    async def move_head_up(self) -> None:
        """Move head up."""
        if self._variant == "okin":
            await self._move_okin("head", True)
        else:
            _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_head_down(self) -> None:
        """Move head down."""
        if self._variant == "okin":
            await self._move_okin("head", False)
        else:
            _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        if self._variant == "okin":
            await self._move_okin("head", None)
        else:
            await self.write_command(
                LeggettPlattGen2Commands.STOP,
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
        """Move legs up."""
        if self._variant == "okin":
            await self._move_okin("feet", True)
        else:
            _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_legs_down(self) -> None:
        """Move legs down."""
        if self._variant == "okin":
            await self._move_okin("feet", False)
        else:
            _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        if self._variant == "okin":
            await self._move_okin("feet", None)
        else:
            await self.write_command(
                LeggettPlattGen2Commands.STOP,
                cancel_event=asyncio.Event(),
            )

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
        if self._variant == "okin":
            self._motor_state = {}
            await self.write_command(
                self._build_okin_command(0),
                cancel_event=asyncio.Event(),
            )
        else:
            await self.write_command(
                LeggettPlattGen2Commands.STOP,
                cancel_event=asyncio.Event(),
            )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.PRESET_FLAT),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        else:
            await self.write_command(
                LeggettPlattGen2Commands.PRESET_FLAT,
                repeat_count=100,
                repeat_delay_ms=300,
            )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        if self._variant == "okin":
            commands = {
                1: LeggettPlattOkinCommands.PRESET_MEMORY_1,
                2: LeggettPlattOkinCommands.PRESET_MEMORY_2,
                3: LeggettPlattOkinCommands.PRESET_MEMORY_3,
                4: LeggettPlattOkinCommands.PRESET_MEMORY_4,
            }
            if command := commands.get(memory_num):
                await self.write_command(
                    self._build_okin_command(command),
                    repeat_count=100,
                    repeat_delay_ms=300,
                )
        else:
            commands = {
                1: LeggettPlattGen2Commands.PRESET_UNWIND,
                2: LeggettPlattGen2Commands.PRESET_SLEEP,
                3: LeggettPlattGen2Commands.PRESET_WAKE_UP,
                4: LeggettPlattGen2Commands.PRESET_RELAX,
            }
            if command := commands.get(memory_num):
                await self.write_command(command, repeat_count=100, repeat_delay_ms=300)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        if self._variant == "okin":
            _LOGGER.warning("Okin beds don't support programming memory presets")
        else:
            commands = {
                1: LeggettPlattGen2Commands.PROGRAM_UNWIND,
                2: LeggettPlattGen2Commands.PROGRAM_SLEEP,
                3: LeggettPlattGen2Commands.PROGRAM_WAKE_UP,
                4: LeggettPlattGen2Commands.PROGRAM_RELAX,
            }
            if command := commands.get(memory_num):
                await self.write_command(command)

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.TOGGLE_LIGHTS)
            )
        else:
            # Gen2 uses RGB commands
            await self.write_command(LeggettPlattGen2Commands.RGB_OFF)

    async def lights_on(self) -> None:
        """Turn on lights (Gen2 only - white at full brightness)."""
        if self._variant == "gen2":
            await self.write_command(
                LeggettPlattGen2Commands.rgb_set(255, 255, 255, 255)
            )

    async def lights_off(self) -> None:
        """Turn off lights."""
        if self._variant == "gen2":
            await self.write_command(LeggettPlattGen2Commands.RGB_OFF)
        else:
            await self.lights_toggle()

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        if self._variant == "gen2":
            self._massage_head_level = 0
            self._massage_foot_level = 0
            await self.write_command(LeggettPlattGen2Commands.massage_head_strength(0))
            await self.write_command(LeggettPlattGen2Commands.massage_foot_strength(0))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.MASSAGE_HEAD_UP)
            )
        else:
            self._massage_head_level = min(10, self._massage_head_level + 1)
            await self.write_command(
                LeggettPlattGen2Commands.massage_head_strength(self._massage_head_level)
            )

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.MASSAGE_HEAD_DOWN)
            )
        else:
            self._massage_head_level = max(0, self._massage_head_level - 1)
            await self.write_command(
                LeggettPlattGen2Commands.massage_head_strength(self._massage_head_level)
            )

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.MASSAGE_FOOT_UP)
            )
        else:
            self._massage_foot_level = min(10, self._massage_foot_level + 1)
            await self.write_command(
                LeggettPlattGen2Commands.massage_foot_strength(self._massage_foot_level)
            )

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.MASSAGE_FOOT_DOWN)
            )
        else:
            self._massage_foot_level = max(0, self._massage_foot_level - 1)
            await self.write_command(
                LeggettPlattGen2Commands.massage_foot_strength(self._massage_foot_level)
            )

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.MASSAGE_STEP)
            )
        else:
            # Toggle wave mode
            await self.write_command(LeggettPlattGen2Commands.MASSAGE_WAVE_ON)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (Okin variant only)."""
        if self._variant == "okin":
            await self.write_command(
                self._build_okin_command(LeggettPlattOkinCommands.PRESET_ZERO_G),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        else:
            _LOGGER.warning("Zero-G preset not available on Gen2 beds")

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (Gen2 variant only)."""
        if self._variant == "gen2":
            await self.write_command(
                LeggettPlattGen2Commands.PRESET_ANTI_SNORE,
                repeat_count=100,
                repeat_delay_ms=300,
            )
        else:
            _LOGGER.warning("Anti-snore preset not available on Okin beds")
