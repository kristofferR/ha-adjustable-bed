"""Leggett & Platt bed controller implementation.

Leggett & Platt beds have two protocol variants:

Gen2 (Richmat-based, ASCII commands):
    Service UUID: 45e25100-3171-4cfc-ae89-1d83cf8d8071
    Write characteristic: 45e25101-3171-4cfc-ae89-1d83cf8d8071
    Read characteristic: 45e25103-3171-4cfc-ae89-1d83cf8d8071
    Command format: ASCII text (e.g., b"MEM 0" for flat preset)
    Motor timing: Single command per action; presets move to position automatically
    Position feedback: Not supported

Okin variant (requires BLE pairing):
    Service UUID: 62741523-52f9-8864-b1ab-3b3a8d65950b (shared with Okimat/Nectar)
    Write characteristic: 62741525-52f9-8864-b1ab-3b3a8d65950b
    Command format: 6-byte binary [0x04, 0x02, <4-byte-command-big-endian>]
    Motor timing: 25 pulses at 200ms intervals for continuous movement
    Position feedback: Not supported
    Pairing: Required before first use; handled by coordinator

Note: The Okin variant shares its BLE service UUID with Okimat and Nectar beds.
Detection uses device name patterns ("leggett", "l&p") to distinguish between these
bed types. See okin_protocol.py for the shared binary protocol specification.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import (
    LEGGETT_GEN2_WRITE_CHAR_UUID,
    LEGGETT_OKIN_CHAR_UUID,
)
from .base import BedController
from .okin_protocol import build_okin_command

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


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

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        # Only Okin variant supports Zero G
        return self._variant == "okin"

    @property
    def supports_preset_anti_snore(self) -> bool:
        # Only Gen2 variant supports Anti-Snore
        return self._variant != "okin"

    @property
    def supports_lights(self) -> bool:
        """Return True - Leggett & Platt beds support lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True only for Gen2 variant which has RGB control.

        Okin variant only supports toggle, not discrete on/off.
        """
        return self._variant == "gen2"

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Leggett & Platt beds support memory presets."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Leggett & Platt beds support memory slots 1-4."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return True only for Gen2 variant which has programming commands.

        Okin variant doesn't support programming memory positions.
        """
        return self._variant == "gen2"

    def _build_okin_command(self, command_value: int) -> bytes:
        """Build Okin binary command by delegating to build_okin_command.

        Args:
            command_value: 32-bit command value (0 to 0xFFFFFFFF)

        Returns:
            6-byte command: [0x04, 0x02, <4-byte-command-big-endian>]
        """
        return build_okin_command(command_value)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Leggett & Platt bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            self._char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

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

        try:
            if command:
                await self.write_command(
                    self._build_okin_command(command),
                    repeat_count=25,
                    repeat_delay_ms=200,
                )
        finally:
            self._motor_state = {}
            # Wrap in try-except to prevent masking the original exception
            try:
                await self.write_command(
                    self._build_okin_command(0),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send stop command during cleanup")

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
