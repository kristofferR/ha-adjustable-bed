"""TSS Remote's catalog and direct bed settings on captured Richmat sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...alarm import AlarmCapability
from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec.richmat import is_valid
from ...command_scheduler import Delivery, delivered, note_frame_skipped
from ...errors import invalid
from ...profiles import tss_remote as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from ..base import BedController, require_controller
from ..cancellation import cancellable
from ..catalog_buttons import on_off_switch
from ..entity_specs import ControllerButtonSpec, ControllerSelectSpec, ControllerSwitchSpec
from . import protocol as p
from .caller import Selection
from .controller import BEFORE_SETTINGS_WRITE
from .dreamlab import DreamlabController
from .dreamlab_controls import Gesture
from .profiles import Control
from .receive import PREFIXES, MalformedFrame, ReceiveState
from .requests import Request
from .transport import Transport
from .tss_remote_controls import name, plan

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

# HA admission budget for an already-issued startup probe, not a device timer.
LAMP_ADMISSION_TIMEOUT_S = 1.0


@dataclass(frozen=True, slots=True)
class GestureAction:
    """The complete admitted gesture behind one on/off choice."""

    node: int
    long: bool
    gesture: Gesture


class TssReceiveState(ReceiveState):
    """The app's mutable search suffix, with bounded HA callback failures."""

    def _pack(self, length: int) -> str:
        original = self.buffer.lower().strip()
        search = original
        for prefix in PREFIXES:
            offset = 0
            while offset <= len(original):
                found = search.find(prefix)
                if found < 0 or found + length > len(search):
                    break
                search = search[found : found + length]
                if is_valid(bytes.fromhex(search)):
                    return search
                offset += found + 4
                if offset > len(original):
                    raise MalformedFrame("Notification search exceeds its buffer")
                search = original[offset:]
        return ""

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
        self.unit_event = None
        self.events = []
        if len(self.buffer) + len(data) * 2 > 1024:
            self.buffer = ""
            raise MalformedFrame("Notification exceeds the HA receive budget")
        super().feed(data, app=app, layout=layout, desk_bound=False, table_controls_bound=False)
        # These records remain diagnostic data. A companion's presence never
        # creates a bed feature or an accessory control.
        self.aroma_capable = False
        self.menu.discard("aroma")


class TssRemoteController(DreamlabController):
    """App-specific data over the shared resource-catalog session runtime."""

    button_prefix = "tss"
    error_namespace = "tss_remote"

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        device_name: str | None = None,
        capability_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        self._lamp_evidence = asyncio.Event()
        snapshot = capability_snapshot or {}
        super().__init__(
            coordinator,
            app=app.APP,
            device_name=device_name,
            runtime=app.RUNTIME,
            capability_snapshot=snapshot if snapshot.get("app") == app.APP else {},
        )
        self._receive = TssReceiveState()

    def _new_receive(self) -> TssReceiveState:
        self._lamp_evidence.set()
        self._lamp_evidence = asyncio.Event()
        return TssReceiveState()

    def _notification(
        self, session: Transport, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        super()._notification(session, sender, data)
        if self.settings_transport is session and self._receive.value_event in (
            "6e0e00017d",
            "6e0e00037f",
        ):
            self._lamp_evidence.set()

    def capability_snapshot(self) -> dict[str, object]:
        return {**super().capability_snapshot(), "app": app.APP}

    async def _probe(self, *, counted: bool = False) -> None:
        # A new physical session gets a fresh parser. Settings probes are direct
        # frames on both vendor routes; the fragrance query is excluded.
        frames = ((p.ALARM_QUERY,) if self._alarm_actions() else ()) + (p.LAMP_QUERY,)
        await self._sequence(frames, self.runtime.query_spacing_ms, counted=counted)

    def _gesture(
        self, button: Control, wire: p.Wire, selection: Selection, *, long: bool
    ) -> Gesture | None:
        return plan(button, self.layout, wire, selection, long=long)

    def _action_name(self, button: Control, *, long: bool, raw: bool) -> str:
        return name(button, self.layout, long=long, raw=raw)

    def _button_spec(
        self, button: Control, *, long: bool, raw: bool
    ) -> ControllerButtonSpec | None:
        name = self._action_name(button, long=long, raw=raw)
        # Unlabelled physical axes and unknown resource words stay diagnostic.
        if not name:
            return None
        if any(word in name.lower() for word in ("motor ", "control ", "code ")):
            if button.tag not in ("51", "52"):
                return None
        return super()._button_spec(button, long=long, raw=raw)

    def _selection_after(self, button: Control) -> None:
        if button.tag in ("53", "54", "55"):
            self._selection = replace(self._selection, press_flag=button.tag)
        if self.layout in ("YFRM", "YGRM", "BRRM") and button.view_id in ("btnRelease", "btnHold"):
            self._selection = replace(self._selection, hold=button.short == "22")
        self._publish()

    @property
    def _has_press_selector(self) -> bool:
        return self.layout in ("YFRM", "YGRM", "BRRM")

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        # Numbered selected motors have no proven anatomical names. Their local
        # selector remains in diagnostics; never relabel it as a physical axis.
        return tuple(
            spec for spec in super().controller_select_specs if str(spec.key) != "dreamlab_axis"
        )

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return True

    def validate_richmat_classic_request(self, request: Request) -> None:
        self._require_receiver()
        if request.operation == "query":
            return
        if (
            request.operation == "rgb"
            and request.color is not None
            and len(request.color) == 3
            and all(type(value) is int and 0 <= value <= 255 for value in request.color)
        ):
            return
        raise invalid("tss_remote_settings")

    def settings_session(self, request: Request) -> Transport:
        """Check capabilities on the session established by command admission."""
        self.validate_richmat_classic_request(request)
        link = self.settings_transport
        if link is None or request.operation == "rgb" and not self._receive.light_capable:
            raise self._invalid("accessory")
        return link

    async def _prepare_lamp(self) -> Transport:
        self._require_receiver()
        link = self.settings_transport
        if link is None:
            raise self._invalid("accessory")
        if not self._receive.light_capable:
            try:
                async with asyncio.timeout(LAMP_ADMISSION_TIMEOUT_S):
                    await cancellable(self._lamp_evidence.wait(), self._coordinator.cancel_command)
            except TimeoutError as err:
                raise self._invalid("accessory") from err
        if self.settings_transport is not link or not self._receive.light_capable:
            raise self._invalid("accessory")
        return link

    async def async_prepare_settings(self, request: Request) -> Transport:
        self.validate_richmat_classic_request(request)
        if request.operation == "rgb":
            return await self._prepare_lamp()
        return self.settings_session(request)

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        await self.async_prepare_settings(request)
        await super().async_execute_richmat_classic_request(request)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        link = await self.async_prepare_settings(Request("rgb", color=rgb_color))
        batch_check = BEFORE_SETTINGS_WRITE.get()

        def before_write() -> bool:
            if batch_check is not None and not batch_check():
                return False
            if self.settings_transport is not link or not self._receive.light_capable:
                note_frame_skipped()
                raise self._invalid("accessory")
            return True

        token = BEFORE_SETTINGS_WRITE.set(before_write)
        try:
            await super().set_light_color(rgb_color)
        finally:
            BEFORE_SETTINGS_WRITE.reset(token)

    def _toggle_light(self) -> Control | None:
        wire = self._resolved_wire or "FRAMED"
        return next(
            (
                button
                for button in self._controls
                if button.status in (2, 3)
                and (gesture := self._plan(button, wire, long=False)) is not None
                and gesture.payload.hex().upper() == app.LIGHT_TOGGLE
            ),
            None,
        )

    async def _set_light_power(self, enabled: bool) -> None:
        await self._prepare_lamp()
        button = self._toggle_light()
        if button is None or self._light_on is None:
            raise self._invalid("accessory")
        if enabled == self._light_on:
            return
        with self._transaction() as session:
            off = self._plan(button, session.wire, long=True) if not enabled else None
            await self.execute_action(
                button.node, long=off is not None and off.payload.hex().upper() == app.LIGHT_OFF
            )

    async def _send(self, packet: bytes, cancel: asyncio.Event | None = None) -> None:
        session = self._captured_session()
        if session is None or packet not in (
            p.control(bytes.fromhex(opcode), session.wire, self._target(session.wire))
            for opcode in (app.LIGHT_TOGGLE, app.LIGHT_OFF)
        ):
            await super()._send(packet, cancel)
            return

        def show(delivery: Delivery) -> None:
            if delivery is not Delivery.NONE and self.settings_transport is session:
                self._light_on = None
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))

        with delivered(show):
            await super()._send(packet, cancel)

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        with self._transaction() as session:
            gesture = self._plan(self._button(node), session.wire, long=long)
            power = gesture is not None and gesture.payload.hex().upper() in (
                app.LIGHT_TOGGLE,
                app.LIGHT_OFF,
            )
            await super().execute_action(node, long=long, hold_ms=hold_ms)
            if power and not self._coordinator.cancel_command.is_set():
                await self._send(p.LAMP_QUERY, self._coordinator.cancel_command)

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        capability = super().alarm_capability
        if capability is None and self._receive.alarm_capable:
            # The Settings reply can reveal Cancel without a selectable wake
            # checkbox. It proves no new preset or alarm-time readback.
            return AlarmCapability(live_check=True)
        return capability

    @property
    def massage_timer_options(self) -> list[int]:
        if self._slider:
            return [minutes for minutes in app.SLIDER_MINUTES if minutes]
        return super().massage_timer_options

    async def set_massage_timer(self, minutes: int) -> None:
        if not self._slider:
            await super().set_massage_timer(minutes)
            return
        if minutes not in app.SLIDER_MINUTES:
            raise self._invalid("control")
        self._require_receiver()
        with self._transaction(), self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self._send(
                p.massage_timer(self.layout, app.SLIDER_MINUTES[minutes]),
                self._coordinator.cancel_command,
            )

    def _inverse_actions(self) -> dict[str, tuple[GestureAction, GestureAction]]:
        wire = self._resolved_wire or "FRAMED"
        names: dict[str, GestureAction] = {}
        for button in self._controls:
            for long in (False, True):
                gesture = self._plan(button, wire, long=long)
                if gesture is not None:
                    names.setdefault(
                        self._action_name(button, long=long, raw=wire == "RAW"),
                        GestureAction(button.node, long, gesture),
                    )
        return {
            key: (names[on], names[off])
            for key, on, off in (
                ("massage", "Massage on", "Massage off"),
                ("synchronization", "Synchronization on", "Synchronization off"),
            )
            if on in names and off in names
        }

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return tuple(
            on_off_switch(
                "tss_" + key,
                "tss_" + key,
                partial(_switch_press, feature=key, enabled=True),
                partial(_switch_press, feature=key, enabled=False),
                assumed_state=True,
                card=CARD_MASSAGE if key == "massage" else CARD_UTILITY,
            )
            for key in self._inverse_actions()
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        paired_keys = {
            f"tss_{action.node}" + suffix
            for pair in self._inverse_actions().values()
            for action in pair
            for suffix in (("_long",) if action.long else ("", "_raw"))
        }
        specs = list(super().controller_button_specs)
        light = self._toggle_light() if self.supports_light_state_feedback else None
        if (
            light is not None
            and (long := self._button_spec(light, long=True, raw=False)) is not None
        ):
            specs.append(long)
        return (
            ControllerButtonSpec(
                "tss_refresh",
                "Refresh bed features",
                _refresh,
                translation_key="tss_refresh",
                diagnostic=True,
                entity_registry_enabled_default=False,
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
            *tuple(spec for spec in specs if spec.key not in paired_keys),
        )

    def controller_button_available(self, key: str) -> bool:
        return key == "tss_refresh" or super().controller_button_available(key)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **super().protocol_diagnostics,
            "unnamed_motion_controls": [
                button.node
                for button in self._controls
                if not self._action_name(button, long=False, raw=self._resolved_wire == "RAW")
                and any(
                    self._gesture(button, wire, self._selection, long=False)
                    for wire in ("RAW", "FRAMED")
                )
            ],
        }


async def _switch_press(controller: BedController, *, feature: str, enabled: bool) -> None:
    ctrl = require_controller(controller, TssRemoteController)
    pair = ctrl._inverse_actions().get(feature)
    if pair is None:
        raise ctrl._invalid("control")
    action = pair[0 if enabled else 1]
    await ctrl.execute_action(action.node, long=action.long)


async def _refresh(controller: BedController) -> None:
    await require_controller(controller, TssRemoteController).async_execute_richmat_classic_request(
        Request("query")
    )
