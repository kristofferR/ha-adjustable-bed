"""Base class for bed controllers.

This module provides the abstract base class that all bed controllers must implement.
Each bed type (Linak, Richmat, Keeson, etc.) extends this class with protocol-specific
command encoding and position reading.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from bleak import BleakClient
from bleak.exc import BleakError

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class BedController(ABC):
    """Abstract base class for bed controllers.

    Subclasses must implement:
    - control_characteristic_uuid: The BLE characteristic UUID for sending commands
    - write_command: Protocol-specific command writing
    - start_notify/stop_notify: Position notification handling
    - read_positions: Active position reading
    - Motor control methods (move_head_up, move_head_down, etc.)
    - Preset methods (preset_flat, preset_memory, program_memory)

    Optional methods that can be overridden:
    - preset_zero_g, preset_anti_snore, preset_tv
    - lights_on, lights_off, lights_toggle
    - massage_* methods
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the controller.

        Args:
            coordinator: The AdjustableBedCoordinator managing the BLE connection
        """
        self._coordinator = coordinator

    @property
    def client(self) -> BleakClient | None:
        """Return the BLE client."""
        return self._coordinator.client

    def log_discovered_services(self, level: int = logging.DEBUG) -> None:
        """Log all discovered GATT services and characteristics.

        Useful for debugging when expected services/characteristics are not found.
        Call this method when the controller fails to find the expected BLE
        services to help users report issues with new device variants.

        Args:
            level: Logging level (default: DEBUG). Use logging.INFO for
                   more visibility when debugging connection issues.
        """
        client = self.client
        if client is None or client.services is None:
            _LOGGER.log(level, "No BLE services discovered (client not connected)")
            return

        services_count = len(list(client.services))
        _LOGGER.log(
            level,
            "Discovered %d GATT services on %s:",
            services_count,
            self._coordinator.address,
        )

        for service in client.services:
            _LOGGER.log(
                level,
                "  Service: %s",
                service.uuid,
            )
            for char in service.characteristics:
                props = ", ".join(char.properties)
                _LOGGER.log(
                    level,
                    "    Char: %s [%s]",
                    char.uuid,
                    props,
                )

    @property
    @abstractmethod
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic.

        This is the BLE characteristic that accepts motor/preset commands.
        """

    async def _write_gatt_with_retry(
        self,
        char_uuid: str,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        response: bool = False,
    ) -> None:
        """Write a command to a GATT characteristic with retry support.

        This is a helper method that handles the common pattern of:
        - Checking connection state
        - Writing to a characteristic with optional response
        - Repeating the command with delays
        - Checking for cancellation between writes

        Args:
            char_uuid: The characteristic UUID to write to
            command: The command bytes to send
            repeat_count: Number of times to repeat the command (default: 1)
            repeat_delay_ms: Delay between repeats in milliseconds (default: 100)
            cancel_event: Optional event that signals cancellation. If set,
                         the command loop will exit early.
            response: Whether to wait for a write response from the device.
                     True = write-with-response (more reliable, slower)
                     False = write-without-response (faster, less reliable)

        Raises:
            ConnectionError: If not connected to the bed
            BleakError: If the GATT write fails
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.debug("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                await self.client.write_gatt_char(char_uuid, command, response=response)
            except BleakError as err:
                _LOGGER.error(
                    "Failed to write command %s to %s: %s",
                    command.hex(),
                    char_uuid,
                    err,
                )
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    @abstractmethod
    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed.

        Subclasses implement this to handle protocol-specific command writing.
        Most implementations can delegate to _write_gatt_with_retry() after
        any necessary command transformation.

        Args:
            command: The command bytes to send (protocol-specific format)
            repeat_count: Number of times to repeat the command. Motor movements
                         typically need 10-25 repeats to keep the motor running.
            repeat_delay_ms: Delay between repeats in milliseconds
            cancel_event: Optional event that signals cancellation (e.g., user
                         pressed stop). If not provided, uses the coordinator's
                         cancel event.

        Raises:
            ConnectionError: If not connected to the bed
            BleakError: If the GATT write fails
        """

    @abstractmethod
    async def start_notify(
        self, callback: Callable[[str, float], None]
    ) -> None:
        """Start listening for position notifications.

        Subscribe to BLE notifications for position updates. When the bed
        reports a position change, the callback is invoked.

        Args:
            callback: Function called with (position_name, angle) when position
                     updates are received. position_name is one of: "back",
                     "legs", "head", "feet". angle is in degrees (0.0 = flat).

        Note:
            Not all bed types support position notifications. Implementations
            that don't support this should store the callback but not subscribe
            to any notifications.
        """

    @abstractmethod
    async def stop_notify(self) -> None:
        """Stop listening for position notifications.

        Unsubscribe from BLE notifications. Safe to call even if notifications
        were never started.
        """

    @abstractmethod
    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data from all motor position characteristics.

        Actively read position values rather than waiting for notifications.
        Useful after movement commands to get immediate position feedback.

        Args:
            motor_count: Number of motors to read positions for (2-4)

        Note:
            Not all bed types support position reading. Implementations that
            don't support this should return immediately without error.
        """

    # Motor control methods
    # These move motors for a fixed duration (~1-2 seconds) then auto-stop.
    # Implementations should use try/finally to ensure stop is always sent.

    @abstractmethod
    async def move_head_up(self) -> None:
        """Move head motor up for a short duration, then stop."""

    @abstractmethod
    async def move_head_down(self) -> None:
        """Move head motor down for a short duration, then stop."""

    @abstractmethod
    async def move_head_stop(self) -> None:
        """Immediately stop head motor movement."""

    @abstractmethod
    async def move_back_up(self) -> None:
        """Move back motor up for a short duration, then stop.

        Note: Some beds treat back and head as the same motor.
        """

    @abstractmethod
    async def move_back_down(self) -> None:
        """Move back motor down for a short duration, then stop."""

    @abstractmethod
    async def move_back_stop(self) -> None:
        """Immediately stop back motor movement."""

    @abstractmethod
    async def move_legs_up(self) -> None:
        """Move legs motor up for a short duration, then stop.

        Note: Some beds treat legs and feet as the same motor.
        """

    @abstractmethod
    async def move_legs_down(self) -> None:
        """Move legs motor down for a short duration, then stop."""

    @abstractmethod
    async def move_legs_stop(self) -> None:
        """Immediately stop legs motor movement."""

    @abstractmethod
    async def move_feet_up(self) -> None:
        """Move feet motor up for a short duration, then stop."""

    @abstractmethod
    async def move_feet_down(self) -> None:
        """Move feet motor down for a short duration, then stop."""

    @abstractmethod
    async def move_feet_stop(self) -> None:
        """Immediately stop feet motor movement."""

    @abstractmethod
    async def stop_all(self) -> None:
        """Immediately stop all motor movement."""

    # Preset methods

    @abstractmethod
    async def preset_flat(self) -> None:
        """Move bed to flat (zero) position.

        This command runs until the bed reaches flat position, which may
        take 30+ seconds depending on current position.
        """

    @abstractmethod
    async def preset_memory(self, memory_num: int) -> None:
        """Move bed to a saved memory preset position.

        Args:
            memory_num: Memory slot number (1-4, availability varies by bed)
        """

    @abstractmethod
    async def program_memory(self, memory_num: int) -> None:
        """Save the current bed position to a memory preset.

        Args:
            memory_num: Memory slot number to save to (1-4)

        Note:
            Not all beds support programming memory presets. Check the
            specific controller implementation for support.
        """

    # Optional preset methods (may not be available on all beds)
    # These raise NotImplementedError by default. Subclasses override if supported.

    async def preset_zero_g(self) -> None:
        """Move bed to zero gravity position (legs elevated, head slightly raised).

        Raises:
            NotImplementedError: If the bed doesn't support this preset
        """
        raise NotImplementedError("Zero gravity preset not supported on this bed")

    async def preset_anti_snore(self) -> None:
        """Move bed to anti-snore position (head elevated).

        Raises:
            NotImplementedError: If the bed doesn't support this preset
        """
        raise NotImplementedError("Anti-snore preset not supported on this bed")

    async def preset_tv(self) -> None:
        """Move bed to TV/lounge position.

        Raises:
            NotImplementedError: If the bed doesn't support this preset
        """
        raise NotImplementedError("TV preset not supported on this bed")

    # Feature methods (may not be available on all beds)

    async def lights_on(self) -> None:
        """Turn on under-bed lights.

        Raises:
            NotImplementedError: If the bed doesn't have controllable lights
        """
        raise NotImplementedError("Light control not supported on this bed")

    async def lights_off(self) -> None:
        """Turn off under-bed lights.

        Raises:
            NotImplementedError: If the bed doesn't have controllable lights
        """
        raise NotImplementedError("Light control not supported on this bed")

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights.

        Raises:
            NotImplementedError: If the bed doesn't have controllable lights
        """
        raise NotImplementedError("Light control not supported on this bed")

    async def massage_off(self) -> None:
        """Turn off all massage motors.

        Raises:
            NotImplementedError: If the bed doesn't have massage
        """
        raise NotImplementedError("Massage not supported on this bed")

    async def massage_toggle(self) -> None:
        """Toggle massage on/off.

        Raises:
            NotImplementedError: If the bed doesn't have massage
        """
        raise NotImplementedError("Massage not supported on this bed")

    async def massage_head_toggle(self) -> None:
        """Toggle head massage zone.

        Raises:
            NotImplementedError: If the bed doesn't have head massage
        """
        raise NotImplementedError("Head massage not supported on this bed")

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage zone.

        Raises:
            NotImplementedError: If the bed doesn't have foot massage
        """
        raise NotImplementedError("Foot massage not supported on this bed")

    async def massage_intensity_up(self) -> None:
        """Increase overall massage intensity.

        Raises:
            NotImplementedError: If the bed doesn't support intensity control
        """
        raise NotImplementedError("Massage intensity control not supported on this bed")

    async def massage_intensity_down(self) -> None:
        """Decrease overall massage intensity.

        Raises:
            NotImplementedError: If the bed doesn't support intensity control
        """
        raise NotImplementedError("Massage intensity control not supported on this bed")

    async def massage_head_up(self) -> None:
        """Increase head massage intensity.

        Raises:
            NotImplementedError: If the bed doesn't support head massage intensity
        """
        raise NotImplementedError("Head massage intensity not supported on this bed")

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity.

        Raises:
            NotImplementedError: If the bed doesn't support head massage intensity
        """
        raise NotImplementedError("Head massage intensity not supported on this bed")

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity.

        Raises:
            NotImplementedError: If the bed doesn't support foot massage intensity
        """
        raise NotImplementedError("Foot massage intensity not supported on this bed")

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity.

        Raises:
            NotImplementedError: If the bed doesn't support foot massage intensity
        """
        raise NotImplementedError("Foot massage intensity not supported on this bed")

    async def massage_mode_step(self) -> None:
        """Cycle through massage patterns/modes.

        Raises:
            NotImplementedError: If the bed doesn't support massage modes
        """
        raise NotImplementedError("Massage modes not supported on this bed")

