"""Svane bed controller implementation (LinonPI protocol).

Svane beds use a multi-service BLE architecture where each motor has its own
service with direction-specific characteristics. This is different from most
other beds which use a single service with command bytes to indicate direction.

Note: JMC400 beds (also supported by Svane app) use the Jensen protocol and
are handled by jensen.py - this controller is specifically for "Svane Bed"
devices using the LinonPI protocol.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    SVANE_CHAR_DOWN_UUID,
    SVANE_CHAR_MEMORY_UUID,
    SVANE_CHAR_POSITION_UUID,
    SVANE_CHAR_UP_UUID,
    SVANE_FEET_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_LIGHT_ON_OFF_UUID,
    SVANE_LIGHT_SERVICE_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SvaneCommands:
    """Svane LinonPI command constants."""

    # Motor control (2-byte, written to direction-specific characteristics)
    MOTOR_MOVE: bytes = bytes([0x01, 0x00])
    MOTOR_STOP: bytes = bytes([0x00, 0x00])

    # Svane Position preset (2-byte, written to MEMORY characteristic)
    # This is a special preset position specific to Svane beds
    SVANE_POSITION: bytes = bytes([0x03, 0x00])

    # Memory/preset commands (6-byte, written to MEMORY characteristic)
    FLATTEN: bytes = bytes([0x3F, 0x81, 0x00, 0x00, 0x00, 0x00])
    SAVE_POSITION: bytes = bytes([0x3F, 0x40, 0x00, 0x00, 0x00, 0x00])
    RECALL_POSITION: bytes = bytes([0x3F, 0x80, 0x00, 0x00, 0x00, 0x00])
    READ_POSITION: bytes = bytes([0x3F, 0xFF, 0x00, 0x00, 0x00, 0x00])

    # Light commands (6-byte, written to LIGHT_ON_OFF characteristic)
    LIGHT_ON: bytes = bytes([0x13, 0x02, 0x50, 0x01, 0x00, 0x50])  # brightness=80
    LIGHT_OFF: bytes = bytes([0x13, 0x02, 0x00, 0x00, 0x00, 0x00])


class SvaneController(BedController):
    """Controller for Svane beds using LinonPI multi-service protocol.

    The LinonPI protocol uses separate BLE services for each motor (head/feet)
    with direction-specific characteristics. The same characteristic UUIDs exist
    in multiple services, so we must find the characteristic within the correct
    service before writing.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Svane controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("SvaneController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the primary control characteristic UUID.

        Note: This controller writes to multiple characteristics, but this
        returns the head UP characteristic as the primary one.
        """
        return SVANE_CHAR_UP_UUID

    # Capability properties
    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Svane beds support flat preset."""
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        """Return True - Svane beds support a 'Svane Position' preset (similar to zero-g)."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Svane beds support memory presets."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 1 - Svane beds support a single memory slot."""
        return 1

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Svane beds support programming memory positions."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - Svane beds support discrete on/off light control."""
        return True

    def _get_char_in_service(
        self, service_uuid: str, char_uuid: str
    ) -> BleakGATTCharacteristic | None:
        """Find a characteristic within a specific service.

        This is required because the same characteristic UUID exists in multiple
        services (e.g., UP_CHAR exists in both HEAD_SERVICE and FEET_SERVICE).

        Args:
            service_uuid: The service UUID to search within
            char_uuid: The characteristic UUID to find

        Returns:
            The BleakGATTCharacteristic if found, None otherwise
        """
        if self.client is None or not self.client.is_connected:
            return None

        for service in self.client.services:
            if service.uuid.lower() == service_uuid.lower():
                for char in service.characteristics:
                    if char.uuid.lower() == char_uuid.lower():
                        return char
        return None

    async def _write_to_service_char(
        self,
        service_uuid: str,
        char_uuid: str,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to a characteristic in a specific service.

        Args:
            service_uuid: The service UUID containing the characteristic
            char_uuid: The characteristic UUID to write to
            command: The bytes to write
            repeat_count: Number of times to send the command
            repeat_delay_ms: Delay between repeated commands in milliseconds
            cancel_event: Optional event to signal cancellation
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        char = self._get_char_in_service(service_uuid, char_uuid)
        if char is None:
            _LOGGER.error(
                "Characteristic %s not found in service %s",
                char_uuid,
                service_uuid,
            )
            raise ConnectionError(
                f"Characteristic {char_uuid} not found in service {service_uuid}"
            )

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing %s to service %s char %s (repeat: %d, delay: %dms)",
            command.hex(),
            service_uuid[:8],
            char_uuid[:8],
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                async with self._ble_lock:
                    await self.client.write_gatt_char(char, command, response=True)
            except BleakError:
                _LOGGER.exception(
                    "Failed to write to service %s char %s",
                    service_uuid[:8],
                    char_uuid[:8],
                )
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed (writes to head memory characteristic).

        This method is provided for compatibility with the base class interface.
        For motor control, use the specific move_* methods instead.
        """
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_MEMORY_UUID,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning(
                "Cannot start position notifications: BLE client not connected"
            )
            return

        # Subscribe to head and foot position characteristics
        # Note: Same char UUID in different services
        position_configs = [
            ("back", SVANE_HEAD_SERVICE_UUID, "head"),
            ("legs", SVANE_FEET_SERVICE_UUID, "feet"),
        ]

        for motor_name, service_uuid, log_name in position_configs:
            char = self._get_char_in_service(service_uuid, SVANE_CHAR_POSITION_UUID)
            if char is None:
                _LOGGER.debug(
                    "Position characteristic not found for %s motor", log_name
                )
                continue

            try:
                # Create a closure to capture the motor name
                def make_handler(name: str) -> Callable[[Any, bytearray], None]:
                    def handler(_: Any, data: bytearray) -> None:
                        _LOGGER.debug("Svane %s position: %s", name, data.hex())
                        self.forward_raw_notification(
                            SVANE_CHAR_POSITION_UUID, bytes(data)
                        )
                        if len(data) >= 1 and self._notify_callback:
                            # Position is a raw value, estimate angle
                            # Assuming 0-100 range maps to 0-60 degrees for head, 0-45 for feet
                            position = data[0]
                            max_angle = 60.0 if name == "back" else 45.0
                            angle = position * max_angle / 100
                            self._notify_callback(name, angle)

                    return handler

                await self.client.start_notify(char, make_handler(motor_name))
                _LOGGER.debug("Started position notifications for %s", log_name)
            except BleakError:
                _LOGGER.debug("Could not start position notifications for %s", log_name)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        for service_uuid in [SVANE_HEAD_SERVICE_UUID, SVANE_FEET_SERVICE_UUID]:
            char = self._get_char_in_service(service_uuid, SVANE_CHAR_POSITION_UUID)
            if char:
                try:
                    await self.client.stop_notify(char)
                except BleakError:
                    pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        del motor_count  # Unused - Svane always has 2 motors (head/feet)
        if self.client is None or not self.client.is_connected:
            return

        position_configs = [
            ("back", SVANE_HEAD_SERVICE_UUID, 60.0),
            ("legs", SVANE_FEET_SERVICE_UUID, 45.0),
        ]

        for motor_name, service_uuid, max_angle in position_configs:
            char = self._get_char_in_service(service_uuid, SVANE_CHAR_POSITION_UUID)
            if char is None:
                continue

            try:
                data = await self.client.read_gatt_char(char)
                if data and len(data) >= 1 and self._notify_callback:
                    position = data[0]
                    angle = position * max_angle / 100
                    self._notify_callback(motor_name, angle)
            except BleakError:
                _LOGGER.debug("Could not read position for %s", motor_name)

    async def _move_motor(
        self,
        service_uuid: str,
        char_uuid: str,
    ) -> None:
        """Move a motor in the given direction, then stop.

        Args:
            service_uuid: The service UUID for this motor
            char_uuid: The characteristic UUID for the direction (UP or DOWN)
        """
        try:
            await self._write_to_service_char(
                service_uuid,
                char_uuid,
                SvaneCommands.MOTOR_MOVE,
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
            )
        finally:
            # Always send stop to the same characteristic
            await self._write_to_service_char(
                service_uuid,
                char_uuid,
                SvaneCommands.MOTOR_STOP,
                cancel_event=asyncio.Event(),  # Fresh event so stop isn't cancelled
            )

    # Motor control methods - Head
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_UP_UUID,
        )

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_DOWN_UUID,
        )

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        # Stop both directions to be safe
        cancel_event = asyncio.Event()
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_UP_UUID,
            SvaneCommands.MOTOR_STOP,
            cancel_event=cancel_event,
        )

    # Motor control methods - Back (alias for head)
    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    # Motor control methods - Legs/Feet
    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_motor(
            SVANE_FEET_SERVICE_UUID,
            SVANE_CHAR_UP_UUID,
        )

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor(
            SVANE_FEET_SERVICE_UUID,
            SVANE_CHAR_DOWN_UUID,
        )

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        cancel_event = asyncio.Event()
        await self._write_to_service_char(
            SVANE_FEET_SERVICE_UUID,
            SVANE_CHAR_UP_UUID,
            SvaneCommands.MOTOR_STOP,
            cancel_event=cancel_event,
        )

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
        cancel_event = asyncio.Event()
        # Stop head
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_UP_UUID,
            SvaneCommands.MOTOR_STOP,
            cancel_event=cancel_event,
        )
        # Stop feet
        await self._write_to_service_char(
            SVANE_FEET_SERVICE_UUID,
            SVANE_CHAR_UP_UUID,
            SvaneCommands.MOTOR_STOP,
            cancel_event=cancel_event,
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_MEMORY_UUID,
            SvaneCommands.FLATTEN,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def preset_zero_g(self) -> None:
        """Go to Svane Position (comfort preset similar to zero-g)."""
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_MEMORY_UUID,
            SvaneCommands.SVANE_POSITION,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Svane beds only support a single memory position (memory_num is ignored).
        """
        del memory_num  # Svane only supports 1 memory slot
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_MEMORY_UUID,
            SvaneCommands.RECALL_POSITION,
            repeat_count=3,
            repeat_delay_ms=100,
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Svane beds only support a single memory position (memory_num is ignored).
        """
        del memory_num  # Svane only supports 1 memory slot
        await self._write_to_service_char(
            SVANE_HEAD_SERVICE_UUID,
            SVANE_CHAR_MEMORY_UUID,
            SvaneCommands.SAVE_POSITION,
        )

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self._write_to_service_char(
            SVANE_LIGHT_SERVICE_UUID,
            SVANE_LIGHT_ON_OFF_UUID,
            SvaneCommands.LIGHT_ON,
        )

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self._write_to_service_char(
            SVANE_LIGHT_SERVICE_UUID,
            SVANE_LIGHT_ON_OFF_UUID,
            SvaneCommands.LIGHT_OFF,
        )

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights.

        Since we don't track state, this just turns on.
        Users should use lights_on/lights_off for discrete control.
        """
        await self.lights_on()
