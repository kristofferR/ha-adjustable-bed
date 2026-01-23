"""Reverie bed controller implementation.

Reverse engineering by Vitaliy and Richard Hopton (smartbed-mqtt).

Reverie beds use a protocol with XOR checksum:
Command format: [0x55, ...bytes, XOR_checksum]
where checksum = bytes XOR'd together XOR 0x55

Reverie supports position-based motor control (0-100%).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from bleak.exc import BleakError

from ..const import REVERIE_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class ReverieCommands:
    """Reverie command constants."""

    # Presets
    PRESET_ZERO_G: ClassVar[list[int]] = [0x15]
    PRESET_ANTI_SNORE: ClassVar[list[int]] = [0x16]
    PRESET_FLAT: ClassVar[list[int]] = [0x05]
    PRESET_MEMORY_1: ClassVar[list[int]] = [0x11]
    PRESET_MEMORY_2: ClassVar[list[int]] = [0x12]
    PRESET_MEMORY_3: ClassVar[list[int]] = [0x13]
    PRESET_MEMORY_4: ClassVar[list[int]] = [0x14]

    # Programming
    PROGRAM_MEMORY_1: ClassVar[list[int]] = [0x21]
    PROGRAM_MEMORY_2: ClassVar[list[int]] = [0x22]
    PROGRAM_MEMORY_3: ClassVar[list[int]] = [0x23]
    PROGRAM_MEMORY_4: ClassVar[list[int]] = [0x24]

    # Lighting
    LIGHTS_TOGGLE: ClassVar[list[int]] = [0x5B, 0x00]

    # Motor stop
    MOTOR_STOP: ClassVar[list[int]] = [0xFF]

    @staticmethod
    def massage_head(level: int) -> list[int]:
        """Create head massage command with level (0-10)."""
        return [0x53, level]

    @staticmethod
    def massage_foot(level: int) -> list[int]:
        """Create foot massage command with level (0-10)."""
        return [0x54, level]

    @staticmethod
    def massage_wave(level: int) -> list[int]:
        """Create wave massage command with level (0-10)."""
        return [0x40 + level]

    @staticmethod
    def motor_head(position: int) -> list[int]:
        """Move head motor to position (0-100)."""
        return [0x51, position]

    @staticmethod
    def motor_feet(position: int) -> list[int]:
        """Move feet motor to position (0-100)."""
        return [0x52, position]


class ReverieController(BedController):
    """Controller for Reverie beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Reverie controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._massage_head_level = 0
        self._massage_foot_level = 0
        self._massage_wave_level = 0
        _LOGGER.debug("ReverieController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return REVERIE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Reverie beds support memory presets (slots 1-4)."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Reverie beds support memory slots 1-4."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Reverie beds support programming memory positions."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - Reverie only supports toggle, not discrete on/off."""
        return False

    @property
    def supports_direct_position_control(self) -> bool:
        """Return True - Reverie beds support direct position commands."""
        return True

    # Massage intensity control - Reverie supports direct level setting (0-10)
    @property
    def supports_massage_intensity_control(self) -> bool:
        """Return True - Reverie supports setting massage intensity directly."""
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        """Return zones with direct intensity control: head, foot, wave."""
        return ["head", "foot", "wave"]

    @property
    def massage_intensity_max(self) -> int:
        """Return 10 - Reverie uses 0-10 intensity scale."""
        return 10

    def angle_to_native_position(self, motor: str, angle: float) -> int:
        """Convert angle to Reverie's native 0-100 position.

        Reverses the angle conversion from _parse_position_data:
        - back: angle = position * 0.6, so position = angle / 0.6
        - legs: angle = position * 0.45, so position = angle / 0.45
        """
        if motor in ("head", "back"):
            position = angle / 0.6
        elif motor in ("feet", "legs"):
            position = angle / 0.45
        else:
            position = angle  # Fallback: assume 1:1

        # Clamp to valid range
        return max(0, min(100, int(round(position))))

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Set a motor to a specific position (0-100).

        Reverie supports direct position control via motor_head/motor_feet commands.
        This is more efficient than incremental seeking for position number entities.

        Args:
            motor: Motor name ("head", "back", "legs", "feet")
            position: Target position as percentage (0=flat, 100=max)
        """
        # Normalize motor names: back->head, legs->feet for Reverie
        if motor in ("head", "back"):
            cmd = ReverieCommands.motor_head(position)
        elif motor in ("feet", "legs"):
            cmd = ReverieCommands.motor_feet(position)
        else:
            _LOGGER.warning("Unknown motor %s for Reverie position control", motor)
            return

        try:
            await self.write_command(
                self._build_command(cmd),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            # Always send STOP to ensure motor stops at target position
            try:
                await self.write_command(
                    self._build_command(ReverieCommands.MOTOR_STOP),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    def _build_command(self, command_bytes: list[int]) -> bytes:
        """Build command with XOR checksum.

        Format: [0x55, ...bytes, checksum]
        Checksum = all bytes XOR'd together XOR 0x55
        """
        checksum = 0x55
        for b in command_bytes:
            checksum ^= b
        return bytes([0x55] + command_bytes + [checksum])

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
            "Writing command to Reverie bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                await self.client.write_gatt_char(REVERIE_CHAR_UUID, command, response=True)
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        # Reverie uses the same characteristic for write and notify
        if self.client is None or not self.client.is_connected:
            return

        try:

            def handler(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Reverie notification: %s", data.hex())
                self.forward_raw_notification(REVERIE_CHAR_UUID, bytes(data))
                self._parse_position_data(data)

            await self.client.start_notify(REVERIE_CHAR_UUID, handler)
            _LOGGER.debug("Started Reverie notifications")
        except BleakError:
            _LOGGER.debug("Could not start notifications")

    def _parse_position_data(self, data: bytearray) -> None:
        """Parse position data from notification.

        Reverie position notification format:
        - Byte 0: 0x55 (header)
        - Byte 1: Command type (0x51 = head, 0x52 = feet)
        - Byte 2: Position (0-100)
        - Byte 3: XOR checksum
        """
        if len(data) < 4:
            return

        # Verify header
        if data[0] != 0x55:
            _LOGGER.debug("Invalid Reverie notification header: %02x", data[0])
            return

        cmd_type = data[1]
        position = data[2]
        checksum = data[3]

        # Verify XOR checksum (XOR of bytes 0-2 should equal byte 3)
        calculated_checksum = data[0] ^ data[1] ^ data[2]
        if checksum != calculated_checksum:
            _LOGGER.debug(
                "Invalid Reverie checksum: expected %02x, got %02x",
                calculated_checksum,
                checksum,
            )
            return

        # Validate position is in range
        if position > 100:
            _LOGGER.debug("Invalid position value: %d", position)
            return

        # Map command type to motor name
        # Use "back" and "legs" to match the sensor position_key expectations
        # (sensors use "back" and "legs" for 2-motor beds)
        motor_map = {
            0x51: "back",  # head motor -> back position
            0x52: "legs",  # feet motor -> legs position
        }

        motor_name = motor_map.get(cmd_type)
        if motor_name and self._notify_callback:
            # Convert position (0-100) to angle estimate
            # Assume max angle of ~60 degrees for back (head), ~45 for legs (feet)
            angle = position * 0.6 if motor_name == "back" else position * 0.45

            _LOGGER.debug(
                "Reverie position update: %s = %d%% (%.1f°)",
                motor_name,
                position,
                angle,
            )
            self._notify_callback(motor_name, angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return
        with contextlib.suppress(BleakError):
            await self.client.stop_notify(REVERIE_CHAR_UUID)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Reverie beds report positions via notifications, not direct reads.
        Position updates are handled by _parse_position_data via start_notify.
        """

    async def _move_to_position(self, motor: str, position: int) -> None:
        """Move a motor to a specific position (0-100) and always send STOP at the end."""
        if motor == "head":
            cmd = ReverieCommands.motor_head(position)
        else:
            cmd = ReverieCommands.motor_feet(position)

        try:
            await self.write_command(
                self._build_command(cmd),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            # Always send STOP with a fresh event so it's not affected by cancellation
            try:
                await self.write_command(
                    self._build_command(ReverieCommands.MOTOR_STOP),
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods - Reverie uses position-based control
    # For up/down we'll move incrementally toward 100/0
    async def move_head_up(self) -> None:
        """Move head up (to 100%)."""
        await self._move_to_position("head", 100)

    async def move_head_down(self) -> None:
        """Move head down (to 0%)."""
        await self._move_to_position("head", 0)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            self._build_command(ReverieCommands.MOTOR_STOP),
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
        """Move legs up (to 100%)."""
        await self._move_to_position("feet", 100)

    async def move_legs_down(self) -> None:
        """Move legs down (to 0%)."""
        await self._move_to_position("feet", 0)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            self._build_command(ReverieCommands.MOTOR_STOP),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            self._build_command(ReverieCommands.PRESET_FLAT),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: ReverieCommands.PRESET_MEMORY_1,
            2: ReverieCommands.PRESET_MEMORY_2,
            3: ReverieCommands.PRESET_MEMORY_3,
            4: ReverieCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=300,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: ReverieCommands.PROGRAM_MEMORY_1,
            2: ReverieCommands.PROGRAM_MEMORY_2,
            3: ReverieCommands.PROGRAM_MEMORY_3,
            4: ReverieCommands.PROGRAM_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(self._build_command(command))

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(self._build_command(ReverieCommands.LIGHTS_TOGGLE))

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        self._massage_head_level = 0
        self._massage_foot_level = 0
        self._massage_wave_level = 0
        await self.write_command(self._build_command(ReverieCommands.massage_head(0)))
        await self.write_command(self._build_command(ReverieCommands.massage_foot(0)))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        self._massage_head_level = min(10, self._massage_head_level + 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_head(self._massage_head_level))
        )

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        self._massage_head_level = max(0, self._massage_head_level - 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_head(self._massage_head_level))
        )

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        self._massage_foot_level = min(10, self._massage_foot_level + 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_foot(self._massage_foot_level))
        )

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        self._massage_foot_level = max(0, self._massage_foot_level - 1)
        await self.write_command(
            self._build_command(ReverieCommands.massage_foot(self._massage_foot_level))
        )

    async def massage_mode_step(self) -> None:
        """Step through wave massage levels."""
        self._massage_wave_level = (self._massage_wave_level + 1) % 11
        await self.write_command(
            self._build_command(ReverieCommands.massage_wave(self._massage_wave_level))
        )

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            self._build_command(ReverieCommands.PRESET_ZERO_G),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(
            self._build_command(ReverieCommands.PRESET_ANTI_SNORE),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    # Direct massage intensity control
    async def set_massage_intensity(self, zone: str, level: int) -> None:
        """Set massage intensity for a specific zone.

        Args:
            zone: "head", "foot", or "wave"
            level: 0-10 (0 = off)
        """
        # Clamp level to valid range
        level = max(0, min(10, level))

        if zone == "head":
            self._massage_head_level = level
            await self.write_command(self._build_command(ReverieCommands.massage_head(level)))
        elif zone == "foot":
            self._massage_foot_level = level
            await self.write_command(self._build_command(ReverieCommands.massage_foot(level)))
        elif zone == "wave":
            self._massage_wave_level = level
            await self.write_command(self._build_command(ReverieCommands.massage_wave(level)))
        else:
            _LOGGER.warning("Unknown massage zone: %s", zone)

    def get_massage_state(self) -> dict[str, Any]:
        """Return current massage state from internal tracking.

        Returns:
            dict with head_intensity, foot_intensity, wave_intensity
        """
        return {
            "head_intensity": self._massage_head_level,
            "foot_intensity": self._massage_foot_level,
            "wave_intensity": self._massage_wave_level,
        }
