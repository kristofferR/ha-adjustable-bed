"""Vibradorm bed controller implementation.

Protocol reverse-engineered from de.vibradorm.vra and com.vibradorm.vmatbasic APKs.

Vibradorm beds (VMAT series) use a simple single-byte command format for motor control.
Position feedback is available via notifications on a separate characteristic.

Device name pattern: "VMAT*" (e.g., "VMATMEM047")
Manufacturer ID: 944 (0x03B0)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import (
    VIBRADORM_COMMAND_CHAR_UUID,
    VIBRADORM_LIGHT_CHAR_UUID,
    VIBRADORM_NOTIFY_CHAR_UUID,
    VIBRADORM_SERVICE_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class VibradormCommands:
    """Vibradorm single-byte command constants.

    Motor naming (German origin):
    - K = Kopf (head/back)
    - OS = Oberschenkel (thigh/legs)
    - F = Fuß (foot - for 4-motor beds)
    - N = Nacken (neck - for 4-motor beds)
    - A = All motors
    - H = Hoch (up)
    - R = Runter (down)
    """

    # Stop command
    STOP: int = 0xFF  # 255

    # 2-motor bed commands (standard configuration)
    # Head/back motor
    HEAD_UP: int = 0x0B  # 11 = KH
    HEAD_DOWN: int = 0x0A  # 10 = KR

    # Legs/thigh motor
    LEGS_UP: int = 0x09  # 9 = OSH
    LEGS_DOWN: int = 0x08  # 8 = OSR

    # 4-motor bed commands (additional motors)
    # Foot motor
    FOOT_UP: int = 0x05  # 5 = FH
    FOOT_DOWN: int = 0x04  # 4 = FR

    # Neck motor
    NECK_UP: int = 0x03  # 3 = NH
    NECK_DOWN: int = 0x02  # 2 = NR

    # All motors
    ALL_UP: int = 0x10  # 16 = AH
    ALL_DOWN: int = 0x00  # 0 = AR (also used as flat preset)

    # Memory presets
    MEMORY_1: int = 0x0E  # 14
    MEMORY_2: int = 0x0F  # 15
    MEMORY_3: int = 0x0C  # 12
    MEMORY_4: int = 0x1A  # 26
    MEMORY_5: int = 0x1B  # 27
    MEMORY_6: int = 0x1C  # 28
    STORE: int = 0x0D  # 13 (save current position to active memory slot)


class VibradormController(BedController):
    """Controller for Vibradorm beds (VMAT series).

    Vibradorm beds use single-byte commands written to the COMMAND characteristic.
    Position feedback is received via notifications on a separate characteristic.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Vibradorm controller.

        Args:
            coordinator: The coordinator managing this controller.
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._lights_on: bool = False
        self._write_with_response: bool = True

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return VIBRADORM_COMMAND_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Vibradorm beds have a dedicated flat command (ALL_DOWN)."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Vibradorm beds support 4 main memory slots (more available)."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Vibradorm beds support programming memory positions."""
        return True

    @property
    def supports_light_cycle(self) -> bool:
        """Return True - Vibradorm beds have light control."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - Vibradorm beds have separate on/off light commands."""
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Vibradorm bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        await self._write_gatt_with_retry(
            VIBRADORM_COMMAND_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    async def _write_motor_command(
        self,
        cmd: int,
        repeat_count: int | None = None,
        repeat_delay_ms: int | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a single-byte motor command.

        Args:
            cmd: The command byte to send
            repeat_count: Number of times to repeat (defaults to coordinator setting)
            repeat_delay_ms: Delay between repeats (defaults to coordinator setting)
            cancel_event: Optional event that signals cancellation
        """
        if repeat_count is None:
            repeat_count = self._coordinator.motor_pulse_count
        if repeat_delay_ms is None:
            repeat_delay_ms = self._coordinator.motor_pulse_delay_ms

        await self.write_command(
            bytes([cmd]),
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    def _handle_notification(self, _sender: int, data: bytearray) -> None:
        """Handle BLE notification data.

        Position notification format (from XMCMotorData.java):
        - Byte 0-1: Header/flags
        - Byte 2: Flags (bit 4 = init request, bit 6 = sync status)
        - Bytes 3-4: Motor 1 position (16-bit little-endian)
        - Bytes 5-6: Motor 2 position (16-bit little-endian)
        - Bytes 7-8: Motor 3 position (16-bit little-endian)
        - Bytes 9-10: Motor 4 position (16-bit little-endian)

        Position values are raw encoder counts, higher values = more raised.
        """
        self.forward_raw_notification(VIBRADORM_NOTIFY_CHAR_UUID, bytes(data))

        if len(data) < 8:
            _LOGGER.debug("Vibradorm notification too short: %s", data.hex())
            return

        # Parse motor positions (16-bit little-endian values)
        # Motor 1 = head/back, Motor 2 = legs
        motor1_pos = int.from_bytes(data[3:5], byteorder="little")
        motor2_pos = int.from_bytes(data[5:7], byteorder="little")

        _LOGGER.debug(
            "Vibradorm position update: motor1=%d, motor2=%d (raw: %s)",
            motor1_pos,
            motor2_pos,
            data.hex(),
        )

        if self._notify_callback:
            # Convert raw positions to percentages
            # Based on user data: flat = ~0, raised = ~0x1922 (~6434) for head
            # Using conservative estimate: 0-10000 range maps to 0-100%
            head_pct = min(100.0, max(0.0, motor1_pos / 100.0))
            legs_pct = min(100.0, max(0.0, motor2_pos / 100.0))

            _LOGGER.debug(
                "Vibradorm position percentages: head=%.1f%%, legs=%.1f%%",
                head_pct,
                legs_pct,
            )

            self._notify_callback("back", head_pct)
            self._notify_callback("legs", legs_pct)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start Vibradorm notifications: not connected")
            return

        # Detect write mode from characteristic properties
        if self.client.services:
            for service in self.client.services:
                if str(service.uuid).lower() == VIBRADORM_SERVICE_UUID.lower():
                    for char in service.characteristics:
                        if str(char.uuid).lower() == VIBRADORM_COMMAND_CHAR_UUID.lower():
                            props = {prop.lower() for prop in char.properties}
                            # Prefer write-with-response when available for acknowledgements
                            if "write" in props:
                                self._write_with_response = True
                            elif "write-without-response" in props:
                                self._write_with_response = False
                            _LOGGER.debug(
                                "Vibradorm write mode: %s (properties: %s)",
                                "with-response" if self._write_with_response else "without-response",
                                char.properties,
                            )

        try:
            await self.client.start_notify(VIBRADORM_NOTIFY_CHAR_UUID, self._handle_notification)
            _LOGGER.info("Started position notifications for Vibradorm bed")
        except BleakError as err:
            _LOGGER.warning("Failed to start Vibradorm notifications: %s", err)
            self.log_discovered_services(level=logging.INFO)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(VIBRADORM_NOTIFY_CHAR_UUID)
            _LOGGER.debug("Stopped Vibradorm position notifications")
        except BleakError:
            pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Vibradorm beds push position updates via notifications.
        This method is a no-op since positions come automatically.
        """
        del motor_count  # Unused - positions come via notifications
        _LOGGER.debug("Vibradorm read_positions called (positions come via notifications)")

    async def _move_with_stop(self, command: int) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self._write_motor_command(command)
        finally:
            try:
                await self._write_motor_command(
                    VibradormCommands.STOP,
                    repeat_count=1,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(VibradormCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(VibradormCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._write_motor_command(
            VibradormCommands.STOP,
            repeat_count=1,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head for Vibradorm)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Vibradorm)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor (same as head for Vibradorm)."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(VibradormCommands.LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(VibradormCommands.LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._write_motor_command(
            VibradormCommands.STOP,
            repeat_count=1,
            cancel_event=asyncio.Event(),
        )

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for 2-motor Vibradorm beds)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for 2-motor Vibradorm beds)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._write_motor_command(
            VibradormCommands.STOP,
            repeat_count=1,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (all motors down)."""
        await self._write_motor_command(VibradormCommands.ALL_DOWN, repeat_count=1)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset position.

        Args:
            memory_num: Memory slot number (1-4)
        """
        memory_commands = {
            1: VibradormCommands.MEMORY_1,
            2: VibradormCommands.MEMORY_2,
            3: VibradormCommands.MEMORY_3,
            4: VibradormCommands.MEMORY_4,
        }
        if memory_num not in memory_commands:
            _LOGGER.warning("Invalid memory preset number: %d (supported: 1-4)", memory_num)
            return
        await self._write_motor_command(memory_commands[memory_num], repeat_count=1)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Note: Vibradorm uses a single STORE command. The app selects which
        memory slot to save to via UI state. For simplicity, we always
        send STORE which saves to the currently selected slot.
        """
        if memory_num < 1 or memory_num > 4:
            _LOGGER.warning("Invalid memory program number: %d (supported: 1-4)", memory_num)
            return
        # The STORE command saves to the currently active memory slot
        # Different from Jensen where memory slots are addressed directly
        await self._write_motor_command(VibradormCommands.STORE, repeat_count=1)
        _LOGGER.info("Saved current position to memory (STORE command sent)")

    # Light methods
    async def lights_on(self) -> None:
        """Turn on lights."""
        # Light command format: [level, 0, timer]
        # level > 0 turns on, level = 0 turns off
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")

        try:
            await self._write_gatt_with_retry(
                VIBRADORM_LIGHT_CHAR_UUID,
                bytes([0xFF, 0x00, 0x00]),  # Full brightness, no timer
                response=self._write_with_response,
            )
            self._lights_on = True
            _LOGGER.debug("Vibradorm lights turned on")
        except BleakError as err:
            _LOGGER.warning("Failed to turn on lights: %s", err)
            raise

    async def lights_off(self) -> None:
        """Turn off lights."""
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")

        try:
            await self._write_gatt_with_retry(
                VIBRADORM_LIGHT_CHAR_UUID,
                bytes([0x00, 0x00, 0x00]),  # Off
                response=self._write_with_response,
            )
            self._lights_on = False
            _LOGGER.debug("Vibradorm lights turned off")
        except BleakError as err:
            _LOGGER.warning("Failed to turn off lights: %s", err)
            raise

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        if self._lights_on:
            await self.lights_off()
        else:
            await self.lights_on()
