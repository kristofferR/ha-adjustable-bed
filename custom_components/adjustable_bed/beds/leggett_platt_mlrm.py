"""Leggett & Platt MlRM variant bed controller implementation.

This is the "mlrm" variant of the Leggett & Platt bed controller, for beds that use
Richmat WiLinke BLE hardware. These beds advertise with "MlRM*" name prefix.

Key difference from standard Richmat: This controller has discrete massage UP/DOWN
commands (0x4c/0x4d for head, 0x4e/0x4f for foot) rather than just cycling "step" commands.

Command format: [0x6e, 0x01, 0x00, command_byte, checksum]
Where checksum = sum of first 4 bytes (truncated to 8 bits)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import LEGGETT_RICHMAT_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class LeggettPlattMlrmCommands:
    """Command constants for Leggett & Platt MlRM beds.

    These were reverse-engineered from the LP Adjustable Bed Control app.
    Commands are the last byte of a 5-byte WiLinke packet.
    """

    # Presets
    PRESET_FLAT = 0x31
    PRESET_ANTI_SNORE = 0x46
    PRESET_LOUNGE = 0x59
    PRESET_MEMORY_1 = 0x2E
    PRESET_MEMORY_2 = 0x2F
    PRESET_TV = 0x58
    PRESET_ZERO_G = 0x45

    # Program presets
    PROGRAM_ANTI_SNORE = 0x69
    PROGRAM_LOUNGE = 0x65
    PROGRAM_MEMORY_1 = 0x2B
    PROGRAM_MEMORY_2 = 0x2C
    PROGRAM_TV = 0x64
    PROGRAM_ZERO_G = 0x66

    # Massage - discrete UP/DOWN commands (from LP app decompilation)
    MASSAGE_HEAD_UP = 0x4C      # Increase head massage intensity
    MASSAGE_HEAD_DOWN = 0x4D    # Decrease head massage intensity
    MASSAGE_FOOT_UP = 0x4E      # Increase foot massage intensity
    MASSAGE_FOOT_DOWN = 0x4F    # Decrease foot massage intensity
    MASSAGE_MOTOR_STOP = 0x47   # Stop massage motors

    # Massage - additional commands
    MASSAGE_MOTOR1_ON_OFF = 0x32  # Toggle head massage
    MASSAGE_MOTOR2_ON_OFF = 0x33  # Toggle foot massage
    MASSAGE_INCREASE_INTENSITY = 0x34  # Overall intensity up
    MASSAGE_DECREASE_INTENSITY = 0x35  # Overall intensity down
    MASSAGE_INCREASE_SPEED = 0x36
    MASSAGE_DECREASE_SPEED = 0x37
    MASSAGE_PATTERN_STEP = 0x38  # Cycle massage patterns
    MASSAGE_WAVE = 0x39          # Wave massage mode
    MASSAGE_ALWAYS_ON = 0x3A

    # Massage timers
    MASSAGE_TIMER_10M = 0x5F
    MASSAGE_TIMER_20M = 0x63
    MASSAGE_TIMER_30M = 0x61

    # Lights
    LIGHTS_TOGGLE = 0x3C

    # Motors
    MOTOR_PILLOW_UP = 0x3F
    MOTOR_PILLOW_DOWN = 0x40
    MOTOR_HEAD_UP = 0x24
    MOTOR_HEAD_DOWN = 0x25
    MOTOR_FEET_UP = 0x26
    MOTOR_FEET_DOWN = 0x27
    MOTOR_LUMBAR_UP = 0x41
    MOTOR_LUMBAR_DOWN = 0x42

    # End/Stop
    END = 0x6E


class LeggettPlattMlrmController(BedController):
    """Controller for Leggett & Platt MlRM variant beds (WiLinke hardware)."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        char_uuid: str | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            char_uuid: The characteristic UUID to use for writing commands
        """
        super().__init__(coordinator)
        self._char_uuid = char_uuid or LEGGETT_RICHMAT_CHAR_UUID
        self._notify_callback: Callable[[str, float], None] | None = None

        _LOGGER.debug(
            "LeggettPlattMlrmController initialized (variant: mlrm, char: %s)",
            self._char_uuid,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

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
    def has_lumbar_support(self) -> bool:
        return False  # Most L&P MlRM beds don't have lumbar

    @property
    def has_pillow_support(self) -> bool:
        return False  # Most L&P MlRM beds don't have pillow tilt

    @property
    def supports_lights(self) -> bool:
        """Return True if this bed supports under-bed lights."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - supports memory presets."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 2 - supports Memory 1 and Memory 2."""
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - supports programming memory positions."""
        return True

    @property
    def has_discrete_motor_control(self) -> bool:
        """Return True - this bed uses discrete motor commands."""
        return True

    def _build_command(self, command_byte: int) -> bytes:
        """Build WiLinke 5-byte command with checksum.

        Format: [0x6e, 0x01, 0x00, command, checksum]
        Checksum = (0x6e + 0x01 + 0x00 + command) & 0xFF = (command + 0x6F) & 0xFF
        """
        checksum = (0x6E + 0x01 + 0x00 + command_byte) & 0xFF
        return bytes([0x6E, 0x01, 0x00, command_byte, checksum])

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
            "Writing command to L&P MlRM bed: %s (repeat: %d, delay: %dms)",
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
            except BleakError as err:
                _LOGGER.exception("Failed to write command")
                if "not found" in str(err).lower() or "invalid" in str(err).lower():
                    _LOGGER.warning(
                        "Characteristic %s may not exist on this device.",
                        self._char_uuid,
                    )
                    self.log_discovered_services(level=logging.INFO)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("L&P MlRM beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""

    async def _send_command(self, command_byte: int, repeat: int | None = None) -> None:
        """Send a command to the bed."""
        command = self._build_command(command_byte)
        pulse_count = repeat if repeat is not None else self._coordinator.motor_pulse_count
        pulse_delay = self._coordinator.motor_pulse_delay_ms
        await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)

    async def _move_with_stop(self, command_byte: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self._send_command(command_byte)
        finally:
            try:
                await self.write_command(
                    self._build_command(LeggettPlattMlrmCommands.END),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send END command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(LeggettPlattMlrmCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(LeggettPlattMlrmCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            self._build_command(LeggettPlattMlrmCommands.END),
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
        await self._move_with_stop(LeggettPlattMlrmCommands.MOTOR_FEET_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(LeggettPlattMlrmCommands.MOTOR_FEET_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(LeggettPlattMlrmCommands.MOTOR_FEET_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(LeggettPlattMlrmCommands.MOTOR_FEET_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            self._build_command(LeggettPlattMlrmCommands.END),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LeggettPlattMlrmCommands.PRESET_MEMORY_1,
            2: LeggettPlattMlrmCommands.PRESET_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: LeggettPlattMlrmCommands.PROGRAM_MEMORY_1,
            2: LeggettPlattMlrmCommands.PROGRAM_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))
        else:
            _LOGGER.warning("Invalid memory number %d (valid: 1-2)", memory_num)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.PRESET_ZERO_G))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.PRESET_ANTI_SNORE))

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.PRESET_TV))

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.PRESET_LOUNGE))

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.LIGHTS_TOGGLE))

    async def lights_on(self) -> None:
        """Turn on under-bed lights (toggle-only)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off under-bed lights (toggle-only)."""
        await self.lights_toggle()

    # Massage methods - DISCRETE UP/DOWN (the key feature of this controller!)
    async def massage_off(self) -> None:
        """Turn off all massage."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_MOTOR_STOP))

    async def massage_toggle(self) -> None:
        """Toggle massage (head motor)."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_MOTOR1_ON_OFF))

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_MOTOR1_ON_OFF))

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_MOTOR2_ON_OFF))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_FOOT_DOWN))

    async def massage_intensity_up(self) -> None:
        """Increase overall massage intensity."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_INCREASE_INTENSITY))

    async def massage_intensity_down(self) -> None:
        """Decrease overall massage intensity."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_DECREASE_INTENSITY))

    async def massage_mode_step(self) -> None:
        """Step through massage patterns."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_PATTERN_STEP))

    async def massage_wave_toggle(self) -> None:
        """Toggle wave massage mode."""
        await self.write_command(self._build_command(LeggettPlattMlrmCommands.MASSAGE_WAVE))
