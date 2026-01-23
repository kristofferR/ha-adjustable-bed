"""OKIN 64-bit bed controller implementation.

OKIN 64-bit beds use a 10-byte command protocol:
- Format: [0x08, 0x02, cmd[0], cmd[1], cmd[2], cmd[3], cmd[4], cmd[5], cmd[6], cmd[7]]
- Commands are 64-bit bitmask values (8 bytes)
- No checksum required

Two protocol variants use the same command format:
- Protocol 25_42_02: Nordic UART service, fire-and-forget (withoutResponse=True)
- Protocol 36_33_04a: Custom OKIN service, wait-for-response (withoutResponse=False)

Protocol reverse-engineered from com.okin.bedding.adjustbed app (Flutter/Dart).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import (
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


# Protocol variants
OKIN_64BIT_VARIANT_NORDIC = "nordic"  # Protocol 25_42_02 - Nordic UART, fire-and-forget
OKIN_64BIT_VARIANT_CUSTOM = "custom"  # Protocol 36_33_04a - Custom OKIN, wait-for-response


class Okin64BitCommands:
    """OKIN 64-bit command values (8-byte arrays)."""

    # Motor commands
    STOP = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    HEAD_UP = bytes([0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
    HEAD_DOWN = bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00])
    FOOT_UP = bytes([0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00])
    FOOT_DOWN = bytes([0x00, 0x00, 0x00, 0x08, 0x00, 0x00, 0x00, 0x00])
    LUMBAR_UP = bytes([0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00])
    LUMBAR_DOWN = bytes([0x00, 0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00])

    # Presets
    FLAT = bytes([0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    ZERO_G = bytes([0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00])
    LOUNGE = bytes([0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00])
    TV_PC = bytes([0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00])
    ANTI_SNORE = bytes([0x00, 0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00])
    MEMORY_1 = bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    MEMORY_2 = bytes([0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    # Set memory (combined with FLAT bit for programming)
    SET_ZERO_G = bytes([0x08, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00])
    SET_LOUNGE = bytes([0x08, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00])
    SET_TV_PC = bytes([0x08, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00])
    SET_ANTI_SNORE = bytes([0x08, 0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00])

    # Massage
    MASSAGE_SWITCH = bytes([0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
    MASSAGE_STOP = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    MASSAGE_TIMER = bytes([0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
    STRENGTH_UP = bytes([0x00, 0x00, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00])
    STRENGTH_DOWN = bytes([0x01, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    WAVE_MODE = bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    WAVE_1 = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x00, 0x00])
    WAVE_2 = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00])
    WAVE_3 = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x20, 0x00, 0x00])

    # Light
    LIGHT_TOGGLE = bytes([0x00, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    LIGHT_ON = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40])
    LIGHT_OFF = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80])


def build_okin_64bit_command(cmd_bytes: bytes) -> bytes:
    """Build a 10-byte OKIN 64-bit command packet.

    Args:
        cmd_bytes: 8-byte command value

    Returns:
        10-byte command packet: [0x08, 0x02, cmd[0], ..., cmd[7]]
    """
    if len(cmd_bytes) != 8:
        raise ValueError(f"Command must be 8 bytes, got {len(cmd_bytes)}")
    return bytes([0x08, 0x02]) + cmd_bytes


class Okin64BitController(BedController):
    """Controller for OKIN 64-bit beds.

    Supports two protocol variants:
    - Nordic (Protocol 25_42_02): Nordic UART service, fire-and-forget
    - Custom (Protocol 36_33_04a): Custom OKIN service, wait-for-response
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = OKIN_64BIT_VARIANT_NORDIC,
        char_uuid: str | None = None,
    ) -> None:
        """Initialize the OKIN 64-bit controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            variant: Protocol variant ('nordic' or 'custom')
            char_uuid: Optional override for characteristic UUID
        """
        super().__init__(coordinator)
        self._variant = variant
        self._notify_callback: Callable[[str, float], None] | None = None

        # Determine characteristic UUID based on variant
        if char_uuid:
            self._char_uuid = char_uuid
        elif variant == OKIN_64BIT_VARIANT_CUSTOM:
            self._char_uuid = OKIMAT_WRITE_CHAR_UUID
        else:
            self._char_uuid = NORDIC_UART_WRITE_CHAR_UUID

        # Determine write response mode based on variant
        self._use_response = variant == OKIN_64BIT_VARIANT_CUSTOM

        _LOGGER.debug(
            "Okin64BitController initialized (variant: %s, char: %s, response: %s)",
            variant,
            self._char_uuid,
            self._use_response,
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
        """Return False - memory programming uses set commands at preset positions."""
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - OKIN 64-bit supports discrete on/off control."""
        return True

    @property
    def has_lumbar_support(self) -> bool:
        """Return True - OKIN 64-bit beds support lumbar motor."""
        return True

    @property
    def supports_stop_all(self) -> bool:
        """Return True - OKIN 64-bit supports explicit stop command."""
        return True

    def _build_command(self, cmd_bytes: bytes) -> bytes:
        """Build command bytes for the given command value."""
        return build_okin_64bit_command(cmd_bytes)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to OKIN 64-bit bed: %s (repeat: %d, delay: %dms, response: %s)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
            self._use_response,
        )
        await self._write_gatt_with_retry(
            self._char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._use_response,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        # OKIN 64-bit beds don't support position notifications
        self._notify_callback = callback
        _LOGGER.debug("OKIN 64-bit beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        return None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        # OKIN 64-bit beds don't support position reading
        return None

    async def _send_command(self, cmd_bytes: bytes, repeat: int | None = None) -> None:
        """Send a command to the bed."""
        command = self._build_command(cmd_bytes)
        pulse_count = repeat if repeat is not None else self._coordinator.motor_pulse_count
        pulse_delay = self._coordinator.motor_pulse_delay_ms
        await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)

    async def _move_with_stop(self, cmd_bytes: bytes) -> None:
        """Execute a movement command and send STOP at the end."""
        try:
            await self._send_command(cmd_bytes)
        finally:
            try:
                await self.write_command(
                    self._build_command(Okin64BitCommands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(Okin64BitCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(Okin64BitCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            self._build_command(Okin64BitCommands.STOP),
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head for OKIN 64-bit)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for OKIN 64-bit)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for OKIN 64-bit)."""
        await self._move_with_stop(Okin64BitCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for OKIN 64-bit)."""
        await self._move_with_stop(Okin64BitCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(Okin64BitCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(Okin64BitCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(Okin64BitCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(Okin64BitCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            self._build_command(Okin64BitCommands.STOP),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(Okin64BitCommands.FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: Okin64BitCommands.MEMORY_1,
            2: Okin64BitCommands.MEMORY_2,
        }
        if cmd_bytes := commands.get(memory_num):
            await self.write_command(self._build_command(cmd_bytes))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:  # noqa: ARG002
        """Program current position to memory (not supported - use set commands)."""
        _LOGGER.warning(
            "OKIN 64-bit beds don't support programming memory presets directly. "
            "Memory positions are programmed by sending set commands at the desired position."
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command(Okin64BitCommands.ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(Okin64BitCommands.ANTI_SNORE))

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(self._build_command(Okin64BitCommands.TV_PC))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(self._build_command(Okin64BitCommands.LOUNGE))

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self.write_command(self._build_command(Okin64BitCommands.LIGHT_ON))

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self.write_command(self._build_command(Okin64BitCommands.LIGHT_OFF))

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(Okin64BitCommands.LIGHT_TOGGLE))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage on/off."""
        await self.write_command(self._build_command(Okin64BitCommands.MASSAGE_SWITCH))

    async def massage_head_up(self) -> None:
        """Increase massage intensity."""
        await self.write_command(self._build_command(Okin64BitCommands.STRENGTH_UP))

    async def massage_head_down(self) -> None:
        """Decrease massage intensity."""
        await self.write_command(self._build_command(Okin64BitCommands.STRENGTH_DOWN))

    async def massage_mode_step(self) -> None:
        """Step through massage wave modes."""
        await self.write_command(self._build_command(Okin64BitCommands.WAVE_MODE))
