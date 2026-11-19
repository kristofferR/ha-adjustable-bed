"""SleepFunction's resource controls over the shared Richmat gesture runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_PRESET_SAVE, CARD_PRESETS, CARD_UTILITY, CardRole, CardSection
from ...command_scheduler import (
    CommandKind,
    Delivery,
    command_frames_counted,
    command_frames_not_counted,
    current_command_context,
    delivered,
    note_frame_skipped,
)
from ...controller_state import StateKey, StateUpdate
from ...errors import failed, invalid
from ...profiles.richmat_resource_apps import AppProfile
from ...profiles.sleepfunction import (
    ALARM_ACTIONS,
    ALARM_COMBINATIONS,
    EXCLUDED_LAYOUTS,
    EXCLUDED_MEDIA_RESOURCES,
    MASSAGE_CODES,
    PICKER_LAYOUTS,
)
from ...state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..cancellation import cancellable, settled
from ..catalog_buttons import catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
)
from ..richmat.labels import resource_label
from . import resource_controller as resource_runtime
from .caller import Selection, selected_operand
from .controller import RichmatClassicController
from .profiles import Control
from .protocol import (
    ALARM_QUERY,
    AROMA_QUERY,
    INITIALIZE,
    LAMP_QUERY,
    RELEASE,
    STARTUP_MS,
    control,
    direct,
    massage_popup,
    massage_timer,
    release,
    rgb,
    worker_interval,
)
from .protocol import (
    alarm as alarm_frames,
)
from .receive import MalformedFrame, ReceiveState
from .resource_controller import ResourceBedController
from .resource_receive import ResourceReceiveState
from .sleepfunction_settings import Settings
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

LIGHT_ON: Final = UNDER_BED_LIGHTS_ON
TIMER_CHOICE: Final = StateKey[str | None]("sleepfunction_timer_choice")
SETTINGS_REPLY_TIMEOUT: Final = 2.0


class SleepFunctionReceive(ResourceReceiveState):
    """The ordered checksum parser, bounded and isolated to one BLE session."""

    def feed(
        self,
        data: bytes,
        *,
        app: str,
        layout: str,
        desk_bound: bool = False,
        table_controls_bound: bool = False,
    ) -> None:
        self.value_event = None
        if len(self.buffer) + len(data) * 2 > 512:
            self.buffer = ""
            return
        try:
            ReceiveState.feed(
                self, data, app=app, layout=layout, desk_bound=False, table_controls_bound=False
            )
        except MalformedFrame:
            self.buffer = ""
            return
        if self.value_event == "6e0e00037f":
            self.light_on_seen = True
        elif self.value_event == "6e0e00017d":
            self.light_off_seen = True


def _value_key(name: str) -> StateKey[int | None]:
    return StateKey[int | None]("sleepfunction_" + name)


class SleepFunctionController(ResourceBedController):
    """One app/layout, with commands fenced to its admitted native owner/session."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str | None = None,
        device_name: str | None = None,
    ) -> None:
        if (app or coordinator.entry.data.get("protocol_variant")) != "sleepfunction":
            raise invalid("sleepfunction_control")
        if (
            str(coordinator.entry.data.get("product_type", "")).strip().upper()
            in EXCLUDED_LAYOUTS | PICKER_LAYOUTS
        ):
            raise invalid("sleepfunction_layout")
        RichmatClassicController.__init__(self, coordinator, app=app, device_name=device_name)
        self.app_profile = AppProfile(
            "SleepFunction Bed Control",
            poll_ms=150,
            raw_6brm_poll_ms=170,
            held_release_ms=50,
            tap_release_ms=150,
            long_press_ms=3000,
        )
        self._native_route = (
            coordinator.entry.data.get("bed_type"),
            coordinator.entry.data.get("address"),
        )
        self._receive: SleepFunctionReceive = SleepFunctionReceive()
        self._preferences = {}
        self._deadline = None
        self._lamp_timeout = self._massage_timer = None
        self._values: dict[str, int | None] = {}
        self._light_on: bool | None = None
        self._hold_keys: dict[str, tuple[int, int, Selection]] = {}
        self._gesture_active = self._gesture_released = False
        self._aroma_ready = asyncio.Event()

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {**super().persisted_app_state, "hold": self._selection.hold}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        hold = state.get("hold")
        if hold is not None and type(hold) is not bool:
            raise ValueError("Invalid saved continuous movement selection")
        super().restore_persisted_app_state(state)
        self._selection = replace(self._selection, hold=hold)

    @contextmanager
    def sent_state(self, *updates: StateUpdate):
        session = self._captured_session()

        def show(delivery: Delivery) -> None:
            if session is None or not self._owned(session):
                return
            if delivery is Delivery.SENT:
                for update in updates:
                    if update.key == LIGHT_ON and (
                        isinstance(update.value, bool) or update.value is None
                    ):
                        self._light_on = update.value
                self.forward_controller_state_updates(*updates)
            elif delivery is Delivery.PARTIAL:
                if any(u.key == LIGHT_ON for u in updates):
                    self._light_on = None
                self.forward_controller_state_updates(*(StateUpdate(u.key, None) for u in updates))

        with delivered(show):
            yield

    def _owned(self, session: Transport) -> bool:
        return (
            self._coordinator.controller is self
            and (
                self._coordinator.entry.data.get("bed_type"),
                self._coordinator.entry.data.get("address"),
            )
            == self._native_route
            and self._session is session
            and self.client is session.client
            and session.client.is_connected
            and self._coordinator.entry.data.get("protocol_variant") == self.app
            and str(self._coordinator.entry.data.get("product_type", "")).upper() == self.layout
        )

    async def _send(self, packet: bytes, cancel: asyncio.Event | None = None) -> None:
        session = self._captured_session()
        if session is None or not self._owned(session):
            raise failed("sleepfunction_session")
        if cancel is not None and cancel.is_set():
            note_frame_skipped()
            return
        await super()._send(packet, cancel)

    def _notification(
        self, session: Transport, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if not self._owned(session):
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        self._receive.feed(bytes(data), app=self.app, layout=self.layout)
        if self._receive.aroma_capable:
            self._aroma_ready.set()
        if self._receive.value_event in ("6e0e00037f", "6e0e00017d"):
            self._light_on = self._receive.value_event == "6e0e00037f"
        self._publish()

    def _owns_state(self) -> bool:
        owner = self._coordinator.controller
        return (
            (owner is None or owner is self)
            and (
                self._coordinator.entry.data.get("bed_type"),
                self._coordinator.entry.data.get("address"),
            )
            == self._native_route
            and self._coordinator.entry.data.get("protocol_variant") == self.app
            and str(self._coordinator.entry.data.get("product_type", "")).upper() == self.layout
        )

    def _publish(self) -> None:
        if not self._owns_state():
            return
        super()._publish()
        self.forward_controller_state_updates(LIGHT_ON(self._light_on))
        self.forward_controller_state_updates(*(_value_key(k)(v) for k, v in self._values.items()))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise failed("sleepfunction_session")
        try:
            session = select(
                client,
                third_service=self._coordinator.entry.data.get(
                    "richmat_classic_third_service", False
                ),
            )
            self._worker.cancel()
            self._worker.set_interval(
                worker_interval(
                    self._device_name
                    if self._device_name is not None
                    else self._coordinator.entry.data.get("ble_device_name"),
                    session.wire,
                    rise=True,
                )
            )
        except ValueError as error:
            raise failed("sleepfunction_session") from error
        self._session, self._wire = session, session.wire
        self._receive = SleepFunctionReceive()
        self._aroma_ready = asyncio.Event()
        self._notifications_started = False
        try:
            with self._transaction(), command_frames_not_counted():
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
                if session.wire == "FRAMED" and self._notifications_started:
                    await asyncio.sleep(STARTUP_MS / 1000)
                    await self._send(INITIALIZE)
                # HA queries the optional settings on connection, in place of
                # Android's Settings navigation. They are never authentication.
                frames = ([ALARM_QUERY] if self._alarm_actions() else []) + [
                    LAMP_QUERY,
                    AROMA_QUERY,
                ]
                for index, frame in enumerate(frames):
                    await self._send(frame)
                    if index + 1 < len(frames):
                        await asyncio.sleep(0.5)
        except BaseException:
            if self._session is session:
                self._session = None
            raise
        self._publish()

    def on_disconnect(self) -> None:
        self._aroma_ready.set()
        self._receive = SleepFunctionReceive()
        if self._owns_state():
            self.forward_controller_state_updates(
                *(_value_key(k)(None) for k in self._values),
                TIMER_CHOICE(None),
                UNDER_BED_LIGHTS_RGB(None),
            )
        self._values.clear()
        self._light_on = None
        super().on_disconnect()
        self._receive = SleepFunctionReceive()

    async def _iteration(self, cancel: asyncio.Event, mode: int) -> bool:
        session = self._captured_session()
        if session is None:
            raise failed("sleepfunction_session")
        if (
            self._worker.mode == 1
            and self._deadline is not None
            and resource_runtime.monotonic() >= self._deadline
        ):
            self._worker.mode = 0
        for emission in self._worker.tick():
            if emission.delay_ms and not await self._wait(emission.delay_ms, cancel):
                return False
            if cancel.is_set():
                if emission.payload not in (None, RELEASE):
                    note_frame_skipped()
                return False
            if emission.payload is None:
                continue
            if emission.payload == RELEASE:

                async def end() -> None:
                    await self._send(release(session.wire, mode))
                    self._note_cleanup()

                await settled(end())
            else:
                await self._send(control(emission.payload, session.wire, mode), cancel)
        return True

    def _inverse_pairs(self) -> tuple[tuple[str, Control, Control], ...]:
        pairs = []
        for name, on_name, off_name in (("Continuous movement", "btnHold", "btnRelease"),):
            on = next((c for c in self._controls if c.view_id == on_name), None)
            off = next((c for c in self._controls if c.view_id == off_name), None)
            if on and off:
                pairs.append((name, on, off))
        on = next((c for c in self._controls if c.label.endswith("sync on")), None)
        off = next((c for c in self._controls if c.label.endswith("sync off")), None)
        if on and off:
            pairs.append(("Synchronized movement", on, off))
        on = next((c for c in self._controls if resource_label(c.label) == "Massage on"), None)
        off = next(
            (
                c
                for c in self._controls
                if resource_label(c.label) in ("Massage off", "Massage off 3")
            ),
            None,
        )
        if on and off and self._usable(on) and self._usable(off):
            pairs.append(("Massage", on, off))
        return tuple(pairs)

    def _inverse_nodes(self) -> frozenset[int]:
        return frozenset(c.node for _, on, off in self._inverse_pairs() for c in (on, off))

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        specs = []
        for name, on, off in self._inverse_pairs():

            async def switch(c: BedController, enabled: bool, *, yes=on, no=off) -> None:
                if not isinstance(c, SleepFunctionController) or c.layout != self.layout:
                    raise invalid("sleepfunction_control")
                button = yes if enabled else no
                await c.execute_action(button.node, long=button.short is None)

            specs.append(
                ControllerSwitchSpec(
                    f"sleepfunction_{on.node}_{off.node}",
                    "sleepfunction_switch",
                    switch,
                    assumed_state=True,
                    translation_placeholders={"action": name},
                )
            )
        return tuple(specs)

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        session = self._captured_session()
        if session is None or self._gesture_active and self._gesture_released:
            return
        target = self._mode if mode is None else mode

        async def cleanup() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if self._owned(session):
                await self._send(release(session.wire, target))
                self._note_cleanup()
            else:
                context = current_command_context()
                if context is not None and context.kind is CommandKind.STOP:
                    note_frame_skipped()

        await settled(cleanup())

    def _note_cleanup(self) -> None:
        if self._gesture_active:
            self._gesture_released = True
        context = current_command_context()
        if context is not None and context.kind is not CommandKind.STOP:
            context.cleanup_stop_sent = True

    async def stop_all(self) -> None:
        self._worker.cancel()
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        session = self._captured_session()
        if session is None:
            return
        context = current_command_context()

        async def cleanup() -> None:
            with (
                command_frames_counted()
                if context is not None and context.kind is CommandKind.STOP
                else nullcontext()
            ):
                # A native global STOP releases every exposed target. Raw P1
                # has no mode operand, so it needs only one END.
                error: Exception | None = None
                for mode in (0,) if session.wire == "RAW" else self._model.modes:
                    if not self._owned(session):
                        if context is not None and context.kind is CommandKind.STOP:
                            note_frame_skipped()
                        break
                    try:
                        await self._release(self.app_profile.held_release_ms, mode=mode)
                    except Exception as failure:
                        error = error or failure
                if error is not None:
                    raise error

        with self._transaction():
            await settled(cleanup())

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    @staticmethod
    def _hidden(button: Control) -> bool:
        return button.visibility in (
            "gone",
            "invisible",
            "4",
            "8",
        ) or RichmatClassicController._hidden(button)

    def _usable(self, button: Control, long: bool = False) -> bool:
        if button.hold_affected:
            if button.view_id.endswith("Long") and self._selection.hold is not True:
                return False
            if long and self._selection.hold is True:
                return False
        elif self._hidden(button):
            return False
        if button.status not in (1, 2, 3) or not button.rich_button:
            return False
        if (self.layout, button.node) in (("FRRM", 11), ("F4RM", 4)):
            return False
        # Audio is outside the native bed feature boundary. These exact
        # resources remain in diagnostics, never reinterpreted by opcode.
        resource = button.resource_keys.get("press_long" if long else "press_short")
        if resource in EXCLUDED_MEDIA_RESOURCES:
            return False
        if long:
            return button.status == 3 and button.long is not None
        wire = self._session.wire if self._session else self._wire
        return any(
            isinstance(
                selected_operand(button, w, 1 if button.status == 1 else 2, self._selection), bytes
            )
            for w in ((wire,) if wire else ("RAW", "FRAMED"))
        )

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        button = self._button(node)
        if not self._usable(button, long):
            raise invalid("sleepfunction_control")
        with self._transaction():
            # btnRelease/btnHold also change the source's subsequent gestures.
            desired = (
                False
                if button.view_id == "btnRelease"
                else True
                if button.view_id == "btnHold"
                else None
            )

            def show(delivery: Delivery) -> None:
                if desired is not None and delivery is Delivery.SENT:
                    self._selection = replace(self._selection, hold=desired)
                    self._publish()

            self._gesture_active, self._gesture_released = True, False
            try:
                with delivered(show):
                    await super().execute_action(node, long=long, hold_ms=hold_ms)
            finally:
                self._gesture_active = self._gesture_released = False

    async def _scoped_action(
        self,
        node: int,
        mode: int,
        selection: Selection,
        *,
        long: bool = False,
        hold_ms: int | None = None,
        expected_wire: str | None = None,
    ) -> None:
        if self._session and len(self._model.modes) > 1 and self._session.wire != expected_wire:
            raise invalid("sleepfunction_control")
        prior_mode, prior_selection = self._mode, self._selection
        self._mode, self._selection = (
            mode,
            replace(
                selection, hold=self._selection.hold, armed=long and self._button(node).mem_special
            ),
        )
        try:
            await self.execute_action(node, long=long, hold_ms=hold_ms)
        finally:
            self._mode, self._selection = (
                prior_mode,
                replace(prior_selection, hold=self._selection.hold),
            )

    def _label(self, button: Control) -> str:
        label = resource_label(button.label)
        if button.tag == "63":
            labels = {
                "37": "Increase head massage",
                "31": "Head up",
                "35": "Head massage off",
                "32": "Head down",
                "38": "Decrease head massage",
            }
            return labels.get(button.short_old or "", label)
        return (
            label.replace("Motor 1+2", "Head and foot")
            .replace("Motor 1 ", "Head ")
            .replace("Motor 2 ", "Foot ")
        )

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec | None] = []
        self._hold_keys = {}
        for button in self._controls:
            if (
                button.view_id in ("btnRelease", "btnHold")
                or button.node in self._inverse_nodes()
                or self._receive.light_capable
                and len(self._model.modes) == 1
                and not self._usable(button, True)
                and button in (self._light_control(), self._light_control(off=True))
            ):
                continue
            if button.label.lower().endswith("rbstart"):
                continue
            if not self._usable(button) and not self._usable(button, True):
                continue
            if button.tag and button.tag.lower() in (
                "b8tt",
                "b9tt",
                "zri0",
                "i4rm",
                "i5rm",
                "d7rm",
                "zr00",
                "zr01",
                "aprm",
                "aqrm",
            ):
                continue  # These layouts are selectable in Reconfigure.
            for mode in (0,) if self._wire == "RAW" else self._model.modes:
                label = self._label(button)
                # Native controls carry their mode; no app-screen side picker.
                suffix = (
                    ""
                    if self._wire == "RAW"
                    else f" {('Left', 'Right', 'Both')[mode]}"
                    if len(self._model.modes) > 1
                    and self.layout not in ("BTRM", "BURM", "BVRM", "BWRM", "DRRM", "EKRM")
                    else f" mode {mode + 1}"
                    if len(self._model.modes) > 1
                    else ""
                )
                choices = ("53", "54", "55") if button.tag in ("51", "52") else ("53",)
                for flag in choices:
                    selection = Selection(press_flag=flag, head=True, hold=self._selection.hold)
                    name = label + suffix
                    if button.tag in ("51", "52"):
                        name = (
                            {"53": "Motor 3", "54": "Motor 4", "55": "Motor 5"}[flag]
                            + (" up" if button.tag == "51" else " down")
                            + suffix
                        )
                    key = f"sleepfunction_{button.node}_{mode}_{flag}" + (
                        "_raw" if self._wire == "RAW" and len(self._model.modes) > 1 else ""
                    )
                    expected_wire = self._wire or "FRAMED"

                    async def press(
                        c: BedController, *, n=button.node, m=mode, s=selection, wire=expected_wire
                    ) -> None:
                        if not isinstance(c, SleepFunctionController) or c.layout != self.layout:
                            raise invalid("sleepfunction_control")
                        await c._scoped_action(n, m, s, expected_wire=wire)

                    if self._usable(button):
                        spec = catalog_button(
                            key, name if button.tag in ("51", "52") else label, press
                        )
                        if spec is not None and suffix:
                            spec = replace(
                                spec,
                                name=name,
                                translation_key="sleepfunction_scoped_" + str(spec.translation_key),
                                translation_placeholders={"action": name},
                                card=(
                                    CARD_PRESET_SAVE
                                    if spec.card.role is CardRole.SAVE
                                    else CARD_PRESETS
                                    if spec.card.section
                                    in (CardSection.MEMORY, CardSection.PRESETS)
                                    else CARD_UTILITY
                                    if spec.card.section is CardSection.MOTORS
                                    else spec.card
                                ),
                                requires_confirmation=spec.requires_confirmation
                                or spec.card.role is CardRole.SAVE,
                            )
                        if (
                            spec is not None
                            and self._keeps(button, selection)
                            and not spec.requires_confirmation
                        ):
                            from ..entity_specs import ControllerHoldSpec

                            self._hold_keys[key] = (button.node, mode, selection)
                            spec = replace(
                                spec,
                                hold=ControllerHoldSpec(
                                    key, release_button_key="richmat_classic_release"
                                ),
                            )
                        result.append(spec)
                    if self._usable(button, True):

                        async def save(
                            c: BedController,
                            *,
                            n=button.node,
                            m=mode,
                            s=selection,
                            wire=expected_wire,
                        ) -> None:
                            if (
                                not isinstance(c, SleepFunctionController)
                                or c.layout != self.layout
                            ):
                                raise invalid("sleepfunction_control")
                            await c._scoped_action(n, m, s, long=True, expected_wire=wire)

                        save_spec = catalog_button(
                            key + "_long",
                            resource_label(
                                button.resource_keys.get("press_long", button.label)
                                .removeprefix("@string/")
                                .replace("_", " ")
                            )
                            + suffix,
                            save,
                            requires_confirmation=True,
                        )
                        if (
                            save_spec is not None
                            and suffix
                            and save_spec.card.role is CardRole.SAVE
                        ):
                            save_spec = replace(save_spec, card=CARD_PRESET_SAVE)
                        result.append(save_spec)
        result.append(
            ControllerButtonSpec(
                "richmat_classic_release",
                "Release",
                lambda c: c.stop_all(),
                translation_key="richmat_classic_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return tuple(
            replace(s, hold=None, requires_confirmation=s.card.section is CardSection.PRESETS)
            if s.card.role is CardRole.SAVE
            else s
            for s in unique_buttons(result)
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.layout not in ("D1RM", "D9RM") and not any(c.tag == "65" for c in self._controls):
            return ()

        async def timer(c: BedController, value: str) -> None:
            if not isinstance(c, SleepFunctionController) or c.layout != self.layout:
                raise invalid("sleepfunction_control")
            if self.layout in ("D1RM", "D9RM"):
                with c.sent_state(TIMER_CHOICE(value)):
                    await c._setting(
                        "massage_timer",
                        {"off": 0, "ten_minutes": 2, "twenty_minutes": 3, "thirty_minutes": 5}[
                            value
                        ],
                    )
            else:
                with c._transaction(), c.sent_state(TIMER_CHOICE(value)):
                    await c.write_command(
                        massage_popup(
                            {
                                "off": "toggle",
                                "fifteen_minutes": "15",
                                "thirty_minutes": "30",
                                "forty_five_minutes": "45",
                            }[value]
                        )
                    )

        options = (
            ("off", "ten_minutes", "twenty_minutes", "thirty_minutes")
            if self.layout in ("D1RM", "D9RM")
            else ("off", "fifteen_minutes", "thirty_minutes", "forty_five_minutes")
        )
        return (
            ControllerSelectSpec(
                "sleepfunction_massage_timer",
                "sleepfunction_massage_timer",
                TIMER_CHOICE,
                options,
                timer,
            ),
        )

    def controller_button_available(self, key: str) -> bool:
        return key == "richmat_classic_release" or any(
            s.key == key for s in self.controller_button_specs
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(s.hold.control for s in self.controller_button_specs if s.hold)

    @property
    def execution(self):
        from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

        held = frozenset(self.held_control_options)
        return (
            ExecutionCapabilities(hold="stream", hold_controls=held)
            if held
            else NO_EXECUTION_CAPABILITIES
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60000:
            raise invalid("sleepfunction_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        node, mode, selection = self._hold_keys[control]
        await self._scoped_action(
            node, mode, selection, hold_ms=duration_ms, expected_wire=self._wire or "FRAMED"
        )

    def _light_control(self, *, off: bool = False) -> Control | None:
        ending = "ubl off" if off else "ubl on off"
        return next(
            (c for c in self._controls if c.label.endswith(ending) and self._usable(c)), None
        )

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._light_control() is not None

    @property
    def supports_light_state_feedback(self) -> bool:
        return self._receive.light_capable and self._light_control(off=True) is not None

    async def lights_toggle(self) -> None:
        button = self._light_control()
        if button is None:
            raise invalid("sleepfunction_control")
        with self.sent_state(LIGHT_ON(None if self._light_on is None else not self._light_on)):
            await self.execute_action(button.node)

    async def lights_off(self) -> None:
        button = self._light_control(off=True)
        if button is not None:
            with self.sent_state(LIGHT_ON(False)):
                await self.execute_action(button.node)
        elif self._receive.light_capable:
            # Keep the selected on-color so the next explicit turn-on can reuse it.
            with self._transaction(), self.sent_state(LIGHT_ON(False)):
                await self.write_command(rgb(0, 0, 0))
                await self._wait(150, self._coordinator.cancel_command)
        else:
            raise invalid("sleepfunction_control")

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._receive.light_capable

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self._receive.light_capable

    @property
    def supports_light_color_control(self) -> bool:
        return self._receive.light_capable

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        red, green, blue = rgb_color
        if not self._receive.light_capable or any(
            type(v) is not int or not 0 <= v <= 255 for v in (red, green, blue)
        ):
            raise invalid("sleepfunction_control")
        with (
            self._transaction(),
            self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color), LIGHT_ON(any(rgb_color))),
        ):
            await self.write_command(rgb(red, green, blue))
            await self._wait(150, self._coordinator.cancel_command)

    def _alarm_actions(self) -> dict[str, int]:
        available = {int(c.alarm_clock, 16) for c in self._controls if c.alarm_clock}
        return {name: code for name, code in ALARM_ACTIONS.items() if code in available}

    def _alarm_massage(self) -> dict[str, int]:
        controls = [
            int(c.alarm_clock, 16)
            for c in self._controls
            if c.alarm_clock and int(c.alarm_clock, 16) in MASSAGE_CODES
        ]
        zones = {name: code for name, code in (("head", 0x4C), ("feet", 0x4E)) if code in controls}
        if 0x5D in controls or len(controls) >= 2:
            zones = {"both": 0x5D, **zones}
        return zones

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        actions = tuple(self._alarm_actions())
        if not actions:
            return None
        return AlarmCapability(
            wake_actions=actions,
            sounds=("none", "alarm"),
            massage=bool(self._alarm_massage()),
            massage_zones=tuple(self._alarm_massage()),
            requires_wake_action=False,
            live_check=True,
        )

    def validate_request(self, request, *, live: bool = True) -> None:
        raise invalid("sleepfunction_control")

    def validate_richmat_classic_request(self, request) -> None:
        raise invalid("sleepfunction_control")

    def _alarm_code(self, request: AlarmRequest) -> int:
        code = self._alarm_actions().get(request.wake_action)
        if request.enabled and code is None and request.sound != "alarm":
            raise invalid("sleepfunction_control")
        if request.enabled and request.sound == "alarm":
            code = 0x80
        elif request.enabled and request.massage:
            zone_code = self._alarm_massage().get(request.massage_zone or "both")
            if zone_code is None:
                raise invalid("sleepfunction_control")
            if code in MASSAGE_CODES:
                code = zone_code
            elif code in ALARM_COMBINATIONS:
                code = ALARM_COMBINATIONS[code][MASSAGE_CODES.index(zone_code)]
            else:
                raise invalid("sleepfunction_control")
        return code or 0

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        try:
            alarm_frames(alarm.minutes_until() if alarm.enabled else 0, self._alarm_code(alarm))
        except ValueError as error:
            raise invalid("sleepfunction_control") from error

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)

    async def _write_settings(self, frames: tuple[bytes, ...], delay_ms: int) -> None:
        remaining = len(frames)
        cancel = self._coordinator.cancel_command
        with self._transaction():
            try:
                for packet in frames:
                    if cancel.is_set():
                        note_frame_skipped()
                        return

                    async def send(frame: bytes = packet) -> None:
                        nonlocal remaining
                        await self.write_command(frame)
                        remaining -= 1

                    # Record the completed frame before propagating task cancellation.
                    await settled(send())
                    if not await self._wait(delay_ms, cancel):
                        if remaining:
                            note_frame_skipped()
                        return
            except asyncio.CancelledError:
                if remaining:
                    note_frame_skipped()
                raise

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        code = self._alarm_code(alarm)
        frames = alarm_frames(alarm.minutes_until(dt_util.now()) if alarm.enabled else 0, code)
        await self._write_settings(frames, 300)

    def validate_settings(self, request: Settings) -> None:
        request.frames()
        if request.operation == "aroma" and not self._receive.aroma_capable:
            raise invalid("sleepfunction_control")

    async def check_settings(self, request: Settings) -> Transport:
        request.frames()
        with self._transaction() as session:
            if request.operation == "aroma" and not self._receive.aroma_capable:
                ready = self._aroma_ready

                async def wait_ready() -> None:
                    await asyncio.wait_for(ready.wait(), SETTINGS_REPLY_TIMEOUT)

                try:
                    await cancellable(wait_ready(), self._coordinator.cancel_command)
                except TimeoutError as error:
                    raise invalid("sleepfunction_control") from error
            if not self._owned(session):
                raise failed("sleepfunction_session")
            self.validate_settings(request)
            return session

    async def execute_settings(
        self, request: Settings, *, checked_session: Transport | None = None
    ) -> None:
        if checked_session is not None and not self._owned(checked_session):
            raise failed("sleepfunction_session")
        self.validate_settings(request)
        await self._write_settings(request.frames(), 150 if request.operation == "aroma" else 300)

    async def _setting(self, key: str, value: int) -> None:
        if key == "lamp_timeout":
            if not self._receive.light_capable or not 0 <= value <= 300:
                raise invalid("sleepfunction_control")
            frames = (direct(0x0B, value >> 8, value & 255),)
        elif key == "massage_timer":
            frames = (massage_timer(self.layout, value),)
        else:
            raise invalid("sleepfunction_control")
        with self._transaction():
            for packet in frames:

                def remember(delivery: Delivery) -> None:
                    session = self._captured_session()
                    if session is not None and self._owned(session):
                        if delivery is Delivery.SENT:
                            self._values[key] = value
                        elif delivery is Delivery.PARTIAL:
                            self._values[key] = None

                with delivered(remember), self.sent_state(_value_key(key)(value)):
                    await self.write_command(packet)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        rows = []
        if self._receive.light_capable:
            rows.append(("lamp_timeout", 0, 300, "s"))
        result = []
        for name, minimum, maximum, unit in rows:

            async def change(c: BedController, value: float, *, key=name) -> None:
                if (
                    not isinstance(c, SleepFunctionController)
                    or c.layout != self.layout
                    or not float(value).is_integer()
                ):
                    raise invalid("sleepfunction_control")
                await c._setting(key, int(value))

            result.append(
                ControllerNumberSpec(
                    "sleepfunction_" + name,
                    "sleepfunction_" + name,
                    _value_key(name),
                    minimum,
                    maximum,
                    1,
                    change,
                    unit,
                )
            )
        return tuple(result)
