"""Sven's property-selected link, captured release and local massage accounting."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError

from ...card import CARD_MASSAGE
from ...command_scheduler import (
    CommandKind,
    copy_context_without_command,
    current_command_context,
    note_frame_skipped,
)
from ...errors import BedNotConnectedError, failed, invalid
from ...profiles import sven as p
from ...profiles.richmat import Button
from ...state_keys import FOUNDATION_PRESET, MASSAGE_TIMER_MINUTES, massage_intensity
from ..base import BedController, require_controller
from ..cancellation import cancellable
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec, MotorControlSpec
from .fixed import FixedRichmatAppController, _Link

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


def select_link(client: BleakClient) -> _Link:
    """Known writable pairs first, then discovered order, within one service."""
    services = list(client.services)
    for service_uuid, char_uuid in p.TARGETS:
        for service in services:
            if service.uuid.lower() == service_uuid:
                for char in service.characteristics:
                    if char.uuid.lower() == char_uuid and {
                        "write",
                        "write-without-response",
                    }.intersection(char.properties):
                        return _Link(
                            client,
                            char,
                            next(
                                (c for c in service.characteristics if "notify" in c.properties),
                                None,
                            ),
                            False,
                        )
    for service in services:
        if service.uuid.lower().startswith(p.EXCLUDED_SERVICES):
            continue
        for char in service.characteristics:
            if {"write", "write-without-response"}.intersection(char.properties):
                return _Link(
                    client,
                    char,
                    next((c for c in service.characteristics if "notify" in c.properties), None),
                    False,
                )
    raise failed("sven_gatt")


async def _motor(axis: str, up: bool, c: BedController, ms: int | None = None) -> None:
    target = require_controller(c, SvenController)
    await target._move_with_stop(
        target._code(p.MOTOR_BUTTONS[axis][0 if up else 1]), duration_ms=ms
    )


async def _timed_motor(axis: str, c: BedController, up: bool, ms: int) -> None:
    await _motor(axis, up, c, ms)


async def _reconcile(rested: bool, c: BedController) -> None:
    require_controller(c, SvenController).confirm_massage_off(rested)


class SvenController(FixedRichmatAppController):
    """Reuse Richmat's encoder, motor methods, settled writes and release context."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        model = p.model_key(coordinator.entry.data.get("protocol_variant"))
        self.model = p.MODELS[model]
        super().__init__(coordinator, self.model.profile, (), gatt_error_key="sven_gatt")
        self._is_current: Callable[[], bool] = lambda: False
        self._epoch = 0
        self._levels: list[int | None] = [None, None]
        self._pattern: int | None = None
        self._used = float(p.MASSAGE_LIMIT_S)
        self._active_since: float | None = None
        self._off_since: float | None = None
        self._timer_minutes: int | None = None
        self._duration_deadline: float | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._stopping_massage: _Link | None = None
        self._timer_epoch = 0

    def _current_link(self, expected: _Link | None = None) -> _Link:
        link = super()._current_link(expected)
        if not self._is_current() or self._coordinator.controller is not self:
            raise BedNotConnectedError
        return link

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return False

    async def async_on_connect(self, session: ControllerSession) -> None:
        self.on_disconnect()
        if session.client is None or not session.is_current():
            raise BedNotConnectedError
        self._link = select_link(session.client)
        self._is_current = session.is_current
        try:
            await session.async_start_notify()
        except BleakError, TimeoutError:
            # Notification setup is optional. A live, current writer remains usable.
            try:
                self._current_link()
            except BedNotConnectedError:
                self.on_disconnect()
                raise
            self._notifying = False
        except BaseException:
            self.on_disconnect()
            raise

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # Historical command label, never a measured or inferred motor angle.
        return {"last_preset": self._coordinator.controller_state.get(FOUNDATION_PRESET)}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        value = state.get("last_preset")
        self.forward_controller_state_update(
            FOUNDATION_PRESET,
            value if isinstance(value, str) and value in p.PRESETS.values() else None,
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "sven_last_preset",
                "sven_last_preset",
                FOUNDATION_PRESET,
                "mdi:bed",
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
        )

    def on_gesture_release(self) -> None:
        self._epoch += 1

    def on_connection_release(self, reason: str) -> None:
        self.on_gesture_release()

    def on_app_state_replaced(self) -> None:
        self.on_disconnect()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._is_current = lambda: False
        self.on_gesture_release()
        self._uncertain()

    def _uncertain(self) -> None:
        self._timer_epoch += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._duration_deadline = None
        self._timer_minutes = None
        self._levels = [None, None]
        self._pattern = None
        self._used = float(p.MASSAGE_LIMIT_S)
        self._active_since = self._off_since = None
        if self._coordinator.controller is self:
            self.forward_controller_state_updates(
                massage_intensity("head")(None),
                massage_intensity("foot")(None),
                MASSAGE_TIMER_MINUTES(None),
            )

    def _receive_notification(self, sender: str, data: bytes) -> None:
        try:
            self._current_link()
        except BedNotConnectedError:
            return
        # The app only emits raw bytes. No status or angle interpretation exists.
        self.forward_raw_notification(sender, data)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "model": self.profile.key,
            "massage_levels_estimated": self._levels[:],
            "massage_pattern_estimated": self._pattern,
            "massage_used_seconds": self._usage(),
            "massage_timer_minutes": self._timer_minutes,
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                partial(_motor, axis, True),
                partial(_motor, axis, False),
                lambda c: c.stop_all(),
                stop_scope="side",
                timed_move_fn=partial(_timed_motor, axis),
            )
            for axis in self.model.axes
        )

    async def _move_with_stop(self, command_byte: int, *, duration_ms: int | None = None) -> None:
        if duration_ms is None and self.leased_hold_refreshes(p.REFRESH_MS) is None:
            await self._tap(command_byte)
            return
        link, epoch = self._current_link(), self._epoch
        cancel = self._coordinator.cancel_command
        ms = min(self.leased_hold_ms(duration_ms or p.TAP_MS), p.HOLD_LIMIT_MS)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ms / 1000
        context = current_command_context()
        attempted = False

        def verify() -> None:
            nonlocal attempted
            if epoch != self._epoch or loop.time() >= deadline:
                note_frame_skipped()
                raise asyncio.CancelledError
            attempted = True

        async def release() -> None:
            if attempted:
                await self._release_on(link)
                if context is not None:
                    context.cleanup_stop_sent = True
                    self._cleanup_context = context

        with self.sent_state(
            FOUNDATION_PRESET(None),
            is_current=lambda: self._link is link and self._coordinator.controller is self,
        ):
            async with self.releasing(release):
                while loop.time() + 1e-6 < deadline and not cancel.is_set():
                    started = loop.time()
                    await self._write_on(
                        link, self._encode(link, command_byte), cancel, before_write=verify
                    )
                    await cancellable(
                        asyncio.sleep(
                            max(0, min(deadline, started + p.REFRESH_MS / 1000) - loop.time())
                        ),
                        cancel,
                    )

    async def _tap(self, code: int) -> None:
        link, epoch = self._current_link(), self._epoch

        def verify() -> None:
            if epoch != self._epoch:
                note_frame_skipped()
                raise asyncio.CancelledError

        async def release() -> None:
            await self._release_on(link)

        position_command = code in p.POSITION_COMMANDS
        updates = (FOUNDATION_PRESET(p.PRESETS.get(code)),) if position_command else ()
        with self.sent_state(
            *updates, is_current=lambda: self._link is link and self._coordinator.controller is self
        ):
            async with self.releasing(release):
                await self._write_on(
                    link,
                    self._encode(link, code),
                    self._coordinator.cancel_command,
                    before_write=verify,
                )
                await cancellable(asyncio.sleep(p.TAP_MS / 1000), self._coordinator.cancel_command)

    async def _send(self, button: Button) -> None:
        await self._tap(self._code(button))

    async def _recall(self, code: int) -> None:
        await self._tap(code)

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise invalid("sven_memory")
        # HA has an explicit confirmed Save action, equivalent to accessibility Save.
        await self._tap(self.profile.memory[memory_num - 1][1])

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
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
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
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_is_assumed(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return list(p.TIMER_OPTIONS)

    def _usage(self) -> float:
        return self._used + (
            asyncio.get_running_loop().time() - self._active_since
            if self._active_since is not None
            else 0
        )

    def confirm_massage_off(self, rested: bool) -> None:
        self._coordinator.require_persistent_command_connection("sven_massage_concurrent")
        self._current_link()
        self._uncertain()
        self._levels = [0, 0]
        self._off_since = asyncio.get_running_loop().time() - (p.MASSAGE_REST_S if rested else 0)
        self.forward_controller_state_updates(
            massage_intensity("head")(0), massage_intensity("foot")(0)
        )

    def _admit_massage(self, *, stopping: bool = False) -> None:
        self._coordinator.require_persistent_command_connection("sven_massage_concurrent")
        if None in self._levels:
            raise failed("sven_massage_uncertain")
        now = asyncio.get_running_loop().time()
        if self._off_since is not None and now - self._off_since >= p.MASSAGE_REST_S:
            self._used = 0
        if not stopping and self._usage() >= p.MASSAGE_LIMIT_S:
            raise failed("sven_massage_rest")

    def _account(self, *, preserve_duration: bool = False) -> None:
        self._timer_epoch += 1
        loop = asyncio.get_running_loop()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if any(self._levels):
            if self._active_since is None:
                self._active_since = loop.time()
            self._off_since = None
            link = self._current_link()
            deadline = loop.time() + max(0, p.MASSAGE_LIMIT_S - self._usage())
            if self._duration_deadline is not None:
                deadline = min(deadline, self._duration_deadline)
            seconds = max(0, deadline - loop.time())
            if self._stopping_massage is not link:
                self._timer = loop.call_later(seconds, self._expire_timer, link, self._timer_epoch)
        else:
            self._used = self._usage()
            self._active_since = None
            self._off_since = loop.time()
            if not preserve_duration:
                self._duration_deadline = None
                self._timer_minutes = None
        self.forward_controller_state_update(
            MASSAGE_TIMER_MINUTES, self._timer_minutes if any(self._levels) else 0
        )

    def _expire_timer(self, link: _Link, epoch: int) -> None:
        if self._link is not link or epoch != self._timer_epoch:
            return
        self._timer = None
        # Timers inherit the command that scheduled them. Admit a fresh safety
        # intent, rather than reusing an expired command's inline reservation.
        copy_context_without_command().run(
            self._coordinator.hass.async_create_task, self._timer_off(link, epoch)
        )

    async def _timer_off(self, link: _Link, epoch: int | None = None) -> None:
        def current() -> bool:
            return (
                self._link is link
                and self.client is link.client
                and link.client.is_connected
                and self._is_current()
                and self._coordinator.controller is self
                and (epoch is None or epoch == self._timer_epoch)
            )

        # A stale timer must not even admit work that could cancel a new command.
        if not current():
            return
        self._coordinator.require_persistent_command_connection("sven_massage_concurrent")

        async def stop(c: BedController) -> None:
            if c is not self or not current():
                return
            self._current_link(link)
            await self.massage_off()

        try:
            await self._coordinator.async_execute_controller_command(
                stop, kind=CommandKind.SAFETY, admit_if=current
            )
        except HomeAssistantError, BleakError, ConnectionError, TimeoutError:
            if self._link is link:
                self._uncertain()

    async def _massage_step(
        self, zone: int, *, stopping: bool = False, preserve_duration: bool = False
    ) -> None:
        link = self._current_link()
        self._admit_massage(stopping=stopping or self._levels[zone] == 3)
        old = self._levels[zone]
        assert old is not None
        key = massage_intensity("head" if zone == 0 else "foot")
        try:
            with self.sent_state(
                key((old + 1) % 4),
                is_current=lambda: self._link is link and self._coordinator.controller is self,
            ):
                await self._tap(self._code("massage_head" if zone == 0 else "massage_foot"))
            self._levels[zone] = (old + 1) % 4
            self._account(preserve_duration=preserve_duration)
        except BaseException:
            if self._link is link:
                self._uncertain()
            raise

    async def massage_head_toggle(self) -> None:
        await self._massage_step(0)

    async def massage_foot_toggle(self) -> None:
        await self._massage_step(1)

    async def massage_mode_step(self) -> None:
        link = self._current_link()
        self._admit_massage()
        if not any(self._levels):
            raise failed("sven_massage_inactive")
        try:
            await self._tap(self._code("massage_mode"))
            self._pattern = (self._pattern + 1) % 3 if self._pattern is not None else None
            self._levels = [1 if level else 0 for level in self._levels]
            self.forward_controller_state_updates(
                massage_intensity("head")(self._levels[0]),
                massage_intensity("foot")(self._levels[1]),
            )
            self._account()
        except BaseException:
            if self._link is link:
                self._uncertain()
            raise

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        link = self._current_link()
        if zone not in ("head", "foot") or type(level) is not int or not 0 <= level <= 3:
            raise invalid("sven_massage_level")
        index = 0 if zone == "head" else 1
        self._admit_massage(stopping=level == 0)
        old = self._levels[index]
        assert old is not None
        try:
            for _ in range((level - old) % 4):
                await self._massage_step(index, stopping=level == 0, preserve_duration=level != 0)
                await cancellable(asyncio.sleep(p.TAP_MS / 1000), self._coordinator.cancel_command)
        except BaseException:
            if self._link is link:
                self._uncertain()
            raise

    async def massage_off(self) -> None:
        # No blind toggle/off opcode is reachable. Off requires known levels.
        link = self._current_link()
        self._stopping_massage = link
        try:
            await self.set_massage_intensity("head", 0)
            await self.set_massage_intensity("foot", 0)
        finally:
            if self._stopping_massage is link:
                self._stopping_massage = None

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes == 0:
            await self.massage_off()
            return
        if minutes not in p.TIMER_OPTIONS:
            raise invalid("sven_massage_timer")
        self._admit_massage()
        if not any(self._levels):
            raise failed("sven_massage_inactive")
        self._timer_minutes = minutes
        self._duration_deadline = asyncio.get_running_loop().time() + minutes * 60
        self._account()
        self.forward_controller_state_update(MASSAGE_TIMER_MINUTES, minutes)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "sven_head_massage",
                "Cycle head massage",
                lambda c: c.massage_head_toggle(),
                translation_key="sven_head_massage",
                card=CARD_MASSAGE,
                combine_sides=True,
            ),
            ControllerButtonSpec(
                "sven_foot_massage",
                "Cycle foot massage",
                lambda c: c.massage_foot_toggle(),
                translation_key="sven_foot_massage",
                card=CARD_MASSAGE,
                combine_sides=True,
            ),
            *tuple(
                ControllerButtonSpec(
                    key,
                    label,
                    partial(_reconcile, rested),
                    translation_key=key,
                    requires_confirmation=True,
                    card=CARD_MASSAGE,
                )
                for key, label, rested in (
                    ("sven_massage_off_now", "Confirm massage is off", False),
                    ("sven_massage_rested", "Confirm massage has rested", True),
                )
            ),
        )
