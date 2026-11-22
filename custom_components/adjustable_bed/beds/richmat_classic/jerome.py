"""Jerome's power base: layout-bound controls and one owned BLE transaction."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, replace
from functools import partial
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_LIGHTING, CARD_MASSAGE, CARD_UTILITY
from ...command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ...const import (
    CONF_MOTOR_PULSE_COUNT,
    CONF_RICHMAT_CLASSIC_THIRD_SERVICE,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from ...controller_state import StateKey
from ...errors import invalid
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles.jerome2 import (
    ALARM_CODES,
    COMBINATIONS,
    EXCLUDED_LAYOUTS,
    SIDE_LAYOUTS,
    TIMER_PROGRESS,
)
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, require_controller
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from . import protocol as p
from .caller import Selection, selected_operand, short_operand
from .controller import APP, LAYOUT, PREFERENCES, REJECTION, STATE, STATUS, RichmatClassicController
from .jerome_controls import Action, actions, inverse_pairs, long_actions
from .receive import MalformedFrame, ReceiveState
from .requests import Request as ClassicRequest
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_SCOPE: ContextVar[tuple[BedController, Transport] | None] = ContextVar(
    "jerome_session", default=None
)
LIGHT_SECONDS: Final = StateKey[int | None]("jerome_light_seconds")
INTENSITY: Final = StateKey[int | None]("jerome_massage_intensity")
AROMA_KEYS: Final = tuple(StateKey[int | None](f"jerome_aroma_{i}") for i in range(3))
MASSAGE: Final = StateKey[bool | None]("jerome_massage")
SYNC: Final = StateKey[bool | None]("jerome_sync")


async def _press(controller: BedController, key: str) -> None:
    await require_controller(controller, JeromeController).press(key)


class JeromeController(RichmatClassicController):
    """Reuse the literal-verified family catalog, codec and source getters.

    HA owns the admitted session, side and gesture, instead of retaining Android's
    queued intent or long-fired latch across commands. No old packet follows a reconnect.
    """

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str | None = None,
        device_name: str | None = None,
        capability_snapshot: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(coordinator, app=app or "jerome2", device_name=device_name)
        if self.layout in EXCLUDED_LAYOUTS:
            raise invalid("jerome_layout")
        self._preferences = {}
        self._light_on: bool | None = None
        saved = capability_snapshot or {}
        self._known_light = saved.get("layout") == self.layout and saved.get("light") is True
        self._known_aroma = saved.get("layout") == self.layout and saved.get("aroma") is True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        # The raw path does not encode curMode; it cannot route Left/Right.
        return self.layout in SIDE_LAYOUTS and self._wire == "FRAMED"

    @property
    def _actions(self) -> dict[str, Action]:
        return actions(self.layout, self._resolved_wire == "RAW")

    @property
    def _pairs(self) -> dict[str, tuple[str, str]]:
        return inverse_pairs(self.layout, self._resolved_wire == "RAW")

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # Only the bed's command format is kept: it names the controls before
        # the first connection.
        return {"wire": self._wire} if self._wire else {}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)
        # Phone screen history cannot add alarm actions or establish bed state.
        self._preferences = {}

    @contextmanager
    def _transaction(self) -> Iterator[Transport]:
        session = self._live()
        token = _SCOPE.set((self, session))
        try:
            yield session
        finally:
            _SCOPE.reset(token)

    def _live(self) -> Transport:
        scope = _SCOPE.get()
        session = scope[1] if scope is not None and scope[0] is self else self._session
        if (
            session is None
            or self._coordinator.controller is not self
            or self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            raise ConnectionError("The admitted bed session has ended")
        return session

    async def _send(self, packet: bytes, cancel: asyncio.Event | None = None) -> None:
        # A waiting writer rechecks cancellation under the physical wire lock.
        async with self.ble_lock:

            async def write() -> None:
                session = self._live()
                if cancel is not None and cancel.is_set():
                    note_frame_skipped()
                    return
                self._record_command_trace(
                    session.write.uuid,
                    packet,
                    response=session.response,
                    characteristic=session.write,
                )
                await session.client.write_gatt_char(
                    session.write, packet, response=session.response
                )
                if cancel is None:
                    note_write_not_counted()
                else:
                    note_frame_written(cancel)

            await settled(write())

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            STATUS("ready" if self._session else "disconnected"),
            APP(self.app),
            LAYOUT(self.layout),
            STATE({**asdict(self._receive), "menu": sorted(self._receive.menu)}),
            PREFERENCES(dict(self._preferences)),
            REJECTION(self._rejection),
        )

    def _notification(
        self, session: Transport, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self._coordinator.controller is not self
            or self.client is not session.client
            or not session.client.is_connected
        ):
            return
        self.forward_raw_notification(session.notify.uuid, bytes(data))
        try:
            self._receive.feed(
                bytes(data),
                app="jerome2",
                layout=self.layout,
                desk_bound=False,
                table_controls_bound=False,
            )
            self._rejection = None
        except MalformedFrame as err:
            self._rejection = str(err)
        if self._receive.value_event in ("6e0e00017d", "6e0e00037f"):
            self._light_on = self._receive.value_event == "6e0e00037f"
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(self._light_on))
        self._known_light |= self._receive.light_capable
        self._known_aroma |= self._receive.aroma_capable
        self._publish()

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True, after_operations=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {"layout": self.layout, "light": self._known_light, "aroma": self._known_aroma}

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        session.persist_capability_snapshot()

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
        if not isinstance(name, str) or len(name.strip()) < 4:
            raise invalid("jerome_device_name")
        self._worker.set_interval(p.worker_interval(name, session.wire, rise=True))
        self._session, self._wire = session, session.wire
        self._worker.cancel()
        self._receive = ReceiveState()
        self._notifications_started = False
        try:
            with self._transaction():
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
                if session.wire == "FRAMED" and self._notifications_started:
                    await asyncio.sleep(p.STARTUP_MS / 1000)
                    await self._send(p.INITIALIZE)
                # Settings entry is a lifecycle probe, never a plumbing entity.
                await self._probe()
        except BaseException:
            self._session = None
            raise
        self._publish()

    async def _probe(self) -> None:
        for frame in ([p.ALARM_QUERY] if self._alarm_actions() else []) + [
            p.LAMP_QUERY,
            p.AROMA_QUERY,
        ]:
            await self._send(frame)
            await asyncio.sleep(p.QUERY_SPACING_MS / 1000)

    def on_disconnect(self) -> None:
        self._session = None
        self._receive = ReceiveState()
        self._notifications_started = False
        self._worker.cancel()
        self._preferences = {}
        self._light_on = None
        self.forward_controller_state_updates(
            LIGHT_SECONDS(None),
            INTENSITY(None),
            MASSAGE(None),
            SYNC(None),
            *(key(None) for key in AROMA_KEYS),
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
        )
        if self._coordinator.controller is self:
            self._coordinator.cache_capability_controller()
        self._publish()

    def _mode_for(self, mode: int | None = None) -> int:
        side = self.command_side
        if side in (SIDE_LEFT, SIDE_RIGHT):
            if not self.supports_single_address_pairing or mode is not None:
                raise invalid("jerome_mode")
            return int(side == SIDE_RIGHT)
        if mode is not None and self.layout in SIDE_LAYOUTS:
            raise invalid("jerome_mode")
        selected = 0 if mode is None else mode
        if selected not in self._model.modes or selected and self._live().wire == "RAW":
            raise invalid("jerome_mode")
        return selected

    def _operand(self, action: Action, wire: p.Wire) -> bytes | None:
        button = self._button(action.node)
        selection = Selection(
            press_flag=action.flag, armed=action.long_press and button.mem_special
        )
        value = selected_operand(
            button, wire, 3 if action.long_press else 1 if action.keep else 2, selection
        )
        return value if isinstance(value, bytes) else None

    def _action_available(self, action: Action) -> bool:
        wires = (self._wire,) if self._wire is not None else ("RAW", "FRAMED")
        return all(self._operand(action, wire) is not None for wire in wires)

    def validate_action(
        self,
        key: str,
        *,
        keep: bool = False,
        mode: int | None = None,
        confirm: bool = False,
        long_press: bool = False,
    ) -> Action:
        action = (long_actions(self.layout) if long_press else self._actions).get(key)
        if action is None or not self._action_available(action):
            raise invalid("jerome_action")
        button = self._button(action.node)
        if action.long_press or action.name.startswith("Save "):
            if not confirm:
                raise invalid("jerome_confirm")
            if keep:
                raise invalid("jerome_hold")
        if keep and not (
            action.keep or button.hold_affected and not button.view_id.endswith("Long")
        ):
            raise invalid("jerome_hold")
        if mode is not None and (self.layout in SIDE_LAYOUTS or mode not in self._model.modes):
            raise invalid("jerome_mode")
        if self._session is not None and mode is not None and mode and self._session.wire == "RAW":
            raise invalid("jerome_mode")
        if self._session is not None:
            self._mode_for(mode)
        return action

    def _require_physical_settings(self) -> None:
        # Direct feature frames have no curMode or side field. Do not route a
        # child's request as if it were a side-specific physical setting.
        if self.command_side in (SIDE_LEFT, SIDE_RIGHT):
            raise invalid("jerome_feature_scope")

    async def press(
        self,
        key: str,
        *,
        keep: bool = False,
        mode: int | None = None,
        confirm: bool = True,
        duration_ms: int | None = None,
        long_press: bool = False,
    ) -> None:
        action = self.validate_action(
            key, keep=keep, mode=mode, confirm=confirm, long_press=long_press
        )
        button = self._button(action.node)
        context = current_command_context()
        leased = context is not None and context.lease is not None
        kept = action.keep or keep or leased and button.hold_affected
        if leased and (action.long_press or not kept):
            raise invalid("jerome_hold")
        with self._transaction() as session:
            target = self._mode_for(mode)
            selection = Selection(
                press_flag=action.flag, armed=action.long_press and button.mem_special
            )
            argument = 3 if action.long_press else 1 if kept else 2
            payload = selected_operand(button, session.wire, argument, selection)
            if not isinstance(payload, bytes):
                raise invalid("jerome_action")
            cancel = self._coordinator.cancel_command
            delay = (
                p.HELD_RELEASE_MS
                if kept
                or button.mem_special
                or action.long_press
                and short_operand(button, session.wire) is None
                else p.TAP_RELEASE_MS
            )
            # A raw long-only widget defines no END. Ending its pending refresh
            # is the cleanup; framed null-short UP has a 50 ms END instead.
            release_defined = not (
                session.wire == "RAW"
                and action.long_press
                and short_operand(button, session.wire) is None
            )
            self._worker.cancel()
            duration = (
                duration_ms
                if duration_ms is not None
                else int(self._coordinator.entry.data.get(CONF_MOTOR_PULSE_COUNT, 10))
                * self._worker.tick_ms
            )
            deadline = monotonic() + duration / 1000
            try:
                if action.long_press and not button.mem_special:
                    threshold = button.threshold_ms // self._worker.tick_ms * self._worker.tick_ms
                    if not await self._wait(threshold, cancel):
                        note_frame_skipped()
                        return
                wrote = False
                if cancel.is_set():
                    note_frame_skipped()
                while not cancel.is_set():
                    if wrote and kept and not leased and monotonic() >= deadline:
                        break
                    await self._send(p.control(payload, session.wire, target), cancel)
                    wrote = True
                    if not kept:
                        break
                    remaining = ceil((deadline - monotonic()) * 1000)
                    if not leased and remaining <= 0:
                        break
                    if not await self._wait(
                        self._worker.tick_ms if leased else min(self._worker.tick_ms, remaining),
                        cancel,
                    ):
                        if leased or remaining > self._worker.tick_ms:
                            note_frame_skipped()
                        break
            finally:
                self._worker.cancel()
                if release_defined:
                    await self._release(delay, mode=target)

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        action = next(
            (
                key
                for key, value in self._actions.items()
                if value.node == node and value.long_press == long
            ),
            None,
        )
        if action is None:
            raise invalid("jerome_action")
        await self.press(action, duration_ms=hold_ms)

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        session = self._live()
        target = self._mode_for() if mode is None else mode

        async def cleanup() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if (
                self._session is session
                and self.client is session.client
                and session.client.is_connected
            ):
                await self._send(p.release(session.wire, target))

        await settled(cleanup())

    async def stop_all(self) -> None:
        self._worker.cancel()
        if not CONTROLLER_GESTURE_RELEASE.get():
            with self._transaction():
                await self._release(p.HELD_RELEASE_MS)

    @property
    def _massage_timer_values(self) -> dict[int, str]:
        """The massage timer choices this layout sends, by their minutes (0 is off)."""
        if self.layout == "Y6RM":
            # The popup's on/off row is a toggle, never an idempotent off.
            return {15: "15_minutes", 30: "30_minutes", 45: "45_minutes"}
        if self.layout in ("D1RM", "D9RM"):
            return {0 if value == "off" else int(value.split("_")[0]): value for value in TIMER_PROGRESS}
        return {}

    @property
    def supports_massage_timer(self) -> bool:
        # Its frame has no side field, so one-address combined-bed sides have none.
        return bool(self._massage_timer_values) and self.command_side not in (SIDE_LEFT, SIDE_RIGHT)

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

    async def set_massage_timer(self, minutes: int) -> None:
        value = self._massage_timer_values.get(minutes)
        if value is None:
            raise invalid("jerome_timer")
        self._require_physical_settings()
        if self.layout == "Y6RM":
            frame = p.massage_popup(value.removesuffix("_minutes"))
        else:
            frame = p.massage_timer(self.layout, TIMER_PROGRESS[value])
        # The bed reports no timer.
        with self._transaction(), self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self._send(frame, self._coordinator.cancel_command)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.command_side in (SIDE_LEFT, SIDE_RIGHT):
            return ()
        result = []
        if self.layout == "R2RM":

            async def intensity(controller: BedController, value: float) -> None:
                ctrl = require_controller(controller, JeromeController)
                ctrl._require_physical_settings()
                with ctrl.sent_state(INTENSITY(int(value))):
                    await ctrl.press(f"massage_intensity_{int(value)}")

            result.append(
                ControllerNumberSpec(
                    "jerome_massage_intensity",
                    "jerome_massage_intensity",
                    INTENSITY,
                    1,
                    3,
                    1,
                    intensity,
                    card=CARD_MASSAGE,
                )
            )
        if self._known_light or self._receive.light_capable:

            async def light_timeout(controller: BedController, value: float) -> None:
                ctrl = require_controller(controller, JeromeController)
                ctrl._require_physical_settings()
                if not ctrl._receive.light_capable:
                    raise invalid("jerome_capability")
                with ctrl._transaction(), ctrl.sent_state(LIGHT_SECONDS(int(value))):
                    await ctrl._send(
                        p.direct(0x0B, int(value) >> 8, int(value)),
                        ctrl._coordinator.cancel_command,
                    )

            result.append(
                ControllerNumberSpec(
                    "jerome_light_seconds",
                    "jerome_light_seconds",
                    LIGHT_SECONDS,
                    0,
                    300,
                    1,
                    light_timeout,
                    "s",
                    card=CARD_LIGHTING,
                )
            )
        if self._known_aroma or self._receive.aroma_capable:
            for index, maximum in enumerate((60, 60, 12)):

                async def aroma_time(
                    controller: BedController, value: float, *, index: int = index
                ) -> None:
                    ctrl = require_controller(controller, JeromeController)
                    ctrl._require_physical_settings()
                    if not ctrl._receive.aroma_capable:
                        raise invalid("jerome_capability")
                    with ctrl._transaction(), ctrl.sent_state(AROMA_KEYS[index](int(value))):
                        await ctrl._send(
                            p.aroma(0x1B + index, int(value)), ctrl._coordinator.cancel_command
                        )
                        await ctrl._wait(p.SETTINGS_SPACING_MS, ctrl._coordinator.cancel_command)

                result.append(
                    ControllerNumberSpec(
                        f"jerome_aroma_{index}",
                        f"jerome_aroma_{index}",
                        AROMA_KEYS[index],
                        1,
                        maximum,
                        1,
                        aroma_time,
                        "h" if index == 2 else "min",
                        card=CARD_UTILITY,
                        # A setting, not a dashboard control.
                        entity_registry_enabled_default=False,
                        entity_category=EntityCategory.CONFIG,
                    )
                )
        return tuple(result)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        result = []
        for key, (on, off) in self._pairs.items():

            async def switch(
                controller: BedController,
                enabled: bool,
                *,
                on: str = on,
                off: str = off,
                key: str = key,
            ) -> None:
                ctrl = require_controller(controller, JeromeController)
                state_key = MASSAGE if key == "massage" else SYNC
                with ctrl.sent_state(state_key(enabled)):
                    await ctrl.press(on if enabled else off)

            result.append(
                ControllerSwitchSpec(
                    f"jerome_{key}",
                    f"jerome_{key}",
                    switch,
                    MASSAGE if key == "massage" else SYNC,
                    assumed_state=True,
                    card=CARD_MASSAGE if key == "massage" else CARD_UTILITY,
                )
            )
        return tuple(result)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        paired = {key for pair in self._pairs.values() for key in pair}
        result: list[ControllerButtonSpec | None] = []
        for key, action in self._actions.items():
            if not self._action_available(action):
                continue
            if self.layout == "R2RM" and key in (
                "massage_intensity_1",
                "massage_intensity_2",
                "massage_intensity_3",
            ):
                continue
            if (
                key in paired
                or key in ("underbed_light_on", "underbed_light_off")
                and self.supports_discrete_light_control
            ):
                continue
            if key == "toggle_underbed_light" and self.supports_light_state_feedback:
                continue
            hold = None
            if (
                (action.keep or self._button(action.node).hold_affected)
                and not action.long_press
                and not action.name.startswith("Save ")
            ):
                hold = ControllerHoldSpec(f"jerome_{key}", release_button_key="jerome_release")
            spec = catalog_button(f"jerome_{key}", action.name, partial(_press, key=key), hold=hold)
            if spec is not None and action.long_press:
                spec = replace(spec, requires_confirmation=spec.card.section != "memory", hold=None)
            result.append(spec)
        if self.layout == "Y6RM":

            async def toggle(controller: BedController) -> None:
                ctrl = require_controller(controller, JeromeController)
                with ctrl._transaction():
                    await ctrl._send(p.massage_popup("toggle"), ctrl._coordinator.cancel_command)

            result.append(
                catalog_button("jerome_toggle_massage", "Toggle massage", toggle, kind=Kind.MASSAGE)
            )
        result.append(
            ControllerButtonSpec(
                "jerome_release",
                "Release",
                lambda c: c.stop_all(),
                translation_key="richmat_classic_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return unique_buttons(result)

    def controller_button_available(self, key: str) -> bool:
        return any(spec.key == key for spec in self.controller_button_specs)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(spec.hold.control for spec in self.controller_button_specs if spec.hold)

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
            raise invalid("jerome_hold")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.press(control.removeprefix("jerome_"), keep=True, duration_ms=duration_ms)

    def _alarm_actions(self) -> dict[str, int]:
        return {f"node_{c.node}": int(c.alarm_clock, 16) for c in self._controls if c.alarm_clock}

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if self.command_side in (SIDE_LEFT, SIDE_RIGHT):
            return None
        available = set(self._alarm_actions().values())
        if not available and not self._receive.alarm_capable:
            return None
        return AlarmCapability(
            wake_actions=(
                "none",
                *(name for name, code in ALARM_CODES.items() if code in available),
            ),
            massage=bool(available & {0x5D, 0x4C, 0x4E}),
            massage_zones=tuple(
                name
                for name, code in (("both", 0x5D), ("head", 0x4C), ("feet", 0x4E))
                if code in available or name == "both" and {0x4C, 0x4E} <= available
            ),
            confirm_actions=frozenset(
                name
                for name in ("memory_1", "memory_2", "memory_3")
                if ALARM_CODES[name] in available
            ),
        )

    def _alarm_code(self, request: AlarmRequest) -> int:
        available = set(self._alarm_actions().values())
        if request.sound != "none":
            raise invalid("jerome_alarm")
        bed = ALARM_CODES.get(request.wake_action)
        massage = (
            {"both": 0x5D, "head": 0x4C, "feet": 0x4E}.get(request.massage_zone or "")
            if request.massage
            else None
        )
        if (
            bed is not None
            and bed not in available
            or massage is not None
            and massage not in available
            and not (massage == 0x5D and {0x4C, 0x4E} <= available)
        ):
            raise invalid("jerome_alarm")
        if massage is None:
            if bed is None:
                raise invalid("jerome_alarm")
            return bed
        if bed is None:
            return massage
        if bed not in COMBINATIONS:
            raise invalid("jerome_alarm")
        return COMBINATIONS[bed][(0x5D, 0x4C, 0x4E).index(massage)]

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self._require_physical_settings()
        if alarm.enabled:
            self._alarm_code(alarm)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self._require_physical_settings()
        request = alarm
        code = self._alarm_code(request) if request.enabled else 0
        delay = min(1440, request.minutes_until(dt_util.now())) if request.enabled else 0
        with self._transaction():
            frames = p.alarm(delay, code)
            for index, frame in enumerate(frames):
                if self._coordinator.cancel_command.is_set():
                    note_frame_skipped()
                    return
                await self._send(frame, self._coordinator.cancel_command)
                if not await self._wait(p.ALARM_SPACING_MS, self._coordinator.cancel_command):
                    if index + 1 < len(frames):
                        note_frame_skipped()
                    return

    @property
    def supports_light_state_feedback(self) -> bool:
        return (
            self.command_side not in (SIDE_LEFT, SIDE_RIGHT)
            and (self._known_light or self._receive.light_capable)
            and "toggle_underbed_light" in self._actions
            and self._action_available(self._actions["toggle_underbed_light"])
        )

    @property
    def supports_discrete_light_control(self) -> bool:
        return "underbed_light_on" in self._actions and "underbed_light_off" in self._actions

    @property
    def supports_explicit_light_on_control(self) -> bool:
        # lights_on resolves a toggle against fresh session state.
        return self.supports_discrete_light_control or self.supports_light_state_feedback

    @property
    def supports_light_toggle_control(self) -> bool:
        # The catalog owns the toggle button; the generic entity owns real state.
        return False

    @property
    def supports_light_color_control(self) -> bool:
        return (self._known_light or self._receive.light_capable) and (
            self.supports_light_state_feedback or self.supports_discrete_light_control
        )

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    @property
    def light_state_is_assumed(self) -> bool:
        return self.supports_discrete_light_control and not self._receive.light_capable

    async def lights_on(self) -> None:
        await self._set_light_power(True)

    async def lights_off(self) -> None:
        await self._set_light_power(False)

    async def _set_light_power(self, enabled: bool) -> None:
        if not self.supports_discrete_light_control and self._light_on is None:
            raise invalid("jerome_capability")
        if self._light_on is enabled:
            return

        def show(delivery: Delivery) -> None:
            if delivery is not Delivery.NONE:
                self._light_on = enabled if delivery is Delivery.SENT else None

        with delivered(show), self.sent_state(UNDER_BED_LIGHTS_ON(enabled)):
            await self.press(
                ("underbed_light_on" if enabled else "underbed_light_off")
                if self.supports_discrete_light_control
                else "toggle_underbed_light"
            )

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        self.validate_utility("light_color", color=rgb_color)
        with self._transaction(), self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color)):
            await self._send(p.rgb(*rgb_color), self._coordinator.cancel_command)
            await self._wait(p.SETTINGS_SPACING_MS, self._coordinator.cancel_command)

    def validate_utility(
        self,
        action: str,
        color: tuple[int, int, int] | None = None,
        aroma: tuple[int, int, int] | None = None,
    ) -> None:
        self._require_physical_settings()
        if action == "light_color":
            if not self._receive.light_capable:
                raise invalid("jerome_capability")
            if color is None or any(type(v) is not int or not 0 <= v <= 255 for v in color):
                raise invalid("jerome_color")
        elif action == "aroma_settings":
            if not self._receive.aroma_capable:
                raise invalid("jerome_capability")
            if aroma is None or any(
                type(v) is not int or not 1 <= v <= limit
                for v, limit in zip(aroma, (60, 60, 12), strict=True)
            ):
                raise invalid("jerome_aroma")
        else:
            raise invalid("jerome_action")

    async def configure_aroma(self, values: tuple[int, int, int]) -> None:
        self.validate_utility("aroma_settings", aroma=values)
        with self._transaction():
            for index, value in enumerate(values):
                with self.sent_state(AROMA_KEYS[index](value)):
                    await self._send(p.aroma(0x1B + index, value), self._coordinator.cancel_command)
                if index + 1 < len(values):
                    if not await self._wait(
                        p.SETTINGS_SPACING_MS, self._coordinator.cancel_command
                    ):
                        note_frame_skipped()
                        return

    def validate_richmat_classic_request(self, request: ClassicRequest) -> None:
        raise invalid("jerome_action")
