"""Okimat bed controller implementation.

Okimat beds use the Okin protocol with 6-byte commands: [0x04, 0x02, ...int_to_bytes(command)]
They require BLE pairing before use.

Note: Okimat shares the same BLE service UUID (62741523-52f9-8864-b1ab-3b3a8d65950b) with
Leggett & Platt Okin variant and Nectar beds. Detection uses device name patterns to
distinguish between these bed types. See okin_protocol.py for shared protocol details.

Supported remote codes (configured via variant):
- 80608: RFS ELLIPSE (Back, Legs)
- 82417: RF TOPLINE (Back, Legs)
- 82418: RF TOPLINE (Back, Legs, 2 Memory)
- 88875: RF LITELINE (Back, Legs)
- 91244: RF-FLASHLINE (Back, Legs)
- 93329: RF TOPLINE (Head, Back, Legs, 4 Memory)
- 93332: RF TOPLINE (Head, Back, Legs, Feet, 2 Memory)
- 94238: RF FLASHLINE (Back, Legs, 2 Memory)

Reference: https://github.com/richardhopton/smartbed-mqtt
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import (
    OKIMAT_VARIANT_80608,
    OKIMAT_VARIANT_82417,
    OKIMAT_VARIANT_82418,
    OKIMAT_VARIANT_88875,
    OKIMAT_VARIANT_91244,
    OKIMAT_VARIANT_93329,
    OKIMAT_VARIANT_93332,
    OKIMAT_VARIANT_94238,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_FOOT_MAX_ANGLE,
    OKIN_FOOT_MAX_RAW,
    OKIN_HEAD_MAX_ANGLE,
    OKIN_HEAD_MAX_RAW,
    OKIN_POSITION_NOTIFY_CHAR_UUID,
    VARIANT_AUTO,
)
from .base import BedController
from .okin_protocol import build_okin_command

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class OkimatComplexCommand:
    """A command with specific timing requirements.

    Some Okimat commands require specific repeat count and delay timing.
    Reference: https://github.com/richardhopton/smartbed-mqtt/commit/6b18011
    """

    data: int  # The command code
    count: int  # Number of times to repeat
    wait_time: int  # Delay in ms between repeats


@dataclass
class OkimatRemoteConfig:
    """Configuration for a specific Okimat remote model."""

    name: str
    flat: int
    back_up: int = 0x1
    back_down: int = 0x2
    legs_up: int = 0x4
    legs_down: int = 0x8
    head_up: int | None = None  # Tilt motor (93329, 93332 only)
    head_down: int | None = None
    feet_up: int | None = None  # Separate feet motor (93332 only)
    feet_down: int | None = None
    memory_1: int | None = None
    memory_2: int | None = None
    memory_3: int | None = None
    memory_4: int | None = None
    memory_save: int | OkimatComplexCommand | None = None
    toggle_lights: int | OkimatComplexCommand = 0x20000  # UBL (under-bed lights)


# Remote configurations based on smartbed-mqtt supportedRemotes.ts
OKIMAT_REMOTES: dict[str, OkimatRemoteConfig] = {
    OKIMAT_VARIANT_80608: OkimatRemoteConfig(
        name="RFS ELLIPSE",
        flat=0x100000AA,
    ),
    OKIMAT_VARIANT_82417: OkimatRemoteConfig(
        name="RF TOPLINE",
        flat=0x000000AA,
    ),
    OKIMAT_VARIANT_82418: OkimatRemoteConfig(
        name="RF TOPLINE",
        flat=0x000000AA,
        memory_1=0x1000,
        memory_2=0x2000,
        memory_save=0x10000,
    ),
    OKIMAT_VARIANT_88875: OkimatRemoteConfig(
        name="RF LITELINE",
        flat=0x100000AA,
    ),
    OKIMAT_VARIANT_91244: OkimatRemoteConfig(
        name="RF-FLASHLINE",
        flat=0x100000AA,
    ),
    OKIMAT_VARIANT_93329: OkimatRemoteConfig(
        name="RF TOPLINE",
        flat=0x0000002A,
        head_up=0x10,
        head_down=0x20,
        memory_1=0x1000,
        memory_2=0x2000,
        memory_3=0x4000,
        memory_4=0x8000,
        memory_save=0x10000,
    ),
    OKIMAT_VARIANT_93332: OkimatRemoteConfig(
        name="RF TOPLINE",
        flat=0x000000AA,
        head_up=0x10,
        head_down=0x20,
        feet_up=0x40,
        feet_down=0x20,  # Note: shares value with head_down per smartbed-mqtt
        memory_1=0x1000,
        memory_2=0x2000,
        memory_save=0x10000,
    ),
    OKIMAT_VARIANT_94238: OkimatRemoteConfig(
        name="RF FLASHLINE",
        flat=0x10000000,
        memory_1=0x1000,
        memory_2=0x2000,
        memory_save=OkimatComplexCommand(data=0x10000, count=25, wait_time=200),
        toggle_lights=OkimatComplexCommand(data=0x20000, count=50, wait_time=100),
    ),
}

# Default remote for auto-detect (most common/basic)
DEFAULT_REMOTE = OKIMAT_VARIANT_82417


class OkimatController(BedController):
    """Controller for Okimat beds.

    Note: Okimat beds require BLE pairing before they can be controlled.
    The pairing must be done through the coordinator during connection.

    Different remote codes have different capabilities:
    - Basic remotes (80608, 82417, 88875, 91244): Back and Legs motors only
    - Memory remotes (82418, 94238): Back, Legs + 2 memory presets
    - Advanced remotes (93329): Head, Back, Legs + 4 memory presets
    - Full remotes (93332): Head, Back, Legs, Feet + 2 memory presets
    """

    def __init__(
        self, coordinator: AdjustableBedCoordinator, variant: str = VARIANT_AUTO
    ) -> None:
        """Initialize the Okimat controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        # Motor state stores command values per motor (head, back, legs, feet)
        # This allows combining multiple motor commands simultaneously
        # Reference: https://github.com/richardhopton/smartbed-mqtt/pull/66
        self._motor_state: dict[str, int] = {}

        # Resolve variant to remote config
        if variant == VARIANT_AUTO or variant not in OKIMAT_REMOTES:
            variant = DEFAULT_REMOTE
        self._variant = variant
        self._remote = OKIMAT_REMOTES[variant]

        _LOGGER.debug(
            "OkimatController initialized with remote %s (%s)",
            variant,
            self._remote.name,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OKIMAT_WRITE_CHAR_UUID

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if this remote supports memory presets."""
        # Check if at least memory_1 is available for this remote variant
        return self._remote.memory_1 is not None

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - Okimat only supports toggle, not discrete on/off."""
        return False

    def _build_command(self, command_value: int) -> bytes:
        """Build command bytes using build_okin_command: [0x04, 0x02, <4-byte>]."""
        return build_okin_command(command_value)

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
            "Writing command to Okimat bed: %s (repeat: %d, delay: %dms)",
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
                    OKIMAT_WRITE_CHAR_UUID, command, response=True
                )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None]) -> None:
        """Start listening for position notifications.

        OKIN beds report position via BLE notifications on characteristic FFE4.
        Data format: bytes 3-4 = head raw (LE), bytes 5-6 = foot raw (LE)
        Reference: https://github.com/richardhopton/smartbed-mqtt/issues/53
        """
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start position notifications: not connected")
            return

        _LOGGER.info(
            "Setting up position notifications for Okin bed at %s",
            self._coordinator.address,
        )

        try:
            await self.client.start_notify(
                OKIN_POSITION_NOTIFY_CHAR_UUID,
                self._handle_position_notification,
            )
            _LOGGER.info(
                "Position notifications active for Okin bed (UUID: %s)",
                OKIN_POSITION_NOTIFY_CHAR_UUID,
            )
        except BleakError as err:
            _LOGGER.debug(
                "Could not start position notifications for Okin bed: %s "
                "(bed may not support position feedback)",
                err,
            )

    def _handle_position_notification(self, _: int, data: bytearray) -> None:
        """Handle position notification data from OKIN controller.

        Data format (7+ bytes):
        - Bytes 0-2: Unknown (possibly status/header)
        - Bytes 3-4: Head position (little-endian uint16)
        - Bytes 5-6: Foot position (little-endian uint16)

        Position values are normalized:
        - Head: 0-16000 raw → 0-60 degrees
        - Foot: 0-12000 raw → 0-45 degrees
        """
        if len(data) < 7:
            _LOGGER.debug(
                "Received invalid position data: expected 7+ bytes, got %d",
                len(data),
            )
            return

        _LOGGER.debug("Okin position notification: %s", data.hex())

        # Extract head position (bytes 3-4, little-endian)
        head_raw = data[3] | (data[4] << 8)
        head_angle = round((head_raw / OKIN_HEAD_MAX_RAW) * OKIN_HEAD_MAX_ANGLE, 1)
        # Clamp to max angle
        head_angle = min(head_angle, OKIN_HEAD_MAX_ANGLE)

        # Extract foot position (bytes 5-6, little-endian)
        foot_raw = data[5] | (data[6] << 8)
        foot_angle = round((foot_raw / OKIN_FOOT_MAX_RAW) * OKIN_FOOT_MAX_ANGLE, 1)
        # Clamp to max angle
        foot_angle = min(foot_angle, OKIN_FOOT_MAX_ANGLE)

        _LOGGER.debug(
            "Okin position: head=%d raw (%.1f°), foot=%d raw (%.1f°)",
            head_raw,
            head_angle,
            foot_raw,
            foot_angle,
        )

        if self._notify_callback:
            # Map to standard position names used by the integration
            # "back" is the primary head/back motor
            self._notify_callback("back", head_angle)
            # "legs" is the primary foot/legs motor
            self._notify_callback("legs", foot_angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(OKIN_POSITION_NOTIFY_CHAR_UUID)
            _LOGGER.debug("Stopped position notifications for Okin bed")
        except BleakError:
            pass

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Note: OKIN beds typically use notifications rather than reads for
        position data. This method attempts a read but may not work on all beds.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot read positions: not connected")
            return

        try:
            data = await self.client.read_gatt_char(OKIN_POSITION_NOTIFY_CHAR_UUID)
            if data:
                _LOGGER.debug("Read Okin position data: %s", data.hex())
                self._handle_position_notification(0, bytearray(data))
        except BleakError as err:
            _LOGGER.debug("Could not read position data: %s", err)

    def _get_move_command(self) -> int:
        """Calculate the combined motor movement command.

        Sums all active motor command values to create a combined command.
        This allows multiple motors to move simultaneously when their
        command values are set in _motor_state.

        Reference: https://github.com/richardhopton/smartbed-mqtt/pull/66
        """
        command = 0
        state = self._motor_state

        # Sum all active motor commands
        if "head" in state:
            command += state["head"]
        if "back" in state:
            command += state["back"]
        if "legs" in state:
            command += state["legs"]
        if "feet" in state:
            command += state["feet"]

        return command

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        """Move a motor with a specific command value or stop it.

        Args:
            motor: Motor name ('head', 'back', 'legs', 'feet')
            command_value: The command code to send, or None to stop the motor.

        This method updates the motor state and sends the combined command
        for all active motors. When command_value is None (stop), only this
        motor is removed from state, allowing other motors to continue.
        """
        # Update motor state
        if command_value is None or command_value == 0:
            # Stop this motor - remove from state
            self._motor_state.pop(motor, None)
        else:
            # Set this motor's command value
            self._motor_state[motor] = command_value

        # Calculate combined command for all active motors
        combined_command = self._get_move_command()

        # Use configurable pulse settings from coordinator
        pulse_count = getattr(self._coordinator, 'motor_pulse_count', 25)
        pulse_delay = getattr(self._coordinator, 'motor_pulse_delay_ms', 200)

        try:
            if combined_command:
                await self.write_command(
                    self._build_command(combined_command),
                    repeat_count=pulse_count,
                    repeat_delay_ms=pulse_delay,
                )
        finally:
            # Clear this motor's state after command completes
            self._motor_state.pop(motor, None)

            # Send stop command only if no other motors are active
            if not self._motor_state:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )

    # Motor control methods - Back (primary motor on all remotes)
    async def move_head_up(self) -> None:
        """Move head/back up."""
        await self._move_motor("back", self._remote.back_up)

    async def move_head_down(self) -> None:
        """Move head/back down."""
        await self._move_motor("back", self._remote.back_down)

    async def move_head_stop(self) -> None:
        """Stop head/back motor."""
        await self._move_motor("back", None)

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_motor("back", self._remote.back_up)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_motor("back", self._remote.back_down)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self._move_motor("back", None)

    # Motor control methods - Legs (all remotes)
    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_motor("legs", self._remote.legs_up)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor("legs", self._remote.legs_down)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("legs", None)

    # Motor control methods - Feet (93332 only, others map to legs)
    async def move_feet_up(self) -> None:
        """Move feet up."""
        if self._remote.feet_up is not None:
            await self._move_motor("feet", self._remote.feet_up)
        else:
            # Fall back to legs for remotes without separate feet motor
            await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        if self._remote.feet_down is not None:
            await self._move_motor("feet", self._remote.feet_down)
        else:
            await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        if self._remote.feet_up is not None:
            await self._move_motor("feet", None)
        else:
            await self.move_legs_stop()

    # Motor control methods - Tilt/Head (93329, 93332 only)
    async def move_tilt_up(self) -> None:
        """Move tilt/head up (93329, 93332 only)."""
        if self._remote.head_up is not None:
            await self._move_motor("head", self._remote.head_up)
        else:
            _LOGGER.debug("Tilt motor not available on remote %s", self._variant)

    async def move_tilt_down(self) -> None:
        """Move tilt/head down (93329, 93332 only)."""
        if self._remote.head_down is not None:
            await self._move_motor("head", self._remote.head_down)
        else:
            _LOGGER.debug("Tilt motor not available on remote %s", self._variant)

    async def move_tilt_stop(self) -> None:
        """Stop tilt motor."""
        if self._remote.head_up is not None:
            await self._move_motor("head", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self.write_command(
            self._build_command(0),
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.write_command(
            self._build_command(self._remote.flat),
            repeat_count=100,
            repeat_delay_ms=300,
        )

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: self._remote.memory_1,
            2: self._remote.memory_2,
            3: self._remote.memory_3,
            4: self._remote.memory_4,
        }
        command = commands.get(memory_num)
        if command is not None:
            await self.write_command(
                self._build_command(command),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        else:
            _LOGGER.warning(
                "Memory %d not available on remote %s", memory_num, self._variant
            )

    async def _execute_command(
        self,
        cmd: int | OkimatComplexCommand,
        default_count: int,
        default_delay_ms: int,
    ) -> None:
        """Execute a command with appropriate timing.

        Handles both simple int commands (using default timing) and
        OkimatComplexCommand objects (using their embedded timing).
        """
        if isinstance(cmd, OkimatComplexCommand):
            await self.write_command(
                self._build_command(cmd.data),
                repeat_count=cmd.count,
                repeat_delay_ms=cmd.wait_time,
            )
        else:
            await self.write_command(
                self._build_command(cmd),
                repeat_count=default_count,
                repeat_delay_ms=default_delay_ms,
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Note: Okimat remotes use a single memory_save command that saves to the
        last-used memory slot. The memory_num parameter is logged but the actual
        slot saved depends on the remote's internal state.
        """
        cmd = self._remote.memory_save
        if cmd is not None:
            _LOGGER.debug(
                "Saving to memory slot %d on remote %s (remote determines actual slot)",
                memory_num,
                self._variant,
            )
            await self._execute_command(cmd, default_count=10, default_delay_ms=200)
        else:
            _LOGGER.warning(
                "Memory save not available on remote %s", self._variant
            )

    # Light methods
    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        await self._execute_command(
            self._remote.toggle_lights, default_count=50, default_delay_ms=100
        )

    # Massage methods (may not work on all Okimat remotes - inherited from Keeson)
    async def massage_toggle(self) -> None:
        """Toggle massage."""
        await self.write_command(self._build_command(0x100))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(0x800))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(0x800000))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(0x400))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(0x1000000))

    async def massage_mode_step(self) -> None:
        """Step through massage modes/timer."""
        await self.write_command(self._build_command(0x200))
