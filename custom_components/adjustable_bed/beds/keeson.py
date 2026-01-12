"""Keeson bed controller implementation.

Keeson beds (Member's Mark, Purple, Ergomotion, GhostBed) have several protocol variants:
- KSBT: Simple 6-byte commands [0x04, 0x02, ...int_to_bytes(command)]
- BaseI4: 8-byte commands with XOR checksum
- BaseI5: Same as BaseI4 with notification support
- Ergomotion: Same as BaseI4/I5 but with position feedback via BLE notifications

All use 32-bit command values for motor and preset operations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_FALLBACK_GATT_PAIRS,
    KEESON_KSBT_CHAR_UUID,
    KEESON_VARIANT_ERGOMOTION,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class KeesonCommands:
    """Keeson command constants (32-bit values)."""

    # Presets
    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000
    PRESET_MEMORY_2 = 0x4000
    PRESET_MEMORY_3 = 0x8000
    PRESET_MEMORY_4 = 0x10000
    # Preset aliases (for Ergomotion compatibility)
    PRESET_LOUNGE = 0x2000  # Same as Memory 1
    PRESET_TV = 0x4000  # Same as Memory 2

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
    TOGGLE_SAFETY_LIGHTS = 0x20000
    TOGGLE_LIGHTS = 0x20000  # Alias for Ergomotion compatibility


def int_to_bytes(value: int) -> list[int]:
    """Convert an integer to 4 bytes (big-endian)."""
    return [
        (value >> 24) & 0xFF,
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ]


class KeesonController(BedController):
    """Controller for Keeson beds (including Ergomotion variant with position feedback)."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = "base",
        char_uuid: str | None = None,
    ) -> None:
        """Initialize the Keeson controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            variant: Protocol variant ('ksbt', 'base', or 'ergomotion')
            char_uuid: The characteristic UUID to use for writing commands
        """
        super().__init__(coordinator)
        self._variant = variant
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}

        # Position feedback state (for ergomotion variant)
        self._head_position: int | None = None
        self._foot_position: int | None = None
        self._head_moving: bool = False
        self._foot_moving: bool = False
        self._head_massage: int = 0
        self._foot_massage: int = 0
        self._led_on: bool = False
        self._timer_mode: str | None = None

        # Determine the characteristic UUID
        if char_uuid:
            self._char_uuid = char_uuid
        elif variant == "ksbt":
            self._char_uuid = KEESON_KSBT_CHAR_UUID
        else:
            # For base/ergomotion variant, try to find a working characteristic UUID
            self._char_uuid = self._detect_characteristic_uuid()

        # Notify characteristic for ergomotion variant
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID

        _LOGGER.debug(
            "KeesonController initialized (variant: %s, char: %s)",
            variant,
            self._char_uuid,
        )

    def _detect_characteristic_uuid(self) -> str:
        """Detect the correct write characteristic UUID from available services.

        Tries the primary UUID first, then falls back to alternative UUIDs
        if the primary service is not available.
        """
        client = self.client
        if client is None or client.services is None:
            _LOGGER.debug("No BLE services available, using default UUID")
            return KEESON_BASE_WRITE_CHAR_UUID

        # Get all available service UUIDs
        available_services = {str(service.uuid).lower() for service in client.services}
        _LOGGER.debug("Available Keeson services: %s", available_services)

        # Check if primary service is available
        if KEESON_BASE_SERVICE_UUID.lower() in available_services:
            _LOGGER.debug("Found primary Keeson service, using primary UUID")
            return KEESON_BASE_WRITE_CHAR_UUID

        # Try fallback service/characteristic pairs
        for fallback_service, fallback_char in KEESON_FALLBACK_GATT_PAIRS:
            if fallback_service.lower() in available_services:
                _LOGGER.info(
                    "Primary Keeson service not found, using fallback: %s/%s",
                    fallback_service,
                    fallback_char,
                )
                return fallback_char

        # No matching service found, log all services for debugging and use default
        _LOGGER.warning(
            "No recognized Keeson service found. "
            "Please report this to help add support for your device."
        )
        # Log all discovered services at INFO level to help with debugging
        self.log_discovered_services(level=logging.INFO)
        return KEESON_BASE_WRITE_CHAR_UUID

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    def _build_command(self, command_value: int) -> bytes:
        """Build command bytes based on protocol variant."""
        if self._variant == "ksbt":
            # KSBT: [0x04, 0x02, ...int_to_bytes(command)]
            return bytes([0x04, 0x02] + int_to_bytes(command_value))
        else:
            # BaseI4/I5: [0xe5, 0xfe, 0x16, ...reversed_int_bytes, checksum]
            int_bytes = int_to_bytes(command_value)
            int_bytes.reverse()  # Little-endian
            data = [0xE5, 0xFE, 0x16] + int_bytes
            checksum = sum(data) ^ 0xFF
            data.append(checksum & 0xFF)
            return bytes(data)

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
            "Writing command to Keeson bed: %s (repeat: %d, delay: %dms)",
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
                    self._char_uuid, command, response=False
                )
            except BleakError as err:
                _LOGGER.error("Failed to write command: %s", err)
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications (ergomotion variant only)."""
        self._notify_callback = callback

        if self._variant != KEESON_VARIANT_ERGOMOTION:
            _LOGGER.debug("Keeson beds don't support position notifications (variant: %s)", self._variant)
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started position notifications for Keeson/Ergomotion bed")
        except BleakError as err:
            _LOGGER.warning("Failed to start notifications: %s", err)

    def _on_notification(self, sender: int, data: bytearray) -> None:
        """Handle incoming BLE notifications (ergomotion variant)."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes) -> None:
        """Parse notification data from the bed (ergomotion variant).

        Data formats based on header byte:
        - 0xED: 16-byte messages
        - 0xF0: 19-byte messages
        - 0xF1: 20-byte messages
        """
        if len(data) < 1:
            return

        header = data[0]

        if header == 0xED and len(data) >= 16:
            self._parse_position_message(data, 16)
        elif header == 0xF0 and len(data) >= 19:
            self._parse_position_message(data, 19)
        elif header == 0xF1 and len(data) >= 20:
            self._parse_position_message(data, 20)
        else:
            _LOGGER.debug("Unknown notification format: header=0x%02X len=%d", header, len(data))

    def _parse_position_message(self, data: bytes, msg_len: int) -> None:
        """Parse position message from ergomotion bed."""
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
        data2 = data[9:msg_len]

        # Movement status and LED: byte 4
        if len(data2) > 4:
            move = data2[4] & 0xF
            self._head_moving = move != 0xF and (move & 1) > 0
            self._foot_moving = move != 0xF and (move & 2) > 0
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

    def _notify_position_update(self) -> None:
        """Notify callback with position updates."""
        if self._notify_callback is None:
            return

        # Notify head position
        if self._head_position is not None:
            self._notify_callback("head", float(self._head_position))

        # Notify foot position
        if self._foot_position is not None:
            self._notify_callback("feet", float(self._foot_position))

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self._variant != KEESON_VARIANT_ERGOMOTION:
            return

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

    # Position feedback properties (for ergomotion variant)
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

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command."""
        command = 0
        state = self._motor_state
        if state.get("head") is True:
            command += KeesonCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            command += KeesonCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            command += KeesonCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            command += KeesonCommands.MOTOR_FEET_DOWN
        if state.get("tilt") is True:
            command += KeesonCommands.MOTOR_TILT_UP
        elif state.get("tilt") is False:
            command += KeesonCommands.MOTOR_TILT_DOWN
        if state.get("lumbar") is True:
            command += KeesonCommands.MOTOR_LUMBAR_UP
        elif state.get("lumbar") is False:
            command += KeesonCommands.MOTOR_LUMBAR_DOWN
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
        """Move back up (same as head for Keeson)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Keeson)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet for Keeson)."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet for Keeson)."""
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
            self._build_command(KeesonCommands.PRESET_FLAT),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: KeesonCommands.PRESET_MEMORY_1,
            2: KeesonCommands.PRESET_MEMORY_2,
            3: KeesonCommands.PRESET_MEMORY_3,
            4: KeesonCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=300,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported on Keeson)."""
        _LOGGER.warning("Keeson beds don't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(
            self._build_command(KeesonCommands.PRESET_ZERO_G),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_lounge(self) -> None:
        """Go to lounge position (Memory 1)."""
        await self.write_command(
            self._build_command(KeesonCommands.PRESET_LOUNGE),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_tv(self) -> None:
        """Go to TV position (Memory 2)."""
        await self.write_command(
            self._build_command(KeesonCommands.PRESET_TV),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle safety lights."""
        await self.write_command(
            self._build_command(KeesonCommands.TOGGLE_SAFETY_LIGHTS)
        )

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_STEP))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_HEAD_UP))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_HEAD_DOWN))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_FOOT_UP))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(KeesonCommands.MASSAGE_FOOT_DOWN))

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(
            self._build_command(KeesonCommands.MASSAGE_TIMER_STEP)
        )
