"""Jensen bed controller implementation.

Protocol reverse-engineered from com.hilding.jbg_ble APK.

Jensen beds (JMC400 / LinON Entry) use a simple 6-byte command format
with no checksum. The bed supports dynamic feature detection via the
CONFIG_READ_ALL command, which returns feature flags indicating
available capabilities (lights, massage, fan, etc.).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import IntFlag
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import JENSEN_CHAR_UUID, JENSEN_SERVICE_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Position calibration constants (from APK analysis)
# Head: 1 = flat (0%), ~30500 = max raised (~100%)
HEAD_POS_FLAT = 1
HEAD_POS_MAX = 30500

# Foot: values appear inverted - higher values may indicate flat
# FLATTEN command uses 0x60EA (24810), ComfortSequenze shows 60000
# Using 60000 as flat for now - needs hardware testing
FOOT_POS_FLAT = 60000
FOOT_POS_MAX = 1  # Inverted: lower value = more raised


class JensenCommands:
    """Jensen 6-byte command constants.

    Command format: [cmd_type, param1, param2, param3, param4, param5]

    Command types:
    - 0x0A: Config commands (read capabilities)
    - 0x10: Motor commands (movement, presets, memory)
    - 0x12: Massage commands
    - 0x13: Light commands
    """

    # Config commands (0x0A prefix)
    CONFIG_READ_ALL = bytes([0x0A, 0x00, 0x00, 0x00, 0x00, 0x00])

    # Motor commands (0x10 prefix)
    MOTOR_STOP = bytes([0x10, 0x00, 0x00, 0x00, 0x00, 0x00])
    MOTOR_HEAD_UP = bytes([0x10, 0x01, 0x00, 0x00, 0x00, 0x00])
    MOTOR_HEAD_DOWN = bytes([0x10, 0x02, 0x00, 0x00, 0x00, 0x00])
    MOTOR_FOOT_UP = bytes([0x10, 0x10, 0x00, 0x00, 0x00, 0x00])
    MOTOR_FOOT_DOWN = bytes([0x10, 0x20, 0x00, 0x00, 0x00, 0x00])

    # Preset commands (0x10 prefix with special param1)
    PRESET_FLAT = bytes([0x10, 0x81, 0x00, 0x00, 0x00, 0x00])
    PRESET_MEMORY_SAVE = bytes([0x10, 0x40, 0x00, 0x00, 0x00, 0x00])
    PRESET_MEMORY_RECALL = bytes([0x10, 0x80, 0x00, 0x00, 0x00, 0x00])

    # Position commands
    READ_POSITION = bytes([0x10, 0xFF, 0x00, 0x00, 0x00, 0x00])
    GET_STATUS = bytes([0x10, 0xFE, 0x00, 0x00, 0x00, 0x00])

    # Massage commands (0x12 prefix)
    MASSAGE_OFF = bytes([0x12, 0x00, 0x00, 0x00, 0x00, 0x00])
    MASSAGE_HEAD_ON = bytes([0x12, 0x05, 0x00, 0x00, 0x00, 0x00])
    MASSAGE_FOOT_ON = bytes([0x12, 0x00, 0x05, 0x00, 0x00, 0x00])
    MASSAGE_BOTH_ON = bytes([0x12, 0x05, 0x05, 0x00, 0x00, 0x00])

    # Light commands (0x13 prefix)
    # Format: [0x13, light_id, brightness, 0x00, 0x00, 0x50]
    LIGHT_MAIN_ON = bytes([0x13, 0x00, 0xFF, 0x00, 0x00, 0x50])
    LIGHT_MAIN_OFF = bytes([0x13, 0x00, 0x00, 0x00, 0x00, 0x50])
    LIGHT_UNDERBED_ON = bytes([0x13, 0x02, 0xFF, 0x00, 0x00, 0x50])
    LIGHT_UNDERBED_OFF = bytes([0x13, 0x02, 0x00, 0x00, 0x00, 0x50])


class JensenFeatureFlags(IntFlag):
    """Feature flags from CONFIG_READ_ALL response byte 2 (CONFIG2).

    These flags indicate which optional features the bed supports.
    """

    NONE = 0
    MASSAGE_HEAD = 0x01  # Bit 0: Head massage motor
    MASSAGE_FOOT = 0x02  # Bit 1: Foot massage motor
    LIGHT = 0x04  # Bit 2: Main light
    FAN = 0x10  # Bit 4: Fan
    LIGHT_UNDERBED = 0x40  # Bit 6: Under-bed light


class JensenController(BedController):
    """Controller for Jensen beds (JMC400 / LinON Entry).

    Jensen beds use a simple 6-byte command protocol with no checksum.
    Optional features (lights, massage, fan) are detected dynamically
    by querying the bed's configuration.
    """

    # Default PIN for Jensen beds
    DEFAULT_PIN: str = "3060"

    def __init__(self, coordinator: AdjustableBedCoordinator, pin: str = "") -> None:
        """Initialize the Jensen controller.

        Args:
            coordinator: The coordinator managing this controller.
            pin: 4-digit PIN for bed authentication. Defaults to "3060" if empty.
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._features: JensenFeatureFlags = JensenFeatureFlags.NONE
        self._config_loaded: bool = False
        # Config query state (used by query_config and _handle_notification)
        self._config_received: asyncio.Event | None = None
        self._config_data: bytes | None = None
        # Note: Light and massage state is tracked locally. It may become out of sync
        # if the bed is controlled via remote or the app, or after HA restarts.
        # The Jensen protocol does not support querying actual state.
        self._lights_on: bool = False
        self._underbed_lights_on: bool = False
        self._massage_head_on: bool = False
        self._massage_foot_on: bool = False

        # PIN for authentication - use provided PIN or default
        self._pin: str = pin if pin else self.DEFAULT_PIN
        _LOGGER.debug("JensenController initialized with PIN: %s", "*" * len(self._pin))

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return JENSEN_CHAR_UUID

    def _build_pin_unlock_command(self) -> bytes:
        """Build the PIN unlock command from the configured PIN.

        PIN command format: [0x1E, digit1, digit2, digit3, digit4, 0x00]
        Each digit is its numeric value (not ASCII code).

        Sanitizes the PIN by stripping whitespace and keeping only digits.
        Falls back to "0000" if the PIN is invalid.
        """
        # Sanitize: strip whitespace and keep only digits
        sanitized = "".join(c for c in self._pin.strip() if c.isdigit())

        # Ensure exactly 4 digits (pad with 0s or truncate)
        if not sanitized:
            _LOGGER.warning("Invalid Jensen PIN configured, using default '%s'", self.DEFAULT_PIN)
            sanitized = self.DEFAULT_PIN
        pin_digits = sanitized.ljust(4, "0")[:4]

        return bytes([0x1E, int(pin_digits[0]), int(pin_digits[1]),
                      int(pin_digits[2]), int(pin_digits[3]), 0x00])

    # Capability properties
    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Jensen beds have a dedicated flat command."""
        return True

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Jensen beds support memory presets."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return 1 - Jensen beds support a single memory slot."""
        return 1

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Jensen beds support programming the memory position."""
        return True

    @property
    def supports_lights(self) -> bool:
        """Return True if bed has main light (determined dynamically)."""
        return bool(self._features & JensenFeatureFlags.LIGHT)

    @property
    def supports_under_bed_lights(self) -> bool:
        """Return True if bed has under-bed light (determined dynamically)."""
        return bool(self._features & JensenFeatureFlags.LIGHT_UNDERBED)

    @property
    def has_massage(self) -> bool:
        """Return True if bed has any massage motor (determined dynamically)."""
        return bool(
            self._features & (JensenFeatureFlags.MASSAGE_HEAD | JensenFeatureFlags.MASSAGE_FOOT)
        )

    @property
    def has_massage_head(self) -> bool:
        """Return True if bed has head massage motor."""
        return bool(self._features & JensenFeatureFlags.MASSAGE_HEAD)

    @property
    def has_massage_foot(self) -> bool:
        """Return True if bed has foot massage motor."""
        return bool(self._features & JensenFeatureFlags.MASSAGE_FOOT)

    @property
    def has_fan(self) -> bool:
        """Return True if bed has fan (determined dynamically)."""
        return bool(self._features & JensenFeatureFlags.FAN)

    async def query_config(self) -> None:
        """Query bed capabilities after connection.

        Sends CONFIG_READ_ALL command and parses the response to
        determine which optional features the bed supports.

        Note: This method uses the main notification handler (_handle_notification)
        rather than starting its own, to avoid interfering with position notifications
        that may already be active.
        """
        if self._config_loaded:
            _LOGGER.debug("Jensen config already loaded, skipping query")
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot query config: not connected")
            return

        _LOGGER.debug("Querying Jensen bed configuration...")

        # Set up event to wait for config response via _handle_notification
        self._config_received = asyncio.Event()
        self._config_data: bytes | None = None

        try:
            # Send config read command - response comes via existing notification handler
            await self.client.write_gatt_char(
                JENSEN_CHAR_UUID, JensenCommands.CONFIG_READ_ALL, response=True
            )

            # Wait for response (with timeout)
            try:
                await asyncio.wait_for(self._config_received.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for config response, assuming full features")
                # Default to all features enabled if we can't query
                self._features = JensenFeatureFlags(
                    JensenFeatureFlags.MASSAGE_HEAD
                    | JensenFeatureFlags.MASSAGE_FOOT
                    | JensenFeatureFlags.LIGHT
                    | JensenFeatureFlags.LIGHT_UNDERBED
                )
                return

            # Parse config response
            if self._config_data is not None:
                data = self._config_data
                if len(data) >= 3:
                    # Byte 2 contains feature flags (CONFIG2)
                    self._features = JensenFeatureFlags(data[2])
                    _LOGGER.info(
                        "Jensen bed features detected: %s (raw: 0x%02X)",
                        self._features,
                        data[2],
                    )
                else:
                    _LOGGER.warning("Config response too short: %s", data.hex())
                    self._features = JensenFeatureFlags.NONE
            else:
                _LOGGER.warning("No config data received")
                self._features = JensenFeatureFlags.NONE

        except BleakError as err:
            _LOGGER.warning("Failed to query config: %s", err)
            self._features = JensenFeatureFlags.NONE
        finally:
            self._config_loaded = True
            # Clean up temporary attributes
            self._config_received = None
            self._config_data = None

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
            "Writing command to Jensen bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                await self.client.write_gatt_char(JENSEN_CHAR_UUID, command, response=True)
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    def _raw_to_percentage(self, raw_value: int, motor: str) -> float:
        """Convert raw position value to percentage (0-100).

        Args:
            raw_value: Raw 16-bit position value from the bed
            motor: Motor name ("head" or "foot")

        Returns:
            Position as percentage (0 = flat, 100 = max raised)
        """
        if motor == "head":
            # Head: 1 = flat (0%), ~30500 = max (100%)
            if raw_value <= HEAD_POS_FLAT:
                return 0.0
            if raw_value >= HEAD_POS_MAX:
                return 100.0
            return min(100.0, (raw_value - HEAD_POS_FLAT) / (HEAD_POS_MAX - HEAD_POS_FLAT) * 100)
        else:
            # Foot: values are inverted (higher = flat, lower = raised)
            # 60000 = flat (0%), 1 = max (100%)
            if raw_value >= FOOT_POS_FLAT:
                return 0.0
            if raw_value <= FOOT_POS_MAX:
                return 100.0
            return min(100.0, (FOOT_POS_FLAT - raw_value) / (FOOT_POS_FLAT - FOOT_POS_MAX) * 100)

    def _handle_notification(self, _sender: int, data: bytearray) -> None:
        """Handle BLE notification data.

        Parses position responses with format:
        [0x10, ??, headMSB, headLSB, footMSB, footLSB]
        """
        self.forward_raw_notification(JENSEN_CHAR_UUID, bytes(data))

        if len(data) < 6:
            _LOGGER.debug("Jensen notification too short: %s", data.hex())
            return

        cmd_type = data[0]

        if cmd_type == 0x10:
            # Motor/position response: [10, ??, headMSB, headLSB, footMSB, footLSB]
            head_pos = (data[2] << 8) | data[3]
            foot_pos = (data[4] << 8) | data[5]

            _LOGGER.debug(
                "Jensen position update: head_raw=%d, foot_raw=%d",
                head_pos,
                foot_pos,
            )

            if self._notify_callback:
                head_pct = self._raw_to_percentage(head_pos, "head")
                foot_pct = self._raw_to_percentage(foot_pos, "foot")

                _LOGGER.debug(
                    "Jensen position percentages: head=%.1f%%, foot=%.1f%%",
                    head_pct,
                    foot_pct,
                )

                # Map to standard motor names (back and legs)
                self._notify_callback("back", head_pct)
                self._notify_callback("legs", foot_pct)

        elif cmd_type == 0x0A:
            # Config response - signal query_config if waiting
            _LOGGER.debug("Jensen config notification: %s", data.hex())
            if self._config_received is not None:
                self._config_data = bytes(data)
                self._config_received.set()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for position notifications.

        The app ALWAYS enables notifications before sending any commands.
        This method must be called even when angle sensing is disabled, because
        Jensen beds require the notification handler to be active for commands to work.
        """
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start Jensen notifications: not connected")
            return

        # Log discovered services and characteristic properties for debugging
        if self.client.services:
            for service in self.client.services:
                if str(service.uuid).lower() == JENSEN_SERVICE_UUID.lower():
                    _LOGGER.info("Found Jensen service: %s", service.uuid)
                    for char in service.characteristics:
                        if str(char.uuid).lower() == JENSEN_CHAR_UUID.lower():
                            _LOGGER.info(
                                "Found Jensen characteristic: %s, properties: %s",
                                char.uuid,
                                char.properties,
                            )

        try:
            # Always enable notifications - the app does this before any commands
            await self.client.start_notify(JENSEN_CHAR_UUID, self._handle_notification)
            _LOGGER.info("Started position notifications for Jensen bed")

            # Send PIN unlock command IMMEDIATELY after notifications are enabled
            # The app ALWAYS does this before any other commands (config, position, etc.)
            _LOGGER.debug("Sending Jensen PIN unlock command")
            await self.client.write_gatt_char(
                JENSEN_CHAR_UUID, self._build_pin_unlock_command(), response=True
            )

            # Request initial position reading only if angle sensing is enabled
            if callback is not None:
                await self.read_positions()

        except BleakError as err:
            _LOGGER.warning("Failed to start Jensen notifications: %s", err)
            # Log all available services for debugging
            self.log_discovered_services(level=logging.INFO)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(JENSEN_CHAR_UUID)
            _LOGGER.debug("Stopped Jensen position notifications")
        except BleakError:
            pass

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current position via READ_POSITION command.

        Sends the position query command. The response will be delivered
        via the notification handler.

        Args:
            motor_count: Unused for Jensen (always reads both head and foot).
        """
        del motor_count  # Unused - Jensen always reads both motors
        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot read positions: not connected")
            return

        try:
            await self.client.write_gatt_char(
                JENSEN_CHAR_UUID, JensenCommands.READ_POSITION, response=True
            )
            _LOGGER.debug("Sent READ_POSITION command to Jensen bed")
        except BleakError as err:
            _LOGGER.warning("Failed to send READ_POSITION command: %s", err)

    async def _move_with_stop(self, command: bytes) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self.write_command(command)
        finally:
            try:
                await self.write_command(
                    JensenCommands.MOTOR_STOP,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(JensenCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(JensenCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            JensenCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head for Jensen)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Jensen)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor (same as head for Jensen)."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs/feet up."""
        await self._move_with_stop(JensenCommands.MOTOR_FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs/feet down."""
        await self._move_with_stop(JensenCommands.MOTOR_FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.write_command(
            JensenCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Jensen)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Jensen)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.write_command(
            JensenCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            JensenCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        try:
            await self.write_command(
                JensenCommands.PRESET_FLAT,
                repeat_count=100,
                repeat_delay_ms=150,
            )
        finally:
            try:
                await self.write_command(
                    JensenCommands.MOTOR_STOP,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP after preset_flat")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (Jensen only has 1 slot)."""
        if memory_num != 1:
            _LOGGER.warning("Invalid memory preset number: %d (Jensen only supports slot 1)", memory_num)
            return
        try:
            await self.write_command(
                JensenCommands.PRESET_MEMORY_RECALL,
                repeat_count=100,
                repeat_delay_ms=150,
            )
        finally:
            try:
                await self.write_command(
                    JensenCommands.MOTOR_STOP,
                    cancel_event=asyncio.Event(),
                )
            except BleakError:
                _LOGGER.debug("Failed to send STOP after preset_memory")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (Jensen only has 1 slot)."""
        if memory_num == 1:
            await self.write_command(JensenCommands.PRESET_MEMORY_SAVE)
        else:
            _LOGGER.warning("Invalid memory program number: %d (Jensen only supports slot 1)", memory_num)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on main lights."""
        if not self.supports_lights:
            raise NotImplementedError("This Jensen bed does not have main lights")
        await self.write_command(JensenCommands.LIGHT_MAIN_ON)
        self._lights_on = True

    async def lights_off(self) -> None:
        """Turn off main lights."""
        if not self.supports_lights:
            raise NotImplementedError("This Jensen bed does not have main lights")
        await self.write_command(JensenCommands.LIGHT_MAIN_OFF)
        self._lights_on = False

    async def lights_toggle(self) -> None:
        """Toggle main lights."""
        if self._lights_on:
            await self.lights_off()
        else:
            await self.lights_on()

    async def underbed_lights_on(self) -> None:
        """Turn on under-bed lights."""
        if not self.supports_under_bed_lights:
            raise NotImplementedError("This Jensen bed does not have under-bed lights")
        await self.write_command(JensenCommands.LIGHT_UNDERBED_ON)
        self._underbed_lights_on = True

    async def underbed_lights_off(self) -> None:
        """Turn off under-bed lights."""
        if not self.supports_under_bed_lights:
            raise NotImplementedError("This Jensen bed does not have under-bed lights")
        await self.write_command(JensenCommands.LIGHT_UNDERBED_OFF)
        self._underbed_lights_on = False

    async def underbed_lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        if self._underbed_lights_on:
            await self.underbed_lights_off()
        else:
            await self.underbed_lights_on()

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off all massage."""
        await self.write_command(JensenCommands.MASSAGE_OFF)
        self._massage_head_on = False
        self._massage_foot_on = False

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        if not self.has_massage_head:
            raise NotImplementedError("This Jensen bed does not have head massage")
        if self._massage_head_on:
            # Turn off (need to send the massage command with 0 for head)
            if self._massage_foot_on:
                await self.write_command(JensenCommands.MASSAGE_FOOT_ON)
            else:
                await self.write_command(JensenCommands.MASSAGE_OFF)
            self._massage_head_on = False
        else:
            if self._massage_foot_on:
                await self.write_command(JensenCommands.MASSAGE_BOTH_ON)
            else:
                await self.write_command(JensenCommands.MASSAGE_HEAD_ON)
            self._massage_head_on = True

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        if not self.has_massage_foot:
            raise NotImplementedError("This Jensen bed does not have foot massage")
        if self._massage_foot_on:
            if self._massage_head_on:
                await self.write_command(JensenCommands.MASSAGE_HEAD_ON)
            else:
                await self.write_command(JensenCommands.MASSAGE_OFF)
            self._massage_foot_on = False
        else:
            if self._massage_head_on:
                await self.write_command(JensenCommands.MASSAGE_BOTH_ON)
            else:
                await self.write_command(JensenCommands.MASSAGE_FOOT_ON)
            self._massage_foot_on = True

    async def massage_toggle(self) -> None:
        """Toggle all massage."""
        if not self.has_massage:
            raise NotImplementedError("This Jensen bed does not have massage")
        if self._massage_head_on or self._massage_foot_on:
            await self.massage_off()
        else:
            # Turn on both if available, otherwise just what's available
            if self.has_massage_head and self.has_massage_foot:
                await self.write_command(JensenCommands.MASSAGE_BOTH_ON)
                self._massage_head_on = True
                self._massage_foot_on = True
            elif self.has_massage_head:
                await self.write_command(JensenCommands.MASSAGE_HEAD_ON)
                self._massage_head_on = True
            elif self.has_massage_foot:
                await self.write_command(JensenCommands.MASSAGE_FOOT_ON)
                self._massage_foot_on = True
