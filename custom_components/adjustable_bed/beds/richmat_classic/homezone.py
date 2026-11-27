"""Home Zone's frozen catalog on the shared Richmat gesture and session runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...alarm import AlarmRequest
from ...codec import richmat as codec
from ...const import CONF_RICHMAT_CLASSIC_THIRD_SERVICE
from ...profiles import homezone as profile
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import CONTROLLER_GESTURE_RELEASE
from ..entity_specs import ControllerButtonSpec
from . import resource_protocol as p
from . import rise
from .caller import Selection
from .controller import (
    APP,
    LAYOUT,
    PREFERENCES,
    REJECTION,
    STATE,
    STATUS,
    RichmatClassicController,
    control_node,
)
from .profiles import Control
from .protocol import (
    ALARM_SPACING_MS,
    INITIALIZE,
    SETTINGS_SPACING_MS,
    SLIDER_MINUTES,
    STARTUP_MS,
    alarm,
    aroma,
    massage_popup,
    massage_timer,
    worker_interval,
)
from .receive import MalformedFrame, ReceiveState
from .resource_controller import LAMP_TIMEOUT, ResourceBedController
from .resource_receive import ResourceReceiveState
from .transport import select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


class HomeZoneReceive(ResourceReceiveState):
    """Source-ordered sum parsing, bounded to the current physical link."""

    def feed(
        self,
        data: bytes,
        *,
        app: str,
        layout: str,
        desk_bound: bool = False,
        table_controls_bound: bool = False,
    ) -> None:
        # A host memory bound, not an inferred protocol length.
        if len(self.buffer) + len(data) * 2 > 512:
            self.buffer = ""
            return
        try:
            ReceiveState.feed(
                self, data, app=app, layout=layout, desk_bound=False, table_controls_bound=False
            )
        except MalformedFrame:
            self.buffer = ""
        if self.value_event == "6e0e00037f":
            self.light_on_seen = True
        elif self.value_event == "6e0e00017d":
            self.light_off_seen = True
        # Alarm ACKs are events without request correlation, not schedule state.
        self.alarm_enabled = None


class HomeZoneController(ResourceBedController):
    """App-specific startup, parser and utilities; shared resource gestures."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, device_name: str | None = None
    ) -> None:
        if (
            str(coordinator.entry.data.get("product_type", "")).strip().upper()
            in profile.EXCLUDED_LAYOUTS
        ):
            raise ValueError("Choose a Home Zone bed control layout")
        RichmatClassicController.__init__(
            self, coordinator, app=profile.APP, device_name=device_name
        )
        self.app_profile = profile.PROFILE
        self._receive = HomeZoneReceive()
        self._preferences = {}
        self._deadline = None
        self._lamp_timeout = self._massage_timer = None

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        # Losing this link's capability proof must not delete a customized row.
        return super().retained_entity_keys | {
            ("number", "controller_number_richmat_resource_lamp_timeout")
        }

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        if self.settings_transport is None or not self._receive.light_capable:
            return ("controller_number_richmat_resource_lamp_timeout",)
        return ()

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # Never retain an armed save, capability reply, setting or phone draft.
        return {"wire": self._wire} if self._wire else {}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._restore_wire(state)
        self._selection = Selection()

    def _publish(self) -> None:
        from .controller import _selection_key

        self.forward_controller_state_updates(
            STATUS("ready" if self._session else "disconnected"),
            APP(self.app),
            LAYOUT(self.layout),
            STATE(
                {
                    "alarm_available": self._receive.alarm_capable,
                    "light_available": self._receive.light_capable,
                    "aroma_available": self._receive.aroma_capable,
                }
            ),
            PREFERENCES(dict(self._preferences)),
            REJECTION(self._rejection),
            LAMP_TIMEOUT(self._lamp_timeout),
            MASSAGE_TIMER_MINUTES(
                next((m for m, stop in SLIDER_MINUTES.items() if stop == self._massage_timer), None)
            ),
            *(
                _selection_key(k)(v)
                for k, v in {
                    "mode": str(self._mode),
                    "program": "armed" if self._selection.armed else "recall",
                    "hold": "hold" if self._selection.hold else "release",
                    "head_foot": "head" if self._selection.head else "foot",
                }.items()
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {**super().protocol_diagnostics, "aroma_reply_seen": self._receive.aroma_capable}

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
        self._worker.cancel()
        name = self._device_name or self._coordinator.entry.data.get("ble_device_name")
        self._worker.set_interval(worker_interval(name, session.wire, rise=True))
        self._session, self._wire = session, session.wire
        self._receive = HomeZoneReceive()
        self._lamp_timeout = self._massage_timer = None
        self._notifications_started = False
        try:
            with self._transaction():
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
                if session.wire == "FRAMED":
                    if not await self._wait(STARTUP_MS, self._coordinator.cancel_command):
                        return
                    await self.write_command(INITIALIZE)
        except BaseException:
            self._session = None
            raise
        self._publish()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._receive = HomeZoneReceive()
        self._selection = Selection()
        self._mode = 0
        self._publish()

    async def stop_all(self) -> None:
        self._worker.cancel()
        if CONTROLLER_GESTURE_RELEASE.get() or self._session is None:
            return
        with self._transaction():
            mode = self._mode
            await self._release(self.app_profile.held_release_ms, mode=mode)

    @staticmethod
    def _hidden(button: Control) -> bool:
        # These widgets have click listeners, not BLE touch actions.
        return button.view_id in ("btnRelease", "btnHold") or RichmatClassicController._hidden(
            button
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # A status=2 control with only press_long never queues that operand.
        # Keep it in the frozen catalog without exposing an unusable button.
        return tuple(
            spec
            for spec in super().controller_button_specs
            if spec.key == "richmat_classic_release"
            or (button := self._button(control_node(spec.key))).status != 2
            or button.short is not None
            or button.short_old is not None
        )

    def _alarm_request(self, alarm: AlarmRequest) -> p.Request:
        return replace(super()._alarm_request(alarm), native_alarm=alarm)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)

    def _alarm_actions(self) -> dict[str, int]:
        return {
            f"node_{c.node}": int(c.alarm_clock, 16)
            for c in self._controls
            if c.rich_button and c.alarm_clock is not None
        }

    @property
    def supports_massage_timer(self) -> bool:
        return self.layout in ("D1RM", "D9RM") or any(c.tag == "65" for c in self._controls)

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage_timer else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return self.layout in ("D1RM", "D9RM")

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage_timer or minutes not in SLIDER_MINUTES:
            raise ValueError("Choose a massage timer offered by this layout")
        if self.layout in ("D1RM", "D9RM"):
            await self.execute_request(p.Request("massage_timer", progress=SLIDER_MINUTES[minutes]))
        else:
            if not minutes:
                raise ValueError("This timer popup has a toggle, not a discrete off command")
            await self.execute_request(
                p.Request("massage_popup", popup={10: "15", 20: "30", 30: "45"}[minutes])
            )

    def validate_request(self, request: p.Request, *, live: bool = True) -> None:
        op = request.operation
        if op in ("bed_command",):
            raise ValueError("Use this layout's labelled bed controls")
        if op == "alarm":
            if request.native_alarm is None:
                raise ValueError("Use the shared Set alarm action")
            rise.alarm_action(self._alarm_actions(), request.actions)
            if request.when and (request.when.second or request.when.microsecond):
                raise ValueError("Choose an alarm time with minute precision")
        elif op == "lamp_timeout":
            if type(request.seconds) is not int or not 0 <= request.seconds <= 300:
                raise ValueError("Choose 0 to 300 seconds")
            if live and (self.settings_transport is None or not self._receive.light_capable):
                raise ValueError("The bed has not reported lighting support")
        elif op == "aroma":
            if (
                request.aroma_times is None
                or len(request.aroma_times) != 3
                or any(
                    type(v) is not int or not 1 <= v <= limit
                    for v, limit in zip(request.aroma_times, (60, 60, 12), strict=True)
                )
            ):
                raise ValueError(
                    "Aroma times are 1 to 60 minutes, 1 to 60 minutes, and 1 to 12 hours"
                )
            if live and not self._receive.aroma_capable:
                raise ValueError("The bed has not reported aroma support")
        elif op == "massage_popup":
            if not any(c.tag == "65" for c in self._controls) or request.popup not in (
                "15",
                "30",
                "45",
                "toggle",
            ):
                raise ValueError("Choose a massage timer popup offered by this layout")
        elif op == "massage_timer":
            if self.layout not in ("D1RM", "D9RM") or request.progress is None:
                raise ValueError("This layout has no massage slider")
            massage_timer(self.layout, request.progress)
        else:
            super().validate_request(request, live=live)

    async def execute_request(self, request: p.Request) -> None:
        self.validate_request(request)
        if request.operation not in ("alarm", "aroma", "lamp_timeout", "massage_popup"):
            await super().execute_request(request)
            return
        with self._transaction() as session:
            if request.operation == "alarm":
                # The app's combined operand uses the shared countdown encoder.
                action = rise.alarm_action(self._alarm_actions(), request.actions)
                assert request.native_alarm is not None
                delay = min(1440, request.native_alarm.minutes_until(dt_util.now()))
                frames, spacing = alarm(delay, action), ALARM_SPACING_MS
            elif request.operation == "aroma":
                assert request.aroma_times is not None
                frames = tuple(
                    aroma(op, v)
                    for op, v in zip((0x1B, 0x1C, 0x1D), request.aroma_times, strict=True)
                )
                spacing = SETTINGS_SPACING_MS
            elif request.operation == "lamp_timeout":
                assert request.seconds is not None
                frames, spacing = (codec.light_timer(request.seconds >> 8, request.seconds),), 0
            else:
                assert request.popup is not None
                frames, spacing = (massage_popup(request.popup),), 0
            cancel = self._coordinator.cancel_command
            for packet in frames:
                if cancel.is_set():
                    return
                await self.write_command(packet)
                if spacing and not await self._wait(spacing, cancel):
                    return
            if self._session is session and not cancel.is_set():
                if request.operation == "lamp_timeout":
                    self._lamp_timeout = request.seconds
                if request.operation == "massage_popup":
                    self._massage_timer = {"15": 2, "30": 3, "45": 5}.get(request.popup or "")
                self._publish()
