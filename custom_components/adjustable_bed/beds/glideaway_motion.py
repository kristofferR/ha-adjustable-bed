"""Glideaway Motion 400/450/500/600, com.ore.bedding.glideawaymontion 1.0.3.

Accepted row068 revision01 proves the E6 FE 16 protocol. This is independent of
legacy Okin ORE (A5 5A). See docs/beds/keeson.md for artifact provenance,
the app's calendar quirks, and deliberate safety differences. Hardware unverified.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime
from time import monotonic_ns
from typing import TYPE_CHECKING, Final, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..codec import keeson as codec
from ..const import GLIDEAWAY_MOTION_MODELS
from ..controller_state import StateKey
from ..profiles import keeson as keeson_profiles
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

WRITE_SERVICE: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
WRITE_CHAR: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
HOLD_INTERVAL: Final = 0.3
MEMORY_HOLD_SECONDS: Final = 5.2
STATE_TIMER: Final = StateKey[int | None]("glideaway_motion_massage_timer")
STATE_TIMER_RAW: Final = StateKey[int | None]("glideaway_motion_massage_timer_raw")
STATE_ALARM: Final = StateKey[str | None]("glideaway_motion_alarm")
STATE_ALARM_HOUR: Final = StateKey[int | None]("glideaway_motion_alarm_hour")
STATE_ALARM_MINUTE: Final = StateKey[int | None]("glideaway_motion_alarm_minute")
STATE_ALARM_WAKE: Final = StateKey[str | None]("glideaway_motion_alarm_wake")
WAKE_MODES: Final = {"none": 0x00, "memory_1": 0x11, "memory_2": 0x13}

# Names follow the live model handlers and remote guide, not unused constants.
AXES: Final = {
    "back": (0x01, 0x02),
    "feet": (0x04, 0x08),
    "both": (0x05, 0x0A),
    "tilt": (0x10, 0x20),
    "bed_height": (0x40, 0x80),
}
LAYOUTS: Final = {
    "motion_400": ("back", "feet", "both"),
    "motion_450": ("back", "feet", "bed_height"),
    "motion_500": ("back", "feet", "both", "bed_height"),
    "motion_600": ("back", "feet", "tilt", "bed_height"),
}
PRESETS: Final = {
    "flat": 0x08000000,
    "anti_snore": 0x8000,
    "zero_g": 0x1000,
    "memory_1": 0x2000,
    "memory_2": 0x4000,
}
MASSAGE: Final = {
    "intensity_up": 0x0C00,
    "intensity_down": 0x01800000,
    "wave_up": 0x10000000,
    "wave_down": 0x04000000,
    "timer": 0x0200,
    "off": 0x0100,
}
LIGHT: Final = 0x00020000


def command_frame(mask: int) -> bytes:
    """The nine-byte E6 frame; the only reachable side parameter is zero."""
    return keeson_profiles.encode(keeson_profiles.GLIDEAWAY_MOTION, mask)


def rtc_frame(now: datetime) -> bytes:
    """Retain the shipped year/month/day/hour offsets, including midnight FF."""
    year = (now.year - 1900) & 255
    return codec.clock_fields(
        (year, now.month - 1, now.day - 1, (now.hour - 1) & 255, now.minute, now.second)
    )


def alarm_frame(enabled: bool, hour: int, minute: int, wake: str, now: datetime) -> bytes:
    """Literal AlarmFragment day selection, not an inferred weekly scheduler.

    Public hour is the wire hour (0..23). The app's wheel labels 1..12 but sends
    its zero-based index plus AM/PM*12. Its weekday rule is also retained.
    """
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or wake not in WAKE_MODES:
        raise ValueError("Invalid Glideaway alarm time or wake mode")
    if enabled:
        sunday_one = (now.weekday() + 1) % 7 + 1
        bit = sunday_one - 1 if (hour, minute) <= (now.hour, now.minute) else sunday_one % 7
        fields = bytes((hour, minute, 1 << bit, WAKE_MODES[wake]))
    else:
        fields = bytes(4)
    return codec.alarm_table(codec.ALARM_WEEKLY, fields)


class GlideawayMotionController(BedController):
    """Manually selected app model, with bounded holds and serialized releases."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, model: str | None) -> None:
        super().__init__(coordinator)
        self.profile = keeson_profiles.GLIDEAWAY_MOTION
        if model is None or model not in GLIDEAWAY_MOTION_MODELS:
            raise ValueError("Choose Motion 400, 450, 500 or 600 from the Glideaway app")
        self.model = model
        self._fragment = b""
        self._fragment_time = 0.0
        self._timer_display = 0

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE_CHAR

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    def _role(self, service_uuid: str, char_uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to Glideaway Motion")
        service = client.services.get_service(service_uuid)
        characteristic = service.get_characteristic(char_uuid) if service is not None else None
        if characteristic is None:
            raise BleakError(f"Glideaway Motion requires {char_uuid} in {service_uuid}")
        return characteristic

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        characteristic = self._role(WRITE_SERVICE, WRITE_CHAR)
        # The APK leaves Android's write type unchanged. Select only a property
        # actually advertised by this characteristic, never assume firmware mode.
        properties = characteristic.properties
        if "write-without-response" in properties:
            response = False
        elif "write" in properties:
            response = True
        else:
            raise BleakError("Glideaway Motion FFE9 is not writable")
        await self._write_gatt_with_retry(
            WRITE_CHAR,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=response,
            characteristic=characteristic,
        )

    async def _release_frames(self) -> None:
        error: Exception | None = None
        for _ in range(2):
            await asyncio.sleep(HOLD_INTERVAL)
            try:
                await self.write_command(command_frame(0), cancel_event=asyncio.Event())
            except Exception as err:
                # The second release remains necessary if the first write fails.
                if error is None:
                    error = err
        if error is not None:
            raise error

    async def stop_all(self) -> None:
        """Await both delayed releases while retaining the command lane on cancellation."""
        release = asyncio.create_task(self._release_frames())
        interrupted = False
        while not release.done():
            try:
                await asyncio.shield(release)
            except asyncio.CancelledError:
                interrupted = True
        release.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _hold(self, mask: int, duration: float) -> None:
        """End a bounded held stream with the proven zero-mask release pair."""
        event = self._coordinator.cancel_command
        deadline = monotonic_ns() + round(duration * 1_000_000_000)
        try:
            while monotonic_ns() < deadline and not event.is_set():
                next_refresh = monotonic_ns() + round(HOLD_INTERVAL * 1_000_000_000)
                await self.write_command(command_frame(mask))
                delay = (min(next_refresh, deadline) - monotonic_ns()) / 1_000_000_000
                if delay > 0:
                    await _wait_for_cancel(event, delay)
        finally:
            await self.stop_all()

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 300

    async def _move_axis(self, axis: str, up: bool) -> None:
        if axis not in LAYOUTS[self.model]:
            raise ValueError(f"{self.model} has no {axis} control")
        # A leased hold (#483) refreshes until its lease ends.
        refreshes = (
            self.leased_hold_refreshes(round(HOLD_INTERVAL * 1000))
            or self._coordinator.motor_pulse_count
        )
        await self._hold(AXES[axis][0 if up else 1], refreshes * HOLD_INTERVAL)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key="head_feet" if axis == "both" else axis,
                open_fn=_axis_action(axis, True),
                close_fn=_axis_action(axis, False),
                stop_fn=lambda c: c.stop_all(),
                scheduler_resource="*",
            )
            for axis in LAYOUTS[self.model]
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset(AXES)

    async def move_back_up(self) -> None:
        await self._move_axis("back", True)

    async def move_back_down(self) -> None:
        await self._move_axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self._move_axis("tilt", True)

    async def move_head_down(self) -> None:
        await self._move_axis("tilt", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_axis("feet", True)

    async def move_legs_down(self) -> None:
        await self._move_axis("feet", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._move_axis("feet", True)

    async def move_feet_down(self) -> None:
        await self._move_axis("feet", False)

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    async def preset_flat(self) -> None:
        await self._hold(PRESETS["flat"], HOLD_INTERVAL)

    async def preset_zero_g(self) -> None:
        await self._hold(PRESETS["zero_g"], HOLD_INTERVAL)

    async def preset_anti_snore(self) -> None:
        await self._hold(PRESETS["anti_snore"], HOLD_INTERVAL)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Glideaway Motion has Memory A (1) and B (2) only")
        # A recall is deliberately shorter than the app's programming hold.
        await self._hold(PRESETS[f"memory_{memory_num}"], HOLD_INTERVAL)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Glideaway Motion has Memory A (1) and B (2) only")
        await self._hold(PRESETS[f"memory_{memory_num}"], MEMORY_HOLD_SECONDS)

    @property
    def supports_lights(self) -> bool:
        return self.model in ("motion_500", "motion_600")

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise ValueError("Only Motion 500 and 600 have light controls")
        await self._hold(LIGHT, HOLD_INTERVAL)

    @property
    def supports_massage(self) -> bool:
        return self.model in ("motion_500", "motion_600")

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_wave_frequency_control(self) -> bool:
        return self.supports_massage

    @property
    def massage_mode_step_is_timer(self) -> bool:
        return True

    async def _massage(self, action: str) -> None:
        if not self.supports_massage:
            raise ValueError("Only Motion 500 and 600 have massage controls")
        await self._hold(MASSAGE[action], HOLD_INTERVAL)

    async def massage_off(self) -> None:
        await self._massage("off")

    async def massage_intensity_up(self) -> None:
        await self._massage("intensity_up")

    async def massage_intensity_down(self) -> None:
        await self._massage("intensity_down")

    async def massage_wave_frequency_up(self) -> None:
        await self._massage("wave_up")

    async def massage_wave_frequency_down(self) -> None:
        await self._massage("wave_down")

    async def massage_mode_step(self) -> None:
        await self._massage("timer")

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            tuple(
                f"{axis}_{direction}"
                for axis in LAYOUTS[self.model]
                for direction in ("up", "down")
            )
            + tuple(PRESETS)
            + (("light", *(f"massage_{key}" for key in MASSAGE)) if self.supports_massage else ())
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 30000:
            raise ValueError("Unknown Glideaway control or hold duration outside 1..30000 ms")
        if control.startswith("memory_") and duration_ms >= 5000:
            raise ValueError("Use save_preset for memory programming holds of 5 seconds or longer")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control in PRESETS:
            mask = PRESETS[control]
        elif control == "light":
            mask = LIGHT
        elif control.startswith("massage_"):
            mask = MASSAGE[control.removeprefix("massage_")]
        else:
            axis, direction = control.rsplit("_", 1)
            mask = AXES[axis][direction == "down"]
        await self._hold(mask, duration_ms / 1000)

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(WAKE_MODES)

    async def sync_clock(self) -> None:
        await self.write_command(rtc_frame(dt_util.now()))

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        if weekdays or head_level or foot_level:
            raise ValueError("Glideaway alarms have no weekly or massage-level selectors")
        now = dt_util.now()
        packet = alarm_frame(enabled, hour, minute, preset, now)
        await self.write_command(rtc_frame(now))
        await asyncio.sleep(HOLD_INTERVAL)
        await self.write_command(packet)

    async def query_alarm(self) -> None:
        await self.write_command(codec.ALARM_QUERY)
        await asyncio.sleep(0.2)
        await self.write_command(codec.ALARM_QUERY)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "glideaway_motion_query_alarm",
                "Refresh alarm",
                lambda c: cast(GlideawayMotionController, c).query_alarm(),
                "mdi:alarm",
                translation_key="glideaway_motion_query_alarm",
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._fragment = b""
        self._notify_callback = callback
        characteristic = self._role(NOTIFY_SERVICE, NOTIFY_CHAR)
        client = self.client
        if client is None:
            raise ConnectionError("Not connected to Glideaway Motion")
        # Bleak enables the CCCD; no extra startup command is in the artifact.
        await client.start_notify(characteristic, self._on_notification)

    async def stop_notify(self) -> None:
        self._fragment = b""
        if self.client is not None and self.client.is_connected:
            await self.client.stop_notify(self._role(NOTIFY_SERVICE, NOTIFY_CHAR))

    def _timer(self, raw: int) -> None:
        # R01-F01: preserve the app's comparison of displayed minutes with raw.
        # For example previous=10/raw=10 stays 10, not 100.
        if raw == 255:
            self._timer_display = 0
        elif self._timer_display != raw:
            self._timer_display = raw * 10
        self.forward_controller_state_updates(
            STATE_TIMER(self._timer_display), STATE_TIMER_RAW(raw)
        )

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        packet = bytes(data)
        self.forward_raw_notification(NOTIFY_CHAR, packet)
        # Preserve all five live forms but reject truncation/overflow and never
        # share a fragment between devices or connections. No checksum contract
        # is proven for replies; do not invent one from the outbound frames.
        if not packet or (len(packet) < 2 and not self._fragment):
            self._fragment = b""
            return
        prefix = packet[:2]
        if prefix in (b"\xe7\xfe", b"\xed\xfe"):
            self._fragment = b""
            minimum, offset = (10, 8) if prefix[0] == 0xE7 else (16, 14)
            if len(packet) >= minimum:
                self._timer(packet[offset])
        elif prefix == b"\xed\x80":
            self._fragment = b""
            if not 7 <= len(packet) <= 16:
                return
            hour, minute, day, wake = packet[3:7]
            signed_hour = hour if hour < 128 else hour - 256
            signed_minute = minute if minute < 128 else minute - 256
            self.forward_controller_state_updates(
                STATE_ALARM("on" if any((hour, minute, day, wake)) else "off"),
                STATE_ALARM_HOUR(signed_hour),
                STATE_ALARM_MINUTE(signed_minute),
                STATE_ALARM_WAKE(next((k for k, v in WAKE_MODES.items() if v == wake), "none")),
            )
        elif prefix == b"\xf4\xfe" and len(packet) > 20:
            self._fragment = b""
            self._timer(packet[19])
        elif len(packet) >= 2 and packet[0] == 0xF4:
            self._fragment = packet if len(packet) <= 30 else b""
            self._fragment_time = asyncio.get_running_loop().time()
        elif self._fragment:
            joined = self._fragment + packet
            fresh = asyncio.get_running_loop().time() - self._fragment_time <= 2.0
            self._fragment = b""
            if fresh and 20 <= len(joined) <= 30:
                self._timer(joined[19])

    def invalidate_diagnostics(self) -> None:
        self._fragment = b""
        self._timer_display = 0
        self.forward_controller_state_updates(
            STATE_TIMER(None),
            STATE_TIMER_RAW(None),
            STATE_ALARM(None),
            STATE_ALARM_HOUR(None),
            STATE_ALARM_MINUTE(None),
            STATE_ALARM_WAKE(None),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        alarm = ControllerStateSensorSpec(
            "glideaway_motion_alarm",
            "glideaway_motion_alarm",
            STATE_ALARM,
            "mdi:alarm",
            attribute_keys=(STATE_ALARM_HOUR, STATE_ALARM_MINUTE, STATE_ALARM_WAKE),
        )
        timer = ControllerStateSensorSpec(
            "glideaway_motion_massage_timer",
            "glideaway_motion_massage_timer",
            STATE_TIMER,
            "mdi:timer-outline",
            "min",
            attribute_keys=(STATE_TIMER_RAW,),
        )
        return (alarm, timer) if self.supports_massage else (alarm,)

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset({"glideaway_motion_massage_timer", "glideaway_motion_alarm"}) - {
            s.key for s in self.controller_state_sensor_specs
        }


def _axis_action(axis: str, up: bool) -> MotorCommandCallable:
    async def move(controller: BedController) -> None:
        await cast(GlideawayMotionController, controller)._move_axis(axis, up)

    return move


async def _wait_for_cancel(event: asyncio.Event, delay: float) -> None:
    """Wait one refresh interval, interrupted by a user STOP."""
    try:
        async with asyncio.timeout(delay):
            await event.wait()
    except TimeoutError:
        pass
