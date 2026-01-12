"""Okimat bed controller implementation.

Okimat beds use the Okin protocol with 6-byte commands: [0x04, 0x02, ...int_to_bytes(command)]
They require BLE pairing before use.

Note: Okimat shares the same BLE UUIDs and protocol as Leggett & Platt Okin variant.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import OKIMAT_WRITE_CHAR_UUID
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


class OkimatCommands:
    """Okimat command constants (32-bit values)."""

    # Presets (same as Keeson/Okin protocol)
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000
    PRESET_MEMORY_2 = 0x4000
    PRESET_MEMORY_3 = 0x8000
    PRESET_MEMORY_4 = 0x10000

    # Motors
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
    MASSAGE_TIMER_STEP = 0x200

    # Lights
    TOGGLE_LIGHTS = 0x20000


class OkimatController(BedController):
    """Controller for Okimat beds.

    Note: Okimat beds require BLE pairing before they can be controlled.
    The pairing must be done through the coordinator during connection.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Okimat controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}
        _LOGGER.debug("OkimatController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OKIMAT_WRITE_CHAR_UUID

    def _build_command(self, command_value: int) -> bytes:
        """Build command bytes: [0x04, 0x02, ...int_to_bytes(command)]."""
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
            "Writing command to Okimat bed: %s (repeat: %d, delay: %dms)",
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
                    OKIMAT_WRITE_CHAR_UUID, command, response=False
                )
            except BleakError as err:
                _LOGGER.error("Failed to write command: %s", err)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Okimat beds don't support position notifications")

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
            command += OkimatCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command += OkimatCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            command += OkimatCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command += OkimatCommands.MOTOR_FEET_DOWN
        if state.get("tilt") is True:
            command += OkimatCommands.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            command += OkimatCommands.MOTOR_TILT_DOWN
        if state.get("lumbar") is True:
            command += OkimatCommands.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            command += OkimatCommands.MOTOR_LUMBAR_DOWN
        return command

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it."""
        self._motor_state[motor] = direction
        command = self._get_move_command()

        if command:
            await self.write_command(
                self._build_command(command),
                repeat_count=25,
                repeat_delay_ms=200,
            )
        # Send stop (zero command)
        self._motor_state = {}
        await self.write_command(
            self._build_command(0),
            cancel_event=asyncio.Event(),
        )

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
        """Move legs up (same as feet)."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self._move_motor("feet", False)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", None)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor("feet", True)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor("feet", False)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._move_motor("feet", None)

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
            self._build_command(OkimatCommands.PRESET_FLAT),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: OkimatCommands.PRESET_MEMORY_1,
            2: OkimatCommands.PRESET_MEMORY_2,
            3: OkimatCommands.PRESET_MEMORY_3,
            4: OkimatCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=300,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("Okimat beds don't support programming memory presets via BLE")

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(OkimatCommands.TOGGLE_LIGHTS))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(self._build_command(OkimatCommands.MASSAGE_STEP))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(OkimatCommands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(OkimatCommands.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(OkimatCommands.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(OkimatCommands.MASSAGE_FOOT_DOWN))

    async def massage_mode_step(self) -> None:
        """Step through massage modes/timer."""
        await self.write_command(self._build_command(OkimatCommands.MASSAGE_TIMER_STEP))
