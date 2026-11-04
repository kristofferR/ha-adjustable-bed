"""Keeson controller: glue that drives the Keeson codec from a profile.

Reverse engineering by alanbixby and Richard Hopton (smartbed-mqtt).

Every ``keeson`` protocol variant, and the ``ergomotion``, ``serta`` and
``okin_ffe`` bed types, is a profile in ``profiles/keeson.py``; the frames come
from ``codec/keeson.py``. This module keeps what the data cannot express: motor
key combination, the release and touch-up sequences, Sino's emulated light
toggle and absolute massage levels, Ergomotion position notifications, the
Adjustable Lite status poll and the Restonic BT held controls.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..codec import keeson as codec
from ..const import BED_MOTOR_PULSE_DEFAULTS, BED_TYPE_KEESON, KEESON_VARIANT_PURPLE
from ..profiles import keeson as profiles
from ..profiles.keeson import (
    RESTONIC_A_CONTROLS as RESTONIC_A_CONTROLS,
)
from ..profiles.keeson import (
    RESTONIC_B_CONTROLS as RESTONIC_B_CONTROLS,
)
from ..profiles.keeson import (
    KeesonCommands as KeesonCommands,
)
from ..profiles.keeson import (
    KeesonProfile,
)
from ..profiles.keeson import (
    SinoCommands as SinoCommands,
)
from ..profiles.keeson import (
    is_ksbt03c_name as is_ksbt03c_name,
)
from .base import (
    POSITION_UNIT_PERCENT,
    BedController,
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_ADJUSTABLE_LITE_STATUS_MIN_LENGTH = 13
STATE_ADJUSTABLE_LITE_LIGHT = "adjustable_lite_light"
STATE_ADJUSTABLE_LITE_MASSAGE_TIMER = "adjustable_lite_massage_timer"
STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW = "adjustable_lite_massage_timer_raw"
RESTONIC_ZZZ_BUTTON_KEY = "restonic_zzz"


async def _wait_unless_cancelled(event: asyncio.Event, seconds: float) -> None:
    """Wait out the rest of a hold, returning early when STOP is requested."""
    if seconds <= 0 or event.is_set():
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(event.wait(), seconds)


def parse_adjustable_lite_status(data: bytes, *, massage_timer: bool) -> dict[str, Any] | None:
    """Decode an Adjustable Lite notification exactly as the app does.

    Any payload longer than 12 bytes is used, with no header or checksum check.
    Byte 12 equal to 1 lights the bulb icon. The KSBT03C remote also reads a
    big-endian value from bytes 3-4 and shows the 30, 20 or 10 minute timer
    image above 1200, 600 or 0. The app declares no unit for the raw value.
    """
    if len(data) < _ADJUSTABLE_LITE_STATUS_MIN_LENGTH:
        return None
    state: dict[str, Any] = {STATE_ADJUSTABLE_LITE_LIGHT: data[12] == 1}
    if massage_timer:
        raw = (data[3] << 8) | data[4]
        state[STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW] = raw
        state[STATE_ADJUSTABLE_LITE_MASSAGE_TIMER] = (
            30 if raw > 1200 else 20 if raw > 600 else 10 if raw > 0 else 0
        )
    return state


_MOTOR_BITS: dict[str, tuple[int, int]] = {
    "head": (codec.HEAD_UP, codec.HEAD_DOWN),
    "feet": (codec.FOOT_UP, codec.FOOT_DOWN),
    "tilt": (codec.TILT_UP, codec.TILT_DOWN),
    "lumbar": (codec.LUMBAR_UP, codec.LUMBAR_DOWN),
}


class KeesonController(BedController):
    """Controller for every Keeson profile that has no app controller of its own."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str = "base",
        char_uuid: str | None = None,
        *,
        betterliving_presets: bool = False,
        cb1322_presets: bool = False,
        device_name: str | None = None,
    ) -> None:
        """Resolve the profile for ``variant``.

        The raw BLE name is authoritative; the configured name is only used when
        this connection surfaced none, so an edited name never overrides it.
        """
        super().__init__(coordinator)
        self._variant = variant
        self.profile: KeesonProfile = profiles.resolve(
            variant,
            device_name or getattr(coordinator, "name", None),
            ksbt_service=variant == KEESON_VARIANT_PURPLE and self._has_ksbt_service(),
            betterliving=betterliving_presets,
            cb1322=cb1322_presets,
        )
        self._notify_callback: Callable[[str, float], None] | None = None
        self._motor_state: dict[str, bool | None] = {}
        self._write_with_response = True
        self._write_mode_initialized = False

        # State from Ergomotion notifications and Sino's tracked massage levels.
        self._head_position: int | None = None
        self._foot_position: int | None = None
        self._head_moving: bool = False
        self._foot_moving: bool = False
        self._head_massage: int = 0
        self._foot_massage: int = 0
        self._wave_massage: int = 0
        self._led_on: bool = False
        self._timer_mode: str | None = None

        transport = codec.TRANSPORTS[self.profile.transport]
        if char_uuid:
            self._char_uuid = char_uuid
        elif self.profile.fixed_write:
            self._char_uuid = transport.write_uuid
        else:
            self._char_uuid = self._detect_write_uuid(transport)
        self._notify_char_uuid = codec.TRANSPORTS[self.profile.notify].notify_uuid
        _LOGGER.debug(
            "KeesonController initialized (variant: %s, profile: %s, char: %s)",
            variant,
            self.profile.key,
            self._char_uuid,
        )

    def _has_ksbt_service(self) -> bool:
        """Return whether the connected device exposes the KSBT (Nordic UART) service."""
        client = self.client
        if client is None or client.services is None:
            return False
        ksbt = codec.TRANSPORTS["ksbt"].service_uuid
        return any(str(service.uuid).lower() == ksbt for service in client.services)

    def _detect_write_uuid(self, transport: codec.Transport) -> str:
        """Return the first of the primary and fallback write roles the device exposes."""
        client = self.client
        if client is None or client.services is None:
            return transport.write_uuid
        services = {str(service.uuid).lower(): service for service in client.services}
        for service_uuid, write_uuid in (
            (transport.service_uuid, transport.write_uuid),
            *transport.fallbacks,
        ):
            service = services.get(service_uuid.lower())
            if service is not None and service.get_characteristic(write_uuid) is not None:
                if write_uuid != transport.write_uuid:
                    _LOGGER.info("Using fallback service/characteristic: %s/%s", service_uuid, write_uuid)
                return write_uuid
        _LOGGER.warning(
            "No recognized Keeson service/characteristic found. "
            "Please report this to help add support for your device."
        )
        self.log_discovered_services(level=logging.INFO)
        return transport.write_uuid

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
        return "lounge" in self.profile.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.profile.presets and "tv" not in self.profile.unlisted_presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self.profile.presets

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.profile.memory)

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        return self.profile.memory_save is not None

    @property
    def supports_lights(self) -> bool:
        """KSBT04C light mappings are unverified; Purple Premium and Restonic A have no light."""
        return self.profile.lights is not None and self.profile.lights_listed

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.lights == "discrete"

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.profile.lights is not None

    @property
    def has_tilt_support(self) -> bool:
        return self.profile.tilt

    @property
    def has_lumbar_support(self) -> bool:
        return self.profile.lumbar

    @property
    def supports_stop_all(self) -> bool:
        """Return False - Keeson beds don't have a dedicated stop command."""
        return False

    @property
    def reports_percentage_position(self) -> bool:
        """Return True - Keeson/Ergomotion report 0-100 percentage, not angle degrees."""
        return True

    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        """Keeson's head motor moves the back, tilt the head and feet the legs."""
        if not self.profile.keeson_motor_names:
            return None
        return {"head": "keeson_back", "tilt": "keeson_head", "feet": "keeson_legs"}

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        """Ergomotion's percentage sliders.

        Remotes label the axes head/feet; the firmware reports them as
        "back"/"legs". Percentages ignore the user's angle calibration.
        """
        if not self.profile.position_feedback:
            return ()
        return (
            build_position_number_spec(
                "head", max_value=100.0, unit=POSITION_UNIT_PERCENT, position_key="back"
            ),
            build_position_number_spec(
                "feet", max_value=100.0, unit=POSITION_UNIT_PERCENT, position_key="legs"
            ),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return the Keeson motor layout used by entities and timed move."""
        names = self.motor_translation_keys or {}
        specs = [
            MotorControlSpec(
                key="head",
                translation_key=names.get("head", "head"),
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
                position_key="back",
            ),
            MotorControlSpec(
                key="feet",
                translation_key=names.get("feet", "feet"),
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                position_key="legs",
                max_angle=45,
            ),
        ]
        # Extra motors fill the motor count in remote order: tilt, then lumbar.
        optional_specs = []
        if self.has_tilt_support:
            optional_specs.append(
                MotorControlSpec(
                    key="tilt",
                    translation_key=names.get("tilt", "tilt"),
                    open_fn=lambda ctrl: ctrl.move_tilt_up(),
                    close_fn=lambda ctrl: ctrl.move_tilt_down(),
                    stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
                    max_angle=45,
                )
            )
        if self.has_lumbar_support:
            optional_specs.append(
                MotorControlSpec(
                    key="lumbar",
                    translation_key=names.get("lumbar", "lumbar"),
                    open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                    close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                    stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                    max_angle=30,
                )
            )
        specs.extend(optional_specs[: max(0, self._coordinator.motor_count - 2)])

        if "back_legs_up" in self.profile.held_controls:
            # Restonic BT remote B's back glyphs drive head and foot together.
            specs.append(
                MotorControlSpec(
                    key="back_legs",
                    translation_key="back_legs",
                    open_fn=lambda ctrl: cast(KeesonController, ctrl).move_back_legs_up(),
                    close_fn=lambda ctrl: cast(KeesonController, ctrl).move_back_legs_down(),
                    stop_fn=lambda ctrl: cast(KeesonController, ctrl).move_back_legs_stop(),
                    # Drives both axes: a head or foot cover, reversal or Stop
                    # must preempt it, so it overlaps every motor resource.
                    scheduler_resource="motor:*",
                )
            )
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Optional covers that may no longer apply; active keys are skipped."""
        return frozenset({"tilt", "lumbar", "back_legs"})

    @property
    def auto_enable_massage(self) -> bool:
        """Expose massage without opt-in when the Adjustable Lite KSBT03C remote shows it."""
        return self.profile.massage == "zone_steps"

    @property
    def _app_without_generic_massage(self) -> bool:
        return self.profile.massage in ("none", "zone_steps")

    @property
    def supports_massage_toggle_control(self) -> bool:
        return not self._app_without_generic_massage and super().supports_massage_toggle_control

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return (
            not self._app_without_generic_massage
            and super().supports_massage_intensity_step_control
        )

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return (
            not self._app_without_generic_massage
            and super().supports_head_massage_toggle_control
        )

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return (
            not self._app_without_generic_massage
            and super().supports_foot_massage_toggle_control
        )

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        if self._app_without_generic_massage:
            return self.profile.massage == "zone_steps"
        return super().supports_head_massage_intensity_step_control

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        if self._app_without_generic_massage:
            return self.profile.massage == "zone_steps"
        return super().supports_foot_massage_intensity_step_control

    @property
    def supports_massage_mode_step_control(self) -> bool:
        if self._app_without_generic_massage:
            return self.profile.massage == "zone_steps"
        return super().supports_massage_mode_step_control

    @property
    def supports_massage_timer(self) -> bool:
        """Return False - Keeson can only step through timer, not set directly."""
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        """Sino zeroes both zones; Sleep Harmony has an all-zone STOP word."""
        return self.profile.massage == "absolute" or self.profile.massage_off is not None

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self.profile.massage == "absolute"

    @property
    def massage_mode_step_is_timer(self) -> bool:
        """Return True when the shared action sends the Keeson timer-step command."""
        return self.profile.massage != "absolute"

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self.profile.wave_controls

    @property
    def supports_massage_intensity_preset_control(self) -> bool:
        return self.profile.wave_controls

    @property
    def massage_intensity_max(self) -> int:
        return 10 if self.profile.massage == "absolute" else 6

    def _refresh_write_mode(self) -> None:
        """Resolve the write mode required by the selected Keeson profile."""
        if self._write_mode_initialized:
            return
        client = self.client
        if client is None or client.services is None:
            return
        for service in client.services:
            for char in service.characteristics:
                if str(char.uuid).lower() != self._char_uuid.lower():
                    continue
                props = {prop.lower() for prop in getattr(char, "properties", [])}
                if self.profile.no_response and "write-without-response" in props:
                    # These apps never set a write type, and Android starts
                    # dual-mode characteristics without response. Waiting for an
                    # acknowledgement stretches every refresh and makes motion stutter.
                    self._write_with_response = False
                elif "write" in props:
                    self._write_with_response = True
                elif "write-without-response" in props:
                    self._write_with_response = False
                self._write_mode_initialized = True
                return
        self._write_mode_initialized = True

    def _json_device_identifier(self) -> str:
        """Return the device identifier used by the JSON/A00A protocol."""
        for candidate in (
            getattr(self._coordinator, "name", None),
            getattr(self.client, "address", None),
            getattr(self._coordinator, "address", None),
        ):
            if candidate:
                return str(candidate)
        return "unknown"

    def _build_command(self, command_value: int) -> bytes:
        """Encode one key word in the profile's carrier, or a Left/Right side frame."""
        side = self.command_side
        if side == "left" or side == "right":
            return profiles.encode(self.profile, command_value, side=side)
        if self.profile.carrier == "json":
            return profiles.encode(self.profile, command_value, self._json_device_identifier())
        return profiles.encode(self.profile, command_value)

    def _step_frame(self, step: int | bytes) -> bytes:
        return step if isinstance(step, bytes) else self._build_command(step)

    @property
    def supports_single_address_pairing(self) -> bool:
        """Only profiles with an artifact-backed Left/Right selector."""
        return self.profile.single_side

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed."""
        selected_cancel_event = (
            cancel_event if cancel_event is not None else self._coordinator.cancel_command
        )
        if selected_cancel_event.is_set():
            return
        self._refresh_write_mode()
        await self._write_gatt_with_retry(
            self._char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=selected_cancel_event,
            response=self._write_with_response,
        )

    # Adjustable Lite status: a 500 ms 00 B0 poll answered by notifications.
    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        """Record which Adjustable Lite remote the device name selected."""
        if not self.profile.status_poll_ms:
            return {}
        return {"adjustable_lite_remote": "KSBT03C" if self.profile.status_timer else "KSBT01C"}

    @property
    def requires_notification_channel(self) -> bool:
        return self.profile.status_poll_ms is not None

    @property
    def diagnostic_poll_interval(self) -> float | None:
        poll_ms = self.profile.status_poll_ms
        return poll_ms / 1000 if poll_ms else None

    async def async_refresh_diagnostics(self) -> None:
        """Send one status query; the reply is a notification."""
        if self.profile.status_poll_ms:
            await self.write_command(codec.STATUS_QUERY, cancel_event=asyncio.Event())

    def invalidate_diagnostics(self) -> None:
        """Forget reported status when the BLE session ends."""
        if self.profile.status_poll_ms:
            self.forward_controller_state_updates(
                dict.fromkeys(
                    (
                        STATE_ADJUSTABLE_LITE_LIGHT,
                        STATE_ADJUSTABLE_LITE_MASSAGE_TIMER,
                        STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW,
                    )
                )
            )

    @property
    def controller_state_binary_sensor_specs(
        self,
    ) -> tuple[ControllerStateBinarySensorSpec, ...]:
        """The app's bulb icon, driven by notification byte 12."""
        if not self.profile.status_poll_ms:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key=STATE_ADJUSTABLE_LITE_LIGHT,
                translation_key=STATE_ADJUSTABLE_LITE_LIGHT,
                state_key=STATE_ADJUSTABLE_LITE_LIGHT,
                icon="mdi:lightbulb",
            ),
        )

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        if self.profile.status_poll_ms:
            return frozenset()
        return frozenset({STATE_ADJUSTABLE_LITE_LIGHT})

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        """The KSBT03C remote's 10/20/30 minute massage timer indicator."""
        if not self.profile.status_timer:
            return ()
        return (
            ControllerStateSensorSpec(
                key=STATE_ADJUSTABLE_LITE_MASSAGE_TIMER,
                translation_key=STATE_ADJUSTABLE_LITE_MASSAGE_TIMER,
                state_key=STATE_ADJUSTABLE_LITE_MASSAGE_TIMER,
                icon="mdi:timer-outline",
                native_unit_of_measurement="min",
                attribute_keys=(STATE_ADJUSTABLE_LITE_MASSAGE_TIMER_RAW,),
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        if self.profile.status_timer:
            return frozenset()
        return frozenset({STATE_ADJUSTABLE_LITE_MASSAGE_TIMER})

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start position (Ergomotion) or status (Adjustable Lite) notifications."""
        self._notify_callback = callback
        if not (self.profile.position_feedback or self.profile.status_poll_ms):
            return
        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start notifications: not connected")
            return
        try:
            await self.client.start_notify(self._notify_char_uuid, self._on_notification)
        except BleakError:
            # Adjustable Lite controls never wait for the subscription either.
            _LOGGER.warning("Failed to start notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle Ergomotion position and Adjustable Lite status notifications."""
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        if self.profile.status_poll_ms:
            state = parse_adjustable_lite_status(
                bytes(data), massage_timer=self.profile.status_timer
            )
            if state is not None:
                self.forward_controller_state_updates(state)
            return
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes) -> None:
        """Apply an Ergomotion ``ED``/``F0``/``F1`` status notification."""
        status = codec.parse_position_status(data)
        if status is None:
            _LOGGER.debug("Unknown notification format: %s", data.hex())
            return
        self._head_position = status.head_position
        self._foot_position = status.foot_position
        self._head_massage = status.head_massage
        self._foot_massage = status.foot_massage
        self._head_moving = status.head_moving
        self._foot_moving = status.foot_moving
        self._led_on = status.led_on
        self._timer_mode = status.timer_minutes
        if self._notify_callback is not None:
            # "back"/"legs" keys match the 2-motor sensors; values are percentages.
            self._notify_callback("back", float(status.head_position))
            self._notify_callback("legs", float(status.foot_position))

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        if not (self.profile.position_feedback or self.profile.status_poll_ms):
            return
        if self.client is None or not self.client.is_connected:
            return
        try:
            await self.client.stop_notify(self._notify_char_uuid)
        except BleakError:
            _LOGGER.debug("Failed to stop notifications")

    async def read_positions(self, motor_count: int = 2) -> None:
        """Ergomotion reports positions through notifications, not reads."""

    @property
    def head_position(self) -> int | None:
        return self._head_position

    @property
    def foot_position(self) -> int | None:
        return self._foot_position

    @property
    def head_moving(self) -> bool:
        return self._head_moving

    @property
    def foot_moving(self) -> bool:
        return self._foot_moving

    @property
    def head_massage_level(self) -> int:
        return self._head_massage

    @property
    def foot_massage_level(self) -> int:
        return self._foot_massage

    @property
    def led_on(self) -> bool:
        return self._led_on

    def _get_move_command(self) -> int:
        """Combine the held motors into one key word."""
        command = 0
        for motor, direction in self._motor_state.items():
            if direction is not None:
                command += _MOTOR_BITS[motor][0 if direction else 1]
        return command

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Return the profile's hold cadence while the stored cadence is the default.

        An explicitly customized cadence stays authoritative. BetterLiving-style
        Sino and OKIN screens use their three-motor cadence for three motors.
        """
        configured = (
            self._coordinator.motor_pulse_count,
            self._coordinator.motor_pulse_delay_ms,
        )
        if configured != BED_MOTOR_PULSE_DEFAULTS[BED_TYPE_KEESON]:
            return configured
        if self.profile.three_motor_hold and self._coordinator.motor_count == 3:
            return self.profile.three_motor_hold
        return self.profile.hold or configured

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        """Move a motor and always run the profile's release."""
        self._motor_state[motor] = direction
        command = self._get_move_command()
        repeat_count, repeat_delay_ms = self.motor_pulse_settings()
        completed = False
        try:
            if command:
                if self.profile.carrier == "json":
                    await self._write_json_motion_command(
                        command, repeat_count=repeat_count, repeat_delay_ms=repeat_delay_ms
                    )
                else:
                    await self.write_command(
                        self._build_command(command),
                        repeat_count=repeat_count,
                        repeat_delay_ms=repeat_delay_ms,
                    )
            completed = True
        finally:
            self._motor_state = {}
            # A touch-up release is immediate after a stop or an interrupted hold.
            guarded = self.profile.release.guarded
            await self._release_motion(delay=(completed and bool(command)) or not guarded)

    async def _release_motion(self, *, delay: bool = True) -> None:
        """Send the profile's release steps with a fresh event, so STOP cannot suppress them.

        An explicit stop (``delay`` False) skips the waits, or sends nothing when
        the release only polls status. Profiles with no steps stop by ending the
        cancellable refresh: the app has no release frame, and inventing one
        would be unsafe.
        """
        release = self.profile.release
        if not release.steps:
            return
        if release.guarded:
            await self._touch_up(delay=delay)
            return
        if not delay and not release.on_stop:
            return
        cancel_event = asyncio.Event()
        for wait_ms, step in release.steps:
            if delay and wait_ms:
                await asyncio.sleep(wait_ms / 1000)
            await self.write_command(self._step_frame(step), cancel_event=cancel_event)

    async def _touch_up(self, *, delay: bool) -> None:
        """Write the touch-up release frame after the app's wait.

        A STOP during the wait ends it early. The write runs on a fresh event in
        its own task, which is never cancelled and is awaited until it finishes,
        however often the caller is cancelled. The cancellation is re-raised
        afterwards, unless the write failed: that error wins.
        """
        ((wait_ms, step),) = self.profile.release.steps
        stop_requested = self._coordinator.cancel_command
        interrupted: asyncio.CancelledError | None = None
        if delay and not stop_requested.is_set():
            try:
                await _wait_unless_cancelled(stop_requested, wait_ms / 1000)
            except asyncio.CancelledError as err:
                interrupted = err
        release = asyncio.create_task(
            self.write_command(self._step_frame(step), cancel_event=asyncio.Event())
        )
        # asyncio.wait never cancels the task, so keep waiting for the write
        # through any number of cancellations of this caller.
        while not release.done():
            try:
                await asyncio.wait((release,))
            except asyncio.CancelledError:
                interrupted = interrupted or asyncio.CancelledError()
        if interrupted is not None:
            # Like an exception raised in a finally block, the write error wins.
            failure = None if release.cancelled() else release.exception()
            if failure is not None:
                raise failure from interrupted
            raise interrupted
        release.result()

    async def _write_single_shot(self, command: bytes) -> None:
        """Write a one-shot action once, then the profile's tap release if any."""
        completed = False
        try:
            await self.write_command(command)
            completed = True
        finally:
            release = self.profile.release
            if release.after_tap:
                await self._release_motion(delay=completed or not release.guarded)

    async def _write_held(self, command: bytes, repeat_count: int, repeat_delay_ms: int) -> None:
        """Refresh a held app control, then release it."""
        completed = False
        try:
            await self.write_command(
                command, repeat_count=repeat_count, repeat_delay_ms=repeat_delay_ms
            )
            completed = True
        finally:
            await self._release_motion(delay=completed)

    async def _write_json_motion_command(
        self, command_value: int, *, repeat_count: int, repeat_delay_ms: int
    ) -> None:
        """Send held-motion JSON commands compatible with all known Juna A00A remotes.

        Quest uses ``ctrm=0`` for held movement while Rewind/Restore/Relax use
        ``ctrm=1``. Sending both start forms keeps one controller compatible with
        the known Juna/Linx remote families without requiring an extra option.
        """
        device_id = self._json_device_identifier()
        for index in range(repeat_count):
            cancel_event = self._coordinator.cancel_command
            if cancel_event.is_set():
                return
            for ctrm in (1, 0):
                await self.write_command(
                    codec.json_command(command_value, device_id, ctrm=ctrm, km=3, keykt=1),
                    cancel_event=cancel_event,
                )
            if index < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    # Motor control methods
    async def move_head_up(self) -> None:
        await self._move_motor("head", True)

    async def move_head_down(self) -> None:
        await self._move_motor("head", False)

    async def move_head_stop(self) -> None:
        await self._move_motor("head", None)

    async def move_back_up(self) -> None:
        """Keeson's head motor moves the back."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Keeson's feet motor moves the legs."""
        await self._move_motor("feet", True)

    async def move_legs_down(self) -> None:
        await self._move_motor("feet", False)

    async def move_legs_stop(self) -> None:
        await self._move_motor("feet", None)

    async def move_feet_up(self) -> None:
        await self._move_motor("feet", True)

    async def move_feet_down(self) -> None:
        await self._move_motor("feet", False)

    async def move_feet_stop(self) -> None:
        await self._move_motor("feet", None)

    async def move_back_legs_up(self) -> None:
        """Restonic BT remote B back-up glyph: head and foot up together (0x05)."""
        await self._move_back_legs(True)

    async def move_back_legs_down(self) -> None:
        """Restonic BT remote B back-down glyph: head and foot down together (0x0A)."""
        await self._move_back_legs(False)

    async def move_back_legs_stop(self) -> None:
        """Release the combined Restonic BT remote B movement."""
        await self._move_back_legs(None)

    async def _move_back_legs(self, direction: bool | None) -> None:
        if "back_legs_up" not in self.profile.held_controls:
            raise NotImplementedError("Combined head and foot movement needs Restonic BT remote B")
        # The combined literal is exactly the head bit OR the foot bit.
        self._motor_state["feet"] = direction
        await self._move_motor("head", direction)

    async def stop_all(self) -> None:
        self._motor_state = {}
        await self._release_motion(delay=False)

    async def move_tilt_up(self) -> None:
        await self._move_motor("tilt", True)

    async def move_tilt_down(self) -> None:
        await self._move_motor("tilt", False)

    async def move_tilt_stop(self) -> None:
        await self._move_motor("tilt", None)

    async def move_lumbar_up(self) -> None:
        await self._move_motor("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_motor("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self._move_motor("lumbar", None)

    # Preset methods
    async def _preset(self, preset: profiles.Preset) -> None:
        word = self.profile.presets.get(preset)
        if word is None:
            _LOGGER.warning("%s preset is not available on %s beds", preset, self._variant)
            return
        await self._write_single_shot(self._build_command(word))

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        """Restonic BT remote A refreshes Zero G while held; others tap it once."""
        held = self.profile.held_controls.get("zero_g")
        if held is not None and held[1]:
            await self._write_held(self._build_command(held[0]), *self.motor_pulse_settings())
            return
        await self._preset("zero_g")

    async def preset_lounge(self) -> None:
        await self._preset("lounge")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a memory slot; words differ per profile (see ``profiles/keeson.py``)."""
        if not self.profile.memory:
            raise NotImplementedError("This Keeson app has no memory presets")
        word = self.profile.memory.get(memory_num)
        if word is None:
            _LOGGER.warning(
                "Memory %d not supported (valid: %s)", memory_num, sorted(self.profile.memory)
            )
            return
        await self._write_single_shot(self._build_command(word))

    async def program_memory(self, memory_num: int) -> None:
        """Program a memory slot as the profile's app does."""
        save = self.profile.memory_save
        word = save.words.get(memory_num) if save is not None else None
        if save is None or word is None:
            _LOGGER.warning("Programming memory %d is not supported on this bed", memory_num)
            return
        command = self._build_command(word)
        if not save.wait_first:
            await self.write_command(
                command, repeat_count=save.repeats, repeat_delay_ms=save.repeat_ms
            )
            return
        cancel_event = self._coordinator.cancel_command
        for _ in range(save.repeats):
            if cancel_event.is_set():
                return
            await asyncio.sleep(save.repeat_ms / 1000)
            await self.write_command(command, cancel_event=cancel_event)

    # Light methods
    def _require_lights(self) -> None:
        if self.profile.lights is None:
            raise NotImplementedError(f"Light control is not verified for {self.profile.key}")

    async def _write_light(self, on: bool) -> None:
        word = SinoCommands.LIGHT_ON if on else SinoCommands.LIGHT_OFF
        await self.write_command(self._build_command(word))
        self._led_on = on

    async def lights_on(self) -> None:
        self._require_lights()
        if self.profile.lights == "discrete":
            await self._write_light(True)
        else:
            await self.lights_toggle()

    async def lights_off(self) -> None:
        self._require_lights()
        if self.profile.lights == "discrete":
            await self._write_light(False)
        else:
            await self.lights_toggle()

    async def lights_toggle(self) -> None:
        """Toggle the lights; discrete-light profiles emulate it with tracked state."""
        self._require_lights()
        if self.profile.lights == "discrete":
            await self._write_light(not self._led_on)
        else:
            await self._write_single_shot(self._build_command(KeesonCommands.TOGGLE_SAFETY_LIGHTS))

    # Restonic BT app controls
    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        """Remote B's ZZZ button, labelled as the app labels it."""
        if "zzz" not in self.profile.held_controls:
            return ()
        return (
            ControllerButtonSpec(
                key=RESTONIC_ZZZ_BUTTON_KEY,
                name="ZZZ",
                translation_key=RESTONIC_ZZZ_BUTTON_KEY,
                press_fn=lambda ctrl: cast(KeesonController, ctrl).restonic_zzz(),
                icon="mdi:sleep",
            ),
        )

    async def restonic_zzz(self) -> None:
        """Tap remote B's ZZZ button (0x8000); its physical effect is unproven."""
        control = self.profile.held_controls.get("zzz")
        if control is None:
            raise NotImplementedError("Only Restonic BT remote B has the ZZZ button")
        await self._write_single_shot(self._build_command(control[0]))

    @property
    def held_control_options(self) -> tuple[str, ...]:
        """Every control on the selected Restonic BT remote can be held."""
        return tuple(self.profile.held_controls)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Hold one app control, then release it as the app's touch-up does.

        Repeating controls write at once and at the hold interval while held;
        one-shot controls write once on touch-down.
        """
        try:
            value, repeats = self.profile.held_controls[control]
        except KeyError as err:
            raise ValueError(f"Unsupported Restonic BT control: {control}") from err
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= 60000:
            raise ValueError("Hold duration must be 100..60000 milliseconds")
        cancel_event = self._coordinator.cancel_command
        if cancel_event.is_set():
            return
        interval_ms = self.profile.hold[1] if self.profile.hold else 100
        writes = -(-duration_ms // interval_ms) if repeats else 1
        completed = False
        try:
            await self.write_command(
                self._build_command(value),
                repeat_count=writes,
                repeat_delay_ms=interval_ms,
                cancel_event=cancel_event,
            )
            await _wait_unless_cancelled(
                cancel_event, (duration_ms - (writes - 1) * interval_ms) / 1000
            )
            completed = True
        finally:
            await self._release_motion(delay=completed)

    # Massage: Keeson step keys, or Sino's absolute levels tracked here.
    async def _sino_levels(self, *, head: int | None = None, foot: int | None = None) -> None:
        """Track, then write, absolute zone levels."""
        if head is not None:
            self._head_massage = head
        if foot is not None:
            self._foot_massage = foot
        await self._write_sino_levels(head, foot)

    async def _write_sino_levels(self, head: int | None, foot: int | None) -> None:
        if head is not None:
            await self.write_command(
                self._build_command(SinoCommands.MASSAGE_HEAD_INTENSITY_BASE + head)
            )
        if foot is not None:
            await self.write_command(
                self._build_command(SinoCommands.MASSAGE_FOOT_INTENSITY_BASE + foot)
            )

    async def _step(self, word: int) -> None:
        await self._write_single_shot(self._build_command(word))

    @property
    def _absolute_massage(self) -> bool:
        return self.profile.massage == "absolute"

    async def massage_toggle(self) -> None:
        if not self._absolute_massage:
            await self._step(KeesonCommands.MASSAGE_STEP)
        elif self._head_massage > 0 or self._foot_massage > 0:
            await self.massage_off()
        else:
            await self._sino_levels(head=1, foot=1)

    async def massage_off(self) -> None:
        if self._absolute_massage:
            # Dynasty-family apps stop massage by setting both zones to zero.
            await self._write_sino_levels(0, 0)
            self._head_massage = self._foot_massage = 0
        elif self.profile.massage_off is not None:
            await self._step(self.profile.massage_off)
        else:
            await super().massage_off()

    async def massage_head_up(self) -> None:
        if self._absolute_massage:
            await self._sino_levels(head=min(10, self._head_massage + 1))
        else:
            await self._step(KeesonCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        if self._absolute_massage:
            await self._sino_levels(head=max(0, self._head_massage - 1))
        else:
            await self._step(KeesonCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        if self._absolute_massage:
            await self._sino_levels(foot=min(10, self._foot_massage + 1))
        else:
            await self._step(KeesonCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        if self._absolute_massage:
            await self._sino_levels(foot=max(0, self._foot_massage - 1))
        else:
            await self._step(KeesonCommands.MASSAGE_FOOT_DOWN)

    async def massage_intensity_up(self) -> None:
        if self._absolute_massage:
            await self._sino_levels(
                head=min(10, self._head_massage + 1), foot=min(10, self._foot_massage + 1)
            )
        else:
            await self._step(KeesonCommands.MASSAGE_HEAD_UP)
            await self._step(KeesonCommands.MASSAGE_FOOT_UP)

    async def massage_intensity_down(self) -> None:
        if self._absolute_massage:
            await self._sino_levels(
                head=max(0, self._head_massage - 1), foot=max(0, self._foot_massage - 1)
            )
        else:
            await self._step(KeesonCommands.MASSAGE_HEAD_DOWN)
            await self._step(KeesonCommands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """Step the Keeson massage timer, or Sino's wave pattern 1..10."""
        if self._absolute_massage:
            self._wave_massage = (self._wave_massage % 10) + 1
            await self.write_command(
                self._build_command(SinoCommands.MASSAGE_HEAD_WAVE_BASE + self._wave_massage)
            )
        else:
            await self._step(KeesonCommands.MASSAGE_TIMER_STEP)

    async def massage_wave_next(self) -> None:
        """Select the next BaseI4/I5 massage wave pattern."""
        if not self.supports_massage_wave_direction_control:
            raise NotImplementedError("Massage wave direction is only verified for base variant")
        await self._step(KeesonCommands.MASSAGE_WAVE_STEP)

    async def massage_wave_previous(self) -> None:
        """Select the previous BaseI4/I5 massage wave pattern."""
        if not self.supports_massage_wave_direction_control:
            raise NotImplementedError("Massage wave direction is only verified for base variant")
        await self._step(KeesonCommands.MASSAGE_WAVE_PREVIOUS)

    async def set_massage_intensity_preset(self, level: int) -> None:
        """Select a hardware-confirmed BaseI4/I5 massage intensity."""
        if not self.supports_massage_intensity_preset_control:
            raise NotImplementedError("Massage intensity presets are only verified for base variant")
        commands = {
            1: KeesonCommands.MASSAGE_INTENSITY_1,
            2: KeesonCommands.MASSAGE_INTENSITY_2,
            3: KeesonCommands.MASSAGE_INTENSITY_3,
        }
        try:
            command = commands[level]
        except KeyError as err:
            raise ValueError(f"Unsupported massage intensity preset: {level}") from err
        await self._step(command)

    async def massage_head_toggle(self) -> None:
        """Toggle the head zone (Sino) or step its intensity, wrapping to off."""
        if self._absolute_massage:
            await self._sino_levels(head=0 if self._head_massage > 0 else 1)
        else:
            await self._step(KeesonCommands.MASSAGE_HEAD_UP)

    async def massage_foot_toggle(self) -> None:
        """Toggle the foot zone (Sino) or step its intensity, wrapping to off."""
        if self._absolute_massage:
            await self._sino_levels(foot=0 if self._foot_massage > 0 else 1)
        else:
            await self._step(KeesonCommands.MASSAGE_FOOT_UP)

    async def sound_toggle(self) -> None:
        """Raise until KSBT04C sound control is verified from captured traffic."""
        raise NotImplementedError("KSBT04C sound control is not yet verified")

    async def light_and_sound_toggle(self) -> None:
        """Raise until KSBT04C light+sound control is verified from traffic."""
        raise NotImplementedError("KSBT04C light+sound control is not yet verified")

    async def therapy_mode_one(self) -> None:
        """Raise until KSBT04C therapy mode packets are captured."""
        raise NotImplementedError("KSBT04C therapy mode control is not yet verified")

    async def therapy_mode_two(self) -> None:
        """Raise until KSBT04C therapy mode packets are captured."""
        raise NotImplementedError("KSBT04C therapy mode control is not yet verified")

    async def therapy_mode_three(self) -> None:
        """Raise until KSBT04C therapy mode packets are captured."""
        raise NotImplementedError("KSBT04C therapy mode control is not yet verified")

    def get_massage_state(self) -> dict[str, Any]:
        """Return massage state from Ergomotion notifications or Sino tracking."""
        return {
            "head_intensity": self._head_massage,
            "foot_intensity": self._foot_massage,
            "wave_intensity": self._wave_massage,
            "timer_mode": self._timer_mode,
            "led_on": self._led_on,
        }
