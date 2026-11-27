"""Explicit OKIN Bedding app profiles over the CST transport."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from functools import partial
from types import SimpleNamespace
from typing import TYPE_CHECKING, Final, Protocol, cast

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability
from ...codec import okin_nframe as codec
from ...const import (
    CONF_BLE_BOND_ESTABLISHED,
    CONF_ZSERIES_ALARM_AVAILABLE,
    ZSERIES_PULSE_COUNT_RANGE,
    ZSERIES_VARIANTS,
)
from ...controller_state import StateKey
from ...errors import BedCommandTimedOutError
from ...profiles.okin_nframe import (
    BEDDING_HOLD,
    BEDDING_PROFILES,
    BEDDING_SAVE_HOLD_MS,
    CST_REFRESH_MS,
    RESTFUL_ACTIONS,
    RIZE_REMEDY_II_ACTIONS,
    SERENITY_ACTIONS,
    SERENITY_SAVE_CODES,
    TRANQUIL_ACTIONS,
    ZSERIES_Z230_ACTIONS,
    ZSERIES_Z280_ACTIONS,
    OkinNFrameProfile,
)
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from ..okin_cst import OkinCstController, _product

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator


class _BeddingWriter(Protocol):
    async def __call__(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None: ...


_LOGGER = logging.getLogger(__name__)

_SERVICE = "62741523-52f9-8864-b1ab-3b3a8d65950b"
_NOTIFY = "62741625-52f9-8864-b1ab-3b3a8d65950b"
_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"
# Two STOPs, 100 and 200 ms after an action ends.
_RELEASE_OFFSETS_S: Final = tuple(
    (BEDDING_HOLD.release_after_ms + index * BEDDING_HOLD.release_ms) / 1000
    for index in range(BEDDING_HOLD.releases)
)

# saveMemory(n) records these local codes; callMemory(n) clears them.
_RECALLS: Final = frozenset(
    {"flat", "anti_snore", "leisure", "lounge", "incline", "memory_1", "zero_g", "tv", "memory_2"}
)

# Alarm frames, Customatic Z-Series only (exact CST13/CST14 manufacturer).
_ALARM_MANUFACTURERS: Final = frozenset({"CST13", "CST14"})
_ALARM_WAKE: Final = {"massage": (9, 1), "memory_1": (17, 2)}  # UI type, wire code
_ALARM_QUERY: Final = b"\x00\xc0"
_ALARM_SELECTION: Final = 1  # Persisted bedSelection default; the app never sets it.


def alarm_frame(*, enabled: bool, hour: int, minute: int, repeat: int, wake: str) -> bytes:
    """Build the app's nine-byte alarm set/off frame."""
    if not enabled:
        return codec.alarm((0, 0, 0, 0, 0, 0, _ALARM_SELECTION))
    if wake not in _ALARM_WAKE:
        raise ValueError("Wake mode must be massage or memory_1")
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and repeat in (1, 2, 4, 8, 16, 32, 64)):
        raise ValueError("Alarm time or repeat day is out of range")
    # Enable is zero only when all four caller fields are zero; wake is never zero here.
    return codec.alarm((repeat, _ALARM_WAKE[wake][1], hour, minute, 0, 1, _ALARM_SELECTION))


def alarm_repeat_bit(now: datetime, hour: int, minute: int) -> int:
    """Return today's Sunday-zero weekday bit, or tomorrow's when the time has passed."""
    bit = 1 << ((now.weekday() + 1) % 7)
    if hour < now.hour or (hour == now.hour and minute < now.minute):
        bit *= 2
        if bit > 64:
            bit = 1
    return bit


def clock_frame(now: datetime) -> bytes:
    """Build the app's binary local-clock frame (DecimaltoBcd is the identity)."""
    return codec.record(
        0x06,
        (
            (now.year - 2000) & 0xFF,
            now.month,
            now.day,
            (now.weekday() + 1) % 7,
            now.hour,
            now.minute,
            now.second,
        ),
    )


@dataclass(frozen=True)
class OkinBeddingApp:
    """One app's literal action table and HA exposure."""

    prefix: str
    label: str
    actions: Mapping[str, tuple[int, int]]
    save_codes: Mapping[str, int]
    buttons: tuple[tuple[str, str], ...]
    profile: OkinNFrameProfile
    information_uuid: str = _MANUFACTURER
    exact_duration: bool = False
    information_log_only: bool = False
    settle_writes: bool = False


_ZSERIES_BUTTONS_TAIL = (
    ("save_zero_g", "Save zero gravity"),
    ("save_tv", "Save TV"),
    ("light_toggle", "Toggle light"),
    ("massage_timer_cycle", "Cycle massage timer"),
)

APPS: Final[dict[str, OkinBeddingApp]] = {
    "restful": OkinBeddingApp(
        prefix="restful",
        label="Restful",
        actions=RESTFUL_ACTIONS,
        save_codes={},  # No status byte identifies a save or proves persistence.
        buttons=(
            ("save_zero_g", "Save zero gravity"),
            ("save_tv", "Save TV"),
            ("light_toggle", "Toggle light"),
            ("massage_timer_cycle", "Cycle massage timer"),
            ("wave_1", "Wave 1"),
            ("wave_2", "Wave 2"),
            ("wave_3", "Wave 3"),
        ),
        profile=BEDDING_PROFILES["restful"],
        exact_duration=True,
        information_log_only=True,
    ),
    "rize_remedy_ii": OkinBeddingApp(
        prefix="rize_remedy_ii",
        label="Rize Remedy II",
        actions=RIZE_REMEDY_II_ACTIONS,
        save_codes={"save_zero_g": 5, "save_incline": 6, "save_lounge": 3},
        buttons=(("wave_1", "Wave 1"), ("wave_2", "Wave 2"), ("wave_3", "Wave 3")),
        profile=BEDDING_PROFILES["rize_remedy_ii"],
        information_uuid="00002a24-0000-1000-8000-00805f9b34fb",
        exact_duration=True,
        information_log_only=True,
    ),
    "serenity": OkinBeddingApp(
        prefix="serenity",
        label="Serenity",
        actions=SERENITY_ACTIONS,
        save_codes=SERENITY_SAVE_CODES,
        buttons=(
            ("refresh_manufacturer", "Refresh manufacturer"),
            ("selector_4_up", "Control 4 up"),
            ("selector_4_down", "Control 4 down"),
            ("selector_5_up", "Control 5 up"),
            ("selector_5_down", "Control 5 down"),
            ("save_zero_g", "Save zero gravity"),
            ("save_tv", "Save TV"),
            ("light_toggle", "Toggle light"),
            ("massage_head_cycle", "Cycle head massage"),
            ("massage_foot_cycle", "Cycle foot massage"),
            ("massage_timer_cycle", "Cycle massage timer"),
            ("wave_1", "Wave 1"),
            ("wave_2", "Wave 2"),
            ("wave_3", "Wave 3"),
        ),
        profile=BEDDING_PROFILES["serenity"],
    ),
    "tranquil": OkinBeddingApp(
        prefix="tranquil",
        label="Tranquil",
        actions=TRANQUIL_ACTIONS,
        save_codes={"save_zero_g": 5, "save_lounge": 3, "save_memory_1": 4, "save_memory_2": 8},
        buttons=(
            ("refresh_manufacturer", "Refresh manufacturer"),
            ("selector_4_up", "Control 4 up"),
            ("selector_4_down", "Control 4 down"),
            ("selector_5_up", "Control 5 up"),
            ("selector_5_down", "Control 5 down"),
            ("save_zero_g", "Save zero gravity"),
            ("save_lounge", "Save lounge"),
            ("light_toggle", "Toggle light"),
            ("massage_head_cycle", "Cycle head massage"),
            ("massage_foot_cycle", "Cycle foot massage"),
            ("massage_timer_cycle", "Cycle massage timer"),
            ("wave_1", "Wave 1"),
            ("wave_2", "Wave 2"),
            ("wave_3", "Wave 3"),
        ),
        profile=BEDDING_PROFILES["tranquil"],
    ),
    "zseries_z230": OkinBeddingApp(
        prefix="zseries",
        label="Z-230",
        actions=ZSERIES_Z230_ACTIONS,
        save_codes={"save_zero_g": 5, "save_memory_1": 4, "save_tv": 6},
        buttons=(
            ("refresh_manufacturer", "Refresh manufacturer"),
            ("head_foot_up", "Head and foot up"),
            ("head_foot_down", "Head and foot down"),
            *_ZSERIES_BUTTONS_TAIL,
            ("massage_intensity_cycle", "Cycle massage intensity"),
        ),
        profile=BEDDING_PROFILES["zseries_z230"],
    ),
    "zseries_z280": OkinBeddingApp(
        prefix="zseries",
        label="Z-280",
        actions=ZSERIES_Z280_ACTIONS,
        save_codes={"save_zero_g": 5, "save_memory_1": 4, "save_tv": 6, "save_memory_2": 8},
        buttons=(
            ("refresh_manufacturer", "Refresh manufacturer"),
            ("selector_5_up", "Control 5 up"),
            ("selector_5_down", "Control 5 down"),
            *_ZSERIES_BUTTONS_TAIL,
            ("massage_head_cycle", "Cycle head massage"),
            ("massage_foot_cycle", "Cycle foot massage"),
        ),
        profile=BEDDING_PROFILES["zseries_z280"],
    ),
}


def _callback(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        if not isinstance(controller, OkinBeddingAppController):
            raise TypeError("This action requires an OKIN Bedding app profile")
        await controller.execute_app_control(action)

    return invoke


class OkinBeddingAppController(OkinCstController):
    """Reuse the proven CST frame without inheriting another app's capabilities."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, app: str | OkinBeddingApp) -> None:
        super().__init__(coordinator)
        self._app = APPS[app] if isinstance(app, str) else app
        self._nframe_profile = self._app.profile
        self._profile = _product(self._nframe_profile)
        self._has_explicit_profile = True
        self._status_code = 0
        self._timer_code = 0
        self._save_code = 0
        self._alarm_type = 0
        self._state: dict[str, object] = {}

    def _key(self, name: str) -> str:
        return f"{self._app.prefix}_{name}"

    def _state_key(self, name: str) -> StateKey[object]:
        return StateKey[object](self._key(name))

    @property
    def light_state_is_assumed(self) -> bool:
        # The app sends light on/off but reads no light state back.
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self._app.actions

    @property
    def supports_discrete_light_control(self) -> bool:
        return "light_on" in self._app.actions

    @property
    def supports_massage_off_control(self) -> bool:
        return "massage_off" in self._app.actions

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return "wave_1" in self._app.actions

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Every release is global, so another axis STOP must preempt this one.
        return tuple(replace(spec, scheduler_resource="*") for spec in super().motor_control_specs)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, CST_REFRESH_MS

    def _hold_ms(self, action: str) -> int:
        """Default hold for a non-service action (voice deadlines and save help)."""
        if action in self._app.save_codes:
            return BEDDING_SAVE_HOLD_MS
        # The reachable voice path stops flat after 1500 ms and the rest after 500 ms.
        return 1500 if action == "flat" else 500

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        diagnostics = {**super().protocol_diagnostics, **self._state}
        if self._app.save_codes:
            diagnostics["save_pending_code"] = self._save_code
        return diagnostics

    def _publish(self, updates: dict[str, object]) -> None:
        """Publish fields named without the app prefix."""
        values = [self._state_key(name)(value) for name, value in updates.items()]
        self._state.update((update.key, update.value) for update in values)
        self.forward_controller_state_updates(*values)

    def _write_role(self) -> tuple[BleakGATTCharacteristic, bool]:
        client = self.client
        label = self._app.label
        if client is None or not client.is_connected:
            raise ConnectionError(f"{label} is not connected")
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == _SERVICE
            for char in service.characteristics
            if char.uuid.lower() == self.control_characteristic_uuid
        ]
        if len(matches) != 1:
            raise ValueError(f"{label} requires its exact writable GATT role")
        # Artifact write type is inherited/unknown; this is HA's property policy.
        if "write" in matches[0].properties:
            return matches[0], True
        if "write-without-response" in matches[0].properties:
            return matches[0], False
        raise ValueError(f"{label} command characteristic is not writable")

    def _write_response(self) -> bool:
        return self._write_role()[1]

    def _notification_role(self, client: BleakClient) -> BleakGATTCharacteristic:
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == _SERVICE
            for char in service.characteristics
            if char.uuid.lower() == _NOTIFY and "notify" in char.properties
        ]
        if len(matches) != 1:
            raise ValueError(f"{self._app.label} requires its notification characteristic")
        return matches[0]

    def require_roles(self) -> None:
        """Raise unless the link has the app's exact command and notification roles."""
        self._write_role()
        client = self.client
        if client is None:
            raise ConnectionError(f"{self._app.label} is not connected")
        self._notification_role(client)

    async def async_discover_capabilities(self) -> None:
        self.require_roles()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_response(),
            wall_clock_pacing=True,
            on_write=on_write,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        await self.async_discover_capabilities()
        client = self.client
        if client is None:
            return
        self._notify_callback = callback
        async with self._ble_lock:
            await client.start_notify(_NOTIFY, self._handle_notification)
        await asyncio.sleep(1)
        await self.refresh_manufacturer()

    async def refresh_manufacturer(self, *, exact_role: bool = False) -> None:
        """Repeat the reachable on-resume read without selecting capabilities."""
        client = self.client
        if client is None or not client.is_connected:
            return
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == "0000180a-0000-1000-8000-00805f9b34fb"
            for char in service.characteristics
            if char.uuid.lower() == self._app.information_uuid and "read" in char.properties
        ]
        if len(matches) != 1:
            return
        try:
            async with asyncio.timeout(2):
                async with self._ble_lock:
                    if exact_role and (client is not self.client or not client.is_connected):
                        return
                    value = await client.read_gatt_char(
                        matches[0] if exact_role else self._app.information_uuid
                    )
            manufacturer = bytes(value).decode("utf-8", errors="replace")
        except BleakError, OSError, TimeoutError:
            return  # Missing diagnostic information does not block control.
        if self._app.information_log_only:
            _LOGGER.debug("%s device information: %s", self._app.label, bytes(value).hex())
            return
        self._manufacturer_read(manufacturer)
        self._publish({"manufacturer": manufacturer})

    def _manufacturer_read(self, manufacturer: str) -> None:
        """Hook for apps whose manufacturer string gates a page."""

    def _handle_notification(self, _: object, data: bytearray) -> None:
        self.forward_raw_notification(_NOTIFY, bytes(data))
        if len(data) <= 10:
            return

        def signed(value: int) -> int:
            return value if value < 128 else value - 256

        if data[1] == 12:
            self._alarm_type = {1: 9, 2: 17, 3: 18, 4: 16, 5: 20, 6: 19, 7: 18, 8: 9, 9: 21}.get(
                data[5], self._alarm_type
            )
            self._publish(
                {
                    "alarm_type": self._alarm_type,
                    "alarm_repeat": signed(data[4]),
                    "alarm_hour": signed(data[6]),
                    "alarm_minute": signed(data[7]),
                    "alarm_on": data[9] == 1,
                }
            )
            return
        self._handle_status(data[10])

    def _handle_status(self, value: int) -> None:
        code = value if value < 128 else value - 256
        if code == self._status_code:
            return
        self._status_code = code
        updates: dict[str, object] = {"status_code": code}
        # HA supplies the active callback equivalent. The source treats any
        # status change during save as a local success, not a hardware ACK.
        if self._save_code:
            updates["save_event_code"] = self._save_code
            self._save_code = 0
        elif code != self._timer_code:
            self._timer_code = code
            updates.update(
                {
                    "massage_timer_code": code,
                    "massage_timer_minutes": {1: 10, 2: 20, 3: 30}.get(code),
                }
            )
        self._publish(updates)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        # Raw status, timer and save codes stay in published state for diagnostics.
        return (
            ControllerStateSensorSpec(
                key=self._key("manufacturer"),
                # The apps share one parser, so their sensors share names.
                translation_key="okin_bedding_app_manufacturer",
                state_key=self._state_key("manufacturer"),
                icon="mdi:information-outline",
            ),
            self._timer_sensor_spec(),
            ControllerStateSensorSpec(
                key=self._key("alarm_type"),
                translation_key="okin_bedding_app_alarm_type",
                state_key=self._state_key("alarm_type"),
                icon="mdi:alarm",
                attribute_keys=tuple(
                    self._state_key(name)
                    for name in ("alarm_repeat", "alarm_hour", "alarm_minute", "alarm_on")
                ),
                entity_category=None,
            ),
        )

    def _timer_sensor_spec(self) -> ControllerStateSensorSpec:
        timer = "massage_timer_minutes"
        return massage_timer_sensor_spec(
            self._key(timer), f"okin_bedding_app_{timer}", self._state_key(timer)
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._app.actions)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unknown {self._app.label} action")
        await self._hold_control(control, duration_ms)

    def _press_writer(self) -> _BeddingWriter:
        return self.write_command

    async def _hold_control(self, control: str, duration_ms: int) -> None:
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Duration must be a positive integer, at most 60000 ms")
        primary, secondary = self._app.actions[control]
        refresh_ms = self.profile.hold.repeat_ms or CST_REFRESH_MS
        write = self._press_writer()
        # The app records local save intent before writing, not a storage ACK.
        if control in self._app.save_codes:
            self._save_code = self._app.save_codes[control]
        elif control in _RECALLS:
            self._save_code = 0
        deadline = asyncio.timeout(duration_ms / 1000)
        controller_timeout = False
        press_written = False
        press_timed_out = False

        def mark_pressed() -> None:
            nonlocal press_written
            press_written = True

        requires_press = self._app.prefix == "restful"
        press = partial(write, on_write=mark_pressed) if requires_press else write
        try:
            try:
                async with deadline:
                    try:
                        await press(
                            codec.frame96(primary, secondary),
                            repeat_count=(duration_ms + refresh_ms - 1) // refresh_ms
                            if self._app.exact_duration
                            else self.timed_move_repeat_count(duration_ms, refresh_ms),
                            repeat_delay_ms=refresh_ms,
                        )
                    except TimeoutError:
                        controller_timeout = True
                        raise
                    if self._app.exact_duration:
                        # Keep the final press until release/deadline, and
                        # let cancellation end it immediately.
                        await self._coordinator.cancel_command.wait()
            except TimeoutError:
                if controller_timeout or not deadline.expired():
                    raise
                press_timed_out = requires_press and not press_written
        finally:
            try:
                await self._release_after_press(write)
            except Exception as err:
                if press_timed_out:
                    raise BedCommandTimedOutError from err
                raise
        if press_timed_out:
            raise BedCommandTimedOutError

    async def _release_after_press(self, write: _BeddingWriter) -> None:
        await self._send_stop_sequence(write)

    async def _send_stop_sequence(self, write: _BeddingWriter | None = None) -> None:
        if write is None:
            write = self._press_writer()

        async def release() -> None:
            event = asyncio.Event()
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for offset in _RELEASE_OFFSETS_S:
                await asyncio.sleep(max(0, started + offset - loop.time()))
                try:
                    await write(codec.frame96(0), cancel_event=event)
                except Exception as error:
                    # The source schedules both releases independently.
                    failure = failure or error
            if failure is not None:
                raise failure

        await settled(release())

    async def _send_repeated_command(
        self,
        *,
        motor_value: int = 0,
        control_value: int = 0,
        repeat_count: int,
        repeat_delay_ms: int,
    ) -> None:
        action = next(
            (
                key
                for key, fields in self._app.actions.items()
                if fields == (motor_value, control_value)
            ),
            None,
        )
        if action is None:
            raise ValueError(f"Command is not reachable in the {self._app.label} app")
        # Inherited callers supply counts; this app defines its own deadline.
        await self.hold_control(action, self._hold_ms(action))

    async def preset_flat(self) -> None:
        await self.hold_control("flat", self._hold_ms("flat"))

    async def preset_tv(self) -> None:
        await self.hold_control("tv", self._hold_ms("tv"))

    def _memory_action(self, memory_num: int, prefix: str = "") -> str:
        slots = len(self._profile.memory_slots)
        if isinstance(memory_num, bool) or memory_num not in range(1, slots + 1):
            names = " and ".join(f"M{slot}" for slot in range(1, slots + 1))
            raise ValueError(f"{self._app.label} has only {names}")
        return f"{prefix}memory_{memory_num}"

    async def program_memory(self, memory_num: int) -> None:
        action = self._memory_action(memory_num, "save_")
        await self.hold_control(action, self._hold_ms(action))

    async def preset_memory(self, memory_num: int) -> None:
        action = self._memory_action(memory_num)
        await self.hold_control(action, self._hold_ms(action))

    async def massage_mode_step(self) -> None:
        await self.hold_control("massage_mode_cycle", self._hold_ms("massage_mode_cycle"))

    @property
    def _shared_light_toggle(self) -> bool:
        """Whether the shared Toggle Light button exists (no light or switch replaces it)."""
        return self.supports_light_toggle_control and not (
            self.supports_discrete_light_control
            or self.supports_light_color_control
            or self.supports_light_state_feedback
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            spec
            for action, name in self._app.buttons
            # The shared light toggle, where the bed has one, sends the same light frame.
            if not (action == "light_toggle" and self._shared_light_toggle)
            if (
                spec := catalog_button(
                    self._key(action),
                    name,
                    _callback(action),
                    kind=Kind.SAVE
                    if action.startswith("save_")
                    else Kind.MOTOR
                    if action.startswith("selector_")
                    else None,
                    diagnostic=action == "refresh_manufacturer",
                )
            )
            is not None
        )

    async def execute_app_control(self, action: str) -> None:
        if action == "refresh_manufacturer":
            await self.refresh_manufacturer()
            return
        await self.hold_control(action, self._hold_ms(action))


class SerenityController(OkinBeddingAppController):
    """Jordan's Serenity 1.0.1 (S01)."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app="serenity")


class TranquilController(OkinBeddingAppController):
    """Jordan's Tranquil 1.0.2: Serenity's core with a Lounge page and no TV."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app="tranquil")


class SessionBeddingAppController(OkinBeddingAppController):
    """Bedding holds, cleanup and notification callbacks on one BLE session."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, app: str | OkinBeddingApp) -> None:
        super().__init__(coordinator, app=app)
        self._connection_generation = 0
        self._subscription: tuple[BleakClient, BleakGATTCharacteristic] | None = None

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                timed_move_fn=lambda ctrl, up, ms, axis="foot" if spec.key == "feet" else spec.key:
                    ctrl.hold_control(f"{axis}_{'up' if up else 'down'}", ms),
            )
            for spec in super().motor_control_specs
        )

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        if command_value is None:
            await self._send_explicit_stop_sequence()
            return
        action = next(key for key, fields in self._app.actions.items() if fields == (command_value, 0))
        pulses, interval = self.motor_pulse_settings()
        await self.hold_control(action, self.leased_hold_ms(min(max(pulses * interval, interval), 60_000)))

    async def stop_all(self) -> None:
        await self._send_explicit_stop_sequence()

    async def _release_after_press(self, write: _BeddingWriter) -> None:
        await super()._release_after_press(write)
        if self._coordinator.cancel_command.is_set():
            self._cleanup_stop_cancel_counter = self._coordinator.cancel_counter

    def _press_writer(self) -> _BeddingWriter:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError(f"{self._app.label} is not connected")
        characteristic, response = self._write_role()
        return partial(
            self._write_on_connection, client, self._connection_generation, self._coordinator.cancel_counter, characteristic, response
        )

    async def _write_on_connection(
        self,
        client: BleakClient,
        generation: int,
        cancel_counter: int,
        characteristic: BleakGATTCharacteristic,
        response: bool,
        /,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        def check_generation() -> None:
            if self._app.settle_writes and cancel_event is None and cancel_counter != self._coordinator.cancel_counter:
                raise asyncio.CancelledError
            if generation != self._connection_generation:
                raise ConnectionError(f"{self._app.label} command belongs to a previous BLE connection")

        # The press already has a deadline. Each of the two neutral attempts
        # also has a limit, including time spent waiting for the BLE lock.
        async with asyncio.timeout(1 if cancel_event is not None else None):
            await self._write_gatt_with_retry(
                self.control_characteristic_uuid,
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
                cancel_event=cancel_event,
                response=response,
                wall_clock_pacing=True,
                characteristic=characteristic,
                expected_client=client,
                before_write=check_generation,
                on_write=on_write, settle_write=self._app.settle_writes,
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._write_role()
        client = self.client
        if client is None:
            return
        characteristic = self._notification_role(client)
        subscription = (client, characteristic)
        generation = self._connection_generation

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._subscription is subscription
                and client is self.client
                and client.is_connected
                and sender.handle == characteristic.handle
            ):
                self._handle_notification(sender, data)

        try:
            async with self._ble_lock:
                if (
                    generation != self._connection_generation
                    or client is not self.client
                    or not client.is_connected
                ):
                    return
                if self._subscription is not None and self._subscription[0] is client:
                    return
                self._subscription = subscription
                await client.start_notify(characteristic, receive)
        except BaseException:
            if self._subscription is subscription:
                self._subscription = None
            raise
        await asyncio.sleep(1)
        if (
            self._subscription is subscription
            and generation == self._connection_generation
            and client is self.client
        ):
            await self.refresh_manufacturer(exact_role=True)
            await self._after_information_read(generation, client)

    async def stop_notify(self) -> None:
        subscription = self._subscription
        if subscription is None:
            return
        client, characteristic = subscription
        try:
            async with self._ble_lock:
                if self._subscription is not subscription:
                    return
                self._subscription = None
                if client is self.client and client.is_connected:
                    await client.stop_notify(characteristic)
        except BleakError as error:
            _LOGGER.debug("Could not stop Restful notifications: %s", error)

    async def _after_information_read(self, generation: int, client: BleakClient) -> None:
        """App startup after its optional diagnostic read."""

    def on_disconnect(self) -> None:
        self._connection_generation += 1
        self._subscription = None
        super().on_disconnect()


class RestfulController(SessionBeddingAppController):
    """Jordan's Restful 1.0.2, with one shared tilt/lumbar control."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app="restful")
        self._saving = False

    @property
    def supports_massage_intensity_up_control(self) -> bool:
        return True

    async def massage_intensity_down(self) -> None:
        raise NotImplementedError("Restful only supports increasing massage intensity")

    @property
    def held_control_options(self) -> tuple[str, ...]:
        # Use the explicit save buttons or program_memory to change a preset.
        return tuple(action for action in self._app.actions if not action.startswith("save_"))

    @property
    def replaced_standard_button_keys(self) -> frozenset[str]:
        return frozenset({"program_memory_1", "program_memory_2"})

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *super().controller_button_specs,
            save_button(
                "program_memory_1", "Save M1", lambda ctrl: ctrl.program_memory(1),
                requires_confirmation=True,
            ),
            save_button(
                "program_memory_2", "Save M2", lambda ctrl: ctrl.program_memory(2),
                requires_confirmation=True,
            ),
        )

    async def _save_preset(self, action: str) -> None:
        self._saving = True
        try:
            await self._hold_control(action, BEDDING_SAVE_HOLD_MS)
        finally:
            self._saving = False

    async def program_memory(self, memory_num: int) -> None:
        await self._save_preset(self._memory_action(memory_num, "save_"))

    async def execute_app_control(self, action: str) -> None:
        if action in ("save_zero_g", "save_tv"):
            await self._save_preset(action)
            return
        await super().execute_app_control(action)

    def on_disconnect(self) -> None:
        if self._state:
            self._publish({
                "status_code": None,
                "massage_timer_code": None,
                "massage_timer_minutes": None,
            })
        self._state.clear()
        self._status_code = self._timer_code = 0
        super().on_disconnect()

    def _handle_notification(self, _: object, data: bytearray) -> None:
        self.forward_raw_notification(_NOTIFY, bytes(data))
        # The status byte is ambiguous during a save. Keep the raw packet.
        if len(data) > 10 and data[1] != 0x0C and not self._saving:
            self._handle_status(data[10])

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (self._timer_sensor_spec(),)


class ZSeriesController(OkinBeddingAppController):
    """Customatic Z-Series 1.0.4, with the user-selected Z-230 or Z-280 page."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, model: str) -> None:
        super().__init__(coordinator, app=f"zseries_{model}")
        # This connection's observation; None until a manufacturer read succeeds.
        self._alarm_available: bool | None = None

    def _hold_ms(self, action: str) -> int:
        if action in self._app.save_codes:
            return BEDDING_SAVE_HOLD_MS  # This app's save help also says five seconds.
        # Touch controls stream until release and voice is unbound, so the app
        # defines no deadline. HA bounds a press with the configured pulse count,
        # clamped so a stored out-of-range count still yields a valid hold.
        low, high = ZSERIES_PULSE_COUNT_RANGE
        return min(max(int(self._coordinator.motor_pulse_count), low), high) * CST_REFRESH_MS

    def _entry_data(self) -> Mapping[str, object] | None:
        entry = getattr(self._coordinator, "entry", None)
        data = getattr(entry, "data", None)
        return data if isinstance(data, Mapping) else None

    @property
    def alarm_state(self) -> bool | None:
        """True for CST13/CST14, False for any other string, None while unknown.

        A failed read never changes the state. The last successful observation
        is persisted per entry, so it survives disconnects, restarts and cached
        offline controllers.
        """
        if self._alarm_available is not None:
            return self._alarm_available
        data = self._entry_data()
        stored = data.get(CONF_ZSERIES_ALARM_AVAILABLE) if data is not None else None
        return stored if isinstance(stored, bool) else None

    def _manufacturer_read(self, manufacturer: str) -> None:
        # Exact, case-sensitive comparison; anything else removes the alarm page.
        self._alarm_available = manufacturer in _ALARM_MANUFACTURERS
        data = self._entry_data()
        if data is None or data.get(CONF_ZSERIES_ALARM_AVAILABLE) is self._alarm_available:
            return
        updated = {**data, CONF_ZSERIES_ALARM_AVAILABLE: self._alarm_available}
        # Internal write: the update listener must not reload (and disconnect) the entry.
        self._coordinator._begin_internal_entry_update(
            bool(data.get(CONF_BLE_BOND_ESTABLISHED, False))
        )
        self._coordinator._async_persist_config(updated, keys={CONF_ZSERIES_ALARM_AVAILABLE})

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {**super().protocol_diagnostics, "alarm_available": self.alarm_state}

    @property
    def supports_clock_alarm(self) -> bool:
        return self.alarm_state is True

    @property
    def supports_clock_sync(self) -> bool:
        return self.alarm_state is True

    @property
    def alarm_not_ruled_out(self) -> bool:
        """Service preflight: only a confirmed non-CST13/CST14 string is rejected offline."""
        return self.alarm_state is not False

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(_ALARM_WAKE) if self.alarm_state is True else ()

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self.alarm_not_ruled_out:
            return None
        # The app will not turn an alarm on until a wake action is chosen.
        return AlarmCapability(wake_actions=tuple(_ALARM_WAKE), requires_wake_action=True)

    async def resolve_alarm_state(self) -> bool | None:
        """Read the manufacturer again while the state is unknown; never downgrade on failure."""
        if self.alarm_state is None:
            await self.refresh_manufacturer()
        return self.alarm_state

    async def _require_alarm(self) -> None:
        # Services resolve every target before writing; this guards direct callers.
        state = await self.resolve_alarm_state()
        if state is None:
            raise ValueError(
                "Could not read the manufacturer string that enables Z-Series alarms; try again"
            )
        if not state:
            raise ValueError("This bed's controller has no alarm")

    async def _query_alarm(self) -> None:
        # Query runs 200 ms after the tap; it writes 300 and 600 ms after that.
        await asyncio.sleep(0.5)
        await self.write_command(_ALARM_QUERY)
        await asyncio.sleep(0.3)
        await self.write_command(_ALARM_QUERY)

    async def sync_clock(self) -> None:
        """Send the alarm page's local-clock frame, then its status queries."""
        await self._require_alarm()
        await self.write_command(clock_frame(dt_util.now()))
        await self._query_alarm()

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int] = (),
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        """Mirror the alarm switch: one set/off frame, then two status queries.

        ``preset`` is the app's wake mode. The app has no weekday or level
        fields; it always targets the next occurrence of the time.
        """
        await self._require_alarm()
        if weekdays or head_level or foot_level:
            raise ValueError("This bed's alarm has no weekdays or massage levels. Remove them and try again")
        now = dt_util.now()
        frame = alarm_frame(
            enabled=enabled,
            hour=hour,
            minute=minute,
            repeat=alarm_repeat_bit(now, hour, minute) if enabled else 0,
            wake=preset,
        )
        # The page always syncs the clock when it opens, before the switch.
        await self.write_command(clock_frame(now))
        await self.write_command(frame)
        await self._query_alarm()


def require_app_roles(client: object, app: str) -> None:
    """Raise unless the link has the roles this OKIN bedding app needs.

    The controller's own check, so a guided change requires what the runtime does.
    """
    link = cast("AdjustableBedCoordinator", SimpleNamespace(client=client))
    OkinBeddingAppController(link, app=app).require_roles()


async def build_zseries(ctx: BuildContext) -> ZSeriesController:
    """Build the Z-Series controller; nothing on the bed identifies the app page."""
    if ctx.variant not in ZSERIES_VARIANTS:
        raise ValueError("Choose the Z-230 or Z-280 page selected in the Z-Series app")
    return ZSeriesController(ctx.coordinator, model=ctx.variant)
