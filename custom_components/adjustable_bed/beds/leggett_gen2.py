"""Leggett & Platt Gen2 bed controller implementation.

Reverse engineering by MarcusW and Richard Hopton (smartbed-mqtt).

This controller handles Leggett & Platt beds using the Gen2 (Richmat-based) ASCII protocol.

Protocol details:
    Service UUID: 45e25100-3171-4cfc-ae89-1d83cf8d8071
    Write characteristic: 45e25101-3171-4cfc-ae89-1d83cf8d8071
    Read characteristic: 45e25103-3171-4cfc-ae89-1d83cf8d8071
    Command format: ASCII text (e.g., b"MEM 0" for flat preset)

Features:
    - Position presets (Flat, Unwind, Sleep, Wake Up, Relax, Anti-Snore)
    - Memory position programming
    - RGB under-bed lighting control
    - Massage control with adjustable strength
    - No motor control (position-based control only)
    - No position feedback
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import LEGGETT_GEN2_WRITE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class LeggettGen2Commands:
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


class LeggettGen2Controller(BedController):
    """Controller for Leggett & Platt Gen2 beds.

    These beds use ASCII commands over BLE for preset control, lighting, and massage.
    They do not support direct motor control (uses position-based control instead).
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Leggett & Platt Gen2 controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._massage_head_level = 0
        self._massage_foot_level = 0
        _LOGGER.debug("LeggettGen2Controller initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LEGGETT_GEN2_WRITE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return False  # Gen2 doesn't support Zero G

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - Gen2 beds support RGB lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - Gen2 has RGB control with discrete on/off."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Gen2 beds support memory presets 1-4."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Gen2 beds support memory slots 1-4."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Gen2 beds support programming memory positions."""
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Leggett & Platt Gen2 bed: %s (repeat: %d, delay: %dms)",
            command,
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            LEGGETT_GEN2_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Leggett & Platt Gen2 beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        _ = motor_count  # Unused - this bed doesn't support position feedback

    # Motor control methods - Gen2 variant doesn't have motor control via BLE
    # (uses position-based control instead)
    async def move_head_up(self) -> None:
        """Move head up."""
        _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_head_down(self) -> None:
        """Move head down."""
        _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            LeggettGen2Commands.STOP,
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
        _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_legs_down(self) -> None:
        """Move legs down."""
        _LOGGER.warning("Gen2 beds use position-based control, not motor commands")

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.write_command(
            LeggettGen2Commands.STOP,
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
        await self.write_command(
            LeggettGen2Commands.STOP,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        try:
            await self.write_command(
                LeggettGen2Commands.PRESET_FLAT,
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            try:
                await self.write_command(
                    LeggettGen2Commands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during preset_flat cleanup")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LeggettGen2Commands.PRESET_UNWIND,
            2: LeggettGen2Commands.PRESET_SLEEP,
            3: LeggettGen2Commands.PRESET_WAKE_UP,
            4: LeggettGen2Commands.PRESET_RELAX,
        }
        if command := commands.get(memory_num):
            try:
                await self.write_command(command, repeat_count=100, repeat_delay_ms=300)
            finally:
                try:
                    await self.write_command(
                        LeggettGen2Commands.STOP,
                        cancel_event=asyncio.Event(),
                    )
                except Exception:
                    _LOGGER.debug("Failed to send STOP command during preset_memory cleanup")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: LeggettGen2Commands.PROGRAM_UNWIND,
            2: LeggettGen2Commands.PROGRAM_SLEEP,
            3: LeggettGen2Commands.PROGRAM_WAKE_UP,
            4: LeggettGen2Commands.PROGRAM_RELAX,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (not supported on Gen2)."""
        _LOGGER.warning("Zero-G preset not available on Gen2 beds")

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        try:
            await self.write_command(
                LeggettGen2Commands.PRESET_ANTI_SNORE,
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            try:
                await self.write_command(
                    LeggettGen2Commands.STOP,
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during preset_anti_snore cleanup")

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(LeggettGen2Commands.RGB_OFF)

    async def lights_on(self) -> None:
        """Turn on lights (white at full brightness)."""
        await self.write_command(LeggettGen2Commands.rgb_set(255, 255, 255, 255))

    async def lights_off(self) -> None:
        """Turn off lights."""
        await self.write_command(LeggettGen2Commands.RGB_OFF)

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        self._massage_head_level = 0
        self._massage_foot_level = 0
        await self.write_command(LeggettGen2Commands.massage_head_strength(0))
        await self.write_command(LeggettGen2Commands.massage_foot_strength(0))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        self._massage_head_level = min(10, self._massage_head_level + 1)
        await self.write_command(
            LeggettGen2Commands.massage_head_strength(self._massage_head_level)
        )

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        self._massage_head_level = max(0, self._massage_head_level - 1)
        await self.write_command(
            LeggettGen2Commands.massage_head_strength(self._massage_head_level)
        )

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        self._massage_foot_level = min(10, self._massage_foot_level + 1)
        await self.write_command(
            LeggettGen2Commands.massage_foot_strength(self._massage_foot_level)
        )

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        self._massage_foot_level = max(0, self._massage_foot_level - 1)
        await self.write_command(
            LeggettGen2Commands.massage_foot_strength(self._massage_foot_level)
        )

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(LeggettGen2Commands.MASSAGE_WAVE_ON)
