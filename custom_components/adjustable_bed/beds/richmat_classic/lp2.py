"""L&P Adjustable Base: its catalog and direct utilities on one owned BLE link."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import partial
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_MASSAGE, CARD_UTILITY
from ...codec import richmat as codec
from ...command_scheduler import current_command_context, note_frame_skipped
from ...controller_state import StateKey
from ...errors import invalid
from ...execution import ExecutionCapabilities
from ...profiles.lp2 import ALARM_COMBINATIONS
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, classify, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
)
from ..richmat.labels import resource_label
from .caller import Selection, effective_status, selected_operand, transition
from .controller import RichmatClassicController
from .profiles import Control
from .protocol import (
    ALARM_QUERY,
    AROMA_QUERY,
    DESK_QUERY,
    INITIALIZE,
    LAMP_QUERY,
    Wire,
    aroma,
    release,
    rgb,
    worker_interval,
)
from .protocol import (
    alarm as alarm_frames,
)
from .receive import ReceiveState
from .requests import Request
from .transport import Transport, select

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

_SCOPE: ContextVar[tuple[BedController, Transport] | None] = ContextVar("lp2_session", default=None)
SYNCHRONIZED: Final = StateKey[bool | None]("lp2_synchronized")
MASSAGE_ON: Final = StateKey[bool | None]("lp2_massage_on")
_ALARMS: Final = {
    0x58: "tv",
    0x46: "anti_snore",
    0x45: "zero_g",
    0x4C: "head_massage",
    0x2E: "memory_1",
    0x4E: "foot_massage",
    0x2F: "memory_2",
    0x59: "lounge",
    0x30: "memory_3",
    0x6B: "zero_g_2",
    0xF6: "flat_sleep",
    0x5D: "massage",
    0xB0: "wake_mode_1",
    0xB1: "wake_mode_2",
}
_PACKAGE_SERVICE: Final = codec.TRANSPORTS["w0"].service_uuid


@dataclass(frozen=True, slots=True)
class Gesture:
    node: int
    resource: str
    status: int
    long: bool = False
    held: bool = False
    # The motor a selected-motor button moves; other controls keep the default.
    flag: str = "53"

    @property
    def label(self) -> str:
        return resource_label(self.resource.removeprefix("@string/"))

    @property
    def saves(self) -> bool:
        shape = classify(self.label)
        return shape is not None and shape.kind is Kind.SAVE

    @property
    def key(self) -> str:
        return (
            f"richmat_classic_{self.node}"
            + ("" if self.flag == "53" else f"_motor{int(self.flag) - 50}")
            + ("_long" if self.long else "_hold" if self.held else "")
        )


def select_transport(client: BleakClient, *, third_service: bool = False) -> Transport:
    """The package's complete first tuple falls through; later services do not."""
    first = client.services.get_service(_PACKAGE_SERVICE)
    standard = codec.TRANSPORTS["w1"]
    if first is not None:
        write = first.get_characteristic(standard.write_uuid)
        notify = first.get_characteristic(standard.notify_uuid)
        if write is not None and notify is not None:
            if not set(write.properties) & {"write", "write-without-response"}:
                raise ValueError("The command characteristic is not writable")
            return Transport(client, write, notify, "FRAMED")
    return select(client, third_service=third_service)


class Lp2Controller(RichmatClassicController):
    """Reuse the literal-verified resource worker, never another app's catalog."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, device_name: str | None = None
    ) -> None:
        super().__init__(coordinator, app="lp2", device_name=device_name)
        self._mode = 0
        self._selection = Selection(hold=False)
        self._deadline: float | None = None
        self._active_button: Control | None = None
        self._preferences = {}

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # Only the bed's command format is kept: it decides which controls exist
        # before the first connection. App UI caches neither prove receiver
        # state nor replay settings.
        return {"wire": self._wire} if self._wire else {}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)

    def _restore_wire(self, state: Mapping[str, object]) -> None:
        wire = state.get("wire")
        if wire not in (None, "RAW", "FRAMED"):
            raise ValueError("Invalid stored command format")
        if wire is not None:
            self._wire = wire

    @property
    def _resolved_wire(self) -> Wire | None:
        """The command format of this session, else of the last one."""
        return self._session.wire if self._session else self._wire

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        # The first connection adds the format's own buttons.
        return True

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        """Before the format is known, keep both formats' own rows."""
        if self._resolved_wire is not None:
            return super().retained_entity_keys
        return frozenset(self._format_entity_keys())

    def _format_entity_keys(self) -> set[tuple[str, str]]:
        """(platform, key) of entities that only one command format lists."""
        by_wire = self._button_gestures()
        shared = by_wire["RAW"] & by_wire["FRAMED"]
        keys = {
            ("button", g.key + "_" + wire.lower())
            for wire, gestures in by_wire.items()
            for g in gestures - shared
        }
        raw, framed = self._pairs("RAW").keys(), self._pairs("FRAMED").keys()
        keys.update(("switch", f"controller_switch_lp2_{name}") for name in raw ^ framed)
        return keys

    def _button(self, node: int) -> Control:
        if self._active_button is not None and self._active_button.node == node:
            return self._active_button
        return super()._button(node)

    @contextmanager
    def _transaction(self) -> Iterator[Transport]:
        session = self._session
        if session is None or self.client is not session.client or not session.client.is_connected:
            raise ConnectionError("The bed is disconnected")
        previous = _SCOPE.get()
        if previous is not None and (previous[0] is not self or previous[1] is not session):
            raise ConnectionError("The admitted bed session changed")
        token = _SCOPE.set((self, session))
        try:
            yield session
        finally:
            _SCOPE.reset(token)

    async def _send(self, packet: bytes, cancel: asyncio.Event | None = None) -> None:
        if self._coordinator.controller is not self:
            raise ConnectionError("The bed controller changed")
        scope = _SCOPE.get()
        if scope is not None and (scope[0] is not self or scope[1] is not self._session):
            raise ConnectionError("The admitted bed session changed")
        session = self._session
        if session is not None and packet == release(session.wire, self._mode):
            cancel = None
        await super()._send(packet, cancel)
        if (
            session is not self._session
            or session is None
            or self.client is not session.client
            or self._coordinator.controller is not self
        ):
            raise ConnectionError("The bed session changed during delivery")

    def _notification(
        self, session: Transport, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            return
        # HA retention budget; the app's longest parsed record is 16 bytes.
        if len(self._receive.buffer) + len(data) * 2 > 256:
            self.forward_raw_notification(session.notify.uuid, bytes(data))
            self._receive.buffer = ""
            self._rejection = "Notification exceeded the receive budget"
            self._publish()
            return
        super()._notification(session, sender, data)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        from ...const import CONF_RICHMAT_CLASSIC_THIRD_SERVICE

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The bed is disconnected")
        session = select_transport(
            client,
            third_service=self._coordinator.entry.data.get(
                CONF_RICHMAT_CLASSIC_THIRD_SERVICE, False
            ),
        )
        self._session = session
        self._wire = session.wire
        self._notify_callback = callback
        self._receive = ReceiveState()
        self._worker.cancel()
        name = self._device_name or self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(name, session.wire, rise=True))
        try:
            with self._transaction():
                self._notifications_started = False
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
                if session.wire == "FRAMED" and self._notifications_started:
                    await asyncio.sleep(0.3)
                    await self._send(DESK_QUERY if self.layout in ("FWRM", "WFRM") else INITIALIZE)
                    for packet in ((ALARM_QUERY,) if self._alarm_actions() else ()) + (
                        LAMP_QUERY,
                        AROMA_QUERY,
                    ):
                        await self._send(packet)
                        await asyncio.sleep(0.5)
        except BaseException:
            self._session = None
            raise
        self._publish()

    def on_disconnect(self) -> None:
        self._receive = ReceiveState()
        self._preferences = {}
        self.forward_controller_state_updates(SYNCHRONIZED(None), MASSAGE_ON(None))
        super().on_disconnect()

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        scope = _SCOPE.get()
        session = scope[1] if scope and scope[0] is self else self._session
        if session is None or self._session is not session or not session.client.is_connected:
            return

        # A command's own cleanup is not delivery of the requested setting.
        async def cleanup() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if (
                self._session is session
                and self.client is session.client
                and session.client.is_connected
                and self._coordinator.controller is self
            ):
                await self._send(release(session.wire, self._mode if mode is None else mode))

        await settled(cleanup())

    async def execute_action(
        self,
        node: int,
        *,
        long: bool = False,
        hold_ms: int | None = None,
        mode: int = 0,
        head: bool = True,
        flag: str = "53",
        held: bool = False,
    ) -> None:
        gestures = self.validate_action(node, long=long, held=held, head=head, flag=flag)
        single_save = any(g.saves and g.status == 1 for g in gestures)
        if mode not in self._model.modes or flag not in ("53", "54", "55"):
            raise ValueError("This control selection is unavailable")
        with self._transaction():
            original, previous_mode = self._selection, self._mode
            self._selection, self._mode = Selection(hold=held, head=head, press_flag=flag), mode
            button = super()._button(node)
            # E3RM changes status for its memory checkbox. Expose recall, save
            # and held recall directly instead of retaining an armed UI state.
            if button.extra == "100" and self.layout == "E3RM":
                button = replace(button, status=1 if held else 3)
            self._active_button = button
            context = current_command_context()
            duration = (
                hold_ms
                if hold_ms is not None
                else int(self._coordinator.entry.data.get("motor_pulse_count", 10))
                * self._worker.tick_ms
            )
            # A confirmed save is one emission even when its catalog status is
            # the repeating motor gesture. Only movement uses the requested duration.
            self._deadline = (
                None if single_save or context and context.lease else monotonic() + duration / 1000
            )
            self._worker.cancel()
            try:
                await super().execute_action(node, long=long, hold_ms=0 if single_save else hold_ms)
            finally:
                self._worker.cancel()
                self._active_button = None
                self._deadline = None
                self._selection, self._mode = original, previous_mode

    async def _iteration(self, cancel: asyncio.Event, mode: int) -> bool:
        if self._worker.mode == 1 and self._deadline is not None and monotonic() >= self._deadline:
            self._worker.mode = 0
        return await super()._iteration(cancel, mode)

    async def _next_tick(self, cancel: asyncio.Event) -> bool:
        delay = self._worker.tick_ms
        if self._worker.mode == 1 and self._deadline is not None:
            delay = min(delay, max(0, ceil((self._deadline - monotonic()) * 1000)))
        return await self._wait(delay, cancel)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        # Side, arming, head/foot and press behavior are operation parameters.
        return ()

    def _gesture(
        self,
        node: int,
        wire: Wire,
        *,
        long: bool = False,
        held: bool = False,
        head: bool = True,
        flag: str = "53",
    ) -> Gesture:
        if long and held:
            raise ValueError("Choose either a long press or a held control")
        button = super()._button(node)
        if button.extra == "100" and self.layout == "E3RM":
            button = replace(button, status=1 if held else 3)
        selection = Selection(hold=held, head=head, press_flag=flag)
        status = effective_status(button, self.layout, selection)
        if (
            status not in (1, 2, 3)
            or transition(button, self.layout, wire, selection, "DOWN", app="lp2").local
        ):
            raise ValueError("Choose a direct bed control, not a local menu")
        if self._hidden(button) and not (button.hold_affected and held):
            raise ValueError("This control is hidden in the selected app state")
        if button.excluded_long if long else button.excluded_short:
            raise ValueError("This gesture controls an excluded accessory")
        if long and (
            status != 3 or button.long is None or button.mem_special or button.select_special
        ):
            raise ValueError("This control has no long press")
        argument = 3 if long else 1 if button.mem_special else 2 if status == 3 else status
        if not isinstance(selected_operand(button, wire, argument, selection), bytes):
            raise ValueError("This gesture has no command on the selected connection")
        field = (
            "press_long"
            if long
            else (
                "press_short_old"
                if wire == "RAW" and button.short_old is not None
                else "press_short"
            )
        )
        if argument == 1:
            if button.tag in ("51", "52"):
                resource = (
                    f"@string/k_motor{int(flag) - 50}_{'up' if button.tag == '51' else 'down'}"
                )
            elif button.tag == "63":
                resource = button.resource_keys.get("press_short_old", "")
            else:
                resource = button.resource_keys.get(field, "")
        else:
            resource = button.resource_keys.get(field, "")
        # A missing resource keeps the catalog's own label, never another opcode's name.
        return Gesture(
            node,
            resource or button.label,
            status,
            long,
            held,
            flag if button.tag in ("51", "52") else "53",
        )

    def validate_action(
        self,
        node: int,
        *,
        long: bool = False,
        held: bool = False,
        head: bool = True,
        flag: str = "53",
    ) -> tuple[Gesture, ...]:
        wire = self._resolved_wire
        wires: tuple[Wire, ...] = (wire,) if wire else ("RAW", "FRAMED")
        gestures = tuple(
            self._gesture(node, selected, long=long, held=held, head=head, flag=flag)
            for selected in wires
        )
        if held and any(g.saves or g.status != 1 for g in gestures):
            raise ValueError("This control does not support held execution")
        context = current_command_context()
        if context and context.lease and any(g.saves or g.status != 1 for g in gestures):
            raise invalid("control_hold_renewal_not_supported")
        return gestures

    def _flags(self, button: Control) -> tuple[str, ...]:
        """The motors a selected-motor button is listed for."""
        return ("53",)

    def _gestures(self, wire: Wire) -> tuple[Gesture, ...]:
        result = []
        for button in self._controls:
            for long, held in ((False, False), (True, False), (False, True)):
                if not button.rich_button or held and not button.hold_affected:
                    continue
                for flag in self._flags(button):
                    try:
                        result.append(
                            self._gesture(button.node, wire, long=long, held=held, flag=flag)
                        )
                    except ValueError:
                        continue
        return tuple(result)

    @staticmethod
    def _resource(gesture: Gesture) -> str:
        return re.sub(r"_(?:old\d*|new)$", "", gesture.resource.removeprefix("@string/"))

    def _pairs(self, wire: Wire) -> dict[str, tuple[Gesture, Gesture]]:
        by_resource = {self._resource(g): g for g in self._gestures(wire) if not g.held}
        return {
            name: (by_resource[on], by_resource[off])
            for name, on, off in (
                ("sync", "k_sync_on", "k_sync_off"),
                ("massage", "com_msg_on", "com_msg_off"),
                ("massage", "com_msg_on", "com_msg_off2"),
                ("massage", "com_msg_on", "com_msg_off3"),
            )
            if on in by_resource and off in by_resource
        }

    def _timers(self, wire: Wire) -> dict[int, int]:
        if any(c.tag == "65" for c in self._controls):
            return {15: -1, 30: -2, 45: -3}
        if self.layout == "APRM":
            return {}  # Its minute resources and button artwork disagree.
        result = {}
        for gesture in self._gestures(wire):
            if gesture.long or gesture.held:
                continue
            if match := re.fullmatch(r"com_msg_(10|20|30)min", self._resource(gesture)):
                result.setdefault(int(match[1]), gesture.node)
        return result

    @property
    def _timer_controls(self) -> dict[int, int]:
        wire = self._resolved_wire
        if wire:
            return self._timers(wire)
        raw, framed = self._timers("RAW"), self._timers("FRAMED")
        return {minutes: node for minutes, node in raw.items() if framed.get(minutes) == node}

    @property
    def auto_enable_massage(self) -> bool:
        return bool(self._timer_controls)

    @property
    def supports_massage_timer(self) -> bool:
        return bool(self._timer_controls)

    @property
    def massage_timer_options(self) -> list[int]:
        return sorted(self._timer_controls)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        node = self._timer_controls.get(minutes)
        if node is None:
            raise ValueError("Choose a massage duration this layout offers")
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            if node < 0:
                from .protocol import massage_popup

                with self._transaction():
                    await self._frames((massage_popup(str(minutes)),))
            else:
                await self.execute_action(node)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        wire = self._resolved_wire
        # Before the format is known, only on/off pairs both formats offer.
        names = (
            self._pairs(wire).keys()
            if wire
            else self._pairs("RAW").keys() & self._pairs("FRAMED").keys()
        )
        specs = []
        for name in sorted(names):

            async def set_value(controller: BedController, enabled: bool, *, feature=name) -> None:
                if not isinstance(controller, Lp2Controller):
                    raise TypeError("The selected bed controller changed")
                with controller._transaction() as session:
                    pair = controller._pairs(session.wire).get(feature)
                    if pair is None:
                        raise ValueError("This connection does not offer the on/off pair")
                    selected = pair[0 if enabled else 1]
                    key = SYNCHRONIZED if feature == "sync" else MASSAGE_ON
                    with controller.sent_state(key(enabled)):
                        await controller.execute_action(selected.node, long=selected.long)

            specs.append(
                ControllerSwitchSpec(
                    "lp2_" + name,
                    "synchronization" if name == "sync" else "massage",
                    set_value,
                    state_key=SYNCHRONIZED if name == "sync" else MASSAGE_ON,
                    assumed_state=True,
                    card=CARD_UTILITY if name == "sync" else CARD_MASSAGE,
                    entity_registry_enabled_default=name == "massage",
                    available_fn=lambda c, key="lp2_" + name: (
                        isinstance(c, Lp2Controller) and c.controller_switch_available(key)
                    ),
                )
            )
        return tuple(specs)

    def controller_switch_available(self, key: str) -> bool:
        wire = self._resolved_wire
        return bool(wire and key.removeprefix("lp2_") in self._pairs(wire))

    def _button_gestures(self) -> dict[Wire, set[Gesture]]:
        """Each format's gestures that are buttons, not switches or timers."""
        by_wire: dict[Wire, set[Gesture]] = {}
        for wire in ("RAW", "FRAMED"):
            pairs = {g for pair in self._pairs(wire).values() for g in pair}
            timers = set(self._timers(wire).values())
            by_wire[wire] = {
                g
                for g in self._gestures(wire)
                if g not in pairs and not (not g.long and not g.held and g.node in timers)
            }
        return by_wire

    def _button_actions(self) -> dict[str, tuple[Gesture, Wire | None]]:
        """Gestures both formats send alike, plus those of the bed's own format.

        A gesture that differs between formats keeps its format in its key, so
        each format's entities have stable unique IDs. The other format's are
        never listed: on some layouts the same node does something else there.
        """
        by_wire = self._button_gestures()
        shared = by_wire["RAW"] & by_wire["FRAMED"]
        result: dict[str, tuple[Gesture, Wire | None]] = {g.key: (g, None) for g in shared}
        if wire := self._resolved_wire:
            result.update({g.key + "_" + wire.lower(): (g, wire) for g in by_wire[wire] - shared})
        return dict(sorted(result.items()))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec | None] = []
        for key, (gesture, _wire) in self._button_actions().items():
            label = gesture.label + (" (hold)" if gesture.held else "")
            if self.layout == "APRM" and gesture.node in (26, 27):
                label = f"Massage timer {gesture.node - 25}"
            result.append(
                catalog_button(
                    key,
                    label,
                    partial(_press, key=key, expected=gesture),
                    hold=ControllerHoldSpec(key, release_button_key="richmat_classic_release")
                    if gesture.status == 1 and not gesture.saves
                    else None,
                    requires_confirmation=gesture.saves or gesture.long,
                )
            )
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
        return unique_buttons(result)

    def controller_button_available(self, key: str) -> bool:
        if key == "richmat_classic_release":
            return True
        selected = self._button_actions().get(key)
        return selected is not None and (selected[1] is None or selected[1] == self._resolved_wire)

    @property
    def execution(self) -> ExecutionCapabilities:
        return ExecutionCapabilities(
            hold="stream",
            hold_controls=frozenset(
                spec.hold.control
                for spec in self.controller_button_specs
                if spec.hold is not None and self.controller_button_available(spec.key)
            ),
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        gesture, _ = self._button_actions()[control]
        await self.execute_action(gesture.node, hold_ms=duration_ms, held=True, flag=gesture.flag)

    def validate_richmat_classic_request(self, request: Request) -> None:
        if request.operation not in (
            "query",
            "massage_timer",
            "massage_popup",
            "desk_target",
            "desk_unit",
            "desk_recall",
            "desk_reset",
        ):
            raise ValueError("Use set_alarm or the bed settings action")
        super().validate_richmat_classic_request(request)

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        with self._transaction():
            await super().async_execute_richmat_classic_request(request)

    def _alarm_zones(self) -> dict[str, int]:
        owned = set(self._alarm_actions().values())
        zones = {
            name: code
            for name, code in (("both", 0x5D), ("head", 0x4C), ("feet", 0x4E))
            if code in owned
        }
        if {0x4C, 0x4E} <= owned:
            zones["both"] = 0x5D
        return {key: zones[key] for key in ("both", "head", "feet") if key in zones}

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        actions = tuple(_ALARMS[code] for code in dict.fromkeys(self._alarm_actions().values()))
        zones = self._alarm_zones()
        return (
            AlarmCapability(
                wake_actions=(*actions, "none") if zones else actions,
                massage=bool(zones),
                massage_zones=tuple(zones),
                requires_wake_action=True,
                live_check=True,
            )
            if actions
            else None
        )

    def _alarm_code(self, alarm: AlarmRequest) -> int:
        if not alarm.enabled:
            return 0
        owned = self._alarm_actions().values()
        bed = next((code for code in owned if _ALARMS[code] == alarm.wake_action), None)
        if alarm.wake_action != "none" and bed is None:
            raise ValueError("Choose an alarm action offered by this bed layout")
        massage = self._alarm_zones().get(alarm.massage_zone or "both") if alarm.massage else None
        if alarm.massage and massage is None:
            raise ValueError("Choose a massage zone offered by this bed layout")
        if bed is None:
            if massage is None:
                raise ValueError("Choose an alarm preset or massage")
            return massage
        if massage is None:
            return bed
        if bed in (0x5D, 0x4C, 0x4E):
            return bed if bed == massage else 0x5D
        combination = ALARM_COMBINATIONS.get(bed)
        if combination is None:
            raise ValueError("This preset has no alarm combination with massage")
        return combination[(0x5D, 0x4C, 0x4E).index(massage)]

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self._alarm_code(alarm)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        if self.alarm_capability is None:
            raise ValueError("Choose a layout with alarm controls")
        self.validate_alarm(alarm)
        if self._session is None:
            raise ConnectionError("The bed is disconnected")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        code = self._alarm_code(alarm)
        with self._transaction():
            await self._frames(
                alarm_frames(alarm.minutes_until(dt_util.now()) if alarm.enabled else 0, code), 300
            )
            await self._wait(300, self._coordinator.cancel_command)

    async def _frames(self, packets: tuple[bytes, ...], gap: int = 0) -> None:
        for i, packet in enumerate(packets):
            if self._coordinator.cancel_command.is_set():
                note_frame_skipped()
                return
            await self.write_command(packet)
            if (
                i + 1 < len(packets)
                and gap
                and not await self._wait(gap, self._coordinator.cancel_command)
            ):
                note_frame_skipped()
                return

    async def settings(
        self,
        *,
        color: tuple[int, int, int] | None = None,
        seconds: int | None = None,
        aroma_times: tuple[int, int, int] | None = None,
        fan: str | None = None,
        level: int = 0,
        duration: int = 0,
    ) -> None:
        """Direct feature frames never inherit an ordinary control's release."""
        with self._transaction():
            if color is not None:
                if (
                    not self._receive.light_capable
                    or len(color) != 3
                    or any(type(v) is not int or not 0 <= v <= 255 for v in color)
                ):
                    raise ValueError("The bed must report lighting support before setting color")
                await self._frames((rgb(*color),))
            elif seconds is not None:
                if not self._receive.light_capable or not 0 <= seconds <= 300:
                    raise ValueError(
                        "Choose a light duration from 0 to 300 seconds on a bed with lighting"
                    )
                await self._frames((codec.light_timer(seconds >> 8, seconds),))
            elif aroma_times is not None:
                if not self._receive.aroma_capable or not all(
                    1 <= n <= limit for n, limit in zip(aroma_times, (60, 60, 12), strict=True)
                ):
                    raise ValueError("Choose supported aromatherapy times")
                await self._frames(
                    tuple(
                        aroma(opcode, value)
                        for opcode, value in zip((0x1B, 0x1C, 0x1D), aroma_times, strict=True)
                    ),
                    150,
                )
            elif fan is not None:
                if (
                    fan not in ("head", "foot")
                    or level not in (0, 20, 40, 60, 80, 100)
                    or not 0 <= duration <= 6
                ):
                    raise ValueError(
                        "Choose the fan, an intensity in steps of 20 and duration 0 to 6"
                    )
                volume = 0xD7 + level // 20
                packets = (
                    (codec.frame(0x6E, 1, 0xD0 + duration, 0), codec.frame(0x6E, 1, volume, 0))
                    if fan == "head"
                    else (codec.command(volume, 1),) * 2
                )
                await self._frames(packets, 300)
            else:
                raise ValueError("Choose a bed setting")


async def _press(controller: BedController, *, key: str, expected: Gesture) -> None:
    if not isinstance(controller, Lp2Controller):
        raise TypeError("The selected bed controller changed")
    selected = controller._button_actions().get(key)
    # Listed means the bed's own format or shared by both.
    if selected is None or selected[0] != expected:
        raise ValueError("The selected control changed on this connection")
    await controller.execute_action(
        expected.node, long=expected.long, held=expected.held, flag=expected.flag
    )
