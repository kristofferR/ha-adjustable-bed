"""Linak bed controller implementation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import (
    LINAK_BACK_MAX_ANGLE,
    LINAK_BACK_MAX_POSITION,
    LINAK_CONTROL_CHAR_UUID,
    LINAK_FEET_MAX_ANGLE,
    LINAK_FEET_MAX_POSITION,
    LINAK_HEAD_MAX_ANGLE,
    LINAK_HEAD_MAX_POSITION,
    LINAK_LEG_MAX_ANGLE,
    LINAK_LEG_MAX_POSITION,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_FEET_UUID,
    LINAK_POSITION_HEAD_UUID,
    LINAK_POSITION_LEG_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class LinakCommands:
    """Linak command constants."""

    # Presets
    PRESET_MEMORY_1 = bytes([0x0E, 0x00])
    PRESET_MEMORY_2 = bytes([0x0F, 0x00])
    PRESET_MEMORY_3 = bytes([0x0C, 0x00])
    PRESET_MEMORY_4 = bytes([0x44, 0x00])

    # Program presets
    PROGRAM_MEMORY_1 = bytes([0x38, 0x00])
    PROGRAM_MEMORY_2 = bytes([0x39, 0x00])
    PROGRAM_MEMORY_3 = bytes([0x3A, 0x00])
    PROGRAM_MEMORY_4 = bytes([0x45, 0x00])

    # Under-bed lights
    LIGHTS_ON = bytes([0x92, 0x00])
    LIGHTS_OFF = bytes([0x93, 0x00])
    LIGHTS_TOGGLE = bytes([0x94, 0x00])

    # Massage - all
    MASSAGE_ALL_OFF = bytes([0x80, 0x00])
    MASSAGE_ALL_TOGGLE = bytes([0x91, 0x00])
    MASSAGE_ALL_UP = bytes([0xA8, 0x00])
    MASSAGE_ALL_DOWN = bytes([0xA9, 0x00])

    # Massage - head
    MASSAGE_HEAD_TOGGLE = bytes([0xA6, 0x00])
    MASSAGE_HEAD_UP = bytes([0x8D, 0x00])
    MASSAGE_HEAD_DOWN = bytes([0x8E, 0x00])

    # Massage - foot
    MASSAGE_FOOT_TOGGLE = bytes([0xA7, 0x00])
    MASSAGE_FOOT_UP = bytes([0x8F, 0x00])
    MASSAGE_FOOT_DOWN = bytes([0x90, 0x00])

    # Massage mode
    MASSAGE_MODE_STEP = bytes([0x81, 0x00])

    # Motor movement commands
    MOVE_STOP = bytes([0x00, 0x00])
    MOVE_ALL_UP = bytes([0x01, 0x00])

    # Individual motor control
    MOVE_HEAD_UP = bytes([0x03, 0x00])
    MOVE_HEAD_DOWN = bytes([0x02, 0x00])
    MOVE_FEET_UP = bytes([0x05, 0x00])
    MOVE_FEET_DOWN = bytes([0x04, 0x00])
    MOVE_LEGS_UP = bytes([0x09, 0x00])
    MOVE_LEGS_DOWN = bytes([0x08, 0x00])
    MOVE_BACK_UP = bytes([0x0B, 0x00])
    MOVE_BACK_DOWN = bytes([0x0A, 0x00])


class LinakController(BedController):
    """Controller for Linak beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Linak controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._notify_handles: dict[str, int] = {}
        _LOGGER.debug(
            "LinakController initialized (motor_count: %d)",
            coordinator.motor_count,
        )

    @property
    def supports_preset_flat(self) -> bool:
        """Return False - Linak has no native flat command.

        Linak's preset_flat() uses Memory 1, which may not be programmed as flat.
        Users should use the memory presets directly instead.
        """
        return False

    @property
    def supports_lights(self) -> bool:
        """Return True - Linak beds support under-bed lighting."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Linak beds support memory presets."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Linak beds support memory slots 1-4."""
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Linak beds support programming memory positions."""
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LINAK_CONTROL_CHAR_UUID

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Linak bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )
        _LOGGER.debug("Command sequence ended (%d writes attempted)", repeat_count)

    async def start_notify(
        self, callback: Callable[[str, float], None]
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning(
                "Cannot start position notifications: BLE client not connected (client=%s, is_connected=%s)",
                self.client,
                getattr(self.client, 'is_connected', 'N/A') if self.client else 'N/A',
            )
            return

        motor_count = self._coordinator.motor_count
        _LOGGER.info(
            "Setting up position notifications for %d-motor Linak bed at %s",
            motor_count,
            self._coordinator.address,
        )
        _LOGGER.debug(
            "Client state: is_connected=%s, mtu_size=%s",
            self.client.is_connected,
            getattr(self.client, 'mtu_size', 'N/A'),
        )

        # Set up notification handlers for position characteristics
        position_chars = [
            ("back", LINAK_POSITION_BACK_UUID, LINAK_BACK_MAX_POSITION, LINAK_BACK_MAX_ANGLE),
            ("legs", LINAK_POSITION_LEG_UUID, LINAK_LEG_MAX_POSITION, LINAK_LEG_MAX_ANGLE),
        ]

        if motor_count > 2:
            position_chars.append(
                ("head", LINAK_POSITION_HEAD_UUID, LINAK_HEAD_MAX_POSITION, LINAK_HEAD_MAX_ANGLE)
            )
            _LOGGER.debug("Adding head position notifications (3+ motors)")

        if motor_count > 3:
            position_chars.append(
                ("feet", LINAK_POSITION_FEET_UUID, LINAK_FEET_MAX_POSITION, LINAK_FEET_MAX_ANGLE)
            )
            _LOGGER.debug("Adding feet position notifications (4 motors)")

        _LOGGER.debug(
            "Will attempt to subscribe to %d position characteristics: %s",
            len(position_chars),
            [name for name, _, _, _ in position_chars],
        )

        successful = []
        failed = []

        for name, uuid, max_pos, max_angle in position_chars:
            _LOGGER.debug(
                "Attempting to start notifications for %s (UUID: %s)...",
                name,
                uuid,
            )
            try:
                def make_handler(n: str, mp: int, ma: float, char_uuid: str):
                    def handler(_, data: bytearray) -> None:
                        _LOGGER.debug(
                            "Notification received for %s: raw_data=%s (%d bytes)",
                            n,
                            data.hex(),
                            len(data),
                        )
                        self.forward_raw_notification(char_uuid, bytes(data))
                        self._handle_position_data(n, data, mp, ma)
                    return handler

                await self.client.start_notify(uuid, make_handler(name, max_pos, max_angle, uuid))
                _LOGGER.debug(
                    "Successfully started notifications for %s position (UUID: %s, max_pos: %d, max_angle: %.1f°)",
                    name,
                    uuid,
                    max_pos,
                    max_angle,
                )
                successful.append(name)
            except BleakError as err:
                _LOGGER.debug(
                    "Could not start notifications for %s position (UUID: %s): %s (type: %s)",
                    name,
                    uuid,
                    err,
                    type(err).__name__,
                )
                failed.append(name)

        if successful:
            _LOGGER.info(
                "Position notifications active for: %s (%d/%d)",
                ", ".join(successful),
                len(successful),
                len(position_chars),
            )
        if failed:
            _LOGGER.warning(
                "Position notifications unavailable for: %s (bed may not support position feedback for these motors)",
                ", ".join(failed),
            )

    def _handle_position_data(
        self, name: str, data: bytearray, max_position: int, max_angle: float
    ) -> None:
        """Handle position notification data."""
        if len(data) < 2:
            _LOGGER.warning(
                "Received invalid position data for %s: expected 2+ bytes, got %d",
                name,
                len(data),
            )
            return

        # Little-endian 2-byte value
        raw_position = data[0] | (data[1] << 8)

        # Ignore clearly invalid values (e.g., uninitialized sensor data)
        # Values more than 10% above max are likely garbage/initialization values
        if raw_position > max_position * 1.1:
            _LOGGER.debug(
                "Ignoring invalid position data for %s: raw=%d exceeds max=%d by >10%%",
                name,
                raw_position,
                max_position,
            )
            return

        # Convert to angle (clamp to max if slightly over)
        if raw_position >= max_position:
            angle = max_angle
        else:
            angle = round(max_angle * (raw_position / max_position), 1)

        _LOGGER.debug(
            "Position update [%s]: raw=%d (max=%d), angle=%.1f° (max=%.1f°)",
            name,
            raw_position,
            max_position,
            angle,
            max_angle,
        )

        if self._notify_callback:
            self._notify_callback(name, angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        uuids = [
            LINAK_POSITION_BACK_UUID,
            LINAK_POSITION_LEG_UUID,
            LINAK_POSITION_HEAD_UUID,
            LINAK_POSITION_FEET_UUID,
        ]

        for uuid in uuids:
            try:
                await self.client.stop_notify(uuid)
            except BleakError:
                pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Actively read position data from all motor position characteristics.

        This provides a way to get current positions without relying solely
        on notifications, which may not always be sent by the bed.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot read positions: not connected")
            return

        position_chars = [
            ("back", LINAK_POSITION_BACK_UUID, LINAK_BACK_MAX_POSITION, LINAK_BACK_MAX_ANGLE),
            ("legs", LINAK_POSITION_LEG_UUID, LINAK_LEG_MAX_POSITION, LINAK_LEG_MAX_ANGLE),
        ]

        if motor_count > 2:
            position_chars.append(
                ("head", LINAK_POSITION_HEAD_UUID, LINAK_HEAD_MAX_POSITION, LINAK_HEAD_MAX_ANGLE)
            )

        if motor_count > 3:
            position_chars.append(
                ("feet", LINAK_POSITION_FEET_UUID, LINAK_FEET_MAX_POSITION, LINAK_FEET_MAX_ANGLE)
            )

        for name, uuid, max_pos, max_angle in position_chars:
            try:
                # Acquire BLE lock to prevent conflicts with concurrent writes
                async with self._ble_lock:
                    data = await self.client.read_gatt_char(uuid)
                if data:
                    _LOGGER.debug("Read position for %s: %s", name, data.hex())
                    self._handle_position_data(name, bytearray(data), max_pos, max_angle)
            except BleakError:
                _LOGGER.debug("Could not read position for %s", name)

    async def read_non_notifying_positions(self) -> None:
        """Read positions only for motors that don't support notifications.

        On Linak beds, only the back motor doesn't send notifications.
        This is used for efficient polling during movement.
        """
        if self.client is None or not self.client.is_connected:
            return

        # Only back needs polling - legs sends notifications
        try:
            # Acquire BLE lock to prevent conflicts with concurrent writes
            async with self._ble_lock:
                data = await self.client.read_gatt_char(LINAK_POSITION_BACK_UUID)
            if data:
                _LOGGER.debug("Polled back position: %s", data.hex())
                self._handle_position_data(
                    "back", bytearray(data), LINAK_BACK_MAX_POSITION, LINAK_BACK_MAX_ANGLE
                )
        except BleakError:
            _LOGGER.debug("Failed to poll back position (may be disconnected)")

    # Motor control methods
    # Linak protocol requires continuous command sending to keep motors moving.
    # Using 15 repeats @ 100ms = ~1.5 seconds of movement per press.
    # Motors auto-stop when commands stop arriving - no explicit STOP needed.

    async def _move_with_stop(self, move_command: bytes) -> None:
        """Execute a movement command.

        Linak beds auto-stop when commands stop arriving (typically within 200-500ms).
        We do NOT send an explicit STOP command because it can cause a brief reverse
        movement due to how the motor controller interprets the 0x00 command.
        See: https://github.com/kristofferR/ha-adjustable-bed/issues/45
        """
        await self.write_command(move_command, repeat_count=15, repeat_delay_ms=100)

    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(LinakCommands.MOVE_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(LinakCommands.MOVE_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(LinakCommands.MOVE_BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(LinakCommands.MOVE_BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(LinakCommands.MOVE_LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(LinakCommands.MOVE_LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(LinakCommands.MOVE_FEET_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(LinakCommands.MOVE_FEET_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(LinakCommands.MOVE_STOP, cancel_event=asyncio.Event())

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (uses memory 1 which is typically flat)."""
        # Memory preset 1 is typically configured as flat position on Linak beds
        await self.preset_memory(1)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: LinakCommands.PRESET_MEMORY_1,
            2: LinakCommands.PRESET_MEMORY_2,
            3: LinakCommands.PRESET_MEMORY_3,
            4: LinakCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            # Keep sending command while bed moves to preset position
            await self.write_command(command, repeat_count=100, repeat_delay_ms=300)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: LinakCommands.PROGRAM_MEMORY_1,
            2: LinakCommands.PROGRAM_MEMORY_2,
            3: LinakCommands.PROGRAM_MEMORY_3,
            4: LinakCommands.PROGRAM_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(command)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_ON)

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_OFF)

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self.write_command(LinakCommands.LIGHTS_TOGGLE)

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        await self.write_command(LinakCommands.MASSAGE_ALL_OFF)

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(LinakCommands.MASSAGE_ALL_TOGGLE)

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_TOGGLE)

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_TOGGLE)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_ALL_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_ALL_DOWN)

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(LinakCommands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        await self.write_command(LinakCommands.MASSAGE_MODE_STEP)

