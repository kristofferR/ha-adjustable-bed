"""Rize Home's product controls and connection-owned shared sender.

The Android manager has one replaceable repeat timer and one parser callback.
HA keeps those effects inside a captured connection and command, never lets an
old timer target a new link, and releases movement on cancellation as on UP.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.exc import BleakError

from ...card import CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY
from ...controller_state import StateKey
from ...profiles import rize_home as p
from ..base import BedController, ProfileExecution
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    ProductButtonSpec,
)
from ..okin_nframe import OkinNFrameController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext
    from ..lifecycle import ControllerSession

SOURCE: Final = StateKey[str | None]("rize_home_source")
TIMER: Final = StateKey[int | None]("rize_home_timer_index")
ACTIVE: Final = StateKey[bool | None]("rize_home_active")
COMBINED: Final = StateKey[int | None]("rize_home_combined_intensity")
HEAD: Final = StateKey[int | None]("rize_home_head_intensity")
FOOT: Final = StateKey[int | None]("rize_home_foot_intensity")
MODE: Final = StateKey[int | None]("rize_home_mode")


@dataclass(frozen=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class RizeHomeController(ProfileExecution[p.RizeHomeProfile], OkinNFrameController):
    """The explicit Remedy III or Contempo IV screen over Okin records."""

    def __init__(self, coordinator: AdjustableBedCoordinator, variant: str = "remedy_iii") -> None:
        super().__init__(coordinator)
        # Auto is the documented default layout only after the user selects
        # this app. Shared smartbed names never infer the app or product.
        self.profile = p.PROFILES["remedy_iii" if variant == "auto" else variant]
        retained = getattr(coordinator, "rize_home_source", "button")
        coordinator.rize_home_source = "speak" if retained == "speak" else "button"
        self._link: _Link | None = None
        self._notifying = False
        self._timer = 0

    @property
    def _source(self) -> p.Source:
        return self._coordinator.rize_home_source

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, p.REFRESH_MS

    @property
    def control_characteristic_uuid(self) -> str:
        return p.WRITE_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def allow_position_polling_during_commands(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.memory_slot_count)

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def has_bed_height_support(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return "reading" in self.profile.presets

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return int("memory" in self.profile.presets)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self.memory_slot_count)

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self.profile.combined_massage

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return not self.profile.combined_massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return not self.profile.combined_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return not self.profile.combined_massage

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # The app labels its main back actuator Head and the legs actuator Foot.
        labels = {"head": "back", "foot": "legs", "head_tilt": "head", "elevate": "bed_height"}
        return tuple(
            MotorControlSpec(
                key=labels.get(axis, axis),
                translation_key=labels.get(axis, axis),
                open_fn=lambda c, a=axis: _rize(c).action(f"{a}_up"),
                close_fn=lambda c, a=axis: _rize(c).action(f"{a}_down"),
                stop_fn=lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", stop_scope="side"),
            )
            for axis in self.profile.axes
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*self._button_actions(), *(f"voice_{key}" for key in p.VOICE_ACTIONS))

    def _button_actions(self) -> tuple[str, ...]:
        intensity = (
            ("massage_up", "massage_down")
            if self.profile.combined_massage
            else (
                "massage_head_up",
                "massage_head_down",
                "massage_foot_up",
                "massage_foot_down",
                "massage_mode",
            )
        )
        return (
            *(f"{axis}_{d}" for axis in self.profile.axes for d in ("up", "down")),
            *self.profile.presets,
            *intensity,
            "massage_toggle",
            "massage_timer",
            "light",
            "motion_on",
            "motion_off",
            "reset_memories",
            "query",
            "stop",
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_anti_snore": "anti_snore",
            "preset_lounge": "leisure",
            "preset_reading": "reading",
            "preset_memory_1": "memory",
            "massage_all_toggle": "massage_toggle",
            "massage_all_up": "massage_up",
            "massage_all_down": "massage_down",
            "massage_head_up": "massage_head_up",
            "massage_head_down": "massage_head_down",
            "massage_foot_up": "massage_foot_up",
            "massage_foot_down": "massage_foot_down",
            "massage_mode_step": "massage_mode",
            "toggle_light": "light",
        }.get(key)
        return ControllerHoldSpec(action) if action in self._button_actions() else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "rize_home_timer",
                "Cycle massage timer",
                lambda c: _rize(c).action("massage_timer"),
                translation_key="rize_home_timer",
                card=CARD_MASSAGE,
                hold=ControllerHoldSpec("massage_timer"),
                scheduler_resource="*",
            ),
            ControllerButtonSpec(
                "rize_home_query",
                "Refresh massage state",
                lambda c: _rize(c).action("query"),
                translation_key="rize_home_query",
                card=CARD_MASSAGE,
                scheduler_resource="*",
            ),
        ]
        for action in ("motion_on", "motion_off", "reset_memories"):
            specs.append(
                ControllerButtonSpec(
                    f"rize_home_{action}",
                    action.replace("_", " "),
                    lambda c, a=action: _rize(c).action(a),
                    translation_key=f"rize_home_{action}",
                    scheduler_resource="*",
                    card=CARD_UTILITY,
                )
            )
        for preset in self.profile.programmable:
            specs.append(
                ControllerButtonSpec(
                    f"rize_home_save_{preset}",
                    f"Save {preset}",
                    lambda c, a=preset: _rize(c).program_preset(a),
                    translation_key=f"rize_home_save_{preset}",
                    scheduler_resource="*",
                    card=CARD_PRESETS,
                )
            )
        # The common voice dispatcher reaches controls absent from a product's
        # page. Keep those explicit, opt-in app actions, not inferred motors.
        specs.extend(
            ProductButtonSpec(
                f"rize_home_voice_{action}",
                f"Voice action: {action.replace('_', ' ')}",
                lambda c, a=action: _rize(c).action(f"voice_{a}"),
                scheduler_resource="*",
                hold=ControllerHoldSpec(f"voice_{action}"),
                invalidates_position=action in p.MOTOR_ACTIONS,
            )
            for action in p.VOICE_ACTIONS
        )
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            ControllerSelectSpec(
                "rize_home_source",
                "rize_home_source",
                SOURCE,
                ("button", "speak"),
                lambda c, value: _rize(c).select_source(value),
            ),
        )

    def _select_source(self, value: str) -> None:
        if value not in ("button", "speak"):
            raise ValueError("Unknown Rize Home command source")
        self._coordinator.rize_home_source = "button" if value == "button" else "speak"
        self.forward_controller_state_updates(SOURCE(self._source))

    async def select_source(self, value: str) -> None:
        self._select_source(value)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        values = (("timer_index", TIMER),)
        values += (
            (("combined_intensity", COMBINED),)
            if self.profile.combined_massage
            else (
                ("head_intensity", HEAD),
                ("foot_intensity", FOOT),
                ("mode", MODE),
            )
        )
        return tuple(
            ControllerStateSensorSpec(
                f"rize_home_{key}",
                f"rize_home_{key}",
                state,
                "mdi:vibrate",
                card=CARD_MASSAGE,
            )
            for key, state in values
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "rize_home_active",
                "rize_home_active",
                ACTIVE,
                "mdi:vibrate",
                card=CARD_MASSAGE,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "com.okin.rize 1.1.2 (12)",
            "product": self.profile.name,
            "source": self._source,
            "notifying": self._notifying,
            "hardware": "unverified",
        }

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("Rize Home BLE session changed or disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("Rize Home is disconnected")
        service = next((s for s in client.services if s.uuid.lower() == p.SERVICE_UUID), None)
        chars = {c.uuid.lower(): c for c in service.characteristics} if service else {}
        write, notify = chars.get(p.WRITE_UUID), chars.get(p.NOTIFY_UUID)
        if (
            write is None
            or "write-without-response" not in write.properties
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError("Rize Home requires its exact UART write and notification roles")
        self._link = _Link(client, write, notify)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            state = p.parse_massage(self.profile, bytes(data))
            if state is not None:
                self.forward_controller_state_updates(
                    TIMER(state.timer_index),
                    ACTIVE(state.active),
                    COMBINED(state.combined_intensity),
                    HEAD(state.head),
                    FOOT(state.foot),
                    MODE(state.mode),
                )

        for attempt in range(2):
            try:
                async with self._ble_lock:
                    self._live(link)
                    await link.client.start_notify(link.notify, receive)
                self._live(link)
                self._notifying = True
                return
            except BleakError:
                if attempt:
                    raise
                # Bleak owns CCCD enable/disable, including an already-enabled
                # channel. Retry only this subscription, bound to the same link.
                async with self._ble_lock:
                    self._live(link)
                    await link.client.stop_notify(link.notify)
                await _pause(p.NOTIFY_RETRY_MS / 1000, asyncio.Event())

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if notifying and link is not None and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._notify_callback = None
        self._timer += 1
        self.forward_controller_state_updates(
            SOURCE(self._source),
            TIMER(None),
            ACTIVE(None),
            COMBINED(None),
            HEAD(None),
            FOOT(None),
            MODE(None),
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        # Android settles 350 ms before MTU512 negotiation. HA's host/proxy
        # negotiates ATT MTU; all app frames fit even the minimum ATT payload.
        link = self._live()
        await _pause(p.MTU_SETTLE_MS / 1000, asyncio.Event())
        self._live(link)
        await session.async_start_notify()
        await self._burst(link, p.FRAMES["query"], self._coordinator.cancel_command)

    async def _write(self, link: _Link, frame: bytes, cancel: asyncio.Event) -> None:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                return
            self._record_command_trace(
                p.WRITE_UUID, frame, response=False, characteristic=link.write
            )
            async with asyncio.timeout(15):
                await link.client.write_gatt_char(link.write, frame, response=False)

    async def _repeat(
        self,
        link: _Link,
        frame: bytes,
        count: int,
        interval_ms: int,
        cancel: asyncio.Event,
        *,
        finish_burst: bool = False,
        start_at: float | None = None,
    ) -> None:
        self._live(link)
        self._timer += 1
        timer = self._timer
        loop = asyncio.get_running_loop()
        start = loop.time() if start_at is None else start_at
        failure: BleakError | TimeoutError | None = None
        for i in range(count):
            if i and await _pause(max(0, start + i * interval_ms / 1000 - loop.time()), cancel):
                return
            if timer != self._timer or cancel.is_set():
                return
            try:
                await self._write(link, frame, cancel)
            except (BleakError, TimeoutError) as error:
                if not finish_burst:
                    raise
                failure = failure or error
        if failure is not None:
            raise failure

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = p.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._repeat(
            self._live(),
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event if cancel_event is not None else self._coordinator.cancel_command,
        )

    async def _burst(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        start_at: float | None = None,
    ) -> None:
        await self._repeat(
            link,
            frame,
            len(p.ONCE_OFFSETS_MS),
            p.REFRESH_MS,
            cancel,
            start_at=start_at,
        )

    async def _poll(self, link: _Link, cancel: asyncio.Event) -> None:
        # Polls belong to the active intensity gesture, not a detached Android
        # page timer. Query starts replace the shared repeat schedule.
        loop = asyncio.get_running_loop()
        tick = loop.time() + p.POLL_MS / 1000
        while not await _pause(max(0, tick - loop.time()), cancel):
            await self._poll_tick(link, cancel, start_at=tick)
            tick += p.POLL_MS / 1000

    async def _poll_tick(
        self,
        link: _Link,
        cancel: asyncio.Event,
        *,
        start_at: float | None = None,
    ) -> None:
        offsets = self.profile.poll_query_offsets_ms
        loop = asyncio.get_running_loop()
        started = loop.time() if start_at is None else start_at
        if len(offsets) == 2:
            await self._repeat(link, p.FRAMES["query"], 1, p.REFRESH_MS, cancel)
            if await _pause(max(0, started + offsets[1] / 1000 - loop.time()), cancel):
                return
        # A pending plugin write does not restart the timer's nominal schedule.
        # Keep overdue writes ordered on the captured link, without detaching
        # unbounded Android Futures or allowing them beyond HA cancellation.
        await self._burst(link, p.FRAMES["query"], cancel, start_at=started + offsets[-1] / 1000)

    async def _release(self, link: _Link, source: p.Source, *, massage: bool = False) -> None:
        async def send() -> None:
            fresh = asyncio.Event()
            loop = asyncio.get_running_loop()
            released_at = loop.time()
            failure: BleakError | TimeoutError | None = None
            if massage:
                await _pause(p.RELEASE_STOP_MS / 1000, fresh)
            # Complete the source's scheduled STOP writes even if one fails.
            # At +500 ms a massage query replaces the third STOP write.
            try:
                await self._repeat(
                    link,
                    p.FRAMES["voice_stop" if source == "speak" else "stop"],
                    2 if massage else len(p.ONCE_OFFSETS_MS),
                    p.REFRESH_MS,
                    fresh,
                    finish_burst=True,
                )
            except (BleakError, TimeoutError) as error:
                failure = error
            if massage:
                await _pause(
                    max(
                        0,
                        released_at + (p.RELEASE_STOP_MS + p.RELEASE_QUERY_MS) / 1000 - loop.time(),
                    ),
                    fresh,
                )
                await self._burst(
                    link,
                    p.FRAMES["query"],
                    fresh,
                    start_at=released_at + (p.RELEASE_STOP_MS + p.RELEASE_QUERY_MS) / 1000,
                )
            if failure is not None:
                raise failure

        # The command retains its scheduler resource until captured-link
        # cleanup finishes, including when the caller task is cancelled.
        task = asyncio.create_task(send())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001 - propagated below
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Control is not available on this Rize Home route")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Hold duration must be an integer from 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.action(control, duration_ms=self.leased_hold_ms(duration_ms))

    async def action(self, control: str, *, duration_ms: int | None = None) -> None:
        self.validate_hold_control(control, duration_ms if duration_ms is not None else 1000)
        voice = control.startswith("voice_")
        action = control.removeprefix("voice_") if voice else control
        if voice:
            self._select_source("speak")  # The app's source flag is shared and sticky.
        source, link = self._source, self._live()
        cancel = self._coordinator.cancel_command
        if action == "stop":
            await self._release(link, source)
            return
        if action == "query":
            await self._burst(link, p.FRAMES[action], cancel)
            return
        light = action == "light"
        sensor = action in ("motion_on", "motion_off")
        reset = action == "reset_memories"
        duration = duration_ms or (
            p.SAVE_MS
            if sensor or reset
            else self.leased_hold_ms(self._coordinator.motor_pulse_count * p.REFRESH_MS)
        )
        held = not light and (action in p.MOTOR_ACTIONS or sensor or reset or source == "button")
        # A sensor voice action ends its six-second refresh without inventing
        # a release frame. The UI compound action has its own STOP path.
        release = (not voice or action in p.MOTOR_ACTIONS) and (
            not light or duration_ms is not None
        )
        massage = action.startswith("massage_")
        deadline = asyncio.timeout(duration / 1000)
        try:
            try:
                async with deadline, asyncio.TaskGroup() as tasks:
                    if held:
                        tasks.create_task(
                            self._repeat(
                                link,
                                p.FRAMES[action],
                                max(1, (duration + p.REFRESH_MS - 1) // p.REFRESH_MS),
                                p.REFRESH_MS,
                                cancel,
                            )
                        )
                    else:
                        tasks.create_task(self._burst(link, p.FRAMES[action], cancel))
                    if action in p.INTENSITY_ACTIONS and not voice:
                        tasks.create_task(self._poll(link, cancel))
                    if (
                        held
                        or duration_ms is not None
                        or action in p.INTENSITY_ACTIONS
                        and not voice
                    ):
                        await _pause(duration / 1000, cancel)
            except TimeoutError:
                if not deadline.expired():
                    raise
            except ExceptionGroup as errors:
                # A single transport failure remains the error the coordinator
                # understands, rather than a TaskGroup implementation detail.
                if len(errors.exceptions) == 1:
                    raise errors.exceptions[0] from None
                raise
        finally:
            if self._link is link:
                self._timer += 1
            if release:
                await self._release(link, source, massage=massage)

    async def program_preset(self, preset: str) -> None:
        if preset not in self.profile.programmable:
            raise ValueError("This Rize Home product cannot program that preset")
        await self.action(preset, duration_ms=p.SAVE_MS)

    async def _send_stop(self) -> None:
        await self._release(self._live(), self._source)

    async def stop_all(self) -> None:
        await self._send_stop()

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
        await self.action("head_tilt_up")

    async def move_head_down(self) -> None:
        await self.action("head_tilt_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("Rize Home has no separate feet actuator")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("Rize Home has no separate feet actuator")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_bed_height_up(self) -> None:
        await self.action("elevate_up")

    async def move_bed_height_down(self) -> None:
        await self.action("elevate_down")

    async def move_bed_height_stop(self) -> None:
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
        await self.action("leisure")

    async def preset_reading(self) -> None:
        await self.action("reading")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("Rize Home MEMORY is slot 1, not the artifact method number m5")
        await self.action("memory")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("Rize Home has one MEMORY action")
        await self.program_preset("memory")

    async def lights_toggle(self) -> None:
        await self.action("light")

    async def massage_toggle(self) -> None:
        await self.action("massage_toggle")

    async def massage_off(self) -> None:
        await self.action("voice_massage_off")

    async def massage_intensity_up(self) -> None:
        await self.action("massage_up")

    async def massage_intensity_down(self) -> None:
        await self.action("massage_down")

    async def massage_head_up(self) -> None:
        await self.action("massage_head_up")

    async def massage_head_down(self) -> None:
        await self.action("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self.action("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self.action("massage_foot_down")

    async def massage_mode_step(self) -> None:
        await self.action("massage_mode")


def _rize(controller: BedController) -> RizeHomeController:
    if not isinstance(controller, RizeHomeController):
        raise TypeError("This action requires Rize Home")
    return controller


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


async def build_controller(ctx: BuildContext) -> RizeHomeController:
    variant = ctx.variant or "remedy_iii"
    if variant == "auto":
        variant = "remedy_iii"
    if variant not in p.PROFILES:
        raise ValueError("Choose the Rize Home product explicitly")
    return RizeHomeController(ctx.coordinator, variant)
