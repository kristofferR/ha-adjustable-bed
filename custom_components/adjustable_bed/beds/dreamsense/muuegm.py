"""MUUEGM current products on the shared session-safe Richmat controller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, replace
from functools import partial
from typing import ClassVar, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_LIGHTING
from ...codec import richmat as codec
from ...const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles.muuegm import PALETTE, PROFILES
from ...state_keys import UNDER_BED_LIGHTS_RGB
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    PositionNumberSpec,
)
from .controller import ACK, ALARMS, LIGHT_SECONDS, DreamSenseController
from .muuegm_receive import Alarm, MuuegmReceive
from .transport import GattRoute, Session

# Independent app declaration: first qualifying handles, last recognized format.
ROUTES: Final[tuple[GattRoute, ...]] = (
    ("6e400001-b5a3-f393-e0a9-e50e24dcca9e", "6e400002-b5a3-f393-e0a9-e50e24dcca9e", False),
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600", True),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622", True),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe2-0000-1000-8000-00805f9b34fb", True),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb", True),
    ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "00000002-3c17-d293-8e48-14fe2e4da212", True),
)
COLOR: Final = StateKey[str | None]("muuegm_color")
DIAGNOSTICS: Final = StateKey[dict[str, object] | None]("muuegm_notifications")
ACTIVE: Final = StateKey[bool | None]("muuegm_alarm_active")


class MuuegmController(DreamSenseController):
    _record_token: int = 0
    _simple_pending: dict[str, object] | None = None
    _selection_namespace = "muuegm_selection"
    _receive_type = MuuegmReceive
    _routes = ROUTES
    _requires_notify = False
    _menu_queries: ClassVar[tuple[str, ...]] = ("CheckClock", "CheckLight")

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def receive(self) -> MuuegmReceive:
        assert isinstance(self._receive, MuuegmReceive)
        return self._receive

    def _matches_product(self, product: str) -> bool:
        data = self._coordinator.entry.data
        return data.get(CONF_BED_TYPE) == "muuegm" and data.get(CONF_PROTOCOL_VARIANT) == product

    def _notification(
        self, session: Session, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if not self._current(session):
            return
        if session.notify is not None:
            self.forward_raw_notification(session.notify.uuid, bytes(data))
        revision = self.receive.revision
        self.receive.feed(bytes(data))
        self._known.update(self.receive.capabilities)
        if revision != self.receive.revision:
            self._record_token += 1
            self._alarm_event.set()
        updates = [ACK(self.receive.last_ack), DIAGNOSTICS(dict(self.receive.events))]
        if self.profile.repeat and revision != self.receive.revision:
            updates.append(ALARMS({str(i): asdict(a) for i, a in enumerate(self.receive.records)}))
        if self.profile.clock and not self.profile.repeat:
            for ack in self.receive.acknowledgements:
                active = ack == "alarm_added"
                updates.append(ACTIVE(active))
                if not active:
                    updates.append(ALARMS(None))
                if self._simple_pending is not None and bool(self._simple_pending) == active:
                    if active:
                        updates.append(ALARMS(dict(self._simple_pending)))
                    self._simple_pending = None
        self.forward_controller_state_updates(*updates)

    def on_disconnect(self) -> None:
        self._record_token += 1
        self._simple_pending = None
        super().on_disconnect()
        self.forward_controller_state_updates(COLOR(None), DIAGNOSTICS(None), ACTIVE(None))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # The accepted current paths do not establish a dedicated light-off opcode.
        return tuple(
            s for s in super().controller_button_specs if s.key != "dreamsense_light_close"
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return tuple(replace(s, native_step=60) for s in super().controller_number_specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self._has_light:
            return ()
        return (
            ControllerSelectSpec(
                "muuegm_color",
                "muuegm_color",
                COLOR,
                tuple(PALETTE),
                _color,
                card=CARD_LIGHTING,
            ),
        )

    def _light_wire(self, seconds: int) -> tuple[int, str | None]:
        if type(seconds) is not int or seconds % 60:
            raise invalid("dreamsense_action")
        return super()._light_wire(seconds)

    def _require(self, name: str) -> None:
        self._physical()
        self._live()
        if not self._gate(name):
            raise invalid("dreamsense_capability")

    async def light_settings(
        self, *, color: tuple[int, int, int] | None = None, seconds: int | None = None
    ) -> None:
        self.validate_light(color, seconds)
        with self._transaction():
            self._require("light")
            cancel = self._coordinator.cancel_command
            if seconds is not None:
                await self._wait(200, cancel)
                with self.sent_state(LIGHT_SECONDS(seconds)):
                    await self._send(
                        codec.light_timer(255, 255)
                        if not seconds
                        else codec.light_timer(seconds >> 8, seconds),
                        cancel,
                        validate=partial(self._require, "light"),
                    )
            if color is not None:
                selected = next((name for name, rgb in PALETTE.items() if rgb == color), None)
                with self.sent_state(UNDER_BED_LIGHTS_RGB(color), COLOR(selected)):
                    await self._send(
                        codec.rgb(*color), cancel, validate=partial(self._require, "light")
                    )

    async def close_light(self) -> None:
        raise invalid("dreamsense_action")

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.profile.product == "ABF03"

    async def lights_toggle(self) -> None:
        await self.press("BedLight")

    async def sync_clock(self) -> None:
        with self._transaction():
            self._require("clock")
            await self._clock()

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        base = super().alarm_capability
        return (
            replace(base, slots=7, live_slots=False, requires_slot=True)
            if base and self.profile.repeat
            else base
        )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        with self._transaction():
            self._require("clock")
            if self.profile.repeat and not alarm.enabled:
                self.validate_record(alarm.slot)

    async def query_alarms(self, *, own: bool = True, number: int | None = None) -> None:
        with self._transaction():
            self._require("clock")
            if not self.profile.repeat:
                raise invalid("dreamsense_action")
            self.receive.records.clear()
            self.receive.revision += 1
            self._record_token += 1
            self.forward_controller_state_updates(ALARMS(None))
            await self._send(
                codec.record_20_len(5, 1, 0, (0,)),
                self._coordinator.cancel_command,
                own=own,
                validate=partial(self._require, "clock"),
            )
            if number is not None:
                async with asyncio.timeout(5):
                    while not any(a.id == number for a in self.receive.records):
                        self._alarm_event.clear()
                        await cancellable(
                            self._alarm_event.wait(), self._coordinator.cancel_command
                        )
                        self._require("clock")

    def validate_record(
        self, number: int, identity: tuple[int, int] | None = None
    ) -> tuple[int, int]:
        self._require("clock")
        if not self.profile.repeat or not any(a.id == number for a in self.receive.records):
            raise invalid("dreamsense_alarm_record")
        # Tokens survive receiver resets, so a reconnect cannot reuse an old stamp.
        current = (number, self._record_token)
        if identity is not None and identity != current:
            raise invalid("dreamsense_alarm_record")
        return current

    def alarm_record_identity(self, alarm: AlarmRequest) -> tuple[int, int] | None:
        if self.profile.repeat and not alarm.enabled:
            return self.validate_record(alarm.slot)
        return None

    async def _write_record(self, frame: bytes, validate: Callable[[], object]) -> bool:
        session = self._live()
        submitted = False

        def guard() -> None:
            nonlocal submitted
            validate()
            submitted = True

        try:
            return await self._send(frame, self._coordinator.cancel_command, validate=guard)
        finally:
            if submitted and self._current(session):
                # An attempted mutation is not a readback, even if the write fails.
                self.receive.records.clear()
                self.receive.revision += 1
                self._record_token += 1
                self.forward_controller_state_updates(ALARMS(None))

    def _simple_alarm_started(self) -> None:
        self._simple_pending = None
        self.forward_controller_state_updates(ALARMS(None), ACTIVE(None))

    def _simple_alarm_submitted(self, pending: dict[str, object]) -> None:
        self._simple_pending = pending

    async def _configure_simple_alarm(self, alarm: AlarmRequest, cancel: asyncio.Event) -> None:
        session = self._live()
        pending = (
            {"hour": alarm.hour, "minute": alarm.minute, "wake_action": alarm.wake_action}
            if alarm.enabled
            else {}
        )
        submitted = False
        complete = False

        def guard(*, final: bool) -> None:
            nonlocal submitted
            self._require("clock")
            if not submitted:
                self._simple_alarm_started()
            if final:
                self._simple_alarm_submitted(pending)
            submitted = True

        now = dt_util.now()
        # The app chooses the next occurrence when this command executes.
        minutes = replace(alarm, reference_time=now).minutes_until(now)
        frames = codec.countdown(
            minutes if alarm.enabled else 0, self._alarm_code(alarm) if alarm.enabled else 0
        )
        try:
            for index, frame in enumerate(frames):
                if not await self._send(
                    frame, cancel, validate=partial(guard, final=index + 1 == len(frames))
                ):
                    return
            complete = True
        finally:
            if (
                not complete
                and submitted
                and self._current(session)
                and (self._simple_pending is pending or self._simple_pending is None)
            ):
                self._simple_pending = None
                self.forward_controller_state_updates(ALARMS(None), ACTIVE(None))

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        with self._transaction():
            self._require("clock")
            cancel = self._coordinator.cancel_command
            if not self.profile.repeat:
                await self._configure_simple_alarm(alarm, cancel)
                return
            if not 1 <= alarm.slot <= 7:
                raise invalid("dreamsense_alarm_record")

            def guard() -> object:
                return self._require("clock")

            if alarm.enabled:
                if (
                    not any(a.id == alarm.slot for a in self.receive.records)
                    and len(self.receive.records) >= 7
                ):
                    raise invalid("dreamsense_alarm_record")
                record = Alarm(
                    alarm.slot,
                    0,
                    alarm.hour,
                    alarm.minute,
                    self._alarm_code(alarm),
                    1 | sum(1 << (7 - day) for day in set(alarm.weekdays)),
                )
            else:
                identity = self.validate_record(alarm.slot, alarm.record_identity)
                previous = next(a for a in self.receive.records if a.id == alarm.slot)
                record = replace(previous, repeat_mask=previous.repeat_mask & 0xFE)
                guard = partial(self.validate_record, alarm.slot, identity)
            if await self._write_record(record.frame(), guard):
                await self._wait(200, cancel)
                await self.query_alarms(own=False)

    async def enable_alarm(self, number: int, enabled: bool, identity: tuple[int, int]) -> None:
        with self._transaction():
            self.validate_record(number, identity)
            previous = next(a for a in self.receive.records if a.id == number)
            record = replace(previous, repeat_mask=(previous.repeat_mask & 0xFE) | int(enabled))
            if await self._write_record(
                record.frame(),
                partial(self.validate_record, number, identity),
            ):
                await self._wait(200, self._coordinator.cancel_command)
                await self.query_alarms(own=False)

    async def delete_alarm(self, number: int, identity: tuple[int, int]) -> None:
        with self._transaction():
            self.validate_record(number, identity)
            if await self._write_record(
                codec.record_20_len(5, 2, 1, (number,)),
                partial(self.validate_record, number, identity),
            ):
                await self._wait(200, self._coordinator.cancel_command)
                await self.query_alarms(own=False)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            replace(spec, attribute_keys=(ALARMS, DIAGNOSTICS, ACTIVE))
            for spec in super().controller_state_sensor_specs
        )


async def _color(controller: BedController, value: str) -> None:
    if value not in PALETTE:
        raise invalid("dreamsense_action")
    await require_controller(controller, MuuegmController).light_settings(color=PALETTE[value])


async def build_controller(ctx: BuildContext) -> BedController:
    if ctx.variant not in PROFILES:
        raise invalid("dreamsense_product")
    return MuuegmController(
        ctx.coordinator,
        product=PROFILES[ctx.variant],
        capability_snapshot=ctx.stored_capabilities("muuegm"),
    )
