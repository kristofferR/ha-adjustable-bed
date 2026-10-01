"""Cool Base bed controller implementation.

Reverse engineering from com.keeson.coolbase APK.

Cool Base is a Keeson/Ergomotion variant with additional cooling fan features.
Uses the same FFE0/FFE5 service UUIDs as Keeson BaseI5 with 8-byte command packets.

Unique features:
- Left/Right fan control with 3 speed levels (0-3)
- Sync fan mode for both sides
- DewertOKIN OKIN-BLE compatibility profile with a second memory slot

The Cool Base profile follows the accepted com.keeson.coolbase 1.0.0 audit
(docs/apk-analysis/dispositions/row047-coolbase.md): every app frame carries a
literal trailer that the builder below reproduces, release ends the 100 ms
refresh without a distinct STOP frame, and fan/massage/light state arrives only
in 28-byte replies to the all-zero status query.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from .base import BedController, ControllerButtonSpec, ControllerStateSensorSpec

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# App timing (RemoteFragment): each tapped control is followed by three status
# queries, each preceded by a 200 ms sleep; a connected idle screen queries
# every 3000 ms.
_CLICK_QUERY_COUNT = 3
_CLICK_QUERY_DELAY = 0.2
STATUS_POLL_INTERVAL = 3.0
STATUS_REPLY_LENGTH = 28
# How long an on/off light request waits for a reply to its own status query.
_LIGHT_STATE_WAIT = 1.0

STATE_LEFT_FAN = "coolbase_left_fan_level"
STATE_RIGHT_FAN = "coolbase_right_fan_level"
STATE_MASSAGE_MODE = "coolbase_massage_mode"
STATE_LIGHT = "coolbase_light_on"


class CoolBaseCommands:
    """Cool Base command constants (32-bit values in little-endian byte order)."""

    # Motor commands (cmd0 byte)
    MOTOR_HEAD_UP = 0x01
    MOTOR_HEAD_DOWN = 0x02
    MOTOR_FEET_UP = 0x04
    MOTOR_FEET_DOWN = 0x08

    # Presets (cmd1/cmd3 bytes)
    PRESET_FLAT = 0x08000000  # cmd3=0x08
    PRESET_ZERO_G = 0x00001000  # cmd1=0x10
    PRESET_TV = 0x00004000  # cmd1=0x40
    PRESET_ANTI_SNORE = 0x00008000  # cmd1=0x80
    PRESET_MEMORY_1 = 0x00010000  # cmd2=0x01
    PRESET_MEMORY_2 = 0x00040000  # cmd2=0x04 on DewertOKIN OKIN-BLE devices

    # Light (cmd2 byte)
    TOGGLE_LIGHT = 0x00020000  # cmd2=0x02

    # Massage (cmd1/cmd3 bytes)
    MASSAGE_HEAD = 0x00000800  # cmd1=0x08
    MASSAGE_FOOT = 0x00000400  # cmd1=0x04
    MASSAGE_LEVEL = 0x04000000  # cmd3=0x04

    # Star artwork button (cmd2=0x01); the app gives it no memory semantics
    STAR = 0x00010000

    # Fan/Wind commands (cmd2/cmd3 bytes) - Unique to Cool Base
    FAN_LEFT = 0x00400000  # cmd2=0x40 - cycles through levels 0-3
    FAN_RIGHT = 0x40000000  # cmd3=0x40 - cycles through levels 0-3
    FAN_SYNC = 0x00040000  # cmd2=0x04 - both fans together


class CoolBaseController(BedController):
    """Controller for Cool Base beds (Keeson BaseI5 with fan control)."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        dewert_okin_profile: bool = False,
    ) -> None:
        """Initialize the Cool Base controller.

        Args:
            coordinator: The AdjustableBedCoordinator instance
            dewert_okin_profile: True for OKIN-BLE/DewertOKIN devices using the
                Cool Base packet format without Cool Base fan controls.
        """
        super().__init__(coordinator)
        self._dewert_okin_profile = dewert_okin_profile
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}

        # State from 28-byte status replies; None until a reply reports it
        self._left_fan_level: int | None = None
        self._right_fan_level: int | None = None
        self._massage_level: int | None = None
        self._light_on: bool | None = None
        self._status_received = asyncio.Event()
        self._write_mode_initialized = False
        self._write_char: BleakGATTCharacteristic | None = None

        self._char_uuid = KEESON_BASE_WRITE_CHAR_UUID
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID

        _LOGGER.debug("CoolBaseController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return self._char_uuid

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        # The Cool Base app has no lounge preset; the DewertOKIN profile keeps
        # its historical Memory 1 alias.
        return self._dewert_okin_profile

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        # The Cool Base app's star frame has no proven memory meaning; it is
        # exposed as its own app-labelled button instead.
        return self._dewert_okin_profile

    @property
    def memory_slot_count(self) -> int:
        return 2 if self._dewert_okin_profile else 0

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False  # Toggle only

    @property
    def supports_light_state_feedback(self) -> bool:
        """Cool Base replies report the light flag; on/off uses it to toggle."""
        return not self._dewert_okin_profile

    @property
    def supports_stop_all(self) -> bool:
        return True  # Send zero command

    @property
    def supports_fan_control(self) -> bool:
        """Return True - Cool Base has fan control."""
        return not self._dewert_okin_profile

    @property
    def fan_level_max(self) -> int:
        """Return maximum fan level (0-3 scale)."""
        return 3

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        """App-labelled Cool Base controls with no inferred axis or memory meaning."""
        if self._dewert_okin_profile:
            return ()
        actions = (
            ("left_fan", "mdi:fan", CoolBaseCommands.FAN_LEFT, False),
            ("right_fan", "mdi:fan", CoolBaseCommands.FAN_RIGHT, False),
            ("fan_sync", "mdi:fan-plus", CoolBaseCommands.FAN_SYNC, False),
            ("head_massage", "mdi:vibrate", CoolBaseCommands.MASSAGE_HEAD, False),
            ("foot_massage", "mdi:vibrate", CoolBaseCommands.MASSAGE_FOOT, False),
            ("massage_mode", "mdi:sine-wave", CoolBaseCommands.MASSAGE_LEVEL, False),
            ("star", "mdi:star", CoolBaseCommands.STAR, True),
        )
        return tuple(
            ControllerButtonSpec(
                f"coolbase_{action}",
                action.replace("_", " ").capitalize(),
                lambda ctrl, value=value: cast(CoolBaseController, ctrl).tap(value),
                icon,
                translation_key=f"coolbase_{action}",
                cancel_movement=cancel_movement,
            )
            for action, icon, value, cancel_movement in actions
        )

    # The Cool Base profile exposes the app's massage taps as named buttons;
    # the generic toggle/up/down controls would duplicate the same frames.
    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._dewert_okin_profile

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self._dewert_okin_profile

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self._dewert_okin_profile

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        """Fan and massage-mode levels reported by the 28-byte status reply."""
        if self._dewert_okin_profile:
            return ()
        return (
            ControllerStateSensorSpec(STATE_LEFT_FAN, STATE_LEFT_FAN, STATE_LEFT_FAN, "mdi:fan"),
            ControllerStateSensorSpec(STATE_RIGHT_FAN, STATE_RIGHT_FAN, STATE_RIGHT_FAN, "mdi:fan"),
            ControllerStateSensorSpec(
                STATE_MASSAGE_MODE, STATE_MASSAGE_MODE, STATE_MASSAGE_MODE, "mdi:sine-wave"
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        """Drop Cool Base state sensors if the entry resolves to the DewertOKIN profile."""
        if not self._dewert_okin_profile:
            return frozenset()
        return frozenset({STATE_LEFT_FAN, STATE_RIGHT_FAN, STATE_MASSAGE_MODE})

    @property
    def requires_notification_channel(self) -> bool:
        """Status replies to the app query arrive as notifications, even without angles."""
        return not self._dewert_okin_profile

    @property
    def diagnostic_poll_interval(self) -> float | None:
        """Mirror the app's 3000 ms status query on an already live connection."""
        return None if self._dewert_okin_profile else STATUS_POLL_INTERVAL

    async def async_refresh_diagnostics(self) -> None:
        """Send one app status query; the reply arrives as a notification."""
        await self._send_status_query()

    def invalidate_diagnostics(self) -> None:
        """Forget reported state and the discovered write instance when the BLE session ends."""
        self._write_char = None
        self._write_mode_initialized = False
        self._left_fan_level = self._right_fan_level = self._massage_level = None
        self._light_on = None
        self._status_received.clear()
        if not self._dewert_okin_profile:
            self.forward_controller_state_updates(
                {STATE_LEFT_FAN: None, STATE_RIGHT_FAN: None, STATE_MASSAGE_MODE: None, STATE_LIGHT: None}
            )

    def _build_command(self, cmd0: int = 0, cmd1: int = 0, cmd2: int = 0, cmd3: int = 0) -> bytes:
        """Build an 8-byte command packet.

        Format: [0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, trailer]
        The Cool Base app sends the trailer as a literal; this formula reproduces
        every literal it ships (tests pin all of them).
        """
        header = [0xE5, 0xFE, 0x16]
        data = header + [cmd0, cmd1, cmd2, cmd3]
        checksum = sum(data) ^ 0xFF
        data.append(checksum & 0xFF)
        return bytes(data)

    def _build_command_from_value(self, command_value: int) -> bytes:
        """Build command from 32-bit value (little-endian byte order)."""
        cmd0 = command_value & 0xFF
        cmd1 = (command_value >> 8) & 0xFF
        cmd2 = (command_value >> 16) & 0xFF
        cmd3 = (command_value >> 24) & 0xFF
        return self._build_command(cmd0, cmd1, cmd2, cmd3)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        _LOGGER.debug(
            "Writing command to Cool Base bed: %s (repeat: %d, delay: %dms)",
            command.hex(),
            repeat_count,
            repeat_delay_ms,
        )
        self._init_write_mode()
        await self._write_gatt_with_retry(
            self._char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
            characteristic=self._write_char,
        )

    def _init_write_mode(self) -> None:
        """Mirror Android's default write type, which the Cool Base app never changes.

        Android starts a characteristic that advertises write-without-response in
        WRITE_TYPE_NO_RESPONSE; otherwise it writes with response.
        """
        if self._write_mode_initialized or self._dewert_okin_profile:
            return
        client = self.client
        if client is None or not client.is_connected:
            return
        for service in client.services:
            # The app's dead alternate writer uses the same characteristic UUID
            # under FFE0; only the FFE5 instance is the live destination.
            if service.uuid.lower() != KEESON_BASE_SERVICE_UUID:
                continue
            for char in service.characteristics:
                if char.uuid.lower() == self._char_uuid:
                    props = {prop.lower() for prop in char.properties}
                    self._write_with_response = "write-without-response" not in props
                    self._write_char = char
                    self._write_mode_initialized = True
                    return

    async def _send_status_query(self) -> None:
        """Send the app's all-zero status query frame."""
        await self.write_command(self._build_command(), cancel_event=asyncio.Event())

    async def tap(self, command_value: int) -> None:
        """Send one tapped app control, then the app's three follow-up status queries."""
        await self.write_command(self._build_command_from_value(command_value))
        if self._dewert_okin_profile:
            return
        for _ in range(_CLICK_QUERY_COUNT):
            await asyncio.sleep(_CLICK_QUERY_DELAY)
            await self._send_status_query()

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return

        try:
            await self.client.start_notify(
                self._notify_char_uuid,
                self._on_notification,
            )
            _LOGGER.debug("Started notifications for Cool Base bed")
        except BleakError:
            if self.requires_notification_channel:
                # Status replies only arrive here; fail the connect so it retries.
                raise
            _LOGGER.warning("Failed to start notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes) -> None:
        """Parse a status reply exactly as the Cool Base app does.

        Only exact 28-byte replies are used. Byte 13 ``(b & 0xF0) >> 6`` is the
        light flag (0 off, 1 on); byte 19 is the massage mode and bytes 20/21 the
        left/right fan levels (0-3). Any other value leaves that field unchanged.
        """
        if len(data) != STATUS_REPLY_LENGTH:
            return

        light = (data[13] & 0xF0) >> 6
        if light in (0, 1):
            self._light_on = light == 1
        if data[19] <= 3:
            self._massage_level = data[19]
        if data[20] <= 3:
            self._left_fan_level = data[20]
        if data[21] <= 3:
            self._right_fan_level = data[21]
        self._status_received.set()
        if not self._dewert_okin_profile:
            self.forward_controller_state_updates(
                {
                    STATE_LEFT_FAN: self._left_fan_level,
                    STATE_RIGHT_FAN: self._right_fan_level,
                    STATE_MASSAGE_MODE: self._massage_level,
                    STATE_LIGHT: self._light_on,
                }
            )

        _LOGGER.debug(
            "Cool Base state: light=%s, massage=%s, left_fan=%s, right_fan=%s",
            self._light_on,
            self._massage_level,
            self._left_fan_level,
            self._right_fan_level,
        )

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        if self.client is None or not self.client.is_connected:
            return

        try:
            await self.client.stop_notify(self._notify_char_uuid)
            _LOGGER.debug("Stopped notifications")
        except BleakError:
            _LOGGER.debug("Failed to stop notifications")

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data (not supported on Cool Base)."""

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor, then send the all-zero frame.

        The app releases a hold by ending its 100 ms refresh and sends no
        distinct STOP. The trailing all-zero frame is the app's own status
        query, so it adds no invented command and requests fresh state.
        """
        self._motor_state[motor] = direction
        cmd0 = 0

        # Build combined motor command
        state = self._motor_state
        if state.get("head") is True:
            cmd0 += CoolBaseCommands.MOTOR_HEAD_UP
        elif state.get("head") is False:
            cmd0 += CoolBaseCommands.MOTOR_HEAD_DOWN
        if state.get("feet") is True:
            cmd0 += CoolBaseCommands.MOTOR_FEET_UP
        elif state.get("feet") is False:
            cmd0 += CoolBaseCommands.MOTOR_FEET_DOWN

        try:
            if cmd0:
                await self.write_command(
                    self._build_command(cmd0=cmd0),
                    repeat_count=self._coordinator.motor_pulse_count,
                    repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
                )
        finally:
            self._motor_state = {}
            try:
                await self.write_command(
                    self._build_command(),  # All zeros = stop
                    cancel_event=asyncio.Event(),
                )
            except Exception:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_motor("head", True)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_motor("head", False)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._move_motor("head", None)

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self._move_motor("feet", False)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("feet", None)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor("feet", True)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor("feet", False)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._move_motor("feet", None)

    async def stop_all(self) -> None:
        """End movement and send the all-zero (status query) frame."""
        self._motor_state = {}
        await self.write_command(
            self._build_command(),  # All zeros = stop
            cancel_event=asyncio.Event(),
        )

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self.tap(CoolBaseCommands.PRESET_FLAT)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (DewertOKIN profile only)."""
        commands: dict[int, int] = {}
        if self._dewert_okin_profile:
            commands = {1: CoolBaseCommands.PRESET_MEMORY_1, 2: CoolBaseCommands.PRESET_MEMORY_2}

        if command := commands.get(memory_num):
            await self.write_command(self._build_command_from_value(command))
        else:
            _LOGGER.warning(
                "Cool Base memory slot %d not supported (valid: %s)",
                memory_num,
                sorted(commands),
            )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (not supported)."""
        _LOGGER.warning("Cool Base doesn't support programming memory presets")

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self.tap(CoolBaseCommands.PRESET_ZERO_G)

    async def preset_lounge(self) -> None:
        """Go to lounge position (same as Memory 1)."""
        await self.preset_memory(1)

    async def preset_tv(self) -> None:
        """Go to TV position."""
        await self.tap(CoolBaseCommands.PRESET_TV)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self.tap(CoolBaseCommands.PRESET_ANTI_SNORE)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on lights, toggling only when the reported state is off."""
        await self._set_light_state(True)

    async def lights_off(self) -> None:
        """Turn off lights, toggling only when the reported state is on."""
        await self._set_light_state(False)

    async def _set_light_state(self, is_on: bool) -> None:
        if self._dewert_okin_profile:
            await self.lights_toggle()
            return
        if self._light_on is None:
            self._status_received.clear()
            await self._send_status_query()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(_LIGHT_STATE_WAIT):
                    await self._status_received.wait()
        if self._light_on is None:
            raise HomeAssistantError(
                "Cool Base light state is unknown; no status reply was received."
            )
        if self._light_on != is_on:
            await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.tap(CoolBaseCommands.TOGGLE_LIGHT)

    def get_light_state(self) -> dict[str, Any]:
        """Return the light flag from the latest status reply."""
        return {"is_on": self._light_on}

    # Massage methods
    async def massage_toggle(self) -> None:
        """Toggle massage (cycles through levels)."""
        await self.tap(CoolBaseCommands.MASSAGE_LEVEL)

    async def massage_head_up(self) -> None:
        """Increase head massage."""
        await self.tap(CoolBaseCommands.MASSAGE_HEAD)

    async def massage_head_down(self) -> None:
        """Decrease head massage (not directly supported, use toggle)."""
        await self.massage_head_up()

    async def massage_foot_up(self) -> None:
        """Increase foot massage."""
        await self.tap(CoolBaseCommands.MASSAGE_FOOT)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage (not directly supported, use toggle)."""
        await self.massage_foot_up()

    # Fan control methods (unique to Cool Base)
    async def fan_left_cycle(self) -> None:
        """Cycle left fan through levels 0-3."""
        await self.tap(CoolBaseCommands.FAN_LEFT)

    async def fan_right_cycle(self) -> None:
        """Cycle right fan through levels 0-3."""
        await self.tap(CoolBaseCommands.FAN_RIGHT)

    async def fan_sync_cycle(self) -> None:
        """Cycle both fans together through levels 0-3."""
        await self.tap(CoolBaseCommands.FAN_SYNC)

    @property
    def left_fan_level(self) -> int | None:
        """Get the last reported left fan level (0-3)."""
        return self._left_fan_level

    @property
    def right_fan_level(self) -> int | None:
        """Get the last reported right fan level (0-3)."""
        return self._right_fan_level

    @property
    def led_on(self) -> bool | None:
        """Get the last reported light flag."""
        return self._light_on

    @property
    def massage_level(self) -> int | None:
        """Get the last reported massage mode (0-3)."""
        return self._massage_level
