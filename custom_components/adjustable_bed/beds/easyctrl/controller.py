"""EasyCtrl's model catalog, gestures and settings on the shared P1 session."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ...alarm import AlarmCapability, AlarmRequest
from ...app_session import app_session
from ...card import CARD_LIGHTING, CARD_MASSAGE
from ...codec import cheerssleep as carrier
from ...codec import easyctrl as codec
from ...command_scheduler import Delivery, delivered, note_frame_skipped
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey, StateUpdate
from ...errors import invalid
from ...profiles import easyctrl as app
from ...state_keys import (
    LIGHT_LEVEL,
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
)
from ..base import ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from ..syndata import Link, SynDataController
from .transport import select_link

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MODES = {zone: StateKey[str | None](f"easyctrl_{zone}_mode") for zone in ("head", "all", "foot")}
POWER = {zone: StateKey[int | None](f"easyctrl_{zone}_power") for zone in MODES}
SLEEP_MINUTES = StateKey[int | None]("easyctrl_sleep_minutes")
SWING = StateKey[bool | None]("easyctrl_swing")
SLEEP = StateKey[bool | None]("easyctrl_sleep")
SWING_TIMER = StateKey[str | None]("easyctrl_swing_timer")


@dataclass(slots=True)
class LocalState:
    counters: codec.Counters = field(default_factory=codec.Counters)
    rgb: tuple[int, int, int] = (255, 255, 255)
    brightness: int = 128
    packed: int = -128
    minutes: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MODES, 10))
    zone: str = "all"
    sleep_minutes: int = 1
    modes: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MODES, 1))
    powers: dict[str, int] = field(default_factory=lambda: dict.fromkeys(MODES, 1))


class EasyCtrlController(ProfileExecution[app.EasyCtrlProfile], SynDataController):
    write_response = False
    settle_writes = True

    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.EasyCtrlProfile) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._link = None
        self.local = app_session(
            coordinator.hass,
            coordinator.address,
            ("easyctrl", str(profile.key)),
            lambda: LocalState(zone="head" if profile.key == 124 else "all"),
        )
        self._raw_state: dict[str, int | str] = {}
        self.forward_controller_state_updates(SLEEP_MINUTES(self.local.sleep_minutes))

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def control_characteristic_uuid(self) -> str:
        return carrier.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return self.profile.key not in (14, 16, 123)

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self.profile.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.profile.presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.profile.presets

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.profile.memory)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self.profile.memory)

    @property
    def supports_massage(self) -> bool:
        return self.profile.massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.profile.massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.profile.massage

    @property
    def supports_lights(self) -> bool:
        return self.profile.light

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self.profile.light

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.light and self.profile.key != 14

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.profile.key == 324

    @property
    def supports_light_color_control(self) -> bool:
        return self.profile.rgb

    @property
    def publishes_rgb_light_state(self) -> bool:
        return self.profile.rgb

    @property
    def supports_light_level_control(self) -> bool:
        return self.profile.rgb

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.profile.rgb else None

    @property
    def light_level_max(self) -> int:
        return 255

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int]:
        return self.local.rgb

    @property
    def light_intensity(self) -> int:
        return self.local.brightness

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "model": self.profile.key,
            "page": self.profile.page,
            "status": dict(self._raw_state),
        }

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.controller is self
        )

    @contextmanager
    def _sent(
        self, *updates: StateUpdate, commit: Callable[[], None] | None = None
    ) -> Iterator[None]:
        link = self._live()

        def committed(delivery: Delivery) -> None:
            if delivery is Delivery.SENT and self._current(link) and commit is not None:
                commit()

        with (
            self.sent_state(*updates, is_current=lambda: self._current(link)),
            delivered(committed),
        ):
            yield

    async def _control(
        self,
        code: int,
        value: int = 0,
        *,
        link: Link | None = None,
        cached: bool = False,
        cleanup: bool = False,
    ) -> None:
        captured = self._live(link)
        frame = self.local.counters.control(code, value, cached=cached)
        if not cleanup and self._coordinator.cancel_command.is_set():
            note_frame_skipped()
            raise asyncio.CancelledError
        await self._send(frame, captured, cleanup=cleanup)
        if not cleanup and self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError

    async def _stops(
        self,
        link: Link,
        code: int = 1,
        *,
        cached: bool = False,
        primary_error: BaseException | None = None,
    ) -> None:
        async def release() -> None:
            start = monotonic()
            failures: list[Exception] = []
            for at in self.profile.release_ms:
                await asyncio.sleep(max(0, start + at / 1000 - monotonic()))
                if not self._current(link):
                    note_frame_skipped()
                    break
                try:
                    await self._control(code, link=link, cached=cached, cleanup=True)
                except (BleakError, ConnectionError, TimeoutError) as error:
                    failures.append(error)
            if failures:
                first = failures[0]
                for failure in failures[1:]:
                    first.add_note(f"Another EasyCtrl STOP failed: {failure!r}")
                raise first

        try:
            await settled(release())
        except BaseException as error:
            if primary_error is None:
                raise
            primary_error.add_note(f"EasyCtrl STOP cleanup also failed: {error!r}")

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        if (
            motor not in {axis.key for axis in self.profile.axes}
            or direction not in ("up", "down")
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 30000
        ):
            raise invalid("easyctrl_control")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid("easyctrl_control")
        key, direction = control.rsplit("_", 1)
        self.validate_timed_movement(key, direction, duration_ms)

    async def move_axis(
        self, key: str, up: bool, duration_ms: int | None = None, *, flat_tap: bool = False
    ) -> None:
        try:
            axis = self.profile.axis(key)
        except StopIteration:
            raise invalid("easyctrl_control") from None
        duration = (
            duration_ms
            if duration_ms is not None
            else max(1, self._coordinator.motor_pulse_count) * self.profile.refresh_ms
        )
        self.validate_timed_movement(key, "up" if up else "down", duration)
        link, cancel = self._live(), self._coordinator.cancel_command
        duration = self.leased_hold_ms(duration)
        next_at = monotonic()
        deadline, completed = next_at + duration / 1000, False
        try:
            while not cancel.is_set():
                await self._control(
                    axis.up if up else axis.down, link=link, cached=self.profile.stream
                )
                next_at += self.profile.refresh_ms / 1000
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                await cancellable(
                    asyncio.sleep(
                        max(0, min(deadline, next_at) - monotonic())
                        if self.profile.stream
                        else remaining
                    ),
                    cancel,
                )
                if monotonic() >= deadline:
                    break
            completed = not cancel.is_set()
        finally:
            if (
                flat_tap
                and completed
                and self.profile.flat_keep
                and duration <= self.profile.flat_threshold_ms
            ):
                # Only a successful explicit Flat tap may leave travel running.
                try:
                    for _ in range(3):
                        await cancellable(asyncio.sleep(self.profile.keep_delay_ms / 1000), cancel)
                        await self._control(3, cached=True, link=link)
                except BaseException:
                    await self._stops(link, primary_error=sys.exception())
                    raise
            elif not (
                flat_tap
                and completed
                and self.profile.flat_latched
                and duration <= self.profile.flat_threshold_ms
            ):
                cached = self.profile.stream and (
                    up or not key.endswith("all") or self.profile.key == 324
                )
                await self._stops(link, axis.stop, cached=cached, primary_error=sys.exception())

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis.key,
                f"easyctrl_{axis.key}",
                lambda ctrl, key=axis.key: require_controller(ctrl, EasyCtrlController).move_axis(
                    key, True
                ),
                lambda ctrl, key=axis.key: require_controller(ctrl, EasyCtrlController).move_axis(
                    key, False
                ),
                lambda ctrl: ctrl.stop_all(),
                hold=ControllerMotorHoldSpec(
                    f"{axis.key}_up", f"{axis.key}_down", press_hold_ms=None, stop_scope="side"
                ),
                stop_scope="side",
                timed_move_fn=lambda ctrl, up, ms, key=axis.key: require_controller(
                    ctrl, EasyCtrlController
                ).move_axis(key, up, ms),
            )
            for axis in self.profile.axes
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis.key}_{direction}" for axis in self.profile.axes for direction in ("up", "down")
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        key, direction = control.rsplit("_", 1)
        await self.move_axis(key, direction == "up", duration_ms)

    async def move_head_up(self) -> None:
        await self.move_axis(
            "back_head" if any(a.key == "back_head" for a in self.profile.axes) else "head", True
        )

    async def move_head_down(self) -> None:
        await self.move_axis(
            "back_head" if any(a.key == "back_head" for a in self.profile.axes) else "head", False
        )

    async def move_back_up(self) -> None:
        await self.move_axis(
            "back_head" if any(a.key == "back_head" for a in self.profile.axes) else "back", True
        )

    async def move_back_down(self) -> None:
        await self.move_axis(
            "back_head" if any(a.key == "back_head" for a in self.profile.axes) else "back", False
        )

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        await self._stops(self._live())

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        if not self.supports_preset_flat:
            raise invalid("easyctrl_control")
        await self.move_axis(
            self.profile.axes[0].key, False, self.profile.flat_tap_ms, flat_tap=True
        )

    async def _preset(self, name: str) -> None:
        if name not in self.profile.presets:
            raise invalid("easyctrl_control")
        await self._control(app.PRESET_CODES[name])

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._control(app.MEMORY_RECALL[memory_num - 1])

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._control(app.MEMORY_SAVE[memory_num - 1])

    async def lights_on(self) -> None:
        if not self.supports_lights:
            raise invalid("easyctrl_control")
        with self._sent(UNDER_BED_LIGHTS_ON(True)):
            await self._control(
                app.CONTROL_CODES["light_on"], 0 if self.profile.key == 14 else self.local.packed
            )

    async def lights_off(self) -> None:
        if not self.supports_discrete_light_control:
            raise invalid("easyctrl_control")
        with self._sent(UNDER_BED_LIGHTS_ON(False)):
            await self._control(app.CONTROL_CODES["light_off"], self.local.packed)

    async def set_light_color_with_level(self, rgb_color: tuple[int, int, int], level: int) -> None:
        if (
            not self.profile.rgb
            or len(rgb_color) != 3
            or any(type(v) is not int or not 0 <= v <= 255 for v in (*rgb_color, level))
        ):
            raise invalid("easyctrl_control")
        packed = carrier.rgb_parameter(*rgb_color, level)
        link = self._live()

        def commit() -> None:
            self.local.rgb, self.local.brightness, self.local.packed = rgb_color, level, packed

        with self._sent(
            UNDER_BED_LIGHTS_RGB(rgb_color),
            LIGHT_LEVEL(level),
            UNDER_BED_LIGHTS_ON(True),
            commit=commit,
        ):
            await self._control(app.CONTROL_CODES["light_on"], packed, link=link)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self.set_light_color_with_level(rgb_color, self.local.brightness)

    async def set_light_level(self, level: int) -> None:
        await self.set_light_color_with_level(self.local.rgb, level)

    async def save_light(self) -> None:
        if not self.profile.rgb:
            raise invalid("easyctrl_control")
        link, packed = self._live(), self.local.packed
        await self._send(self.local.counters.setting(app.CONTROL_CODES["light_delay"], 10), link)
        await cancellable(
            asyncio.sleep(self.profile.setting_delay_ms / 1000), self._coordinator.cancel_command
        )
        await self._control(app.CONTROL_CODES["light_save"], packed, link=link)

    @property
    def supports_massage_timer(self) -> bool:
        return self.profile.massage

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def massage_timer_is_assumed(self) -> bool:
        return True

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.profile.massage or minutes not in (0, 10, 20, 30):
            raise invalid("easyctrl_control")
        if not minutes:
            await self.massage_off()
            return
        zone = self.local.zone
        await self.massage_mode(zone, self.local.modes[zone], minutes=minutes)

    async def massage_off(self) -> None:
        if not self.profile.massage:
            raise invalid("easyctrl_control")
        with self._sent(*(key("off") for key in MODES.values()), MASSAGE_TIMER_MINUTES(0)):
            await self._control(app.CONTROL_CODES["massage_stop"])

    async def massage_mode(self, zone: str, mode: int, *, minutes: int | None = None) -> None:
        if not self.profile.massage or zone not in MODES or mode not in (0, 1, 2, 3):
            raise invalid("easyctrl_control")
        if not mode:
            await self.massage_off()
            return
        link = self._live()
        selected_minutes = self.local.minutes[zone] if minutes is None else minutes
        if selected_minutes not in self.massage_timer_options:
            raise invalid("easyctrl_control")
        if self.profile.page == "Bed8BtnActivity":
            with self._sent(*(key("off") for key in MODES.values()), MASSAGE_TIMER_MINUTES(0)):
                await self._control(app.CONTROL_CODES["massage_stop"], link=link)
            await cancellable(
                asyncio.sleep(self.profile.setting_delay_ms / 1000),
                self._coordinator.cancel_command,
            )

        def commit() -> None:
            self.local.zone = zone
            self.local.modes[zone], self.local.minutes[zone] = mode, selected_minutes

        with self._sent(
            *(key(f"mode_{mode}" if other == zone else "off") for other, key in MODES.items()),
            MASSAGE_TIMER_MINUTES(selected_minutes),
            commit=commit,
        ):
            await self._control(
                app.MASSAGE_MODES[zone][mode - 1],
                selected_minutes * 60,
                link=link,
            )
        await cancellable(
            asyncio.sleep(self.profile.setting_delay_ms / 1000), self._coordinator.cancel_command
        )
        await self.massage_power(zone, self.local.powers[zone], link=link)

    async def massage_power(self, zone: str, level: int, *, link: Link | None = None) -> None:
        if not self.profile.massage or zone not in POWER or level not in (1, 2, 3):
            raise invalid("easyctrl_control")

        def commit() -> None:
            self.local.powers[zone] = level

        with self._sent(POWER[zone](level), commit=commit):
            await self._control(app.MASSAGE_POWER[zone], app.POWER_VALUES[level - 1], link=link)

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        return (
            AlarmCapability(weekdays=True, wake_actions=("none", "backrest"), massage=True)
            if self.profile.alarm
            else None
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        super().validate_alarm(alarm)
        if alarm.enabled and not alarm.weekdays:
            raise invalid("easyctrl_alarm_repeat")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link = self._live()
        if not alarm.enabled:
            await self._control(app.CONTROL_CODES["wakeup_delete"], link=link)
            return
        seconds, mask = codec.alarm_values(
            alarm.hour, alarm.minute, alarm.weekdays, alarm.reference_time
        )
        motor = alarm.wake_action == "backrest"
        mode = 4 if motor and alarm.massage else 2 if motor else 1 if alarm.massage else 0
        await self._control(app.CONTROL_CODES["wakeup_countdown"], seconds, link=link)
        await cancellable(
            asyncio.sleep(self.profile.alarm_delay_ms / 1000), self._coordinator.cancel_command
        )
        await self._control(app.CONTROL_CODES["wakeup_action"], mode | mask << 8, link=link)

    async def sleep_timer(self, enabled: bool) -> None:
        if not self.profile.alarm:
            raise invalid("easyctrl_control")
        link = self._live()
        with self._sent(SLEEP(enabled)):
            if enabled:
                await self._control(
                    app.CONTROL_CODES["sleep_countdown"], self.local.sleep_minutes * 60, link=link
                )
                await cancellable(
                    asyncio.sleep(self.profile.alarm_delay_ms / 1000),
                    self._coordinator.cancel_command,
                )
                await self._control(app.CONTROL_CODES["sleep_action"], 3, link=link)
            else:
                await self._control(app.CONTROL_CODES["sleep_delete"], link=link)

    async def set_sleep_minutes(self, value: float) -> None:
        if not self.profile.alarm or not value.is_integer() or not 1 <= value <= 120:
            raise invalid("easyctrl_control")
        self.local.sleep_minutes = int(value)
        self.forward_controller_state_updates(SLEEP_MINUTES(int(value)))

    async def swing(self, enabled: bool) -> None:
        if self.profile.key != 124:
            raise invalid("easyctrl_control")
        with self._sent(SWING(enabled)):
            await self._control(
                app.CONTROL_CODES["swing_on"] if enabled else app.CONTROL_CODES["swing_off"]
            )

    async def swing_time(self, value: str) -> None:
        if self.profile.key != 124 or value not in ("10", "20", "30"):
            raise invalid("easyctrl_control")
        with self._sent(SWING_TIMER(value)):
            await self._control(app.SWING_TIMERS[value])

    async def action(self, key: str) -> None:
        allowed = {"sleep"} if self.profile.key in (124, 312, 324) else set()
        if self.profile.key == 312:
            allowed |= {"sleep_left", "sleep_right"}
        if self.profile.key == 124:
            allowed |= {"swing_up", "swing_down"}
        if key not in allowed:
            raise invalid("easyctrl_control")
        await self._control(app.ACTION_CODES[key])

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = [("sleep", "Automatic sleep")] if self.profile.key in (124, 312, 324) else []
        if self.profile.key == 312:
            actions += [
                ("sleep_left", "Left automatic sleep"),
                ("sleep_right", "Right automatic sleep"),
            ]
        if self.profile.key == 124:
            actions += [("swing_up", "Increase swing"), ("swing_down", "Decrease swing")]
        result = []
        for key, label in actions:
            spec = catalog_button(
                f"easyctrl_{key}",
                label,
                lambda ctrl, key=key: require_controller(ctrl, EasyCtrlController).action(key),
                kind=Kind.PRESET if key.startswith("sleep") else Kind.MASSAGE,
            )
            if spec:
                result.append(spec)
        if self.profile.key == 14:
            spec = catalog_button(
                "easyctrl_light_on", "Light on", lambda ctrl: ctrl.lights_on(), kind=Kind.LIGHT
            )
            if spec:
                result.append(spec)
        if self.profile.rgb:
            result.append(
                ControllerButtonSpec(
                    "easyctrl_save_light",
                    "Save light settings",
                    lambda ctrl: require_controller(ctrl, EasyCtrlController).save_light(),
                    translation_key="easyctrl_save_light",
                    requires_confirmation=True,
                    card=CARD_LIGHTING,
                )
            )
        return tuple(result)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs = (
            [
                ControllerSelectSpec(
                    f"easyctrl_{zone}_mode",
                    f"easyctrl_{zone}_mode",
                    MODES[zone],
                    ("off", "mode_1", "mode_2", "mode_3"),
                    lambda ctrl, value, zone=zone: require_controller(
                        ctrl, EasyCtrlController
                    ).massage_mode(zone, 0 if value == "off" else int(value[-1])),
                    card=CARD_MASSAGE,
                )
                for zone in MODES
            ]
            if self.profile.massage
            else []
        )
        if self.profile.key == 124:
            specs.append(
                ControllerSelectSpec(
                    "easyctrl_swing_timer",
                    "easyctrl_swing_timer",
                    SWING_TIMER,
                    ("10", "20", "30"),
                    lambda ctrl, value: require_controller(ctrl, EasyCtrlController).swing_time(
                        value
                    ),
                    card=CARD_MASSAGE,
                )
            )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = (
            [
                ControllerNumberSpec(
                    f"easyctrl_{zone}_power",
                    f"easyctrl_{zone}_power",
                    POWER[zone],
                    1,
                    3,
                    1,
                    lambda ctrl, value, zone=zone: require_controller(
                        ctrl, EasyCtrlController
                    ).massage_power(zone, int(value)),
                    assumed_state=True,
                    card=CARD_MASSAGE,
                )
                for zone in POWER
            ]
            if self.profile.massage
            else []
        )
        if self.profile.alarm:
            specs.append(
                ControllerNumberSpec(
                    "easyctrl_sleep_minutes",
                    "easyctrl_sleep_minutes",
                    SLEEP_MINUTES,
                    1,
                    120,
                    1,
                    lambda ctrl, value: require_controller(
                        ctrl, EasyCtrlController
                    ).set_sleep_minutes(float(value)),
                    native_unit_of_measurement="min",
                    assumed_state=True,
                )
            )
        return tuple(specs)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        specs = []
        if self.profile.alarm:
            specs.append(
                ControllerSwitchSpec(
                    "easyctrl_sleep",
                    "easyctrl_sleep",
                    lambda ctrl, enabled: require_controller(ctrl, EasyCtrlController).sleep_timer(
                        enabled
                    ),
                    SLEEP,
                    assumed_state=True,
                )
            )
        if self.profile.key == 124:
            specs.append(
                ControllerSwitchSpec(
                    "easyctrl_swing",
                    "easyctrl_swing",
                    lambda ctrl, enabled: require_controller(ctrl, EasyCtrlController).swing(
                        enabled
                    ),
                    SWING,
                    assumed_state=True,
                    card=CARD_MASSAGE,
                )
            )
        return tuple(specs)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()
        if self.profile.key == 324:
            link = self._live()
            await cancellable(
                asyncio.sleep(self.profile.query_delay_ms / 1000), self._coordinator.cancel_command
            )
            await self._send(self.local.counters.query(app.CONTROL_CODES["light_query"]), link)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("EasyCtrl is disconnected")
        link = select_link(client)
        self._link = link
        try:
            await client.start_notify(
                link.notify, lambda sender, data: self._receive(link, carrier.NOTIFY, data)
            )
            self._live(link)
            if {"notify", "indicate"}.intersection(link.write.properties):
                await client.start_notify(
                    link.write, lambda sender, data: self._receive(link, carrier.WRITE, data)
                )
                self._live(link)
        except BaseException:
            self.on_disconnect()
            raise

    def _receive(self, link: Link, uuid: str, data: bytearray) -> None:
        if (
            self._link is not link
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
        ):
            return
        self.forward_raw_notification(uuid, bytes(data))
        if parsed := codec.parse(bytes(data)):
            event, value = parsed
            self._raw_state[event] = value
            if self.profile.key == 324 and event in ("led_status_1", "led_status_2"):
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(value == 1))

    def on_disconnect(self) -> None:
        self._link = None
        self._raw_state.clear()
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
            LIGHT_LEVEL(None),
            SLEEP(None),
            SWING(None),
            SWING_TIMER(None),
            MASSAGE_TIMER_MINUTES(None),
            *(key(None) for key in (*MODES.values(), *POWER.values())),
        )

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link and self.client is link.client and link.client.is_connected:
            await link.client.stop_notify(link.notify)
            if {"notify", "indicate"}.intersection(link.write.properties):
                await link.client.stop_notify(link.write)


async def build_controller(ctx: BuildContext) -> EasyCtrlController:
    value = ctx.data.get(CONF_PRODUCT_TYPE)
    if value is None and ctx.manufacturer_data:
        value = app.advertised_model(ctx.manufacturer_data)
    try:
        profile = app.MODELS[int(str(value))]
    except ValueError, KeyError:
        raise invalid("easyctrl_model") from None
    return EasyCtrlController(ctx.coordinator, profile)
