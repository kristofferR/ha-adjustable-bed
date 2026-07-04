"""Okin UUID-based bed controller implementation.

Reverse engineering by david_nagy, corne, PT, and Richard Hopton (smartbed-mqtt).

This controller handles beds that use the Okin 6-byte protocol via BLE UUID writes.
Known brands using this protocol:
- Okimat
- Various Okin-based OEM beds

These beds use the Okin protocol with 6-byte commands: [0x04, 0x02, ...int_to_bytes(command)]
They require BLE pairing before use.

Note: This shares the same BLE service UUID (62741523-52f9-8864-b1ab-3b3a8d65950b) with
Leggett & Platt Okin variant and Nectar beds. Detection uses device name patterns to
distinguish between these bed types. See okin_protocol.py for shared protocol details.

Supported remote codes (configured via variant):
- RFS-ELLIPSE/06: 76688, 78375, 78378, 78386, 80599, 80602, 80608, 80616
- RF-TOPLINE basic: 82417, 82620, 82757, 82760, 82764, 82767, 82770, 83358,
  83462, 83489, 84931, 84963, 92461, 93305
- RF-TOPLINE/11: 82418, 85058, 92471, 93306
- RF-LITELINE/07: 88875, 88877, 89137, 89138, 89139, 92535
- RF-FLASHLINE/07: 91244
- RF-FLASHLINE/09: 91246, 92591, 94238
- 93329: RF TOPLINE (Head, Back, Legs, 4 Memory)
- 93332: RF TOPLINE (Head, Back, Legs, Feet, 2 Memory)

Reference: https://github.com/richardhopton/smartbed-mqtt
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_FOOT_MAX_ANGLE,
    OKIN_FOOT_MAX_RAW,
    OKIN_HEAD_MAX_ANGLE,
    OKIN_HEAD_MAX_RAW,
    OKIN_POSITION_NOTIFY_CHAR_UUID,
    VARIANT_AUTO,
)
from .base import BedController, MotorControlSpec
from .okin_protocol import build_okin_command
from .okin_uuid_remotes import (
    DEFAULT_OKIN_UUID_REMOTE,
    OKIN_UUID_REMOTE_DATA,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Error message constant for connection checks
_NOT_CONNECTED_MSG = "Not connected to bed"


@dataclass
class OkinUuidComplexCommand:
    """A command with specific timing requirements.

    Some commands require specific repeat count and delay timing.
    Reference: https://github.com/richardhopton/smartbed-mqtt/commit/6b18011
    """

    data: int  # The command code
    count: int  # Number of times to repeat
    wait_time: int  # Delay in ms between repeats


@dataclass
class OkinUuidRemoteConfig:
    """Configuration for a specific remote model."""

    name: str
    flat: int | None = None  # Some basic RF-ECO remotes have no flat/home button
    # Motor keycodes. The generated table is authoritative about which motors a
    # handset actually drives, so absent motors stay None instead of inheriting
    # family defaults — the controller only exposes controls for defined axes.
    back_up: int | None = None
    back_down: int | None = None
    legs_up: int | None = None
    legs_down: int | None = None
    head_up: int | None = None  # Head/tilt motor (M1, usually 0x10/0x20)
    head_down: int | None = None
    feet_up: int | None = None  # Separate feet motor (M4, usually 0x40/0x80)
    feet_down: int | None = None
    memory_1: int | None = None
    memory_2: int | None = None
    memory_3: int | None = None
    memory_4: int | None = None
    memory_save: int | OkinUuidComplexCommand | None = None
    # UBL (under-bed lights); None when the handset has no light key.
    toggle_lights: int | OkinUuidComplexCommand | None = None
    sync: int | None = None  # Re-sync both sides of a split base
    child_lock: int | None = None  # Toggle handset child lock
    zero_gravity: int | None = None  # Zero-gravity preset (rare)
    quiet_sleep: int | None = None  # Quiet-sleep preset (rare)
    # Massage sub-commands keyed by function name (authoritative backend values).
    # Recognised keys: head_up, head_down, foot_up, foot_down, stop, wave, all,
    # mode1, mode2, mode3, head_toggle, foot_toggle.
    massage: dict[str, int] | None = None


def _remote_config(kwargs: dict) -> OkinUuidRemoteConfig:
    """Build a remote config, expanding generated (keycode, count, delay) holds."""
    expanded: dict[str, Any] = dict(kwargs)
    for key in ("memory_save", "toggle_lights"):
        value = expanded.get(key)
        if isinstance(value, tuple):
            expanded[key] = OkinUuidComplexCommand(*value)
    return OkinUuidRemoteConfig(**expanded)


# The remote table is generated from the DewertOkin handset backend + the
# bundled handsetlist.csv capability flags. See okin_uuid_remotes.py for
# provenance and the tools/okin_remotes/ regeneration pipeline.
OKIN_UUID_REMOTES: dict[str, OkinUuidRemoteConfig] = {
    code: _remote_config(kwargs) for code, kwargs in OKIN_UUID_REMOTE_DATA.items()
}

# Default remote for auto-detect (most common/basic)
DEFAULT_REMOTE = DEFAULT_OKIN_UUID_REMOTE


class OkinUuidController(BedController):
    """Controller for beds using Okin UUID-based protocol.

    Note: These beds require BLE pairing before they can be controlled.
    The pairing must be done through the coordinator during connection.

    Different remote codes have different capabilities:
    - Basic remotes: Back and Legs motors only
    - Memory remotes (82418, 85058, 91246, 92471, 92591, 93306, 94238):
      Back, Legs + 2 memory presets
    - Advanced remotes (93329): Head, Back, Legs + 4 memory presets
    - Full remotes (93332): Head, Back, Legs, Feet + 2 memory presets
    """

    def __init__(self, coordinator: AdjustableBedCoordinator, variant: str = VARIANT_AUTO) -> None:
        """Initialize the Okin UUID controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        # Motor state stores command values per motor (head, back, legs, feet)
        # This allows combining multiple motor commands simultaneously
        # Reference: https://github.com/richardhopton/smartbed-mqtt/pull/66
        self._motor_state: dict[str, int] = {}
        # Cycles the discrete massage programs for handsets without a wave key.
        self._massage_mode_index = 0

        # Resolve variant to remote config
        if variant == VARIANT_AUTO or variant not in OKIN_UUID_REMOTES:
            variant = DEFAULT_REMOTE
        self._variant = variant
        self._remote = OKIN_UUID_REMOTES[variant]

        _LOGGER.debug(
            "OkinUuidController initialized with remote %s (%s)",
            variant,
            self._remote.name,
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OKIMAT_WRITE_CHAR_UUID

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove covers that no longer apply to this remote.

        Installs misdetected as the RF ECO BT stair profile registered a
        ``<address>_stair`` cover. When they are promoted back to this
        multi-motor profile (issue #406), drop that orphaned stair entity so the
        registry and Lovelace card no longer expose a dead control.

        Earlier releases also exposed back/legs covers for every remote, even
        when the handset has no such motor — listing all motor keys here lets
        the cover platform clean up axes this remote doesn't drive (active keys
        are skipped by the cleanup).
        """
        return frozenset({"stair", "back", "legs", "head", "feet"})

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose only the motor axes this remote actually drives.

        The generated table is authoritative about the handset layout, so the
        exposed covers are derived from the per-remote keycodes (in the
        standard back/legs/head/feet order) instead of assuming every remote
        has back+legs. The configured motor count still caps how many axes are
        shown, matching the previous behavior for multi-motor remotes.
        """
        remote = self._remote
        available: list[MotorControlSpec] = []
        if remote.back_up is not None:
            available.append(
                MotorControlSpec(
                    key="back",
                    translation_key="back",
                    open_fn=lambda ctrl: ctrl.move_back_up(),
                    close_fn=lambda ctrl: ctrl.move_back_down(),
                    stop_fn=lambda ctrl: ctrl.move_back_stop(),
                )
            )
        if remote.legs_up is not None:
            available.append(
                MotorControlSpec(
                    key="legs",
                    translation_key="legs",
                    open_fn=lambda ctrl: ctrl.move_legs_up(),
                    close_fn=lambda ctrl: ctrl.move_legs_down(),
                    stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                    max_angle=45,
                )
            )
        if remote.head_up is not None:
            available.append(
                MotorControlSpec(
                    key="head",
                    translation_key="head",
                    open_fn=lambda ctrl: ctrl.move_head_up(),
                    close_fn=lambda ctrl: ctrl.move_head_down(),
                    stop_fn=lambda ctrl: ctrl.move_head_stop(),
                )
            )
        if remote.feet_up is not None:
            available.append(
                MotorControlSpec(
                    key="feet",
                    translation_key="feet",
                    open_fn=lambda ctrl: ctrl.move_feet_up(),
                    close_fn=lambda ctrl: ctrl.move_feet_down(),
                    stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                    max_angle=45,
                )
            )
        return tuple(available[: self._coordinator.motor_count])

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if this remote supports memory presets."""
        # Check if at least memory_1 is available for this remote variant
        return self._remote.memory_1 is not None

    @property
    def memory_slot_count(self) -> int:
        """Return number of memory slots based on remote variant."""
        count = 0
        if self._remote.memory_1 is not None:
            count = 1
        if self._remote.memory_2 is not None:
            count = 2
        if self._remote.memory_3 is not None:
            count = 3
        if self._remote.memory_4 is not None:
            count = 4
        return count

    @property
    def supports_memory_programming(self) -> bool:
        """Return True if this remote supports programming memory positions."""
        # Remotes use a single memory_save command
        return self._remote.memory_save is not None

    @property
    def supports_lights(self) -> bool:
        """Return True only when this remote's handset has a light (UBL) key."""
        return self._remote.toggle_lights is not None

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only supports toggle, not discrete on/off."""
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
            raise ConnectionError(_NOT_CONNECTED_MSG)

        effective_cancel = cancel_event or self._coordinator.cancel_command

        _LOGGER.debug(
            "Writing command to Okin UUID bed (%s): %s (repeat: %d, delay: %dms, response=True)",
            OKIMAT_WRITE_CHAR_UUID,
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            try:
                # Acquire BLE lock to prevent conflicts with concurrent position reads
                async with self._ble_lock:
                    await self.client.write_gatt_char(
                        OKIMAT_WRITE_CHAR_UUID, command, response=True
                    )
            except BleakError:
                _LOGGER.exception("Failed to write command")
                raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
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
            "Setting up position notifications for Okin UUID bed at %s",
            self._coordinator.address,
        )

        try:
            await self.client.start_notify(
                OKIN_POSITION_NOTIFY_CHAR_UUID,
                self._handle_position_notification,
            )
            _LOGGER.info(
                "Position notifications active for Okin UUID bed (UUID: %s)",
                OKIN_POSITION_NOTIFY_CHAR_UUID,
            )
        except BleakError as err:
            _LOGGER.debug(
                "Could not start position notifications for Okin UUID bed: %s "
                "(bed may not support position feedback)",
                err,
            )

    def _handle_position_notification(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle position notification data from OKIN controller.

        Data format (7+ bytes):
        - Bytes 0-2: Unknown (possibly status/header)
        - Bytes 3-4: Head position (little-endian uint16)
        - Bytes 5-6: Foot position (little-endian uint16)

        Position values are normalized:
        - Head: 0-16000 raw -> 0-60 degrees
        - Foot: 0-12000 raw -> 0-45 degrees
        """
        self.forward_raw_notification(OKIN_POSITION_NOTIFY_CHAR_UUID, bytes(data))

        if len(data) < 7:
            _LOGGER.debug(
                "Received invalid position data: expected 7+ bytes, got %d",
                len(data),
            )
            return

        _LOGGER.debug("Okin UUID position notification: %s", data.hex())

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
            "Okin UUID position: head=%d raw (%.1f deg), foot=%d raw (%.1f deg)",
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
            _LOGGER.debug("Stopped position notifications for Okin UUID bed")
        except BleakError:
            pass

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current position data.

        Note: OKIN beds typically use notifications rather than reads for
        position data. This method attempts a read but may not work on all beds.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot read positions: not connected")
            return

        try:
            # Acquire BLE lock to prevent conflicts with concurrent writes
            async with self._ble_lock:
                data = await self.client.read_gatt_char(OKIN_POSITION_NOTIFY_CHAR_UUID)
            if data:
                _LOGGER.debug("Read Okin UUID position data: %s", data.hex())
                self._handle_position_notification(0, bytearray(data))  # type: ignore[arg-type]
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
        pulse_count = getattr(self._coordinator, "motor_pulse_count", 25)
        pulse_delay = getattr(self._coordinator, "motor_pulse_delay_ms", 200)

        try:
            if combined_command:
                await self.write_command(
                    self._build_command(combined_command),
                    repeat_count=pulse_count,
                    repeat_delay_ms=pulse_delay,
                )
        finally:
            # Cleanup: always clear motor state and send stop if no motors active
            self._motor_state.pop(motor, None)

            # Send stop command only if no other motors are active
            if not self._motor_state:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )

    # Motor control methods - Head. When the remote has a dedicated head/tilt
    # motor (M1 keycodes), the head controls drive it; otherwise head is the
    # usual synonym for the primary back motor on 2-motor remotes.
    async def move_head_up(self) -> None:
        """Move head up (dedicated head/tilt motor, or back on 2-motor remotes)."""
        if self._remote.head_up is not None:
            await self._move_motor("head", self._remote.head_up)
        else:
            await self.move_back_up()

    async def move_head_down(self) -> None:
        """Move head down (dedicated head/tilt motor, or back on 2-motor remotes)."""
        if self._remote.head_down is not None:
            await self._move_motor("head", self._remote.head_down)
        else:
            await self.move_back_down()

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        if self._remote.head_up is not None:
            await self._move_motor("head", None)
        else:
            await self.move_back_stop()

    async def move_back_up(self) -> None:
        """Move back up."""
        if self._remote.back_up is None:
            _LOGGER.debug("Back motor not available on remote %s", self._variant)
            return
        await self._move_motor("back", self._remote.back_up)

    async def move_back_down(self) -> None:
        """Move back down."""
        if self._remote.back_down is None:
            _LOGGER.debug("Back motor not available on remote %s", self._variant)
            return
        await self._move_motor("back", self._remote.back_down)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self._move_motor("back", None)

    # Motor control methods - Legs
    async def move_legs_up(self) -> None:
        """Move legs up."""
        if self._remote.legs_up is None:
            _LOGGER.debug("Legs motor not available on remote %s", self._variant)
            return
        await self._move_motor("legs", self._remote.legs_up)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        if self._remote.legs_down is None:
            _LOGGER.debug("Legs motor not available on remote %s", self._variant)
            return
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
    @property
    def supports_preset_flat(self) -> bool:
        """Return True only when this remote defines a flat/home command."""
        return self._remote.flat is not None

    async def preset_flat(self) -> None:
        """Go to flat position."""
        flat = self._remote.flat
        if flat is None:
            _LOGGER.debug("Flat preset not available on remote %s", self._variant)
            return
        try:
            await self.write_command(
                self._build_command(flat),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            try:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )
            except (TimeoutError, BleakError):
                _LOGGER.debug(
                    "Failed to send STOP command during preset_flat cleanup", exc_info=True
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
            try:
                await self.write_command(
                    self._build_command(command),
                    repeat_count=100,
                    repeat_delay_ms=300,
                )
            finally:
                try:
                    await self.write_command(
                        self._build_command(0),
                        cancel_event=asyncio.Event(),
                    )
                except (TimeoutError, BleakError):
                    _LOGGER.debug(
                        "Failed to send STOP command during preset_memory cleanup", exc_info=True
                    )
        else:
            _LOGGER.warning("Memory %d not available on remote %s", memory_num, self._variant)

    async def _execute_command(
        self,
        cmd: int | OkinUuidComplexCommand,
        default_count: int,
        default_delay_ms: int,
    ) -> None:
        """Execute a command with appropriate timing.

        Handles both simple int commands (using default timing) and
        OkinUuidComplexCommand objects (using their embedded timing).
        """
        if isinstance(cmd, OkinUuidComplexCommand):
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

        Note: These remotes use a single memory_save command that saves to the
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
            _LOGGER.warning("Memory save not available on remote %s", self._variant)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off under-bed lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        if self._remote.toggle_lights is None:
            _LOGGER.debug("Under-bed light not available on remote %s", self._variant)
            return
        await self._execute_command(
            # Most Okin UUID remotes treat under-bed lights as a single toggle press.
            # Repeating the command causes visible flashing and can end in "off".
            self._remote.toggle_lights,
            default_count=1,
            default_delay_ms=100,
        )

    # ------------------------------------------------------------------
    # Massage (config-driven; keycodes come from the per-remote table, not
    # from the Keeson protocol). Only remotes whose handset actually exposes
    # massage keys advertise these capabilities.
    # ------------------------------------------------------------------
    @property
    def _massage(self) -> dict[str, int]:
        return self._remote.massage or {}

    @property
    def supports_massage(self) -> bool:
        """Return True only when this remote's handset exposes massage."""
        return bool(self._remote.massage)

    @property
    def supports_massage_toggle_control(self) -> bool:
        """Massage start/toggle maps to the "all zones" key."""
        return "all" in self._massage

    @property
    def supports_massage_off_control(self) -> bool:
        return "stop" in self._massage

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return "head_up" in self._massage and "head_down" in self._massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return "foot_up" in self._massage and "foot_down" in self._massage

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return "head_toggle" in self._massage

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return "foot_toggle" in self._massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return "wave" in self._massage or "mode1" in self._massage

    async def _massage_press(self, key: str) -> None:
        """Send a single massage command if the remote defines it."""
        code = self._massage.get(key)
        if code is None:
            _LOGGER.debug("Massage function %s not available on remote %s", key, self._variant)
            return
        await self.write_command(self._build_command(code))

    async def massage_toggle(self) -> None:
        """Start/toggle massage (all zones)."""
        await self._massage_press("all")

    async def massage_off(self) -> None:
        """Stop massage."""
        await self._massage_press("stop")

    async def massage_head_toggle(self) -> None:
        """Toggle head-zone massage."""
        await self._massage_press("head_toggle")

    async def massage_foot_toggle(self) -> None:
        """Toggle foot-zone massage."""
        await self._massage_press("foot_toggle")

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self._massage_press("head_up")

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self._massage_press("head_down")

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self._massage_press("foot_up")

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self._massage_press("foot_down")

    async def massage_mode_step(self) -> None:
        """Step massage mode.

        Handsets with a wave key step modes through it; handsets with only the
        discrete program keys (mode1/mode2/mode3) have no step key, so cycle
        through the programs on consecutive presses.
        """
        if "wave" in self._massage:
            await self._massage_press("wave")
            return
        modes = [key for key in ("mode1", "mode2", "mode3") if key in self._massage]
        if not modes:
            _LOGGER.debug("No massage modes available on remote %s", self._variant)
            return
        mode = modes[self._massage_mode_index % len(modes)]
        self._massage_mode_index += 1
        await self._massage_press(mode)

    # ------------------------------------------------------------------
    # Sync / child lock / zero-gravity (config-driven extras)
    # ------------------------------------------------------------------
    @property
    def supports_sync(self) -> bool:
        """Return True if the remote can re-sync both sides of a split base."""
        return self._remote.sync is not None

    async def sync_positions(self) -> None:
        """Re-synchronise both sides of a split base (held command)."""
        if self._remote.sync is None:
            _LOGGER.debug("Sync not available on remote %s", self._variant)
            return
        # The handset streams this for ~6s and releases with keycode 0, like
        # every other held key; mirror that as a long hold followed by STOP.
        try:
            await self.write_command(
                self._build_command(self._remote.sync),
                repeat_count=60,
                repeat_delay_ms=100,
            )
        finally:
            try:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )
            except (TimeoutError, BleakError):
                _LOGGER.debug(
                    "Failed to send STOP command during sync cleanup", exc_info=True
                )

    @property
    def supports_child_lock(self) -> bool:
        """Return True if the remote can toggle the handset child lock."""
        return self._remote.child_lock is not None

    async def child_lock_toggle(self) -> None:
        """Toggle the handset child lock (held command)."""
        if self._remote.child_lock is None:
            _LOGGER.debug("Child lock not available on remote %s", self._variant)
            return
        try:
            await self.write_command(
                self._build_command(self._remote.child_lock),
                repeat_count=60,
                repeat_delay_ms=100,
            )
        finally:
            try:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )
            except (TimeoutError, BleakError):
                _LOGGER.debug(
                    "Failed to send STOP command during child lock cleanup", exc_info=True
                )

    @property
    def supports_preset_zero_g(self) -> bool:
        """Return True if the remote exposes a dedicated zero-gravity preset."""
        return self._remote.zero_gravity is not None

    async def preset_zero_g(self) -> None:
        """Go to the zero-gravity preset."""
        if self._remote.zero_gravity is None:
            _LOGGER.debug("Zero-gravity not available on remote %s", self._variant)
            return
        try:
            await self.write_command(
                self._build_command(self._remote.zero_gravity),
                repeat_count=100,
                repeat_delay_ms=300,
            )
        finally:
            try:
                await self.write_command(
                    self._build_command(0),
                    cancel_event=asyncio.Event(),
                )
            except (TimeoutError, BleakError):
                _LOGGER.debug(
                    "Failed to send STOP command during preset_zero_g cleanup", exc_info=True
                )
