"""Explicit profiles for Avocado Eco Base, CoasterSleep, Forty Winks,
Milemont and Superior. No capabilities are inherited from legacy Richmat.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from functools import partial
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ..cluster018_caller import RETAIN, Selection, effective_status, transition
from ..cluster018_profiles import Control, controls, load_catalog
from ..cluster018_protocol import (
    ALARM_QUERY,
    ALARM_SPACING_MS,
    AROMA_QUERY,
    DESK_CONFIRM,
    DESK_QUERY,
    DESK_REFRESH_MS,
    HELD_RELEASE_MS,
    INITIALIZE,
    LAMP_QUERY,
    QUERY_SPACING_MS,
    SETTINGS_SPACING_MS,
    STARTUP_MS,
    TAP_RELEASE_MS,
    TICK_MS,
    Worker,
    alarm,
    alarm_delay,
    aroma,
    control,
    desk_button,
    desk_target,
    desk_unit,
    lamp_timer,
    massage_popup,
    massage_timer,
    release,
    rgb,
    worker_interval,
)
from ..cluster018_receive import MalformedFrame, ReceiveState
from ..cluster018_requests import Request
from ..cluster018_transport import Transport, select
from ..const import (
    CONF_CLUSTER018_THIRD_SERVICE,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
)
from ..profiles.richmat import RICHMAT_CLASSIC
from .base import (
    CONTROLLER_GESTURE_RELEASE,
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


# Settings rows a capability reply reveals (``ReceiveState.menu``).
_MENU_ROWS = frozenset({"alarm", "light", "aroma"})


async def _press(controller: BedController, node: int, long: bool = False) -> None:
    if not isinstance(controller, Cluster018Controller):
        raise TypeError("This action requires the selected app controller")
    await controller.execute_action(node, long=long)


class Cluster018Controller(BedController):
    """One selected package/layout and one current physical BLE session."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._device_name = device_name
        self.app = app or str(coordinator.entry.data[CONF_PROTOCOL_VARIANT])
        self.profile = RICHMAT_CLASSIC[self.app]
        self.layout = str(coordinator.entry.data[CONF_PRODUCT_TYPE]).strip().upper()
        if self.layout in ("TEST", "RMCS"):
            raise ValueError("Diagnostic endurance and motor-mapping layouts are excluded")
        self._controls = controls(self.app, self.layout)
        self._model = load_catalog(self.app)["models"][self.layout]
        self._selection = Selection()
        self._mode = 0
        self._worker = Worker()
        self._receive = ReceiveState()
        self._session: Transport | None = None
        self._rejection: str | None = None
        self._preferences: dict[str, object] = {"lamp_minutes": 0, "lamp_rgb": "ffffff", "alarm_selection": None, "massage_progress": 0}
        self._pending_alarm: str | None = None
        self._unit_switch = False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._session.write.uuid if self._session else ""

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        # Mode labels are not sufficient evidence of physical left/right roles.
        return False

    @property
    def supports_cluster018(self) -> bool:
        return True

    @property
    def persisted_app_state_key(self) -> str:
        return f"cluster018:{self.app}:{self.layout}"

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {**self._preferences, "mode": self._mode, "selection": {
            "press_flag": self._selection.press_flag, "head": self._selection.head,
            "armed": self._selection.armed, "hold": self._selection.hold,
        }, "menu": sorted(self._receive.menu)}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        minutes = state.get("lamp_minutes", 0)
        color = state.get("lamp_rgb", "ffffff")
        selected = state.get("alarm_selection")
        progress = state.get("massage_progress", 0)
        mode = state.get("mode", 0)
        selection = state.get("selection", {})
        if type(mode) is not int or mode not in self._model["modes"] or not isinstance(selection, Mapping):
            raise ValueError("Invalid saved app selection")
        flag, head, armed, hold = (selection.get("press_flag", "53"), selection.get("head", True), selection.get("armed", False), selection.get("hold"))
        if flag not in ("53", "54", "55") or type(head) is not bool or type(armed) is not bool or hold is not None and type(hold) is not bool:
            raise ValueError("Invalid saved app selection")
        if type(minutes) is not int or not 0 <= minutes <= 15:
            raise ValueError("Invalid saved lamp timer")
        if not isinstance(color, str) or len(color) != 6:
            raise ValueError("Invalid saved RGB value")
        try:
            bytes.fromhex(color)
        except ValueError as err:
            raise ValueError("Invalid saved RGB value") from err
        if selected is not None and selected not in self._alarm_actions():
            raise ValueError("Saved alarm action is absent from this app layout")
        if type(progress) is not int or not 0 <= progress <= 5:
            raise ValueError("Invalid saved massage slider")
        menu = state.get("menu", [])
        if not isinstance(menu, list) or not set(menu) <= _MENU_ROWS:
            raise ValueError("Invalid saved settings menu")
        self._preferences = {"lamp_minutes": minutes, "lamp_rgb": color, "alarm_selection": selected, "massage_progress": progress}
        self._mode = mode
        self._selection = Selection(press_flag=flag, head=head, armed=armed, hold=hold)
        self._receive.menu = set(menu)

    def _publish(self) -> None:
        state = asdict(self._receive)
        state["menu"] = sorted(self._receive.menu)
        self.forward_controller_state_updates({
            "cluster018_status": "ready" if self._session else "disconnected",
            "cluster018_app": self.app,
            "cluster018_layout": self.layout,
            "cluster018_state": state,
            "cluster018_preferences": dict(self._preferences),
            "cluster018_rejection": self._rejection,
            "cluster018_mode": str(self._mode),
            "cluster018_program": "armed" if self._selection.armed else "recall",
            "cluster018_hold": "hold" if self._selection.hold else "release",
            "cluster018_head_foot": "head" if self._selection.head else "foot",
        })

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": self.app, "layout": self.layout,
            "transport": self._session.wire if self._session else None,
            "notifications": self._session.has_notifications if self._session else False,
            "state": {**asdict(self._receive), "menu": sorted(self._receive.menu)},
            "alarm_actions": self._alarm_actions(),
            "controls": [{"node": c.node, "name": c.label} for c in self._controls],
            "rejection": self._rejection,
            "hardware": "UNVERIFIED",
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (ControllerStateSensorSpec(
            "cluster018_status", "cluster018_status", "cluster018_status", "mdi:bed",
            attribute_keys=("cluster018_app", "cluster018_layout", "cluster018_state", "cluster018_preferences", "cluster018_rejection"),
        ),)

    def _notification(self, session: Transport, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._session is not session or self.client is not session.client or not session.client.is_connected:
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        try:
            self._receive.feed(bytes(data), app=self.app, layout=self.layout, desk_bound=self.layout in ("FWRM", "WFRM"), table_controls_bound=self.layout in ("FWRM", "WFRM"))
            if self._receive.value_event == "6e07010177":
                self._preferences["alarm_selection"] = self._pending_alarm
            elif self._receive.value_event == "6e07010278":
                self._preferences["alarm_selection"] = None
            unit = self._receive.unit_event
            if unit in (0, 1) and bool(unit) != self._unit_switch:
                self._unit_switch = bool(unit)
                self._coordinator.hass.async_create_task(self._reply_unit(session, unit))
            self._rejection = None
        except MalformedFrame as err:
            self._rejection = str(err)
        self._publish()

    async def _reply_unit(self, session: Transport, unit: int) -> None:
        async def send(controller: BedController) -> None:
            if controller is self and self._session is session:
                await self._send(desk_unit(bool(unit)))
        if self._session is session:
            try:
                await self._coordinator.async_execute_controller_command(send, cancel_running=False, resource="configuration")
            except ConnectionError:
                # The source has no retry or success guarantee after link loss.
                return

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The app's bed is disconnected")
        session = select(client, third_service=self._coordinator.entry.data.get(CONF_CLUSTER018_THIRD_SERVICE, False))
        name = self._device_name if self._device_name is not None else self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(name, session.wire))
        self._session = session
        # The bed's query replies proved these settings rows; a new session keeps
        # them, since with a disconnect between calls it could never prove one.
        self._receive = ReceiveState(menu=set(self._receive.menu))
        self._unit_switch = False
        try:
            if session.has_notifications:
                await client.start_notify(session.notify, partial(self._notification, session))
            if self.layout in ("WFRM", "FWRM"):
                # RemoteFragment.initData issues this independently of the
                # delayed, notification-conditioned FRAMED transport startup.
                await self._send(DESK_QUERY)
            if session.wire == "FRAMED" and session.has_notifications:
                await asyncio.sleep(STARTUP_MS / 1000)
                await self._send(DESK_QUERY if self.layout in ("WFRM", "FWRM") else INITIALIZE)
        except BaseException:
            self._session = None
            raise
        self._publish()

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        self._worker.mode = -1
        if session and session.client.is_connected and session.has_notifications:
            await session.client.stop_notify(session.notify)
        self._publish()

    def on_disconnect(self) -> None:
        self._session = None
        self._worker.cancel()
        self._pending_alarm = None
        if self._coordinator.controller is self:
            self._coordinator.cache_capability_controller()
        self._publish()

    async def _send(self, packet: bytes) -> None:
        session = self._session
        if session is None or self.client is not session.client or not session.client.is_connected:
            raise ConnectionError("No current app BLE session")
        # Calls are admitted under the coordinator command lock. Never retry an
        # actuator write or carry cached Android objects across connections.
        await session.client.write_gatt_char(session.write, packet, response=session.response)

    async def write_command(self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = TICK_MS, cancel_event: asyncio.Event | None = None) -> None:
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                return
            await self._send(command)
            if index + 1 < repeat_count and not await self._wait(repeat_delay_ms, cancel):
                return

    @staticmethod
    async def _wait(milliseconds: int, cancel: asyncio.Event) -> bool:
        if cancel.is_set():
            return False
        try:
            await asyncio.wait_for(cancel.wait(), milliseconds / 1000)
        except TimeoutError:
            return True
        return False

    async def _iteration(self, cancel: asyncio.Event, mode: int) -> bool:
        """Send one worker tick; False when a cancel stopped it before its last emission."""
        session = self._session
        if session is None:
            raise ConnectionError("No current app BLE session")
        for emission in self._worker.tick():
            if emission.delay_ms and not await self._wait(emission.delay_ms, cancel):
                return False
            if cancel.is_set():
                return False
            if emission.payload is None:
                # RAW drops null at dispatch; FRAMED dereferences before enqueue.
                if session.wire == "FRAMED":
                    raise ValueError("Selected app getter has no framed payload")
                continue
            await self._send(control(emission.payload, session.wire, mode))
        return True

    def _button(self, node: int) -> Control:
        for button in self._controls:
            if button.node == node and button.rich_button:
                return button
        raise ValueError("Choose an action from the selected app layout")

    def _apply(self, button: Control, event: str, selection: Selection) -> Selection:
        session = self._session
        if session is None:
            raise ConnectionError("No current app BLE session")
        result = transition(button, self.layout, session.wire, selection, "UP" if event == "UP" else "DOWN", app=self.app)
        if result.idle_up_guard and self._worker.mode == -1:
            return selection
        if result.payload is not RETAIN:
            self._worker.payload = result.payload
        if result.mode is not RETAIN:
            self._worker.mode = result.mode
        if result.count_ms is not RETAIN:
            self._worker.set_count(result.count_ms)
        if result.press_flag is not RETAIN:
            self._selection = replace(self._selection, press_flag=result.press_flag)
            selection = replace(selection, press_flag=result.press_flag)
        if result.consume_arm:
            self._selection = replace(self._selection, armed=False)
            selection = replace(selection, armed=False)
        return selection

    async def execute_action(self, node: int, *, long: bool = False, hold_ms: int | None = None) -> None:
        button = self._button(node)
        if button.status not in (1, 2, 3):
            raise ValueError("This node uses a separate local or settings action")
        if self._hidden(button) and not (button.hold_affected and self._selection.hold is True):
            raise ValueError("This control is hidden in the selected app state")
        if long and button.hold_affected and self._selection.hold is True:
            raise ValueError("Choose the separate save button in Hold mode")
        cancel = self._coordinator.cancel_command
        # Offline selectors remain usable; a gesture keeps its admitted target
        # and getter context through cleanup while later choices await the next.
        mode, selection = self._mode, self._selection
        status = effective_status(button, self.layout, selection)
        programmed = button.mem_special and selection.armed or button.select_special and selection.armed
        up_applied = False
        completed = False
        selection = self._apply(button, "DOWN", selection)
        try:
            if status == 3 and not long and not button.mem_special and not programmed:
                selection = self._apply(button, "UP", selection)
                up_applied = True
            duration = hold_ms if hold_ms is not None else int(self._coordinator.entry.data.get(CONF_MOTOR_PULSE_COUNT, 10)) * self._worker.tick_ms
            elapsed = 0
            while not cancel.is_set():
                await self._iteration(cancel, mode)
                if self._worker.mode == -1:
                    break
                if self._worker.mode == 1 and elapsed >= duration:
                    break
                if not await self._wait(self._worker.tick_ms, cancel):
                    break
                elapsed += self._worker.tick_ms
            if not cancel.is_set():
                if up_applied:
                    completed = True
                else:
                    self._apply(button, "UP", selection)
                    # A cancel during the UP tick's release delay skips that
                    # release, so only a finished tick completes the gesture.
                    completed = await self._iteration(cancel, mode)
        finally:
            # HA cancellation also cancels pending saves and refreshes. The app's
            # in-bounds CANCEL/pause can leave them running; that is unsafe here.
            self._worker.mode = -1
            try:
                if not completed:
                    self._worker.cancel()
                    await self._release(HELD_RELEASE_MS if status == 1 else TAP_RELEASE_MS, mode=mode)
            finally:
                self._publish()

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        async def send() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if self._session is not None:
                await self.write_command(release(self._session.wire, self._mode if mode is None else mode), cancel_event=asyncio.Event())

        # The scheduler may cancel the operation while its cooperative cancel
        # path already awaits this delay. Drain the same cleanup, never retry it.
        task = asyncio.create_task(send())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def stop_all(self) -> None:
        self._worker.cancel()
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        await self._release(HELD_RELEASE_MS)

    @staticmethod
    def _hidden(button: Control) -> bool:
        return any(v in ("gone", "invisible", "8", "4") for v in button.ancestor_visibility)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(spec.hold.control for spec in self.controller_button_specs if spec.hold is not None and self.controller_button_available(spec.key))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not self.controller_button_available(control) or not 1 <= duration_ms <= 60000:
            raise ValueError("Choose an available held control and duration of 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.execute_action(int(control.removeprefix("cluster018_").removesuffix("_hold")), hold_ms=duration_ms)

    def controller_button_available(self, key: str) -> bool:
        if key == "cluster018_release":
            return True
        try:
            node = int(key.removeprefix("cluster018_").removesuffix("_long").removesuffix("_hold"))
            button = self._button(node)
        except ValueError:
            return False
        if button.hold_affected:
            if button.view_id.endswith("Long") or key.endswith("_hold"):
                return self._selection.hold is True
            return self._selection.hold is not True
        return not self._hidden(button)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec] = []
        for button in self._controls:
            if not button.rich_button or button.status not in (1, 2, 3):
                continue
            if self._hidden(button) and not button.hold_affected:
                continue
            if transition(button, self.layout, "FRAMED", self._selection, "DOWN", app=self.app).local:
                continue
            if button.short is None and button.short_old is None and button.long is None and button.tag is None:
                continue
            key = f"cluster018_{button.node}"
            result.append(ControllerButtonSpec(
                key, button.label, partial(_press, node=button.node),
                translation_key="cluster018_action", translation_placeholders={"action": button.label},
                hold=ControllerHoldSpec(key, release_button_key="cluster018_release") if button.status == 1 else None,
            ))
            if button.hold_affected and not button.view_id.endswith("Long"):
                held_key = key + "_hold"
                name = "Hold " + button.label
                result.append(ControllerButtonSpec(
                    held_key, name, partial(_press, node=button.node),
                    translation_key="cluster018_action", translation_placeholders={"action": name},
                    hold=ControllerHoldSpec(held_key, release_button_key="cluster018_release"),
                ))
            if button.status == 3 and button.long and not button.mem_special and not button.select_special:
                name = "Long press " + button.label
                result.append(ControllerButtonSpec(
                    key + "_long", name, partial(_press, node=button.node, long=True),
                    translation_key="cluster018_action", translation_placeholders={"action": name},
                ))
        result.append(ControllerButtonSpec("cluster018_release", "Release", lambda c: c.stop_all(), translation_key="cluster018_release", release_only=True))
        return tuple(result)

    def _select(self, kind: str, value: str) -> None:
        if kind == "mode" and int(value) in self._model["modes"]:
            self._mode = int(value)
        elif kind == "program" and value in ("recall", "armed"):
            self._selection = replace(self._selection, armed=value == "armed")
        elif kind == "hold" and value in ("release", "hold"):
            self._selection = replace(self._selection, hold=value == "hold")
        elif kind == "head_foot" and value in ("head", "foot"):
            self._selection = replace(self._selection, head=value == "head")
        else:
            raise ValueError("Selection is unavailable on this app layout")
        self._publish()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        choices: dict[str, tuple[str, ...]] = {}
        if len(self._model["modes"]) > 1:
            choices["mode"] = tuple(str(v) for v in self._model["modes"])
        if any(c.mem_special or c.select_special for c in self._controls):
            choices["program"] = ("recall", "armed")
        if any(c.hold_affected for c in self._controls):
            choices["hold"] = ("release", "hold")
        if any(c.tag == "63" for c in self._controls):
            choices["head_foot"] = ("head", "foot")
        specs = []
        for kind, options in choices.items():
            def local(value: str, *, key: str = kind) -> None:
                self._select(key, value)

            async def selected(_controller: BedController, value: str, *, key: str = kind) -> None:
                self._select(key, value)

            specs.append(ControllerSelectSpec("cluster018_" + kind, "cluster018_" + kind, "cluster018_" + kind, options, selected, local_select_fn=local))
        return tuple(specs)

    def _alarm_actions(self) -> dict[str, int]:
        allowed = set(load_catalog(self.app)["alarm_allowlist"].values())
        return {f"node_{c.node}": int(c.alarm_clock, 16) for c in self._controls if c.rich_button and c.alarm_clock in allowed and c.alarm_clock is not None}

    def validate_cluster018_request(self, request: Request) -> None:
        op = request.operation
        if op == "query":
            return
        feature = "alarm" if op in ("alarm", "cancel_alarm") else "light" if op in ("rgb", "lamp_slider", "lamp_save") else "aroma" if op == "aroma" else None
        if feature and feature not in self._receive.menu:
            if feature != "alarm" or not any(c.status == 7 for c in self._controls):
                raise ValueError("The app's capability/menu gate has not enabled this feature")
        if op == "alarm":
            if request.action not in self._alarm_actions() or request.when is not None and (request.when.second or request.when.microsecond):
                raise ValueError("Choose one selected-layout alarm action and a time with minute precision")
        elif op == "rgb":
            if request.color is None or len(request.color) != 3 or any(not 0 <= v <= 255 for v in request.color):
                raise ValueError("Choose an RGB color")
        elif op in ("lamp_slider", "lamp_save"):
            if request.minutes is None or not 0 <= request.minutes <= 15:
                raise ValueError("Choose 0 to 15 minutes")
        elif op == "aroma":
            if request.aroma_values is None or not all(1 <= v <= limit for v, limit in zip(request.aroma_values, (60, 60, 12), strict=True)):
                raise ValueError("Aroma times are 1 to 60 minutes, 1 to 60 minutes, and 1 to 12 hours")
        elif op == "massage_popup":
            if request.popup not in ("15", "30", "45", "toggle") or not any(c.tag == "65" for c in self._controls):
                raise ValueError("Choose a timer offered by this layout’s massage popup")
        elif op == "massage_timer":
            if request.progress is None:
                raise ValueError("Choose the massage timer slider value")
            massage_timer(self.layout, request.progress)
        elif op.startswith("desk_"):
            if self.layout not in ("FWRM", "WFRM"):
                raise ValueError("The desk action requires an exact desk layout")
            if op in ("desk_target", "desk_unit", "desk_recall") and not self._receive.modern_controls:
                raise ValueError("The app's old-desk response has hidden this control")
            if op == "desk_reset" and not self._receive.error_confirmation_pending:
                raise ValueError("The desk has no reported error awaiting confirmation")
            if op == "desk_target" and (request.height is None or self._receive.minimum is None or self._receive.maximum is None):
                raise ValueError("The desk must report its range before setting a target")
            if op == "desk_target":
                assert request.height is not None and self._receive.minimum is not None and self._receive.maximum is not None
                if not math.isfinite(request.height) or not self._receive.minimum <= request.height <= self._receive.maximum or not self._receive.modern_controls:
                    raise ValueError("Choose a target within the current app ruler range")
            if op == "desk_unit" and request.unit not in ("cm", "inches"):
                raise ValueError("Choose cm or inches")
            if op == "desk_recall" and request.slot not in (1, 2, 3, 4):
                raise ValueError("Choose desk button 1 through 4")
            if op == "desk_recall" and not 1 <= request.duration_ms <= 60000:
                raise ValueError("Desk button duration must be between 1 and 60000 ms")

    async def async_execute_cluster018_request(self, request: Request) -> None:
        self.validate_cluster018_request(request)
        op = request.operation
        if op == "query":
            frames = ([ALARM_QUERY] if any(c.alarm_clock is not None for c in self._controls) else []) + [LAMP_QUERY, AROMA_QUERY]
            delay = QUERY_SPACING_MS
        elif op in ("alarm", "cancel_alarm"):
            now = dt_util.now()
            when = request.when
            delay_minutes = alarm_delay(now.hour * 60 + now.minute, when.hour * 60 + when.minute if when else None) if op == "alarm" else 0
            frames = list(alarm(delay_minutes, self._alarm_actions()[request.action] if op == "alarm" and request.action else 0))
            self._pending_alarm = request.action if op == "alarm" else None
            if op == "cancel_alarm":
                self._preferences["alarm_selection"] = None
            delay = ALARM_SPACING_MS
        elif op == "rgb":
            assert request.color is not None
            frames, delay = [rgb(*request.color)], SETTINGS_SPACING_MS
        elif op in ("lamp_slider", "lamp_save"):
            assert request.minutes is not None
            frames, delay = [lamp_timer(request.minutes, save=op == "lamp_save")], 0
        elif op == "aroma":
            assert request.aroma_values is not None
            frames, delay = [aroma(code, value) for code, value in zip((0x1B, 0x1C, 0x1D), request.aroma_values, strict=True)], SETTINGS_SPACING_MS
        elif op == "massage_popup":
            assert request.popup is not None
            frames, delay = [massage_popup(request.popup)], 0
        elif op == "massage_timer":
            assert request.progress is not None
            frames, delay = [massage_timer(self.layout, request.progress)], 0
        elif op == "desk_target":
            assert request.height is not None
            frames, delay = [desk_target(request.height)], 0
        elif op == "desk_unit":
            self._unit_switch = request.unit == "inches"
            frames, delay = [desk_unit(request.unit == "inches")], 0
        elif op == "desk_reset":
            frames, delay = [DESK_CONFIRM], 0
        elif op == "desk_recall":
            assert request.slot is not None
            packet = desk_button(request.slot)
            elapsed = 0
            while elapsed < request.duration_ms and not self._coordinator.cancel_command.is_set():
                await self.write_command(packet)
                if not await self._wait(DESK_REFRESH_MS, self._coordinator.cancel_command):
                    break
                elapsed += DESK_REFRESH_MS
            # This separate worker ends its refresh on UP. No release frame is
            # defined for this path, unlike ordinary RichButton movement.
            return
        else:
            raise ValueError("Unknown app action")
        for packet in frames:
            if self._coordinator.cancel_command.is_set():
                return
            await self.write_command(packet)
            if delay and not await self._wait(delay, self._coordinator.cancel_command):
                return
        if self._coordinator.cancel_command.is_set():
            return
        if op in ("lamp_slider", "lamp_save"):
            self._preferences["lamp_minutes"] = request.minutes
        elif op == "massage_timer":
            self._preferences["massage_progress"] = request.progress
        elif op == "rgb":
            assert request.color is not None
            self._preferences["lamp_rgb"] = bytes(request.color).hex()
        elif op == "desk_reset":
            self._receive.error_confirmation_pending = False
        self._publish()

    async def _unsupported(self) -> None:
        raise NotImplementedError("Use the selected app's labelled controls")

    move_head_up = _unsupported
    move_head_down = _unsupported
    move_back_up = _unsupported
    move_back_down = _unsupported
    move_legs_up = _unsupported
    move_legs_down = _unsupported
    move_feet_up = _unsupported
    move_feet_down = _unsupported
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
    preset_flat = _unsupported

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the selected app's labelled memory controls")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the selected app's labelled programming controls")
