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

from ..const import JENSEN_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


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

    # Position read command
    READ_POSITION = bytes([0x10, 0xFF, 0x00, 0x00, 0x00, 0x00])

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

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Jensen controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._features: JensenFeatureFlags = JensenFeatureFlags.NONE
        self._config_loaded: bool = False
        self._lights_on: bool = False
        self._underbed_lights_on: bool = False
        self._massage_head_on: bool = False
        self._massage_foot_on: bool = False
        _LOGGER.debug("JensenController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return JENSEN_CHAR_UUID

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
        """
        if self._config_loaded:
            _LOGGER.debug("Jensen config already loaded, skipping query")
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot query config: not connected")
            return

        _LOGGER.debug("Querying Jensen bed configuration...")

        # Set up notification handler to receive config response
        config_received = asyncio.Event()
        config_data: list[bytes] = []

        def notification_handler(sender: int, data: bytearray) -> None:
            """Handle config notification."""
            _LOGGER.debug("Received config notification: %s", data.hex())
            config_data.append(bytes(data))
            config_received.set()

        try:
            # Subscribe to notifications
            await self.client.start_notify(JENSEN_CHAR_UUID, notification_handler)

            # Send config read command
            await self.client.write_gatt_char(
                JENSEN_CHAR_UUID, JensenCommands.CONFIG_READ_ALL, response=True
            )

            # Wait for response (with timeout)
            try:
                await asyncio.wait_for(config_received.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                _LOGGER.warning("Timeout waiting for config response, assuming full features")
                # Default to all features enabled if we can't query
                self._features = JensenFeatureFlags(
                    JensenFeatureFlags.MASSAGE_HEAD
                    | JensenFeatureFlags.MASSAGE_FOOT
                    | JensenFeatureFlags.LIGHT
                    | JensenFeatureFlags.LIGHT_UNDERBED
                )
                self._config_loaded = True
                return

            # Stop notifications
            await self.client.stop_notify(JENSEN_CHAR_UUID)

            # Parse config response
            if config_data:
                data = config_data[0]
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

            self._config_loaded = True

        except BleakError as err:
            _LOGGER.warning("Failed to query config: %s", err)
            # Default to basic features on error
            self._config_loaded = True

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

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback
        _LOGGER.debug("Jensen beds don't support continuous position notifications")

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        # Jensen beds may support position reading via READ_POSITION command
        # but the response format is not fully documented
        pass

    async def _move_with_stop(self, command: bytes) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self.write_command(command, repeat_count=10, repeat_delay_ms=100)
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
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Jensen)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Jensen)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            JensenCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            JensenCommands.PRESET_FLAT,
            repeat_count=100,
            repeat_delay_ms=150,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (Jensen only has 1 slot)."""
        if memory_num == 1:
            await self.write_command(
                JensenCommands.PRESET_MEMORY_RECALL,
                repeat_count=100,
                repeat_delay_ms=150,
            )
        else:
            _LOGGER.warning("Invalid memory preset number: %d (Jensen only supports slot 1)", memory_num)

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
