"""Superior Sleep's product UI, input timing and connection-owned sender."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.util import dt as dt_util

from ... import errors
from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE
from ...command_scheduler import note_frame_skipped, note_frame_written
from ...profiles import superior_sleep as p
from ..base import BedController, ProfileExecution
from ..cancellation import cancellable, settled
from ..catalog_buttons import catalog_button, save_button, save_name
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from ..okin_nframe import OkinNFrameController
from . import state_keys as s

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext
    from ..lifecycle import ControllerSession


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    generation: int


@dataclass(slots=True)
class _Window:
    deadline: float
    started: bool = False


class SuperiorSleepController(ProfileExecution[p.SuperiorSleepProfile], OkinNFrameController):
    """One explicit SS350/SS650 product, never inferred from its transport."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, product: str = "ss350", name: str = ""
    ) -> None:
        super().__init__(coordinator)
        if product not in p.PROFILES:
            raise errors.invalid("superior_sleep_product")
        self.profile = p.PROFILES[product]
        self.transport = p.transport_for_name(name)
        self._link: _Link | None = None
        self._notifying = False
        self._notify_owner: object | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self.transport.write

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        # On/off both use the same catalog shape, with button release timing.
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in self.profile.presets

    @property
    def supports_memory_presets(self) -> bool:
        return "memory_1" in self.profile.presets

    @property
    def memory_slot_count(self) -> int:
        return 2 if self.supports_memory_presets else 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=("wake_mode_1", "wake_mode_2"), weekdays=True, resource="*"
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, p.REFRESH_MS

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # App Head/Foot are the main back/legs row. Its SS650 Back label is
        # a separate neckTilt wire builder, not a measured anatomical position.
        labels = {"head": "back", "foot": "legs", "back": "head", "lumbar": "lumbar"}
        return tuple(
            MotorControlSpec(
                key=labels[axis],
                translation_key=labels[axis],
                open_fn=lambda c, a=axis: _bed(c).action(f"{a}_up"),
                close_fn=lambda c, a=axis: _bed(c).action(f"{a}_down"),
                stop_fn=lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", stop_scope="side"),
            )
            for axis in self.profile.axes
        )

    @property
    def button_actions(self) -> tuple[str, ...]:
        return (
            *(f"{a}_{d}" for a in self.profile.axes for d in ("up", "down")),
            *self.profile.presets,
            *self.profile.adjustments,
            "massage_on",
            "massage_off",
            "light",
            "motion_on",
            "motion_off",
            "reset_memories",
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        # Speech alternatives are exposed by the typed action, never duplicated
        # as entities or made available on the ten button-only adjustments.
        return tuple(
            k for k in self.button_actions if k not in ("reset_memories", "motion_on", "motion_off")
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_anti_snore": "anti_snore",
            "preset_lounge": "lounge",
            "preset_memory_1": "memory_1",
            "preset_memory_2": "memory_2",
            "toggle_light": "light",
        }.get(key)
        return ControllerHoldSpec(action) if action in self.held_control_options else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec] = []
        for action in (
            *self.profile.adjustments,
            "speech_stop",
            "query_massage",
            "query_alarm",
            "reset_memories",
        ):
            diagnostic = action.startswith("query_")
            spec = catalog_button(
                f"superior_sleep_{action}",
                p.LABELS[action],
                lambda c, a=action: _bed(c).action(a),
                scheduler_resource="*",
                diagnostic=diagnostic,
                enabled=not diagnostic and action not in ("speech_stop", "reset_memories"),
                requires_confirmation=action == "reset_memories",
                hold=ControllerHoldSpec(action) if action in self.held_control_options else None,
            )
            assert spec is not None
            specs.append(spec)
        specs.extend(
            save_button(
                f"superior_sleep_save_{action}",
                save_name(action),
                lambda c, a=action: _bed(c).program_preset(a),
                scheduler_resource="*",
            )
            for action in self.profile.programmable
            if not action.startswith("memory_")
        )
        return tuple(specs)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "superior_sleep_motion",
                "superior_sleep_motion",
                lambda c, on: _bed(c).action("motion_on" if on else "motion_off"),
                state_key=s.MOTION,
                assumed_state=True,
                icon="mdi:motion-sensor",
            ),
            # The app's Massage on and Massage off keys.
            ControllerSwitchSpec(
                "superior_sleep_massage",
                "superior_sleep_massage",
                lambda c, on: _bed(c).action("massage_on" if on else "massage_off"),
                state_key=s.MASSAGE,
                assumed_state=True,
                icon="mdi:vibrate",
                card=CARD_MASSAGE,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            massage_timer_sensor_spec(
                "superior_sleep_timer_minutes",
                "superior_sleep_timer_minutes",
                s.TIMER,
                card=CARD_MASSAGE,
            ),
        ) + tuple(
            ControllerStateSensorSpec(
                f"superior_sleep_{name}",
                f"superior_sleep_{name}",
                key,
                "mdi:vibrate",
                entity_registry_enabled_default=True,
                entity_category=None,
                card=CARD_MASSAGE,
            )
            for name, key in (
                ("mode", s.MODE),
                ("head_level", s.HEAD),
                ("foot_level", s.FOOT),
            )
        ) + (
            ControllerStateSensorSpec(
                "superior_sleep_alarm_hour",
                "superior_sleep_alarm_hour",
                s.ALARM_HOUR,
                "mdi:alarm",
                attribute_keys=(s.ALARM_MINUTE, s.ALARM_MASK, s.ALARM_SELECTOR, s.ALARM_DAYS),
            ),
            ControllerStateSensorSpec(
                "superior_sleep_timer_seconds",
                "superior_sleep_timer_seconds",
                s.SECONDS,
                "mdi:timer-outline",
                native_unit_of_measurement="s",
                device_class=SensorDeviceClass.DURATION,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "superior_sleep_alarm_enabled",
                "superior_sleep_alarm_enabled",
                s.ALARM_ENABLED,
                "mdi:alarm",
            ),
        )

    def _current(self, link: _Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.connection_generation == link.generation
            and self._coordinator.controller is self
        )

    def _live(self) -> _Link:
        if self._link is None or not self._current(self._link):
            raise errors.failed("superior_sleep_session")
        return self._link

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise errors.failed("superior_sleep_session")
        service = next(
            (item for item in client.services if item.uuid.lower() == self.transport.service), None
        )
        write = (
            next(
                (c for c in service.characteristics if c.uuid.lower() == self.transport.write), None
            )
            if service
            else None
        )
        notify = (
            next(
                (c for c in service.characteristics if c.uuid.lower() == self.transport.notify),
                None,
            )
            if service
            else None
        )
        if write is None or notify is None:
            raise errors.failed("superior_sleep_gatt")
        self._link = _Link(client, write, notify, self._coordinator.connection_generation)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return
        owner = self._notify_owner = object()

        def receive(sender: BleakGATTCharacteristic, value: bytearray) -> None:
            if not self._current(link) or self._notify_owner is not owner:
                return
            data = bytes(value)
            self.forward_raw_notification(sender.uuid, data)
            if (state := p.parse_massage(data)) is not None:
                self.forward_controller_state_updates(
                    s.TIMER(state.timer_minutes),
                    s.SECONDS(state.timer_seconds),
                    s.MODE(state.mode),
                    s.HEAD(state.head_level),
                    s.FOOT(state.foot_level),
                )
            elif (alarm := p.parse_alarm(data)) is not None:
                # No round trip to the outbound mask: these are app display fields.
                self.forward_controller_state_updates(
                    s.ALARM_HOUR(alarm.alarm_hour),
                    s.ALARM_MINUTE(alarm.alarm_minute),
                    s.ALARM_MASK(alarm.alarm_mask),
                    s.ALARM_SELECTOR(alarm.alarm_selector),
                    s.ALARM_ENABLED(alarm.alarm_enabled),
                    s.ALARM_DAYS(alarm.display_days),
                )

        try:
            async with self._ble_lock:
                if not self._current(link):
                    raise errors.failed("superior_sleep_session")
                await link.client.start_notify(link.notify, receive)
        except BaseException:
            if self._notify_owner is owner:
                self._notify_owner = None
            raise
        if self._current(link):
            self._notifying = True

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        # Unsubscribing does not prove physical disconnection. Bleak can fail
        # to close the link, and the coordinator then retains this controller.
        self._notifying = False
        self._notify_owner = None
        self._notify_callback = None
        if (
            link is not None
            and notifying
            and self.client is link.client
            and link.client.is_connected
        ):
            async with self._ble_lock:
                if self._current(link):
                    await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._notify_owner = None
        self._notify_callback = None
        if self._coordinator.controller is self:
            self.forward_controller_state_updates(
                s.TIMER(None),
                s.SECONDS(None),
                s.MODE(None),
                s.HEAD(None),
                s.FOOT(None),
                s.MOTION(None),
                s.MASSAGE(None),
                s.ALARM_HOUR(None),
                s.ALARM_MINUTE(None),
                s.ALARM_MASK(None),
                s.ALARM_SELECTOR(None),
                s.ALARM_DAYS(None),
                s.ALARM_ENABLED(None),
            )

    async def async_on_connect(self, session: ControllerSession) -> None:
        # The coordinator advances its public generation after discovery and
        # before this hook. Bind the resolved GATT roles to that ready session.
        if self._link is None or not session.is_current():
            raise errors.failed("superior_sleep_session")
        self._link = replace(self._link, generation=self._coordinator.connection_generation)
        await session.async_start_notify()
        link = self._live()
        start = asyncio.get_running_loop().time()
        await self._burst(link, p.clock(dt_util.now()), self._coordinator.cancel_command)
        await cancellable(
            asyncio.sleep(
                max(0, start + p.QUERY_DELAY_MS / 1000 - asyncio.get_running_loop().time())
            ),
            self._coordinator.cancel_command,
        )
        await self._burst(link, p.FRAMES["query_massage"], self._coordinator.cancel_command)

    async def _send(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        window: _Window | None = None,
        count_delivery: bool = True,
    ) -> bool:
        dispatched = False
        held_back = False
        owner_task = asyncio.current_task()
        try:
            async with self._ble_lock:

                async def write() -> bool:
                    nonlocal dispatched, held_back
                    # settled schedules a task, so ownership, cancellation and
                    # the held window must be checked inside that task too.
                    if window is not None and asyncio.get_running_loop().time() >= window.deadline:
                        if count_delivery and not window.started:
                            note_frame_skipped()  # The initial command never dispatched.
                            held_back = True
                        return False  # No refresh is needed outside its window.
                    if (
                        cancel.is_set()
                        or not self._current(link)
                        or owner_task is not None
                        and owner_task.cancelling()
                    ):
                        if count_delivery:
                            note_frame_skipped()
                            held_back = True
                        return False
                    self._record_command_trace(
                        self.transport.write, frame, response=False, characteristic=link.write
                    )
                    async with asyncio.timeout(15):
                        dispatched = True
                        if window is not None:
                            window.started = True
                        await link.client.write_gatt_char(link.write, frame, response=False)
                        if count_delivery:
                            note_frame_written(cancel)
                    return True

                return await settled(write())
        except asyncio.CancelledError:
            # Cancellation can arrive while the final intended frame is still
            # waiting for the lock, or before its settled task starts.
            if (
                count_delivery
                and not dispatched
                and not held_back
                and (
                    window is None
                    or not window.started
                    or asyncio.get_running_loop().time() < window.deadline
                )
            ):
                note_frame_skipped()
            raise

    async def _burst(
        self, link: _Link, frame: bytes, cancel: asyncio.Event, *, count_delivery: bool = True
    ) -> None:
        failure: BleakError | TimeoutError | None = None
        loop = asyncio.get_running_loop()
        start = loop.time()
        for i in range(p.ONCE_COUNT):
            if i:
                try:
                    await cancellable(
                        asyncio.sleep(max(0, start + i * p.REFRESH_MS / 1000 - loop.time())), cancel
                    )
                except asyncio.CancelledError:
                    if count_delivery:
                        note_frame_skipped()
                    raise
            try:
                if not await self._send(link, frame, cancel, count_delivery=count_delivery):
                    break
            except asyncio.CancelledError:
                if count_delivery and i + 1 < p.ONCE_COUNT:
                    note_frame_skipped()
                raise
            except (BleakError, TimeoutError) as err:
                failure = failure or err
        if failure is not None:
            raise failure

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = p.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link, cancel = (
            self._live(),
            cancel_event if cancel_event is not None else self._coordinator.cancel_command,
        )
        for i in range(repeat_count):
            if i:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)
            if not await self._send(link, command, cancel):
                return

    async def _release(
        self,
        link: _Link,
        *,
        massage: bool = False,
        tail_frame: bytes | None = None,
        next_tick: float = 0,
        released_at: float | None = None,
    ) -> None:
        async def cleanup() -> None:
            fresh = asyncio.Event()
            failure: BleakError | TimeoutError | None = None
            if massage:
                loop = asyncio.get_running_loop()
                query_at = (
                    loop.time() if released_at is None else released_at
                ) + p.MASSAGE_RELEASE_MS / 1000
                # The app leaves its refresh timer running until the delayed
                # query replaces it, including any tick in this final window.
                if tail_frame is not None and next_tick < query_at:
                    await asyncio.sleep(max(0, next_tick - loop.time()))
                    try:
                        await self._send(
                            link,
                            tail_frame,
                            fresh,
                            window=_Window(query_at, started=True),
                            count_delivery=False,
                        )
                    except (BleakError, TimeoutError) as err:
                        failure = err
                await asyncio.sleep(max(0, query_at - loop.time()))
            try:
                await self._burst(
                    link,
                    p.FRAMES["query_massage" if massage else "stop"],
                    fresh,
                    count_delivery=False,
                )
            finally:
                if failure is not None:
                    raise failure

        await settled(cleanup())

    def validate_action(self, action: str, speech: bool = False) -> None:
        allowed = (
            p.SPEECH_ACTIONS
            if speech
            else (*self.button_actions, "stop", "speech_stop", "query_alarm", "query_massage")
        )
        if action not in allowed:
            raise errors.invalid("superior_sleep_control", control=action)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise errors.invalid("superior_sleep_control", control=control)
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise errors.invalid("superior_sleep_duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.action(control, duration_ms=self.leased_hold_ms(duration_ms))

    async def action(
        self, action: str, *, speech: bool = False, duration_ms: int | None = None
    ) -> None:
        self.validate_action(action, speech)
        link, cancel = self._live(), self._coordinator.cancel_command
        if action in ("stop", "speech_stop", "query_alarm", "query_massage"):
            await self._burst(
                link, p.FRAMES[action], asyncio.Event() if action.endswith("stop") else cancel
            )
            return
        sensor = action in ("motion_on", "motion_off")
        updates = (
            (s.MOTION(action == "motion_on"),)
            if sensor
            else (s.MASSAGE(action == "massage_on"),)
            if action in ("massage_on", "massage_off")
            else ()
        )
        if speech and action not in p.MOTORS and not sensor:
            # A spoken massage on or off is what the Massage switch shows.
            with self.sent_state(*updates, is_current=lambda: self._current(link)):
                await self._burst(link, p.FRAMES[action], cancel)
            return
        duration = (
            p.MOTION_MS
            if sensor
            else duration_ms
            if duration_ms is not None
            else (
                p.SAVE_MS
                if action == "reset_memories"
                else self.leased_hold_ms(self._coordinator.motor_pulse_count * p.REFRESH_MS)
            )
        )
        loop = asyncio.get_running_loop()
        start = loop.time()
        end_at, next_tick = start + duration / 1000, start
        window = _Window(end_at)
        with self.sent_state(*updates, is_current=lambda: self._current(link)):
            count = max(1, (duration + p.REFRESH_MS - 1) // p.REFRESH_MS)
            index = 0
            try:
                for index in range(count):
                    next_tick = start + (index + 1) * p.REFRESH_MS / 1000
                    if not await self._send(link, p.FRAMES[action], cancel, window=window):
                        return
                    await cancellable(
                        asyncio.sleep(max(0, min(next_tick, end_at) - loop.time())), cancel
                    )
            except asyncio.CancelledError:
                if index + 1 < count and loop.time() < end_at:
                    note_frame_skipped()
                raise
            finally:
                if not sensor:
                    massage = action.startswith(("massage_", "wave_"))
                    await self._release(
                        link,
                        massage=massage,
                        tail_frame=p.FRAMES[action] if massage and window.started else None,
                        next_tick=next_tick,
                        released_at=min(loop.time(), end_at),
                    )

    async def program_preset(self, preset: str) -> None:
        if preset not in self.profile.programmable:
            raise errors.invalid("superior_sleep_control", control=preset)
        await self.action(preset, duration_ms=p.SAVE_MS)

    async def sync_clock(self) -> None:
        await self._burst(self._live(), p.clock(dt_util.now()), self._coordinator.cancel_command)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        start = asyncio.get_running_loop().time()
        failure: BleakError | TimeoutError | None = None
        try:
            await self._burst(link, p.alarm(alarm), cancel)
        except (BleakError, TimeoutError) as err:
            failure = err
        try:
            await cancellable(
                asyncio.sleep(
                    max(0, start + p.QUERY_DELAY_MS / 1000 - asyncio.get_running_loop().time())
                ),
                cancel,
            )
            await self._burst(link, p.FRAMES["query_alarm"], cancel)
        except Exception:
            if failure is not None:
                raise failure from None
            raise
        if failure is not None:
            raise failure

    async def stop_all(self) -> None:
        # The scheduler owns cancellation. This local STOP never sets its event.
        await self._release(self._live())

    async def _send_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.action("head_up")

    async def move_back_down(self) -> None:
        await self.action("head_down")

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.action("foot_up")

    async def move_legs_down(self) -> None:
        await self.action("foot_down")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self.action("back_up")

    async def move_head_down(self) -> None:
        await self.action("back_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        raise errors.invalid("superior_sleep_control", control="feet_up")

    async def move_feet_down(self) -> None:
        raise errors.invalid("superior_sleep_control", control="feet_down")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self.action("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self.action("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self.action("flat")

    async def preset_zero_g(self) -> None:
        await self.action("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.action("anti_snore")

    async def preset_lounge(self) -> None:
        await self.action("lounge")

    async def preset_memory(self, memory_num: int) -> None:
        await self.action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self.program_preset(f"memory_{memory_num}")

    async def lights_toggle(self) -> None:
        await self.action("light")

    async def massage_off(self) -> None:
        await self.action("massage_off")


def _bed(controller: BedController) -> SuperiorSleepController:
    if not isinstance(controller, SuperiorSleepController):
        raise errors.invalid("superior_sleep_product")
    return controller


async def build_controller(ctx: BuildContext) -> SuperiorSleepController:
    product = ctx.variant
    if product in (None, "auto"):
        product = "ss350"
    name = ctx.data.get("ble_device_name") or ctx.live_device_name or ""
    return SuperiorSleepController(ctx.coordinator, product, str(name))
