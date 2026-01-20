"""Leggett & Platt Okin variant bed controller implementation.

Reverse engineering by MarcusW and Richard Hopton (smartbed-mqtt).

This controller handles Leggett & Platt beds using the Okin binary protocol.

Protocol details:
    Service UUID: 62741523-52f9-8864-b1ab-3b3a8d65950b (shared with Okimat/Nectar)
    Write characteristic: 62741525-52f9-8864-b1ab-3b3a8d65950b
    Command format: 6-byte binary [0x04, 0x02, <4-byte-command-big-endian>]
    Motor timing: 25 pulses at 200ms intervals for continuous movement
    Position feedback: Not supported
    Pairing: Required before first use; handled by coordinator

Note: This shares the same BLE service UUID with Okimat and Nectar beds.
Detection uses device name patterns ("leggett", "l&p") to distinguish between these
bed types. See okin_protocol.py for the shared binary protocol specification.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import LEGGETT_OKIN_CHAR_UUID
from .base import BedController
from .okin_protocol import build_okin_command

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class LeggettOkinCommands:
    """Leggett & Platt Okin command constants (32-bit values).

    Same as Keeson/Okimat since they share the Okin protocol.
    """

    # Presets
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000
    PRESET_MEMORY_2 = 0x4000
    PRESET_MEMORY_3 = 0x8000
    PRESET_MEMORY_4 = 0x10000

    # Motor controls
    MOTOR_HEAD_UP = 0x1
    MOTOR_HEAD_DOWN = 0x2
    MOTOR_FEET_UP = 0x4
    MOTOR_FEET_DOWN = 0x8
    MOTOR_TILT_UP = 0x10
    MOTOR_TILT_DOWN = 0x20
    MOTOR_LUMBAR_UP = 0x40
    MOTOR_LUMBAR_DOWN = 0x80

    # Massage
    MASSAGE_HEAD_UP = 0x800
    MASSAGE_HEAD_DOWN = 0x800000
    MASSAGE_FOOT_UP = 0x400
    MASSAGE_FOOT_DOWN = 0x1000000
    MASSAGE_STEP = 0x100

    # Lights
    TOGGLE_LIGHTS = 0x20000


class LeggettOkinController(BedController):
    """Controller for Leggett & Platt beds using Okin protocol.

    These beds use the binary Okin protocol and require BLE pairing.
    They support motor control, presets, massage, and under-bed lighting.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Leggett & Platt Okin controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}
        _LOGGER.debug("LeggettOkinController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LEGGETT_OKIN_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False  # Okin variant doesn't support Anti-Snore

    @property
    def supports_lights(self) -> bool:
        """Return True - Okin beds support under-bed lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - Okin only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Okin beds support memory presets 1-4."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Okin beds support memory slots 1-4."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - Okin beds don't support programming memory positions."""
        return False

    def _build_command(self, command_value: int) -> bytes:
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
            "Writing command to Leggett & Platt Okin bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            LEGGETT_OKIN_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Leggett & Platt Okin beds don't support position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command."""
        command = 0
        state = self._motor_state
        if state.get("head") is True:
            command += LeggettOkinCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command += LeggettOkinCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            command += LeggettOkinCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command += LeggettOkinCommands.MOTOR_FEET_DOWN
        return command

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it."""
        self._motor_state[motor] = direction
        command = self._get_move_command()

        try:
            if command:
                await self.write_command(
                    self._build_command(command),
                    repeat_count=25,
                    repeat_delay_ms=200,
                )
        finally:
            self._motor_state = {}
            # Wrap in try-except to prevent masking the original exception
            try:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send stop command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor("head", True)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor("head", False)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._move_motor("head", None)

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
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor("feet", False)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", None)

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
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.PRESET_FLAT),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LeggettOkinCommands.PRESET_MEMORY_1,
            2: LeggettOkinCommands.PRESET_MEMORY_2,
            3: LeggettOkinCommands.PRESET_MEMORY_3,
            4: LeggettOkinCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=300,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on Okin)."""
        _LOGGER.warning("Okin beds don't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.PRESET_ZERO_G),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (not supported on Okin)."""
        _LOGGER.warning("Anti-snore preset not available on Okin beds")

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.TOGGLE_LIGHTS)
        )

    async def lights_on(self) -> None:
        """Turn on lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        # No direct off command, step through modes
        pass

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.MASSAGE_HEAD_UP)
        )

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.MASSAGE_HEAD_DOWN)
        )

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.MASSAGE_FOOT_UP)
        )

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.MASSAGE_FOOT_DOWN)
        )

    async def massage_toggle(self) -> None:
        """Toggle massage / step through modes."""
        await self.write_command(
            self._build_command(LeggettOkinCommands.MASSAGE_STEP)
        )


# Backwards compatibility aliases
LeggettPlattOkinCommands = LeggettOkinCommands
