"""Explicit OKIN Bedding app profiles that share one OREBleDeviceManager core.

Jordan's Serenity 1.0.1 (S01), Jordan's Tranquil 1.0.2 and the Customatic
Z-Series 1.0.4 Z-230/Z-280 pages (row 052, cluster 010) were each frozen and
accepted independently. They reuse the same CST frame, refresh/release
lifecycle and notification parser, but every action table, save code, button
and alarm capability below comes from its own app. Nothing is inherited from
another app's capabilities.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..const import (
    CONF_BLE_BOND_ESTABLISHED,
    CONF_ZSERIES_ALARM_AVAILABLE,
    ZSERIES_PULSE_COUNT_RANGE,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)
from .okin_cst import CstFields, CstMemorySlot, CstProfile, OkinCstController
from .okin_protocol import build_cst_command

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ..coordinator import AdjustableBedCoordinator

_SERVICE = "62741523-52f9-8864-b1ab-3b3a8d65950b"
_NOTIFY = "62741625-52f9-8864-b1ab-3b3a8d65950b"
_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"
_ACTIONS = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "selector_4_up": (0x10, 0),
    "selector_4_down": (0x20, 0),
    "selector_5_up": (0x40, 0),
    "selector_5_down": (0x80, 0),
    "flat": (0x08000000, 0),
    "zero_g": (0x1000, 0),
    "memory_1": (0x10000, 0),
    "tv": (0x4000, 0),
    "memory_2": (0x40000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_tv": (0x08004000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
    "massage_toggle": (0x100, 0),
    "light_toggle": (0x20000, 0),
    "leisure": (0x2000, 0),
    "anti_snore": (0x8000, 0),
    "wave_1": (0, 0x80000),
    "wave_2": (0, 0x100000),
    "wave_3": (0, 0x200000),
    "massage_off": (0x02000000, 0),
    "light_on": (0, 0x40),
    "light_off": (0, 0x80),
}
_SAVE_CODES = {"save_zero_g": 5, "save_memory_1": 4, "save_tv": 6, "save_memory_2": 8}
_SAVE_HOLD_MS = 5000  # The app's save-help gesture, not a hardware threshold.

# Jordan's Tranquil 1.0.2 live Z280 remote/massage pages plus its Activity
# voice switch. Lounge is a touch button here (op9), and there is no TV.
_TRANQUIL_ACTIONS = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "selector_4_up": (0x10, 0),
    "selector_4_down": (0x20, 0),
    "selector_5_up": (0x40, 0),
    "selector_5_down": (0x80, 0),
    "flat": (0x08000000, 0),
    "zero_g": (0x1000, 0),
    "lounge": (0x2000, 0),
    "memory_1": (0x10000, 0),
    "memory_2": (0x40000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_lounge": (0x08002000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
    "massage_toggle": (0x100, 0),
    "light_toggle": (0x20000, 0),
    "anti_snore": (0x8000, 0),
    "wave_1": (0, 0x80000),
    "wave_2": (0, 0x100000),
    "wave_3": (0, 0x200000),
    "massage_off": (0x02000000, 0),
    "light_on": (0, 0x40),
    "light_off": (0, 0x80),
}

# Customatic Z-Series 1.0.4. Voice is unbound, so there are no waves, massage
# off or discrete light frames. Builder op5 emits 0x10/0x20 in this app.
_ZSERIES_COMMON_ACTIONS = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "flat": (0x08000000, 0),
    "anti_snore": (0x8000, 0),
    "memory_1": (0x10000, 0),
    "zero_g": (0x1000, 0),
    "tv": (0x4000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_tv": (0x08004000, 0),
    "light_toggle": (0x20000, 0),
    "massage_toggle": (0x100, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
}
_ZSERIES_Z230_ACTIONS = {
    **_ZSERIES_COMMON_ACTIONS,
    "head_foot_up": (0x05, 0),
    "head_foot_down": (0x0A, 0),
    "massage_intensity_cycle": (0x0C00, 0),
}
_ZSERIES_Z280_ACTIONS = {
    **_ZSERIES_COMMON_ACTIONS,
    "selector_5_up": (0x10, 0),
    "selector_5_down": (0x20, 0),
    "memory_2": (0x40000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
}

# saveMemory(n) records these local codes; callMemory(n) clears them.
_RECALLS: Final = frozenset({"flat", "anti_snore", "leisure", "lounge", "memory_1", "zero_g", "tv", "memory_2"})

# Alarm frames, Customatic Z-Series only (exact CST13/CST14 manufacturer).
_ALARM_MANUFACTURERS: Final = frozenset({"CST13", "CST14"})
_ALARM_WAKE: Final = {"massage": (9, 1), "memory_1": (17, 2)}  # UI type, wire code
_ALARM_QUERY: Final = b"\x00\xc0"
_ALARM_SELECTION: Final = 1  # Persisted bedSelection default; the app never sets it.


def alarm_frame(*, enabled: bool, hour: int, minute: int, repeat: int, wake: str) -> bytes:
    """Build the app's nine-byte alarm set/off frame."""
    if not enabled:
        return bytes((0x07, 0x05, 0, 0, 0, 0, 0, 0, _ALARM_SELECTION))
    if wake not in _ALARM_WAKE:
        raise ValueError("Wake mode must be massage or memory_1")
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and repeat in (1, 2, 4, 8, 16, 32, 64)):
        raise ValueError("Alarm time or repeat day is out of range")
    # Enable is zero only when all four caller fields are zero; wake is never zero here.
    return bytes((0x07, 0x05, repeat, _ALARM_WAKE[wake][1], hour, minute, 0, 1, _ALARM_SELECTION))


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
    return bytes(
        (
            0x07,
            0x06,
            (now.year - 2000) & 0xFF,
            now.month,
            now.day,
            (now.weekday() + 1) % 7,
            now.hour,
            now.minute,
            now.second,
        )
    )


@dataclass(frozen=True)
class OkinBeddingApp:
    """One app's literal action table and HA exposure."""

    prefix: str
    label: str
    actions: Mapping[str, tuple[int, int]]
    save_codes: Mapping[str, int]
    buttons: tuple[tuple[str, str], ...]
    profile: CstProfile


def _two_axis_profile(
    key: str,
    memory_slots: tuple[CstMemorySlot, ...],
    *,
    lounge: bool,
) -> CstProfile:
    return CstProfile(
        key=key,
        motors=("head", "feet"),
        lounge=lounge,
        incline=False,
        memory_slots=memory_slots,
        lights=True,
        massage_style="zoned",
        massage_toggle=CstFields(primary=0x100),
    )


_M1 = CstMemorySlot("M1", 0x10000, 0x08010000)
_M2 = CstMemorySlot("M2", 0x40000, 0x08040000)
_ZSERIES_BUTTONS_TAIL = (
    ("save_zero_g", "Save Zero Gravity"),
    ("save_tv", "Save TV"),
    ("light_toggle", "Toggle Light"),
    ("massage_timer_cycle", "Massage Timer Cycle"),
)

APPS: Final[dict[str, OkinBeddingApp]] = {
    "serenity": OkinBeddingApp(
        prefix="serenity",
        label="Serenity",
        actions=_ACTIONS,
        save_codes=_SAVE_CODES,
        buttons=(
            ("refresh_manufacturer", "Refresh Manufacturer"),
            ("selector_4_up", "Remote Selector 4 Up"),
            ("selector_4_down", "Remote Selector 4 Down"),
            ("selector_5_up", "Remote Selector 5 Up"),
            ("selector_5_down", "Remote Selector 5 Down"),
            ("save_zero_g", "Save Zero Gravity"),
            ("save_tv", "Save TV"),
            ("light_toggle", "Toggle Light"),
            ("massage_head_cycle", "Head Massage Cycle"),
            ("massage_foot_cycle", "Foot Massage Cycle"),
            ("massage_timer_cycle", "Massage Timer Cycle"),
            ("wave_1", "Wave 1"),
            ("wave_2", "Wave 2"),
            ("wave_3", "Wave 3"),
        ),
        profile=_two_axis_profile("serenity", (_M1, _M2), lounge=True),
    ),
    "tranquil": OkinBeddingApp(
        prefix="tranquil",
        label="Tranquil",
        actions=_TRANQUIL_ACTIONS,
        save_codes={"save_zero_g": 5, "save_lounge": 3, "save_memory_1": 4, "save_memory_2": 8},
        buttons=(
            ("refresh_manufacturer", "Refresh Manufacturer"),
            ("selector_4_up", "Remote Selector 4 Up"),
            ("selector_4_down", "Remote Selector 4 Down"),
            ("selector_5_up", "Remote Selector 5 Up"),
            ("selector_5_down", "Remote Selector 5 Down"),
            ("save_zero_g", "Save Zero Gravity"),
            ("save_lounge", "Save Lounge"),
            ("light_toggle", "Toggle Light"),
            ("massage_head_cycle", "Head Massage Cycle"),
            ("massage_foot_cycle", "Foot Massage Cycle"),
            ("massage_timer_cycle", "Massage Timer Cycle"),
            ("wave_1", "Wave 1"),
            ("wave_2", "Wave 2"),
            ("wave_3", "Wave 3"),
        ),
        profile=_two_axis_profile("tranquil", (_M1, _M2), lounge=True),
    ),
    "zseries_z230": OkinBeddingApp(
        prefix="zseries",
        label="Z-230",
        actions=_ZSERIES_Z230_ACTIONS,
        save_codes={"save_zero_g": 5, "save_memory_1": 4, "save_tv": 6},
        buttons=(
            ("refresh_manufacturer", "Refresh Manufacturer"),
            ("head_foot_up", "Head and Foot Up"),
            ("head_foot_down", "Head and Foot Down"),
            *_ZSERIES_BUTTONS_TAIL,
            ("massage_intensity_cycle", "Massage Intensity"),
        ),
        profile=_two_axis_profile("zseries_z230", (_M1,), lounge=False),
    ),
    "zseries_z280": OkinBeddingApp(
        prefix="zseries",
        label="Z-280",
        actions=_ZSERIES_Z280_ACTIONS,
        save_codes={"save_zero_g": 5, "save_memory_1": 4, "save_tv": 6, "save_memory_2": 8},
        buttons=(
            ("refresh_manufacturer", "Refresh Manufacturer"),
            ("selector_5_up", "Remote Selector 5 Up"),
            ("selector_5_down", "Remote Selector 5 Down"),
            *_ZSERIES_BUTTONS_TAIL,
            ("massage_head_cycle", "Head Massage Cycle"),
            ("massage_foot_cycle", "Foot Massage Cycle"),
        ),
        profile=_two_axis_profile("zseries_z280", (_M1, _M2), lounge=False),
    ),
}


def _callback(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        if not isinstance(controller, OkinBeddingAppController) and not (
            isinstance(controller, SideBoundController)
            and isinstance(controller._controller, OkinBeddingAppController)
        ):
            raise TypeError("This action requires an OKIN Bedding app profile")
        await controller.execute_app_control(action)

    return invoke


class OkinBeddingAppController(OkinCstController):
    """Reuse the proven CST frame without inheriting another app's capabilities."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, app: str) -> None:
        super().__init__(coordinator)
        self._app = APPS[app]
        self._profile = self._app.profile
        self._has_explicit_profile = True
        self._status_code = 0
        self._timer_code = 0
        self._save_code = 0
        self._alarm_type = 0
        self._state: dict[str, object] = {}

    def _key(self, name: str) -> str:
        return f"{self._app.prefix}_{name}"

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
        return self._coordinator.motor_pulse_count, 100

    def _hold_ms(self, action: str) -> int:
        """Default hold for a non-service action (voice deadlines and save help)."""
        if action in self._app.save_codes:
            return _SAVE_HOLD_MS
        # The reachable voice path stops flat after 1500 ms and the rest after 500 ms.
        return 1500 if action == "flat" else 500

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {**super().protocol_diagnostics, **self._state, "save_pending_code": self._save_code}

    def _publish(self, updates: dict[str, object]) -> None:
        self._state.update(updates)
        self.forward_controller_state_updates(updates)

    def _write_response(self) -> bool:
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
            return True
        if "write-without-response" in matches[0].properties:
            return False
        raise ValueError(f"{label} command characteristic is not writable")

    async def async_discover_capabilities(self) -> None:
        self._write_response()
        client = self.client
        if client is None:
            raise ConnectionError(f"{self._app.label} is not connected")
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == _SERVICE
            for char in service.characteristics
            if char.uuid.lower() == _NOTIFY and "notify" in char.properties
        ]
        if len(matches) != 1:
            raise ValueError(f"{self._app.label} requires its notification characteristic")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_response(),
            wall_clock_pacing=True,
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

    async def refresh_manufacturer(self) -> None:
        """Repeat the reachable on-resume read without selecting capabilities."""
        client = self.client
        if client is None or not client.is_connected:
            return
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == "0000180a-0000-1000-8000-00805f9b34fb"
            for char in service.characteristics
            if char.uuid.lower() == _MANUFACTURER and "read" in char.properties
        ]
        if len(matches) != 1:
            return
        try:
            async with asyncio.timeout(2):
                async with self._ble_lock:
                    value = await client.read_gatt_char(_MANUFACTURER)
            manufacturer = bytes(value).decode("utf-8", errors="replace")
        except BleakError, OSError, TimeoutError:
            return  # Missing diagnostic information does not block control.
        self._manufacturer_read(manufacturer)
        self._publish({self._key("manufacturer"): manufacturer})

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
                    self._key("alarm_type"): self._alarm_type,
                    self._key("alarm_repeat"): signed(data[4]),
                    self._key("alarm_hour"): signed(data[6]),
                    self._key("alarm_minute"): signed(data[7]),
                    self._key("alarm_on"): data[9] == 1,
                }
            )
            return
        code = signed(data[10])
        if code == self._status_code:
            return
        self._status_code = code
        updates: dict[str, object] = {self._key("status_code"): code}
        # HA supplies the active callback equivalent. The source treats any
        # status change during save as a local success, not a hardware ACK.
        if self._save_code:
            updates[self._key("save_event_code")] = self._save_code
            self._save_code = 0
        elif code != self._timer_code:
            self._timer_code = code
            updates.update(
                {
                    self._key("massage_timer_code"): code,
                    self._key("massage_timer_minutes"): {1: 10, 2: 20, 3: 30}.get(code),
                }
            )
        self._publish(updates)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        keys = (
            "manufacturer",
            "status_code",
            "massage_timer_code",
            "massage_timer_minutes",
            "save_event_code",
            "alarm_type",
        )
        return tuple(
            ControllerStateSensorSpec(
                key=self._key(key),
                # The apps share one parser, so their sensors share names.
                translation_key=f"okin_bedding_app_{key}",
                state_key=self._key(key),
                icon="mdi:information-outline",
                native_unit_of_measurement="min" if key == "massage_timer_minutes" else None,
                attribute_keys=tuple(
                    self._key(name)
                    for name in ("alarm_repeat", "alarm_hour", "alarm_minute", "alarm_on")
                )
                if key == "alarm_type"
                else (),
            )
            for key in keys
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._app.actions)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self._app.actions:
            raise ValueError(f"Unknown {self._app.label} action")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Duration must be a positive integer, at most 60000 ms")
        primary, secondary = self._app.actions[control]
        # The app records local save intent before writing, not a storage ACK.
        if control in self._app.save_codes:
            self._save_code = self._app.save_codes[control]
        elif control in _RECALLS:
            self._save_code = 0
        deadline = asyncio.timeout(duration_ms / 1000)
        controller_timeout = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            build_cst_command(primary, secondary),
                            repeat_count=self.timed_move_repeat_count(duration_ms, 100),
                            repeat_delay_ms=100,
                        )
                    except TimeoutError:
                        controller_timeout = True
                        raise
            except TimeoutError:
                if controller_timeout or not deadline.expired():
                    raise
        finally:
            await self._send_stop_sequence()

    async def _send_stop_sequence(self) -> None:
        async def release() -> None:
            event = asyncio.Event()
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for offset in (0.1, 0.2):
                await asyncio.sleep(max(0, started + offset - loop.time()))
                try:
                    await self.write_command(build_cst_command(), cancel_event=event)
                except Exception as error:
                    # The source schedules both releases independently.
                    failure = failure or error
            if failure is not None:
                raise failure

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

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
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(self._key(action), name, _callback(action))
            for action, name in self._app.buttons
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


class ZSeriesController(OkinBeddingAppController):
    """Customatic Z-Series 1.0.4, with the user-selected Z-230 or Z-280 page."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, model: str
    ) -> None:
        super().__init__(coordinator, app=f"zseries_{model}")
        # This connection's observation; None until a manufacturer read succeeds.
        self._alarm_available: bool | None = None

    def _hold_ms(self, action: str) -> int:
        if action in self._app.save_codes:
            return _SAVE_HOLD_MS  # This app's save help also says five seconds.
        # Touch controls stream until release and voice is unbound, so the app
        # defines no deadline. HA bounds a press with the configured pulse count,
        # clamped so a stored out-of-range count still yields a valid hold.
        low, high = ZSERIES_PULSE_COUNT_RANGE
        return min(max(int(self._coordinator.motor_pulse_count), low), high) * 100

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
            raise ValueError("This controller's manufacturer string does not enable app alarms")

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
            raise ValueError("Z-Series alarms have no weekday or massage-level fields")
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
