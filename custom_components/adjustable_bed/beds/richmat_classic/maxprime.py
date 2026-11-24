"""Maxprime's resource-driven control and connection-scoped feature replies."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import partial
from math import ceil
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_MASSAGE, CARD_UTILITY
from ...codec import richmat as codec
from ...command_scheduler import (
    CommandContext,
    current_command_context,
    note_frame_skipped,
)
from ...const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE, CONF_RICHMAT_CLASSIC_THIRD_SERVICE
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles import maxprime
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, require_controller
from ..cancellation import settled
from ..catalog_buttons import catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerSwitchSpec,
)
from ..lifecycle import ControllerSession
from . import protocol as p
from .caller import Selection
from .controller import STATUS
from .maxprime_commands import MASSAGE_ZONES, Gesture, alarm_code, gesture
from .receive import MalformedFrame, ReceiveState
from .requests import Request
from .session import SessionController
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

RELEASE_KEY: Final = "maxprime_release"
MODE: Final = StateKey[str | None]("maxprime_mode")
PRESS: Final = StateKey[str | None]("maxprime_press")
AXIS: Final = StateKey[str | None]("maxprime_axis")
LAMP_SECONDS: Final = StateKey[int | None]("maxprime_lamp_seconds")
MASSAGE_POSITION: Final = StateKey[int | None]("maxprime_massage_position")
SYNCHRONIZED: Final = StateKey[bool | None]("maxprime_synchronized")
MASSAGE_ON: Final = StateKey[bool | None]("maxprime_massage_on")
ALARM_ENABLED: Final = StateKey[bool | None]("maxprime_alarm_enabled")
_LIGHT_TOGGLES: Final = frozenset({"k_ubl_on_off", "com_ubl_on_off", "com_msg_ubl_on_off_old"})
_PROBES: Final = (p.LAMP_QUERY, p.AROMA_QUERY)
_AROMA_LIMITS: Final = (60, 60, 12)


class MaxprimeController(SessionController):
    """A classic Richmat receiver with Maxprime's own layouts and settings."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, device_name: str | None = None
    ) -> None:
        layout = coordinator.entry.data.get(CONF_PRODUCT_TYPE)
        if layout not in maxprime.LAYOUTS or layout in maxprime.NAVIGATION:
            raise invalid("maxprime_layout")
        super().__init__(coordinator, app=maxprime.APP, device_name=device_name)
        self._selection = Selection(hold=False)
        self._release_scope: tuple[CommandContext, Transport, int] | None = None
        self._known_light = False
        self._alarm_enabled: bool | None = None
        self._alarm_codes = frozenset(
            int(button.alarm_clock, 16) for button in self._controls if button.alarm_clock
        )
        self._direct_alarm = any(button.status == 7 for button in self._controls)

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {
            "wire": self._wire,
            "known_light": self._known_light,
            "mode": self._mode,
            "hold": self._selection.hold,
            "axis": self._selection.press_flag,
            "alarm_enabled": self._alarm_enabled,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)
        self._known_light = state.get("known_light") is True
        enabled = state.get("alarm_enabled")
        if isinstance(enabled, bool):
            self._alarm_enabled = enabled
        mode = state.get("mode")
        if type(mode) is int and mode in self._model.modes:
            self._mode = mode
        axis = state.get("axis")
        self._selection = Selection(
            hold=state.get("hold") is True,
            press_flag=axis if isinstance(axis, str) and axis in ("53", "54", "55") else "53",
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        state = self._receive
        return {
            "layout": self.layout,
            "wire": self._resolved_wire,
            "mode": self._mode,
            "reported_settings": sorted(state.menu),
            "alarm_enabled": self._alarm_enabled,
            "last_settings_reply": state.last_value,
            "rejection": self._rejection,
            "hardware": "UNVERIFIED",
        }

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        if "light" in self._receive.menu:
            return ()
        keys = ("controller_number_maxprime_lamp_seconds",)
        return (*keys, "under_bed_lights") if self.light_color_control_pending else keys

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            STATUS("ready" if self._session else "disconnected"),
            MODE(str(self._mode)),
            PRESS("hold" if self._selection.hold else "release"),
            AXIS(self._selection.press_flag),
            ALARM_ENABLED(self._alarm_enabled),
        )

    def _clear_link_state(self) -> None:
        self._release_scope = None
        self._receive = ReceiveState()
        self._rejection = None
        self.forward_controller_state_updates(
            LAMP_SECONDS(None),
            SYNCHRONIZED(None),
            MASSAGE_ON(None),
            MASSAGE_POSITION(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        fallback = self._coordinator.entry.data.get(CONF_RICHMAT_CLASSIC_THIRD_SERVICE) is True
        services = list(client.services)
        # The hidden network-management characteristic cannot become a bed role.
        if len(services) > 2 and services[2].uuid.lower() == "0000ffe0-0000-1000-8000-00805f9b34fb":
            fallback = False
        try:
            session = select(client, third_service=fallback)
        except ValueError as error:
            raise BedNotConnectedError("maxprime_transport") from error
        name = self._device_name or self._coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
        self._worker.set_interval(maxprime.interval_ms(name, raw=session.wire == "RAW"))
        self._clear_link_state()
        self._notifications_started = False
        self._session = session
        try:
            with self._transaction():
                if session.has_notifications:

                    async def subscribe() -> None:
                        # Bleak may register its callback before the await returns.
                        self._notifications_started = True
                        try:
                            result = await client.start_notify(
                                session.notify, partial(self._notification, session)
                            )
                            self._notifications_started = result is not False
                        except BleakError:
                            self._rejection = "Subscription failed"
                            await self._unsubscribe(session)

                    await settled(subscribe())
                if session.wire == "FRAMED" and self._notifications_started:
                    await asyncio.sleep(p.STARTUP_MS / 1000)
                    await self._send(p.INITIALIZE)
        except BaseException:
            if self._session is session:
                await settled(self.stop_notify())
            raise
        self._wire = session.wire
        self._publish()

    async def async_after_connect(self, session: ControllerSession) -> None:
        if not self._notifications_started or self._session is None:
            return
        with self._transaction():
            for frame in self._probes:
                if not session.is_current():
                    return
                try:
                    await self._send(frame)
                except BleakError, OSError:
                    self._rejection = "Settings probe failed"
                await asyncio.sleep(p.QUERY_SPACING_MS / 1000)

    async def _unsubscribe(self, session: Transport) -> None:
        subscribed, self._notifications_started = self._notifications_started, False
        if subscribed and self.client is session.client and session.client.is_connected:
            try:
                await session.client.stop_notify(session.notify)
            except BleakError:
                # On link teardown Bleak also removes its subscription callback.
                pass

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        self._clear_link_state()
        if session is not None:
            await settled(self._unsubscribe(session))
        self._publish()

    def on_disconnect(self) -> None:
        self._clear_link_state()
        super().on_disconnect()

    def _notification(
        self, session: Transport, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        if len(self._receive.buffer) + len(data) * 2 > 4096:
            self._receive.buffer = ""
        try:
            self._receive.feed(
                bytes(data),
                app=self.app,
                layout=self.layout,
                desk_bound=False,
                table_controls_bound=False,
            )
        except MalformedFrame:
            self._rejection = "Malformed settings reply"
            return
        self._rejection = None
        self._known_light |= "light" in self._receive.menu
        packet = self._receive.value_event
        if packet in ("6e0e00017d", "6e0e00037f"):
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(packet == "6e0e00037f"))
        elif packet in ("6e07010177", "6e07010278"):
            self._alarm_enabled = packet == "6e07010177"
        if packet is not None:
            self._publish()

    @property
    def _probes(self) -> tuple[bytes, ...]:
        return (p.ALARM_QUERY, *_PROBES) if self._alarm_codes else _PROBES

    def _gestures(self, wire: p.Wire, *, both_press_modes: bool = False) -> dict[str, Gesture]:
        result = {}
        hold_modes = (False, True) if both_press_modes else (bool(self._selection.hold),)
        for button in self._controls:
            for hold in hold_modes:
                selection = replace(self._selection, hold=hold)
                for long in (False, True):
                    action = gesture(button, self.layout, wire, selection, long=long)
                    if action is None:
                        continue
                    key = f"maxprime_{self.layout.lower()}_{action.node}" + (
                        "_long" if long else ""
                    )
                    if button.hold_affected and hold and not long:
                        key += "_hold"
                    result[key] = action
        return result

    def _named_gestures(self, *, both_press_modes: bool = False) -> dict[str, Gesture]:
        raw = self._gestures("RAW", both_press_modes=both_press_modes)
        framed = self._gestures("FRAMED", both_press_modes=both_press_modes)
        shared = {
            key for key in raw.keys() & framed.keys() if raw[key].resource == framed[key].resource
        }
        wire = self._resolved_wire
        if wire is None:
            return {key: action for key, action in framed.items() if key in shared}
        current = raw if wire == "RAW" else framed
        return {
            key if key in shared else f"{key}_{wire.lower()}": action
            for key, action in current.items()
        }

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        async def press(controller: BedController, *, key: str) -> None:
            await require_controller(controller, MaxprimeController)._execute_gesture(key)

        specs = []
        light_toggle = self._light_toggle_key
        paired_keys = {key for pair in self._switch_gestures().values() for key in pair}
        for key, action in self._named_gestures(both_press_modes=True).items():
            if key == light_toggle or key in paired_keys:
                continue
            label = action.label
            if key.endswith(("_hold", "_hold_raw", "_hold_framed")) and action.repeat:
                label += " (hold)"
            specs.append(
                catalog_button(
                    key,
                    label,
                    partial(press, key=key),
                    kind=action.kind,
                    meaning=action.label,
                    hold=ControllerHoldSpec(key, release_button_key=RELEASE_KEY)
                    if action.repeat
                    else None,
                    requires_confirmation=action.confirm,
                    invalidates_position=action.repeat,
                )
            )
        specs.append(
            ControllerButtonSpec(
                RELEASE_KEY,
                "Release",
                lambda c: c.stop_all(),
                translation_key="richmat_classic_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        if self.layout == "Y6RM":
            specs.append(
                ControllerButtonSpec(
                    "maxprime_massage_timer_toggle",
                    "Toggle massage timer",
                    lambda c: require_controller(c, MaxprimeController)._toggle_massage_timer(),
                    translation_key="maxprime_massage_timer_toggle",
                    card=CARD_MASSAGE,
                )
            )
        return unique_buttons(specs)

    def controller_button_available(self, key: str) -> bool:
        return (
            key == RELEASE_KEY
            or (key == "maxprime_massage_timer_toggle" and self.layout == "Y6RM")
            or key in self._named_gestures()
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs = []
        if len(self._model.modes) > 1 and self._resolved_wire == "FRAMED":
            specs.append(
                self._local_select("richmat_classic_mode", MODE, tuple(map(str, self._model.modes)))
            )
        if any(button.hold_affected for button in self._controls):
            specs.append(self._local_select("richmat_classic_hold", PRESS, ("release", "hold")))
        if self.layout == "U3RM":
            specs.append(self._local_select("maxprime_axis", AXIS, ("53", "54", "55")))
        return tuple(specs)

    def _local_select(
        self, translation: str, state: StateKey[str | None], options: tuple[str, ...]
    ) -> ControllerSelectSpec:
        def choose(value: str) -> None:
            if value not in options or state is MODE and self._resolved_wire != "FRAMED":
                raise invalid("maxprime_control")
            if state is MODE:
                if self._mode != int(value):
                    self._mode = int(value)
                    self.forward_controller_state_updates(SYNCHRONIZED(None), MASSAGE_ON(None))
            elif state is PRESS:
                self._selection = replace(self._selection, hold=value == "hold")
            else:
                self._selection = replace(self._selection, press_flag=value)
            self._publish()

        async def selected(_controller: BedController, value: str) -> None:
            choose(value)

        return ControllerSelectSpec(
            state, translation, state, options, selected, local_select_fn=choose
        )

    def _switch_gestures(self) -> dict[str, tuple[str, str]]:
        active = {
            action.resource: key
            for key, action in self._named_gestures().items()
            if not action.repeat and not action.confirm
        }
        result = {}
        if "k_sync_on" in active and "k_sync_off" in active:
            result["synchronization"] = (active["k_sync_on"], active["k_sync_off"])
        if "com_msg_on" in active:
            for off in ("com_msg_off", "com_msg_off2", "com_msg_off3"):
                if off in active:
                    result["massage"] = (active["com_msg_on"], active[off])
                    break
        return result

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        async def set_switch(controller: BedController, enabled: bool, *, name: str) -> None:
            current = require_controller(controller, MaxprimeController)
            pair = current._switch_gestures().get(name)
            if pair is None:
                raise invalid("maxprime_control")
            key = SYNCHRONIZED if name == "synchronization" else MASSAGE_ON
            session, mode = current._session, current._mode
            with current.sent_state(
                key(enabled),
                is_current=lambda: current._session is session and current._mode == mode,
            ):
                await current._execute_gesture(pair[0 if enabled else 1])

        return tuple(
            ControllerSwitchSpec(
                "maxprime_" + name,
                name,
                partial(set_switch, name=name),
                state_key=SYNCHRONIZED if name == "synchronization" else MASSAGE_ON,
                assumed_state=True,
                card=CARD_MASSAGE if name == "massage" else CARD_UTILITY,
            )
            for name in self._switch_gestures()
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key, action in self._named_gestures().items() if action.repeat)

    @property
    def execution(self) -> ExecutionCapabilities:
        controls = frozenset(self.held_control_options)
        if not controls:
            return NO_EXECUTION_CAPABILITIES
        return ExecutionCapabilities(hold="stream", hold_controls=controls)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60000:
            raise invalid("maxprime_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._execute_gesture(control, duration_ms=duration_ms)

    async def _execute_gesture(self, key: str, *, duration_ms: int | None = None) -> None:
        with self._transaction() as session:
            action = self._named_gestures().get(key)
            if action is None:
                raise invalid("maxprime_control")
            context = current_command_context()
            lease = context.lease if context else None
            if not action.repeat and (duration_ms is not None or lease is not None):
                raise invalid("maxprime_control")
            mode = self._mode
            cancel = self._coordinator.cancel_command
            tick = self._worker.tick_ms
            threshold = action.threshold_ms // tick * tick
            packet = p.control(action.payload, session.wire, mode)
            clock = asyncio.get_running_loop().time
            duration = (
                duration_ms
                if duration_ms is not None
                else self._coordinator.motor_pulse_count * tick
            )
            deadline = clock() + duration / 1000
            try:
                if threshold and not await self._wait(threshold, cancel):
                    note_frame_skipped()
                    return
                next_tick = clock()
                await self.write_command(packet)
                if action.axis_after is not None and not cancel.is_set():
                    self._selection = replace(self._selection, press_flag=action.axis_after)
                    self._publish()
                while action.repeat and not cancel.is_set():
                    next_tick += tick / 1000
                    if lease is None and next_tick >= deadline - 1e-6:
                        end = ceil((deadline - clock()) * 1000)
                        if end > 0:
                            await self._wait(end, cancel)
                        break
                    delay = ceil((next_tick - clock()) * 1000 - 1e-6)
                    if delay > 0:
                        if not await self._wait(delay, cancel):
                            note_frame_skipped()
                            break
                    else:
                        # A slow acknowledged write must never cause a burst.
                        next_tick = clock()
                    if lease is None and clock() >= deadline:
                        break
                    await self.write_command(packet)
            finally:
                if action.release_ms is not None:
                    await self._release_gesture(session, mode, action.release_ms, context)

    async def _release_gesture(
        self, session: Transport, mode: int, delay: int, context: CommandContext | None
    ) -> None:
        async def send() -> None:
            await asyncio.sleep(delay / 1000)
            if self._session is session:
                await self._send(p.release(session.wire, mode))
                if context is not None:
                    context.cleanup_stop_sent = True

        if context is not None:
            self._release_scope = (context, session, mode)
        # Record delivery inside the cleanup task, before cancellation returns
        # the wire lane to the public STOP.
        await settled(send())

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        with self._transaction() as session:
            mode = self._mode
            context, scope = current_command_context(), self._release_scope
            self._release_scope = None
            if context is not None and scope is not None:
                previous, link, captured_mode = scope
                if link is session and any(
                    preempted is previous for preempted in context.preempted_contexts
                ):
                    if previous.cleanup_stop_sent:
                        return
                    mode = captured_mode
            await self._release(p.HELD_RELEASE_MS, mode=mode)

    async def _frames(self, frames: tuple[bytes, ...], delay: int = 0) -> None:
        cancel = self._coordinator.cancel_command
        with self._transaction():
            for index, frame in enumerate(frames):
                try:
                    await self.write_command(frame)
                    if delay and not await self._wait(delay, cancel):
                        if index + 1 < len(frames):
                            note_frame_skipped()
                        return
                except asyncio.CancelledError:
                    if index + 1 < len(frames):
                        note_frame_skipped()
                    raise

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self._alarm_codes:
            return None
        actions = tuple(
            dict.fromkeys(
                action for code, action in p.ALARM_WAKE_ACTIONS.items() if code in self._alarm_codes
            )
        )
        zones = tuple(
            zone
            for zone, code in MASSAGE_ZONES.items()
            if code in self._alarm_codes or zone == "both" and {0x4C, 0x4E} <= self._alarm_codes
        )
        return AlarmCapability(
            wake_actions=(*actions, "none") if zones else actions,
            massage=bool(zones),
            massage_zones=zones,
            default_massage_zone=False,
            requires_wake_action=True,
            live_check=not self._direct_alarm,
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self._alarm_codes:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                ALARM_ENABLED,
                ALARM_ENABLED,
                ALARM_ENABLED,
                "mdi:alarm",
            ),
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if self.alarm_capability is None:
            raise invalid("maxprime_alarm")
        alarm_code(self._alarm_codes, alarm)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        if not self._direct_alarm and "alarm" not in self._receive.menu:
            raise invalid("maxprime_settings")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        now = dt_util.now()
        minutes = (
            p.alarm_delay(now.hour * 60 + now.minute, alarm.hour * 60 + alarm.minute)
            if alarm.enabled
            else 0
        )
        await self._frames(
            p.alarm(minutes, alarm_code(self._alarm_codes, alarm)), p.ALARM_SPACING_MS
        )

    @property
    def _light_toggle_key(self) -> str | None:
        # A single HA light cannot represent a mode-scoped power toggle.
        if len(self._model.modes) > 1:
            return None
        return next(
            (
                key
                for key, action in self._named_gestures().items()
                if action.resource in _LIGHT_TOGGLES and not action.repeat
            ),
            None,
        )

    @property
    def supports_lights(self) -> bool:
        return self._light_toggle_key is not None

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_color_control(self) -> bool:
        return self.supports_lights and "light" in self._receive.menu

    @property
    def light_color_control_pending(self) -> bool:
        return self.supports_lights and self._known_light and "light" not in self._receive.menu

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    async def lights_toggle(self) -> None:
        if (key := self._light_toggle_key) is None:
            await super().lights_toggle()
            return
        await self._execute_gesture(key)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if (
            "light" not in self._receive.menu
            or len(rgb_color) != 3
            or any(
                type(component) is not int or not 0 <= component <= 255 for component in rgb_color
            )
        ):
            raise invalid("maxprime_settings")
        with self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color)):
            await self._frames((codec.rgb(*rgb_color),), p.SETTINGS_SPACING_MS)

    @property
    def supports_massage_timer(self) -> bool:
        return self.layout == "Y6RM"

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    @property
    def massage_timer_options(self) -> list[int]:
        return [15, 30, 45] if self.supports_massage_timer else []

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage_timer

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise invalid("maxprime_control")
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self._frames((p.massage_popup(str(minutes)),))

    async def _toggle_massage_timer(self) -> None:
        if not self.supports_massage_timer:
            raise invalid("maxprime_control")
        with self.sent_state(MASSAGE_TIMER_MINUTES(None)):
            await self._frames((p.massage_popup("toggle"),))

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        if "light" in self._receive.menu or self._known_light:

            async def lamp(controller: BedController, value: float) -> None:
                await require_controller(controller, MaxprimeController)._set_light_duration(value)

            specs.append(
                ControllerNumberSpec(
                    LAMP_SECONDS,
                    LAMP_SECONDS,
                    LAMP_SECONDS,
                    0,
                    300,
                    1,
                    lamp,
                    "s",
                )
            )
        if self.layout in ("D1RM", "D9RM"):

            async def timer(controller: BedController, value: float) -> None:
                current = require_controller(controller, MaxprimeController)
                if not 0 <= value <= 5 or int(value) != value:
                    raise invalid("maxprime_control")
                with current.sent_state(MASSAGE_POSITION(int(value))):
                    await current._frames((p.massage_timer(current.layout, int(value)),))

            specs.append(
                ControllerNumberSpec(
                    MASSAGE_POSITION,
                    MASSAGE_POSITION,
                    MASSAGE_POSITION,
                    0,
                    5,
                    1,
                    timer,
                    card=CARD_MASSAGE,
                )
            )
        return tuple(specs)

    async def _set_light_duration(self, value: float) -> None:
        if "light" not in self._receive.menu or not 0 <= value <= 300 or int(value) != value:
            raise invalid("maxprime_settings")
        seconds = int(value)
        with self.sent_state(LAMP_SECONDS(seconds)):
            await self._frames((codec.light_timer(seconds >> 8, seconds),))

    def validate_richmat_classic_request(self, request: Request) -> None:
        if request.operation == "query":
            return
        if (
            request.operation == "rgb"
            and request.color is not None
            and len(request.color) == 3
            and all(type(v) is int and 0 <= v <= 255 for v in request.color)
        ):
            return
        if (
            request.operation == "aroma"
            and request.aroma_values is not None
            and len(request.aroma_values) == 3
            and all(
                type(v) is int and 1 <= v <= maximum
                for v, maximum in zip(request.aroma_values, _AROMA_LIMITS, strict=True)
            )
        ):
            return
        raise invalid("maxprime_settings")

    def settings_session(self, request: Request) -> Transport:
        """Return the current session that proved support for this settings write."""
        link = self.settings_transport
        feature = {"rgb": "light", "aroma": "aroma"}.get(request.operation)
        if link is None or (feature is not None and feature not in self._receive.menu):
            raise invalid("maxprime_settings")
        return link

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        self.validate_richmat_classic_request(request)
        if request.operation != "query":
            self.settings_session(request)
        if request.operation == "query":
            await self._frames(self._probes, p.QUERY_SPACING_MS)
        elif request.operation == "rgb" and request.color is not None:
            await self.set_light_color(request.color)
        elif request.operation == "aroma" and request.aroma_values is not None:
            await self._frames(
                tuple(
                    p.aroma(0x1B + index, value) for index, value in enumerate(request.aroma_values)
                ),
                p.SETTINGS_SPACING_MS,
            )
