"""Base Remote's catalog, with one captured BLE session per admitted command."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from functools import partial
from math import ceil, isfinite
from typing import TYPE_CHECKING, Final

from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory

from ...alarm import AlarmCapability, AlarmRequest
from ...card import (
    CARD_HIDDEN,
    CARD_LIGHTING,
    CARD_UTILITY,
    CardRole,
    CardSection,
    motor_card,
)
from ...command_scheduler import current_command_context, note_frame_skipped
from ...const import CONF_BASEREMOTE_SINGLE_BASE
from ...controller_state import StateKey
from ...errors import failed, invalid
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles.baseremote import (
    ALARM_SPACING_MS,
    EXCLUDED_LAYOUTS,
    GROUP_SETTLE_MS,
    HELD_RELEASE_MS,
    MODE_LABELS,
    QUERY_SPACING_MS,
    SETTINGS_SPACING_MS,
    SIDE_LAYOUTS,
    STARTUP_MS,
    TAP_RELEASE_MS,
    sender_interval,
)
from ...profiles.richmat import RICHMAT_CODES
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, classify, on_off_switch, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..richmat.labels import resource_label
from ..richmat_classic.caller import (
    RETAIN,
    Selection,
    effective_status,
    nordic_label,
    selected_operand,
    short_operand,
    transition,
)
from ..richmat_classic.controller import STATUS, RichmatClassicController
from ..richmat_classic.profiles import Control
from ..richmat_classic.protocol import (
    ALARM_QUERY,
    AROMA_QUERY,
    INITIALIZE,
    LAMP_QUERY,
    RELEASE,
    aroma,
    control,
    massage_popup,
    massage_timer,
)
from ..richmat_classic.protocol import (
    alarm as countdown_alarm,
)
from ..richmat_classic.receive import MalformedFrame, ReceiveState
from ..richmat_classic.session import SessionController
from ..richmat_classic.transport import Transport, select
from . import protocol as p

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


async def _stop_subscription(client: BleakClient, characteristic: BleakGATTCharacteristic) -> None:
    try:
        await client.stop_notify(characteristic)
    except BaseException:
        # Bleak registers before StartNotify, but failed StopNotify leaves that callback behind.
        backend = getattr(client, "_backend", None)
        if isinstance(backend, BleakClientBlueZDBus):
            backend._notification_callbacks.pop(characteristic.obj[0], None)
        raise


LAMP_TIMEOUT: Final = StateKey[int | None]("baseremote_lamp_timeout")
AROMA_ON_TIME: Final = StateKey[int | None]("baseremote_aroma_on_time")
AROMA_INTERVAL: Final = StateKey[int | None]("baseremote_aroma_interval")
AROMA_PAUSE: Final = StateKey[int | None]("baseremote_aroma_pause")

# The card finds a held control's release button by its translation key.
_RELEASE: Final = "richmat_classic_release"

# What the Richmat remotes move the head and the feet with. A control that sends
# one of these is that motor, whatever number the app's layout gives it (#1161).
_MOTORS: Final = {
    bytes((RICHMAT_CODES["head_up"],)): ("head", "up"),
    bytes((RICHMAT_CODES["head_down"],)): ("head", "down"),
    bytes((RICHMAT_CODES["feet_up"],)): ("feet", "up"),
    bytes((RICHMAT_CODES["feet_down"],)): ("feet", "down"),
}


@dataclass(frozen=True, slots=True)
class Gesture:
    node: int
    mode: int = 0
    long: bool = False
    selection: Selection = Selection()
    label: str = ""
    # Listed for a Nordic connection, where this control does something else.
    nordic: bool = False

    @property
    def key(self) -> str:
        suffix = "_save" if self.long else "_hold" if self.selection.hold else ""
        return (
            f"baseremote_m{self.mode}_n{self.node}{suffix}_{self.selection.press_flag}"
            + ("_raw" if self.nordic else "")
        )


async def _press(controller: BedController, gesture: Gesture) -> None:
    assert isinstance(controller, BaseRemoteController)
    await controller.async_gesture(gesture)


class BaseRemoteController(SessionController):
    """Reuse the classic getters and the resource controller's drained ATT writes.

    Catalogs, startup, parsing, entities and utilities belong to this app. UI
    draft selectors are replaced by commands that capture their own context.
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str | None = None,
        device_name: str | None = None,
    ) -> None:
        if str(coordinator.entry.data.get("product_type", "")).upper() in EXCLUDED_LAYOUTS:
            raise invalid("baseremote_layout")
        RichmatClassicController.__init__(
            self, coordinator, app=app or "baseremote", device_name=device_name
        )
        if self.layout in EXCLUDED_LAYOUTS:
            raise invalid("baseremote_layout")
        self._single_base = (
            self.layout in SIDE_LAYOUTS
            and coordinator.entry.data.get(CONF_BASEREMOTE_SINGLE_BASE) is True
        )
        self._receive = ReceiveState()
        self._group_only = False
        self._color_light_identity = False
        self._preferences = {}

    @property
    def _modes(self) -> tuple[int, ...]:
        # One base answers Left and Right alike, so it keeps the first.
        return (0,) if self._single_base else self._model.modes

    def _mode_label(self, mode: int) -> str:
        return "" if self._single_base else MODE_LABELS.get(self.layout, {}).get(mode, "")

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"color_light_identity": self._color_light_identity}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        # Registry identity only, never permission to send a color command.
        self._color_light_identity = state.get("color_light_identity") is True

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "layout": self.layout,
            "state": {**asdict(self._receive), "menu": sorted(self._receive.menu)},
            "rejection": self._rejection,
            "hardware": "UNVERIFIED",
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return ()

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        # Identity retention never grants permission to use a stale capability.
        return frozenset(
            {
                ("light", "under_bed_lights"),
                ("number", "controller_number_baseremote_lamp_timeout"),
                *(
                    ("number", "controller_number_baseremote_" + key)
                    for key in (
                        "aroma_on_time",
                        "aroma_interval",
                        "aroma_pause",
                    )
                ),
            }
        )

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        keys = []
        if not self._receive.light_capable:
            keys.append("controller_number_baseremote_lamp_timeout")
        if not self._receive.aroma_capable:
            keys.extend(
                "controller_number_baseremote_" + key
                for key in (
                    "aroma_on_time",
                    "aroma_interval",
                    "aroma_pause",
                )
            )
        if not self.supports_lights or self.light_color_control_pending:
            keys.append("under_bed_lights")
        return tuple(keys)

    @property
    def _massage_timer_values(self) -> dict[int, int | str]:
        """What each timer choice sends, by its minutes (0 is off)."""
        if self._group_only:
            return {}
        if self.layout in ("D1RM", "D9RM"):
            return {0: 0, 15: 2, 30: 3, 45: 5}
        if any(c.tag == "65" for c in self._controls):
            # The popup's on/off row is a toggle, never an idempotent off.
            return {15: "15", 30: "30", 45: "45"}
        return {}

    @property
    def supports_massage_timer(self) -> bool:
        return bool(self._massage_timer_values)

    @property
    def auto_enable_massage(self) -> bool:
        # The app always shows the layout's massage timer.
        return super().auto_enable_massage or self.supports_massage_timer

    @property
    def massage_timer_options(self) -> list[int]:
        return sorted(minutes for minutes in self._massage_timer_values if minutes)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return 0 in self._massage_timer_values

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        # The massage timer is the shared timer select.
        return ()

    def _publish(self) -> None:
        # The state event also discovers newly proven light/aroma entities.
        self.forward_controller_state_updates(STATUS("ready" if self._session else "disconnected"))

    def _clear_state(self) -> None:
        self._receive = ReceiveState()
        self._rejection = None
        self.forward_controller_state_updates(
            LAMP_TIMEOUT(None),
            MASSAGE_TIMER_MINUTES(None),
            AROMA_ON_TIME(None),
            AROMA_INTERVAL(None),
            AROMA_PAUSE(None),
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
        )

    def on_disconnect(self) -> None:
        self._clear_state()
        RichmatClassicController.on_disconnect(self)

    async def stop_notify(self) -> None:
        session, self._session = self._session, None
        subscribed, self._notifications_started = self._notifications_started, False
        self._worker.cancel()
        self._clear_state()

        try:
            # The caller owns the connection lane and its teardown deadline.
            # Cancellation still clears the exact captured BlueZ callback.
            if (
                session is not None
                and subscribed
                and self._coordinator.controller is self
                and self._session is None
                and self.client is session.client
                and session.client.is_connected
            ):
                await _stop_subscription(session.client, session.notify)
        finally:
            self._publish()

    async def async_refresh_auth(self) -> None:
        # A failed close can retain the physical link after stopping this session.
        if self._session is None:
            async with self._coordinator.async_connection_operation_guard():
                if self._coordinator.controller is not self:
                    raise ConnectionError("The bed controller changed before session recovery")
                if self._session is None:
                    await self.start_notify()

    @property
    def restore_notifications_after_cancel(self) -> bool:
        # Initialization drains subscription registration and ATT preparation.
        # Retry under the next command's admission, outside bounded pair rollback.
        return False

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The bed is disconnected")
        self._group_only = False
        third_service = self._coordinator.entry.data.get("richmat_classic_third_service", False)
        services = list(client.services)
        if len(services) > 2 and services[2].uuid.lower() == "0000ffe0-0000-1000-8000-00805f9b34fb":
            # FFE0 is the local group configuration lane, never a bed transport.
            third_service = False
        try:
            session = select(
                client,
                third_service=third_service,
            )
        except ValueError:
            # A configuration-only receiver must never receive bed opcodes.
            session = self._group_transport()
            self._group_only = True
        self._worker.cancel()
        self._worker.set_interval(
            sender_interval(
                self._device_name or self._coordinator.entry.data.get("ble_device_name"),
                raw=session.wire == "RAW",
            )
        )
        self._session, self._wire = session, session.wire
        self._clear_state()
        self._notifications_started = False
        subscribed = False
        try:
            with self._transaction():
                if session.has_notifications:

                    async def subscribe() -> None:
                        nonlocal subscribed
                        if self._session is not session or self.client is not client:
                            raise ConnectionError("The captured bed session ended before subscribe")
                        subscribed = True
                        result = await client.start_notify(
                            session.notify, partial(self._notification, session)
                        )
                        # BlueZ registers its callback before awaiting StartNotify.
                        # Record completion before cancellation can enter rollback.
                        subscribed = result is not False
                        if self._session is session:
                            self._notifications_started = subscribed

                    await settled(subscribe())
                if self._group_only:
                    return
                if session.wire == "FRAMED" and self._notifications_started:
                    await asyncio.sleep(STARTUP_MS / 1000)
                    await self._send(INITIALIZE)
                # Opening Settings in Android is a preparation step in HA.
                frames = ([ALARM_QUERY] if self._alarm_codes() else []) + [LAMP_QUERY, AROMA_QUERY]
                for packet in frames:
                    await self._send(packet)
                    await asyncio.sleep(QUERY_SPACING_MS / 1000)
        except BaseException:
            if self._session is session:
                self._session = None
                self._notifications_started = False
                self._clear_state()

                async def rollback() -> None:
                    # Connect and retained-link recovery own the connection lane.
                    # A stale initializer must never unsubscribe a replacement.
                    if (
                        subscribed
                        and self._coordinator.controller is self
                        and self._session is None
                        and self.client is session.client
                        and session.client.is_connected
                    ):
                        await _stop_subscription(session.client, session.notify)

                try:
                    await settled(rollback())
                except Exception:
                    _LOGGER.debug("Failed to stop Base Remote's failed subscription", exc_info=True)
            raise

    def _notification(self, session, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        if self._group_only:
            return
        try:
            self._receive.feed(
                bytes(data),
                app=self.app,
                layout=self.layout,
                desk_bound=False,
                table_controls_bound=False,
            )
            self._rejection = None
        except MalformedFrame as error:
            self._rejection = str(error)
        if self._receive.light_capable and self.supports_lights:
            self._color_light_identity = True
        if self._receive.value_event in ("6e0e00017d", "6e0e00037f"):
            self.forward_controller_state_updates(
                UNDER_BED_LIGHTS_ON(self._receive.value_event == "6e0e00037f")
            )
        self._publish()

    def _nordic_label(self, button: Control) -> str | None:
        """The control's own name on a Nordic connection, when it differs."""
        wire = self._session.wire if self._session else self._wire
        return nordic_label(button) if wire == "RAW" else None

    def _contexts(self) -> tuple[Gesture, ...]:
        if self._group_only:
            return ()
        gestures = []
        for mode in self._modes:
            prefix = self._mode_label(mode)
            for button in self._controls:
                if button.excluded_short and button.excluded_long or button.status not in (1, 2, 3):
                    continue
                if self._hidden(button) and not button.hold_affected:
                    continue
                if transition(
                    button, self.layout, "FRAMED", Selection(), "DOWN", app=self.app
                ).local:
                    continue
                selections = (Selection(),)
                if button.tag in ("51", "52"):
                    selections = tuple(Selection(press_flag=flag) for flag in ("53", "54", "55"))
                for selection in selections:
                    legacy = self._nordic_label(button)
                    label = legacy or resource_label(
                        (
                            button.resource_keys.get("press_short")
                            or button.resource_keys.get("press_short_old")
                            or button.resource_keys.get("press_long")
                            or ""
                        ).removeprefix("@string/")
                    )
                    if button.tag in ("51", "52"):
                        label = f"Motor {int(selection.press_flag) - 50} {'up' if button.tag == '51' else 'down'}"
                    if button.tag == "63":
                        key = button.resource_keys.get("press_short_old", "")
                        label = (
                            "Set"
                            if key == "@string/k_set_old"
                            else resource_label(key.removeprefix("@string/"))
                        )
                    if prefix:
                        label = (
                            f"Save {prefix.lower()} {label[5:]}"
                            if label.startswith("Save ")
                            else f"{prefix} {label}"
                        )
                    if not button.excluded_short and (
                        button.short or button.short_old or button.tag in ("51", "52", "63")
                    ):
                        gestures.append(
                            Gesture(button.node, mode, False, selection, label, bool(legacy))
                        )
                    if (
                        button.long
                        and not button.excluded_long
                        and (button.status == 3 or button.mem_special)
                    ):
                        name = resource_label(
                            button.resource_keys.get("press_long", "").removeprefix("@string/")
                        )
                        if prefix:
                            name = (
                                f"Save {prefix.lower()} {name[5:]}"
                                if name.startswith("Save ")
                                else f"{prefix} {name}"
                            )
                        gestures.append(Gesture(button.node, mode, True, selection, name))
                    if button.hold_affected and not button.view_id.endswith("Long"):
                        gestures.append(
                            Gesture(
                                button.node,
                                mode,
                                False,
                                replace(selection, hold=True),
                                "Move to " + label,
                                bool(legacy),
                            )
                        )
        return tuple(gestures)

    def _held(self, gesture: Gesture) -> bool:
        button = self._button(gesture.node)
        return (
            not gesture.long
            and not gesture.label.startswith("Save ")
            and self._keeps(button, gesture.selection)
        )

    def _pair_groups(self) -> dict[tuple[int, str], dict[bool, Gesture]]:
        groups: dict[tuple[int, str], dict[bool, Gesture]] = {}
        for gesture in self._contexts():
            label = gesture.label
            for ending, value in ((" on", True), (" off", False)):
                if label.lower().endswith(ending) and not gesture.long:
                    groups.setdefault((gesture.mode, label[: -len(ending)]), {})[value] = gesture
        return {key: pair for key, pair in groups.items() if len(pair) == 2}

    def _motors(self) -> dict[tuple[int, str], dict[str, Gesture]]:
        """The held controls that move the head or the feet, by mode and motor.

        Only a control that sends the motor's operand on both connections, so a
        bed's entities never depend on its connection. Numbered modes keep
        their buttons: only a side names a motor of its own.
        """
        motors: dict[tuple[int, str], dict[str, Gesture]] = {}
        for gesture in self._contexts():
            if (
                gesture.long
                or not self._held(gesture)
                or self._mode_label(gesture.mode) not in ("", "Left", "Right")
            ):
                continue
            button = self._button(gesture.node)
            operands = {
                selected_operand(button, wire, 1, gesture.selection) for wire in ("RAW", "FRAMED")
            }
            operand = operands.pop()
            if not operands and isinstance(operand, bytes) and operand in _MOTORS:
                motor, direction = _MOTORS[operand]
                motors.setdefault((gesture.mode, motor), {})[direction] = gesture
        return {key: pair for key, pair in motors.items() if len(pair) == 2}

    @property
    def supports_motor_control(self) -> bool:
        return bool(self._motors())

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = []
        for (mode, motor), pair in self._motors().items():
            side = self._mode_label(mode).lower()
            key = f"{side}_{motor}" if side else motor
            specs.append(
                MotorControlSpec(
                    key,
                    key,
                    partial(_press, gesture=pair["up"]),
                    partial(_press, gesture=pair["down"]),
                    lambda c: c.stop_all(),
                    max_angle=45 if motor == "feet" else 68,
                    # One worker sends every held control.
                    scheduler_resource="*",
                    # A press moves for the bed's "Movement per tap", as its buttons do.
                    hold=ControllerMotorHoldSpec(
                        pair["up"].key,
                        pair["down"].key,
                        release_button_key=_RELEASE,
                        stop_scope="side",
                        press_hold_ms=None,
                    ),
                )
            )
        return tuple(specs)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        result = []
        for (_, label), pair in self._pair_groups().items():
            if "light" in label.lower():
                continue
            result.append(
                on_off_switch(
                    pair[True].key + "_switch",
                    "baseremote_switch",
                    partial(_press, gesture=pair[True]),
                    partial(_press, gesture=pair[False]),
                    translation_placeholders={"action": label},
                    assumed_state=True,
                )
            )
        return tuple(result)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        paired = {g.key for pair in self._pair_groups().values() for g in pair.values()}
        # The head and feet covers send these.
        paired |= {g.key for pair in self._motors().values() for g in pair.values()}
        specs = []
        seen = set()
        for gesture in self._contexts():
            if gesture.key in paired:
                continue
            if (
                "light" in gesture.label.lower()
                and not gesture.long
                and self._light_toggle() == gesture.node
                and len(self._modes) == 1
            ):
                # The light entity is this toggle; a separate long-press off stays a button.
                continue
            button = self._button(gesture.node)
            save = gesture.label.startswith("Save ")
            if save:
                argument = 3 if gesture.long else 2
                signature = (
                    gesture.mode,
                    gesture.label,
                    *(
                        selected_operand(button, wire, argument, gesture.selection)
                        for wire in ("RAW", "FRAMED")
                    ),
                )
                if signature in seen:
                    continue
                seen.add(signature)
            elif self._held(gesture):
                signature = (
                    gesture.mode,
                    gesture.label,
                    button.status,
                    button.threshold_ms,
                    *(
                        selected_operand(button, wire, argument, gesture.selection)
                        for wire in ("RAW", "FRAMED")
                        for argument in (1, 2, 3)
                    ),
                )
                if signature in seen:
                    continue
                seen.add(signature)
            prefix = self._mode_label(gesture.mode)
            meaning = gesture.label.removeprefix(prefix + " ") if prefix else gesture.label
            semantic = classify(meaning)
            kind = Kind.SAVE if save else Kind.PRESET if gesture.selection.hold else None
            if kind is None and prefix and semantic is not None and semantic.kind is Kind.MEMORY:
                # Mode-scoped memories are named preset tiles, not one shared slot.
                kind = Kind.PRESET
            if kind is None and meaning.lower().startswith("motor "):
                # Mode-scoped and combined actuators keep their own motor rows.
                kind = Kind.MOTOR
            spec = catalog_button(
                gesture.key,
                gesture.label,
                partial(_press, gesture=gesture),
                kind=kind,
                hold=ControllerHoldSpec(gesture.key, release_button_key=_RELEASE)
                if self._held(gesture)
                else None,
            )
            if spec and kind is Kind.MOTOR and spec.card.section is CardSection.UTILITY:
                part, _, direction = meaning.lower().rpartition(" ")
                if direction in ("up", "down"):
                    motor = f"baseremote_m{gesture.mode}_" + part.replace("+", "_and_").replace(
                        " ", "_"
                    )
                    spec = replace(
                        spec,
                        translation_key=f"{motor}_{direction}",
                        card=motor_card(motor, CardRole(direction)),
                    )
            specs.append(spec)
        if any(c.tag == "65" for c in self._controls):

            async def popup_toggle(controller: BedController) -> None:
                assert isinstance(controller, BaseRemoteController)
                with controller._transaction():
                    await controller.write_command(massage_popup("toggle"))

            specs.append(
                catalog_button("baseremote_massage_toggle", "Toggle massage", popup_toggle)
            )
        specs.append(
            ControllerButtonSpec(
                "baseremote_release",
                "Stop",
                lambda c: c.stop_all(),
                translation_key=_RELEASE,
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return unique_buttons(specs)

    def controller_button_available(self, key: str) -> bool:
        if key == "baseremote_release":
            return not self._group_only
        if key == "baseremote_massage_toggle":
            return any(c.tag == "65" for c in self._controls) and not self._group_only
        gesture = next((g for g in self._contexts() if g.key == key), None)
        if gesture is None:
            return False
        wire = self._session.wire if self._session else self._wire
        if self._group_only or wire == "RAW" and gesture.mode:
            return False
        button = self._button(gesture.node)
        argument = 3 if gesture.long else 1 if button.status == 1 or button.mem_special else 2
        return any(
            isinstance(selected_operand(button, candidate, argument, gesture.selection), bytes)
            for candidate in ((wire,) if wire else ("RAW", "FRAMED"))
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            g.key
            for g in self._contexts()
            if self._held(g) and self.controller_button_available(g.key)
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
            raise invalid("baseremote_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        gesture = next(g for g in self._contexts() if g.key == control)
        await self.async_gesture(gesture, duration_ms=duration_ms)

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        gesture = next(
            (
                g
                for g in self._contexts()
                if g.node == node and g.long == long and not g.selection.hold
            ),
            None,
        )
        if gesture is None:
            raise invalid("baseremote_control")
        await self.async_gesture(gesture, duration_ms=hold_ms)

    async def async_gesture(self, gesture: Gesture, *, duration_ms: int | None = None) -> None:
        if gesture not in self._contexts() or not self.controller_button_available(gesture.key):
            raise invalid("baseremote_control")
        button = self._button(gesture.node)
        cancel = self._coordinator.cancel_command
        context = current_command_context()
        if context and context.lease and not self._held(gesture):
            raise invalid("baseremote_control")
        mode, selection = gesture.mode, gesture.selection
        if button.mem_special:
            selection = replace(selection, armed=gesture.long)
        status = effective_status(button, self.layout, selection)
        with self._transaction() as session:
            self._worker.cancel()
            self._worker.total_ms = button.threshold_ms
            self._worker.set_count(
                0 if button.mem_special and gesture.long else button.threshold_ms
            )
            down = transition(button, self.layout, session.wire, selection, "DOWN", app=self.app)
            if down.local:
                raise invalid("baseremote_control")
            if down.payload is not RETAIN:
                self._worker.payload = down.payload
            if down.mode is not RETAIN:
                self._worker.mode = down.mode
            null_short = status == 3 and short_operand(button, session.wire) is None
            cleanup_ms = (
                HELD_RELEASE_MS
                if status == 1 or button.mem_special or null_short
                else TAP_RELEASE_MS
            )
            release_needed = not (null_short and session.wire == "RAW")
            if status == 3 and not gesture.long and not button.mem_special:
                up = transition(button, self.layout, session.wire, selection, "UP", app=self.app)
                if null_short:
                    self._worker.cancel()
                else:
                    self._worker.payload = up.payload if isinstance(up.payload, bytes) else None
                    self._worker.mode = 4
            deadline = (
                asyncio.get_running_loop().time()
                + (
                    duration_ms
                    if duration_ms is not None
                    else int(self._coordinator.entry.data.get("motor_pulse_count", 10))
                    * self._worker.tick_ms
                )
                / 1000
            )
            try:
                if cancel.is_set() and self._worker.mode != -1:
                    note_frame_skipped()
                while not cancel.is_set() and self._worker.mode != -1:
                    if (
                        self._worker.mode == 1
                        and not (context and context.lease)
                        and asyncio.get_running_loop().time() >= deadline
                    ):
                        break
                    for emission in self._worker.tick():
                        if emission.payload == RELEASE and emission.delay_ms:
                            # All cleanup is drained below and never counted as an action frame.
                            continue
                        if emission.payload is not None:
                            await self.write_command(control(emission.payload, session.wire, mode))
                    if self._worker.mode == -1:
                        break
                    delay = self._worker.tick_ms
                    if self._worker.mode == 1 and not (context and context.lease):
                        delay = min(
                            delay,
                            max(0, ceil((deadline - asyncio.get_running_loop().time()) * 1000)),
                        )
                    if not await self._wait(delay, cancel):
                        if self._worker.mode != -1:
                            note_frame_skipped()
                        break
            finally:
                self._worker.cancel()
                if release_needed:
                    await self._release(cleanup_ms, mode=mode)

    def validate_richmat_classic_request(self, request) -> None:
        raise invalid("baseremote_control")

    def validate_richmat_rise_request(self, request, *, live: bool = True) -> None:
        raise invalid("baseremote_control")

    def _alarm_codes(self) -> tuple[int, ...]:
        if self._group_only:
            return ()
        return tuple(
            dict.fromkeys(
                int(c.alarm_clock, 16)
                for c in self._controls
                if c.alarm_clock is not None and not c.excluded_short
            )
        )

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        codes = self._alarm_codes()
        if (
            self._group_only
            or not codes
            and not self._receive.alarm_capable
            and not any(c.status == 7 for c in self._controls)
        ):
            return None
        return AlarmCapability(
            wake_actions=tuple(dict.fromkeys(p.ALARM_ACTIONS[code] for code in codes)),
            massage_zones=tuple(
                zone
                for zone, code in (("both", 0x5D), ("head", 0x4C), ("feet", 0x4E))
                if code in codes or zone == "both" and {0x4C, 0x4E} <= set(codes)
            ),
            default_massage_zone=False,
            requires_wake_action=True,
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if self.alarm_capability is None:
            raise invalid("baseremote_alarm")
        if alarm.enabled:
            try:
                p.alarm_code(self._alarm_codes(), alarm.wake_action, alarm.massage_zone)
            except (ValueError, KeyError) as error:
                raise invalid("baseremote_alarm") from error

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        try:
            code = (
                p.alarm_code(
                    self._alarm_codes(),
                    alarm.wake_action or "none",
                    alarm.massage_zone,
                )
                if alarm.enabled
                else 0
            )
        except (ValueError, KeyError) as error:
            raise invalid("baseremote_alarm") from error
        with self._transaction():
            frames = countdown_alarm(alarm.minutes_until() if alarm.enabled else 0, code)
            for index, packet in enumerate(frames):
                try:
                    if self._coordinator.cancel_command.is_set():
                        note_frame_skipped()
                        return
                    await self.write_command(packet)
                    if not await self._wait(ALARM_SPACING_MS, self._coordinator.cancel_command):
                        if index + 1 < len(frames):
                            note_frame_skipped()
                        return
                except asyncio.CancelledError:
                    if index + 1 < len(frames):
                        note_frame_skipped()
                    raise

    def _group_transport(self) -> Transport:
        client = self.client
        service = (
            client.services.get_service("0000ffe0-0000-1000-8000-00805f9b34fb") if client else None
        )
        write = (
            service.get_characteristic("0000ffe2-0000-1000-8000-00805f9b34fb") if service else None
        )
        notify = (
            service.get_characteristic("0000ffe1-0000-1000-8000-00805f9b34fb") if service else None
        )
        if (
            client is None
            or write is None
            or notify is None
            or not set(write.properties) & {"write", "write-without-response"}
        ):
            raise invalid("baseremote_group")
        return Transport(client, write, notify, "RAW")

    async def async_group(
        self, name: str | None, *, before_write: Callable[[], bool] | None = None
    ) -> None:
        from ...codec.richmat import local_group

        try:
            packet = local_group(name)
        except ValueError as error:
            raise invalid("baseremote_group") from error
        group = self._group_transport()
        with self._transaction() as session:
            cancel = self._coordinator.cancel_command
            if cancel.is_set():
                note_frame_skipped()
                return
            extra_subscription = False
            operation_failed = False
            try:
                if group.notify is not session.notify and set(group.notify.properties) & {
                    "notify",
                    "indicate",
                }:

                    async def subscribe_group() -> None:
                        nonlocal extra_subscription
                        if self._session is not session or self.client is not group.client:
                            raise ConnectionError("The captured bed session ended before subscribe")
                        extra_subscription = True
                        result = await group.client.start_notify(
                            group.notify, lambda _sender, _data: None
                        )
                        extra_subscription = result is not False

                    await settled(subscribe_group())
                if cancel.is_set():
                    note_frame_skipped()
                    return
                await self._send_at(
                    packet, characteristic=group.write, cancel=cancel, before_write=before_write
                )
            except BaseException:
                operation_failed = True
                raise
            finally:

                async def close() -> None:
                    await asyncio.sleep(GROUP_SETTLE_MS / 1000)
                    async with self._coordinator.async_connection_operation_guard() as disconnect:
                        if self.client is None and not session.client.is_connected:
                            return
                        if self._session is not session or self.client is not session.client:
                            raise ConnectionError(
                                "The captured bed session changed before group cleanup"
                            )
                        if not session.client.is_connected:
                            return
                        try:
                            if extra_subscription:
                                await _stop_subscription(group.client, group.notify)
                        finally:
                            closed = await disconnect("baseremote_group")
                            if not closed or session.client.is_connected:
                                raise failed("baseremote_group_disconnect")

                try:
                    await settled(close())
                except Exception:
                    if not operation_failed:
                        raise
                    _LOGGER.debug(
                        "Failed to close Base Remote's failed group operation", exc_info=True
                    )

    async def stop_all(self) -> None:
        self._worker.cancel()
        if self._group_only or CONTROLLER_GESTURE_RELEASE.get():
            return
        with self._transaction() as session:
            for mode in (0,) if session.wire == "RAW" else self._modes:
                await self._release(HELD_RELEASE_MS, mode=mode)

    async def set_massage_timer(self, minutes: int) -> None:
        value = self._massage_timer_values.get(minutes)
        if value is None:
            raise invalid("baseremote_control")
        packet = massage_timer(self.layout, value) if isinstance(value, int) else massage_popup(value)
        # The bed reports no timer.
        with self._transaction(), self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self.write_command(packet)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        if self._receive.light_capable:

            async def timeout(controller: BedController, value: float) -> None:
                assert isinstance(controller, BaseRemoteController)
                if (
                    not controller._receive.light_capable
                    or not isfinite(value)
                    or value != int(value)
                    or not 0 <= value <= 300
                ):
                    raise invalid("baseremote_control")
                with controller._transaction(), controller.sent_state(LAMP_TIMEOUT(int(value))):
                    await controller.write_command(p.light_timeout(int(value)))

            specs.append(
                ControllerNumberSpec(
                    "baseremote_lamp_timeout",
                    "baseremote_lamp_timeout",
                    LAMP_TIMEOUT,
                    0,
                    300,
                    1,
                    timeout,
                    "s",
                    card=CARD_LIGHTING,
                )
            )
        if self._receive.aroma_capable:
            for opcode, key, name, limit, unit in (
                (0x1B, AROMA_ON_TIME, "aroma_on_time", 60, "min"),
                (0x1C, AROMA_INTERVAL, "aroma_interval", 60, "min"),
                (0x1D, AROMA_PAUSE, "aroma_pause", 12, "h"),
            ):

                async def aroma_time(
                    controller: BedController,
                    value: float,
                    *,
                    code: int = opcode,
                    state_key: StateKey[int | None] = key,
                    maximum: int = limit,
                ) -> None:
                    assert isinstance(controller, BaseRemoteController)
                    if (
                        not isfinite(value)
                        or value != int(value)
                        or not 1 <= value <= maximum
                        or not controller._receive.aroma_capable
                    ):
                        raise invalid("baseremote_control")
                    with controller._transaction(), controller.sent_state(state_key(int(value))):
                        await controller.write_command(aroma(code, int(value)))
                    await controller._wait(
                        SETTINGS_SPACING_MS, controller._coordinator.cancel_command
                    )

                specs.append(
                    ControllerNumberSpec(
                        "baseremote_" + name,
                        "baseremote_" + name,
                        key,
                        1,
                        limit,
                        1,
                        aroma_time,
                        unit,
                        card=CARD_UTILITY,
                        # A setting, not a dashboard control.
                        entity_registry_enabled_default=False,
                        entity_category=EntityCategory.CONFIG,
                    )
                )
        return tuple(specs)

    def _light_toggle(self) -> int | None:
        if self._group_only or len(self._modes) > 1:
            return None
        return next(
            (
                c.node
                for c in self._controls
                if not c.excluded_short
                and c.resource_keys.get("press_short")
                in ("@string/k_ubl_on_off", "@string/com_ubl_on_off")
                # Over Nordic UART a few layouts send another function from this control.
                and not self._nordic_label(c)
            ),
            None,
        )

    @property
    def supports_lights(self) -> bool:
        return self._light_toggle() is not None or self.supports_discrete_light_control

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._light_toggle() is not None

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    @property
    def supports_light_color_control(self) -> bool:
        return self._receive.light_capable and self.supports_lights

    @property
    def light_color_control_pending(self) -> bool:
        return self._color_light_identity and not self._receive.light_capable

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    async def lights_toggle(self) -> None:
        node = self._light_toggle()
        if node is None:
            raise invalid("baseremote_control")
        await self.execute_action(node)

    async def set_light_color(
        self, rgb_color: tuple[int, int, int], *, before_write: Callable[[], bool] | None = None
    ) -> None:
        if not self._receive.light_capable or any(
            type(v) is not int or not 0 <= v <= 255 for v in rgb_color
        ):
            raise invalid("baseremote_control")
        from ...codec.richmat import rgb

        with self._transaction(), self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color)):
            await self._send_at(
                rgb(*rgb_color), cancel=self._coordinator.cancel_command, before_write=before_write
            )
        await self._wait(SETTINGS_SPACING_MS, self._coordinator.cancel_command)
