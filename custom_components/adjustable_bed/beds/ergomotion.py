"""Ergomotion bed controller implementation.

Ergomotion beds use the same protocol as Keeson BaseI4/BaseI5:
- 8-byte commands with header [0xE5, 0xFE, 0x16], little-endian 32-bit command, checksum
- Same 32-bit command values for motors, presets, massage, lights

Key differences from Keeson:
- Supports real-time position feedback via BLE notifications
- Massage levels 0-6 (scaled to 0-100%)
- Timer support for massage

Based on protocol analysis from AlexxIT/Ergomotion.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import (
    ERGOMOTION_NOTIFY_CHAR_UUID,
    ERGOMOTION_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class ErgomotionCommands:
    """Ergomotion command constants (32-bit values).

    Same as Keeson commands - the protocol is identical.
    """

    # Presets
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_LOUNGE = 0x2000  # Memory 1
    PRESET_TV = 0x4000  # Memory 2
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
    MASSAGE_WAVE_STEP = 0x10000000

    # Lights
    TOGGLE_LIGHTS = 0x20000


def int_to_bytes_le(value: int) -> list[int]:
    """Convert an integer to 4 bytes (little-endian)."""
    return [
        value & 0xFF,
        (value >> 8) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 24) & 0xFF,
    ]


def crc(data: bytes) -> int:
    """Calculate CRC checksum (inverted sum)."""
    return (~sum(data)) & 0xFF


class ErgomotionController(BedController):
    """Controller for Ergomotion beds with position feedback support."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
    ) -> None:
        """Initialize the Ergomotion controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
        """
        super().__init__(coordinator)
        self._write_char_uuid = ERGOMOTION_WRITE_CHAR_UUID
        self._notify_char_uuid = ERGOMOTION_NOTIFY_CHAR_UUID
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}

        # Position state
        self._head_position: int | None = None
        self._foot_position: int | None = None
        self._head_moving: bool = False
        self._foot_moving: bool = False
        self._head_massage: int = 0
        self._foot_massage: int = 0
        self._led_on: bool = False
        self._timer_mode: str | None = None
        self._timer_remain: int = 0

        _LOGGER.debug(
            "ErgomotionController initialized (write: %s, notify: %s)",
            self._write_char_uuid,
            self._notify_char_uuid,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._write_char_uuid

    def _build_command(self, command_value: int) -> bytes:
        """Build command bytes with checksum.

        Format: [0xE5, 0xFE, 0x16, b0, b1, b2, b3, checksum]
        - Header: 0xE5, 0xFE, 0x16
        - Command: 4-byte little-endian integer
        - Checksum: inverted sum of all previous bytes
        """
        int_bytes = int_to_bytes_le(command_value)
        data = bytes([0xE5, 0xFE, 0x16] + int_bytes)
        checksum = crc(data)
        return data + bytes([checksum])

    def _parse_notification(self, data: bytes) -> None:
        """Parse notification data from the bed.

        Data formats based on header byte:
        - 0xED: 16-byte messages
        - 0xF0: 19-byte messages
        - 0xF1: 20-byte messages
        """
        if len(data) < 1:
            return

        header = data[0]

        if header == 0xED and len(data) >= 16:
            self._parse_ed_message(data)
        elif header == 0xF0 and len(data) >= 19:
            self._parse_f0_message(data)
        elif header == 0xF1 and len(data) >= 20:
            self._parse_f1_message(data)
        else:
            _LOGGER.debug("Unknown notification format: header=0x%02X len=%d", header, len(data))

    def _parse_ed_message(self, data: bytes) -> None:
        """Parse 0xED message (16 bytes) - basic position data."""
        # data1 starts at offset 1
        data1 = data[1:9]

        # Head position: bytes 0-1 (little-endian)
        head_pos = int.from_bytes(data1[0:2], "little")
        if head_pos != 0xFFFF:
            self._head_position = head_pos
        else:
            self._head_position = 0

        # Foot position: bytes 2-3 (little-endian)
        foot_pos = int.from_bytes(data1[2:4], "little")
        if foot_pos != 0xFFFF:
            self._foot_position = foot_pos
        else:
            self._foot_position = 0

        # Massage levels: bytes 4-5 (0-6 scale)
        self._head_massage = data1[4] if len(data1) > 4 else 0
        self._foot_massage = data1[5] if len(data1) > 5 else 0

        # data2 starts at offset 9
        data2 = data[9:16]

        # Movement status: byte 4 (bits indicate which motors are moving)
        if len(data2) > 4:
            move = data2[4] & 0xF
            self._head_moving = move != 0xF and (move & 1) > 0
            self._foot_moving = move != 0xF and (move & 2) > 0

            # LED status: bit 6
            self._led_on = (data2[4] & 0x40) > 0

        # Timer: byte 5
        if len(data2) > 5:
            timer_val = data2[5]
            timer_options = ["10", "20", "30"]
            if 1 <= timer_val <= 3:
                self._timer_mode = timer_options[timer_val - 1]
            else:
                self._timer_mode = None

        self._notify_position_update()

    def _parse_f0_message(self, data: bytes) -> None:
        """Parse 0xF0 message (19 bytes) - extended position data."""
        # Similar structure to 0xED
        data1 = data[1:9]

        head_pos = int.from_bytes(data1[0:2], "little")
        if head_pos != 0xFFFF:
            self._head_position = head_pos
        else:
            self._head_position = 0

        foot_pos = int.from_bytes(data1[2:4], "little")
        if foot_pos != 0xFFFF:
            self._foot_position = foot_pos
        else:
            self._foot_position = 0

        self._head_massage = data1[4] if len(data1) > 4 else 0
        self._foot_massage = data1[5] if len(data1) > 5 else 0

        data2 = data[9:19]
        if len(data2) > 4:
            move = data2[4] & 0xF
            self._head_moving = move != 0xF and (move & 1) > 0
            self._foot_moving = move != 0xF and (move & 2) > 0
            self._led_on = (data2[4] & 0x40) > 0

        self._notify_position_update()

    def _parse_f1_message(self, data: bytes) -> None:
        """Parse 0xF1 message (20 bytes) - full status data."""
        data1 = data[1:9]

        head_pos = int.from_bytes(data1[0:2], "little")
        if head_pos != 0xFFFF:
            self._head_position = head_pos
        else:
            self._head_position = 0

        foot_pos = int.from_bytes(data1[2:4], "little")
        if foot_pos != 0xFFFF:
            self._foot_position = foot_pos
        else:
            self._foot_position = 0

        self._head_massage = data1[4] if len(data1) > 4 else 0
        self._foot_massage = data1[5] if len(data1) > 5 else 0

        data2 = data[9:20]
        if len(data2) > 4:
            # 0xF1 messages use different move flag interpretation
            move = 0xF  # Assume not moving for F1 messages
            self._head_moving = False
            self._foot_moving = False
            self._led_on = (data2[4] & 0x40) > 0

        self._notify_position_update()

    def _notify_position_update(self) -> None:
        """Notify callback with position updates."""
        if self._notify_callback is None:
            return

        # Notify head position (as percentage of max, assuming max ~100)
        if self._head_position is not None:
            self._notify_callback("head", float(self._head_position))

        # Notify foot position
        if self._foot_position is not None:
            self._notify_callback("feet", float(self._foot_position))

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

        effective_cancel = cancel_event or self._coordinator._cancel_command

        _LOGGER.debug(
            "Writing command to Ergomotion bed: %s (repeat: %d, delay: %dms)",
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
                    self._write_char_uuid, command, response=False
                )
            except BleakError as err:
                _LOGGER.error("Failed to write command: %s", err)
                self.log_discovered_services(level=logging.INFO)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started position notifications for Ergomotion bed")
        except BleakError as err:
            _LOGGER.warning("Failed to start notifications: %s", err)

    def _on_notification(self, sender: int, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self._parse_notification(bytes(data))

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
            _LOGGER.debug("Stopped position notifications")
        except BleakError as err:
            _LOGGER.debug("Failed to stop notifications: %s", err)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Ergomotion beds report positions via notifications, not direct reads.
        """
        pass

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command."""
        command = 0
        state = self._motor_state
        if state.get("head") is True:
            command += ErgomotionCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command += ErgomotionCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            command += ErgomotionCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command += ErgomotionCommands.MOTOR_FEET_DOWN
        if state.get("tilt") is True:
            command += ErgomotionCommands.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            command += ErgomotionCommands.MOTOR_TILT_DOWN
        if state.get("lumbar") is True:
            command += ErgomotionCommands.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            command += ErgomotionCommands.MOTOR_LUMBAR_DOWN
        return command

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it."""
        self._motor_state[motor] = direction
        command = self._get_move_command()

        if command:
            await self.write_command(
                self._build_command(command),
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
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
        """Move back up (same as head for Ergomotion)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Ergomotion)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for Ergomotion)."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for Ergomotion)."""
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
            self._build_command(ErgomotionCommands.PRESET_FLAT),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: ErgomotionCommands.PRESET_MEMORY_1,
            2: ErgomotionCommands.PRESET_MEMORY_2,
            3: ErgomotionCommands.PRESET_MEMORY_3,
            4: ErgomotionCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=300,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on Ergomotion)."""
        _LOGGER.warning("Ergomotion beds don't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            self._build_command(ErgomotionCommands.PRESET_ZERO_G),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_lounge(self) -> None:
        """Go to lounge position (Memory 1)."""
        await self.write_command(
            self._build_command(ErgomotionCommands.PRESET_LOUNGE),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_tv(self) -> None:
        """Go to TV position (Memory 2)."""
        await self.write_command(
            self._build_command(ErgomotionCommands.PRESET_TV),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(
            self._build_command(ErgomotionCommands.TOGGLE_LIGHTS)
        )

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage (step through modes)."""
        await self.write_command(self._build_command(ErgomotionCommands.MASSAGE_STEP))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(ErgomotionCommands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(ErgomotionCommands.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(ErgomotionCommands.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(ErgomotionCommands.MASSAGE_FOOT_DOWN))

    async def massage_mode_step(self) -> None:
        """Step through massage timer modes."""
        await self.write_command(
            self._build_command(ErgomotionCommands.MASSAGE_TIMER_STEP)
        )

    async def massage_wave_step(self) -> None:
        """Step through wave massage modes."""
        await self.write_command(
            self._build_command(ErgomotionCommands.MASSAGE_WAVE_STEP)
        )

    # Position feedback properties
    @property
    def head_position(self) -> int | None:
        """Get current head position (0-100)."""
        return self._head_position

    @property
    def foot_position(self) -> int | None:
        """Get current foot position (0-100)."""
        return self._foot_position

    @property
    def head_moving(self) -> bool:
        """Check if head motor is currently moving."""
        return self._head_moving

    @property
    def foot_moving(self) -> bool:
        """Check if foot motor is currently moving."""
        return self._foot_moving

    @property
    def head_massage_level(self) -> int:
        """Get head massage level (0-6)."""
        return self._head_massage

    @property
    def foot_massage_level(self) -> int:
        """Get foot massage level (0-6)."""
        return self._foot_massage

    @property
    def led_on(self) -> bool:
        """Check if LED is on."""
        return self._led_on
