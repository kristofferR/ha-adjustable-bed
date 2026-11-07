"""Explicit BF 1.2.3 and Cherish 1.0.4 profiles (accepted row063).

These apps share framing, not their command tables or alarm format. No
advertisement identifies either app.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..app_session import app_session
from ..codec import keeson as codec
from ..controller_state import StateKey
from ..profiles import keeson as keeson_profiles
from ..state_keys import MASSAGE_TIMER_MINUTES
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
_LEVEL_KEYS: Final = {
    field: StateKey[int | None](f"bf_cherish_{field}") for field in ("intensity", "wave")
}
ALARM: Final = StateKey[str]("bf_cherish_alarm")
ALARM_HOUR: Final = StateKey[int]("bf_cherish_alarm_hour")
ALARM_MINUTE: Final = StateKey[int]("bf_cherish_alarm_minute")
ALARM_MEMORY: Final = StateKey[str]("bf_cherish_alarm_memory")
ALARM_RAW_SELECTOR: Final = StateKey[int | None]("bf_cherish_alarm_raw_selector")
ALARM_SOURCE: Final = StateKey[str]("bf_cherish_alarm_source")
MOVE_KEYS: Final = {
    "back_up": 1,
    "back_down": 2,
    "legs_up": 4,
    "legs_down": 8,
    "head_up": 16,
    "head_down": 32,
    "both_up": 5,
    "both_down": 10,
}
BF_PRESETS: Final = {
    "zero_g": 0x01000001,
    "flat": 0x01000002,
    "anti_snore": 0x01000004,
    "memory_1": 0x01000008,
    "memory_2": 0x01000009,
}
CH_PRESETS: Final = {
    "zero_g": 0x21000001,
    "flat": 0x21000002,
    "anti_snore": 0x21000003,
    "memory_1": 0x21000004,
    "memory_2": 0x21000006,
}
PRESET_POSITIONS: Final = {"zero_g": 6, "flat": 7, "anti_snore": 8, "memory_1": 9, "memory_2": 11}


def control_frame(key: int, profile: keeson_profiles.KeesonProfile = keeson_profiles.BF) -> bytes:
    """The big-endian E5 frame of the low 32 bits of ``key``; BF and Cherish share it."""
    return keeson_profiles.encode(profile, key & 0xFFFFFFFF)


def query_frame(now: datetime) -> bytes:
    return codec.checked(
        bytes((0xE2, 0xFE, 0x16, now.second, now.minute, now.hour, (now.weekday() + 1) % 7))
    )


def alarm_frame(
    cherish: bool, now: datetime, *, enabled: bool, hour: int, minute: int, memory: str
) -> bytes:
    """Build an explicit alarm setting, without Android wheel/selector races."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59) or memory not in (
        "none",
        "memory_1",
        "memory_2",
    ):
        raise ValueError("Choose a valid alarm time and memory")
    selector = (
        {"none": 255, "memory_1": 4, "memory_2": 6}
        if cherish
        else {"none": 255, "memory_1": 248, "memory_2": 249}
    )[memory]
    if cherish:
        return codec.checked(
            bytes(
                (
                    0xEA,
                    0xFE,
                    0x16,
                    now.second,
                    now.minute,
                    now.hour,
                    minute if enabled else 255,
                    hour if enabled else 255,
                    255,
                    255,
                    255,
                    selector if enabled else 255,
                )
            )
        )
    weekday = (now.weekday() + 1) % 7
    day = (weekday + ((hour, minute) < (now.hour, now.minute))) % 7
    return codec.checked(
        bytes(
            (
                0xEB,
                0xFE,
                0x16,
                now.second,
                now.minute,
                now.hour,
                minute if enabled else 255,
                hour if enabled else 255,
                weekday,
                (1 << day) if enabled else 255,
                0 if enabled else 255,
                0 if enabled else 255,
                selector if enabled else 255,
            )
        )
    )


@dataclass(slots=True)
class AppState:
    last_position: int = -1
    count: int = -1
    light_on: bool = False
    wave: int = 0
    intensity: int = 0
    timer: int = 10
    timer_selected: int | None = None
    massage_on: bool = False
    alarm_hour: int = 0
    alarm_minute: int = 0
    alarm_memory: str = "none"
    alarm_enabled: bool | None = None
    alarm_until: str | None = None
    alarm_raw_selector: int | None = None
    alarm_source: str = "unknown"


def _action(method: str, *args: object) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        if not isinstance(controller, BfCherishController):
            raise ValueError("Requires a BF or Cherish app bed")
        await getattr(controller, method)(*args)

    return invoke


class BfCherishController(BedController):
    """App-owned controls with HA serialization, cancellation and readiness checks."""

    def __init__(self, coordinator: Any, *, cherish: bool = False) -> None:
        super().__init__(coordinator)
        self.cherish = cherish
        self.profile = keeson_profiles.CHERISH if cherish else keeson_profiles.BF
        self.state = app_session(
            coordinator.hass, str(coordinator.address), ("bf_cherish", cherish), AppState
        )
        self._subscriptions: list[BleakGATTCharacteristic] = []
        self._notify_role: tuple[str, str] | None = None
        self._publish()

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE_UUID

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        # Alarm/diagnostic notifications are independent of angle sensing.
        return True

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = ("back", "legs") if self.cherish else ("back", "legs", "head")
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                _action("move", axis + "_up"),
                _action("move", axis + "_down"),
                _action("movement_stop"),
            )
            for axis in axes
        )

    def _target(self) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        selected = None
        # The selected apps retain the last matching service/characteristic role.
        for service in client.services:
            matches = [char for char in service.characteristics if char.uuid.lower() == WRITE_UUID]
            if matches:
                selected = matches[0]
        if selected is None or "write" not in selected.properties:
            raise ConnectionError("The selected bed has no writable FFE9 characteristic")
        return selected

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            WRITE_UUID,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event,
            characteristic=self._target(),
            response=True,
            wall_clock_pacing=True,
        )

    async def _key(self, key: int, *, cleanup: bool = False) -> bool:
        event = asyncio.Event() if cleanup else self._coordinator.cancel_command
        if event.is_set():
            return False
        await self.write_command(control_frame(key, self.profile), cancel_event=event)
        return not event.is_set()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        await self.stop_notify()
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        try:
            for service in client.services:
                for char in service.characteristics:
                    if char.uuid.lower() != NOTIFY_UUID:
                        continue
                    self._notify_role = (char.service_uuid.lower(), char.uuid.lower())
                    if "notify" in char.properties:
                        try:
                            await client.start_notify(char, self._notification)
                        except BleakError, TimeoutError:
                            continue
                        self._subscriptions.append(char)
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        client = self.client
        subscriptions, self._subscriptions = self._subscriptions, []
        for char in subscriptions:
            if client is not None and client.is_connected:
                try:
                    await client.stop_notify(char)
                except Exception:  # The disconnected transport can already have removed the CCCD.
                    pass
        self._notify_callback = None

    def _notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        # MyService filters by its last discovered UUID pair, not by payload alone.
        if sender.uuid.lower() != NOTIFY_UUID or (
            self._notify_role is not None
            and (sender.service_uuid.lower(), sender.uuid.lower()) != self._notify_role
        ):
            return
        # Cherish registers this event but has no consuming alarm parser.
        if self.cherish or len(data) < 10 or data[:3] != b"\xe2\xfe\x16":
            return
        state = self.state
        minute, hour, selector = data[3], data[4], data[9]
        state.alarm_enabled = not (minute > 59 and hour > 24)
        if state.alarm_enabled:
            state.alarm_minute, state.alarm_hour = minute, hour
        else:
            now = dt_util.now()
            state.alarm_minute, state.alarm_hour = now.minute, now.hour
        if selector in (248, 249, 255):
            state.alarm_memory = {248: "memory_1", 249: "memory_2", 255: "none"}[selector]
        state.alarm_source = "reported"
        state.alarm_raw_selector = selector
        self._publish()

    async def move(self, control: str) -> None:
        allowed = {
            axis + suffix for axis in ("back", "legs", "head") for suffix in ("_up", "_down")
        }
        if self.cherish:
            allowed = allowed - {"head_up", "head_down"} | {"both_up", "both_down"}
        if control not in allowed:
            raise ValueError("This app does not expose that motor")
        self._target()
        if self._coordinator.cancel_command.is_set():
            return
        self.state.last_position = {
            "back_up": 0,
            "legs_up": 1,
            "head_up": 2,
            "both_up": 2,
            "back_down": 3,
            "legs_down": 4,
            "head_down": 5,
            "both_down": 5,
        }[control]
        count, _ = self.motor_pulse_settings()
        # A leased hold (#483) refreshes until its lease ends.
        count = self.leased_hold_refreshes(200) or count
        try:
            await self.write_command(
                control_frame(MOVE_KEYS[control], self.profile), repeat_count=count, repeat_delay_ms=200
            )
        finally:
            await self.movement_stop()

    async def _finish_cleanup(self, action: Awaitable[object]) -> None:
        task = asyncio.ensure_future(action)
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def movement_stop(self) -> None:
        await self._finish_cleanup(self._key(0, cleanup=True))

    async def stop_all(self) -> None:
        await self._finish_cleanup(self._stop_frames())

    async def _stop_frames(self) -> None:
        # Preset STOP differs from movement release. Attempt both even on failure.
        try:
            await self.movement_stop()
        finally:
            await self._key(0x21000000 if self.cherish else 0x01000000, cleanup=True)

    async def move_head_up(self) -> None:
        await self.move("head_up")

    async def move_head_down(self) -> None:
        await self.move("head_down")

    async def move_head_stop(self) -> None:
        await self.movement_stop()

    async def move_back_up(self) -> None:
        await self.move("back_up")

    async def move_back_down(self) -> None:
        await self.move("back_down")

    async def move_back_stop(self) -> None:
        await self.movement_stop()

    async def move_legs_up(self) -> None:
        await self.move("legs_up")

    async def move_legs_down(self) -> None:
        await self.move("legs_down")

    async def move_legs_stop(self) -> None:
        await self.movement_stop()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("These apps have no fourth axis")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("These apps have no fourth axis")

    async def move_feet_stop(self) -> None:
        await self.movement_stop()

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    async def tap_preset(self, name: str) -> None:
        keys = CH_PRESETS if self.cherish else BF_PRESETS
        if name not in keys:
            raise ValueError("Unknown app preset")
        self._target()
        state = self.state
        position = PRESET_POSITIONS[name]
        if state.last_position != position or state.count == 0:
            if not await self._key(keys[name]):
                return
            state.count = 1
        elif state.count == 1:
            if not await self._key(0x21000000 if self.cherish else 0x01000000):
                return
            state.count = 0
        state.last_position = position

    async def preset_flat(self) -> None:
        await self.tap_preset("flat")

    async def preset_zero_g(self) -> None:
        await self.tap_preset("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.tap_preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Choose memory 1 or 2")
        await self.tap_preset(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Choose memory 1 or 2")
        key = ({1: 0x21000014, 2: 0x21000016} if self.cherish else {1: 0x20000008, 2: 0x20000009})[
            memory_num
        ]
        if await self._key(key):
            self.state.last_position = PRESET_POSITIONS[f"memory_{memory_num}"]
            # Long-save preserves the shared count, including the initial -1 no-write branch.

    @property
    def supports_lights(self) -> bool:
        return self.cherish

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.cherish

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.cherish

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def lights_on(self) -> None:
        if not self.cherish:
            raise NotImplementedError("BF's light command collides with Zero Gravity")
        if await self._key(0x31000001):
            self.state.light_on = True
            self.state.last_position, self.state.count = 10, 1

    async def lights_off(self) -> None:
        if not self.cherish:
            raise NotImplementedError("BF's light command collides with Zero Gravity")
        if await self._key(0x31000000):
            self.state.light_on = False
            self.state.last_position, self.state.count = 10, 0

    async def lights_toggle(self) -> None:
        await (
            self.lights_off()
            if self.state.last_position == 10 and self.state.count == 1
            else self.lights_on()
        )

    @property
    def supports_massage(self) -> bool:
        return self.cherish

    @property
    def auto_enable_massage(self) -> bool:
        return self.cherish

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self.cherish

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self.cherish

    @property
    def supports_massage_off_control(self) -> bool:
        return self.cherish

    @property
    def supports_massage_timer(self) -> bool:
        return self.cherish

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.cherish else []

    def _massage(self) -> None:
        if not self.cherish:
            raise NotImplementedError("BF has no massage page")

    async def massage_on(self) -> None:
        self._massage()
        state = self.state
        if state.massage_on:
            return
        wave, intensity = state.wave or 1, state.intensity or 1
        try:
            if not await self._key(0x10000030 + state.timer // 10 - 1):
                return
            await asyncio.sleep(0.1)
            if not await self._key(0x10000020 + wave):
                return
            await asyncio.sleep(0.2)
            if not await self._key(0x10000010 + intensity):
                return
            state.wave, state.intensity, state.massage_on = wave, intensity, True
            state.timer_selected = state.timer
        finally:
            # HA does not leave Android's delayed starts running after STOP/cancellation.
            if not state.massage_on:
                await self.massage_off()
        self._publish()

    async def massage_off(self) -> None:
        self._massage()
        await self._finish_cleanup(self._massage_release())

    async def _massage_release(self) -> None:
        try:
            await self._key(0x10000010, cleanup=True)
        finally:
            await asyncio.sleep(0.1)
            await self._key(0x10000020, cleanup=True)
            self.state.massage_on = False
            self.state.timer_selected = None
            self._publish()

    async def massage_toggle(self) -> None:
        await (self.massage_off() if self.state.massage_on else self.massage_on())

    async def set_massage_timer(self, minutes: int) -> None:
        self._massage()
        if minutes == 0:
            await self.massage_off()
            return
        if minutes not in (10, 20, 30):
            raise ValueError("Choose 10, 20 or 30 minutes")
        if await self._key(0x10000030 + minutes // 10 - 1):
            self.state.timer, self.state.massage_on = minutes, False
            self.state.timer_selected = minutes
            self._publish()

    async def set_level(self, field: str, level: int) -> None:
        self._massage()
        if field not in ("wave", "intensity") or level not in (1, 2, 3):
            raise ValueError("Choose wave or intensity 1, 2 or 3")
        if not self.state.massage_on:
            raise ValueError("Start massage before changing its levels")
        if await self._key((0x10000020 if field == "wave" else 0x10000010) + level):
            setattr(self.state, field, level)
            self._publish()

    async def _step(self, field: str, delta: int) -> None:
        level = getattr(self.state, field) + delta
        if 1 <= level <= 3:
            await self.set_level(field, level)

    async def massage_intensity_up(self) -> None:
        await self._step("intensity", 1)

    async def massage_intensity_down(self) -> None:
        await self._step("intensity", -1)

    async def massage_wave_next(self) -> None:
        await self._step("wave", 1)

    async def massage_wave_previous(self) -> None:
        await self._step("wave", -1)

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self.cherish

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.cherish:
            return ()

        def spec(field: str) -> ControllerNumberSpec:
            async def set_value(controller: BedController, value: float) -> None:
                if not isinstance(controller, BfCherishController):
                    raise ValueError("Requires Cherish")
                await controller.set_level(field, int(value))

            return ControllerNumberSpec(
                "bf_cherish_" + field,
                "bf_cherish_" + field,
                _LEVEL_KEYS[field],
                1,
                3,
                1,
                set_value,
            )

        return (spec("intensity"), spec("wave"))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self.cherish:
            return tuple(
                ControllerButtonSpec(
                    "bf_cherish_" + control,
                    label,
                    _action("move", control),
                    translation_key="bf_cherish_" + control,
                )
                for control, label in (
                    ("both_up", "Back and legs up"),
                    ("both_down", "Back and legs down"),
                )
            )
        return (
            ControllerButtonSpec(
                "bf_query_alarm",
                "Query bed alarm",
                _action("query_alarm"),
                translation_key="bf_query_alarm",
                cancel_movement=False,
            ),
        )

    async def query_alarm(self) -> None:
        if self.cherish:
            raise NotImplementedError("Cherish has no reachable alarm query")
        await self.write_command(query_frame(dt_util.now()))

    @property
    def supports_clock_alarm(self) -> bool:
        return True

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
        if weekdays or head_level or foot_level:
            raise ValueError("These apps have no selectable recurrence or massage alarm fields")
        now = dt_util.now()
        frame = alarm_frame(
            self.cherish, now, enabled=enabled, hour=hour, minute=minute, memory=preset
        )
        event = self._coordinator.cancel_command
        if event.is_set():
            return
        await self.write_command(frame)
        if not enabled and not event.is_set():
            # Each disable frame samples the clock separately. BF uses EB then EA; CH EA twice.
            await self.write_command(
                alarm_frame(True, dt_util.now(), enabled=False, hour=0, minute=0, memory="none")
            )
        if event.is_set():
            return
        if enabled:
            self.state.alarm_hour, self.state.alarm_minute, self.state.alarm_memory = (
                hour,
                minute,
                preset,
            )
            when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if (hour, minute) < (now.hour, now.minute):
                when += timedelta(days=1)
            self.state.alarm_until = when.isoformat()
        self.state.alarm_enabled = enabled
        self.state.alarm_source = "commanded"
        self._coordinator.save_app_state(self)
        self._publish()

    @property
    def persisted_app_state(self) -> Mapping[str, Any] | None:
        if not self.cherish:
            return None
        return {
            "hour": self.state.alarm_hour,
            "minute": self.state.alarm_minute,
            "memory": self.state.alarm_memory,
            "until": self.state.alarm_until,
            "enabled": self.state.alarm_enabled,
        }

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        if not self.cherish:
            return
        hour, minute, memory = (
            state.get("hour", 0),
            state.get("minute", 0),
            state.get("memory", "none"),
        )
        alarm_frame(True, dt_util.now(), enabled=True, hour=hour, minute=minute, memory=memory)
        until = state.get("until")
        when = dt_util.parse_datetime(until) if isinstance(until, str) else None
        self.state.alarm_hour, self.state.alarm_minute, self.state.alarm_memory = (
            hour,
            minute,
            memory,
        )
        self.state.alarm_until = until
        self.state.alarm_enabled = bool(
            state.get("enabled") and when and dt_util.as_utc(when) > dt_util.utcnow()
        )
        self._publish()

    def get_massage_state(self) -> dict[str, Any]:
        return {"timer_mode": self.state.timer_selected}

    def _publish(self) -> None:
        state = self.state
        self.forward_controller_state_updates(
            MASSAGE_TIMER_MINUTES(state.timer_selected),
            _LEVEL_KEYS["intensity"](state.intensity or None),
            _LEVEL_KEYS["wave"](state.wave or None),
            ALARM(
                "unknown"
                if state.alarm_enabled is None
                else "enabled"
                if state.alarm_enabled
                else "disabled"
            ),
            ALARM_HOUR(state.alarm_hour),
            ALARM_MINUTE(state.alarm_minute),
            ALARM_MEMORY(state.alarm_memory),
            ALARM_RAW_SELECTOR(state.alarm_raw_selector),
            ALARM_SOURCE(state.alarm_source),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "bf_cherish_alarm",
                "bf_cherish_alarm",
                ALARM,
                "mdi:alarm",
                attribute_keys=(
                    ALARM_HOUR,
                    ALARM_MINUTE,
                    ALARM_MEMORY,
                    ALARM_RAW_SELECTOR,
                    ALARM_SOURCE,
                ),
            ),
        )
