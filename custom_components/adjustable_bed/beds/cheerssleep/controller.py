"""CheersSleep model-selected bed controls and immutable physical sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING, Final, Literal, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory

from ...app_session import app_session
from ...card import CARD_MASSAGE
from ...codec import cheerssleep as codec
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey, sided
from ...errors import invalid
from ...profiles import cheerssleep as app
from ...state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    SleepRate,
    sleep_flag_binary_sensor_spec,
    sleep_rate_sensor_spec,
)
from ..lifecycle import ControllerSession
from . import state_keys as keys

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


# Standalone split entries control the left side, like the app's initial selection.
# Native Left/Right side devices target each side.
STANDALONE_SIDE: Final = 1


@dataclass(slots=True)
class LocalState:
    counters: codec.Counters = field(default_factory=codec.Counters)
    burst: codec.Burst = field(default_factory=codec.Burst)
    light: bool = False
    presets: dict[int, str | None] = field(default_factory=dict)
    massage: dict[int, list[int]] = field(default_factory=lambda: {1: [0, 0, 0], 2: [0, 0, 0]})


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    value: int = 0
    rgb: tuple[int, int, int] = (255, 255, 255)
    brightness: int = 255
    duration_ms: int = 1000
    axis: str = "all"
    up: bool = True
    position: int = 1
    sleeper: str | None = None

_RATE_FIELDS: Final[tuple[tuple[str, SleepRate], ...]] = (("heart", "heart_rate"), ("breath", "breathing_rate"))


class CheersSleepController(ProfileExecution[app.CheersSleepProfile], BedController):
    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        model: app.Model = app.MODELS[45],
        *,
        new_notifications: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self.model = model
        self.profile = app.PROFILES[model.format]
        self.new_notifications = new_notifications
        self._link: Link | None = None
        self.local = app_session(
            coordinator.hass, coordinator.address, ("cheerssleep", str(model.key)), LocalState
        )
        self._counters = self.local.counters
        self._burst = self.local.burst
        self._presets = self.local.presets
        self._massage = self.local.massage
        self._rgb: tuple[int, int, int] | None = None
        self._brightness: int | None = None
        self._light_feedback: dict[int, bool] = {}
        self._light_pending: dict[int, bool | None] = {}
        self._mac: str | None = None
        if model.format == "p2" and model.light:
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))
            if model.split and not model.rgb:
                self.forward_controller_state_updates(
                    sided(UNDER_BED_LIGHTS_ON, "left")(None),
                    sided(UNDER_BED_LIGHTS_ON, "right")(None),
                )

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return self.model.format == "p2"

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.model.split

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return self.model.memory

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.model.memory)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self.model.memory)

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_tv(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return self.model.massage or self.model.sonic or self.model.as_layout

    @property
    def supports_lights(self) -> bool:
        return self.model.light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.model.light

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.model.light and self.model.format == "p1"

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self.model.light

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.model.light and self.model.format == "p2"

    @property
    def supports_light_color_control(self) -> bool:
        return self.model.rgb

    @property
    def supports_light_level_control(self) -> bool:
        return self.model.rgb

    @property
    def light_level_max(self) -> int:
        return 100

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int] | None:
        return self._rgb

    @property
    def light_intensity(self) -> int | None:
        return self._brightness

    def _side(self) -> int:
        if not self.model.split:
            return 0
        return {"left": 1, "right": 2}.get(self.command_side or "", STANDALONE_SIDE)

    def _invalidate_preset(self, selected: int) -> None:
        if selected == 0:
            self._presets.clear()
        else:
            self._presets.pop(selected, None)

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or self._coordinator.controller is not self
            or (link is not None and current is not link)
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("CheersSleep physical session changed")
        return current

    async def _send(self, frame: bytes, link: Link, *, cleanup: bool = False) -> None:
        self._live(link)
        await self._write_gatt_with_retry(
            codec.WRITE,
            frame,
            1,
            0,
            asyncio.Event() if cleanup else self._coordinator.cancel_command,
            response=True,
            characteristic=link.write,
            expected_client=link.client,
        )

    async def _release(self, link: Link, frame: bytes, delay_ms: int = 0) -> None:
        async def release() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if (
                self._coordinator.controller is self
                and self._link is link
                and self.client is link.client
                and link.client.is_connected
            ):
                await self._send(frame, link, cleanup=True)

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

    async def _hold(
        self, frame: bytes, release: bytes, duration_ms: int, *, latched: bool = False
    ) -> None:
        link = self._live()
        duration_ms = self.leased_hold_ms(duration_ms)
        deadline = monotonic() + duration_ms / 1000
        cancel = self._coordinator.cancel_command
        timer = asyncio.timeout(duration_ms / 1000)
        try:
            try:
                async with timer:
                    while not cancel.is_set() and monotonic() < deadline:
                        await self._send(frame, link)
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            break
                        await _pause(
                            remaining
                            if latched
                            else min(self.profile.refresh_ms / 1000, remaining),
                            cancel,
                        )
            except TimeoutError:
                if not timer.expired():
                    raise
        finally:
            await self._release(link, release, self.profile.release_ms if latched else 0)

    async def _tap(self, command: bytes, release: bytes | None = None) -> None:
        link = self._live()
        if release is None:
            await self._send(command, link)
            return
        cancel = self._coordinator.cancel_command
        finished = False
        try:
            while not cancel.is_set():
                use_command, final = self._burst.step()
                await self._send(command if use_command else release, link)
                if final:
                    await self._send(release, link, cleanup=True)
                    finished = True
                    return
                if not await _pause(self.profile.refresh_ms / 1000, cancel):
                    return
        finally:
            if not finished:
                await self._release(link, release)

    def _motion(
        self,
        axis: str,
        up: bool,
        *,
        auxiliary: bool = False,
        split: bool = False,
        selected_side: int | None = None,
    ) -> tuple[bytes, bytes]:
        if not auxiliary and (
            axis not in (*self.model.axes, "all") or axis == "all" and not self.model.combined
        ):
            raise NotImplementedError("This model does not expose that actuator")
        selected = self._side() if selected_side is None else selected_side
        if self.model.format == "p1" or auxiliary:
            mapping = (
                app.P1_SPLIT[selected or 1]
                if split or self.model.split and not auxiliary
                else app.P1_AXES
            )
            values = mapping[axis]
            return self._counters.control(
                values[0 if up else 1], held=True
            ), self._counters.control(values[2], held=True)
        if axis == "all":
            values = (21, 42) if "lumbar" in self.model.axes else (5, 10)
        elif axis == "head":
            values = (1024, 2048) if self.model.key == 174 else (64, 128)
        else:
            values = app.P2_AXES[axis]
        return codec.normal(values[0 if up else 1], selected), codec.normal(0)

    async def move_axis(self, axis: str, up: bool, duration_ms: int | None = None) -> None:
        if duration_ms is None:
            duration_ms = min(
                self.execution.hold_ceiling_ms or 30000,
                max(1, self._coordinator.motor_pulse_count) * self.profile.refresh_ms,
            )
        command, release = self._motion(axis, up)
        self._invalidate_preset(0 if self.model.format == "p1" and axis == "legs" else self._side())
        await self._hold(command, release, duration_ms, latched=self.model.format == "p1")

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        if (
            motor not in self.model.axes
            or direction not in ("up", "down")
            or not 1 <= duration_ms <= 30000
        ):
            raise ValueError("Choose an exposed CheersSleep actuator and bounded duration")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                app.AXIS_LABELS[axis],
                lambda ctrl, axis=axis: require_controller(ctrl, CheersSleepController).move_axis(
                    axis, True
                ),
                lambda ctrl, axis=axis: require_controller(ctrl, CheersSleepController).move_axis(
                    axis, False
                ),
                lambda ctrl: ctrl.stop_all(),
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", press_hold_ms=None),
                shared_across_sides=self.model.format == "p1"
                and self.model.split
                and axis == "legs",
            )
            for axis in self.model.axes
        )

    async def move_head_up(self) -> None:
        await self.move_axis("head" if "head" in self.model.axes else "back", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head" if "head" in self.model.axes else "back", False)

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        link = self._live()
        selected = 0 if self.model.format == "p1" else self._side()
        frame = (
            self._counters.control(1)
            if self.model.format == "p1"
            else codec.normal(0x40000000, selected)
        )
        self._invalidate_preset(selected)
        await self._release(link, frame)

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        self._invalidate_preset(0 if self.model.format == "p1" else self._side())
        await self._tap(
            self._counters.control(0x111)
            if self.model.format == "p1"
            else codec.normal(0x08000000, self._side()),
            None if self.model.format == "p1" else codec.normal(0, self._side()),
        )

    async def preset_memory(self, memory_num: int) -> None:
        if not self.model.memory:
            raise NotImplementedError("This model has no memory controls")
        self.validate_memory_recall(memory_num)
        selected = self._side()
        self._invalidate_preset(selected)
        command = (
            (0x6530 if selected == 1 else 0x6538) + memory_num - 1
            if self.model.split
            else (0x311 if memory_num == 1 else 0x313)
        )
        await self._tap(
            self._counters.control(command)
            if self.model.format == "p1"
            else codec.normal(0x10000 if memory_num == 1 else 0x40000, selected),
            None if self.model.format == "p1" else codec.normal(0, selected),
        )

    async def program_memory(self, memory_num: int) -> None:
        if not self.model.memory:
            raise NotImplementedError("This model has no memory controls")
        self.validate_memory_recall(memory_num)
        selected = self._side()
        command = (
            (0x6540 if selected == 1 else 0x6548) + memory_num - 1
            if self.model.split
            else (0x310 if memory_num == 1 else 0x312)
        )
        await self._tap(
            self._counters.control(command)
            if self.model.format == "p1"
            else codec.setting(6, memory_num + 4, selected=selected),
            None if self.model.format == "p1" else codec.setting(0xAA, selected=selected),
        )

    async def _preset(self, name: str) -> None:
        if not self.model.presets:
            raise NotImplementedError("This model has no ZZ/TV/ZG controls")
        selected = self._side()
        if self._presets.get(selected) == name:
            self._invalidate_preset(selected)
            await self._tap(
                self._counters.control(1)
                if self.model.format == "p1"
                else codec.normal(0x40000000, selected)
            )
            return
        legacy, modern = app.PRESETS[name]
        if self.model.split:
            legacy = (0x6511 if selected == 1 else 0x6521) + (legacy - 0x301)
        await self._tap(
            self._counters.control(legacy)
            if self.model.format == "p1"
            else codec.normal(modern, selected),
            None if self.model.format == "p1" else codec.normal(0, selected),
        )
        self._presets[selected] = name

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def lights_toggle(self) -> None:
        if not self.model.light:
            raise NotImplementedError("This model has no light controls")
        if self.model.format == "p1":
            await self._light(not self.local.light)
        else:
            await self._toggle_light(0 if self.model.rgb else self._side())

    async def _toggle_light(self, selected: int) -> None:
        self._live()
        previous = self._light_feedback.get(selected)
        # Keep the guard if a write is cancelled or fails: its physical effect is unknown.
        self._light_pending[selected] = (
            None if previous is None or selected in self._light_pending else not previous
        )
        await self._tap(codec.normal(0x20000, selected), codec.normal(0, selected))

    def _observe_light(self, selected: int, enabled: bool) -> None:
        self._light_feedback[selected] = enabled
        if selected in self._light_pending and self._light_pending[selected] in (None, enabled):
            del self._light_pending[selected]
        updates = (
            [sided(UNDER_BED_LIGHTS_ON, {1: "left", 2: "right"}[selected])(enabled)]
            if selected
            else []
        )
        if not selected or selected == STANDALONE_SIDE:
            updates.append(UNDER_BED_LIGHTS_ON(enabled))
        self.forward_controller_state_updates(*updates)

    async def _light(self, enabled: bool) -> None:
        if not self.model.light:
            raise NotImplementedError("This model has no light controls")
        if self.model.format == "p2":
            self._live()
            selected = 0 if self.model.rgb else self._side()
            if selected in self._light_pending:
                raise invalid("light_state_unknown")
            observed = self._light_feedback.get(selected)
            if observed is None:
                raise invalid("light_state_unknown")
            if observed != enabled:
                await self._toggle_light(selected)
            return
        await self._tap(self._counters.control(0x501 if enabled else 0x500))
        self.local.light = enabled
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(enabled))

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if not self.model.rgb:
            raise NotImplementedError("This model has no RGB controls")
        if any(not 0 <= v <= 255 for v in rgb_color):
            raise ValueError("Choose an RGB-capable CheersSleep model and RGB 0..255")
        await self._tap(codec.setting(5, *rgb_color), codec.setting(0xAA))

    async def set_light_level(self, level: int) -> None:
        if not self.model.rgb:
            raise NotImplementedError("This model has no brightness control")
        if not 0 <= level <= 100:
            raise ValueError("Choose RGB brightness 0..100")
        await self._tap(codec.setting(10, level), codec.setting(0xAA))

    async def massage_action(self, action: str, value: int = 0) -> None:
        if not self.model.massage:
            raise ValueError("This model has no conventional vibration controls")
        selected = self._side()
        state = self._massage[selected or 1]
        if self.model.format == "p2":
            word = app.P2_MASSAGE[action]
            await self._tap(codec.normal(word, selected), codec.normal(0, selected))
            return
        if action == "mode":
            mode = (state[2] + 1) % 3
            command = app.P1_WAVE_MODE[selected][mode]
            next_state = (
                [1, 1, 1] if mode == 1 else [state[0], state[1], 2] if mode == 2 else [0, 0, 0]
            )
        else:
            index = 0 if action == "head" else 1
            level = (state[index] % 3 + 1) if state[2] else (state[index] + 1) % 4
            if value in range(1, 5):
                level = value - 1  # Explicit service levels0..3, encoded as1..4.
            command = (
                app.P1_WAVE[selected][action][level - 1]
                if state[2] and level
                else app.P1_STEADY[selected][action][level]
            )
            next_state = list(state)
            next_state[index] = level
        await self._tap(self._counters.control(command))
        self._massage[selected or 1] = next_state
        self._publish_massage(selected, next_state)

    def _publish_massage(self, selected: int, state: list[int]) -> None:
        side = {1: "left", 2: "right"}.get(selected)
        updates = [
            sided(key, side)(value)
            for key, value in zip((keys.HEAD, keys.FOOT, keys.MODE), state, strict=True)
        ]
        if not selected or selected == STANDALONE_SIDE:
            updates.extend(
                key(value)
                for key, value in zip((keys.HEAD, keys.FOOT, keys.MODE), state, strict=True)
            )
        self.forward_controller_state_updates(*updates)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            tuple(
                f"{axis}_{direction}"
                for axis in (
                    *self.model.axes,
                    *(("all",) if self.model.combined and "all" not in self.model.axes else ()),
                )
                for direction in ("up", "down")
            )
            + (("sonic_switch",) if self.model.sonic else ())
            + (("sonic_increase", "sonic_decrease") if self.model.as_layout else ())
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 30000:
            raise ValueError("Choose an exposed CheersSleep held control")
        if self.model.format == "p1" and duration_ms > 10000:
            raise ValueError("Legacy latched holds are limited to 10 seconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control == "sonic_switch":
            link = self._live()
            try:
                await self._hold(
                    codec.normal(app.SONIC[control], self._side()), codec.normal(0), duration_ms
                )
            finally:
                if self.model.key != 172:  # OBS-098-02: split handler omits follow-up.
                    await self._release(link, codec.query(True), 200)
        elif control in ("sonic_increase", "sonic_decrease"):
            await self._hold(
                codec.setting(11, 2, int(control == "sonic_increase")), codec.normal(0), duration_ms
            )
        else:
            axis, direction = control.rsplit("_", 1)
            await self.move_axis(axis, direction == "up", duration_ms)

    async def sonic_action(self, action: str) -> None:
        if self.model.sonic and action in app.SONIC and action != "sonic_switch":
            await self._tap(
                codec.normal(app.SONIC[action], self._side()), codec.normal(0, self._side())
            )
        elif self.model.as_layout and action == "sonic_toggle":
            await self._tap(codec.setting(11, 2, 3), codec.setting(0xAA))
        else:
            raise ValueError("This sonic control is unavailable on the chosen model")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result = []
        if self.model.light and self.model.format == "p2":
            result.append(
                ControllerButtonSpec(
                    "cheerssleep_refresh",
                    "Refresh bed state",
                    lambda ctrl: require_controller(ctrl, CheersSleepController).refresh_state(),
                    translation_key="cheerssleep_refresh",
                    # Connect queries one side, so a split bed's other side
                    # only gets light feedback from this button.
                    diagnostic=not (self.model.split and not self.model.rgb),
                )
            )
        if self.model.combined and "all" not in self.model.axes:
            for direction in ("up", "down"):
                # Every section together: the shared all-motors row.
                spec = catalog_button(
                    f"cheerssleep_all_{direction}",
                    f"All motors {direction}",
                    lambda ctrl, direction=direction: require_controller(
                        ctrl, CheersSleepController
                    ).move_axis("all", direction == "up"),
                    kind=Kind.MOTOR,
                    hold=ControllerHoldSpec(f"all_{direction}"),
                )
                assert spec is not None
                result.append(spec)
        if self.model.massage:
            for action in ("head", "foot", "mode"):
                result.append(
                    ControllerButtonSpec(
                        f"cheerssleep_massage_{action}",
                        f"Massage {action}",
                        lambda ctrl, action=action: require_controller(
                            ctrl, CheersSleepController
                        ).massage_action(action),
                        translation_key=f"cheerssleep_massage_{action}",
                        card=CARD_MASSAGE,
                    )
                )
        for action in (
            tuple(app.SONIC)
            if self.model.sonic
            else ("sonic_toggle", "sonic_increase", "sonic_decrease")
            if self.model.as_layout
            else ()
        ):
            held = action in ("sonic_switch", "sonic_increase", "sonic_decrease")
            result.append(
                ControllerButtonSpec(
                    f"cheerssleep_{action}",
                    action.replace("_", " "),
                    lambda ctrl, action=action, held=held: (
                        require_controller(ctrl, CheersSleepController).hold_control(action, 1000)
                        if held
                        else require_controller(ctrl, CheersSleepController).sonic_action(action)
                    ),
                    translation_key=f"cheerssleep_{action}",
                    hold=ControllerHoldSpec(action) if held else None,
                    card=CARD_MASSAGE,
                )
            )
        return tuple(result)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            (
                ControllerNumberSpec(
                    "cheerssleep_sonic_level",
                    "cheerssleep_sonic_level",
                    keys.SONIC_LEVEL,
                    0,
                    100,
                    1,
                    lambda ctrl, value: require_controller(
                        ctrl, CheersSleepController
                    ).set_sonic_level(int(value)),
                    card=CARD_MASSAGE,
                ),
            )
            if self.model.sonic
            else ()
        )

    async def set_sonic_level(self, value: int) -> None:
        if not self.model.sonic or not 0 <= value <= 100:
            raise ValueError("Choose a sonic level0..100 on an I/HI model")
        await self._tap(codec.setting(11, 3, value), codec.setting(0xAA))

    def validate_request(self, request: Request) -> None:
        op = request.operation
        if request.sleeper is not None:
            if op != "seven_motion" or request.sleeper not in ("left", "right"):
                raise ValueError("The auxiliary sleeper selector belongs to Seven motion")
            if self.command_side in ("left", "right") and self.command_side != request.sleeper:
                raise ValueError("The auxiliary sleeper conflicts with the targeted child side")
        if op in ("position_light_toggle", "color_light_toggle"):
            if (
                self.model.format != "p2"
                or not self.model.light
                or op == "color_light_toggle"
                and not self.model.rgb
            ):
                raise ValueError("Choose a model with that light consumer")
        elif op in ("query", "query_shared"):
            if self.model.format != "p2" or not self.model.light:
                raise ValueError("P2 queries require a P2 model")
        elif op in (
            "rgb_preview",
            "rgb2_preview",
            "rgb_commit",
            "rgb2_commit",
            "snore_setting",
            "out_of_bed_setting",
            "yb_massage",
            "seven_motion",
            "ten_motion",
            "ten_recall",
            "ten_save",
            "newten_motion",
            "newten_recall",
            "newten_save",
        ):
            if self.model.format != "p1":
                raise ValueError("These conditional exported screens use legacy P1")
            if op.endswith("motion") and (
                request.axis not in app.P1_AXES
                or not 1 <= request.position <= 4
                or not 1 <= request.duration_ms <= 10000
            ):
                raise ValueError("Choose a legacy axis, position1..4 and duration1..10000ms")
            if op.endswith(("recall", "save")) and request.value not in (1, 2):
                raise ValueError("Choose memory1 or2")
            if op in ("snore_setting", "out_of_bed_setting") and request.value not in (0, 1):
                raise ValueError("Choose0 or1")
            if op == "yb_massage" and (
                request.value not in (1, 2, 3) or request.duration_ms not in app.YB_TIMERS
            ):
                raise ValueError("Yb uses speed1..3 and timer parameter300 or900 only")
            if op.endswith("commit") and not 10 <= request.value <= 120:
                raise ValueError("Choose the app delay setting10..120 (firmware units unproven)")
            if any(not 0 <= v <= 255 for v in (*request.rgb, request.brightness)):
                raise ValueError("RGB and brightness must be0..255")
        elif op.startswith("massage_"):
            if (
                not self.model.massage
                or op[8:] not in ("head", "foot", "mode")
                or not 0 <= request.value <= 4
            ):
                raise ValueError("Choose a conventional massage control")
            if self.model.format == "p2" and request.value:
                raise ValueError("P2 conventional massage exposes cycles, not absolute levels")
        elif op == "sonic_level":
            if not self.model.sonic or not 0 <= request.value <= 100:
                raise ValueError("Choose an I/HI sonic level0..100")
        elif op in ("sonic_switch", "sonic_increase", "sonic_decrease"):
            self.validate_hold_control(op, request.duration_ms)
        elif op in app.SONIC:
            if not self.model.sonic and not (self.model.as_layout and op == "sonic_toggle"):
                raise ValueError("This model has no such sonic action")
        else:
            raise ValueError("Unknown CheersSleep action")

    async def execute_request(self, request: Request) -> None:
        self.validate_request(request)
        op = request.operation
        link = self._live()
        if op in ("position_light_toggle", "color_light_toggle"):
            selected = 0 if op == "color_light_toggle" else self._side()
            if op == "position_light_toggle" and self.model.rgb:
                # This position-page light is separate from the shared RGB light.
                await self._tap(codec.normal(0x20000, selected), codec.normal(0, selected))
            else:
                await self._toggle_light(selected)
        elif op in ("query", "query_shared"):
            await self._send(codec.query(op == "query_shared", self._side()), link)
        elif op.startswith("massage_"):
            await self.massage_action(op[8:], request.value)
        elif op == "sonic_level":
            await self.set_sonic_level(request.value)
        elif op in ("sonic_switch", "sonic_increase", "sonic_decrease"):
            await self.hold_control(op, request.duration_ms)
        elif op in app.SONIC:
            await self.sonic_action(op)
        elif op in ("snore_setting", "out_of_bed_setting"):
            await self._send(
                self._counters.configure(app.P1_SETTINGS[op], request.value),
                link,
            )
        elif op == "yb_massage":
            await self._tap(
                self._counters.control(app.YB_SPEEDS[request.value - 1], request.duration_ms)
            )
        elif op.endswith("motion"):
            axis = (
                request.axis
                if op == "seven_motion"
                else ("all", "back", "legs", "lumbar")[request.position - 1]
            )
            command, release = self._motion(
                axis,
                request.up,
                auxiliary=True,
                split=op == "seven_motion",
                selected_side={"left": 1, "right": 2}.get(request.sleeper)
                if request.sleeper
                else None,
            )
            self._invalidate_preset(
                {"left": 1, "right": 2}.get(request.sleeper or "", self._side())
                if self.model.split and op == "seven_motion" and axis != "legs"
                else 0
            )
            await self._hold(command, release, request.duration_ms, latched=True)
        elif op.endswith(("recall", "save")):
            if op.endswith("recall"):
                self._invalidate_preset(0)
            await self._tap(
                self._counters.control(
                    (0x310 if op.endswith("save") else 0x311) + 2 * (request.value - 1)
                )
            )
        else:
            rgb = (255, 255, 255) if op.startswith("rgb2") else request.rgb
            parameter = codec.rgb_parameter(*rgb, request.brightness)
            if op.endswith("commit"):
                await self._send(
                    self._counters.configure(app.P1_SETTINGS["delay"], request.value), link
                )
                if await _pause(app.RGB_SAVE_MS / 1000, self._coordinator.cancel_command):
                    await self._send(self._counters.control(0x50F, parameter), link)
            elif await _pause(app.RGB_PREVIEW_MS[op] / 1000, self._coordinator.cancel_command):
                await self._send(self._counters.control(0x501, parameter), link)

    async def refresh_state(self) -> None:
        link = self._live()
        if self.model.format == "p2":
            await self._send(codec.query(self.model.shared, self._side()), link)
        elif self.model.key in (45, 53):
            await self._send(self._counters.mac_query(), link)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True  # No Device Information read in the accepted app session.

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()
        if self.model.format == "p2" and self.model.light:
            # Parent navigation resume is unscoped even on Position500i.
            if self.model.shared:
                await self._send(codec.query(True), self._live())
                await self._send(codec.query(True), self._live())
            else:
                await self.refresh_state()
        elif self.model.key in (45, 53):
            for _ in range(app.MAC_QUERY_ATTEMPTS):
                if self._mac or not await _pause(
                    app.MAC_QUERY_INTERVAL_MS / 1000, self._coordinator.cancel_command
                ):
                    break
                await self.refresh_state()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is not None:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("CheersSleep is disconnected")
        service = next((s for s in client.services if s.uuid.lower() == codec.SERVICE), None)
        write = service.get_characteristic(codec.WRITE) if service else None
        notify = service.get_characteristic(codec.NOTIFY) if service else None
        if (
            write is None
            or notify is None
            or "write" not in write.properties
            or "notify" not in notify.properties
        ):
            raise ConnectionError(
                "CheersSleep requires its writable and notifying bed characteristics"
            )
        link = Link(client, write, notify)
        self._link = link
        try:
            await client.start_notify(notify, lambda sender, data: self._receive(link, data))
            # Bleak owns the notify CCCD. Android also registers WRITE locally
            # on legacy scans, but never writes its CCCD. No second subscription.
        except BaseException:
            self.on_disconnect()
            raise

    def _receive(self, link: Link, data: bytearray) -> None:
        if (
            self._coordinator.controller is not self
            or self._link is not link
            or self.client is not link.client
            or not link.client.is_connected
        ):
            return
        raw = bytes(data)
        self.forward_raw_notification(codec.NOTIFY, raw)
        if self.model.format == "p1":
            if (mac := codec.sleep_mac(raw)) is not None:
                self._mac = mac
            if (sleep := codec.sleep_state(raw)) is not None:
                self.forward_controller_state_updates(
                    *(
                        key(getattr(sleep, name))
                        for name, key in keys.SLEEP_KEYS[sleep.side].items()
                    )
                )
            return
        basic = codec.basic_state(raw, massage=self.model.massage)
        if basic:
            if not self.model.rgb:
                selected = {0xAA: 1, 0xBB: 2}.get(raw[3]) if self.model.split else 0
                if selected is not None:
                    self._observe_light(selected, basic.light)
            for selected in (1, 2) if self.model.split else (0,):
                state = codec.basic_state(raw, massage=self.model.massage, selected=selected)
                if (
                    state
                    and state.mode is not None
                    and state.head is not None
                    and state.foot is not None
                ):
                    self._publish_massage(selected, [state.head, state.foot, state.mode])
        if not self.model.shared:
            return
        shared = codec.shared_state(raw, as_layout=self.model.as_layout)
        if shared:
            if self.model.rgb:
                color = codec.shared_state(raw)
                assert color is not None
                self._rgb, self._brightness = color.rgb, color.brightness
                self._observe_light(0, color.light)
                self.forward_controller_state_updates(
                    UNDER_BED_LIGHTS_RGB(color.rgb),
                    LIGHT_LEVEL(color.brightness if 0 <= color.brightness <= 100 else None),
                )
            else:
                selected = {0xAA: 1, 0xBB: 2}.get(raw[3]) if self.model.split else 0
                if selected is not None:
                    self._observe_light(selected, shared.light)
            if self.model.sonic:
                self.forward_controller_state_updates(keys.SONIC_LEVEL(shared.level))
                for selected in (1, 2) if self.model.split else (0,):
                    state = codec.shared_state(raw, selected=selected)
                    if state:
                        self.forward_controller_state_updates(
                            sided(keys.MODE, {1: "left", 2: "right"}.get(selected))(state.mode)
                        )
                        if selected == STANDALONE_SIDE:
                            self.forward_controller_state_updates(keys.MODE(state.mode))

    def on_disconnect(self) -> None:
        self._link = None
        self._mac = None
        self._rgb = None
        self._brightness = None
        self._light_feedback.clear()
        self._light_pending.clear()
        if self.model.split and not self.model.rgb and self.model.format == "p2":
            self.forward_controller_state_updates(
                sided(UNDER_BED_LIGHTS_ON, "left")(None),
                sided(UNDER_BED_LIGHTS_ON, "right")(None),
            )
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
            LIGHT_LEVEL(None),
            keys.SONIC_LEVEL(None),
        )
        for side in (None, "left", "right"):
            self.forward_controller_state_updates(
                *(sided(key, side)(None) for key in (keys.HEAD, keys.FOOT, keys.MODE))
            )
        self.forward_controller_state_updates(
            *(key(None) for fields in keys.SLEEP_KEYS.values() for key in fields.values())
        )

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link and self.client is link.client and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        result = [
            ControllerStateSensorSpec(
                str(key),
                str(key).removesuffix("_left").removesuffix("_right"),
                key,
                "mdi:vibrate",
                # Massage levels are dashboard state.
                entity_registry_enabled_default=level,
                entity_category=None if level else EntityCategory.DIAGNOSTIC,
            )
            for key, level in (
                ((keys.HEAD, True), (keys.FOOT, True), (keys.MODE, False))
                if self.model.massage
                else ((keys.MODE, False),)
                if self.model.sonic
                else ()
            )
            for key in (sided(key, self.command_side),)
        ]
        # Sleep notifications name their side; a native side device shows only its own.
        for side, fields in self._sleep_fields():
            result.extend(
                sleep_rate_sensor_spec(
                    kind,
                    str(fields[name]),
                    cast(StateKey[int | None], fields[name]),
                    side,
                    has_unit=False,
                )
                for name, kind in _RATE_FIELDS
            )
            result.extend(
                ControllerStateSensorSpec(
                    str(fields[name]),
                    str(fields[name]),
                    fields[name],
                    "mdi:bed",
                    entity_registry_enabled_default=False,
                )
                for name in ("snore_count", "snore_power")
            )
        return tuple(result)

    def _sleep_fields(
        self,
    ) -> list[tuple[Literal["left", "right"], dict[str, StateKey[int | bool | None]]]]:
        if self.model.format != "p1":
            return []
        return [
            (side, keys.SLEEP_KEYS[side])
            for side in keys.SIDES
            if self.command_side not in keys.SIDES or side == self.command_side
        ]

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        specs: list[ControllerStateBinarySensorSpec] = []
        for side, fields in self._sleep_fields():
            specs.append(
                sleep_flag_binary_sensor_spec(
                    "bed_presence",
                    str(fields["on_bed"]),
                    cast(StateKey[bool | None], fields["on_bed"]),
                    side,
                )
            )
            specs.append(
                ControllerStateBinarySensorSpec(
                    str(fields["asleep"]),
                    str(fields["asleep"]),
                    fields["asleep"],
                    "mdi:sleep",
                    entity_registry_enabled_default=False,
                )
            )
        return tuple(specs)


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
        return False
    except TimeoutError:
        return True


async def build_controller(ctx: BuildContext) -> CheersSleepController:
    found = app.advertisement(ctx.manufacturer_data or {})
    key = int(
        ctx.data.get(
            CONF_PRODUCT_TYPE, found[0].key if found else 134 if ctx.variant == "p2" else 45
        )
    )
    if key not in app.MODELS:
        raise ValueError("Choose an accepted CheersSleep model key")
    return CheersSleepController(
        ctx.coordinator, app.MODELS[key], new_notifications=found[1] if found else False
    )
