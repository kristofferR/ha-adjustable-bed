"""OKIN Smart Sleep bed session, app gestures and caller-scoped admission."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import TYPE_CHECKING, Any

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...app_session import app_session
from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_PRESETS, CARD_UTILITY
from ...codec import smart_sleep as codec
from ...const import CONF_PRODUCT_TYPE
from ...profiles import smart_sleep as app
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from . import state_keys as keys

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass
class AppState:
    child: bool = False


class SmartSleepController(ProfileExecution[app.SmartSleepProfile], BedController):
    """One physical receiver; neither format proves paired side addressing."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: app.SmartSleepProfile = app.PROFILES["p1"],
        model: int = 0,
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self.model = 80 if profile.key == "p2" else model if model in app.MODELS else 0
        self.app = app_session(
            coordinator.hass, coordinator.address, ("smart_sleep", profile.key), AppState
        )
        self._notify: BleakGATTCharacteristic | None = None
        self._session = 0
        self._replies = codec.Replies()
        self._partial_at = 0.0
        self._new_privacy = False
        self._light: codec.LightState | None = None
        self._massage: codec.MassageState | None = None
        self.forward_controller_state_updates(
            keys.CHILD_MODE("on" if self.app.child else "off"), keys.MODEL(self.model)
        )

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def persisted_app_state(self) -> Mapping[str, Any]:
        return {"child_mode": self.app.child}

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        if type(state.get("child_mode")) is bool:
            self.app.child = state["child_mode"]
            self.forward_controller_state_updates(
                keys.CHILD_MODE("on" if self.app.child else "off")
            )

    def _admit(self) -> None:
        if self.app.child:
            raise ValueError("Smart Sleep child mode is enabled in Home Assistant")

    def _role(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Smart Sleep is disconnected")
        for service in client.services:
            if service.uuid.lower() == codec.SERVICE:
                char = service.get_characteristic(uuid)
                if char is not None:
                    return char
        raise ConnectionError(f"Smart Sleep requires {uuid} under its bed service")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        admit: bool = False,
    ) -> None:
        client = self.client
        char = self._role(codec.WRITE)
        if "write" not in char.properties:
            raise ConnectionError("Smart Sleep requires writes with response")
        await self._write_gatt_with_retry(
            codec.WRITE,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event,
            response=True,
            characteristic=char,
            expected_client=client,
            wall_clock_pacing=True,
            before_write=self._admit if admit else None,
        )

    async def _cleanup(self, frame: bytes, session: int, client: object, delay_ms: int = 0) -> None:
        """The admitted session owns an immutable release, even after child/cancel changes."""

        async def release() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if (
                session != self._session
                or self.client is not client
                or self.client is None
                or not self.client.is_connected
            ):
                return
            await self.write_command(frame, cancel_event=asyncio.Event())

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

    async def _held(
        self, frame: bytes, *, interval: int, duration_ms: int | None = None, motor: bool = False
    ) -> None:
        self._admit()
        session, client = self._session, self.client
        release = codec.stop(self.profile.key, motor=motor)
        count = self.leased_hold_refreshes(interval)
        # The scheduler owns lease expiry; only an unleased press uses this deadline.
        duration = duration_ms / 1000 if duration_ms is not None and count is None else None
        if count is None:
            count = (
                max(1, (duration_ms + interval - 1) // interval)
                if duration_ms is not None
                else self._coordinator.motor_pulse_count
            )
        deadline = asyncio.timeout(duration)
        try:
            try:
                async with deadline:
                    await self.write_command(frame, count, interval, admit=True)
                    if duration is not None:
                        await self._coordinator.cancel_command.wait()
            except TimeoutError:
                if not deadline.expired():
                    raise
        finally:
            await self._cleanup(release, session, client, self.profile.release_ms)

    async def move_axis(self, axis: str, up: bool, duration_ms: int | None = None) -> None:
        if axis not in app.AXES:
            raise ValueError("Unknown Smart Sleep app actuator")
        await self._held(
            codec.motion(self.profile.key, app.AXES[axis][0], up),
            interval=self.profile.refresh_ms,
            duration_ms=duration_ms,
            motor=True,
        )

    async def move_head_up(self) -> None:
        await self.move_axis("head", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head", False)

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    async def move_lumbar_up(self) -> None:
        await self.move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self.move_axis("lumbar", False)

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        # HA safety STOP bypasses UI child admission on both formats (audit A2).
        await self._cleanup(
            codec.stop(self.profile.key), self._session, self.client, self.profile.release_ms
        )

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
    move_lumbar_stop = stop_all

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        self._admit()
        if (
            motor not in app.AXES
            or direction not in ("up", "down")
            or not 1 <= duration_ms <= 30000
        ):
            raise ValueError("Choose an app actuator, direction and duration up to 30 seconds")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                label,
                lambda ctrl, axis=axis: require_controller(ctrl, SmartSleepController).move_axis(
                    axis, True
                ),
                lambda ctrl, axis=axis: require_controller(ctrl, SmartSleepController).move_axis(
                    axis, False
                ),
                lambda ctrl: ctrl.stop_all(),
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", press_hold_ms=None),
            )
            for axis, (_, label) in app.AXES.items()
        )

    @property
    def presets(self) -> tuple[str, ...]:
        if self.profile.key == "p1" and self.model == 8:
            return ("ai_zero", "memory_1", "memory_2", "flat")
        return tuple(codec.PRESETS)

    async def recall(self, name: str) -> None:
        self._admit()
        if name not in self.presets:
            raise ValueError("This model does not offer that preset")
        frame = codec.preset(self.profile.key, name)
        if self.profile.key == "p2":
            await self.stop_all()
            await self.write_command(frame, admit=True)
        elif name == "ai_zero":
            session, client = self._session, self.client
            release, delay = codec.stop(self.profile.key), self.profile.release_ms
            try:
                await self.write_command(frame, 2, self.profile.query_ms, admit=True)
            finally:
                await self._cleanup(release, session, client, delay)
        else:
            await self._held(frame, interval=self.profile.refresh_ms)

    async def preset_flat(self) -> None:
        await self.recall("flat")

    async def preset_zero_g(self) -> None:
        await self.recall("zero_g")

    async def preset_lounge(self) -> None:
        await self.recall("read")

    async def preset_tv(self) -> None:
        await self.recall("tv")

    async def preset_anti_snore(self) -> None:
        await self.recall("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.recall(f"memory_{memory_num}")

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        self._admit()

    async def save(self, name: str) -> None:
        self._admit()
        if not self.supports_memory_programming or name not in codec.PRESETS or name == "flat":
            raise ValueError("Only P2's six non-flat presets have a proven SAVE")
        await self.write_command(codec.preset(self.profile.key, name, save=True), admit=True)

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.save(f"memory_{memory_num}")

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return self.profile.key == "p2"

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.presets

    @property
    def supports_preset_lounge(self) -> bool:
        return "read" in self.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self.presets

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if self.profile.key == "p1" and key in ("preset_memory_1", "preset_memory_2"):
            return ControllerHoldSpec(key)
        return None

    @property
    def held_control_options(self) -> tuple[str, ...]:
        motors = tuple(f"{axis}_{direction}" for axis in app.AXES for direction in ("up", "down"))
        massage = tuple(
            f"massage_{action}"
            for action in ("all", "off", "wave", "timer", "head_strength", "foot_strength")
        )
        return (*motors, *massage, *(f"preset_{name}" for name in self.presets))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 30000
        ):
            raise ValueError("Choose a supported held control and duration up to 30 seconds")
        self._admit()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control.startswith("preset_"):
            name = control.removeprefix("preset_")
            if self.profile.key == "p1":
                if name == "ai_zero":
                    await self._ai_hold(duration_ms)
                else:
                    await self._held(
                        codec.preset("p1", name),
                        interval=self.profile.refresh_ms,
                        duration_ms=duration_ms,
                    )
                return
            # P2's press is empty; SAVE happens at 5.5s, release then STOP/recall.
            session, client = self._session, self.client
            try:
                if (
                    not await self._wait_cancel(min(duration_ms, self.profile.save_ms))
                    and duration_ms >= self.profile.save_ms
                    and name != "flat"
                ):
                    await self.save(name)
                if duration_ms > self.profile.save_ms:
                    await self._wait_cancel(duration_ms - self.profile.save_ms)
            finally:
                await self._cleanup(codec.stop("p2"), session, client)
            if (
                not self._coordinator.cancel_command.is_set()
                and session == self._session
                and self.client is client
            ):
                self._admit()
                await self.write_command(codec.preset("p2", name), admit=True)
        elif control.startswith("massage_"):
            await self.massage_action(control.removeprefix("massage_"), duration_ms=duration_ms)
        else:
            axis, direction = control.rsplit("_", 1)
            await self.move_axis(axis, direction == "up", duration_ms)

    async def _ai_hold(self, duration_ms: int) -> None:
        session, client = self._session, self.client
        frame = codec.preset("p1", "ai_zero")
        duplicates: list[asyncio.Task[None]] = []

        async def duplicate() -> None:
            if (
                not await self._wait_cancel(self.profile.query_ms)
                and session == self._session
                and self.client is client
            ):
                await self.write_command(frame, admit=True)

        count = self.leased_hold_refreshes(self.profile.refresh_ms)
        deadline = asyncio.timeout(duration_ms / 1000 if count is None else None)
        if count is None:
            count = max(1, (duration_ms + self.profile.refresh_ms - 1) // self.profile.refresh_ms)
        try:
            try:
                async with deadline:
                    for _ in range(count):
                        if self._coordinator.cancel_command.is_set():
                            break
                        await self.write_command(frame, admit=True)
                        duplicates.append(asyncio.create_task(duplicate()))
                        if await self._wait_cancel(self.profile.refresh_ms):
                            break
            except TimeoutError:
                if not deadline.expired():
                    raise
        finally:
            # Delayed refreshes belong to this gesture, never to the next command.
            for task in duplicates:
                task.cancel()
            await asyncio.gather(*duplicates, return_exceptions=True)
            await self._cleanup(codec.stop("p1"), session, client, self.profile.release_ms)

    async def _wait_cancel(self, ms: int) -> bool:
        try:
            async with asyncio.timeout(ms / 1000):
                await self._coordinator.cancel_command.wait()
        except TimeoutError:
            return False
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    async def massage_action(
        self, action: str, *, index: int | None = None, duration_ms: int | None = None
    ) -> None:
        self._admit()
        action = {"all": "massage_all", "off": "massage_off"}.get(action, action)
        frame = self._massage_frame(action, index)
        session, client = self._session, self.client
        try:
            if duration_ms is None:
                await self.write_command(frame, admit=True)
            else:
                count = self.leased_hold_refreshes(self.profile.massage_ms) or max(
                    1, (duration_ms + self.profile.massage_ms - 1) // self.profile.massage_ms
                )
                for _ in range(count):
                    if self._coordinator.cancel_command.is_set():
                        break
                    await self.write_command(self._massage_frame(action, index), admit=True)
                    if await self._wait_cancel(self.profile.massage_ms):
                        break
        finally:
            await self._cleanup(
                codec.stop(self.profile.key), session, client, self.profile.release_ms
            )
        if session == self._session and not self._coordinator.cancel_command.is_set():
            await self.refresh("massage")

    def _massage_frame(self, action: str, index: int | None) -> bytes:
        if self.profile.key == "p1" or action in ("massage_all", "massage_off"):
            return codec.massage(self.profile.key, action)
        if index is not None:
            first, count = codec.CATALOGS[action]
            if index not in range(1, count + 1):
                raise ValueError("Choose a catalog option")
            return codec.massage("p2", action, index)
        if self._massage is None:
            raise ValueError("Massage state is unknown; refresh or select an explicit option")
        if action == "wave":
            return codec.wave_cycle(self._massage.wave)
        value = {
            "head_strength": self._massage.head,
            "foot_strength": self._massage.foot,
            "timer": self._massage.timer,
        }[action]
        return codec.massage("p2", action, value + 1)

    async def massage_toggle(self) -> None:
        await self.massage_action("all" if self._massage is None or not self._massage.on else "off")

    async def massage_mode_step(self) -> None:
        await self.massage_action("wave")

    async def select_option(self, action: str, option: str) -> None:
        if action in codec.CATALOGS and action != "alarm":
            await self.massage_action(action, index=int(option))
            return
        if action == "privacy":
            await self.write_command(codec.privacy(option == "on"))
        elif action == "antisnore":
            await self.write_command(
                codec.antisnore(
                    option != "off", int(option) if option.isdigit() else 0, demo=option == "demo"
                )
            )
        elif action == "sensitivity":
            await self.write_command(codec.sensitivity(int(option)))
        else:
            raise ValueError("Unknown setting")
        if action != "sensitivity":
            await self.refresh("settings")

    def select_child(self, option: str) -> None:
        self.app.child = option == "on"
        self.forward_controller_state_updates(keys.CHILD_MODE(option))

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs = [
            ControllerSelectSpec(
                "smart_sleep_child_mode",
                "smart_sleep_child_mode",
                keys.CHILD_MODE,
                ("off", "on"),
                lambda ctrl, option: _local_child(ctrl, option),
                local_select_fn=self.select_child,
            )
        ]
        for name, key, options in (
            ("privacy", keys.PRIVACY, ("off", "on")),
            ("antisnore", keys.ANTISNORE, ("off", "1", "3", "6", "demo")),
            ("sensitivity", keys.SENSITIVITY, ("1", "2", "3")),
            *(
                (name, key, tuple(str(i) for i in range(1, codec.CATALOGS[name][1] + 1)))
                for name, key in (
                    ("wave", keys.WAVE),
                    ("head_strength", keys.HEAD),
                    ("foot_strength", keys.FOOT),
                    ("timer", keys.TIMER),
                )
                if self.profile.key == "p2"
            ),
        ):
            specs.append(
                ControllerSelectSpec(
                    f"smart_sleep_{name}",
                    f"smart_sleep_{name}",
                    key,
                    options,
                    lambda ctrl, option, name=name: require_controller(
                        ctrl, SmartSleepController
                    ).select_option(name, option),
                    card=CARD_MASSAGE_TIMER
                    if name == "timer"
                    else CARD_MASSAGE
                    if name in codec.CATALOGS
                    else CARD_UTILITY,
                )
            )
        return tuple(specs)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "smart_sleep_refresh",
                "Refresh bed state",
                lambda ctrl: require_controller(ctrl, SmartSleepController).refresh_all(),
                translation_key="smart_sleep_refresh",
                cancel_movement=False,
            )
        ]
        specs.extend(
            ControllerButtonSpec(
                f"smart_sleep_{name}",
                name.replace("_", " ").title(),
                lambda ctrl, name=name: require_controller(ctrl, SmartSleepController).recall(name),
                translation_key=f"smart_sleep_{name}",
                hold=ControllerHoldSpec(f"preset_{name}") if self.profile.key == "p1" else None,
                card=CARD_PRESETS,
                invalidates_position=True,
            )
            for name in self.presets
            if name not in ("memory_1", "memory_2")
        )
        if self.profile.key == "p2":
            specs.extend(
                ControllerButtonSpec(
                    f"smart_sleep_save_{name}",
                    f"Save {name}",
                    lambda ctrl, name=name: require_controller(ctrl, SmartSleepController).save(
                        name
                    ),
                    translation_key=f"smart_sleep_save_{name}",
                    card=CARD_PRESETS,
                )
                for name in codec.PRESETS
                if name not in ("flat", "memory_1", "memory_2")
            )
        specs.extend(
            ControllerButtonSpec(
                f"smart_sleep_massage_{name}",
                f"Massage {name}",
                lambda ctrl, name=name: require_controller(
                    ctrl, SmartSleepController
                ).massage_action(name),
                translation_key=f"smart_sleep_massage_{name}",
                hold=ControllerHoldSpec(f"massage_{name}"),
                card=CARD_MASSAGE_TIMER if name == "timer" else CARD_MASSAGE,
            )
            for name in ("all", "off", "wave", "timer", "head_strength", "foot_strength")
        )
        return tuple(specs)

    def controller_button_available(self, key: str) -> bool:
        return key == "smart_sleep_refresh" or not self.app.child

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.key == "p2"

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.profile.key == "p2"

    async def _light_set(self, enabled: bool) -> None:
        self._admit()
        session, client = self._session, self.client
        await self._cleanup(codec.stop(self.profile.key), session, client, self.profile.release_ms)
        if session != self._session or self.client is not client:
            raise ConnectionError("Smart Sleep session ended before light command")
        await self.write_command(codec.light(self.profile.key, enabled), admit=True)

    async def lights_on(self) -> None:
        if self.profile.key == "p1":
            raise NotImplementedError("Legacy light is a toggle only")
        await self._light_set(True)

    async def lights_off(self) -> None:
        if self.profile.key == "p1":
            raise NotImplementedError("Legacy light is a toggle only")
        await self._light_set(False)

    async def lights_toggle(self) -> None:
        if self.profile.key == "p2" and self._light is None:
            raise ValueError("Light state is unknown; choose on or off explicitly")
        await self._light_set(self._light.state == 0 if self._light else True)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(
            app.LEGACY_ALARM_ACTIONS
            if self.profile.key == "p1"
            else {**app.ALARM_ACTIONS, **app.APP_ALARM_LABELS}
        )

    def alarm_frame(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        flexible: bool = False,
        now: datetime | None = None,
        week_mask: int | None = None,
    ) -> bytes:
        self._admit()
        if flexible and (self.profile.key != "p1" or self.model != 67):
            raise ValueError("Flexible wake belongs to legacy model 67")
        if preset not in self.clock_alarm_preset_options:
            raise ValueError("Choose a supported alarm action")
        if any(type(day) is not int or day not in range(7) for day in weekdays) or len(
            set(weekdays)
        ) != len(weekdays):
            raise ValueError("Choose unique weekdays Monday 0 through Sunday 6")
        now = now or dt_util.now()
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        week = sum(1 << ((day + 2) % 7) for day in weekdays) if weekdays else 128
        if self.profile.key == "p2":
            week = codec.gain_week(week, scheduled, now)
        elif weekdays and week_mask is None:
            raise ValueError("Legacy Smart Sleep weekday schedules require the exact app week_mask")
        if week_mask is not None:
            week = week_mask
        action = (
            app.LEGACY_ALARM_ACTIONS[preset]
            if self.profile.key == "p1"
            else ({**app.ALARM_ACTIONS, **app.APP_ALARM_LABELS})[preset]
        )
        return codec.alarm(
            self.profile.key,
            enabled=enabled,
            week=week,
            action=action,
            hour=hour,
            minute=minute,
            flexible=flexible,
        )

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
        flexible: bool = False,
        week_mask: int | None = None,
    ) -> None:
        frame = self.alarm_frame(
            enabled=enabled,
            weekdays=weekdays,
            hour=hour,
            minute=minute,
            preset=preset,
            flexible=flexible,
            week_mask=week_mask,
        )
        session, client = self._session, self.client
        await self.write_command(frame, admit=True)
        if self.profile.key == "p1" and enabled:
            if await self._wait_cancel(self.profile.query_ms):
                return
            if session != self._session or client is not self.client:
                raise ConnectionError("Smart Sleep session ended before clock sync")
            await self.sync_clock()
        await self.refresh("alarm")

    async def sync_clock(self) -> None:
        if self.profile.key == "p2":
            self._admit()
        await self.write_command(
            codec.clock(self.profile.key, dt_util.now()), admit=self.profile.key == "p2"
        )

    async def refresh(self, kind: str) -> None:
        session, client = self._session, self.client
        if self.profile.key == "p1" or kind == "settings":
            if await self._wait_cancel(self.profile.query_ms):
                return
        if session != self._session or client is not self.client:
            raise ConnectionError("Smart Sleep session ended before query")
        await self.write_command(codec.query(self.profile.key, kind))

    async def refresh_all(self) -> None:
        await self.write_command(codec.query(self.profile.key, "settings"))
        await self.refresh("settings")
        if self.profile.key == "p2":
            await self.refresh("massage")
        await self.refresh("alarm")

    async def async_on_connect(self, session: ControllerSession) -> None:
        # The Android app requests MTU512 after350ms. Bleak/proxies negotiate
        # MTU themselves; every bed write here fits the default ATT payload20.
        protocol = firmware = ""
        client = self.client
        if client is None:
            raise ConnectionError("Smart Sleep is disconnected")
        for uuid in (codec.NAME, codec.FIRMWARE, codec.PROTOCOL):
            service_uuid = (
                "00001800-0000-1000-8000-00805f9b34fb"
                if uuid == codec.NAME
                else "0000180a-0000-1000-8000-00805f9b34fb"
            )
            char = next(
                (
                    char
                    for service in client.services
                    if service.uuid.lower() == service_uuid
                    if (char := service.get_characteristic(uuid)) is not None
                ),
                None,
            )
            if char is not None and "read" in char.properties:
                value = (
                    bytes(await client.read_gatt_char(char))
                    .decode("utf-8", errors="replace")
                    .rstrip("\x00")
                )
                if uuid == codec.FIRMWARE:
                    firmware = value
                elif uuid == codec.PROTOCOL:
                    protocol = value
        self._new_privacy = codec.privacy_compat(protocol, firmware)
        await self.start_notify()
        if self.profile.key == "p2":
            await self.write_command(codec.INITIALIZE)
        await self.refresh_all()

    @property
    def reads_light_state_on_connect(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._notify is not None:
            return
        client = self.client
        if client is None:
            raise ConnectionError("Smart Sleep is disconnected")
        char = self._role(codec.NOTIFY)
        if not {"notify", "indicate"}.intersection(char.properties):
            raise ConnectionError("Smart Sleep requires its notification channel")
        self._session += 1
        session = self._session
        self._replies = codec.Replies()
        self._notify = char
        try:
            await client.start_notify(
                char, lambda sender, data: self._notification(sender, data, session, client)
            )
        except BaseException:
            self._end_session()
            raise

    def _notification(
        self, sender: BleakGATTCharacteristic, data: bytearray, session: int, client: object
    ) -> None:
        if (
            session != self._session
            or self.client is not client
            or self.client is None
            or not self.client.is_connected
            or self._notify is None
            or sender.handle != self._notify.handle
        ):
            return
        raw = bytes(data)
        self.forward_raw_notification(codec.NOTIFY, raw)
        now = monotonic()
        if now - self._partial_at > 1:
            self._replies = codec.Replies()
        for frame in self._replies.feed(raw, self.profile.key):
            parsed = codec.parse(frame, self.profile.key, new_privacy=self._new_privacy)
            self._publish(parsed)
        self._partial_at = now

    def _publish(self, parsed: codec.State | None) -> None:
        if isinstance(parsed, codec.SettingsState):
            self.forward_controller_state_updates(
                keys.PRIVACY("on" if parsed.privacy else "off"),
                keys.SENSITIVITY(str(parsed.sensitivity)),
                keys.ANTISNORE(str(parsed.antisnore_value) if parsed.antisnore else "off"),
            )
            parsed = parsed.massage
        if isinstance(parsed, codec.MassageState):
            self._massage = parsed
            self.forward_controller_state_updates(
                keys.MASSAGE_ON(parsed.on),
                keys.WAVE(str(parsed.wave)),
                keys.HEAD(str(parsed.head)),
                keys.FOOT(str(parsed.foot)),
                keys.TIMER(str(parsed.timer_index + 1) if parsed.on else None),
            )
        elif isinstance(parsed, codec.LightState):
            self._light = parsed
            self.forward_controller_state_updates(
                UNDER_BED_LIGHTS_ON(parsed.on), keys.BRIGHTNESS(parsed.brightness)
            )
        elif isinstance(parsed, codec.AlarmState):
            self.forward_controller_state_updates(keys.ALARM_ON(parsed.enabled))
            if parsed.week is not None:
                self.forward_controller_state_updates(
                    keys.ALARM_WEEK(parsed.week),
                    keys.ALARM_ACTION(parsed.action),
                    keys.ALARM_TIME(
                        ":".join(f"{v:02}" for v in parsed.time) if parsed.time else None
                    ),
                )
            if parsed.flexible is not None:
                self.forward_controller_state_updates(keys.FLEXIBLE(parsed.flexible))
        elif isinstance(parsed, codec.AIZeroState):
            self.forward_controller_state_updates(
                keys.AI_STATUS(parsed.status), keys.AI_SCORE(parsed.score)
            )

    def _end_session(self) -> None:
        self._session += 1
        self._notify = None
        self._replies = codec.Replies()
        self._massage = None
        self._light = None
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            keys.MASSAGE_ON(None),
            keys.ALARM_ON(None),
            keys.PRIVACY(None),
            keys.ANTISNORE(None),
            keys.SENSITIVITY(None),
            keys.WAVE(None),
            keys.HEAD(None),
            keys.FOOT(None),
            keys.TIMER(None),
            keys.ALARM_WEEK(None),
            keys.ALARM_ACTION(None),
            keys.ALARM_TIME(None),
            keys.FLEXIBLE(None),
            keys.BRIGHTNESS(None),
            keys.AI_STATUS(None),
            keys.AI_SCORE(None),
        )

    async def stop_notify(self) -> None:
        char, client = self._notify, self.client
        self._end_session()
        if char is not None and client is not None and client.is_connected:
            await client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._end_session()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(str(key), str(key), key, "mdi:information-outline")
            for key in (
                keys.MODEL,
                keys.ALARM_WEEK,
                keys.ALARM_ACTION,
                keys.ALARM_TIME,
                *((keys.BRIGHTNESS,) if self.profile.key == "p2" else ()),
                *((keys.AI_STATUS, keys.AI_SCORE) if self.model == 8 else ()),
            )
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(str(key), str(key), key, "mdi:information-outline")
            for key in (
                keys.MASSAGE_ON,
                keys.ALARM_ON,
                *((keys.FLEXIBLE,) if self.model == 67 and self.profile.key == "p1" else ()),
            )
        )


async def _local_child(ctrl: BedController, option: str) -> None:
    require_controller(ctrl, SmartSleepController).select_child(option)


async def build_controller(ctx: BuildContext) -> SmartSleepController:
    # GATT service identity never selects the app or dialect. Setup stores the
    # explicit format, or auto may use only this app's fresh scan predicate.
    variant = ctx.variant
    detected = app.advertisement(
        ctx.advertisement_name or ctx.live_device_name or "",
        ctx.manufacturer_data or {},
        ctx.coordinator.address,
    )
    if variant in (None, "auto"):
        variant = detected.format if detected else "p1"
    if variant not in app.PROFILES:
        raise ValueError("Choose Smart Sleep P1 or P2")
    model = int(ctx.data.get(CONF_PRODUCT_TYPE, detected.model if detected else 0))
    return SmartSleepController(ctx.coordinator, app.PROFILES[variant], model)
