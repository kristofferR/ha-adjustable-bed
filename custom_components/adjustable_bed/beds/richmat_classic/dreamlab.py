"""Dreamlab Control sessions, selectors and direct bed settings."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import partial
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_LIGHTING
from ...command_scheduler import current_command_context, note_frame_skipped
from ...const import (
    CONF_BLE_DEVICE_NAME,
    CONF_MOTOR_PULSE_COUNT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles import dreamlab
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, require_controller
from ..catalog_buttons import Kind, catalog_button, classify, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy
from . import protocol as p
from .caller import Selection, nordic_label, short_operand
from .controller import APP, LAYOUT, PREFERENCES, REJECTION, STATE, STATUS
from .dreamlab_controls import Gesture, action_name, gesture
from .profiles import Control, load_catalog
from .receive import MalformedFrame, ReceiveState
from .requests import Request
from .session import SessionController
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MODE: Final = StateKey[str | None]("dreamlab_mode")
HEAD_FOOT: Final = StateKey[str | None]("dreamlab_head_foot")
PRESS_MODE: Final = StateKey[str | None]("dreamlab_press_mode")
AXIS: Final = StateKey[str | None]("dreamlab_axis")
LIGHT_SECONDS: Final = StateKey[int | None]("dreamlab_light_seconds")
RELEASE_KEY: Final = "dreamlab_release"
_PAIRED_SIDES: Final = (SIDE_LEFT, SIDE_RIGHT)


async def _press(controller: BedController, node: int, *, long: bool, raw: bool) -> None:
    ctrl = require_controller(controller, DreamlabController)
    if not long and raw != (
        ctrl._resolved_wire == "RAW" and nordic_label(ctrl._button(node)) is not None
    ):
        raise invalid("dreamlab_control")
    await ctrl.execute_action(node, long=long)


class DreamlabController(SessionController):
    """Capture one command, one physical session and one bank through END."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str,
        device_name: str | None = None,
        capability_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(coordinator, app=app, device_name=device_name)
        if self.layout not in dreamlab.LAYOUTS:
            raise invalid("dreamlab_layout")
        self._preferences = {}
        snapshot = capability_snapshot or {}
        self._known_light = snapshot.get("layout") == self.layout and snapshot.get("light") is True
        self._light_on: bool | None = None

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True, after_operations=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {"layout": self.layout, "light": self._known_light}

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {
            "wire": self._wire,
            "mode": self._mode,
            "head": self._selection.head,
            "press_flag": self._selection.press_flag,
            "hold": self._selection.hold,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)
        mode = state.get("mode")
        self._mode = mode if type(mode) is int and mode in self._model.modes else 0
        head = state.get("head")
        flag = state.get("press_flag")
        hold = state.get("hold")
        self._selection = Selection(
            head=head if isinstance(head, bool) else True,
            press_flag=flag if isinstance(flag, str) and flag in ("53", "54", "55") else "53",
            hold=hold if isinstance(hold, bool) else None,
        )

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.layout in dreamlab.SIDE_LAYOUTS and self._resolved_wire == "FRAMED"

    def _target(self, wire: p.Wire) -> int:
        if self.command_side in _PAIRED_SIDES:
            if self.layout not in dreamlab.SIDE_LAYOUTS or wire == "RAW":
                raise invalid("dreamlab_side")
            return int(self.command_side == SIDE_RIGHT)
        return self._mode if wire == "FRAMED" else 0

    def _publish(self) -> None:
        state: dict[str, object] = {
            "alarm_available": self._receive.alarm_capable,
            "light_available": self._receive.light_capable,
            "aroma_available": self._receive.aroma_capable,
            "alarm_acknowledged": self._receive.alarm_enabled,
            "last_notification": self._receive.last_value,
        }
        mode = _mode_value(self.layout, self._mode)
        hold = self._selection.hold
        self.forward_controller_state_updates(
            STATUS("ready" if self._session else "disconnected"),
            APP(self.app),
            LAYOUT(self.layout),
            STATE(state),
            PREFERENCES({}),
            REJECTION(self._rejection),
            MODE(mode if self._resolved_wire == "FRAMED" else None),
            HEAD_FOOT("head" if self._selection.head else "foot"),
            PRESS_MODE(None if hold is None else "hold" if hold else "release"),
            AXIS(_axis_value(self._selection)),
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
        try:
            self._receive.feed(
                bytes(data),
                app=self.app,
                layout=self.layout,
                desk_bound=False,
                table_controls_bound=False,
            )
            self._rejection = None
        except MalformedFrame:
            # Recover the next frame boundary without carrying a broken substring.
            self._receive.buffer = "6e" if data.endswith(b"\x6e") else ""
            self._rejection = "Malformed notification"
        if self._receive.value_event in ("6e0e00017d", "6e0e00037f"):
            self._light_on = self._receive.value_event == "6e0e00037f"
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(self._light_on))
        self._known_light |= self._receive.light_capable
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        try:
            session = select(
                client,
                third_service=bool(
                    self._coordinator.entry.data.get(CONF_RICHMAT_CLASSIC_THIRD_SERVICE)
                ),
            )
        except ValueError as err:
            raise BedNotConnectedError("dreamlab_transport") from err
        name = self._device_name or self._coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
        self._worker.set_interval(
            dreamlab.poll_interval(
                name if isinstance(name, str) else None, raw=session.wire == "RAW"
            )
        )
        self._session, self._wire = session, session.wire
        self._receive = ReceiveState()
        self._light_on = None
        self._notifications_started = False
        self._rejection = None
        try:
            with self._transaction():
                if session.has_notifications:
                    try:
                        result = await client.start_notify(
                            session.notify, partial(self._notification, session)
                        )
                        self._notifications_started = result is not False
                    except BleakError:
                        self._rejection = "Notification registration failed"
                if self._notifications_started:
                    if session.wire == "FRAMED":
                        await asyncio.sleep(p.STARTUP_MS / 1000)
                        await self._send(p.INITIALIZE)
                    await self._probe()
        except BaseException:
            self._session = None
            self._notifications_started = False
            raise
        self._publish()

    def on_disconnect(self) -> None:
        self._receive = ReceiveState()
        self._light_on = None
        self.forward_controller_state_updates(
            LIGHT_SECONDS(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_RGB(None),
        )
        super().on_disconnect()

    async def _probe(self, *, counted: bool = False) -> None:
        frames = (
            (p.ALARM_QUERY, p.LAMP_QUERY, p.AROMA_QUERY)
            if any(button.alarm_clock for button in self._controls)
            else (p.LAMP_QUERY, p.AROMA_QUERY)
        )
        await self._sequence(frames, p.QUERY_SPACING_MS, counted=counted)

    async def _sequence(
        self, frames: tuple[bytes, ...], spacing: int, *, counted: bool = True
    ) -> None:
        cancel = self._coordinator.cancel_command if counted else None
        for index, frame in enumerate(frames):
            if index:
                if cancel is None:
                    await asyncio.sleep(spacing / 1000)
                elif not await self._wait(spacing, cancel):
                    note_frame_skipped()
                    return
            await self._send(frame, cancel)

    def _plan(self, button: Control, wire: p.Wire, *, long: bool) -> Gesture | None:
        return gesture(button, self.layout, wire, self._selection, long=long)

    def _selection_after(self, button: Control) -> None:
        if button.tag in ("53", "54", "55"):
            self._selection = replace(self._selection, press_flag=button.tag)
        if button.view_id in ("btnRelease", "btnHold") and self.layout != "AQRM":
            self._selection = replace(self._selection, hold=button.short == "22")
        self._publish()

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        button = self._button(node)
        cancel = self._coordinator.cancel_command
        with self._transaction() as session:
            plan = self._plan(button, session.wire, long=long)
            if plan is None:
                raise invalid("dreamlab_control")
            target = self._target(session.wire)
            name = action_name(button, long=long, raw=session.wire == "RAW")
            control = classify(name)
            context = current_command_context()
            leased = context is not None and context.lease is not None
            if (hold_ms is not None or leased) and (
                not plan.held or long or control is not None and control.kind is Kind.SAVE
            ):
                raise invalid("control_hold_renewal_not_supported")
            interval = self._worker.tick_ms
            duration = (
                hold_ms
                if hold_ms is not None
                else int(self._coordinator.entry.data.get(CONF_MOTOR_PULSE_COUNT, 10)) * interval
            )
            packet = p.control(plan.payload, session.wire, target)
            try:
                if plan.threshold_ms and not await self._wait(
                    plan.threshold_ms // interval * interval, cancel
                ):
                    note_frame_skipped()
                    return
                deadline = monotonic() + duration / 1000
                while not cancel.is_set():
                    await self._send(packet, cancel)
                    if not plan.held:
                        if not cancel.is_set() and self._session is session:
                            self._selection_after(button)
                        return
                    remaining = ceil((deadline - monotonic()) * 1000)
                    if not leased and remaining <= 0:
                        return
                    if not await self._wait(
                        interval if leased else min(interval, remaining), cancel
                    ):
                        if leased or remaining > interval:
                            note_frame_skipped()
                        return
                    if not leased and monotonic() >= deadline:
                        return
                note_frame_skipped()
            finally:
                if plan.release_ms is not None:
                    await self._release(plan.release_ms, mode=target)

    async def stop_all(self) -> None:
        if not CONTROLLER_GESTURE_RELEASE.get():
            with self._transaction() as session:
                await self._release(p.HELD_RELEASE_MS, mode=self._target(session.wire))

    def _button_spec(
        self, button: Control, *, long: bool, raw: bool
    ) -> ControllerButtonSpec | None:
        selection = self._selection
        if button.hold_affected:
            # Keep registry IDs stable while the selector changes availability.
            selection = replace(selection, hold=button.view_id.endswith("Long") or not long)
        elif button.tag == "63":
            selection = replace(selection, head=True)
        wires: tuple[p.Wire, ...] = ("RAW",) if raw else ("FRAMED", "RAW")
        plans = [
            plan
            for wire in wires
            if (plan := gesture(button, self.layout, wire, selection, long=long)) is not None
        ]
        if not plans:
            return None
        name = action_name(button, long=long, raw=raw)
        shape = classify(name)
        if shape is None:
            name = f"Control {button.node}"
        save = long or shape is not None and shape.kind is Kind.SAVE
        key = f"dreamlab_{button.node}" + ("_raw" if raw else "") + ("_long" if long else "")
        wire = self._resolved_wire
        active = (
            (plan := self._plan(button, wire, long=long)) is not None and plan.held
            if wire is not None
            else any(plan.held for plan in plans) and not button.hold_affected
        )
        hold = (
            ControllerHoldSpec(key, release_button_key=RELEASE_KEY) if active and not save else None
        )
        return catalog_button(
            key,
            name,
            partial(_press, node=button.node, long=long, raw=raw),
            hold=hold,
            requires_confirmation=save,
            enabled=button.tag in ("51", "52") or shape is not None and shape.enabled,
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        light = self._toggle_light() if self.supports_light_state_feedback else None
        for button in self._controls:
            if (
                button is light
                or self._has_press_selector
                and button.view_id in ("btnRelease", "btnHold")
            ):
                continue
            raw = self._resolved_wire == "RAW" and nordic_label(button) is not None
            specs.extend(
                (
                    self._button_spec(button, long=False, raw=raw),
                    self._button_spec(button, long=True, raw=False),
                )
            )
        if self.layout == "Y6RM":
            specs.append(
                catalog_button(
                    "dreamlab_massage_toggle", "Toggle massage", _toggle_massage, kind=Kind.MASSAGE
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
        return unique_buttons(specs)

    def controller_button_available(self, key: str) -> bool:
        if key == RELEASE_KEY or key == "dreamlab_massage_toggle" and self.layout == "Y6RM":
            return True
        prefix, separator, node = key.partition("_")
        number = node.split("_", 1)[0]
        if not separator or prefix != "dreamlab" or not number.isdecimal():
            return False
        button = next((button for button in self._controls if button.node == int(number)), None)
        if button is None:
            return False
        long = key.endswith("_long")
        raw = self._resolved_wire == "RAW" and not long and nordic_label(button) is not None
        if raw != key.endswith("_raw"):
            return False
        wire = self._resolved_wire
        if wire is not None:
            return self._plan(button, wire, long=long) is not None
        return (
            self._plan(button, "FRAMED", long=long) is not None
            or self._plan(button, "RAW", long=long) is not None
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            spec.hold.control
            for spec in self.controller_button_specs
            if spec.hold is not None and self.controller_button_available(spec.key)
        )

    @property
    def execution(self) -> ExecutionCapabilities:
        controls = frozenset(self.held_control_options)
        return (
            ExecutionCapabilities(hold="stream", hold_controls=controls)
            if controls
            else NO_EXECUTION_CAPABILITIES
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60000:
            raise invalid("dreamlab_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.execute_action(int(control.split("_")[1]), hold_ms=duration_ms)

    @property
    def _has_press_selector(self) -> bool:
        return self.layout in ("YFRM", "YGRM", "BRRM", "APRM")

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs = []
        if self._resolved_wire != "RAW" and len(self._model.modes) > 1:
            options = tuple(_mode_value(self.layout, mode) for mode in self._model.modes)
            if self.command_side not in _PAIRED_SIDES:
                specs.append(self._select_spec(MODE, options))
        if self.layout == "GVRM":
            specs.append(self._select_spec(HEAD_FOOT, ("head", "foot")))
        if self.layout == "U3RM":
            specs.append(self._select_spec(AXIS, ("3", "4", "5")))
        if self._has_press_selector:
            specs.append(
                ControllerSelectSpec(
                    PRESS_MODE,
                    PRESS_MODE,
                    PRESS_MODE,
                    ("release", "hold"),
                    _select_press_mode,
                )
            )
        return tuple(specs)

    def _select_spec(
        self, key: StateKey[str | None], options: tuple[str, ...]
    ) -> ControllerSelectSpec:
        def select_local(value: str) -> None:
            if value not in options:
                raise invalid("dreamlab_control")
            if key == MODE:
                self._mode = self._model.modes[options.index(value)]
            elif key == HEAD_FOOT:
                self._selection = replace(self._selection, head=value == "head")
            else:
                self._selection = replace(
                    self._selection, press_flag=("53", "54", "55")[options.index(value)]
                )
            self._publish()

        async def select_option(controller: BedController, value: str) -> None:
            select_local(value)

        return ControllerSelectSpec(
            key, key, key, options, select_option, local_select_fn=select_local
        )

    @property
    def _slider(self) -> bool:
        """D1RM and D9RM have the massage slider instead of the timer popup."""
        return self.layout in ("D1RM", "D9RM")

    @property
    def supports_massage_timer(self) -> bool:
        return (self.layout == "Y6RM" or self._slider) and self.command_side not in _PAIRED_SIDES

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage_timer

    @property
    def massage_timer_options(self) -> list[int]:
        if not self.supports_massage_timer:
            return []
        return [m for m in p.SLIDER_MINUTES if m] if self._slider else [10, 20, 30]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return self._slider and self.supports_massage_timer

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage_timer or minutes not in (0, *self.massage_timer_options):
            raise invalid("dreamlab_control")
        if not self._slider and not minutes:
            raise invalid("dreamlab_control")
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            if self._slider:
                self._require_receiver()
                with self._transaction():
                    await self._send(
                        p.massage_timer(self.layout, p.SLIDER_MINUTES[minutes]),
                        self._coordinator.cancel_command,
                    )
            else:
                await self._massage_popup(minutes)

    async def _massage_popup(self, minutes: int) -> None:
        self._require_receiver()
        with self._transaction():
            await self._send(
                p.control(bytes((dreamlab.MASSAGE_POPUP[minutes],)), "FRAMED"),
                self._coordinator.cancel_command,
            )

    def _require_receiver(self) -> None:
        if self.command_side in _PAIRED_SIDES:
            raise invalid("dreamlab_side")

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.command_side in _PAIRED_SIDES:
            return ()
        result = []
        if self._known_light:
            result.append(
                ControllerNumberSpec(
                    LIGHT_SECONDS,
                    LIGHT_SECONDS,
                    LIGHT_SECONDS,
                    0,
                    300,
                    1,
                    _set_light_seconds,
                    "s",
                    card=CARD_LIGHTING,
                )
            )
        return tuple(result)

    def _alarm_actions(self) -> dict[str, int]:
        allowed = load_catalog(self.app).alarm_allowlist.values()
        return {
            f"node_{button.node}": int(button.alarm_clock, 16)
            for button in self._controls
            if button.alarm_clock is not None and button.alarm_clock in allowed
        }

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if self.command_side in _PAIRED_SIDES:
            return None
        capability = p.alarm_capability(self._alarm_actions())
        if capability is not None and self.layout not in dreamlab.DIRECT_ALARM_LAYOUTS:
            return replace(capability, live_check=True)
        return capability

    def _alarm_code(self, request: AlarmRequest) -> int:
        if not request.enabled:
            return 0
        available = self._alarm_actions()
        try:
            selected = {available[key] for key in p.alarm_choices(available, request)}
            massage_codes = (0x5D, 0x4C, 0x4E)
            bed = selected.difference(massage_codes)
            massage = selected.intersection(massage_codes)
            zone = 0x5D if len(massage) > 1 else next(iter(massage), None)
            if bed:
                preset = next(iter(bed))
                return (
                    preset
                    if zone is None
                    else dreamlab.ALARM_COMBINATIONS[preset][massage_codes.index(zone)]
                )
            if zone is not None:
                return zone
        except (KeyError, ValueError) as err:
            raise invalid("dreamlab_alarm") from err
        raise invalid("dreamlab_alarm")

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self._require_receiver()
        self._alarm_code(alarm)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self._require_receiver()
        if not self._receive.alarm_capable and self.layout not in dreamlab.DIRECT_ALARM_LAYOUTS:
            raise invalid("dreamlab_accessory")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        code = self._alarm_code(alarm)
        minutes = min(1440, alarm.minutes_until(dt_util.now())) if alarm.enabled else 0
        with self._transaction():
            await self._sequence(p.alarm(minutes, code), p.ALARM_SPACING_MS)

    def _toggle_light(self) -> Control | None:
        return next(
            (
                button
                for button in self._controls
                if button.short == "3C"
                and button.status == 2
                and not button.excluded_short
                and short_operand(button, self._resolved_wire or "FRAMED") == "3C"
            ),
            None,
        )

    @property
    def supports_light_state_feedback(self) -> bool:
        return (
            self._known_light
            and self._toggle_light() is not None
            and self.command_side not in _PAIRED_SIDES
        )

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self.supports_light_state_feedback

    @property
    def supports_light_color_control(self) -> bool:
        return self.supports_light_state_feedback

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    async def _set_light_power(self, enabled: bool) -> None:
        self._require_receiver()
        button = self._toggle_light()
        if button is None:
            raise NotImplementedError
        if self._light_on is None:
            raise invalid("dreamlab_accessory")
        if enabled != self._light_on:
            # A second power request needs a fresh state reply, even if the
            # first turn's cleanup was cancelled after its toggle write.
            self._light_on = None
            with self._transaction():
                await self.execute_action(button.node)
                if not self._coordinator.cancel_command.is_set():
                    await self._send(p.LAMP_QUERY)

    async def lights_on(self) -> None:
        await self._set_light_power(True)

    async def lights_off(self) -> None:
        await self._set_light_power(False)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        self._require_receiver()
        if not self._receive.light_capable:
            raise invalid("dreamlab_accessory")
        with self._transaction(), self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color)):
            await self._send(p.rgb(*rgb_color), self._coordinator.cancel_command)
            await self._wait(p.SETTINGS_SPACING_MS, self._coordinator.cancel_command)

    def validate_richmat_classic_request(self, request: Request) -> None:
        self._require_receiver()
        if request.operation == "query" or request.operation == "rgb" and request.color is not None:
            return
        values = request.aroma_values
        if (
            request.operation == "aroma"
            and values is not None
            and len(values) == 3
            and all(
                1 <= value <= maximum for value, maximum in zip(values, (60, 60, 12), strict=True)
            )
        ):
            return
        raise invalid("dreamlab_settings")

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        self.validate_richmat_classic_request(request)
        with self._transaction():
            if request.operation == "query":
                await self._probe(counted=True)
            elif request.operation == "rgb" and request.color is not None:
                await self.set_light_color(request.color)
            elif request.aroma_values is not None:
                if not self._receive.aroma_capable:
                    raise invalid("dreamlab_accessory")
                frames = tuple(
                    p.aroma(op, value)
                    for op, value in zip((0x1B, 0x1C, 0x1D), request.aroma_values, strict=True)
                )
                await self._sequence(frames, p.SETTINGS_SPACING_MS)


def _mode_value(layout: str, mode: int) -> str:
    return _PAIRED_SIDES[mode] if layout in dreamlab.SIDE_LAYOUTS else str(mode)


def _axis_value(selection: Selection) -> str:
    return {"53": "3", "54": "4", "55": "5"}[selection.press_flag]


async def _select_press_mode(controller: BedController, value: str) -> None:
    ctrl = require_controller(controller, DreamlabController)
    if value not in ("release", "hold"):
        raise invalid("dreamlab_control")
    view_id = "btnRelease" if value == "release" else "btnHold"
    button = next((button for button in ctrl._controls if button.view_id == view_id), None)
    if button is None:
        raise invalid("dreamlab_control")
    await ctrl.execute_action(button.node)


async def _toggle_massage(controller: BedController) -> None:
    await require_controller(controller, DreamlabController)._massage_popup(0)


async def _set_light_seconds(controller: BedController, value: float) -> None:
    ctrl = require_controller(controller, DreamlabController)
    ctrl._require_receiver()
    if not ctrl._receive.light_capable:
        raise invalid("dreamlab_accessory")
    seconds = int(value)
    with ctrl._transaction(), ctrl.sent_state(LIGHT_SECONDS(seconds)):
        await ctrl._send(p.direct(0x0B, seconds >> 8, seconds), ctrl._coordinator.cancel_command)
