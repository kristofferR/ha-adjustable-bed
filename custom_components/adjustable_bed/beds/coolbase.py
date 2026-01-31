"""Cool Base bed controller implementation.

Reverse engineering from com.keeson.coolbase APK.

Cool Base is a Keeson/Ergomotion variant with additional cooling fan features.
Uses the same FFE0/FFE5 service UUIDs as Keeson BaseI5 with 8-byte command packets.

Unique features:
- Left/Right fan control with 3 speed levels (0-3)
- Sync fan mode for both sides
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class CoolBaseCommands:
    """Cool Base command constants (32-bit values in little-endian byte order)."""

    # Motor commands (cmd0 byte)
    MOTOR_HEAD_UP = 0x01
    MOTOR_HEAD_DOWN = 0x02
    MOTOR_FEET_UP = 0x04
    MOTOR_FEET_DOWN = 0x08

    # Presets (cmd1/cmd3 bytes)
    PRESET_FLAT = 0x08000000  # cmd3=0x08
    PRESET_ZERO_G = 0x00001000  # cmd1=0x10
    PRESET_TV = 0x00004000  # cmd1=0x40
    PRESET_ANTI_SNORE = 0x00008000  # cmd1=0x80
    PRESET_MEMORY_1 = 0x00010000  # cmd2=0x01

    # Light (cmd2 byte)
    TOGGLE_LIGHT = 0x00020000  # cmd2=0x02

    # Massage (cmd1/cmd3 bytes)
    MASSAGE_HEAD = 0x00000800  # cmd1=0x08
    MASSAGE_FOOT = 0x00000400  # cmd1=0x04
    MASSAGE_LEVEL = 0x04000000  # cmd3=0x04

    # Fan/Wind commands (cmd2/cmd3 bytes) - Unique to Cool Base
    FAN_LEFT = 0x00400000  # cmd2=0x40 - cycles through levels 0-3
    FAN_RIGHT = 0x40000000  # cmd3=0x40 - cycles through levels 0-3
    FAN_SYNC = 0x00040000  # cmd2=0x04 - both fans together


class CoolBaseController(BedController):
    """Controller for Cool Base beds (Keeson BaseI5 with fan control)."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Cool Base controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}

        # Fan state from notifications
        self._left_fan_level: int = 0
        self._right_fan_level: int = 0
        self._massage_level: int = 0
        self._light_on: bool = False

        self._char_uuid = KEESON_BASE_WRITE_CHAR_UUID
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID

        _LOGGER.debug("CoolBaseController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1  # Only Memory 1 confirmed in the app

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False  # Toggle only

    @property
    def supports_stop_all(self) -> bool:
        return True  # Send zero command

    @property
    def supports_fan_control(self) -> bool:
        """Return True - Cool Base has fan control."""
        return True

    @property
    def fan_level_max(self) -> int:
        """Return maximum fan level (0-3 scale)."""
        return 3

    def _build_command(self, cmd0: int = 0, cmd1: int = 0, cmd2: int = 0, cmd3: int = 0) -> bytes:
        """Build an 8-byte command packet.

        Format: [0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
        Checksum: XOR of header and command bytes, then XOR with 0xFF
        """
        header = [0xE5, 0xFE, 0x16]
        data = header + [cmd0, cmd1, cmd2, cmd3]
        checksum = sum(data) ^ 0xFF
        data.append(checksum & 0xFF)
        return bytes(data)

    def _build_command_from_value(self, command_value: int) -> bytes:
        """Build command from 32-bit value (little-endian byte order)."""
        cmd0 = command_value & 0xFF
        cmd1 = (command_value >> 8) & 0xFF
        cmd2 = (command_value >> 16) & 0xFF
        cmd3 = (command_value >> 24) & 0xFF
        return self._build_command(cmd0, cmd1, cmd2, cmd3)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Cool Base bed: %s (repeat: %d, delay: %dms)",
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

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started notifications for Cool Base bed")
        except BleakError:
            _LOGGER.warning("Failed to start notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes) -> None:
        """Parse notification data from the bed.

        Expected format: 28 bytes with state information.
        Key positions:
        - Byte 13 (high bits): Light status (bit 6)
        - Byte 19: Massage level (0-3)
        - Byte 20: Left wind level (0-3)
        - Byte 21: Right wind level (0-3)
        """
        if len(data) < 22:
            return

        # Light status - bit 6 of byte 13
        if len(data) > 13:
            self._light_on = (data[13] >> 6) & 0x01 == 1

        # Massage level
        if len(data) > 19:
            self._massage_level = data[19] & 0x03

        # Fan levels
        if len(data) > 20:
            self._left_fan_level = data[20] & 0x03
        if len(data) > 21:
            self._right_fan_level = data[21] & 0x03

        _LOGGER.debug(
            "Cool Base state: light=%s, massage=%d, left_fan=%d, right_fan=%d",
            self._light_on,
            self._massage_level,
            self._left_fan_level,
            self._right_fan_level,
        )

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
            _LOGGER.debug("Stopped notifications")
        except BleakError:
            _LOGGER.debug("Failed to stop notifications")

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data (not supported on Cool Base)."""
        pass

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor in a direction or stop it, always sending STOP at the end."""
        self._motor_state[motor] = direction
        cmd0 = 0

        # Build combined motor command
        state = self._motor_state
        if state.get("head") is True:
            cmd0 += CoolBaseCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            cmd0 += CoolBaseCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            cmd0 += CoolBaseCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            cmd0 += CoolBaseCommands.MOTOR_FEET_DOWN

        try:
            if cmd0:
                await self.write_command(
                    self._build_command(cmd0=cmd0),
                    repeat_count=self._coordinator.motor_pulse_count,
                    repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
                )
        finally:
            # Always send stop
            self._motor_state = {}
            try:
                await self.write_command(
                    self._build_command(),  # All zeros = stop
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

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
            self._build_command(),  # All zeros = stop
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.PRESET_FLAT))

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        if memory_num == 1:
            await self.write_command(self._build_command_from_value(CoolBaseCommands.PRESET_MEMORY_1))
        else:
            _LOGGER.warning("Cool Base only supports Memory 1, requested: %d", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("Cool Base doesn't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.PRESET_ZERO_G))

    async def preset_lounge(self) -> None:
        """Go to lounge position (same as Memory 1)."""
        await self.preset_memory(1)

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.PRESET_TV))

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.PRESET_ANTI_SNORE))

    # Light methods
    async def lights_on(self) -> None:
        """Turn on lights (toggle)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (toggle)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.TOGGLE_LIGHT))

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage (cycles through levels)."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.MASSAGE_LEVEL))

    async def massage_head_up(self) -> None:
        """Increase head massage."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.MASSAGE_HEAD))

    async def massage_head_down(self) -> None:
        """Decrease head massage (not directly supported, use toggle)."""
        await self.massage_head_up()

    async def massage_foot_up(self) -> None:
        """Increase foot massage."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.MASSAGE_FOOT))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage (not directly supported, use toggle)."""
        await self.massage_foot_up()

    # Fan control methods (unique to Cool Base)
    async def fan_left_cycle(self) -> None:
        """Cycle left fan through levels 0-3."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.FAN_LEFT))

    async def fan_right_cycle(self) -> None:
        """Cycle right fan through levels 0-3."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.FAN_RIGHT))

    async def fan_sync_cycle(self) -> None:
        """Cycle both fans together through levels 0-3."""
        await self.write_command(self._build_command_from_value(CoolBaseCommands.FAN_SYNC))

    @property
    def left_fan_level(self) -> int:
        """Get current left fan level (0-3)."""
        return self._left_fan_level

    @property
    def right_fan_level(self) -> int:
        """Get current right fan level (0-3)."""
        return self._right_fan_level

    @property
    def led_on(self) -> bool:
        """Check if LED is on."""
        return self._light_on

    @property
    def massage_level(self) -> int:
        """Get current massage level (0-3)."""
        return self._massage_level
