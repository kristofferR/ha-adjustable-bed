"""Okin CB24 protocol bed controller implementation.

Protocol reverse-engineered from SmartBed by Okin app (com.okin.bedding.smartbedwifi).
Source: disassembly/output/com.okin.bedding.smartbedwifi/ANALYSIS.md

This controller handles beds using the CB24 protocol over Nordic UART service.
Known brands using this protocol:
- SmartBed by Okin (Amada, and other OKIN-based beds)
- CB24, CB24AB, CB27, CB27New, CB1221, Dacheng profiles

Detection: Manufacturer ID 89 (OKIN Automotive)

Commands follow the format: [0x05, 0x02, cmd3, cmd2, cmd1, cmd0, bed_selection]
- Bytes 0-1: Length and type (0x05, 0x02)
- Bytes 2-5: 32-bit command in big-endian order
- Byte 6: Bed selection (0x00=default, 0xAA=bed A, 0xBB=bed B)

The 32-bit command values are identical to LeggettOkin protocol.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import NORDIC_UART_WRITE_CHAR_UUID
from .base import BedController
from .okin_protocol import int_to_bytes

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class OkinCB24Commands:
    """Okin CB24 command constants (32-bit values).

    These are the same command values used by LeggettOkin, CB24, and related protocols.
    The CB24 protocol uses a 7-byte format with bed selection byte.
    """

    # Presets
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000  # Also known as Lounge
    PRESET_MEMORY_2 = 0x4000  # Also known as TV/PC
    PRESET_ANTI_SNORE = 0x8000
    PRESET_MEMORY_3 = 0x10000

    # Motor controls
    MOTOR_HEAD_UP = 0x1
    MOTOR_HEAD_DOWN = 0x2
    MOTOR_FEET_UP = 0x4
    MOTOR_FEET_DOWN = 0x8
    MOTOR_BOTH_UP = 0x5  # HEAD_UP + FEET_UP
    MOTOR_BOTH_DOWN = 0xA  # HEAD_DOWN + FEET_DOWN
    MOTOR_TILT_UP = 0x10
    MOTOR_TILT_DOWN = 0x20
    MOTOR_WAIST_UP = 0x40
    MOTOR_WAIST_DOWN = 0x80

    # Lights
    TOGGLE_LIGHTS = 0x20000

    # Stretch/other
    STRETCH_MOVE = 0x40000

    # Massage - intensity control (up = increase, minus = decrease)
    MASSAGE_HEAD_UP = 0x800  # Increase head massage intensity
    MASSAGE_HEAD_DOWN = 0x800000  # Decrease head massage intensity
    MASSAGE_FEET_UP = 0x400  # Increase foot massage intensity
    MASSAGE_FEET_DOWN = 0x1000000  # Decrease foot massage intensity
    MASSAGE_WAIST_UP = 0x400000  # Increase waist massage intensity
    MASSAGE_WAIST_DOWN = 0x10000000  # Decrease waist massage intensity

    # Massage - global controls
    MASSAGE_ALL_TOGGLE = 0x100  # Toggle all massage zones
    MASSAGE_ON_OFF = 0x4000000  # Master massage on/off toggle
    MASSAGE_STOP_ALL = 0x2000000  # Stop all massage

    # Massage - mode and timer
    MASSAGE_WAVE_STEP = 0x10000000  # Cycle through wave patterns
    MASSAGE_TIMER_UP = 0x200  # Increase massage timer
    MASSAGE_TIMER_DOWN = 0x100000  # Decrease massage timer

    # Massage - intensity levels (direct set)
    MASSAGE_INTENSITY_UP = 0xC00  # Increase overall intensity
    MASSAGE_INTENSITY_DOWN = 0x1800000  # Decrease overall intensity


class MotorDirection(Enum):
    """Direction for motor movement."""

    UP = "up"
    DOWN = "down"
    STOP = "stop"


def build_cb24_command(command_value: int, bed_selection: int = 0x00) -> bytes:
    """Build a 7-byte CB24 protocol command.

    Args:
        command_value: 32-bit integer representing the command
        bed_selection: Bed selection byte (0x00=default, 0xAA=bed A, 0xBB=bed B)

    Returns:
        7-byte command: [0x05, 0x02, cmd3, cmd2, cmd1, cmd0, bed_selection]
    """
    return bytes([0x05, 0x02, *int_to_bytes(command_value), bed_selection])


class OkinCB24Controller(BedController):
    """Controller for beds using Okin CB24 protocol over Nordic UART.

    Protocol discovered from SmartBed by Okin app analysis.
    Uses 7-byte commands with 32-bit command values.
    Supports dual-bed configurations via bed selection byte.
    """

    # CB24 memory/preset actions in the OEM app run as hold-to-run commands
    # with a 300ms resend cadence. We approximate that with a long burst that
    # can still be preempted by later commands (e.g. massage/stop).
    PRESET_REPEAT_COUNT = 83
    PRESET_REPEAT_DELAY_MS = 300

    def __init__(
        self, coordinator: AdjustableBedCoordinator, bed_selection: int = 0x00
    ) -> None:
        """Initialize the Okin CB24 controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            bed_selection: Bed selection (0x00=default, 0xAA=bed A, 0xBB=bed B)
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, MotorDirection] = {}
        self._bed_selection = bed_selection
        _LOGGER.debug(
            "OkinCB24Controller initialized (bed_selection=%#x)", bed_selection
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return NORDIC_UART_WRITE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True - CB24 beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - CB24 only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - CB24 beds support memory presets 1-3."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 3 - CB24 beds support memory slots 1-3."""
        return 3

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - CB24 beds don't support programming memory positions."""
        return False

    @property
    def supports_preset_lounge(self) -> bool:
        """Return True - Memory 1 is often Lounge position."""
        return True

    @property
    def supports_preset_tv(self) -> bool:
        """Return True - Memory 2 is often TV/PC position."""
        return True

    @property
    def supports_massage(self) -> bool:
        """Return True - CB24 beds support massage functions."""
        return True

    def _build_command(self, command_value: int) -> bytes:
        """Build CB24 binary command.

        Args:
            command_value: 32-bit command value (0 to 0xFFFFFFFF)

        Returns:
            7-byte command: [0x05, 0x02, <4-byte-command-big-endian>, bed_selection]
        """
        return build_cb24_command(command_value, self._bed_selection)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Okin CB24 bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            NORDIC_UART_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Okin CB24 beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        _ = motor_count  # Unused - this bed doesn't support position feedback

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command."""
        command = 0
        state = self._motor_state
        if state.get("head") == MotorDirection.UP:
            command += OkinCB24Commands.MOTOR_HEAD_UP
        elif state.get("head") == MotorDirection.DOWN:
            command += OkinCB24Commands.MOTOR_HEAD_DOWN
        if state.get("feet") == MotorDirection.UP:
            command += OkinCB24Commands.MOTOR_FEET_UP
        elif state.get("feet") == MotorDirection.DOWN:
            command += OkinCB24Commands.MOTOR_FEET_DOWN
        return command

    async def _move_motor(self, motor: str, direction: MotorDirection) -> None:
        """Move a motor in a direction or stop it."""
        if direction == MotorDirection.STOP:
            self._motor_state.pop(motor, None)
        else:
            self._motor_state[motor] = direction
        command = self._get_move_command()

        try:
            if command:
                pulse_count = self._coordinator.motor_pulse_count
                pulse_delay = self._coordinator.motor_pulse_delay_ms
                await self.write_command(
                    self._build_command(command),
                    repeat_count=pulse_count,
                    repeat_delay_ms=pulse_delay,
                )
        finally:
            self._motor_state = {}
            # Shield the STOP command to ensure it runs even if cancelled
            try:
                await asyncio.shield(
                    self.write_command(
                        self._build_command(0),
                        cancel_event=asyncio.Event(),
                    )
                )
            except asyncio.CancelledError:
                raise
            except BleakError:
                _LOGGER.debug("Failed to send stop command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor("head", MotorDirection.UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor("head", MotorDirection.DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._move_motor("head", MotorDirection.STOP)

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
        await self._move_motor("feet", MotorDirection.UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor("feet", MotorDirection.DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", MotorDirection.STOP)

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
        self._motor_state = {}
        await self.write_command(
            self._build_command(0),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def _send_preset(self, command_value: int) -> None:
        """Send a preset command in an interruptible hold-style burst.

        CB24 presets behave like hold-to-run commands, so we resend at 300ms
        intervals and do NOT send STOP afterwards.
        """
        await self.write_command(
            self._build_command(command_value),
            repeat_count=self.PRESET_REPEAT_COUNT,
            repeat_delay_ms=self.PRESET_REPEAT_DELAY_MS,
        )

    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_preset(OkinCB24Commands.PRESET_FLAT)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: OkinCB24Commands.PRESET_MEMORY_1,
            2: OkinCB24Commands.PRESET_MEMORY_2,
            3: OkinCB24Commands.PRESET_MEMORY_3,
        }
        if command := commands.get(memory_num):
            await self._send_preset(command)
        else:
            _LOGGER.warning("Memory slot %d not supported (valid: 1-3)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on CB24)."""
        _LOGGER.warning(
            "CB24 beds don't support programming memory presets (requested slot: %d)",
            memory_num,
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._send_preset(OkinCB24Commands.PRESET_ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._send_preset(OkinCB24Commands.PRESET_ANTI_SNORE)

    async def preset_lounge(self) -> None:
        """Go to lounge position (Memory 1)."""
        await self._send_preset(OkinCB24Commands.PRESET_MEMORY_1)

    async def preset_tv(self) -> None:
        """Go to TV/PC position (Memory 2)."""
        await self._send_preset(OkinCB24Commands.PRESET_MEMORY_2)

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(OkinCB24Commands.TOGGLE_LIGHTS))

    async def lights_on(self) -> None:
        """Turn on lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    # Massage methods
    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_HEAD_DOWN))

    async def massage_head_toggle(self) -> None:
        """Toggle head massage (via intensity up)."""
        await self.massage_head_up()

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_FEET_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_FEET_DOWN))

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage (via intensity up)."""
        await self.massage_foot_up()

    async def massage_toggle(self) -> None:
        """Toggle all massage zones."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_ALL_TOGGLE))

    async def massage_intensity_up(self) -> None:
        """Increase all massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_INTENSITY_UP))

    async def massage_intensity_down(self) -> None:
        """Decrease all massage intensity."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_INTENSITY_DOWN))

    async def massage_off(self) -> None:
        """Turn off all massage."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_STOP_ALL))

    async def massage_mode_step(self) -> None:
        """Cycle through massage wave patterns."""
        await self.write_command(self._build_command(OkinCB24Commands.MASSAGE_WAVE_STEP))
