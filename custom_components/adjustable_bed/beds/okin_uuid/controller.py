"""Okin UUID-based bed controller implementation.

Reverse engineering by david_nagy, corne, PT, and Richard Hopton (smartbed-mqtt).

This controller handles beds that use the Okin 6-byte protocol via BLE UUID writes.
Known brands using this protocol:
- Okimat
- Various Okin-based OEM beds

Commands are 32-bit Okin N-frames (``codec/okin_nframe.py``); timing is the
``OKIMAT`` profile and the keys come from the selected handset's remote table.
These beds require BLE pairing before use.

Note: This shares the Okin service UUID with Leggett & Platt Okin and Nectar beds.
Detection uses device name patterns to distinguish between these bed types.

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

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ...codec import okin_nframe as codec
from ...const import (
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_FOOT_MAX_ANGLE,
    OKIN_FOOT_MAX_RAW,
    OKIN_HEAD_MAX_ANGLE,
    OKIN_HEAD_MAX_RAW,
    VARIANT_AUTO,
)
from ...profiles.okin_nframe import OKIMAT, OkinNFrameProfile, Tap
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import MotorControlSpec
from ..furnimove.profiles import FURNIMOVE_PRODUCTION_IDS, FurniMoveProfile, get_furnimove_profile
from ..okin_nframe import OkinNFrameController
from .remotes import (
    DEFAULT_OKIN_UUID_REMOTE,
    OKIN_DOT_VARIANT_LABELS,
    OKIN_UUID_REMOTE_DATA,
    OKIN_UUID_VARIANT_LABELS,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


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
    toggle_lights: int | None = None
    sync: int | None = None  # Re-sync both sides of a split base
    child_lock: int | None = None  # Toggle handset child lock
    zero_gravity: int | None = None  # Zero-gravity preset (rare)
    quiet_sleep: int | None = None  # Quiet-sleep preset (rare)
    anti_snore: int | None = None  # Anti-snore preset (DOT RF1058 codes)
    # True for "DOT PROTOCOL" handsets (RF1058/RF34/RF6707): same keycode
    # space, but the box takes CB24-style 7-byte frames over Nordic UART.
    # Driven by OkinDotController (okin_dot.py), not this controller.
    dot: bool = False
    # Massage sub-commands keyed by function name (authoritative backend values).
    # Recognised keys: head_up, head_down, foot_up, foot_down, stop, wave, all,
    # mode1, mode2, mode3, head_toggle, foot_toggle.
    massage: dict[str, int] | None = None


def _remote_config(kwargs: dict) -> OkinUuidRemoteConfig:
    """Build a remote config, expanding generated (keycode, count, delay) holds."""
    expanded: dict[str, Any] = dict(kwargs)
    memory_save = expanded.get("memory_save")
    if isinstance(memory_save, tuple):
        expanded["memory_save"] = OkinUuidComplexCommand(*memory_save)
    return OkinUuidRemoteConfig(**expanded)


# FurniMove action name -> remote config field. M1-M4 are the app's head, back,
# legs and feet channels; "Out" raises and "In" lowers.
_FURNIMOVE_FIELDS: Final = {
    "Flat": "flat",
    "M1Out": "head_up",
    "M1In": "head_down",
    "M2Out": "back_up",
    "M2In": "back_down",
    "M3Out": "legs_up",
    "M3In": "legs_down",
    "M4Out": "feet_up",
    "M4In": "feet_down",
    "Sync": "sync",
    "ChildLock": "child_lock",
    "ZeroGravity": "zero_gravity",
    "QuietSleep": "quiet_sleep",
    "UBL": "toggle_lights",
    "Memo1": "memory_1",
    "Memo2": "memory_2",
    "Memo3": "memory_3",
    "Memo4": "memory_4",
}
_FURNIMOVE_MASSAGE: Final = {
    "MassagerHeadPlus": "head_up",
    "MassagerHeadMinus": "head_down",
    "MassagerFeetPlus": "foot_up",
    "MassagerFeetMinus": "foot_down",
    "MassagerStop": "stop",
    "MassagerWave": "wave",
    "MassageAll": "all",
    "Massager1": "mode1",
    "Massager2": "mode2",
    "Massager3": "mode3",
    "MassagerHead": "head_toggle",
    "MassagerFeet": "foot_toggle",
}


def _furnimove_remote(profile: FurniMoveProfile, *, dot: bool) -> OkinUuidRemoteConfig:
    """Project a pinned FurniMove handset table onto this controller's fields.

    The first row of each name wins, as in the app. MemoSave keeps its hold
    timing; UBL stays a single press. Rows this controller has no consumer for
    (Reset, the standby release, mode switches) are skipped. Only DOT handsets
    map Snore, matching the table v4.0.2 shipped.
    """
    description = (profile.description or "").strip().strip('"').strip()
    model = re.match(r"[A-Za-z0-9/\-]+", description) if description else None
    fields: dict[str, Any] = {
        "name": model.group(0) if model else (description[:20] or "Okin RF"),
        "dot": dot,
    }
    massage: dict[str, int] = {}
    for row in profile.actions:
        keycode = int(row.keycode, 16)
        if row.action == "MemoSave":
            if row.duration_ms and row.frequency_ms:
                if row.duration_ms % row.frequency_ms:
                    raise ValueError(f"{profile.handset_id}: MemoSave hold is not whole ticks")
                fields.setdefault(
                    "memory_save",
                    OkinUuidComplexCommand(
                        keycode, row.duration_ms // row.frequency_ms, row.frequency_ms
                    ),
                )
            else:
                fields.setdefault("memory_save", keycode)
        elif row.action == "Snore" and dot:
            fields.setdefault("anti_snore", keycode)
        elif field := _FURNIMOVE_FIELDS.get(row.action):
            fields.setdefault(field, keycode)
        elif key := _FURNIMOVE_MASSAGE.get(row.action):
            massage.setdefault(key, keycode)
    return OkinUuidRemoteConfig(**fields, massage=massage or None)


# Handsets in the pinned FurniMove production catalog take their keycodes only
# from it; the generated table holds the remaining codes. New setups keep the
# standard handsets on this route, which adds the BLE bond and FFE4 position
# feedback the FurniMove app profile lacks. The DOT handsets move to FurniMove,
# whose per-consumer framing is the app's exact behavior.
FURNIMOVE_STANDARD_HANDSETS: Final = FURNIMOVE_PRODUCTION_IDS & frozenset(OKIN_UUID_VARIANT_LABELS)
FURNIMOVE_DOT_HANDSETS: Final = FURNIMOVE_PRODUCTION_IDS & frozenset(OKIN_DOT_VARIANT_LABELS)

OKIN_UUID_REMOTES: dict[str, OkinUuidRemoteConfig] = {
    code: (
        _furnimove_remote(get_furnimove_profile(code), dot=code in FURNIMOVE_DOT_HANDSETS)
        if code in FURNIMOVE_PRODUCTION_IDS
        else _remote_config(OKIN_UUID_REMOTE_DATA[code])
    )
    for code in sorted({*OKIN_UUID_VARIANT_LABELS, *OKIN_DOT_VARIANT_LABELS}, key=int)
}

# Default remote for auto-detect (most common/basic)
DEFAULT_REMOTE = DEFAULT_OKIN_UUID_REMOTE


class OkinUuidController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
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

    # Timing and framing of this route. Subclasses with their own command
    # surface (the stair lift, DOT boxes) replace it.
    _route_profile: ClassVar[OkinNFrameProfile] = OKIMAT

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"variant": self._variant}

    @property
    def profile(self) -> OkinNFrameProfile:
        """This route's profile."""
        return self._route_profile

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
        return self._remote.memory_1 is not None

    @property
    def memory_slot_count(self) -> int:
        """Return the highest memory slot this remote defines."""
        remote = self._remote
        slots = (remote.memory_1, remote.memory_2, remote.memory_3, remote.memory_4)
        return max((slot for slot, key in enumerate(slots, 1) if key is not None), default=0)

    @property
    def supports_memory_programming(self) -> bool:
        """Return True if this remote has a memory save key."""
        return self._remote.memory_save is not None

    @property
    def supports_lights(self) -> bool:
        """Return True only when this remote's handset has a light (UBL) key."""
        return self._remote.toggle_lights is not None

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only supports toggle, not discrete on/off."""
        return False

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for position notifications.

        OKIN beds report position via BLE notifications on characteristic FFE4.
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
            await self.client.start_notify(codec.POSITION_UUID, self._handle_position_notification)
            _LOGGER.info(
                "Position notifications active for Okin UUID bed (UUID: %s)", codec.POSITION_UUID
            )
        except BleakError as err:
            _LOGGER.debug(
                "Could not start position notifications for Okin UUID bed: %s "
                "(bed may not support position feedback)",
                err,
            )

    def _handle_position_notification(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle a position notification (see ``codec.parse_position``).

        Head 0-16000 raw maps to 0-60 degrees and foot 0-12000 raw to 0-45.
        """
        self.forward_raw_notification(codec.POSITION_UUID, bytes(data))

        positions = codec.parse_position(bytes(data))
        if positions is None:
            _LOGGER.debug("Received invalid position data: expected 7+ bytes, got %d", len(data))
            return

        _LOGGER.debug("Okin UUID position notification: %s", data.hex())
        head_raw, foot_raw = positions
        head_angle = min(
            round((head_raw / OKIN_HEAD_MAX_RAW) * OKIN_HEAD_MAX_ANGLE, 1), OKIN_HEAD_MAX_ANGLE
        )
        foot_angle = min(
            round((foot_raw / OKIN_FOOT_MAX_RAW) * OKIN_FOOT_MAX_ANGLE, 1), OKIN_FOOT_MAX_ANGLE
        )
        _LOGGER.debug(
            "Okin UUID position: head=%d raw (%.1f deg), foot=%d raw (%.1f deg)",
            head_raw,
            head_angle,
            foot_raw,
            foot_angle,
        )

        if self._notify_callback:
            # "back" is the primary head/back motor, "legs" the foot/legs motor.
            self._notify_callback("back", head_angle)
            self._notify_callback("legs", foot_angle)

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(codec.POSITION_UUID)
            _LOGGER.debug("Stopped position notifications for Okin UUID bed")
        except BleakError:
            pass

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Read current position data.

        OKIN beds typically use notifications rather than reads for position
        data. This method attempts a read but may not work on all beds.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot read positions: not connected")
            return

        try:
            async with self._ble_lock:
                data = await self.client.read_gatt_char(codec.POSITION_UUID)
            if data:
                _LOGGER.debug("Read Okin UUID position data: %s", data.hex())
                self._handle_position_notification(0, bytearray(data))  # type: ignore[arg-type]
        except BleakError as err:
            _LOGGER.debug("Could not read position data: %s", err)

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        """Hold a motor key, or release it with ``None``.

        Active motors' keys are summed into one command word, so motors held
        together move together. Stopping one motor removes only its key; STOP
        follows only when no other motor is still held.
        Reference: https://github.com/richardhopton/smartbed-mqtt/pull/66
        """
        if command_value is None or command_value == 0:
            self._motor_state.pop(motor, None)
        else:
            self._motor_state[motor] = command_value

        combined_command = sum(self._motor_state.values())
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
            self._motor_state.pop(motor, None)
            if not self._motor_state:
                await self._send_stop()

    # When the remote has a dedicated head/tilt motor (M1 keycodes), the head
    # controls drive it; otherwise head is the usual synonym for the primary
    # back motor on 2-motor remotes.
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

    async def _move_defined(self, motor: str, keycode: int | None) -> None:
        if keycode is None:
            _LOGGER.debug("%s motor not available on remote %s", motor.title(), self._variant)
            return
        await self._move_motor(motor, keycode)

    async def move_back_up(self) -> None:
        await self._move_defined("back", self._remote.back_up)

    async def move_back_down(self) -> None:
        await self._move_defined("back", self._remote.back_down)

    async def move_back_stop(self) -> None:
        await self._move_motor("back", None)

    async def move_legs_up(self) -> None:
        await self._move_defined("legs", self._remote.legs_up)

    async def move_legs_down(self) -> None:
        await self._move_defined("legs", self._remote.legs_down)

    async def move_legs_stop(self) -> None:
        await self._move_motor("legs", None)

    # Feet: a separate motor on some remotes; others map feet to legs.
    async def move_feet_up(self) -> None:
        if self._remote.feet_up is not None:
            await self._move_motor("feet", self._remote.feet_up)
        else:
            await self.move_legs_up()

    async def move_feet_down(self) -> None:
        if self._remote.feet_down is not None:
            await self._move_motor("feet", self._remote.feet_down)
        else:
            await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        if self._remote.feet_up is not None:
            await self._move_motor("feet", None)
        else:
            await self.move_legs_stop()

    # Tilt: the dedicated head motor, on remotes that have one.
    async def move_tilt_up(self) -> None:
        if self._remote.head_up is not None:
            await self._move_motor("head", self._remote.head_up)
        else:
            _LOGGER.debug("Tilt motor not available on remote %s", self._variant)

    async def move_tilt_down(self) -> None:
        if self._remote.head_down is not None:
            await self._move_motor("head", self._remote.head_down)
        else:
            _LOGGER.debug("Tilt motor not available on remote %s", self._variant)

    async def move_tilt_stop(self) -> None:
        if self._remote.head_up is not None:
            await self._move_motor("head", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self._send_stop()

    async def _press(self, keycode: int | None, tap: Tap | None, name: str) -> None:
        """Send a remote key as a fixed burst and its STOP, if the remote has it."""
        if keycode is None or tap is None:
            _LOGGER.debug("%s not available on remote %s", name, self._variant)
            return
        await self._tap_then_stop(keycode, tap, name)

    @property
    def supports_preset_flat(self) -> bool:
        """Return True only when this remote defines a flat/home command."""
        return self._remote.flat is not None

    async def preset_flat(self) -> None:
        await self._press(self._remote.flat, self._route_profile.recall, "Flat preset")

    async def preset_memory(self, memory_num: int) -> None:
        remote = self._remote
        command = {1: remote.memory_1, 2: remote.memory_2, 3: remote.memory_3, 4: remote.memory_4}
        keycode = command.get(memory_num)
        if keycode is None:
            _LOGGER.warning("Memory %d not available on remote %s", memory_num, self._variant)
            return
        profile = self._route_profile
        await self._press(keycode, profile.memory_recall or profile.recall, f"Memory {memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        """Program the current position.

        These remotes use one memory save key that saves to the last-used
        slot, so ``memory_num`` is only logged.
        """
        cmd = self._remote.memory_save
        save = self._route_profile.memory_save
        if cmd is None or save is None:
            _LOGGER.warning("Memory save not available on remote %s", self._variant)
            return
        _LOGGER.debug(
            "Saving to memory slot %d on remote %s (remote determines actual slot)",
            memory_num,
            self._variant,
        )
        if isinstance(cmd, OkinUuidComplexCommand):
            # The handset's own MemoSave hold timing.
            save = Tap(repeats=cmd.count, repeat_ms=cmd.wait_time)
            cmd = cmd.data
        await self.write_command(
            self._build_command(cmd), repeat_count=save.repeats, repeat_delay_ms=save.repeat_ms
        )

    async def lights_on(self) -> None:
        """Turn on under-bed lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off under-bed lights (via toggle - no discrete control)."""
        await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights with one press.

        Repeating the key causes visible flashing and can end in "off".
        """
        if self._remote.toggle_lights is None:
            _LOGGER.debug("Under-bed light not available on remote %s", self._variant)
            return
        await self.write_command(self._build_command(self._remote.toggle_lights))

    # Massage keycodes come from the per-remote table. Only remotes whose
    # handset exposes massage keys advertise these capabilities.
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
        await self._massage_press("all")

    async def massage_off(self) -> None:
        await self._massage_press("stop")

    async def massage_head_toggle(self) -> None:
        await self._massage_press("head_toggle")

    async def massage_foot_toggle(self) -> None:
        await self._massage_press("foot_toggle")

    async def massage_head_up(self) -> None:
        await self._massage_press("head_up")

    async def massage_head_down(self) -> None:
        await self._massage_press("head_down")

    async def massage_foot_up(self) -> None:
        await self._massage_press("foot_up")

    async def massage_foot_down(self) -> None:
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

    @property
    def supports_sync(self) -> bool:
        """Return True if the remote can re-sync both sides of a split base."""
        return self._remote.sync is not None

    async def sync_positions(self) -> None:
        """Re-synchronise both sides of a split base.

        The handset streams this key for ~6 s and releases with STOP, like
        every other held key.
        """
        await self._press(self._remote.sync, self._route_profile.long_press, "Sync")

    @property
    def supports_child_lock(self) -> bool:
        """Return True if the remote can toggle the handset child lock."""
        return self._remote.child_lock is not None

    async def child_lock_toggle(self) -> None:
        """Toggle the handset child lock (held command)."""
        await self._press(self._remote.child_lock, self._route_profile.long_press, "Child lock")

    @property
    def supports_preset_zero_g(self) -> bool:
        """Return True if the remote exposes a dedicated zero-gravity preset."""
        return self._remote.zero_gravity is not None

    async def preset_zero_g(self) -> None:
        await self._press(self._remote.zero_gravity, self._route_profile.recall, "Zero-gravity")

    @property
    def _anti_snore_keycode(self) -> int | None:
        """Anti-snore preset keycode, falling back to quiet-sleep.

        RF1058 handsets carry the same 0x4000 preset slot as either "Snore"
        (91983/93558) or "QuietSleep" (90167); both are a sleep-position
        preset, so a quiet-sleep-only remote drives the anti-snore button.
        """
        if self._remote.anti_snore is not None:
            return self._remote.anti_snore
        return self._remote.quiet_sleep

    @property
    def supports_preset_anti_snore(self) -> bool:
        """Return True if the remote exposes an anti-snore/quiet-sleep preset."""
        return self._anti_snore_keycode is not None

    async def preset_anti_snore(self) -> None:
        await self._press(self._anti_snore_keycode, self._route_profile.recall, "Anti-snore")


async def build_controller(ctx: BuildContext) -> BedController:
    """Build the Okin UUID controller, or the receiver the live link turns out to be."""
    variant = ctx.variant or "auto"
    await ctx.preload("dewertokin_rf_gateway")
    from ..dewertokin_rf_gateway import DewertOkinUuidRfGatewayController, is_rf_gateway

    if is_rf_gateway(ctx):
        _LOGGER.info(
            "Auto-detected DewertOkin RF-Gateway command endpoint for %s "
            "using Okin UUID variant %s",
            ctx.coordinator.address,
            variant,
        )
        return DewertOkinUuidRfGatewayController(ctx.coordinator, variant=variant)

    # FurniMove flags a DOT box by its Nordic UART write characteristic. A DOT
    # box has no Okin 62741523 service, so require both signals to avoid
    # demoting a standard Okimat box that also exposes Nordic UART.
    if ctx.has_characteristic(
        NORDIC_UART_SERVICE_UUID, NORDIC_UART_WRITE_CHAR_UUID
    ) and not ctx.has_characteristic(OKIMAT_SERVICE_UUID, OKIMAT_WRITE_CHAR_UUID):
        await ctx.preload("okin_dot")
        from ..okin_dot import OkinDotController

        _LOGGER.info(
            "Auto-detected DewertOkin DOT PROTOCOL box for %s "
            "(Nordic UART, no Okin 62741523 service); using variant %s",
            ctx.coordinator.address,
            variant,
        )
        return OkinDotController(ctx.coordinator, variant=variant)

    _LOGGER.debug("Using Okin UUID variant: %s", variant)
    return OkinUuidController(ctx.coordinator, variant=variant)
