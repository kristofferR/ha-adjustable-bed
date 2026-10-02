"""Jensen LinOn bed controller.

Protocol from the clean-room APK Protocol Audit of ``air.no.jensen.adjustablesleep``
2.0.37 (106). The Jensen Adjustable Sleep app drives LinOn beds ("Adjustable Bed"
and "Jensen Bed" names) through the LinonPI services the Svane controller uses,
but with its own one-byte frames. See docs/beds/jensen.md.

The app never subscribes to LinOn notifications, so this profile has no
position feedback, and its memory and light-intensity paths never reach the bed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from bleak.backends.characteristic import BleakGATTCharacteristic
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
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# The app resends a held frame, or steps a combined-motion sequence, every 800 ms.
HOLD_INTERVAL_MS = 800

_MOTOR_SERVICES = {
    "back": SVANE_HEAD_SERVICE_UUID,
    "legs": SVANE_FEET_SERVICE_UUID,
}


class JensenLinonCommands:
    """One-byte LinOn frames, each written to a per-function characteristic."""

    MOVE = bytes([0x01])
    STOP = bytes([0xFF])
    # Written to both position characteristics: go to position zero.
    FLAT = bytes([0x00])

    @staticmethod
    def light(on: bool) -> bytes:
        """Build the under-bed light frame: state, timer seconds (none), 0."""
        return bytes([0x01 if on else 0x00, 0x00, 0x00])


def _hold_steps(duration_ms: int) -> int:
    """Return the MOVE writes that cover ``duration_ms``, one per 800 ms."""
    return max(1, -(-duration_ms // HOLD_INTERVAL_MS))


def _direction_char(up: bool) -> str:
    return SVANE_CHAR_UP_UUID if up else SVANE_CHAR_DOWN_UUID


class JensenLinonController(BedController):
    """Controller for Jensen LinOn beds (Jensen Adjustable Sleep app profile)."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Jensen LinOn controller."""
        super().__init__(coordinator)
        # The bed does not report light state, so track what was last sent.
        self._light_on = False

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
            raise ConnectionError(f"Characteristic {char_uuid} not found in service {service_uuid}")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing %s to service %s char %s (repeat: %d, delay: %dms, response=True)",
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

    @property
    def control_characteristic_uuid(self) -> str:
        return SVANE_CHAR_UP_UUID

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    async def move_head_up(self) -> None:
        await self._move_motor(SVANE_HEAD_SERVICE_UUID, SVANE_CHAR_UP_UUID)

    async def move_head_down(self) -> None:
        await self._move_motor(SVANE_HEAD_SERVICE_UUID, SVANE_CHAR_DOWN_UUID)

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move_motor(SVANE_FEET_SERVICE_UUID, SVANE_CHAR_UP_UUID)

    async def move_legs_down(self) -> None:
        await self._move_motor(SVANE_FEET_SERVICE_UUID, SVANE_CHAR_DOWN_UUID)

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    # Capabilities
    @property
    def supports_preset_flat(self) -> bool:
        """Return True - the app's flat writes zero to both position characteristics."""
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        """Return False - the Svane position preset is not part of this app."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return False - the app's LinOn favourite recall writes nothing."""
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return 0 - no memory slots reach the bed."""
        return 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return False - no memory slots reach the bed."""
        return False

    @property
    def supports_light_level_control(self) -> bool:
        """Return False - the app's intensity slider never writes a frame."""
        return False

    @property
    def supports_simultaneous_movement(self) -> bool:
        """Return True - the app alternates head and foot frames."""
        return True

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        """Return the two sections combined motion can drive."""
        return ("back", "legs")

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Keep the configured hold duration at the app's 800 ms cadence."""
        pulse_count, pulse_delay = super().motor_pulse_settings()
        return _hold_steps(max(0, pulse_count - 1) * pulse_delay), HOLD_INTERVAL_MS

    # Notifications: the app never subscribes, so there is nothing to follow.
    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Keep the callback; LinOn reports are not used."""
        self._notify_callback = callback

    async def stop_notify(self) -> None:
        """Nothing to stop."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """LinOn beds have no position feedback in this profile."""
        del motor_count

    # Movement
    async def _hold_sequence(self, steps: Sequence[tuple[str, str]], repeat_count: int) -> None:
        """Write MOVE through ``steps`` in turn every 800 ms, then always STOP.

        Each write is held for a full interval, so the last step of a combined
        move runs as long as the others before STOP.
        """
        cancel_event = self._coordinator.cancel_command
        try:
            for index in range(repeat_count):
                if cancel_event.is_set():
                    break
                service_uuid, char_uuid = steps[index % len(steps)]
                await self._write_to_service_char(
                    service_uuid, char_uuid, JensenLinonCommands.MOVE, cancel_event=cancel_event
                )
                await asyncio.sleep(HOLD_INTERVAL_MS / 1000)
        except BaseException:
            # Release the bed, but let the original error or cancellation propagate.
            try:
                await asyncio.shield(self._send_stop())
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send Jensen LinOn STOP after an interrupted move")
            raise
        await self._send_stop()

    async def _move_motor(self, service_uuid: str, char_uuid: str) -> None:
        """Hold one direction characteristic, then STOP."""
        pulse_count, _ = self.motor_pulse_settings()
        await self._hold_sequence(((service_uuid, char_uuid),), pulse_count)

    async def _send_stop(self) -> None:
        """Write STOP to the head, then the foot, up characteristic.

        The foot STOP is attempted even when the head write fails; the first
        failure is raised afterwards.
        """
        cancel_event = asyncio.Event()  # STOP must not be suppressed by a cancel
        first_error: BleakError | ConnectionError | None = None
        for service_uuid in (SVANE_HEAD_SERVICE_UUID, SVANE_FEET_SERVICE_UUID):
            try:
                await self._write_to_service_char(
                    service_uuid,
                    SVANE_CHAR_UP_UUID,
                    JensenLinonCommands.STOP,
                    cancel_event=cancel_event,
                )
            except (BleakError, ConnectionError) as err:
                first_error = first_error or err
        if first_error is not None:
            raise first_error

    async def move_head_stop(self) -> None:
        """Stop both motors; the app has one STOP for the bed."""
        await self._send_stop()

    async def move_legs_stop(self) -> None:
        """Stop both motors; the app has one STOP for the bed."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop both motors."""
        await self._send_stop()

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        """Alternate head and foot frames, as the app's combined controls do."""
        directions = {first_axis: first_up, second_axis: second_up}
        if set(directions) != set(self.simultaneous_movement_axes):
            raise ValueError("Jensen LinOn beds combine only the back and legs sections")
        repeat_count, _ = self.motor_pulse_settings()
        if duration_ms is not None:
            repeat_count = _hold_steps(duration_ms)
        steps = tuple(
            (_MOTOR_SERVICES[axis], _direction_char(directions[axis])) for axis in ("back", "legs")
        )
        await self._hold_sequence(steps, max(2, repeat_count))

    # Presets
    async def preset_flat(self) -> None:
        """Send position zero to the head, then the foot, motor.

        The motors then move on their own, so an interrupted flat sends STOP.
        """
        cancel_event = self._coordinator.cancel_command
        try:
            for service_uuid in (SVANE_HEAD_SERVICE_UUID, SVANE_FEET_SERVICE_UUID):
                if cancel_event.is_set():
                    break
                await self._write_to_service_char(
                    service_uuid, SVANE_CHAR_POSITION_UUID, JensenLinonCommands.FLAT
                )
        except BaseException:
            try:
                await asyncio.shield(self._send_stop())
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send Jensen LinOn STOP after an interrupted flat")
            raise
        if cancel_event.is_set():
            await self._send_stop()

    async def preset_zero_g(self) -> None:
        """Not part of the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no position preset")

    async def preset_memory(self, memory_num: int) -> None:
        """Not reachable in the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no memory recall")

    async def program_memory(self, memory_num: int) -> None:
        """Not reachable in the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no memory programming")

    # Lights
    async def _set_light(self, on: bool) -> None:
        await self._write_to_service_char(
            SVANE_LIGHT_SERVICE_UUID, SVANE_LIGHT_ON_OFF_UUID, JensenLinonCommands.light(on)
        )
        self._light_on = on
        self.forward_controller_state_updates({"under_bed_lights_on": on})

    async def lights_on(self) -> None:
        """Turn the under-bed light on."""
        await self._set_light(True)

    async def lights_off(self) -> None:
        """Turn the under-bed light off."""
        await self._set_light(False)

    async def lights_toggle(self) -> None:
        """Toggle the under-bed light."""
        await self._set_light(not self._light_on)

    async def set_light_level(self, level: int) -> None:
        """Not reachable in the Jensen LinOn profile."""
        raise NotImplementedError("Jensen LinOn beds have no light level control")

    def get_light_state(self) -> dict[str, Any]:
        """Return the light state this integration last sent."""
        return {"is_on": self._light_on}
