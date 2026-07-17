"""Sleepy's Elite BOX25 Star controller implementation.

Reverse-engineered from the Sleepy's Elite app (com.okin.bedding.sleepy)
for the DewertOkin BOX25 Star controller using Nordic UART Service.

Protocol: BOX25 Star (NUS-based StarCode)
BLE Name: Star*
Service: Nordic UART (6e400001-b5a3-f393-e0a9-e50e24dcca9e)
Write:   TX characteristic (6e400002)
Notify:  RX characteristic (6e400003)

Command formats:
- Motor/preset/light/massage: 5A 01 03 10 [category] [key] A5 (7 bytes)
- Position:                   5A F0 03 [zone] [position] 00 A5 (7 bytes)
- Position query:             5A B0 00 A5 (4 bytes)

The OEM app sends commands every 100 ms while a button is held and writes normal
commands to Nordic UART without response. Its one-time wake write uses a response
and is sent before notifications are enabled. A BOX25_STAR controller must not be
confused with the legacy BOX25 packet formats bundled in the same app.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import NORDIC_UART_WRITE_CHAR_UUID
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _star_command(key: int, category: int = 0x30) -> bytes:
    """Build an OEM BOX25_STAR command frame."""
    return bytes([0x5A, 0x01, 0x03, 0x10, category, key, 0xA5])


def _star_extended(subcommand: int, value: int, value2: int = 0) -> bytes:
    """Build an OEM BOX25_STAR extended-value frame."""
    return bytes([0x5A, 0xE0, 0x04, subcommand, value, value2, 0x00, 0xA5])


_MASSAGE_MODES = (0x52, 0x53, 0x54)


class Box25Commands:
    """BOX25 Star protocol command constants."""

    # The previously used 00 D0 / 00 B0 initializers and 05/08/04 command
    # families belong to legacy BOX25. The Sleepy's app selects BOX25_STAR after
    # the NUS/Device Information check and uses StarCode for every control.
    WAKE = bytes([0x5A, 0x0B, 0x00, 0xA5])
    QUERY_STATUS = bytes([0x5A, 0xB0, 0x00, 0xA5])

    MOTOR_STOP = _star_command(0x0F)
    HEAD_UP = _star_command(0x00)
    HEAD_DOWN = _star_command(0x01)
    FOOT_UP = _star_command(0x02)
    FOOT_DOWN = _star_command(0x03)
    LUMBAR_UP = _star_command(0x06)
    LUMBAR_DOWN = _star_command(0x07)
    NECK_TILT_UP = _star_command(0x0A)
    NECK_TILT_DOWN = _star_command(0x0B)

    STAR_PRESET_FLAT = _star_command(0x10)
    STAR_PRESET_TV = _star_command(0x11)
    STAR_PRESET_ZERO_GRAVITY = _star_command(0x13)
    STAR_PRESET_ANTI_SNORE = _star_command(0x16)
    STAR_PRESET_LOUNGE = _star_command(0x17)  # app "reading"
    STAR_PRESET_MEMORY_1 = _star_command(0x1A)
    STAR_PRESET_MEMORY_2 = _star_command(0x1B)
    STAR_MEMORY_PRESETS = (STAR_PRESET_MEMORY_1, STAR_PRESET_MEMORY_2)
    STAR_PRESET_TERMINATOR = MOTOR_STOP

    # Saving a position is a long-press operation in the M1X12 app. It repeats
    # the selected key 110 times at the sender's 100 ms interval, without a
    # trailing terminator.
    STAR_STORE_MEMORY_1 = _star_command(0x94)
    STAR_STORE_MEMORY_2 = _star_command(0x95)
    STAR_MEMORY_STORE = (STAR_STORE_MEMORY_1, STAR_STORE_MEMORY_2)

    LIGHT_ON_WHITE = _star_command(0x73)
    LIGHT_OFF = _star_command(0x74)
    LIGHT_TOGGLE = _star_command(0x71)
    MASSAGE_TOGGLE = _star_command(0x5A)
    MASSAGE_EXIT = _star_command(0x6F)
    MASSAGE_WAVE1 = _star_command(0x52)
    MASSAGE_WAVE2 = _star_command(0x53)
    MASSAGE_WAVE3 = _star_command(0x54)
    MASSAGE_INTENSITY_UP = _star_command(0x60, category=0x40)
    MASSAGE_INTENSITY_DOWN = _star_command(0x61, category=0x40)
    MASSAGE_HEAD_UP = _star_command(0x60)
    MASSAGE_HEAD_DOWN = _star_command(0x61)
    MASSAGE_FOOT_UP = _star_command(0x62)
    MASSAGE_FOOT_DOWN = _star_command(0x63)
    MASSAGE_MODES = (MASSAGE_WAVE1, MASSAGE_WAVE2, MASSAGE_WAVE3)


# Preset send tuning, mirroring the decompiled "Adjustable Comfort M1X12" app
# (StarCode/DewertOkin CB25 protocol). The app enqueues every preset as four
# packets drained 100 ms apart by its periodic BLE sender: the preset key ×3,
# then a terminator that *commits* the preset — the bed arms while it keeps
# receiving the key and only drives to the target once the terminator arrives.
# The terminator is the StarCode 0x0F packet. See _send_preset (#372).
_PRESET_REPEAT_COUNT = 3
_PRESET_REPEAT_DELAY_MS = 100
_PRESET_COMMIT_DELAY = 0.1
_MEMORY_STORE_REPEAT_COUNT = 110


class SleepysBox25Controller(BedController):
    """Controller for Sleepy's Elite BOX25 Star beds.

    Uses the OEM app's BOX25_STAR command family over Nordic UART. All controls
    share the same StarCode framing and use write-without-response.

    Presets are armed by repeating the StarCode key, then committed by a trailing
    StarCode 0x0F frame — see _send_preset (#372).
    """

    # Position feedback: head/feet/lumbar at 0-100 percentage
    _HEAD_MAX_ANGLE: float = 100.0
    _FEET_MAX_ANGLE: float = 100.0
    _LUMBAR_MAX_ANGLE: float = 100.0

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the BOX25 Star controller."""
        super().__init__(coordinator)
        self._initialized = False
        self._head_position: float | None = None
        self._foot_position: float | None = None
        self._lumbar_position: float | None = None
        self._is_moving = False
        self._massage_active = False
        self._massage_mode_index = -1  # First step selects OEM mode 1.
        self._massage_intensity = 0
        self._massage_timer_minutes = 0
        self._light_level: int | None = None

    # ─── BLE Properties ──────────────────────────────────────────────────

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the Nordic UART TX characteristic UUID."""
        return NORDIC_UART_WRITE_CHAR_UUID

    # ─── Capability Properties ───────────────────────────────────────────

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_neck_support(self) -> bool:
        return True

    @property
    def has_tilt_support(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        """Expose the one combined intensity slider proven by the OEM app."""
        return ["all"]

    @property
    def massage_intensity_max(self) -> int:
        """Return the OEM UI's normalized 0-7 intensity range."""
        return 7

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def supports_light_level_control(self) -> bool:
        return True

    @property
    def light_level_max(self) -> int:
        """Return the OEM UI's exact 0-6 brightness range."""
        return 6

    @property
    def supports_position_feedback(self) -> bool:
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose the BOX25 motor surface using the integration's public motor names."""
        return (
            MotorControlSpec(
                key="head",
                translation_key="head",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
                position_key="head",
                max_angle=100,
            ),
            MotorControlSpec(
                key="feet",
                translation_key="feet",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                position_key="feet",
                max_angle=100,
            ),
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                position_key="lumbar",
                max_angle=100,
            ),
            MotorControlSpec(
                key="tilt",
                translation_key="head_end_tilt",
                open_fn=lambda ctrl: ctrl.move_tilt_up(),
                close_fn=lambda ctrl: ctrl.move_tilt_down(),
                stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
                max_angle=45,
            ),
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove stale standard-layout entities from older BOX25 setups."""
        return frozenset({"back", "legs"})

    # ─── Init / Write Helpers ────────────────────────────────────────────

    def _effective_cancel_event(
        self,
        cancel_event: asyncio.Event | None = None,
    ) -> asyncio.Event | None:
        """Return the command-specific cancel event, falling back to the coordinator event."""
        return cancel_event if cancel_event is not None else self._coordinator.cancel_command

    def _is_cancelled(self, cancel_event: asyncio.Event | None = None) -> bool:
        """Return True when the active cancel event has been set."""
        effective_cancel = self._effective_cancel_event(cancel_event)
        return effective_cancel.is_set() if effective_cancel is not None else False

    async def _ensure_initialized(self, cancel_event: asyncio.Event | None = None) -> None:
        """Send the proven Star wake frame once per connection."""
        if self._initialized or self._is_cancelled(cancel_event):
            return

        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            Box25Commands.WAKE,
            cancel_event=cancel_event,
            response=True,
        )
        if self._is_cancelled(cancel_event):
            return
        self._initialized = True

    async def _write_motor_command(
        self,
        command: bytes,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a BOX25_STAR motor or position command."""
        await self.write_command(command, cancel_event=cancel_event)

    async def _write_massage_light_command(
        self,
        command: bytes,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a BOX25_STAR massage or light command."""
        await self.write_command(command, cancel_event=cancel_event)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a BOX25_STAR command using the OEM app's BLE write mode."""
        if self._is_cancelled(cancel_event):
            return
        await self._ensure_initialized(cancel_event)
        if self._is_cancelled(cancel_event):
            return
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    # ─── Notification Handling ───────────────────────────────────────────

    def _on_notification(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle BLE notification data from the bed."""
        raw = bytes(data)
        self.forward_raw_notification(characteristic.uuid, raw)

        if len(raw) < 2:
            return

        length = len(raw)

        if length >= 19 and raw[0:2] == bytes([0xA5, 0x0D]):
            # Both legacy BOX25 and BOX25_STAR use this shared status parser.
            # The Sleepy's app reads the 0-100 motor positions from bytes 4, 6,
            # and 8 respectively and clamps them.
            for key, attr, position in (
                ("head", "_head_position", raw[4]),
                ("feet", "_foot_position", raw[6]),
                ("lumbar", "_lumbar_position", raw[8]),
            ):
                value = float(min(100, max(0, position)))
                setattr(self, attr, value)
                if self._notify_callback:
                    self._notify_callback(key, value)
            self._is_moving = raw[17] != 0
        elif length >= 16 and raw[0:2] == bytes([0xA5, 0x0B]):
            # The app buckets the big-endian remaining duration into its three
            # timer choices. Other nibble fields are intentionally not assigned
            # semantics here because this app's recovered model names are gone.
            seconds = (raw[4] << 8) | raw[5]
            if 1 <= seconds <= 600:
                minutes = 10
            elif 601 <= seconds <= 1200:
                minutes = 20
            elif 1201 <= seconds <= 1800:
                minutes = 30
            else:
                minutes = 0
            self._massage_timer_minutes = minutes
            self._massage_active = seconds > 0
            self.forward_controller_state_updates(
                {
                    "massage_timer": minutes,
                    "massage_active": self._massage_active,
                }
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for position notifications via Nordic UART RX."""
        from ..const import NORDIC_UART_READ_CHAR_UUID

        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            # The OEM session writes wake with response before enabling RX.
            await self._ensure_initialized()
            await client.start_notify(NORDIC_UART_READ_CHAR_UUID, self._on_notification)
            _LOGGER.debug("Subscribed to BOX25 notifications")
        except BleakError:
            _LOGGER.warning("Could not subscribe to BOX25 notifications")

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        from ..const import NORDIC_UART_READ_CHAR_UUID

        self._notify_callback = None
        client = self.client
        if client is not None and client.is_connected:
            try:
                await client.stop_notify(NORDIC_UART_READ_CHAR_UUID)
            except BleakError:
                pass

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Request the shared BOX25 status frame used for motor positions."""
        await self.write_command(Box25Commands.QUERY_STATUS)

    # ─── Direct Position Control ─────────────────────────────────────────

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Set a motor to a specific position (0-100)."""
        zone_map = {
            "head": 0x00,
            "back": 0x00,
            "feet": 0x01,
            "legs": 0x01,
            "lumbar": 0x02,
        }
        zone = zone_map.get(motor)
        if zone is None:
            raise ValueError(f"Unknown motor: {motor}")

        pos = max(0, min(100, int(position)))
        cmd = bytes([0x5A, 0xF0, 0x03, zone, pos, 0x00, 0xA5])
        await self._write_motor_command(cmd)

    def angle_to_native_position(self, motor: str, angle: float) -> int:  # noqa: ARG002
        """Convert angle to position (0-100 percentage-based)."""
        return int(max(0, min(100, angle)))

    # ─── Motor Control ───────────────────────────────────────────────────

    async def _send_stop(self) -> None:
        """Send motor stop command with a fresh cancel event."""
        stop_event = asyncio.Event()
        await self.write_command(Box25Commands.MOTOR_STOP, cancel_event=stop_event)

    async def move_head_up(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_UP)

    async def move_head_down(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_UP)

    async def move_back_down(self) -> None:
        await self._move_with_stop(Box25Commands.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_UP)

    async def move_legs_down(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_UP)

    async def move_feet_down(self) -> None:
        await self._move_with_stop(Box25Commands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # ─── Lumbar Motor ────────────────────────────────────────────────────

    async def move_lumbar_up(self) -> None:
        await self._move_with_stop(Box25Commands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        await self._move_with_stop(Box25Commands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    # ─── Neck Motor ──────────────────────────────────────────────────────

    async def move_neck_up(self) -> None:
        await self._move_with_stop(Box25Commands.NECK_TILT_UP)

    async def move_neck_down(self) -> None:
        await self._move_with_stop(Box25Commands.NECK_TILT_DOWN)

    async def move_neck_stop(self) -> None:
        await self._send_stop()

    async def move_tilt_up(self) -> None:
        """Expose the neck motor through the integration's standard tilt surface."""
        await self.move_neck_up()

    async def move_tilt_down(self) -> None:
        """Expose the neck motor through the integration's standard tilt surface."""
        await self.move_neck_down()

    async def move_tilt_stop(self) -> None:
        """Expose the neck motor through the integration's standard tilt surface."""
        await self.move_neck_stop()

    # ─── Presets ─────────────────────────────────────────────────────────

    async def _send_preset(self, preset_cmd: bytes) -> None:
        """Send a preset (key ×3 at 100 ms), then commit it with StarCode 0x0F.

        The decompiled "Adjustable Comfort M1X12" app (StarCode/DewertOkin CB25
        protocol, e.g. Star252201 / Ashley/Nectar M1X1232) sends every preset as
        the preset key ×3 at 100 ms followed by a terminator packet. The trailing
        terminator is what *commits* the preset: the bed arms while it keeps
        receiving the key and only drives to the target once the terminator
        arrives.

        Without it the bed stays armed but never moves until the user manually
        presses Stop All or disconnects (#372). Conversely a terminator sent too
        soon (the old 50 ms confirm) lands before the bed arms and cancels the
        preset — hence the key is repeated first to hold it long enough.

        Star* devices use StarCode framing (5A 01 03 10 30 KK A5), including
        Memory 1/2. The terminator's framing must match its preset key's framing.
        """
        try:
            await self.write_command(
                preset_cmd,
                repeat_count=_PRESET_REPEAT_COUNT,
                repeat_delay_ms=_PRESET_REPEAT_DELAY_MS,
            )
            await asyncio.sleep(_PRESET_COMMIT_DELAY)
        finally:
            try:
                # Fresh cancel event so a pending Stop All can't suppress the
                # commit packet — without it the preset never executes.
                await self.write_command(
                    Box25Commands.STAR_PRESET_TERMINATOR,
                    cancel_event=asyncio.Event(),
                )
            except (BleakError, ConnectionError):
                _LOGGER.debug(
                    "Failed to send committing terminator after preset",
                    exc_info=True,
                )

    async def preset_flat(self) -> None:
        await self._send_preset(Box25Commands.STAR_PRESET_FLAT)

    async def preset_tv(self) -> None:
        await self._send_preset(Box25Commands.STAR_PRESET_TV)

    async def preset_zero_g(self) -> None:
        await self._send_preset(Box25Commands.STAR_PRESET_ZERO_GRAVITY)

    async def preset_anti_snore(self) -> None:
        await self._send_preset(Box25Commands.STAR_PRESET_ANTI_SNORE)

    async def preset_lounge(self) -> None:
        """Move bed to lounge or relax position."""
        await self._send_preset(Box25Commands.STAR_PRESET_LOUNGE)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num < 1 or memory_num > len(Box25Commands.STAR_MEMORY_PRESETS):
            _LOGGER.warning("Invalid memory slot %d (valid: 1-2)", memory_num)
            return
        await self._send_preset(Box25Commands.STAR_MEMORY_PRESETS[memory_num - 1])

    async def program_memory(self, memory_num: int) -> None:
        if memory_num < 1 or memory_num > len(Box25Commands.STAR_MEMORY_STORE):
            _LOGGER.warning("Invalid memory slot %d (valid: 1-2)", memory_num)
            return
        await self.write_command(
            Box25Commands.STAR_MEMORY_STORE[memory_num - 1],
            repeat_count=_MEMORY_STORE_REPEAT_COUNT,
            repeat_delay_ms=_PRESET_REPEAT_DELAY_MS,
        )

    # ─── Lights ──────────────────────────────────────────────────────────

    async def lights_on(self) -> None:
        await self._write_massage_light_command(Box25Commands.LIGHT_ON_WHITE)

    async def lights_off(self) -> None:
        await self._write_massage_light_command(Box25Commands.LIGHT_OFF)

    async def lights_toggle(self) -> None:
        await self._write_massage_light_command(Box25Commands.LIGHT_TOGGLE)

    async def set_light_level(self, level: int) -> None:
        """Set the exact OEM 0-6 under-bed light brightness value."""
        normalized = max(0, min(self.light_level_max, int(level)))
        await self._write_massage_light_command(_star_extended(0x00, normalized))
        self._light_level = normalized
        self.forward_controller_state_updates(
            {
                "light_level": normalized,
                "under_bed_lights_on": normalized > 0,
            }
        )

    # ─── Massage ─────────────────────────────────────────────────────────

    async def massage_off(self) -> None:
        """Exit massage mode."""
        await self._write_motor_command(Box25Commands.MASSAGE_EXIT)
        self._massage_active = False
        self._massage_timer_minutes = 0
        self.forward_controller_state_updates(
            {"massage_active": False, "massage_timer": 0}
        )

    async def massage_toggle(self) -> None:
        """Send the OEM's dedicated massage on/off toggle."""
        await self._write_massage_light_command(Box25Commands.MASSAGE_TOGGLE)
        self._massage_active = not self._massage_active
        self.forward_controller_state_update("massage_active", self._massage_active)

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity (both zones)."""
        await self._write_massage_light_command(Box25Commands.MASSAGE_INTENSITY_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity (both zones)."""
        await self._write_massage_light_command(Box25Commands.MASSAGE_INTENSITY_DOWN)

    async def massage_head_up(self) -> None:
        await self._write_massage_light_command(Box25Commands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        await self._write_massage_light_command(Box25Commands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        await self._write_massage_light_command(Box25Commands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        await self._write_massage_light_command(Box25Commands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """Cycle through massage wave modes (wave1 -> wave2 -> wave3 -> wave1)."""
        self._massage_mode_index = (self._massage_mode_index + 1) % len(_MASSAGE_MODES)
        await self._write_massage_light_command(
            Box25Commands.MASSAGE_MODES[self._massage_mode_index]
        )

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        """Set the combined massage intensity exactly as the OEM slider does."""
        if zone != "all":
            raise ValueError(f"Unsupported BOX25 massage zone: {zone}")
        normalized = max(0, min(self.massage_intensity_max, int(level)))
        # The UI presents 0..7 but encodes positive levels as 2..8. Feedback
        # decoders in the corroborating StarCode apps subtract one again.
        encoded = normalized + 1 if normalized > 0 else 0
        await self._write_massage_light_command(_star_extended(0x06, encoded, encoded))
        self._massage_intensity = normalized
        self.forward_controller_state_update("massage_intensity", normalized)

    async def set_massage_timer(self, minutes: int) -> None:
        """Select the OEM massage timer (10/20/30 minutes), or turn it off."""
        if minutes == 0:
            await self.massage_off()
            return
        try:
            encoded = self.massage_timer_options.index(int(minutes)) + 1
        except ValueError as err:
            raise ValueError(
                f"Unsupported BOX25 massage timer {minutes}; "
                f"expected one of {self.massage_timer_options}"
            ) from err
        await self._write_massage_light_command(_star_extended(0x07, encoded))
        self._massage_timer_minutes = int(minutes)
        self.forward_controller_state_update("massage_timer", int(minutes))

    def get_massage_state(self) -> dict[str, object]:
        """Return normalized combined intensity and timer state."""
        return {
            "intensity": self._massage_intensity,
            "timer_mode": str(self._massage_timer_minutes),
            "active": self._massage_active,
        }


def _legacy_normal(key: int) -> bytes:
    """Build the OEM legacy CB25 32-bit normal frame."""
    return b"\x05\x02" + int(key).to_bytes(4, "big") + b"\x00"


def _legacy_extended(subcommand: int, value: int, value2: int = 0) -> bytes:
    """Build the OEM legacy CB25 extended-value frame."""
    return bytes([0x04, 0xE0, subcommand, value, value2, 0x00])


_LEGACY_NORMAL_BY_STAR_KEY: dict[tuple[int, int], bytes] = {
    # Motors and STOP.
    (0x30, 0x00): _legacy_normal(0x00000001),
    (0x30, 0x01): _legacy_normal(0x00000002),
    (0x30, 0x02): _legacy_normal(0x00000004),
    (0x30, 0x03): _legacy_normal(0x00000008),
    (0x30, 0x06): _legacy_normal(0x00000010),
    (0x30, 0x07): _legacy_normal(0x00000020),
    (0x30, 0x0A): _legacy_normal(0x00000040),
    (0x30, 0x0B): _legacy_normal(0x00000080),
    (0x30, 0x0F): _legacy_normal(0x00000000),
    # Presets and memory.
    (0x30, 0x10): _legacy_normal(0x08000000),
    (0x30, 0x11): _legacy_normal(0x00004000),
    (0x30, 0x13): _legacy_normal(0x00001000),
    (0x30, 0x16): _legacy_normal(0x00008000),
    (0x30, 0x17): _legacy_normal(0x00002000),
    (0x30, 0x1A): _legacy_normal(0x00010000),
    (0x30, 0x1B): _legacy_normal(0x00040000),
    (0x30, 0x94): _legacy_normal(0x08010000),
    (0x30, 0x95): _legacy_normal(0x08040000),
    # Light and massage actions exposed by the Sleepy's control surface.
    (0x30, 0x71): bytes.fromhex("08020002000000000000"),
    (0x30, 0x73): _legacy_extended(0x01, 0x01),
    (0x30, 0x74): _legacy_extended(0x01, 0x00),
    (0x30, 0x5A): _legacy_normal(0x00080000),
    (0x30, 0x6F): _legacy_normal(0x02000000),
    (0x30, 0x52): bytes.fromhex("08020000000000080000"),
    (0x30, 0x53): bytes.fromhex("08020000000000100000"),
    (0x30, 0x54): bytes.fromhex("08020000000000200000"),
    (0x30, 0x60): _legacy_normal(0x00000800),
    (0x30, 0x61): _legacy_normal(0x00800000),
    (0x30, 0x62): _legacy_normal(0x00000400),
    (0x30, 0x63): _legacy_normal(0x01000000),
    (0x40, 0x60): _legacy_normal(0x00000C00),
    (0x40, 0x61): _legacy_normal(0x01800000),
}


def _translate_star_to_legacy(command: bytes) -> bytes:
    """Translate an inherited BOX25 Star action into the proven legacy dialect."""
    if command == Box25Commands.WAKE:
        # Sleepy's sends this transport wake for both runtime dialects.
        return command
    if command == Box25Commands.QUERY_STATUS:
        return b"\x00\xD0"
    if len(command) == 7 and command[:4] == b"\x5A\x01\x03\x10" and command[-1] == 0xA5:
        try:
            return _LEGACY_NORMAL_BY_STAR_KEY[(command[4], command[5])]
        except KeyError as err:
            raise ValueError(
                "No artifact-proven legacy CB25 mapping for StarCode action "
                f"{command.hex()}"
            ) from err
    if len(command) == 7 and command[:3] == b"\x5A\xF0\x03" and command[-1] == 0xA5:
        return bytes([0x03, 0xF0, command[3], command[4], 0x00])
    if len(command) == 8 and command[:3] == b"\x5A\xE0\x04" and command[-1] == 0xA5:
        return _legacy_extended(command[3], command[4], command[5])
    raise ValueError(f"Unsupported StarCode frame for legacy CB25: {command.hex()}")


class SleepysBox25LegacyController(SleepysBox25Controller):
    """Sleepy's BOX25 runtime controller using the legacy CB25 wire dialect.

    The OEM app uses this dialect when the Device Information manufacturer
    value does not contain ``star``. Session setup and feedback parsing are
    shared with BOX25_STAR; every outbound action is translated to the exact
    legacy packet family recovered from the same app.
    """

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Translate inherited actions and write the legacy frame without response."""
        if self._is_cancelled(cancel_event):
            return
        translated = _translate_star_to_legacy(command)
        if self._is_cancelled(cancel_event):
            return
        await self._ensure_initialized(cancel_event)
        if self._is_cancelled(cancel_event):
            return
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            translated,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    async def _ensure_initialized(self, cancel_event: asyncio.Event | None = None) -> None:
        """Send the common transport wake without translating it recursively."""
        if self._initialized or self._is_cancelled(cancel_event):
            return
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            Box25Commands.WAKE,
            cancel_event=cancel_event,
            response=True,
        )
        if not self._is_cancelled(cancel_event):
            self._initialized = True
