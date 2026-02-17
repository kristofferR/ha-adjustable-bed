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

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakCharacteristicNotFoundError, BleakError

from ..const import (
    VIBRADORM_CBI_CHAR_UUID,
    VIBRADORM_COMMAND_CHAR_UUID,
    VIBRADORM_LIGHT_CHAR_UUID,
    VIBRADORM_NOTIFY_CHAR_UUID,
    VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

VIBRADORM_SERVICE_UUID_CANDIDATES = (
    VIBRADORM_SERVICE_UUID,
    VIBRADORM_SECONDARY_SERVICE_UUID,
)

VIBRADORM_COMMAND_UUID_CANDIDATES = (
    VIBRADORM_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_COMMAND_CHAR_UUID,
    VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID,
)


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

    # Vibration/massage commands (via CBI characteristic)
    VRT_ON_OFF: int = 0x34  # Toggle vibration on/off


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
        self._write_with_response: bool = False
        self._cbi_toggle: bool = False  # Alternates 0x0000/0x8000 per CBI write
        self._command_char_uuid: str = VIBRADORM_COMMAND_CHAR_UUID
        self._light_char_uuid: str = VIBRADORM_LIGHT_CHAR_UUID
        self._cbi_char_uuid: str = VIBRADORM_CBI_CHAR_UUID
        self._notify_char_uuid: str = VIBRADORM_NOTIFY_CHAR_UUID
        self._characteristics_initialized: bool = False

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._command_char_uuid

    @staticmethod
    def _get_characteristic_by_uuid(service: object, char_uuid: str) -> object | None:
        """Get characteristic from a service by UUID with broad compatibility."""
        get_characteristic = getattr(service, "get_characteristic", None)
        if callable(get_characteristic):
            try:
                characteristic = get_characteristic(char_uuid)
            except Exception:
                characteristic = None
            if characteristic is not None:
                return characteristic

        for characteristic in getattr(service, "characteristics", []):
            if str(characteristic.uuid).lower() == char_uuid.lower():
                return characteristic
        return None

    @staticmethod
    def _characteristic_properties(characteristic: object) -> set[str]:
        """Return normalized characteristic properties."""
        return {prop.lower() for prop in getattr(characteristic, "properties", [])}

    def _refresh_characteristics(self, *, force: bool = False) -> None:
        """Resolve runtime UUIDs for VMAT variants from discovered services."""
        if self._characteristics_initialized and not force:
            return

        client = self.client
        if client is None or client.services is None:
            return

        service_map = {str(service.uuid).lower(): service for service in client.services}
        candidate_services = [
            service_map[service_uuid.lower()]
            for service_uuid in VIBRADORM_SERVICE_UUID_CANDIDATES
            if service_uuid.lower() in service_map
        ]

        if not candidate_services:
            if force:
                _LOGGER.debug(
                    "No Vibradorm services found during characteristic refresh; using defaults"
                )
            return

        selected_command_char = None
        for char_uuid in VIBRADORM_COMMAND_UUID_CANDIDATES:
            for service in candidate_services:
                char = self._get_characteristic_by_uuid(service, char_uuid)
                if char is None:
                    continue
                props = self._characteristic_properties(char)
                if "write" in props or "write-without-response" in props:
                    selected_command_char = char
                    break
            if selected_command_char is not None:
                break

        if selected_command_char is None:
            excluded_uuids = {
                VIBRADORM_LIGHT_CHAR_UUID.lower(),
                VIBRADORM_CBI_CHAR_UUID.lower(),
                VIBRADORM_NOTIFY_CHAR_UUID.lower(),
            }
            for service in candidate_services:
                for char in getattr(service, "characteristics", []):
                    props = self._characteristic_properties(char)
                    if "write" not in props and "write-without-response" not in props:
                        continue
                    char_uuid = str(char.uuid).lower()
                    if char_uuid in excluded_uuids:
                        continue
                    selected_command_char = char
                    break
                if selected_command_char is not None:
                    break

        if selected_command_char is not None:
            resolved_command_uuid = str(selected_command_char.uuid)
            if resolved_command_uuid != self._command_char_uuid:
                _LOGGER.info(
                    "Resolved Vibradorm command characteristic: %s -> %s",
                    self._command_char_uuid,
                    resolved_command_uuid,
                )
            self._command_char_uuid = resolved_command_uuid

            props = self._characteristic_properties(selected_command_char)
            if "write" in props:
                self._write_with_response = True
            elif "write-without-response" in props:
                self._write_with_response = False

            _LOGGER.debug(
                "Vibradorm write mode: %s (characteristic: %s, properties: %s)",
                "with-response" if self._write_with_response else "without-response",
                self._command_char_uuid,
                getattr(selected_command_char, "properties", []),
            )

        for service in candidate_services:
            light_char = self._get_characteristic_by_uuid(service, VIBRADORM_LIGHT_CHAR_UUID)
            if light_char is not None:
                self._light_char_uuid = str(light_char.uuid)
                break

        for service in candidate_services:
            cbi_char = self._get_characteristic_by_uuid(service, VIBRADORM_CBI_CHAR_UUID)
            if cbi_char is not None:
                self._cbi_char_uuid = str(cbi_char.uuid)
                break

        for service in candidate_services:
            notify_char = self._get_characteristic_by_uuid(service, VIBRADORM_NOTIFY_CHAR_UUID)
            if notify_char is None:
                continue
            props = self._characteristic_properties(notify_char)
            if "notify" in props:
                self._notify_char_uuid = str(notify_char.uuid)
                break

        self._characteristics_initialized = True

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

        # Use coordinator's cancel event if none provided
        if cancel_event is None:
            cancel_event = self._coordinator._cancel_command

        self._refresh_characteristics()

        try:
            await self._write_gatt_with_retry(
                self._command_char_uuid,
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
                cancel_event=cancel_event,
                response=self._write_with_response,
            )
        except BleakCharacteristicNotFoundError:
            previous_char = self._command_char_uuid
            self._refresh_characteristics(force=True)

            if self._command_char_uuid == previous_char:
                _LOGGER.error(
                    "Vibradorm command characteristic %s not found; no fallback characteristic "
                    "available",
                    previous_char,
                )
                self.log_discovered_services(level=logging.INFO)
                raise

            _LOGGER.warning(
                "Vibradorm command characteristic %s not found, retrying with %s",
                previous_char,
                self._command_char_uuid,
            )
            await self._write_gatt_with_retry(
                self._command_char_uuid,
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

    async def _write_cbi_command(self, cmd: int) -> None:
        """Write a 2-byte command to the CBI characteristic with toggle bit.

        The toggle bit alternates between 0x0000 and 0x8000 on each send,
        matching the APK's MC.java behavior.
        """
        toggle = 0x8000 if self._cbi_toggle else 0x0000
        value = toggle | cmd
        data = value.to_bytes(2, byteorder="big")
        _LOGGER.debug(
            "Writing CBI command: 0x%04X (cmd=0x%02X, toggle=%s)",
            value,
            cmd,
            self._cbi_toggle,
        )
        self._refresh_characteristics()
        await self._write_gatt_with_retry(
            self._cbi_char_uuid,
            data,
            response=self._write_with_response,
        )
        self._cbi_toggle = not self._cbi_toggle

    def _handle_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle BLE notification data.

        Position notification format (from XMCMotorData.java):
        - Byte 0-1: Header/flags
        - Byte 2: Flags (bit 4 = init request, bit 6 = sync status)
        - Bytes 3-4: Motor 1 position (16-bit big-endian)
        - Bytes 5-6: Motor 2 position (16-bit big-endian)
        - Bytes 7-8: Motor 3 position (16-bit big-endian)
        - Bytes 9-10: Motor 4 position (16-bit big-endian)

        Position values are raw encoder counts, higher values = more raised.
        """
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))

        if len(data) < 8:
            _LOGGER.debug("Vibradorm notification too short: %s", data.hex())
            return

        # Parse motor positions (16-bit big-endian values)
        # Motor 1 = head/back, Motor 2 = legs
        motor1_pos = int.from_bytes(data[3:5], byteorder="big")
        motor2_pos = int.from_bytes(data[5:7], byteorder="big")

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

        self._refresh_characteristics(force=True)

        try:
            await self.client.start_notify(self._notify_char_uuid, self._handle_notification)
            _LOGGER.info("Started position notifications for Vibradorm bed")
        except BleakError as err:
            _LOGGER.warning("Failed to start Vibradorm notifications: %s", err)
            self.log_discovered_services(level=logging.INFO)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
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
        """Move feet up.

        On 4-motor beds, uses dedicated foot motor (FOOT_UP).
        On 2/3-motor beds, falls back to legs motor.
        """
        if self._coordinator.motor_count >= 4:
            await self._move_with_stop(VibradormCommands.FOOT_UP)
        else:
            await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down.

        On 4-motor beds, uses dedicated foot motor (FOOT_DOWN).
        On 2/3-motor beds, falls back to legs motor.
        """
        if self._coordinator.motor_count >= 4:
            await self._move_with_stop(VibradormCommands.FOOT_DOWN)
        else:
            await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        # STOP command stops all motors, works for both dedicated foot and legs
        await self._write_motor_command(
            VibradormCommands.STOP,
            repeat_count=1,
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._write_motor_command(
            VibradormCommands.STOP,
            repeat_count=1,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (all motors down).

        Presets work like motor commands - they trigger movement that
        continues until STOP is sent (based on APK analysis).
        """
        await self._move_with_stop(VibradormCommands.ALL_DOWN)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset position via CBI characteristic.

        Memory recall sends the slot command to the CBI characteristic
        with toggle bit, then STOP to halt after reaching position.

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
        try:
            await self._write_cbi_command(memory_commands[memory_num])
        finally:
            try:
                await self._write_motor_command(
                    VibradormCommands.STOP,
                    repeat_count=1,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP after memory recall")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory via CBI characteristic.

        APK sequence (MC.storeMemPos):
        1. Send STORE ×4 to CBI (with toggle bit)
        2. Send memory slot command to CBI (with toggle bit)
        3. Send STOP ×4

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
            _LOGGER.warning("Invalid memory program number: %d (supported: 1-4)", memory_num)
            return

        # Step 1: Send STORE ×4 to CBI
        for _ in range(4):
            await self._write_cbi_command(VibradormCommands.STORE)

        # Step 2: Send memory slot command to CBI
        await self._write_cbi_command(memory_commands[memory_num])

        # Step 3: Send STOP ×4
        for _ in range(4):
            await self._write_motor_command(
                VibradormCommands.STOP,
                repeat_count=1,
                cancel_event=asyncio.Event(),
            )

        _LOGGER.info("Saved position to memory slot %d", memory_num)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on lights."""
        # Light command format: [level, 0, timer]
        # level > 0 turns on, level = 0 turns off
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")

        self._refresh_characteristics()
        try:
            await self._write_gatt_with_retry(
                self._light_char_uuid,
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

        self._refresh_characteristics()
        try:
            await self._write_gatt_with_retry(
                self._light_char_uuid,
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

    # Massage/vibration methods (via CBI characteristic)
    async def massage_toggle(self) -> None:
        """Toggle vibration on/off via CBI characteristic."""
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")

        await self._write_cbi_command(VibradormCommands.VRT_ON_OFF)
