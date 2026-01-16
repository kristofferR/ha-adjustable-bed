"""Octo bed controller implementation.

Octo beds use a packet-based BLE protocol with the following format:
[0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]

The checksum is calculated as: ((sum_of_bytes XOR 0xff) + 1) & 0xff

Response packets use 0x80 as the first byte for checksum calculation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from bleak.exc import BleakError

from ..const import (
    OCTO_CHAR_UUID,
    OCTO_PIN_KEEPALIVE_INTERVAL,
    OCTO_STAR2_CHAR_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


# Motor bit masks
OCTO_MOTOR_HEAD = 0x02
OCTO_MOTOR_LEGS = 0x04

# Feature IDs
OCTO_FEATURE_PIN = 0x000003

# Feature discovery timeout
OCTO_FEATURE_TIMEOUT = 5.0


class OctoController(BedController):
    """Controller for Octo beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator, pin: str = "") -> None:
        """Initialize the Octo controller.

        Args:
            coordinator: The bed coordinator.
            pin: Optional PIN for authentication. Required for some Octo beds.
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._pin: str = pin
        self._keepalive_task: asyncio.Task[None] | None = None

        # Feature discovery state
        self._has_pin: bool | None = None  # None = not yet discovered
        self._pin_locked: bool | None = None
        self._features_loaded: asyncio.Event = asyncio.Event()

        _LOGGER.debug(
            "OctoController initialized (PIN %s)",
            "configured" if pin else "not configured",
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OCTO_CHAR_UUID

    def _calculate_checksum(self, packet: list[int]) -> int:
        """Calculate the Octo checksum.

        The checksum is: ((sum_of_bytes XOR 0xff) + 1) & 0xff
        """
        total = sum(packet) & 0xFF
        return ((total ^ 0xFF) + 1) & 0xFF

    def _build_packet(self, command: list[int], data: list[int] | None = None) -> bytes:
        """Build an Octo command packet.

        Format: [0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]
        """
        data = data or []
        data_len = len(data)

        # Build packet without checksum first
        packet = [
            0x40,  # Start byte
            command[0],
            command[1],
            (data_len >> 8) & 0xFF,  # Length high byte
            data_len & 0xFF,  # Length low byte
            0x00,  # Placeholder for checksum
            *data,
            0x40,  # End byte
        ]

        # Calculate and insert checksum at position 5
        packet[5] = self._calculate_checksum(packet)

        return bytes(packet)

    def _parse_response_packet(self, message: bytes) -> dict | None:
        """Parse a response packet from the bed.

        Format: [0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]
        Response checksum is calculated with 0x80 as the first byte.

        Returns:
            Dict with 'command' and 'data' keys, or None if invalid.
        """
        if len(message) < 7:
            return None

        if message[0] != 0x40 or message[-1] != 0x40:
            return None

        command = [message[1], message[2]]
        data_len = (message[3] << 8) + message[4]
        checksum = message[5]
        data = list(message[6:-1])

        if len(data) != data_len:
            _LOGGER.debug(
                "Packet data length mismatch: expected %d, got %d",
                data_len,
                len(data),
            )
            return None

        # Verify checksum (response uses 0x80 as first byte)
        check_data = [0x80, *command, message[3], message[4], *data]
        expected_checksum = self._calculate_checksum(check_data)
        if checksum != expected_checksum:
            _LOGGER.debug(
                "Checksum mismatch: expected 0x%02x, got 0x%02x",
                expected_checksum,
                checksum,
            )
            return None

        return {"command": command, "data": data}

    def _extract_feature_value_pair(self, data: list[int]) -> tuple[int, list[int]] | None:
        """Extract a feature ID and value from data bytes.

        Data format:
        - 3 bytes: feature ID (big-endian)
        - 1 byte: flag (unused)
        - 1 byte: skip length
        - N bytes: skipped data
        - 1 byte: unknown
        - remaining: value bytes

        Returns:
            Tuple of (feature_id, value_bytes) or None if invalid.
        """
        if len(data) < 6:
            return None

        # Extract 3-byte feature ID (big-endian)
        feature_id = (data[0] << 16) + (data[1] << 8) + data[2]

        # Skip flag byte (index 3)
        skip_length = data[4]

        # Calculate value start position: 5 (header) + skip_length + 1 (unknown byte)
        value_start = 5 + skip_length + 1
        if value_start > len(data):
            return None

        value = data[value_start:]
        return (feature_id, value)

    def _handle_feature_response(self, data: list[int]) -> None:
        """Process feature data from a 0x21 0x71 response."""
        result = self._extract_feature_value_pair(data)
        if result is None:
            _LOGGER.debug("Could not extract feature from data: %s", data)
            return

        feature_id, value = result
        _LOGGER.debug("Feature 0x%06x: %s", feature_id, value)

        if feature_id == OCTO_FEATURE_PIN:
            # value[0] = hasPin (0x01 if bed has PIN feature)
            # value[1] = pinLock (0x01 if unlocked, other if locked)
            self._has_pin = len(value) > 0 and value[0] == 0x01
            self._pin_locked = len(value) > 1 and value[1] != 0x01
            _LOGGER.info(
                "PIN feature detected: hasPin=%s, pinLocked=%s",
                self._has_pin,
                self._pin_locked,
            )
            self._features_loaded.set()

    def _on_notification(self, _sender: int, data: bytearray) -> None:
        """Handle BLE notifications from the bed."""
        _LOGGER.debug("Received notification: %s", data.hex())

        packet = self._parse_response_packet(bytes(data))
        if packet is None:
            return

        command = packet["command"]
        packet_data = packet["data"]

        # Handle feature response (0x21 0x71)
        if command[0] == 0x21 and command[1] == 0x71:
            self._handle_feature_response(packet_data)

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
            "Writing command to Octo bed: %s (repeat: %d, delay: %dms)",
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
                    OCTO_CHAR_UUID, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def _write_octo_command(
        self,
        command: list[int],
        data: list[int] | None = None,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Build and write an Octo command packet."""
        packet = self._build_packet(command, data)
        await self.write_command(packet, repeat_count, repeat_delay_ms, cancel_event)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for notifications.

        Octo beds don't support position notifications, but we use notifications
        for feature discovery responses.
        """
        self._notify_callback = callback
        if self.client is not None and self.client.is_connected:
            try:
                await self.client.start_notify(OCTO_CHAR_UUID, self._on_notification)
                _LOGGER.debug("Started Octo notifications for feature discovery")
            except BleakError as err:
                _LOGGER.debug("Could not start notifications: %s", err)

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        if self.client is not None and self.client.is_connected:
            try:
                await self.client.stop_notify(OCTO_CHAR_UUID)
            except BleakError:
                pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    @property
    def requires_pin(self) -> bool:
        """Check if the bed requires PIN authentication.

        Returns True if:
        - Features have been discovered AND hasPin is True AND pinLocked is True
        - OR features have not been discovered and a PIN is configured (fallback)
        """
        if self._has_pin is not None:
            # Features discovered - use actual detection
            return self._has_pin and (self._pin_locked or False)
        # Features not discovered - fall back to config
        return bool(self._pin)

    async def discover_features(self) -> bool:
        """Discover bed features including PIN requirement.

        Sends feature request command and waits for response.

        Returns:
            True if features were discovered, False on timeout.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot discover features: not connected")
            return False

        # Reset state
        self._features_loaded.clear()
        self._has_pin = None
        self._pin_locked = None

        _LOGGER.debug("Requesting bed features...")

        try:
            # Send feature request [0x20, 0x71]
            await self._write_octo_command(command=[0x20, 0x71])

            # Wait for response with timeout
            try:
                await asyncio.wait_for(
                    self._features_loaded.wait(),
                    timeout=OCTO_FEATURE_TIMEOUT,
                )
                _LOGGER.info(
                    "Feature discovery complete: hasPin=%s, pinLocked=%s",
                    self._has_pin,
                    self._pin_locked,
                )
                return True
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    "Feature discovery timed out - bed may not support feature query"
                )
                # Set defaults for beds that don't respond to feature query
                self._has_pin = bool(self._pin)  # Assume PIN needed if configured
                self._pin_locked = bool(self._pin)
                return False

        except BleakError as err:
            _LOGGER.warning("Feature discovery failed: %s", err)
            return False

    async def _move_motor(
        self, motor_bits: int, direction: str, cancel_event: asyncio.Event | None = None
    ) -> None:
        """Move a motor in the specified direction.

        Args:
            motor_bits: Bit mask for which motors to move (0x02=head, 0x04=legs)
            direction: "up" or "down"
            cancel_event: Optional event to cancel the command
        """
        # 0x70 = open (up), 0x71 = close (down)
        direction_byte = 0x70 if direction == "up" else 0x71
        await self._write_octo_command(
            command=[0x02, direction_byte],
            data=[motor_bits],
            repeat_count=25,
            repeat_delay_ms=200,
            cancel_event=cancel_event,
        )

    async def _stop_motors(self) -> None:
        """Send stop command to all motors."""
        await self._write_octo_command(
            command=[0x02, 0x73],
            cancel_event=asyncio.Event(),  # Don't cancel stop commands
        )

    async def _move_with_stop(self, motor_bits: int, direction: str) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self._move_motor(motor_bits, direction)
        finally:
            await self._stop_motors()

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head motor up."""
        await self._move_with_stop(OCTO_MOTOR_HEAD, "up")

    async def move_head_down(self) -> None:
        """Move head motor down."""
        await self._move_with_stop(OCTO_MOTOR_HEAD, "down")

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._stop_motors()

    async def move_back_up(self) -> None:
        """Move back up (same as head for Octo)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Octo)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up."""
        await self._move_with_stop(OCTO_MOTOR_LEGS, "up")

    async def move_legs_down(self) -> None:
        """Move legs motor down."""
        await self._move_with_stop(OCTO_MOTOR_LEGS, "down")

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._stop_motors()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Octo)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Octo)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._stop_motors()

    # Preset methods - Octo doesn't have built-in presets
    async def preset_flat(self) -> None:
        """Go to flat position.

        Octo doesn't have a flat preset, so we move both motors down.
        """
        # Move both head and legs down simultaneously
        await self._move_with_stop(OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS, "down")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Octo doesn't support memory presets.
        """
        _LOGGER.warning("Octo beds don't support memory presets")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Octo doesn't support memory presets.
        """
        _LOGGER.warning("Octo beds don't support memory presets")

    # Light control
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        await self._write_octo_command(
            command=[0x20, 0x72],
            data=[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x01],
        )

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        await self._write_octo_command(
            command=[0x20, 0x72],
            data=[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x00],
        )

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights.

        Octo tracks state internally, but we don't have access to it.
        This is a best-effort toggle that turns lights on.
        """
        await self.lights_on()

    # PIN authentication and keep-alive methods

    async def send_pin(self) -> None:
        """Send PIN authentication command.

        The PIN command uses [0x20, 0x43] followed by the PIN digits as integers.
        This must be sent periodically to maintain the BLE connection.

        Only sends PIN if the bed requires it (detected via feature discovery
        or assumed if PIN is configured but features not discovered).
        """
        if not self._pin:
            _LOGGER.debug("No PIN configured, skipping PIN authentication")
            return

        if not self.requires_pin:
            _LOGGER.debug("Bed does not require PIN authentication")
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot send PIN: not connected")
            return

        try:
            # Convert PIN string to list of integer digits
            # Validation should happen in config flow, but add defensive check
            if not self._pin.isdigit():
                _LOGGER.error("Invalid PIN: must contain only digits")
                return
            pin_data = [int(c) for c in self._pin]
            _LOGGER.debug("Sending PIN authentication (%d digits)", len(pin_data))
            await self._write_octo_command(
                command=[0x20, 0x43],
                data=pin_data,
            )
            _LOGGER.debug("PIN authentication sent successfully")
        except (ValueError, BleakError) as err:
            _LOGGER.warning("Failed to send PIN: %s", err)

    async def start_keepalive(self) -> None:
        """Start the PIN keep-alive loop.

        Octo beds drop BLE connection after ~30 seconds without PIN re-authentication.
        This starts a background task to periodically send the PIN.

        Only starts if the bed requires PIN authentication.
        """
        if not self._pin:
            _LOGGER.debug("No PIN configured, keep-alive not needed")
            return

        if not self.requires_pin:
            _LOGGER.debug("Bed does not require PIN, keep-alive not needed")
            return

        if self._keepalive_task is not None:
            _LOGGER.debug("Keep-alive already running")
            return

        _LOGGER.info(
            "Starting PIN keep-alive (interval: %ds)",
            OCTO_PIN_KEEPALIVE_INTERVAL,
        )
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def stop_keepalive(self) -> None:
        """Stop the keep-alive loop."""
        if self._keepalive_task is None:
            return

        _LOGGER.debug("Stopping PIN keep-alive")
        self._keepalive_task.cancel()
        try:
            await self._keepalive_task
        except asyncio.CancelledError:
            pass
        self._keepalive_task = None
        _LOGGER.debug("PIN keep-alive stopped")

    async def _keepalive_loop(self) -> None:
        """Periodically send PIN to maintain connection."""
        while True:
            try:
                await asyncio.sleep(OCTO_PIN_KEEPALIVE_INTERVAL)
                if self.client is not None and self.client.is_connected:
                    _LOGGER.debug("Sending keep-alive PIN")
                    # Use coordinator's command execution for proper locking
                    await self._coordinator.async_execute_controller_command(
                        lambda c: c.send_pin(),
                        cancel_running=False,
                    )
                else:
                    _LOGGER.debug("Keep-alive: not connected, skipping PIN send")
            except asyncio.CancelledError:
                _LOGGER.debug("Keep-alive loop cancelled")
                break
            except Exception as err:
                _LOGGER.warning("Keep-alive PIN send failed: %s", err)


class OctoStar2Controller(BedController):
    """Controller for Octo Remote Star2 beds.

    Star2 uses a different protocol with fixed command bytes:
    - Service UUID: aa5c
    - Characteristic UUID: 5a55
    - Packet format: starts with 0x68, ends with 0x16
    """

    # Star2 fixed command bytes
    # Protocol reverse-engineered by goedh452
    # (https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10)
    # Format: starts with 0x68, ends with 0x16
    CMD_HEAD_UP = bytes([0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x36, 0x31, 0x38, 0x16])
    CMD_HEAD_DOWN = bytes([0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x39, 0x31, 0x3B, 0x16])
    CMD_FEET_UP = bytes([0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x34, 0x31, 0x36, 0x16])
    CMD_FEET_DOWN = bytes([0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x37, 0x31, 0x39, 0x16])
    CMD_BOTH_UP = bytes([0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x32, 0x37, 0x31, 0x3B, 0x16])
    CMD_BOTH_DOWN = bytes([0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x32, 0x38, 0x31, 0x3C, 0x16])

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Octo Star2 controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("OctoStar2Controller initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OCTO_STAR2_CHAR_UUID

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
            "Writing command to Octo Star2 bed: %s (repeat: %d, delay: %dms)",
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
                    OCTO_STAR2_CHAR_UUID, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for notifications.

        Star2 doesn't support position notifications, so this only stores the callback.
        """
        _LOGGER.debug(
            "start_notify called for OctoStar2Controller - notifications not supported"
        )
        self._notify_callback = callback

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        _LOGGER.debug(
            "stop_notify called for OctoStar2Controller - notifications not supported"
        )
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> list[float]:
        """Read current position data.

        Star2 doesn't support position feedback.

        Args:
            motor_count: Number of motors to read positions for (unused).

        Returns:
            Empty list as position feedback is not supported.
        """
        _LOGGER.debug(
            "read_positions called for OctoStar2Controller with motor_count=%d "
            "- position feedback not supported",
            motor_count,
        )
        return []

    async def _send_stop(self) -> None:
        """Send stop command.

        Star2 protocol doesn't have an explicit stop command.
        Motors stop when commands stop being sent.
        """
        _LOGGER.debug(
            "Stop requested for OctoStar2Controller - Star2 has no explicit stop command, "
            "motors stop when commands cease"
        )

    # Motor control methods using fixed Star2 commands
    async def move_head_up(self) -> None:
        """Move head motor up."""
        try:
            await self.write_command(
                self.CMD_HEAD_UP,
                repeat_count=25,
                repeat_delay_ms=200,
            )
        finally:
            await self._send_stop()

    async def move_head_down(self) -> None:
        """Move head motor down."""
        try:
            await self.write_command(
                self.CMD_HEAD_DOWN,
                repeat_count=25,
                repeat_delay_ms=200,
            )
        finally:
            await self._send_stop()

    async def move_head_stop(self) -> None:
        """Stop head motor.

        Star2 doesn't have explicit stop - motors stop when commands cease.
        """
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back up (same as head for Star2)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Star2)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up."""
        try:
            await self.write_command(
                self.CMD_FEET_UP,
                repeat_count=25,
                repeat_delay_ms=200,
            )
        finally:
            await self._send_stop()

    async def move_legs_down(self) -> None:
        """Move legs motor down."""
        try:
            await self.write_command(
                self.CMD_FEET_DOWN,
                repeat_count=25,
                repeat_delay_ms=200,
            )
        finally:
            await self._send_stop()

    async def move_legs_stop(self) -> None:
        """Stop legs motor.

        Star2 doesn't have explicit stop - motors stop when commands cease.
        """
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Star2)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Star2)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors.

        Star2 doesn't have explicit stop command - motors stop when commands cease.
        """
        await self._send_stop()

    async def preset_flat(self) -> None:
        """Go to flat position by moving both motors down."""
        try:
            await self.write_command(
                self.CMD_BOTH_DOWN,
                repeat_count=25,
                repeat_delay_ms=200,
            )
        finally:
            await self._send_stop()

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Star2 doesn't support memory presets.

        Args:
            memory_num: Memory slot number (unused - feature not supported).
        """
        _LOGGER.warning(
            "Octo Star2 beds don't support memory presets (requested memory_num=%d)",
            memory_num,
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Star2 doesn't support memory presets.

        Args:
            memory_num: Memory slot number (unused - feature not supported).
        """
        _LOGGER.warning(
            "Octo Star2 beds don't support programming memory presets "
            "(requested memory_num=%d)",
            memory_num,
        )
