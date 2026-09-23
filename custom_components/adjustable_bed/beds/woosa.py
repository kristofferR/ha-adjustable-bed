"""Explicit Woosa Sleep profile, verified against com.sn.woosa 1.1.9.

The shared discovery names cannot identify the app. Only an explicit profile
selects these commands. See docs/beds/woosa-disposition.md for evidence and
intentional differences from the Android UI.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Collection
from functools import partial
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from .base import BedController, ControllerButtonSpec
from .solace import (
    SolaceCommands,
    SolaceController,
    SolaceProfile,
    build_solace_alarm_command,
    build_solace_clock_command,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_INIT = bytes.fromhex("FFFFFFFF02000E0B001704")
_ALARM_QUERY = bytes.fromhex("FFFFFFFF01000A0B0F2104")
_PRESET_QUERIES = tuple(
    bytes.fromhex(frame)
    for frame in (
        "FFFFFFFF03002800039F09",
        "FFFFFFFF03001800039F06",
        "FFFFFFFF03002000031ECB",
        "FFFFFFFF03003800039ECC",
    )
)
_LIGHT_OFF = bytes.fromhex("FFFFFFFF050000004B9737")
_MODE_STEP = bytes.fromhex("FFFFFFFF0500050014C70E")
_HEAD_LEVELS = tuple(
    bytes.fromhex(frame)
    for frame in (
        "FFFFFFFF050000004F96F4",
        "FFFFFFFF0500000050D73C",
        "FFFFFFFF050000005116FC",
        "FFFFFFFF050000005256FD",
    )
)
_FOOT_LEVELS = tuple(
    bytes.fromhex(frame)
    for frame in (
        "FFFFFFFF0500000053973D",
        "FFFFFFFF0500000054D6FF",
        "FFFFFFFF0500000055173F",
        "FFFFFFFF0500000056573E",
    )
)
_MODES = tuple(
    bytes.fromhex(frame)
    for frame in (
        "FFFFFFFF050000005796FE",
        "FFFFFFFF0500000058D6FA",
        "FFFFFFFF0500000059173A",
        "FFFFFFFF050000005A573B",
    )
)
_MASSAGE_REPLIES = {
    "head": tuple(
        bytes.fromhex(frame)
        for frame in (
            "FFFFFFFF0500000100D690",
            "FFFFFFFF050000011E5698",
            "FFFFFFFF050000011F9758",
            "FFFFFFFF0500000120D748",
        )
    ),
    "foot": tuple(
        bytes.fromhex(frame)
        for frame in (
            "FFFFFFFF0500000200D660",
            "FFFFFFFF05000002211678",
            "FFFFFFFF05000002225679",
            "FFFFFFFF050000022397B9",
        )
    ),
    "mode": tuple(
        bytes.fromhex(frame)
        for frame in (
            "FFFFFFFF0500000324D7EB",
            "FFFFFFFF0500000325162B",
            "FFFFFFFF0500000326562A",
            "FFFFFFFF050000032797EA",
        )
    ),
}
_SAVES = {
    "memory_1": SolaceCommands.PROGRAM_MEMORY_1,
    "love": SolaceCommands.PROGRAM_ANTI_SNORE,
    "tv": SolaceCommands.PROGRAM_TV,
    "zero_g": SolaceCommands.PROGRAM_ZERO_G,
}


async def _button_action(controller: BedController, *, action: str) -> None:
    """Dispatch profile actions on the live controller, including paired sides."""
    if not isinstance(controller, WoosaController):
        raise ValueError("This action requires the Woosa Sleep profile")
    if action == "love":
        await controller.preset_love()
    elif action.startswith("save_"):
        await controller.save_preset(action.removeprefix("save_"))
    else:
        await controller.set_massage_mode(int(action.removeprefix("mode_")))


class WoosaController(SolaceController):
    """Woosa's two-motor, lighting, massage, preset and alarm surface."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._massage_expiry_handle: asyncio.TimerHandle | None = None

    @property
    def profile(self) -> SolaceProfile:
        return SolaceProfile.WOOSA

    @property
    def _query_family(self) -> str:
        return "woosa"

    @property
    def supports_preset_anti_snore(self) -> bool:
        # The app labels this command Love, not anti-snore.
        return False

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_level_control(self) -> bool:
        return True

    @property
    def light_timer_options(self) -> list[str]:
        return ["Off", "10 min", "8 hours", "10 hours"]

    @property
    def light_auto_off_seconds(self) -> int | None:
        option = self._coordinator.controller_state.get("light_timer_option")
        if not isinstance(option, str):
            return None
        return {
            "10 min": 10 * 60,
            "8 hours": 8 * 60 * 60,
            "10 hours": 10 * 60 * 60,
        }.get(option)

    def on_light_auto_off(self) -> None:
        self.forward_controller_state_updates(
            {"under_bed_lights_on": False, "light_timer_option": "Off"}
        )

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_wave_frequency_control(self) -> bool:
        return False

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["head", "foot"]

    @property
    def massage_intensity_max(self) -> int:
        return 3

    @property
    def supports_solace_alarm(self) -> bool:
        return True

    @property
    def solace_alarm_sound_options(self) -> tuple[str, ...]:
        return ("none", "alarm")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = (
            ("love", "Love"),
            ("save_love", "Save Love position"),
            ("save_tv", "Save TV position"),
            ("save_zero_g", "Save zero-gravity position"),
            *((f"mode_{mode}", f"Massage mode {mode}") for mode in range(1, 5)),
        )
        return tuple(
            ControllerButtonSpec(
                key=f"woosa_{action.replace('save_', 'program_').replace('mode_', 'massage_mode_')}",
                name=name,
                press_fn=partial(_button_action, action=action),
            )
            for action, name in actions
        )

    async def _async_query_preset_states(self, query_family: str) -> None:
        """Serialize both app startup workers and the light-screen query."""

        async def query(controller: BedController) -> None:
            if controller is not self:
                return
            self.forward_controller_state_updates(
                {f"solace_{key}_selected": False for key in _SAVES}
            )
            # Preserve each worker's offsets; serialize coincident writes.
            schedule = (
                (0.5, _INIT),
                (0.6, _PRESET_QUERIES[0]),
                (0.9, _PRESET_QUERIES[1]),
                (1.0, None),
                (1.2, _PRESET_QUERIES[2]),
                (1.5, _ALARM_QUERY),
                (1.5, _PRESET_QUERIES[3]),
                (1.5, SolaceCommands.LIGHT_STATUS_QUERY),
            )
            previous = 0.0
            for offset, command in schedule:
                await asyncio.sleep(offset - previous)
                await self.write_command(
                    command if command is not None else build_solace_clock_command(dt_util.now())
                )
                previous = offset

        try:
            await self._coordinator.async_execute_controller_query(
                query,
                skip_disconnect=True,
                preemptible=True,
                run_if=lambda: (
                    self._query_task is asyncio.current_task()
                    and self._coordinator.controller is self
                ),
            )
        except (BleakError, ConnectionError, RuntimeError) as err:
            _LOGGER.debug("Woosa startup query failed: %s", err)
        finally:
            if self._query_task is asyncio.current_task():
                self._query_task = None

    async def move_legs_down(self) -> None:
        """Follow the app's leg arrow, which shares its frame with Flat."""
        await self._move_with_stop(SolaceCommands.PRESET_FLAT_BED)

    async def _send_preset(self, command: bytes) -> None:
        await self._send_stop()
        await asyncio.sleep(0.2)
        if not self._coordinator.cancel_command.is_set():
            await self.write_command(command)

    async def preset_flat(self) -> None:
        # Flat's direct button has no preset-selection preamble.
        await self.write_command(SolaceCommands.PRESET_FLAT_BED)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("Woosa has one numbered Favourite memory")
        if not self._preset_is_selected("memory_1"):
            raise ValueError("Woosa has not reported a saved Favourite position")
        await self._send_preset(SolaceCommands.PRESET_MEMORY_1)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("Woosa has one numbered Favourite memory")
        await self.save_preset("memory_1")

    async def save_preset(self, key: str) -> None:
        await self.write_command(_SAVES[key])
        # The app re-queries after saving; only replies establish saved state.
        for command in _PRESET_QUERIES:
            await asyncio.sleep(0.3)
            await self.write_command(command)

    async def preset_love(self) -> None:
        await self._send_preset(
            SolaceCommands.PRESET_ANTI_SNORE_SELECTED
            if self._preset_is_selected("love")
            else SolaceCommands.PRESET_ANTI_SNORE
        )

    async def lights_on(self) -> None:
        timer = self._coordinator.controller_state.get("woosa_light_timer", "10 min")
        await self.set_light_timer(str(timer))

    async def lights_off(self) -> None:
        await self.write_command(_LIGHT_OFF)
        self.forward_controller_state_updates(
            {"under_bed_lights_on": False, "light_timer_option": "Off"}
        )

    async def set_light_level(self, level: int) -> None:
        await super().set_light_level(level)
        if 0 <= level <= self.light_level_max:
            self.forward_controller_state_updates(
                {
                    "under_bed_lights_on": level > 0,
                    **({"light_timer_option": "Off"} if level == 0 else {}),
                }
            )

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option == "Off":
            await self.lights_off()
            return
        if timer_option not in self.light_timer_options:
            raise ValueError("Unsupported Woosa light timer")
        await super().set_light_timer(timer_option)
        self.forward_controller_state_updates(
            {
                "woosa_light_timer": timer_option,
                "light_timer_option": timer_option,
                "under_bed_lights_on": True,
            }
        )

    def get_massage_state(self) -> dict[str, int | str | bool]:
        state = self._coordinator.controller_state
        return {
            "head_intensity": int(state.get("woosa_head_level", 0)),
            "foot_intensity": int(state.get("woosa_foot_level", 0)),
            "timer_mode": str(state.get("woosa_massage_timer", 0)),
        }

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in {"head", "foot"} or not 0 <= level <= 3:
            raise ValueError("Woosa massage supports head/foot levels 0-3")
        commands = _HEAD_LEVELS if zone == "head" else _FOOT_LEVELS
        await self.write_command(commands[level])
        self.forward_controller_state_updates(
            {f"woosa_{zone}_level": level, f"woosa_{zone}_preference": level}
        )

    async def set_massage_mode(self, mode: int) -> None:
        if mode not in range(1, 5):
            raise ValueError("Woosa massage modes are 1-4")
        await self.write_command(_MODES[mode - 1])
        self.forward_controller_state_updates(
            {"woosa_massage_mode": mode, "woosa_mode_preference": mode}
        )

    async def massage_mode_step(self) -> None:
        await self.write_command(_MODE_STEP)

    async def _step_massage(self, zone: str, delta: int) -> None:
        """Use the manual screen's bounded, single-write adjustment path."""
        current = int(self._coordinator.controller_state.get(f"woosa_{zone}_level", 2))
        level = current + delta
        if not 0 <= level <= 3:
            return
        command = {
            ("head", 1): SolaceCommands.MASSAGE_HEAD_UP,
            ("head", -1): SolaceCommands.MASSAGE_HEAD_DOWN,
            ("foot", 1): SolaceCommands.MASSAGE_FOOT_UP,
            ("foot", -1): SolaceCommands.MASSAGE_FOOT_DOWN,
        }[zone, delta]
        await self.write_command(command)
        self.forward_controller_state_updates(
            {f"woosa_{zone}_level": level, f"woosa_{zone}_preference": level}
        )

    async def massage_head_up(self) -> None:
        await self._step_massage("head", 1)

    async def massage_head_down(self) -> None:
        await self._step_massage("head", -1)

    async def massage_foot_up(self) -> None:
        await self._step_massage("foot", 1)

    async def massage_foot_down(self) -> None:
        await self._step_massage("foot", -1)

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in {0, 10, 20, 30}:
            raise ValueError("Woosa massage timers are 10, 20 or 30 minutes")
        if minutes == 0:
            await self.massage_off()
            return
        await super().set_massage_timer(minutes)
        if self._massage_expiry_handle is not None:
            self._massage_expiry_handle.cancel()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + minutes * 60
        self._massage_expiry_handle = loop.call_later(
            minutes * 60, self._expire_massage, deadline
        )
        self.forward_controller_state_updates(
            {
                "woosa_massage_timer": minutes,
                "woosa_massage_timer_preference": minutes,
                "woosa_massage_deadline": deadline,
            }
        )

    def _expire_massage(self, deadline: float) -> None:
        state = self._coordinator.controller_state
        if state.get("woosa_massage_deadline") != deadline:
            return
        self._massage_expiry_handle = None
        self.forward_controller_state_updates(
            {
                "woosa_massage_active": False,
                "woosa_massage_timer": 0,
                "woosa_massage_deadline": None,
                "woosa_head_level": 0,
                "woosa_foot_level": 0,
            }
        )

    async def massage_off(self) -> None:
        await super().massage_off()
        if self._massage_expiry_handle is not None:
            self._massage_expiry_handle.cancel()
            self._massage_expiry_handle = None
        self.forward_controller_state_updates(
            {
                "woosa_massage_active": False,
                "woosa_massage_timer": 0,
                "woosa_massage_deadline": None,
                "woosa_head_level": 0,
                "woosa_foot_level": 0,
            }
        )

    async def massage_toggle(self) -> None:
        state = self._coordinator.controller_state
        if state.get("woosa_massage_active", False):
            await self.massage_off()
            return
        # Proven MassageActivity route; keep preferences independent per zone.
        head = int(state.get("woosa_head_preference", 2))
        foot = int(state.get("woosa_foot_preference", 2))
        mode = int(state.get("woosa_mode_preference", 2))
        timer = int(state.get("woosa_massage_timer_preference", 10))
        try:
            await self.massage_off()
            await asyncio.sleep(0.4)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_timer(timer)
            await asyncio.sleep(0.4)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_intensity("head", head)
            await asyncio.sleep(0.4)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_intensity("foot", foot)
            await asyncio.sleep(0.4)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_mode(mode)
            self.forward_controller_state_updates({"woosa_massage_active": bool(head or foot)})
        except Exception, asyncio.CancelledError:
            try:
                await self.write_command(SolaceCommands.MASSAGE_STOP, cancel_event=asyncio.Event())
                if self._massage_expiry_handle is not None:
                    self._massage_expiry_handle.cancel()
                    self._massage_expiry_handle = None
                self.forward_controller_state_updates(
                    {
                        "woosa_massage_active": False,
                        "woosa_massage_timer": 0,
                        "woosa_massage_deadline": None,
                        "woosa_head_level": 0,
                        "woosa_foot_level": 0,
                    }
                )
            except BleakError, ConnectionError:
                _LOGGER.debug("Could not stop interrupted Woosa massage sequence")
            raise

    async def program_solace_alarm(
        self,
        *,
        enabled: bool,
        hour: int,
        minute: int,
        weekdays: Collection[int],
        mode: str,
        massage: bool,
        sound: str,
    ) -> None:
        if sound not in {"none", "alarm"}:
            raise ValueError("Woosa supports alarm sound on/off, not music tracks")
        # Only proven UI choices are writable; raw received mode remains diagnostic.
        await self.write_command(
            build_solace_alarm_command(
                enabled=enabled,
                hour=hour,
                minute=minute,
                weekdays=weekdays,
                mode=mode,
                massage=massage,
                sound=sound,
            )
        )
        await self.write_command(_ALARM_QUERY)

    def _parse_notification(self, data: bytes) -> None:
        updates: dict[str, bool | int | str] = {}
        for selector, key in ((0x0A, "memory_1"), (0x0F, "love"), (0x05, "tv"), (0x09, "zero_g")):
            if data.startswith(bytes.fromhex("FFFFFFFF030600") + bytes([selector])):
                updates[f"solace_{key}_selected"] = True
        for zone, frames in _MASSAGE_REPLIES.items():
            if (
                bytes.fromhex("FFFFFFFF050000") + bytes([{"head": 1, "foot": 2, "mode": 3}[zone]])
                not in data
            ):
                continue
            for level, frame in enumerate(frames):
                if frame in data:
                    key = "woosa_massage_mode" if zone == "mode" else f"woosa_{zone}_level"
                    updates[key] = level + (zone == "mode")
                    break
            break  # The app's outer zone predicates are mutually exclusive.
        if "woosa_head_level" in updates or "woosa_foot_level" in updates:
            current = self._coordinator.controller_state
            updates["woosa_massage_active"] = bool(
                updates.get("woosa_head_level", current.get("woosa_head_level", 0))
                or updates.get("woosa_foot_level", current.get("woosa_foot_level", 0))
            )
        # The app treats arbitrary control/massage replies as light brightness.
        # Keep its candidate diagnostic only; it cannot establish physical state.
        if bytes.fromhex("FFFFFFFF0500") in data and len(data) > 7:
            updates["woosa_light_candidate"] = data[7]
        if data.startswith(bytes.fromhex("FFFFFFFF0100030B00")):
            updates.update(
                {
                    "solace_alarm_enabled": False,
                    "solace_alarm_time": "00:00",
                    "solace_alarm_weekdays": "",
                    "solace_alarm_mode": "no_action",
                    "solace_alarm_massage": False,
                    "solace_alarm_sound": "none",
                }
            )
        elif data.startswith(bytes.fromhex("FFFFFFFF01000413")) and len(data) >= 17:
            updates.update(
                {
                    "solace_alarm_enabled": data[8] == 0x0F,
                    "solace_alarm_time": f"{data[9]:02x}:{data[10]:02x}",
                    "solace_alarm_weekdays": ",".join(
                        str(day) for day in range(1, 8) if data[12] & (1 << day)
                    ),
                    "solace_alarm_mode": {1: "zero_g", 2: "memory_1", 3: "no_action"}.get(
                        data[14], f"unknown_{data[14]:02x}"
                    ),
                    "solace_alarm_massage": data[15] == 1,
                    "solace_alarm_sound": "alarm" if data[16] == 1 else "none",
                }
            )
        if updates:
            self.forward_controller_state_updates(updates)
