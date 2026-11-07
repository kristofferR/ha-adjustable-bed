"""Comfort Enhancements 1.0.3 (com.okin.enhancements), explicit MC2..MC5 layouts.

Evidence: APK Protocol Audit row 110. No live status parser is reachable in
the app, so local control state is assumed only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE, CARD_PRESETS, CardPlacement
from ...codec import keeson as codec
from ...const import (
    COMFORT_ENHANCEMENTS_VARIANTS,
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
)
from ...profiles import keeson as keeson_profiles
from ...state_keys import MASSAGE_TIMER_MINUTES, massage_intensity
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import ControllerButtonSpec, MotorCommandCallable, MotorControlSpec

if TYPE_CHECKING:
    from datetime import datetime

    from ...coordinator import AdjustableBedCoordinator

HOLD_INTERVAL_MS = 200
RELEASE_DELAY_S = 0.1
STOP = 0x00000000
PRESET_STOP = 0x01000000
MASSAGE_BASE = {"head": 0x10000010, "foot": 0x11000010, "wave": 0x10000020}


def control_frame(word: int) -> bytes:
    """The big-endian E5 frame (CmdUtils.getCmd / CreateData)."""
    return keeson_profiles.encode(keeson_profiles.COMFORT_ENHANCEMENTS, word)


def clock_frame(now: datetime) -> bytes:
    return codec.checked(
        bytes((0xE2, 0xFE, 0x16, now.second, now.minute, now.hour, (now.weekday() + 1) % 7))
    )


def alarm_frame(
    now: datetime, *, enabled: bool, hour: int, minute: int, massage: bool, memory: int
) -> bytes:
    """Commit explicit settled fields, avoiding the app's stale wheel callbacks."""
    day = (now.weekday() + 1) % 7
    fields = (minute, hour, day, 1 << day, 0x11 if massage else 0, 0x33 if massage else 0, memory)
    if not enabled:
        fields = (0xFF, 0xFF, day, 0xFF, 0xFF, 0xFF, 0xFF)
    return codec.checked(bytes((0xEB, 0xFE, 0x16, now.second, now.minute, now.hour, *fields)))


def _axis_action(axis: str, up: bool) -> MotorCommandCallable:
    async def action(controller: BedController) -> None:
        await cast(ComfortEnhancementsController, controller)._move(axis, up)

    return action


class ComfortEnhancementsController(BedController):
    """One address, three controls and an explicitly selected app layout."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, layout: str) -> None:
        super().__init__(coordinator)
        self.profile = keeson_profiles.COMFORT_ENHANCEMENTS
        if layout not in COMFORT_ENHANCEMENTS_VARIANTS:
            raise ValueError("Choose a Comfort Enhancements MC2, MC3, MC4 or MC5 layout")
        self.layout = layout
        self._third = (
            "both" if layout in ("mc2", "mc3") else "lumbar" if layout == "mc4" else "bed_height"
        )
        self._axes = {"back": (1, 2), "legs": (4, 8), self._third: (0x10, 0x20)}
        self._last_preset: int | None = None
        self._levels = dict.fromkeys(MASSAGE_BASE, 0)
        self._timer = 0
        self._notify_char: BleakGATTCharacteristic | None = None
        # The timer is tracked from this session's commands only.
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(0))

    @property
    def control_characteristic_uuid(self) -> str:
        return KEESON_BASE_WRITE_CHAR_UUID

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def _roles(self) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic | None]:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        write = notify = None
        for service in client.services:
            for char in service.characteristics:
                if (
                    char.uuid.lower() == self.control_characteristic_uuid
                    and "write" in char.properties
                ):
                    write = char
                if (
                    char.uuid.lower() == KEESON_BASE_NOTIFY_CHAR_UUID
                    and "notify" in char.properties
                ):
                    notify = char
        if write is None:
            raise ConnectionError(
                "Comfort Enhancements requires an FFE9 characteristic with write support"
            )
        return write, notify

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        char, _ = self._roles()
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event=cancel_event,
            response="write-without-response" not in char.properties,
            characteristic=char,
            wall_clock_pacing=True,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        _, char = self._roles()
        if char is self._notify_char:
            return
        await self.stop_notify()
        if char is not None and self.client is not None:
            await self.client.start_notify(char, self._notification)
            self._notify_char = char

    def _notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        # The app's lowercase/uppercase mismatch rejects every payload. Preserve
        # raw diagnostics without inventing a parser from its unreachable code.
        self.forward_raw_notification(KEESON_BASE_NOTIFY_CHAR_UUID, bytes(data))

    async def stop_notify(self) -> None:
        char, self._notify_char = self._notify_char, None
        if char is not None and self.client is not None and self.client.is_connected:
            await self.client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._notify_char = None
        self._last_preset = None
        self._levels = dict.fromkeys(MASSAGE_BASE, 0)
        self._timer = 0

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, HOLD_INTERVAL_MS

    async def _finish_cleanup(self, action: Awaitable[None]) -> None:
        """Finish release writes before another command can own the wire."""
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

    async def _release(self, *, delay: bool) -> None:
        try:
            if delay:
                async with asyncio.timeout(RELEASE_DELAY_S):
                    await self._coordinator.cancel_command.wait()
        except TimeoutError:
            pass
        finally:
            await self._finish_cleanup(
                self.write_command(control_frame(STOP), cancel_event=asyncio.Event())
            )

    async def _move(self, axis: str, up: bool) -> None:
        if axis not in self._axes:
            raise ValueError(f"The {self.layout} layout has no {axis} control")
        try:
            count, delay = self.motor_pulse_settings()
            # A leased hold (#483) refreshes until its lease ends.
            count = self.leased_hold_refreshes(delay) or count
            await self.write_command(control_frame(self._axes[axis][0 if up else 1]), count, delay)
        finally:
            await self._release(delay=not self._coordinator.cancel_command.is_set())

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=_axis_action(axis, True),
                close_fn=_axis_action(axis, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
            )
            for axis in self._axes
        )

    async def move_back_up(self) -> None:
        await self._move("back", True)

    async def move_back_down(self) -> None:
        await self._move("back", False)

    async def move_legs_up(self) -> None:
        await self._move("legs", True)

    async def move_legs_down(self) -> None:
        await self._move("legs", False)

    async def move_head_up(self) -> None:
        await self.move_back_up()

    async def move_head_down(self) -> None:
        await self.move_back_down()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar", False)

    async def move_bed_height_up(self) -> None:
        await self._move("bed_height", True)

    async def move_bed_height_down(self) -> None:
        await self._move("bed_height", False)

    async def move_bed_height_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        # STOP is explicit in HA. A preset's repeated tap uses its separate frame.
        await self._release(delay=False)
        await self.write_command(control_frame(PRESET_STOP), cancel_event=asyncio.Event())
        self._last_preset = None

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def _preset(self, value: int) -> None:
        word = PRESET_STOP if self._last_preset == value else 0x01000000 + value
        await self.write_command(control_frame(word))
        if not self._coordinator.cancel_command.is_set():
            self._last_preset = None if word == PRESET_STOP else value

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return self.layout in ("mc2", "mc3")

    async def preset_flat(self) -> None:
        await self._preset(2)

    async def preset_zero_g(self) -> None:
        await self._preset(1)

    async def preset_tv(self) -> None:
        if not self.supports_preset_tv:
            raise ValueError("TV is only available on MC2/MC3")
        await self._preset(3)

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2 if self.layout in ("mc2", "mc3") else 1

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B") if self.memory_slot_count == 2 else ("Memory",)

    @property
    def supports_memory_programming(self) -> bool:
        return True

    def _memory_id(self, slot: int) -> int:
        if not 1 <= slot <= self.memory_slot_count:
            raise ValueError("This memory slot is unavailable on the selected layout")
        return slot + 7 if self.memory_slot_count == 2 else 3

    async def preset_memory(self, memory_num: int) -> None:
        await self._preset(self._memory_id(memory_num))

    async def program_memory(self, memory_num: int) -> None:
        await self.write_command(control_frame(0x20000000 + self._memory_id(memory_num)))

    @property
    def supports_lights(self) -> bool:
        return self.layout != "mc3"

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def lights_on(self) -> None:
        if not self.supports_lights:
            raise ValueError("MC3 has no light control")
        await self.write_command(control_frame(0x31000001))

    async def lights_off(self) -> None:
        if not self.supports_lights:
            raise ValueError("MC3 has no light control")
        await self.write_command(control_frame(0x31000000))

    @property
    def supports_massage(self) -> bool:
        return self.layout != "mc3"

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    def _require_massage(self) -> None:
        if not self.supports_massage:
            raise ValueError("MC3 has no massage page")

    async def _level(self, zone: str, level: int, *, cleanup: bool = False) -> None:
        self._require_massage()
        event = asyncio.Event() if cleanup else self._coordinator.cancel_command
        await self.write_command(control_frame(MASSAGE_BASE[zone] + level), cancel_event=event)
        if not event.is_set():
            self._levels[zone] = level
            self.forward_controller_state_updates(massage_intensity(zone)(level))
            if zone in ("head", "foot") and self._levels["head"] == self._levels["foot"] == 0:
                self._timer = 0
                self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(0))

    async def _delay(self, seconds: float) -> None:
        try:
            async with asyncio.timeout(seconds):
                await self._coordinator.cancel_command.wait()
        except TimeoutError:
            pass

    async def _start_timer(self) -> None:
        if self._timer == 0:
            await self.set_massage_timer(10)

    async def _zone_click(self, zone: str, *, cycle: bool) -> None:
        self._require_massage()
        old = self._levels[zone]
        level = (3 if old == 0 else old - 1) if cycle else (3 if old == 0 else 0)
        if old == 0:
            await self._start_timer()
            await self._delay(0.2)
        await self._level(zone, level)

    async def massage_head_toggle(self) -> None:
        await self._zone_click("head", cycle=False)

    async def massage_foot_toggle(self) -> None:
        await self._zone_click("foot", cycle=False)

    async def massage_off(self) -> None:
        await self._finish_cleanup(self._massage_shutdown(wave=False))

    async def _massage_shutdown(self, *, wave: bool) -> None:
        if wave:
            await self._level("wave", 0, cleanup=True)
            await self._delay(0.2)
            await self._level("foot", 0, cleanup=True)
            await self._delay(0.1)
            await self._level("head", 0, cleanup=True)
            return
        await self._level("head", 0, cleanup=True)
        await self._delay(0.2)
        await self._level("foot", 0, cleanup=True)

    async def massage_mode_step(self) -> None:
        self._require_massage()
        if self._coordinator.cancel_command.is_set():
            return
        if self._levels["head"] == self._levels["foot"] == 0:
            await self._start_timer()
            await self._delay(0.2)
            await self._level("head", 3)
            await self._delay(0.1)
            await self._level("foot", 3)
        else:
            wave = (self._levels["wave"] + 1) % 4
            if wave == 0:
                await self._finish_cleanup(self._massage_shutdown(wave=True))
            else:
                await self._level("wave", wave)

    @property
    def supports_massage_timer(self) -> bool:
        return self.supports_massage

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage else []

    async def set_massage_timer(self, minutes: int) -> None:
        self._require_massage()
        if minutes == 0:
            await self.massage_off()
            return
        if minutes not in self.massage_timer_options:
            raise ValueError("Choose 10, 20 or 30 minutes")
        await self.write_command(control_frame(0x10000030 + minutes // 10 - 1))
        if not self._coordinator.cancel_command.is_set():
            self._timer = minutes
            self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(minutes))

    async def _timer_click(self) -> None:
        if self._levels["head"] or self._levels["foot"]:
            await self.massage_off()
        else:
            await self.set_massage_timer(self._timer % 30 + 10)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self.write_command(clock_frame(dt_util.now()))

    def validate_alarm(
        self, *, enabled: bool, hour: int, minute: int, memory: int, massage: bool
    ) -> None:
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Choose a valid alarm time")
        if enabled and memory:
            self._memory_id(memory)
        # AlarmFragment exposes its massage checkbox on all four layouts,
        # including MC3, independently of the hidden massage page.

    async def set_alarm(
        self, *, enabled: bool, hour: int, minute: int, memory: int, massage: bool
    ) -> None:
        self.validate_alarm(
            enabled=enabled, hour=hour, minute=minute, memory=memory, massage=massage
        )
        value = 0xF0 + self._memory_id(memory) if enabled and memory else 0xFF
        await self.write_command(
            alarm_frame(
                dt_util.now(),
                enabled=enabled,
                hour=hour,
                minute=minute,
                massage=massage,
                memory=value,
            )
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def button(
            key: str, name: str, fn: MotorCommandCallable, card: CardPlacement = CARD_MASSAGE
        ) -> ControllerButtonSpec:
            return ControllerButtonSpec(key, name, fn, translation_key=key, card=card)

        specs = [
            button(
                "comfort_enhancements_quiet_sleep",
                "Quiet sleep",
                lambda c: cast(ComfortEnhancementsController, c)._preset(4),
                CARD_PRESETS,
            )
        ]
        if self.supports_massage:
            specs.extend(
                (
                    button(
                        "comfort_enhancements_head_cycle",
                        "Head massage intensity",
                        lambda c: cast(ComfortEnhancementsController, c)._zone_click(
                            "head", cycle=True
                        ),
                    ),
                    button(
                        "comfort_enhancements_foot_cycle",
                        "Foot massage intensity",
                        lambda c: cast(ComfortEnhancementsController, c)._zone_click(
                            "foot", cycle=True
                        ),
                    ),
                    button(
                        "comfort_enhancements_timer_cycle",
                        "Massage timer / stop",
                        lambda c: cast(ComfortEnhancementsController, c)._timer_click(),
                    ),
                )
            )
        return tuple(specs)


async def build_controller(ctx: BuildContext) -> ComfortEnhancementsController:
    """Build the controller for the selected Comfort Enhancements layout."""
    return ComfortEnhancementsController(ctx.coordinator, layout=ctx.variant or "")
