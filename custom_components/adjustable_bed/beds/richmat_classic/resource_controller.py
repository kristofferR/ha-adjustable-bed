"""Shared HA session/lifecycle for Lady Americana, ACAA, STA and Zero Gravity."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import time
from functools import partial
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, ClassVar, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_UTILITY
from ...command_scheduler import current_command_context
from ...const import CONF_MOTOR_PULSE_COUNT, CONF_RICHMAT_CLASSIC_THIRD_SERVICE
from ...controller_state import StateKey
from ...profiles.richmat_resource_apps import APPS, worker_interval
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..entity_specs import ControllerButtonSpec, ControllerNumberSpec
from . import resource_protocol as p
from .caller import Selection, selected_operand
from .controller import APP, LAYOUT, PREFERENCES, REJECTION, STATE, STATUS, control_node
from .protocol import (
    ALARM_QUERY,
    ALARM_SPACING_MS,
    AROMA_QUERY,
    INITIALIZE,
    LAMP_QUERY,
    QUERY_SPACING_MS,
    SETTINGS_SPACING_MS,
    SLIDER_MINUTES,
    alarm,
    alarm_capability,
    alarm_choices,
    alarm_delay,
    control,
    massage_timer,
    rgb,
)
from .resource_receive import ResourceReceiveState
from .session import SessionController
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from .requests import Request

LAMP_TIMEOUT: Final = StateKey[int | None]("richmat_resource_lamp_timeout")


class ResourceBedController(SessionController):
    """Resource getters stay shared; app timing, parser and utilities are explicit."""

    # A subclass that keeps its own timer state publishes it itself.
    _publishes_massage_timer: ClassVar[bool] = True

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator, app=app, device_name=device_name)
        self.app_profile = APPS[self.app]
        if self.layout in self.app_profile.excluded_layouts:
            raise ValueError("This app layout is outside the bed integration")
        self._receive: ResourceReceiveState = ResourceReceiveState()
        self._preferences = {}
        self._deadline: float | None = None
        self._lamp_timeout: int | None = None
        self._massage_timer: int | None = None

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": self.app,
            "layout": self.layout,
            "transport": self._session.wire if self._session else None,
            "alarm_reply_seen": self._receive.alarm_capable,
            "led_reply_seen": self._receive.light_capable,
            "led_on_reply_seen": self._receive.light_on_seen,
            "led_off_reply_seen": self._receive.light_off_seen,
            "last_notification": self._receive.last_value,
            "buffer_bytes": len(self._receive.buffer) // 2,
            "alarm_actions": self._alarm_actions(),
            "requests": dict(self._preferences),
            "hardware": "UNVERIFIED",
        }

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # These are local choices/requests, never device feedback or a schedule.
        return {
            **self._preferences,
            "press_flag": self._selection.press_flag,
            "head": self._selection.head,
            "wire": self._wire,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)
        flag, head = state.get("press_flag", "53"), state.get("head", True)
        if flag not in ("53", "54", "55") or type(head) is not bool:
            raise ValueError("Invalid saved app selector")
        self._selection = Selection(press_flag=str(flag), head=head)
        # A saved color/timer can be shown as a request but is never replayed on
        # a new bed session. Missing phone cache must not send default green.
        self._preferences = {}

    def _publish(self) -> None:
        received = self._receive
        state = {
            "last_notification": received.last_value,
            "alarm_capable": received.alarm_capable,
            "light_capable": received.light_capable,
            "alarm_actions": self._alarm_actions(),
            "head_foot": "head" if self._selection.head else "foot",
            "axis_selector": self._selection.press_flag,
        }
        self.forward_controller_state_updates(
            STATUS("ready" if self._session else "disconnected"),
            APP(self.app),
            LAYOUT(self.layout),
            STATE(state),
            PREFERENCES(dict(self._preferences)),
            REJECTION(self._rejection),
            LAMP_TIMEOUT(self._lamp_timeout),
        )
        if self._publishes_massage_timer:
            # The request's slider stop; the bed reports no timer.
            self.forward_controller_state_updates(
                MASSAGE_TIMER_MINUTES(
                    next(
                        (m for m, stop in SLIDER_MINUTES.items() if stop == self._massage_timer),
                        None,
                    )
                )
            )
        # Shared select entities use this typed state key as well.
        from .controller import _selection_key

        self.forward_controller_state_updates(
            _selection_key("head_foot")("head" if self._selection.head else "foot")
        )

    def _notification(
        self, session: Transport, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        self._receive.feed(bytes(data), app=self.app, layout=self.layout)
        # ACK is a received event, without request/address correlation or a
        # stored scheduled time. It cannot overwrite newer local selections.
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The bed is disconnected")
        session = select(
            client,
            third_service=self._coordinator.entry.data.get(
                CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False
            ),
        )
        name = self._device_name or self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(self.app, name, session.wire == "RAW"))
        self._worker.cancel()
        self._session, self._wire = session, session.wire
        self._receive = ResourceReceiveState()
        self._notifications_started = False
        self._rejection = None
        try:
            with self._transaction():
                # Exact startup precedes notification setup. There is no source
                # 300 ms wait, capability/auth ACK, or raw startup write.
                if session.wire == "FRAMED":
                    await self._send(INITIALIZE)
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
        except BaseException:
            self._session = None
            raise
        self._publish()

    def on_disconnect(self) -> None:
        self._receive = ResourceReceiveState()
        self._lamp_timeout = self._massage_timer = None
        super().on_disconnect()

    async def _iteration(self, cancel: asyncio.Event, mode: int) -> bool:
        if self._worker.mode == 1 and self._deadline is not None and monotonic() >= self._deadline:
            self._worker.mode = 0
        return await super()._iteration(cancel, mode)

    async def _next_tick(self, cancel: asyncio.Event) -> bool:
        delay = self._worker.tick_ms
        if self._worker.mode == 1 and self._deadline is not None:
            delay = min(delay, max(0, ceil((self._deadline - monotonic()) * 1000)))
        return await self._wait(delay, cancel)

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        with self._transaction():
            context = current_command_context()
            duration = (
                hold_ms
                if hold_ms is not None
                else int(self._coordinator.entry.data.get(CONF_MOTOR_PULSE_COUNT, 10))
                * self._worker.tick_ms
            )
            self._deadline = None if context and context.lease else monotonic() + duration / 1000
            self._worker.cancel()
            try:
                await super().execute_action(node, long=long, hold_ms=hold_ms)
            finally:
                self._deadline = None
                self._worker.cancel()

    async def stop_all(self) -> None:
        self._worker.cancel()
        if not CONTROLLER_GESTURE_RELEASE.get():
            await self._release(self.app_profile.held_release_ms)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for spec in super().controller_button_specs:
            if spec.hold is not None:
                if not self._keeps(self._button(control_node(spec.hold.control)), self._selection):
                    spec = replace(spec, hold=None)
            buttons.append(spec)
        return tuple(buttons)

    def controller_button_available(self, key: str) -> bool:
        if not super().controller_button_available(key):
            return False
        if key == "richmat_classic_release":
            return True
        try:
            button = self._button(control_node(key))
        except ValueError:
            return False
        if key.endswith("_long"):
            return button.long is not None and not button.excluded_long
        if button.excluded_short:
            return False
        wire = self._session.wire if self._session else self._wire
        return any(
            isinstance(
                selected_operand(
                    button, candidate, 1 if button.status == 1 else 2, self._selection
                ),
                bytes,
            )
            for candidate in ((wire,) if wire is not None else ("RAW", "FRAMED"))
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        if self._receive.light_capable:

            async def timeout(controller: BedController, value: float) -> None:
                if isinstance(controller, ResourceBedController):
                    await controller.execute_request(p.Request("lamp_timeout", seconds=int(value)))

            specs.append(
                ControllerNumberSpec(
                    "richmat_resource_lamp_timeout",
                    "richmat_resource_lamp_timeout",
                    LAMP_TIMEOUT,
                    0,
                    300,
                    1,
                    timeout,
                    "s",
                    card=CARD_UTILITY,
                )
            )
        return tuple(specs)

    # D1RM's massage slider: four stops the app labels 0, 2H, 3H and 5H.
    @property
    def supports_massage_timer(self) -> bool:
        return self.layout == "D1RM"

    @property
    def auto_enable_massage(self) -> bool:
        return super().auto_enable_massage or self.supports_massage_timer

    @property
    def massage_timer_options(self) -> list[int]:
        return [m for m in SLIDER_MINUTES if m] if self.supports_massage_timer else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return self.supports_massage_timer

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in SLIDER_MINUTES:
            raise ValueError("Choose a massage timer this bed model offers")
        await self.execute_request(p.Request("massage_timer", progress=SLIDER_MINUTES[minutes]))

    def validate_richmat_classic_request(self, request: Request) -> None:
        raise ValueError("Use the Lady Americana / ACAA / STA Homecare / Zero Gravity bed action")

    def _alarm_actions(self) -> dict[str, int]:
        actions = {}
        for button in self._controls:
            if not button.rich_button or button.alarm_clock is None:
                continue
            code = int(button.alarm_clock, 16)
            name = p.ALARM_NAMES[code]
            key, duplicate = name, 1
            while key in actions:
                duplicate += 1
                key = f"{name}_{duplicate}"
            actions[key] = code
        return actions

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        return alarm_capability(self._alarm_actions())

    def _alarm_request(self, alarm: AlarmRequest) -> p.Request:
        if not alarm.enabled:
            return p.Request("cancel_alarm")
        actions = alarm_choices(self._alarm_actions(), alarm)
        return p.Request("alarm", actions=actions, when=time(alarm.hour, alarm.minute))

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_request(self._alarm_request(alarm))

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.execute_request(self._alarm_request(alarm))

    def validate_request(self, request: p.Request, *, live: bool = True) -> None:
        op = request.operation
        if op == "alarm":
            p.alarm_action(self._alarm_actions(), request.actions)
            if request.when and (request.when.second or request.when.microsecond):
                raise ValueError("Choose a time with minute precision")
            # Metadata/direct navigation is independent of the menu reply.
        elif op in ("rgb", "lamp_timeout"):
            if live and (self._session is None or not self._receive.light_capable):
                raise ValueError("The bed has not reported a light. Reconnect it and try again")
            if op == "rgb":
                if (
                    request.color is None
                    or len(request.color) != 3
                    or any(type(v) is not int or not 0 <= v <= 255 for v in request.color)
                ):
                    raise ValueError("Enter a light color as red, green and blue values from 0 to 255")
            elif request.seconds is None:
                raise ValueError("Choose a light timeout in seconds")
            else:
                p.lamp_timeout(request.seconds)
        elif op == "massage_timer":
            if self.layout != "D1RM" or request.progress is None:
                raise ValueError("This bed model has no massage timer")
            massage_timer(self.layout, request.progress)
        elif op == "bed_command":
            if request.command not in p.BED_COMMANDS or not 1 <= request.duration_ms <= 60000:
                raise ValueError(
                    "Choose a control this bed offers and a duration of up to 60 seconds"
                )
        elif op not in ("query", "cancel_alarm"):
            raise ValueError("Unknown bed action")

    async def execute_request(self, request: p.Request) -> None:
        self.validate_request(request)
        with self._transaction() as session:
            cancel = self._coordinator.cancel_command
            op = request.operation
            if op == "bed_command":
                assert request.command is not None
                code, held = p.BED_COMMANDS[request.command]
                deadline = monotonic() + request.duration_ms / 1000
                try:
                    while not cancel.is_set() and monotonic() < deadline:
                        await self.write_command(control(bytes((code,)), session.wire))
                        delay = min(
                            self._worker.tick_ms, max(0, ceil((deadline - monotonic()) * 1000))
                        )
                        if not held or not await self._wait(delay, cancel):
                            break
                finally:
                    await self._release(
                        self.app_profile.held_release_ms
                        if held
                        else self.app_profile.tap_release_ms
                    )
                return
            if op == "query":
                frames = ([ALARM_QUERY] if self._alarm_actions() else []) + [
                    LAMP_QUERY,
                    AROMA_QUERY,
                ]
                delay = QUERY_SPACING_MS
            elif op in ("alarm", "cancel_alarm"):
                now, when = dt_util.now(), request.when
                minutes = (
                    alarm_delay(
                        now.hour * 60 + now.minute, when.hour * 60 + when.minute if when else None
                    )
                    if op == "alarm"
                    else 0
                )
                action = (
                    p.alarm_action(self._alarm_actions(), request.actions) if op == "alarm" else 0
                )
                frames, delay = alarm(minutes, action), ALARM_SPACING_MS
            elif op == "rgb":
                assert request.color is not None
                frames, delay = (rgb(*request.color),), SETTINGS_SPACING_MS
            elif op == "lamp_timeout":
                assert request.seconds is not None
                frames, delay = (p.lamp_timeout(request.seconds),), 0
            else:
                assert request.progress is not None
                frames, delay = (massage_timer(self.layout, request.progress),), 0
            for packet in frames:
                if cancel.is_set():
                    return
                await self.write_command(packet)
                if delay and not await self._wait(delay, cancel):
                    return
            # Request state, never an observed device value. ACKs cannot replace
            # a newer request, current-side notification or pending session.
            if not cancel.is_set() and self._session is session:
                if op == "lamp_timeout":
                    self._lamp_timeout = request.seconds
                elif op == "massage_timer":
                    self._massage_timer = request.progress
                elif op == "alarm":
                    self._preferences["last_alarm_request"] = list(request.actions)
                elif op == "cancel_alarm":
                    self._preferences.pop("last_alarm_request", None)
                self._publish()
