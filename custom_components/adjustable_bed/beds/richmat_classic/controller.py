"""Explicit resource-driven Richmat app profiles, including Luuna and Power Cool.

Each app owns its catalog. No capabilities are inherited from legacy Richmat.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import asdict, replace
from datetime import time
from functools import partial
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_UTILITY
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...const import (
    CONF_MOTOR_PULSE_COUNT,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
)
from ...controller_state import StateKey, StateUpdate
from ...errors import invalid
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles.richmat import RICHMAT_CLASSIC
from ...state_keys import DESK_HEIGHT
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button, classify, unique_buttons
from ..entity_specs import (
    DESK_HEIGHT_SENSOR,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..richmat.labels import resource_label
from . import rise
from .caller import RETAIN, Selection, effective_status, nordic_label, transition
from .profiles import RISE_APPS, Control, controls, load_catalog
from .protocol import (
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
    Wire,
    Worker,
    alarm,
    alarm_capability,
    alarm_choices,
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
from .receive import MalformedFrame, ReceiveState
from .removed_layouts import REMOVED_LAYOUTS
from .requests import Request
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


def control_node(key: str) -> int:
    """The catalog node behind a control key (``richmat_classic_<node>[_raw][_long|_hold]``)."""
    node = key.removeprefix("richmat_classic_")
    for suffix in ("_hold", "_long", "_raw"):
        node = node.removesuffix(suffix)
    return int(node)


# Set only by an admitted multi-receiver settings write, including mixed classic apps.
BEFORE_SETTINGS_WRITE: Final[ContextVar[Callable[[], bool] | None]] = ContextVar(
    "richmat_before_settings_write", default=None
)


# Settings rows a capability reply reveals (``ReceiveState.menu``).
_MENU_ROWS = frozenset({"alarm", "light", "aroma"})


async def _press(
    controller: BedController, node: int, long: bool = False, raw: bool = False
) -> None:
    if not isinstance(controller, RichmatClassicController):
        raise TypeError("This action requires the selected app controller")
    if raw != controller.named_for_nordic(node):
        # Listed for the other connection, where this control does something else.
        raise invalid("richmat_classic_control")
    await controller.execute_action(node, long=long)


STATUS: Final = StateKey[str]("richmat_classic_status")
APP: Final = StateKey[str]("richmat_classic_app")
LAYOUT: Final = StateKey[str]("richmat_classic_layout")
STATE: Final = StateKey[dict[str, object]]("richmat_classic_state")
PREFERENCES: Final = StateKey[dict[str, object]]("richmat_classic_preferences")
REJECTION: Final = StateKey[str | None]("richmat_classic_rejection")
LAMP_SECONDS: Final = StateKey[int | None]("richmat_rise_lamp_seconds")


def _selection_key(kind: str) -> StateKey[str | None]:
    return StateKey[str | None]("richmat_classic_" + kind)


class RichmatClassicController(BedController):
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
        if self.layout in REMOVED_LAYOUTS:
            raise ValueError("This layout ran a factory test; choose the bed's layout in Configure")
        if self.app in RISE_APPS and self.layout in ("WFRM", "FWRM"):
            raise ValueError("Standalone desk layouts are outside the bed integration")
        self._controls = controls(self.app, self.layout)
        self._model = load_catalog(self.app).models[self.layout]
        self._selection = Selection()
        self._mode = 0
        self._worker = Worker()
        self._receive = ReceiveState()
        self._session: Transport | None = None
        self._notifications_started = False
        # The wire of the last session, which still decides the hold scope offline.
        self._wire: Wire | None = None
        self._rejection: str | None = None
        self._preferences: dict[str, object] = {"lamp_minutes": 0, "lamp_rgb": "ffffff", "alarm_selection": None, "massage_progress": 0}
        self._pending_alarm: str | None = None
        self._unit_switch = False
        self._lamp_seconds: int | None = None

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
    def persisted_app_state_key(self) -> str:
        return f"{self.app}:{self.layout}"

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {**self._preferences, "mode": self._mode, "selection": {
            "press_flag": self._selection.press_flag, "head": self._selection.head,
            "armed": self._selection.armed, "hold": self._selection.hold,
        }, "menu": sorted(self._receive.menu), "wire": self._wire}

    def _restore_wire(self, state: Mapping[str, object]) -> None:
        """Take the stored command format: it names the controls before the first connection."""
        wire = state.get("wire")
        if wire not in (None, "RAW", "FRAMED"):
            raise ValueError("Invalid stored command format")
        if wire is not None:
            self._wire = wire

    @property
    def _resolved_wire(self) -> Wire | None:
        """The command format of this session, else of the last one."""
        return self._session.wire if self._session else self._wire

    def _nordic_label(self, button: Control) -> str | None:
        """The control's own name on a Nordic connection, when it differs."""
        return nordic_label(button) if self._resolved_wire == "RAW" else None

    def named_for_nordic(self, node: int) -> bool:
        """Whether this connection lists the control under its Nordic name."""
        return self._nordic_label(self._button(node)) is not None

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)
        minutes = state.get("lamp_minutes", 0)
        color = state.get("lamp_rgb", "ffffff")
        selected = state.get("alarm_selection")
        progress = state.get("massage_progress", 0)
        mode = state.get("mode", 0)
        selection = state.get("selection", {})
        if type(mode) is not int or mode not in self._model.modes or not isinstance(selection, Mapping):
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
        if selected is not None:
            if self.app in RISE_APPS and isinstance(selected, str):
                rise.alarm_action(self._alarm_actions(), tuple(selected.split(",")))
            elif selected not in self._alarm_actions():
                raise ValueError("Saved alarm action is absent from this app layout")
        if type(progress) is not int or not 0 <= progress <= 5:
            raise ValueError("Invalid saved massage slider")
        menu = state.get("menu", [])
        if not isinstance(menu, list) or not set(menu) <= _MENU_ROWS:
            raise ValueError("Invalid saved settings menu")
        self._preferences = {"lamp_minutes": minutes, "lamp_rgb": color, "alarm_selection": selected, "massage_progress": progress}
        self._mode = mode
        self._selection = Selection(press_flag=flag, head=head, armed=armed, hold=hold)
        # Stored menus never prove capabilities about a new receiver session.
        self._receive.menu = set() if self.app in RISE_APPS else set(menu)
        if self.app in RISE_APPS:
            seconds = state.get("lamp_seconds")
            if seconds is not None and (type(seconds) is not int or not 0 <= seconds <= 300):
                raise ValueError("Invalid saved lamp timer")
            self._lamp_seconds = seconds
            self._preferences["lamp_seconds"] = seconds

    def _publish(self) -> None:
        state = asdict(self._receive)
        state["menu"] = sorted(self._receive.menu)
        self.forward_controller_state_updates(
            STATUS("ready" if self._session else "disconnected"),
            APP(self.app),
            LAYOUT(self.layout),
            STATE(state),
            PREFERENCES(dict(self._preferences)),
            REJECTION(self._rejection),
            _selection_key("mode")(str(self._mode)),
            _selection_key("program")("armed" if self._selection.armed else "recall"),
            _selection_key("hold")("hold" if self._selection.hold else "release"),
            _selection_key("head_foot")("head" if self._selection.head else "foot"),
            LAMP_SECONDS(self._lamp_seconds),
            *self._desk_height(),
        )

    def _desk_height(self) -> tuple[StateUpdate, ...]:
        """The cm height the desk screen keeps, whichever unit the desk reports in.

        The last one stays through a reconnect, until the desk reports again.
        """
        height = self._receive.height_cm
        if self.layout not in ("FWRM", "WFRM") or height is None:
            return ()
        # The app's binary32 one-decimal value, as the decimal it displays.
        return (DESK_HEIGHT(round(height, 1)),)

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return self.app in RISE_APPS or self.has_dynamic_buttons

    @property
    def has_dynamic_buttons(self) -> bool:
        # The first connection lists a Nordic bed's own controls.
        return any(c.rich_button and nordic_label(c) for c in self._controls)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.app not in RISE_APPS or "light" not in self._receive.menu:
            return ()

        async def timer(controller: BedController, value: float) -> None:
            if not isinstance(controller, RichmatClassicController):
                raise TypeError("Choose a Luuna Rise or Power Cool bed")
            await controller.async_execute_richmat_rise_request(rise.Request("lamp_timer", seconds=int(value)))

        return (ControllerNumberSpec("richmat_rise_lamp_seconds", "richmat_rise_lamp_seconds", LAMP_SECONDS, 0, 300, 1, timer, "s"),)

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
        status = ControllerStateSensorSpec(
            "richmat_classic_status", "richmat_classic_status", STATUS, "mdi:bed",
            attribute_keys=(APP, LAYOUT, STATE, PREFERENCES, REJECTION),
            card=CARD_UTILITY,
            entity_registry_enabled_default=False,
        )
        return (DESK_HEIGHT_SENSOR, status) if self.layout in ("FWRM", "WFRM") else (status,)

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
        session = select(client, third_service=self._coordinator.entry.data.get(CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False))
        name = self._device_name if self._device_name is not None else self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(name, session.wire, rise=self.app in RISE_APPS))
        self._session = session
        self._wire = session.wire
        # Older profiles retain their proved menu; Rise/Power Cool query it on
        # each session instead of trusting Android's stale activity-local flags.
        self._receive = ReceiveState(menu=set() if self.app in RISE_APPS else set(self._receive.menu))
        self._pending_alarm = None
        self._unit_switch = False
        try:
            self._notifications_started = False
            if session.has_notifications:
                try:
                    result = await client.start_notify(session.notify, partial(self._notification, session))
                    self._notifications_started = result is not False
                except BleakError:
                    if self.app not in RISE_APPS:
                        raise
                    # No authenticated-ready response exists. Failed local
                    # registration blocks capability proof, not bed controls.
                    self._rejection = "Notification registration failed"
            if self.layout in ("WFRM", "FWRM"):
                # RemoteFragment.initData issues this independently of the
                # delayed, notification-conditioned FRAMED transport startup.
                await self._send(DESK_QUERY)
            if session.wire == "FRAMED" and self._notifications_started:
                await asyncio.sleep(STARTUP_MS / 1000)
                await self._send(DESK_QUERY if self.layout in ("WFRM", "FWRM") else INITIALIZE)
            if self.app in RISE_APPS:
                await self.async_execute_richmat_rise_request(rise.Request("query"))
        except BaseException:
            self._session = None
            raise
        self._publish()

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        self._worker.mode = -1
        if session and session.client.is_connected and self._notifications_started:
            await session.client.stop_notify(session.notify)
        self._notifications_started = False
        self._publish()

    def on_disconnect(self) -> None:
        self._session = None
        self._notifications_started = False
        self._worker.cancel()
        self._pending_alarm = None
        if self.app in RISE_APPS:
            self._receive = ReceiveState()
        if self._coordinator.controller is self:
            self._coordinator.cache_capability_controller()
        self._publish()

    async def _send(self, packet: bytes, cancel: asyncio.Event | None = None) -> None:
        """Write one packet; ``cancel`` is set for the command's own frames.

        Setup, query and release writes pass none and are not counted.
        """
        session = self._session
        if session is None or self.client is not session.client or not session.client.is_connected:
            raise ConnectionError("No current app BLE session")
        # Calls are admitted under the coordinator command lock. Never retry an
        # actuator write or carry cached Android objects across connections.
        async with self._ble_lock:
            before_write = BEFORE_SETTINGS_WRITE.get()
            if before_write is not None:
                if self._session is not session or self.client is not session.client or not session.client.is_connected:
                    raise ConnectionError("The captured bed session has ended")
                if (cancel is not None and cancel.is_set()) or not before_write():
                    note_frame_skipped()
                    return
            await session.client.write_gatt_char(session.write, packet, response=session.response)
        note_frame_written(cancel)

    async def write_command(self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = TICK_MS, cancel_event: asyncio.Event | None = None) -> None:
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                note_frame_skipped()
                return
            await self._send(command, cancel)
            if index + 1 < repeat_count and not await self._wait(repeat_delay_ms, cancel):
                note_frame_skipped()
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
            await self._send(control(emission.payload, session.wire, mode), cancel)
        return True

    async def _next_tick(self, cancel: asyncio.Event) -> bool:
        return await self._wait(self._worker.tick_ms, cancel)

    def _button(self, node: int) -> Control:
        for button in self._controls:
            if button.node == node and button.rich_button:
                return button
        raise ValueError("Choose an action this bed model offers")

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

    def _keeps(self, button: Control, selection: Selection) -> bool:
        """Whether a press runs the keep mode under ``selection``.

        The keep mode (mode 1) sends its payload every worker tick until UP; UP
        sets mode 0, which sends the release 50 ms later. The Hold/Release
        selector, memory arming and head/foot selection change which mode a
        press runs. Offline the last session's wire decides; before any session
        either wire may, and the press checks the session's own once connected.
        """
        wire = self._session.wire if self._session is not None else self._wire
        return any(
            self._keeps_on(button, selection, candidate)
            for candidate in ((wire,) if wire is not None else ("FRAMED", "RAW"))
        )

    def _keeps_on(self, button: Control, selection: Selection, wire: Wire) -> bool:
        down = transition(button, self.layout, wire, selection, "DOWN", app=self.app)
        if down.local or down.mode != 1 or not isinstance(down.payload, bytes):
            return False
        return transition(button, self.layout, wire, selection, "UP", app=self.app).mode == 0

    @property
    def execution(self) -> ExecutionCapabilities:
        """Renewable holds on the held controls that run the keep mode (#483).

        All five classic apps: a keep button repeats its payload
        every 150 ms tick (110 ms for TWRM and MLRM names) with no fixed count
        until UP, then releases 50 ms later. Short, long and armed presses keep
        their own gestures, and the Hold/Release selector moves presets and Flat
        between them, so the scope follows the current selection.
        """
        controls = frozenset(
            control
            for control in self.held_control_options
            if self._keeps(self._button(control_node(control)), self._selection)
        )
        if not controls:
            return NO_EXECUTION_CAPABILITIES
        return ExecutionCapabilities(hold="stream", hold_controls=controls)

    async def execute_action(self, node: int, *, long: bool = False, hold_ms: int | None = None) -> None:
        button = self._button(node)
        if button.status not in (1, 2, 3):
            raise ValueError("This node uses a separate local or settings action")
        if self._hidden(button) and not (button.hold_affected and self._selection.hold is True):
            raise ValueError("This control is not available right now")
        if long and button.hold_affected and self._selection.hold is True:
            raise ValueError("Choose the separate save button in Hold mode")
        if button.excluded_long if long else button.excluded_short:
            raise ValueError("This gesture controls an excluded music or aroma accessory")
        cancel = self._coordinator.cancel_command
        # Offline selectors remain usable; a gesture keeps its admitted target
        # and getter context through cleanup while later choices await the next.
        mode, selection = self._mode, self._selection
        context = current_command_context()
        if context is not None and context.lease is not None and not self._keeps(button, selection):
            # Admission checks the scope too; a selector may change after it.
            raise invalid("control_hold_renewal_not_supported")
        status = effective_status(button, self.layout, selection)
        programmed = button.mem_special and selection.armed or button.select_special and selection.armed
        up_applied = False
        completed = False
        if self.app in RISE_APPS:
            # Android can carry a pending save/latch across gestures. HA owns
            # one gesture at a time and cancels that stale actuator intent.
            self._worker.cancel()
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
                if self._worker.mode == 1 and elapsed >= duration and not (context and context.lease):
                    break
                if not await self._next_tick(cancel):
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
                if not completed and not (self.app in RISE_APPS and self._session and self._session.wire == "RAW" and status == 3 and button.short is None and button.short_old is None):
                    self._worker.cancel()
                    delay = HELD_RELEASE_MS if status == 1 or button.mem_special or self.app in RISE_APPS and status == 3 and button.short is None else TAP_RELEASE_MS
                    await self._release(delay, mode=mode)
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
            raise ValueError("Choose a control this bed offers and a duration of up to 60 seconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.execute_action(control_node(control), hold_ms=duration_ms)

    def controller_button_available(self, key: str) -> bool:
        if key == "richmat_classic_release":
            return True
        try:
            button = self._button(control_node(key))
        except ValueError:
            return False
        if ("_raw" in key) != (self._nordic_label(button) is not None):
            return False
        if button.hold_affected:
            if button.view_id.endswith("Long") or key.endswith("_hold"):
                return self._selection.hold is True
            return self._selection.hold is not True
        return not self._hidden(button)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec | None] = []
        for button in self._controls:
            if not button.rich_button or button.status not in (1, 2, 3):
                continue
            if self._hidden(button) and not button.hold_affected:
                continue
            if transition(button, self.layout, "FRAMED", self._selection, "DOWN", app=self.app).local:
                continue
            if button.short is None and button.short_old is None and button.long is None and button.tag is None:
                continue
            # A control a Nordic bed gives another function is another entity.
            legacy = self._nordic_label(button)
            key = f"richmat_classic_{button.node}" + ("_raw" if legacy else "")
            label = legacy or resource_label(button.label)
            press = partial(_press, node=button.node, raw=legacy is not None)
            control = classify(label)
            if not button.excluded_short:
                result.append(catalog_button(
                key, label, press,
                # The Set key only arms programming: it is a tap, as the saves it arms are.
                # A motor key that saves on a Nordic bed is a tap too.
                hold=ControllerHoldSpec(key, release_button_key="richmat_classic_release") if (button.status == 1 or button.mem_special and not self._selection.armed) and label != "Program" and not (control and control.kind is Kind.SAVE) else None,
                ))
            if button.hold_affected and not button.view_id.endswith("Long"):
                held_key = key + "_hold"
                result.append(catalog_button(
                    held_key, f"{label} (hold)", press,
                    kind=control.kind if control is not None else None,
                    hold=ControllerHoldSpec(held_key, release_button_key="richmat_classic_release"),
                ))
            if button.status == 3 and button.long and not button.excluded_long and not button.mem_special and not button.select_special:
                long = partial(press, long=True)
                if button.excluded_short or button.short is None and button.short_old is None:
                    # The long press is this button's only action.
                    result.append(catalog_button(key + "_long", label, long))
                elif control is not None and control.kind in (Kind.PRESET, Kind.MEMORY):
                    # A preset's long press saves the position there.
                    result.append(catalog_button(key + "_long", "Save " + label, long, kind=Kind.SAVE))
                elif button.long != button.short:
                    # Another long operand's effect is unnamed: there to enable.
                    result.append(catalog_button(key + "_long", f"{label} (long press)", long, enabled=False))
        result.append(ControllerButtonSpec(
            "richmat_classic_release", "Release", lambda c: c.stop_all(),
            translation_key="richmat_classic_release", release_only=True, card=CARD_HIDDEN,
        ))
        return unique_buttons(result)

    def _select(self, kind: str, value: str) -> None:
        if kind == "mode" and int(value) in self._model.modes:
            self._mode = int(value)
        elif kind == "program" and value in ("recall", "armed"):
            self._selection = replace(self._selection, armed=value == "armed")
        elif kind == "hold" and value in ("release", "hold"):
            self._selection = replace(self._selection, hold=value == "hold")
        elif kind == "head_foot" and value in ("head", "foot"):
            self._selection = replace(self._selection, head=value == "head")
        else:
            raise ValueError("This bed model does not offer that choice")
        self._publish()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        choices: dict[str, tuple[str, ...]] = {}
        if len(self._model.modes) > 1:
            choices["mode"] = tuple(str(v) for v in self._model.modes)
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

            specs.append(ControllerSelectSpec("richmat_classic_" + kind, "richmat_classic_" + kind, _selection_key(kind), options, selected, local_select_fn=local))
        return tuple(specs)

    def _alarm_actions(self) -> dict[str, int]:
        allowed = set(load_catalog(self.app).alarm_allowlist.values())
        return {f"node_{c.node}": int(c.alarm_clock, 16) for c in self._controls if c.rich_button and c.alarm_clock in allowed and c.alarm_clock is not None}

    @property
    def settings_transport(self) -> Transport | None:
        """Return the live transport whose settings have been admitted."""
        session = self._session
        if session is not None and self.client is session.client and session.client.is_connected:
            return session
        return None

    def validate_richmat_classic_request(self, request: Request) -> None:
        if self.app in RISE_APPS:
            raise ValueError("Use the Luuna Rise / Power Cool bed settings action")
        op = request.operation
        if op == "lamp_timeout":
            raise invalid("dynasty_request")
        if op == "query":
            return
        feature = "alarm" if op in ("alarm", "cancel_alarm") else "light" if op in ("rgb", "lamp_slider", "lamp_save") else "aroma" if op == "aroma" else None
        if feature and feature not in self._receive.menu:
            if feature != "alarm" or not any(c.status == 7 for c in self._controls):
                raise ValueError("The bed has not reported that it offers this. Reconnect it and try again")
        if op == "alarm":
            if request.action not in self._alarm_actions() or request.when is not None and (request.when.second or request.when.microsecond):
                raise ValueError("Choose an alarm action this bed model offers and an alarm time")
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
                raise ValueError("Choose a massage timer this bed model offers")
        elif op == "massage_timer":
            if request.progress is None:
                raise ValueError("Choose a massage timer value")
            massage_timer(self.layout, request.progress)
        elif op.startswith("desk_"):
            if self.layout not in ("FWRM", "WFRM"):
                raise ValueError("The desk action requires an exact desk layout")
            if op in ("desk_target", "desk_unit", "desk_recall") and not self._receive.modern_controls:
                raise ValueError("This desk does not offer that control")
            if op == "desk_reset" and not self._receive.error_confirmation_pending:
                raise ValueError("The desk has no reported error awaiting confirmation")
            if op == "desk_target" and (request.height is None or self._receive.minimum is None or self._receive.maximum is None):
                raise ValueError("The desk must report its range before setting a target")
            if op == "desk_target":
                assert request.height is not None and self._receive.minimum is not None and self._receive.maximum is not None
                if not math.isfinite(request.height) or not self._receive.minimum <= request.height <= self._receive.maximum or not self._receive.modern_controls:
                    raise ValueError("Choose a height within the desk's range")
            if op == "desk_unit" and request.unit not in ("cm", "inches"):
                raise ValueError("Choose cm or inches")
            if op == "desk_recall" and request.slot not in (1, 2, 3, 4):
                raise ValueError("Choose desk button 1 through 4")
            if op == "desk_recall" and not 1 <= request.duration_ms <= 60000:
                raise ValueError("Choose a duration of up to 60 seconds")

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        self.validate_richmat_classic_request(request)
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

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        # The other classic apps keep their alarm in their own action.
        capability = alarm_capability(self._alarm_actions()) if self.app in RISE_APPS else None
        # The bed reports its alarm page on each connection.
        return replace(capability, live_check=True) if capability else None

    def _rise_alarm(self, alarm: AlarmRequest) -> rise.Request:
        if not alarm.enabled:
            return rise.Request("cancel_alarm")
        actions = alarm_choices(self._alarm_actions(), alarm)
        return rise.Request("alarm", actions=actions, when=time(alarm.hour, alarm.minute))

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_richmat_rise_request(self._rise_alarm(alarm), live=False)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_richmat_rise_request(self._rise_alarm(alarm))

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.async_execute_richmat_rise_request(self._rise_alarm(alarm))

    def validate_richmat_rise_request(self, request: rise.Request, *, live: bool = True) -> None:
        if self.app not in RISE_APPS:
            raise ValueError("Choose a Luuna Rise or Power Cool profile")
        op = request.operation
        feature = "alarm" if op in ("alarm", "cancel_alarm") else "light" if op in ("rgb", "lamp_timer") else None
        if live and feature and (self._session is None or feature not in self._receive.menu):
            raise ValueError("The bed has not reported that it offers this. Reconnect it and try again")
        if op == "alarm":
            rise.alarm_action(self._alarm_actions(), request.actions)
            if request.when and (request.when.second or request.when.microsecond):
                raise ValueError("Choose a time with minute precision")
        elif op == "rgb":
            if request.color is None or len(request.color) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in request.color):
                raise ValueError("Enter a light color as red, green and blue values from 0 to 255")
        elif op == "lamp_timer":
            if request.seconds is None:
                raise ValueError("Choose the lamp timer in seconds")
            rise.lamp_timer(request.seconds, save=request.timer_save)
        elif op == "massage_timer":
            if request.progress is None:
                raise ValueError("Choose a timer value")
            massage_timer(self.layout, request.progress)
        elif op == "massage_popup":
            if request.popup not in ("15", "30", "45", "toggle") or not any(c.tag == "65" for c in self._controls):
                raise ValueError("This bed model does not offer that timer")
        elif op not in ("query", "cancel_alarm"):
            raise ValueError("Unknown bed utility")

    async def async_execute_richmat_rise_request(self, request: rise.Request) -> None:
        self.validate_richmat_rise_request(request)
        op = request.operation
        cancel = self._coordinator.cancel_command
        delay = 0
        if op == "query":
            frames = ([ALARM_QUERY] if any(c.alarm_clock is not None for c in self._controls) else []) + [LAMP_QUERY]
            delay = QUERY_SPACING_MS
        elif op in ("alarm", "cancel_alarm"):
            now = dt_util.now()
            when = request.when
            minutes = alarm_delay(now.hour * 60 + now.minute, when.hour * 60 + when.minute if when else None) if op == "alarm" else 0
            code = rise.alarm_action(self._alarm_actions(), request.actions) if op == "alarm" else 0
            frames = list(alarm(minutes, code))
            self._pending_alarm = ",".join(request.actions) if op == "alarm" else None
            delay = ALARM_SPACING_MS
        elif op == "rgb":
            assert request.color is not None
            frames, delay = [rgb(*request.color)], SETTINGS_SPACING_MS
        elif op == "lamp_timer":
            assert request.seconds is not None
            frames = [rise.lamp_timer(request.seconds, save=request.timer_save)]
        elif op == "massage_timer":
            assert request.progress is not None
            frames = [massage_timer(self.layout, request.progress)]
        elif op == "massage_popup":
            assert request.popup is not None
            frames = [massage_popup(request.popup)]
        else:
            raise ValueError("Unknown bed utility")
        for frame in frames:
            if cancel.is_set():
                return
            await self.write_command(frame)
            if delay and not await self._wait(delay, cancel):
                return
        if op == "lamp_timer":
            self._lamp_seconds = request.seconds
            self._preferences["lamp_seconds"] = request.seconds
        elif op == "massage_timer":
            self._preferences["massage_progress"] = request.progress
        elif op == "rgb":
            assert request.color is not None
            self._preferences["lamp_rgb"] = bytes(request.color).hex()
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


async def build_controller(ctx: BuildContext) -> RichmatClassicController:
    """Build the controller after loading the app's gzip catalog off the event loop."""
    from .profiles import load_catalog

    await ctx.coordinator.hass.async_add_executor_job(load_catalog, ctx.variant)
    if ctx.variant == "dynasty":
        await ctx.preload("richmat_classic.dynasty")
        from .dynasty import DynastyController

        return DynastyController(ctx.coordinator, app=ctx.variant, device_name=ctx.device_name)
    if ctx.variant == "dreamlab2":
        await ctx.preload("richmat_classic.dreamlab")
        from .dreamlab import DreamlabController

        return DreamlabController(
            ctx.coordinator,
            app=ctx.variant,
            device_name=ctx.advertisement_local_name,
            capability_snapshot=ctx.stored_capabilities("richmat_classic_apps"),
        )
    if ctx.variant == "jerome2":
        await ctx.preload("richmat_classic.jerome")
        from .jerome import JeromeController

        return JeromeController(
            ctx.coordinator, app=ctx.variant, device_name=ctx.device_name,
            capability_snapshot=ctx.stored_capabilities("richmat_classic_apps"),
        )
    if ctx.variant == "maxprime":
        await ctx.preload("richmat_classic.maxprime")
        from .maxprime import MaxprimeController

        return MaxprimeController(ctx.coordinator, device_name=ctx.device_name)
    if ctx.variant == "baseremote":
        await ctx.preload("baseremote.controller")
        from ..baseremote.controller import BaseRemoteController

        return BaseRemoteController(ctx.coordinator, app=ctx.variant, device_name=ctx.device_name)
    from ...profiles.richmat_resource_apps import APPS

    if ctx.variant == "sleepfunction":
        await ctx.preload("richmat_classic.sleepfunction")
        from .sleepfunction import SleepFunctionController

        return SleepFunctionController(ctx.coordinator, app=ctx.variant, device_name=ctx.device_name)
    if ctx.variant == "bedsmart":
        await ctx.preload("richmat_classic.bedsmart")
        from .bedsmart import BedSmartController

        return BedSmartController(ctx.coordinator, device_name=ctx.device_name)
    if ctx.variant == "lp2":
        await ctx.preload("richmat_classic.lp2")
        from .lp2 import Lp2Controller

        return Lp2Controller(ctx.coordinator, device_name=ctx.device_name)
    if ctx.variant in APPS:
        await ctx.preload("richmat_classic.resource_controller")
        from .resource_controller import ResourceBedController

        return ResourceBedController(ctx.coordinator, app=ctx.variant, device_name=ctx.device_name)
    return RichmatClassicController(ctx.coordinator, app=ctx.variant, device_name=ctx.device_name)
