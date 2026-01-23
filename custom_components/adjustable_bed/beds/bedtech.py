"""BedTech bed controller implementation.

BedTech beds use a 5-byte ASCII command protocol:
- Single char commands: [0x6E, 0x01, 0x00, charCode, charCode + 0x6F]
- Dual base commands: [0x6E, 0x01, 0x01, charCode2, charCode2 + 0x70]

Protocol reverse-engineered from com.bedtech BedTech app (React Native/Hermes).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import (
    BEDTECH_SERVICE_UUID,
    BEDTECH_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class BedTechCommands:
    """BedTech command characters."""

    # Head motor
    HEAD_UP = "$"  # 0x24
    HEAD_DOWN = "%"  # 0x25
    HEAD_MASSAGE_UP = "L"  # 0x4C
    HEAD_MASSAGE_DOWN = "M"  # 0x4D

    # Head2 motor (dual base)
    HEAD2_UP = "_$"
    HEAD2_DOWN = "_%"
    HEAD2_MASSAGE_UP = "_L"
    HEAD2_MASSAGE_DOWN = "_M"

    # Foot motor
    FOOT_UP = "&"  # 0x26
    FOOT_DOWN = "'"  # 0x27
    FOOT_MASSAGE_UP = "N"  # 0x4E
    FOOT_MASSAGE_DOWN = "O"  # 0x4F

    # Both heads/feet (sync)
    BOTH_HEADS_UP = "?"  # 0x3F
    BOTH_HEADS_DOWN = "@"  # 0x40
    BOTH_FEET_UP = "A"  # 0x41
    BOTH_FEET_DOWN = "B"  # 0x42

    # Leg/Pillow motor
    LEG_UP = ")"  # 0x29
    LEG_DOWN = "*"  # 0x2A

    # Presets
    PRESET_FLAT = "1"  # 0x31
    PRESET_FLAT2 = "l"  # 0x6C
    PRESET_ZERO_G = "E"  # 0x45
    PRESET_ANTI_SNORE = "F"  # 0x46
    PRESET_TV = "X"  # 0x58
    PRESET_LOUNGE = "e"  # 0x65

    # Presets (dual base)
    PRESET2_FLAT = "_1"
    PRESET2_ZERO_G = "_E"
    PRESET2_ANTI_SNORE = "_F"
    PRESET2_TV = "_X"
    PRESET2_LOUNGE = "_e"

    # Massage modes
    MASSAGE_CONSTANT = ":"  # 0x3A
    MASSAGE_PULSE = "8"  # 0x38
    MASSAGE_WAVE1 = "I"  # 0x49
    MASSAGE_WAVE2 = "J"  # 0x4A
    MASSAGE_WAVE3 = "K"  # 0x4B

    # Massage control
    MASSAGE_ON = "]"  # 0x5D
    MASSAGE_OFF = "^"  # 0x5E
    MASSAGE_SWITCH = "H"  # 0x48

    # Massage timer
    MASSAGE_TIMER_10 = "_"  # 0x5F
    MASSAGE_TIMER_20 = "c"  # 0x63
    MASSAGE_TIMER_30 = "a"  # 0x61

    # Light control
    LIGHT_GO = "."  # 0x2E
    LIGHT_SAVE = "+"  # 0x2B
    LIGHT_OFF = "u"  # 0x75
    LIGHT_TOGGLE = "<"  # 0x3C

    # Light2 (dual base)
    LIGHT2_GO = "_."
    LIGHT2_SAVE = "_+"
    LIGHT2_OFF = "_u"
    LIGHT2_TOGGLE = "_<"

    # Memory
    MEMORY_GO = "/"  # 0x2F
    MEMORY_SAVE = ","  # 0x2C

    # Memory2 (dual base)
    MEMORY2_GO = "_/"
    MEMORY2_SAVE = "_,"


def build_bedtech_command(cmd_char: str) -> bytes:
    """Build a 5-byte BedTech command packet.

    Args:
        cmd_char: Command character (single char or "_X" for dual base)

    Returns:
        5-byte command packet
    """
    if len(cmd_char) == 2 and cmd_char.startswith("_"):
        # Two-character command (dual-base): [0x6E, 0x01, 0x01, char2, char2 + 0x70]
        char_code = ord(cmd_char[1])
        return bytes([0x6E, 0x01, 0x01, char_code, (char_code + 0x70) & 0xFF])
    else:
        # Single character command: [0x6E, 0x01, 0x00, char, char + 0x6F]
        char_code = ord(cmd_char[0])
        return bytes([0x6E, 0x01, 0x00, char_code, (char_code + 0x6F) & 0xFF])


class BedTechController(BedController):
    """Controller for BedTech beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        is_dual_base: bool = False,
    ) -> None:
        """Initialize the BedTech controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            is_dual_base: Whether this is a dual-base bed (King/Split King)
        """
        super().__init__(coordinator)
        self._is_dual_base = is_dual_base
        self._char_uuid = BEDTECH_WRITE_CHAR_UUID
        self._notify_callback: Callable[[str, float], None] | None = None

        _LOGGER.debug(
            "BedTechController initialized (char: %s, dual_base: %s)",
            self._char_uuid,
            is_dual_base,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

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
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - BedTech supports discrete on/off control."""
        return True

    @property
    def has_pillow_support(self) -> bool:
        """Return True - BedTech beds support leg/pillow motor."""
        return True

    @property
    def supports_stop_all(self) -> bool:
        """Return False - BedTech beds auto-stop on command release."""
        return False

    def _build_command(self, cmd_char: str) -> bytes:
        """Build command bytes for the given command character."""
        return build_bedtech_command(cmd_char)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to BedTech bed: %s (repeat: %d, delay: %dms)",
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
        # BedTech beds don't support position notifications
        self._notify_callback = callback
        _LOGGER.debug("BedTech beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        return None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        # BedTech beds don't support position reading
        return None

    async def _send_command(self, cmd_char: str, repeat: int | None = None) -> None:
        """Send a command to the bed."""
        command = self._build_command(cmd_char)
        pulse_count = repeat if repeat is not None else self._coordinator.motor_pulse_count
        pulse_delay = self._coordinator.motor_pulse_delay_ms
        await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._send_command(BedTechCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._send_command(BedTechCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor (no-op - BedTech auto-stops)."""
        pass

    async def move_back_up(self) -> None:
        """Move back up (same as head for BedTech)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for BedTech)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for BedTech)."""
        await self._send_command(BedTechCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for BedTech)."""
        await self._send_command(BedTechCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        pass

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._send_command(BedTechCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._send_command(BedTechCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        pass

    async def move_pillow_up(self) -> None:
        """Move pillow/leg up."""
        await self._send_command(BedTechCommands.LEG_UP)

    async def move_pillow_down(self) -> None:
        """Move pillow/leg down."""
        await self._send_command(BedTechCommands.LEG_DOWN)

    async def move_pillow_stop(self) -> None:
        """Stop pillow motor."""
        pass

    async def stop_all(self) -> None:
        """Stop all motors (no-op - BedTech auto-stops)."""
        pass

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(BedTechCommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: BedTechCommands.MEMORY_GO,
            2: BedTechCommands.MEMORY2_GO if self._is_dual_base else BedTechCommands.MEMORY_GO,
        }
        if cmd_char := commands.get(memory_num):
            await self.write_command(self._build_command(cmd_char))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: BedTechCommands.MEMORY_SAVE,
            2: BedTechCommands.MEMORY2_SAVE if self._is_dual_base else BedTechCommands.MEMORY_SAVE,
        }
        if cmd_char := commands.get(memory_num):
            await self.write_command(self._build_command(cmd_char))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command(BedTechCommands.PRESET_ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(BedTechCommands.PRESET_ANTI_SNORE))

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(self._build_command(BedTechCommands.PRESET_TV))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(self._build_command(BedTechCommands.PRESET_LOUNGE))

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self.write_command(self._build_command(BedTechCommands.LIGHT_GO))

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self.write_command(self._build_command(BedTechCommands.LIGHT_OFF))

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(BedTechCommands.LIGHT_TOGGLE))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(self._build_command(BedTechCommands.MASSAGE_ON))

    async def massage_head_toggle(self) -> None:
        """Cycle head massage intensity."""
        await self.write_command(self._build_command(BedTechCommands.HEAD_MASSAGE_UP))

    async def massage_foot_toggle(self) -> None:
        """Cycle foot massage intensity."""
        await self.write_command(self._build_command(BedTechCommands.FOOT_MASSAGE_UP))

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(self._build_command(BedTechCommands.MASSAGE_SWITCH))
