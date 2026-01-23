"""Base class for bed controllers.

This module provides the abstract base class that all bed controllers must implement.
Each bed type (Linak, Richmat, Keeson, etc.) extends this class with protocol-specific
command encoding and position reading.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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
        self._raw_notify_callback: Callable[[str, bytes], None] | None = None
        self._ble_lock = asyncio.Lock()

    @property
    def ble_lock(self) -> asyncio.Lock:
        """Return the BLE operation lock.

        This lock should be acquired by any code that performs BLE read/write
        operations to prevent concurrent GATT operations which can cause
        'operation in progress' errors on some BLE backends.
        """
        return self._ble_lock

    def set_raw_notify_callback(self, callback: Callable[[str, bytes], None] | None) -> None:
        """Set a callback to receive raw notification data.

        This is used by diagnostics to capture raw BLE notifications without
        disrupting normal notification handling. The callback receives the
        characteristic UUID and raw bytes for each notification.

        Args:
            callback: Function to call with (characteristic_uuid, data), or None to clear.
        """
        self._raw_notify_callback = callback

    def forward_raw_notification(self, characteristic_uuid: str, data: bytes) -> None:
        """Forward raw notification data to the registered callback.

        Subclasses should call this from their notification handlers to
        enable diagnostics capture.

        Args:
            characteristic_uuid: The UUID of the characteristic that sent the notification.
            data: The raw notification data bytes.
        """
        if self._raw_notify_callback is not None:
            try:
                self._raw_notify_callback(characteristic_uuid, data)
            except Exception:
                _LOGGER.debug("Error in raw notification callback", exc_info=True)

    @property
    def client(self) -> BleakClient | None:
        """Return the BLE client."""
        return self._coordinator.client

    @property
    def auto_stops_on_idle(self) -> bool:
        """Return True if motors auto-stop when commands stop arriving.

        Controllers that auto-stop (like Linak) should override this to return True.
        This allows the coordinator to skip explicit STOP commands which can cause
        brief reverse movements on some bed types.
        """
        return False

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
        response: bool = True,
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
                     True = write-with-response (more reliable, slower) [default]
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
                # Acquire BLE lock for each individual write to prevent conflicts
                # with concurrent position reads during movement
                async with self._ble_lock:
                    await self.client.write_gatt_char(char_uuid, command, response=response)
            except BleakError:
                _LOGGER.exception(
                    "Failed to write command %s to %s",
                    command.hex(),
                    char_uuid,
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
    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
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

    async def read_non_notifying_positions(self) -> None:  # noqa: B027
        """Read positions only for motors that don't support notifications.

        Used for efficient polling during movement - only reads motors that
        don't push updates via BLE notifications.

        Default implementation does nothing. Override in subclasses where
        some motors support notifications and others don't.
        """

    # Direct position control (optional)
    # Beds that can command motors to specific positions should override these

    @property
    def supports_direct_position_control(self) -> bool:
        """Return True if the bed supports setting motor positions directly.

        Beds that can command motors to specific positions (0-100%) should
        override this to return True and implement set_motor_position().
        This allows the coordinator to skip the incremental seek loop.
        """
        return False

    def angle_to_native_position(self, motor: str, angle: float) -> int:
        """Convert an angle value to the bed's native position format.

        Override in subclasses that use a different position format.
        Default implementation assumes angle IS the position (for percentage beds).

        Args:
            motor: Motor name ("head", "back", "legs", "feet")
            angle: Angle in degrees (or percentage for some bed types)

        Returns:
            Position in the bed's native format (typically 0-100)
        """
        return int(angle)

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Set a motor to a specific position (0-100).

        Override in subclasses that support direct position control.

        Args:
            motor: Motor name ("head", "back", "legs", "feet")
            position: Target position as percentage (0=flat, 100=max)

        Raises:
            NotImplementedError: If the bed doesn't support direct position control
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support direct position control"
        )

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

    # Capability properties - override in subclasses that support these features
    # These are used by button.py and cover.py to determine which entities to create

    @property
    def supports_preset_flat(self) -> bool:
        """Return True if bed has a dedicated flat preset.

        Some beds (like Linak) don't have a native flat command - they use
        Memory 1 which may not actually be programmed as flat. Those controllers
        should override this to return False.
        """
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        """Return True if bed supports zero gravity preset."""
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        """Return True if bed supports anti-snore preset."""
        return False

    @property
    def supports_preset_tv(self) -> bool:
        """Return True if bed supports TV preset."""
        return False

    @property
    def supports_preset_lounge(self) -> bool:
        """Return True if bed supports lounge preset."""
        return False

    @property
    def supports_preset_incline(self) -> bool:
        """Return True if bed supports incline preset."""
        return False

    @property
    def supports_preset_yoga(self) -> bool:
        """Return True if bed supports yoga preset."""
        return False

    @property
    def supports_light_cycle(self) -> bool:
        """Return True if bed supports light cycle control."""
        return False

    @property
    def has_lumbar_support(self) -> bool:
        """Return True if bed has lumbar motor control."""
        return False

    @property
    def has_pillow_support(self) -> bool:
        """Return True if bed has pillow motor control."""
        return False

    @property
    def has_tilt_support(self) -> bool:
        """Return True if bed has tilt motor control."""
        return False

    @property
    def supports_motor_control(self) -> bool:
        """Return True if bed supports direct motor control (up/down/stop).

        Some beds (like Jiecang) only support preset positions, not
        individual motor movement commands.
        """
        return True

    @property
    def has_discrete_motor_control(self) -> bool:
        """Return True if bed uses discrete (button-press) motor control.

        Discrete motor control means each command moves the motor a small
        amount (like pressing a button), rather than continuous movement
        that requires a stop command. Beds with discrete control should
        expose button entities instead of cover entities for motor control.
        """
        return False

    @property
    def supports_stop_all(self) -> bool:
        """Return True if bed supports a stop-all command.

        Some beds (like Keeson) don't have a dedicated stop command -
        motors stop automatically when commands stop being sent.
        """
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return the number of memory preset slots supported.

        Override in subclasses. Common values:
        - 0: No memory presets (Octo, Serta, Nectar, MattressFirm)
        - 2: Memory 1-2 (Jiecang, MotoSleep, DewertOkin, Linak)
        - 4: Memory 1-4 (Keeson, Reverie)
        """
        return 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return True if bed supports programming memory positions via BLE.

        Some beds have read-only memory presets (can recall but not save).
        Override in subclasses that support programming.
        """
        return False

    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        """Return custom translation keys for motor cover entities, or None for defaults.

        Override in subclasses where motor labels differ from the standard naming.
        The dict maps motor key (e.g., "head", "feet", "tilt") to a translation key
        (e.g., "keeson_back", "keeson_legs", "keeson_head").
        """
        return None

    # Lumbar motor control (optional - only some beds have this)

    async def move_lumbar_up(self) -> None:
        """Move lumbar motor up for a short duration, then stop.

        Raises:
            NotImplementedError: If the bed doesn't have lumbar motor
        """
        raise NotImplementedError("Lumbar motor not supported on this bed")

    async def move_lumbar_down(self) -> None:
        """Move lumbar motor down for a short duration, then stop.

        Raises:
            NotImplementedError: If the bed doesn't have lumbar motor
        """
        raise NotImplementedError("Lumbar motor not supported on this bed")

    async def move_lumbar_stop(self) -> None:
        """Immediately stop lumbar motor movement.

        Raises:
            NotImplementedError: If the bed doesn't have lumbar motor
        """
        raise NotImplementedError("Lumbar motor not supported on this bed")

    # Pillow motor control (optional - only some beds have this)

    async def move_pillow_up(self) -> None:
        """Move pillow motor up for a short duration, then stop.

        Raises:
            NotImplementedError: If the bed doesn't have pillow motor
        """
        raise NotImplementedError("Pillow motor not supported on this bed")

    async def move_pillow_down(self) -> None:
        """Move pillow motor down for a short duration, then stop.

        Raises:
            NotImplementedError: If the bed doesn't have pillow motor
        """
        raise NotImplementedError("Pillow motor not supported on this bed")

    async def move_pillow_stop(self) -> None:
        """Immediately stop pillow motor movement.

        Raises:
            NotImplementedError: If the bed doesn't have pillow motor
        """
        raise NotImplementedError("Pillow motor not supported on this bed")

    # Tilt motor control (optional - only some beds have this)

    async def move_tilt_up(self) -> None:
        """Move tilt motor up for a short duration, then stop.

        Raises:
            NotImplementedError: If the bed doesn't have tilt motor
        """
        raise NotImplementedError("Tilt motor not supported on this bed")

    async def move_tilt_down(self) -> None:
        """Move tilt motor down for a short duration, then stop.

        Raises:
            NotImplementedError: If the bed doesn't have tilt motor
        """
        raise NotImplementedError("Tilt motor not supported on this bed")

    async def move_tilt_stop(self) -> None:
        """Immediately stop tilt motor movement.

        Raises:
            NotImplementedError: If the bed doesn't have tilt motor
        """
        raise NotImplementedError("Tilt motor not supported on this bed")

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

    async def preset_yoga(self) -> None:
        """Move bed to yoga position.

        Raises:
            NotImplementedError: If the bed doesn't support this preset
        """
        raise NotImplementedError("Yoga preset not supported on this bed")

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

    # Massage intensity and timer control (optional - for beds with direct control)

    @property
    def supports_massage_intensity_control(self) -> bool:
        """Return True if bed supports setting massage intensity directly.

        When True, the bed can set specific intensity levels (0-10) rather than
        just stepping up/down. This enables number entity sliders for massage.
        """
        return False

    @property
    def massage_intensity_zones(self) -> list[str]:
        """Return list of massage zones that support direct intensity control.

        Possible zones: "head", "foot", "wave", "lumbar"
        Override in subclasses that support direct intensity control.
        """
        return []

    @property
    def massage_intensity_max(self) -> int:
        """Return maximum intensity level for massage zones.

        Most beds use 0-10, some use 0-6. Default is 10.
        """
        return 10

    @property
    def supports_massage_timer(self) -> bool:
        """Return True if bed supports setting massage timer directly."""
        return False

    @property
    def massage_timer_options(self) -> list[int]:
        """Return available timer durations in minutes.

        Common options: [10, 20, 30]
        Override in subclasses that support timer selection.
        """
        return []

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        """Set massage intensity for a specific zone.

        Args:
            zone: Massage zone ("head", "foot", "wave", "lumbar")
            level: Intensity level (0 to massage_intensity_max, 0 = off)

        Raises:
            NotImplementedError: If the bed doesn't support direct intensity control
        """
        raise NotImplementedError("Direct massage intensity control not supported on this bed")

    async def set_massage_timer(self, minutes: int) -> None:
        """Set massage timer duration.

        Args:
            minutes: Timer duration in minutes (0 = off, or a value from massage_timer_options)

        Raises:
            NotImplementedError: If the bed doesn't support timer selection
        """
        raise NotImplementedError("Massage timer selection not supported on this bed")

    def get_massage_state(self) -> dict[str, Any]:
        """Return current massage state for state feedback.

        Returns a dict with current state info (keys vary by bed):
        - head_intensity: int (0-10 or 0-6)
        - foot_intensity: int
        - wave_intensity: int
        - timer_mode: str | None ("10", "20", "30")
        - head_active: bool
        - foot_active: bool

        Override in subclasses with state tracking/feedback.
        """
        return {}
