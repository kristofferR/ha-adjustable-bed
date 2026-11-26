"""Sleeptime's single Nordic UART connection and app gestures."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.const import UnitOfTime
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_MASSAGE, CARD_PRESET_SAVE, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...command_scheduler import (
    command_frames_counted,
    current_command_context,
    note_frame_skipped,
    note_frame_written,
)
from ...const import NORDIC_UART_WRITE_CHAR_UUID
from ...controller_state import StateKey
from ...errors import BedNotConnectedError
from ...profiles import sleeptime as app
from ...profiles.okin_nframe import OkinNFrameProfile
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..catalog_buttons import save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from ..okin_nframe import OkinNFrameController
from .transport import gatt_roles

if TYPE_CHECKING:
    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

MASSAGE_REMAINING: Final = StateKey[int]("massage_remaining_seconds")
MASSAGE_HEAD: Final = StateKey[int]("head_massage_level")
MASSAGE_FOOT: Final = StateKey[int]("foot_massage_level")
MASSAGE_MODE: Final = StateKey[int]("massage_mode")
MASSAGE_TIMER_BAND: Final = StateKey[int]("massage_timer_band")

ALARM_TIME: Final = StateKey[str]("alarm_editor_time")
ALARM_ENABLED: Final = StateKey[bool]("alarm_editor_enabled")
ALARM_MODE: Final = StateKey[int]("alarm_editor_mode")
ALARM_DAYS: Final = StateKey[int]("alarm_editor_weekday_mask")
RAW_ALARM_DAYS: Final = StateKey[int]("alarm_reported_weekday_mask")
RAW_ALARM_OPEN: Final = StateKey[int]("alarm_reported_open")

_RELEASE_BUTTON = "sleeptime_release"


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class _HoldEnded(Exception):
    """The hold deadline passed while waiting for the write lock."""


async def _wait(cancel: asyncio.Event, seconds: float) -> bool:
    """True if cancellation ended the delay."""
    if cancel.is_set():
        return True
    if seconds <= 0:
        return False
    try:
        async with asyncio.timeout(seconds):
            await cancel.wait()
    except TimeoutError:
        return False
    return True


def _press(control: str) -> MotorCommandCallable:
    async def press(controller: BedController) -> None:
        await require_controller(controller, SleeptimeController).press_motor(control)

    return press


class SleeptimeController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
    """Controls a selected Sleeptime layout over its fixed UART write and status roles."""

    profile = app.PROFILE

    def __init__(self, coordinator: AdjustableBedCoordinator, selector: str) -> None:
        super().__init__(coordinator)
        self._write_with_response = False
        self.selector = selector
        self.layout = app.LAYOUTS[selector]
        self._link: Link | None = None
        self._pending_stop: Link | None = None
        self._cleanup_stop: tuple[Link, CommandContext] | None = None
        self._parser: codec.SingleRecordParser | None = None
        self._subscribed = False
        self._alarm_reply: asyncio.Future[codec.ShortAlarmReport] | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return NORDIC_UART_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def stop_on_active_sequential_link(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"selector": self.selector, "axes": self.layout.axes}

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or (expected is not None and link is not expected)
            or self.client is not link.client
            or not link.client.is_connected
        ):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        roles = gatt_roles(client.services)
        if roles is None:
            raise BedNotConnectedError("sleeptime_gatt")
        self._link = Link(client, *roles)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed:
            return
        for attempt in range(2):
            parser = codec.SingleRecordParser()
            self._parser = parser

            def receive(
                _sender: BleakGATTCharacteristic,
                data: bytearray,
                parser: codec.SingleRecordParser = parser,
            ) -> None:
                if (
                    self._link is link
                    and self._parser is parser
                    and self.client is link.client
                    and link.client.is_connected
                ):
                    raw = bytes(data)
                    self.forward_raw_notification(link.notify.uuid, raw)
                    self._receive(parser.feed(raw))

            try:
                async with self._ble_lock:
                    self._live(link)
                    await link.client.start_notify(link.notify, receive)
                self._live(link)
            except BleakError, TimeoutError:
                if self._parser is parser:
                    self._parser = None
                if attempt:
                    raise
                await asyncio.sleep(app.NOTIFY_RETRY_MS / 1000)
            else:
                self._subscribed = True
                return

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self._parser = None
        self._subscribed = False
        if link is not None and subscribed and link.client.is_connected:
            async with self._ble_lock:
                if self._link is link and self.client is link.client and link.client.is_connected:
                    await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = self._pending_stop = None
        self._cleanup_stop = None
        self._parser = None
        self._subscribed = False
        if self._alarm_reply is not None:
            self._alarm_reply.cancel()
        super().on_disconnect()

    def _receive(self, report: codec.MassageReport | codec.ShortAlarmReport | None) -> None:
        if isinstance(report, codec.MassageReport):
            self.forward_controller_state_updates(
                MASSAGE_REMAINING(report.seconds),
                MASSAGE_TIMER_BAND(
                    (report.seconds - 1) // 600 + 1 if 1 <= report.seconds <= 1800 else 0
                ),
                MASSAGE_HEAD(report.head),
                MASSAGE_FOOT(report.foot),
                MASSAGE_MODE(report.mode),
            )
        elif isinstance(report, codec.ShortAlarmReport):
            if self._alarm_reply is not None and not self._alarm_reply.done():
                self._alarm_reply.set_result(report)
            days, mode, hour, minute = self._editor_fields(report)
            self.forward_controller_state_updates(
                ALARM_TIME(f"{hour:02d}:{minute:02d}"),
                ALARM_ENABLED(report.week != 0 and report.enabled == 1),
                ALARM_MODE(mode),
                ALARM_DAYS(days),
                RAW_ALARM_DAYS(report.week),
                RAW_ALARM_OPEN(report.enabled),
            )

    @staticmethod
    def _editor_fields(report: codec.ShortAlarmReport) -> tuple[int, int, int, int]:
        if report.week == 0:
            return 0xFF, app.WAKE_MODES["massage"], 6, 30
        return report.week, report.mode, report.hour, report.minute

    async def _write(
        self,
        link: Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        deadline: float | None = None,
        track: bool = True,
        before_send: Callable[[], None] | None = None,
    ) -> None:
        def validate() -> None:
            self._live(link)
            if deadline is not None and asyncio.get_running_loop().time() + 1e-9 >= deadline:
                raise _HoldEnded
            if before_send is not None:
                before_send()

        await self._write_gatt_with_retry(
            link.write.uuid,
            frame,
            cancel_event=cancel,
            response=False,
            characteristic=link.write,
            expected_client=link.client,
            before_write=validate,
            track_command_write=track,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and await _wait(cancel, repeat_delay_ms / 1000):
                return
            await self._write(link, command, cancel)

    async def _stop_link(self, link: Link, *, track: bool) -> None:
        await asyncio.sleep(app.RELEASE_MS / 1000)
        await self._write(link, app.STOP, asyncio.Event(), track=track)
        if self._pending_stop is link:
            self._pending_stop = None

    async def _release(self, link: Link) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        try:
            await self._stop_link(link, track=False)
        except BedNotConnectedError:
            # The link can drop during the release delay.
            if self._link is link and self.client is link.client and link.client.is_connected:
                raise
            return
        if self._link is link and (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True
            self._cleanup_stop = (link, context)

    async def _send_stop(self) -> None:
        link, context = self._live(), current_command_context()
        if self._cleanup_stop is not None and context is not None:
            released_link, owner = self._cleanup_stop
            if (
                released_link is link
                and owner.cleanup_stop_sent
                and any(owner is previous for previous in context.preempted_contexts)
            ):
                owner.cleanup_stop_sent = False
                self._cleanup_stop = None
                note_frame_written(context.cancel_event)
                return
        if not CONTROLLER_GESTURE_RELEASE.get() or self._pending_stop is link:
            self._cleanup_stop = None
            with command_frames_counted():
                await self._stop_link(link, track=True)

    async def stop_all(self) -> None:
        await self._send_stop()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *(f"{axis}_{direction}" for axis in self.layout.axes for direction in ("up", "down")),
            *self.layout.presets,
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise self.not_supported(control)
        limit = (
            app.SAVE_MS - app.REFRESH_MS
            if control in self.layout.presets and control != "flat"
            else 60000
        )
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= limit
        ):
            raise ValueError(f"Choose a hold duration between 1 and {limit} ms")

    async def _held(self, frame: bytes, duration_ms: int) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        # After a failed release, clear the same live receiver before moving again.
        if self._pending_stop is link and not cancel.is_set():
            await self._stop_link(link, track=False)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        attempted = False

        def mark_attempt() -> None:
            nonlocal attempted
            attempted = True
            self._pending_stop = link
            self._cleanup_stop = None

        async def release() -> None:
            if attempted:
                await self._release(link)

        async with self.releasing(release):
            while not cancel.is_set() and (started := loop.time()) + 1e-9 < deadline:
                try:
                    await self._write(
                        link, frame, cancel, deadline=deadline, before_send=mark_attempt
                    )
                except _HoldEnded:
                    note_frame_skipped()
                    return
                if await _wait(
                    cancel, min(deadline, started + app.REFRESH_MS / 1000) - loop.time()
                ):
                    return

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        hold_ms = (
            self.leased_hold_ms(duration_ms) if control not in self.layout.presets else duration_ms
        )
        await self._held(codec.frame40(self.profile.keys[control], 1), hold_ms)

    async def press_motor(self, control: str) -> None:
        await self.hold_control(
            control, min(60000, self._coordinator.motor_pulse_count * app.REFRESH_MS)
        )

    async def _preset(self, preset: str) -> None:
        await self.hold_control(preset, app.REFRESH_MS)

    async def _save(self, preset: str) -> None:
        if preset == "flat" or preset not in self.layout.presets:
            raise self.not_supported(preset)
        await self._held(codec.frame40(app.PRESETS[preset], 1), app.SAVE_MS)

    async def _reset(self) -> None:
        if not self.supports_preset_flat:
            raise self.not_supported("reset saved positions")
        # Send the chord once, then release it under the same command ownership.
        await self._held(app.RESET, app.REFRESH_MS)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                "tilt" if axis == "head_tilt" else axis,
                axis,
                _press(f"{axis}_up"),
                _press(f"{axis}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    release_button_key=_RELEASE_BUTTON,
                    press_hold_ms=None,
                    stop_scope="side",
                ),
            )
            for axis in self.layout.axes
        )

    async def move_head_up(self) -> None:
        await self.press_motor("back_up")

    async def move_head_down(self) -> None:
        await self.press_motor("back_down")

    async def move_feet_up(self) -> None:
        await self.press_motor("legs_up")

    async def move_feet_down(self) -> None:
        await self.press_motor("legs_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_feet_stop = stop_all
    move_legs_stop = stop_all

    @property
    def supports_preset_flat(self) -> bool:
        return "flat" in self.layout.presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.layout.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.layout.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_reading(self) -> None:
        await self._preset("reading")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._preset(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._save(f"memory_{memory_num}")

    @property
    def supports_lights(self) -> bool:
        return True

    async def lights_toggle(self) -> None:
        await self.write_command(app.LIGHT)

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    async def _massage(self, action: str) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        word, delay = app.MASSAGE[action]
        await self._write(link, codec.frame40(word), cancel)
        if not await _wait(cancel, delay / 1000):
            await self._write(link, app.MASSAGE_QUERY, cancel, track=False)

    async def massage_toggle(self) -> None:
        await self._massage("massage_toggle")

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        await self._clock(asyncio.Event(), track=False)

    async def sync_clock(self) -> None:
        await self._clock(self._coordinator.cancel_command, track=True)

    async def _clock(self, cancel: asyncio.Event, *, track: bool) -> None:
        link = self._live()
        frame = app.clock(dt_util.now())
        await self._write(link, frame, cancel, track=track)
        if not await _wait(cancel, app.CLOCK_REPEAT_MS / 1000):
            await self._write(link, frame, cancel, track=track)

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(wake_actions=self.layout.wake_actions, weekdays=True, resource="*")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        if alarm.enabled:
            frame = app.alarm(
                app.WAKE_MODES[alarm.wake_action],
                app.day_mask(alarm),
                alarm.hour,
                alarm.minute,
                True,
            )
        else:
            # Like the app's off gesture, change open while retaining the editor values.
            reply: asyncio.Future[codec.ShortAlarmReport] = (
                asyncio.get_running_loop().create_future()
            )
            self._alarm_reply = reply
            try:
                await self._write(link, app.ALARM_QUERY, cancel, track=False)
                if cancel.is_set():
                    return
                async with asyncio.timeout(2):
                    report = await reply
            finally:
                self._alarm_reply = None
            days, mode, hour, minute = self._editor_fields(report)
            if (
                mode not in (app.WAKE_MODES[action] for action in self.layout.wake_actions)
                or hour > 23
                or minute > 59
            ):
                raise ValueError("Sleeptime returned unsupported alarm settings")
            if days == 0x80:
                days = app.once_mask(alarm.reference_time, hour, minute)
            frame = app.alarm(mode, days, hour, minute, False)
        loop = asyncio.get_running_loop()
        start = loop.time()
        for delay, action in app.ALARM_WRITES:
            if await _wait(cancel, start + delay / 1000 - loop.time()):
                return
            await self._write(
                link, frame if action == "set" else app.ALARM_QUERY, cancel, track=action == "set"
            )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *(
                ControllerButtonSpec(
                    f"sleeptime_{action}",
                    label,
                    lambda c, a=action: require_controller(c, SleeptimeController)._massage(a),
                    translation_key=f"sleeptime_{action}",
                    scheduler_resource="*",
                    card=CARD_MASSAGE,
                )
                for action, label in (
                    ("massage_timer", "Cycle massage timer"),
                    ("massage_head_up", "Increase head massage"),
                    ("massage_head_down", "Decrease head massage"),
                    ("massage_foot_up", "Increase foot massage"),
                    ("massage_foot_down", "Decrease foot massage"),
                    ("massage_mode_next", "Next massage mode"),
                    ("massage_mode_previous", "Previous massage mode"),
                )
            ),
            *(
                save_button(
                    f"sleeptime_save_{preset}",
                    label,
                    lambda c, p=preset: require_controller(c, SleeptimeController)._save(p),
                    scheduler_resource="*",
                )
                for preset, label in (
                    ("tv", "Save TV position"),
                    ("zero_g", "Save zero gravity position"),
                    ("reading", "Save reading position"),
                    ("anti_snore", "Save anti-snore position"),
                )
                if preset in self.layout.presets
            ),
            *(
                (
                    ControllerButtonSpec(
                        "sleeptime_reset_memory",
                        "Reset saved positions",
                        lambda c: require_controller(c, SleeptimeController)._reset(),
                        translation_key="sleeptime_reset_memory",
                        scheduler_resource="*",
                        requires_confirmation=True,
                        card=CARD_PRESET_SAVE,
                    ),
                )
                if self.supports_preset_flat
                else ()
            ),
            *(
                ControllerButtonSpec(
                    f"sleeptime_query_{kind}",
                    label,
                    lambda c, f=frame: c.write_command(f),
                    translation_key=f"sleeptime_query_{kind}",
                    scheduler_resource="*",
                    diagnostic=True,
                    card=CARD_UTILITY,
                )
                for kind, label, frame in (
                    ("massage", "Refresh massage", app.MASSAGE_QUERY),
                    ("alarm", "Refresh alarm", app.ALARM_QUERY),
                )
            ),
            ControllerButtonSpec(
                _RELEASE_BUTTON,
                "Release held control",
                lambda c: c.stop_all(),
                translation_key=_RELEASE_BUTTON,
                release_only=True,
                card=CARD_HIDDEN,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "sleeptime_massage_status",
                "sleeptime_massage_status",
                MASSAGE_REMAINING,
                "mdi:timer-outline",
                native_unit_of_measurement=UnitOfTime.SECONDS,
                attribute_keys=(MASSAGE_TIMER_BAND, MASSAGE_HEAD, MASSAGE_FOOT, MASSAGE_MODE),
                entity_registry_enabled_default=True,
                card=CARD_MASSAGE,
                entity_category=None,
            ),
            ControllerStateSensorSpec(
                "sleeptime_alarm_status",
                "sleeptime_alarm_status",
                ALARM_TIME,
                "mdi:alarm",
                attribute_keys=(
                    ALARM_ENABLED,
                    ALARM_DAYS,
                    ALARM_MODE,
                    RAW_ALARM_DAYS,
                    RAW_ALARM_OPEN,
                ),
                entity_registry_enabled_default=True,
                card=CARD_UTILITY,
                entity_category=None,
            ),
        )


async def build_controller(ctx: BuildContext) -> SleeptimeController:
    if ctx.variant is None or ctx.variant not in app.LAYOUTS:
        raise ValueError("Choose the Sleeptime Bluetooth name prefix in setup")
    return SleeptimeController(ctx.coordinator, ctx.variant)
