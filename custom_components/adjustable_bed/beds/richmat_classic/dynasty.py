"""Dynasty DM9000 1.0.4: catalog behavior on the shared Richmat session.

Accepted row189 E4/E7/E10/E12/E19. No hardware mapping is inferred.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from datetime import time
from functools import partial
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped
from ...controller_state import StateKey
from ...errors import invalid
from ..base import BedController
from ..cancellation import cancellable, settled
from ..entity_specs import ControllerButtonSpec, ControllerNumberSpec, ControllerStateSensorSpec
from . import protocol as p
from .controller import LAMP_SECONDS
from .profiles import load_catalog
from .requests import Request
from .resource_protocol import alarm_action
from .session import SessionController
from .transport import Transport, select

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

# Preset: (head-and-foot massage, head massage, foot massage).
ALARM_COMBINATIONS: Final = {
    0x58: (0x77, 0x7A, 0x7D),
    0x46: (0x78, 0x7B, 0x7E),
    0x45: (0x79, 0x7C, 0x7F),
    0x59: (0xAC, 0xAD, 0xAE),
    0x2E: (0x81, 0x82, 0x83),
    0x2F: (0xA6, 0xA7, 0xA8),
    0x30: (0xA9, 0xAA, 0xAB),
}


def alarm_choices(declared: dict[str, int]) -> dict[str, int]:
    """Only a screen-declared preset enables its proven combination branches."""
    result = dict(declared)
    available = set(declared.values())
    massage = {
        "head_and_foot": 0x4C in available and 0x4E in available,
        "head": 0x4C in available,
        "foot": 0x4E in available,
    }
    for key, operand in declared.items():
        for suffix, code in zip(
            ("head_and_foot", "head", "foot"),
            ALARM_COMBINATIONS.get(operand, ()),
            strict=False,
        ):
            if massage[suffix]:
                result[f"{key}_{suffix}"] = code
    # The alarm dialog's independent massage and buzzer choices. Mode1/2 and
    # flat-sleep with massage have no sender branch and are deliberately absent.
    if massage["head_and_foot"]:
        result["massage_head_and_foot"] = 0x5D
    return result


ALARM_ACTIONS: Final = StateKey[dict[str, int]]("dynasty_alarm_actions")
LIGHT_ON: Final = StateKey[bool | None]("dynasty_light_on")
EXCLUDED_LAYOUTS: Final = frozenset({"TEST", "RMCS", "FWRM", "WFRM"})
ALARM_REPLY_TIMEOUT: Final = 2.0
LAMP_ENTITY: Final = "controller_number_dynasty_lamp_seconds"


def lamp_timeout(seconds: int) -> bytes:
    """Dynasty's BE16 seconds, distinct from other resource apps' byte fold."""
    if type(seconds) is not int or not 0 <= seconds <= 300:
        raise invalid("dynasty_request")
    return codec.light_timer(seconds >> 8, seconds)


class DynastyController(SessionController):
    """Dynasty's catalog and utilities, on the shared captured-session runtime."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str = "dynasty",
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator, app=app, device_name=device_name)
        if self.layout in EXCLUDED_LAYOUTS:
            raise invalid("dynasty_request")
        self._light_on: bool | None = None
        self._alarm_ready = asyncio.Event()

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset({("number", LAMP_ENTITY)})

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        return () if self._light_available else (LAMP_ENTITY,)

    @property
    def _light_available(self) -> bool:
        session = self._session
        return (
            session is not None
            and self.client is session.client
            and session.client.is_connected
            and "light" in self._receive.menu
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The bed is disconnected")
        session = select(
            client,
            third_service=self._coordinator.entry.data.get("richmat_classic_third_service", False),
        )
        name = self._device_name or self._coordinator.entry.data.get("ble_device_name")
        # This existing builder's app-proven optional branch is exactly Dynasty's
        # actual-name cadence, including TWRM/MLRM and RAW 6BRM.
        self._worker.set_interval(p.worker_interval(name, session.wire, rise=True))
        self._worker.cancel()
        self._session, self._wire = session, session.wire
        self._notifications_started = False
        self._receive = type(self._receive)()
        self._alarm_ready.set()
        self._alarm_ready = asyncio.Event()
        self._light_on = None
        self._pending_alarm = None
        try:
            with self._transaction():
                if session.has_notifications:
                    result = await client.start_notify(
                        session.notify, partial(self._notification, session)
                    )
                    self._notifications_started = result is not False
                if session.wire == "FRAMED" and self._notifications_started:
                    await self._send(p.INITIALIZE)
                    await asyncio.sleep(p.STARTUP_MS / 1000)
        except BaseException:
            self._session = None
            raise
        self._publish()

    def _notification(
        self, session: Transport, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if (
            self._session is not session
            or self.client is not session.client
            or not session.client.is_connected
        ):
            return
        if len(self._receive.buffer) + len(data) * 2 > 512:
            self._receive.buffer = ""
            return
        super()._notification(session, sender, data)
        if self._receive.alarm_capable:
            self._alarm_ready.set()
        if self._receive.value_event in ("6e0e00017d", "6e0e00037f"):
            self._light_on = self._receive.value_event == "6e0e00037f"
            self.forward_controller_state_updates(LIGHT_ON(self._light_on))

    def on_disconnect(self) -> None:
        self._alarm_ready.set()
        self._alarm_ready = asyncio.Event()
        self._receive = type(self._receive)()
        self._lamp_seconds = None
        self._light_on = None
        super().on_disconnect()

    def _publish(self) -> None:
        super()._publish()
        self.forward_controller_state_updates(
            ALARM_ACTIONS(self._alarm_actions()), LIGHT_ON(self._light_on)
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        from dataclasses import replace

        return tuple(
            replace(spec, attribute_keys=(*spec.attribute_keys, ALARM_ACTIONS, LIGHT_ON))
            for spec in super().controller_state_sensor_specs
        )

    async def execute_action(
        self, node: int, *, long: bool = False, hold_ms: int | None = None
    ) -> None:
        with self._transaction():
            self._worker.cancel()
            await super().execute_action(node, long=long, hold_ms=hold_ms)

    async def _release(self, delay_ms: int = 0, *, mode: int | None = None) -> None:
        session = self._captured_session()
        admitted_mode = self._mode if mode is None else mode
        if session is None:
            return

        async def cleanup() -> None:
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if self._session is session and session.client.is_connected:
                await self._send(p.release(session.wire, admitted_mode))

        await settled(cleanup())

    def _alarm_actions(self) -> dict[str, int]:
        allowed = set(load_catalog(self.app).alarm_allowlist.values())
        declared = {
            f"node_{c.node}": int(c.alarm_clock, 16)
            for c in self._controls
            if c.alarm_clock is not None and c.alarm_clock in allowed
        }
        # E12 also declares the alarm dialog's independent buzzer branch.
        # The live alarm/menu gate still applies before any write.
        return {**alarm_choices(declared), "buzzer": 0x80}

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        from dataclasses import replace

        capability = p.alarm_capability(self._alarm_actions())
        if 0x6B in self._alarm_actions().values():
            if capability is None:
                capability = AlarmCapability(wake_actions=("zero_g_2",), requires_wake_action=True)
            else:
                capability = replace(capability, wake_actions=(*capability.wake_actions, "zero_g_2"))
        return (
            replace(capability, live_check=not any(c.status == 7 for c in self._controls))
            if capability else None
        )

    def _native_alarm(self, request: AlarmRequest) -> Request:
        if not request.enabled:
            return Request("cancel_alarm")
        available = alarm_choices(super()._alarm_actions())
        if request.wake_action == "zero_g_2":
            keys = tuple(key for key, code in available.items() if code == 0x6B)[:1]
            if request.massage:
                raise invalid("dynasty_request")
        else:
            keys = p.alarm_choices(available, request)
        code = alarm_action(available, keys, combinations=ALARM_COMBINATIONS)
        action = next(key for key, value in self._alarm_actions().items() if value == code)
        return Request(
            "alarm",
            action=action,
            when=time(request.hour, request.minute) if request.time_provided else None,
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        # Static preflight also runs on the cached controller before reconnect.
        try:
            request = self._native_alarm(alarm)
            code = self._alarm_actions()[request.action] if request.action else 0
            p.alarm(alarm.minutes_until() if alarm.enabled else 0, code)
        except ValueError as err:
            raise invalid("dynasty_request") from err

    def _require_alarm(self) -> None:
        if not self._receive.alarm_capable and not any(c.status == 7 for c in self._controls):
            raise invalid("dynasty_request")

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        with self._transaction() as session:
            if not self._receive.alarm_capable and not any(c.status == 7 for c in self._controls):
                ready = self._alarm_ready
                await self._send(p.ALARM_QUERY)
                try:
                    await cancellable(
                        asyncio.wait_for(ready.wait(), ALARM_REPLY_TIMEOUT),
                        self._coordinator.cancel_command,
                    )
                except TimeoutError as err:
                    raise invalid("dynasty_request") from err
            if (
                self._session is not session
                or self.client is not session.client
                or not session.client.is_connected
            ):
                raise ConnectionError("The checked bed session has ended")
            self._require_alarm()

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        with self._transaction():
            await self.check_alarm(alarm)
            request = self._native_alarm(alarm)
            code = self._alarm_actions()[request.action] if request.action else 0
            frames = p.alarm(alarm.minutes_until(dt_util.now()) if alarm.enabled else 0, code)
            self._pending_alarm = request.action
            if not alarm.enabled:
                self._preferences["alarm_selection"] = None
            cancel = self._coordinator.cancel_command
            remaining = len(frames)
            try:
                for packet in frames:
                    if cancel.is_set():
                        note_frame_skipped()
                        return

                    async def send(frame: bytes = packet) -> None:
                        nonlocal remaining
                        await self.write_command(frame)
                        remaining -= 1

                    await settled(send())
                    if not await self._wait(p.ALARM_SPACING_MS, cancel):
                        if remaining:
                            note_frame_skipped()
                        return
            except asyncio.CancelledError:
                if remaining:
                    note_frame_skipped()
                raise
            self._publish()

    def validate_richmat_classic_request(self, request: Request) -> None:
        try:
            if request.operation == "lamp_timeout":
                if request.seconds is None or not self._light_available:
                    raise ValueError
                lamp_timeout(request.seconds)
            elif request.operation in ("lamp_slider", "lamp_save") or request.operation.startswith(
                "desk_"
            ):
                raise ValueError
            else:
                super().validate_richmat_classic_request(request)
        except ValueError as err:
            raise invalid("dynasty_request") from err

    async def async_execute_richmat_classic_request(self, request: Request) -> None:
        self.validate_richmat_classic_request(request)
        with self._transaction():
            if request.operation == "lamp_timeout":
                assert request.seconds is not None
                await self.write_command(lamp_timeout(request.seconds))
                if not self._coordinator.cancel_command.is_set():
                    self._lamp_seconds = request.seconds
                    self._preferences["lamp_seconds"] = request.seconds
                    self._publish()
            else:
                await super().async_execute_richmat_classic_request(request)

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        super().restore_persisted_app_state(state)
        seconds = state.get("lamp_seconds")
        if seconds is not None:
            if type(seconds) is not int or not 0 <= seconds <= 300:
                raise invalid("dynasty_request")
            self._lamp_seconds = seconds
            self._preferences["lamp_seconds"] = seconds

    def controller_button_available(self, key: str) -> bool:
        return key == "dynasty_query" or super().controller_button_available(key)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        async def query(controller: BedController) -> None:
            if isinstance(controller, DynastyController):
                await controller.async_execute_richmat_classic_request(Request("query"))

        return (
            *super().controller_button_specs,
            ControllerButtonSpec(
                "dynasty_query",
                "Query settings",
                query,
                translation_key="dynasty_query",
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self._light_available:
            return ()

        async def timeout(controller: BedController, value: float) -> None:
            if (
                not isinstance(controller, DynastyController)
                or not math.isfinite(value)
                or value != int(value)
            ):
                raise invalid("dynasty_request")
            await controller.async_execute_richmat_classic_request(
                Request("lamp_timeout", seconds=int(value))
            )

        return (
            ControllerNumberSpec(
                "dynasty_lamp_seconds",
                "dynasty_lamp_seconds",
                LAMP_SECONDS,
                0,
                300,
                1,
                timeout,
                "s",
            ),
        )
