"""Explicit Woosa Sleep profile, verified against com.sn.woosa 1.1.9.

The shared discovery names cannot identify the app. Only an explicit profile
selects these commands. Evidence: the accepted com.sn.woosa 1.1.9 audit (issue
#606), including intentional differences from the Android UI.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Collection
from functools import partial
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..controller_state import StateKey, StateUpdate
from ..profiles.ff_frame import (
    SOLACE_PROFILES,
    WOOSA_ALARM_QUERY,
    WOOSA_FOOT_LEVELS,
    WOOSA_HEAD_LEVELS,
    WOOSA_LIGHT_OFF,
    WOOSA_MASSAGE_REPLIES,
    WOOSA_MODE_STEP,
    WOOSA_MODES,
    WOOSA_PRESET_QUERIES,
    WOOSA_SAVES,
    WOOSA_STARTUP,
    SolaceProfile,
)
from ..state_keys import (
    LIGHT_TIMER_OPTION,
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    massage_intensity,
)
from .base import BedController, ControllerButtonSpec
from .solace.controller import (
    ALARM_ENABLED,
    ALARM_MASSAGE,
    ALARM_MODE,
    ALARM_SOUND,
    ALARM_TIME,
    ALARM_WEEKDAYS,
    SolaceCommands,
    SolaceController,
    build_solace_alarm_command,
    build_solace_clock_command,
    preset_selected,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

LIGHT_TIMER: Final = StateKey[str]("woosa_light_timer")
LIGHT_DEADLINE: Final = StateKey[float | None]("woosa_light_deadline")
LIGHT_CANDIDATE: Final = StateKey[int]("woosa_light_candidate")
MASSAGE_ACTIVE: Final = StateKey[bool]("woosa_massage_active")
MASSAGE_MODE: Final = StateKey[int]("woosa_massage_mode")
MODE_PREFERENCE: Final = StateKey[int]("woosa_mode_preference")
MASSAGE_TIMER_PREFERENCE: Final = StateKey[int]("woosa_massage_timer_preference")
MASSAGE_DEADLINE: Final = StateKey[float | None]("woosa_massage_deadline")


def _preference(zone: str) -> StateKey[int]:
    return StateKey[int](f"woosa_{zone}_preference")


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
        return SOLACE_PROFILES["woosa"]
    @property
    def supports_preset_anti_snore(self) -> bool:
        # Keep the app-specific action separate from the generic anti-snore capability.
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def light_auto_off_seconds(self) -> int | None:
        option = self._coordinator.controller_state.get(LIGHT_TIMER_OPTION)
        if option is None:
            return None
        duration = {
            "10 min": 10 * 60,
            "8 hours": 8 * 60 * 60,
            "10 hours": 10 * 60 * 60,
        }.get(option)
        deadline = self._coordinator.controller_state.get(LIGHT_DEADLINE)
        if duration is None or deadline is None:
            return None
        return max(0, math.ceil(deadline - asyncio.get_running_loop().time()))

    def on_light_auto_off(self) -> None:
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(False), LIGHT_TIMER_OPTION("Off"), LIGHT_DEADLINE(None)
        )

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
    def solace_alarm_sound_options(self) -> tuple[str, ...]:
        return ("none", "alarm")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = (
            ("love", "Anti-Snore"),
            ("save_love", "Save Anti-Snore position"),
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
                *(preset_selected(key)(False) for key in WOOSA_SAVES)
            )
            # Preserve each worker's offsets; serialize coincident writes.
            previous = 0
            for offset, command in WOOSA_STARTUP:
                await asyncio.sleep((offset - previous) / 1000)
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
        await asyncio.sleep(self.profile.preset_preamble_ms / 1000)
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
        await self.write_command(WOOSA_SAVES[key])
        # The app re-queries after saving; only replies establish saved state.
        for command in WOOSA_PRESET_QUERIES:
            await asyncio.sleep(self.profile.save_requery_ms / 1000)
            await self.write_command(command)

    async def preset_love(self) -> None:
        await self._send_preset(
            SolaceCommands.PRESET_ANTI_SNORE_SELECTED
            if self._preset_is_selected("love")
            else SolaceCommands.PRESET_ANTI_SNORE
        )

    async def lights_on(self) -> None:
        await self.set_light_timer(self._coordinator.controller_state.get(LIGHT_TIMER, "10 min"))

    async def lights_off(self) -> None:
        await self.write_command(WOOSA_LIGHT_OFF)
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(False), LIGHT_TIMER_OPTION("Off"), LIGHT_DEADLINE(None)
        )

    async def set_light_level(self, level: int) -> None:
        await super().set_light_level(level)
        if 0 <= level <= self.light_level_max:
            self.forward_controller_state_updates(
                UNDER_BED_LIGHTS_ON(level > 0),
                *((LIGHT_TIMER_OPTION("Off"), LIGHT_DEADLINE(None)) if level == 0 else ()),
            )

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option == "Off":
            await self.lights_off()
            return
        if timer_option not in self.light_timer_options:
            raise ValueError("Unsupported Woosa light timer")
        await super().set_light_timer(timer_option)
        duration = {"10 min": 600, "8 hours": 28800, "10 hours": 36000}[timer_option]
        self.forward_controller_state_updates(
            LIGHT_TIMER(timer_option),
            LIGHT_TIMER_OPTION(timer_option),
            UNDER_BED_LIGHTS_ON(True),
            LIGHT_DEADLINE(asyncio.get_running_loop().time() + duration),
        )

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in {"head", "foot"} or not 0 <= level <= 3:
            raise ValueError("Woosa massage supports head/foot levels 0-3")
        commands = WOOSA_HEAD_LEVELS if zone == "head" else WOOSA_FOOT_LEVELS
        await self.write_command(commands[level])
        self._publish_massage_level(zone, level)

    def _publish_massage_level(self, zone: str, level: int) -> None:
        other_zone = "foot" if zone == "head" else "head"
        other_level = self._coordinator.controller_state.get(massage_intensity(other_zone))
        self.forward_controller_state_updates(
            massage_intensity(zone)(level),
            _preference(zone)(level),
            MASSAGE_ACTIVE(bool(level or other_level)),
        )

    async def set_massage_mode(self, mode: int) -> None:
        if mode not in range(1, 5):
            raise ValueError("Woosa massage modes are 1-4")
        await self.write_command(WOOSA_MODES[mode - 1])
        self.forward_controller_state_updates(MASSAGE_MODE(mode), MODE_PREFERENCE(mode))

    async def massage_mode_step(self) -> None:
        await self.write_command(WOOSA_MODE_STEP)

    async def _step_massage(self, zone: str, delta: int) -> None:
        """Use the manual screen's bounded, single-write adjustment path."""
        current = self._coordinator.controller_state.get(massage_intensity(zone), 2) or 0
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
        self._publish_massage_level(zone, level)

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
            MASSAGE_TIMER_MINUTES(minutes),
            MASSAGE_TIMER_PREFERENCE(minutes),
            MASSAGE_DEADLINE(deadline),
        )

    def _expire_massage(self, deadline: float) -> None:
        state = self._coordinator.controller_state
        if state.get(MASSAGE_DEADLINE) != deadline:
            return
        self._massage_expiry_handle = None
        self._publish_massage_stopped()

    async def massage_off(self) -> None:
        await super().massage_off()
        if self._massage_expiry_handle is not None:
            self._massage_expiry_handle.cancel()
            self._massage_expiry_handle = None
        self._publish_massage_stopped()

    def _publish_massage_stopped(self) -> None:
        self.forward_controller_state_updates(
            MASSAGE_ACTIVE(False),
            MASSAGE_TIMER_MINUTES(0),
            MASSAGE_DEADLINE(None),
            massage_intensity("head")(0),
            massage_intensity("foot")(0),
        )

    async def massage_toggle(self) -> None:
        state = self._coordinator.controller_state
        if state.get(MASSAGE_ACTIVE, False):
            await self.massage_off()
            return
        # Proven MassageActivity route; keep preferences independent per zone.
        head = state.get(_preference("head"), 2)
        foot = state.get(_preference("foot"), 2)
        mode = state.get(MODE_PREFERENCE, 2)
        timer = state.get(MASSAGE_TIMER_PREFERENCE, 10)
        try:
            await self.massage_off()
            await asyncio.sleep(self.profile.massage_step_ms / 1000)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_timer(timer)
            await asyncio.sleep(self.profile.massage_step_ms / 1000)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_intensity("head", head)
            await asyncio.sleep(self.profile.massage_step_ms / 1000)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_intensity("foot", foot)
            await asyncio.sleep(self.profile.massage_step_ms / 1000)
            if self._coordinator.cancel_command.is_set():
                raise asyncio.CancelledError
            await self.set_massage_mode(mode)
            self.forward_controller_state_updates(MASSAGE_ACTIVE(bool(head or foot)))
        except Exception, asyncio.CancelledError:
            try:
                await self.write_command(SolaceCommands.MASSAGE_STOP, cancel_event=asyncio.Event())
                if self._massage_expiry_handle is not None:
                    self._massage_expiry_handle.cancel()
                    self._massage_expiry_handle = None
                self._publish_massage_stopped()
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
        await self.write_command(WOOSA_ALARM_QUERY)

    def _parse_notification(self, data: bytes) -> None:
        updates: list[StateUpdate] = []
        for selector, key in ((0x0A, "memory_1"), (0x0F, "love"), (0x05, "tv"), (0x09, "zero_g")):
            if data.startswith(bytes.fromhex("FFFFFFFF030600") + bytes([selector])):
                updates.append(preset_selected(key)(True))
        levels: dict[str, int] = {}
        for zone, frames in WOOSA_MASSAGE_REPLIES.items():
            if (
                bytes.fromhex("FFFFFFFF050000") + bytes([{"head": 1, "foot": 2, "mode": 3}[zone]])
                not in data
            ):
                continue
            for level, frame in enumerate(frames):
                if frame in data:
                    if zone == "mode":
                        updates.append(MASSAGE_MODE(level + 1))
                    else:
                        levels[zone] = level
                        updates.append(massage_intensity(zone)(level))
                    break
            break  # The app's outer zone predicates are mutually exclusive.
        if levels:
            current = self._coordinator.controller_state
            updates.append(
                MASSAGE_ACTIVE(
                    bool(
                        levels.get("head", current.get(massage_intensity("head"), 0))
                        or levels.get("foot", current.get(massage_intensity("foot"), 0))
                    )
                )
            )
        # The app treats arbitrary control/massage replies as light brightness.
        # Keep its candidate diagnostic only; it cannot establish physical state.
        if bytes.fromhex("FFFFFFFF0500") in data and len(data) > 7:
            updates.append(LIGHT_CANDIDATE(data[7]))
        if data.startswith(bytes.fromhex("FFFFFFFF0100030B00")):
            updates += [
                ALARM_ENABLED(False),
                ALARM_TIME("00:00"),
                ALARM_WEEKDAYS(""),
                ALARM_MODE("no_action"),
                ALARM_MASSAGE(False),
                ALARM_SOUND("none"),
            ]
        elif data.startswith(bytes.fromhex("FFFFFFFF01000413")) and len(data) >= 17:
            updates += [
                ALARM_ENABLED(data[8] == 0x0F),
                ALARM_TIME(f"{data[9]:02x}:{data[10]:02x}"),
                ALARM_WEEKDAYS(
                    ",".join(str(day) for day in range(1, 8) if data[12] & (1 << day))
                ),
                ALARM_MODE(
                    {1: "zero_g", 2: "memory_1", 3: "no_action"}.get(
                        data[14], f"unknown_{data[14]:02x}"
                    )
                ),
                ALARM_MASSAGE(data[15] == 1),
                ALARM_SOUND("alarm" if data[16] == 1 else "none"),
            ]
        if updates:
            self.forward_controller_state_updates(*updates)
