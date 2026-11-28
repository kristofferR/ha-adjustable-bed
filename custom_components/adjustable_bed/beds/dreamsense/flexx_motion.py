"""Flexx product and consumer policy over the shared Richmat session engine."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from functools import partial
from typing import Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmRequest
from ...card import CARD_LIGHTING
from ...codec import richmat as codec
from ...const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey, StateUpdate
from ...errors import invalid
from ...execution import ExecutionCapabilities
from ...profiles.flexx_motion import (
    BOX_SPLIT,
    BOX_STANDARD,
    CATALOG_TRANSPORTS,
    HOLD_MS,
    IO_TIMEOUT_S,
    LIGHT_CLOSE_OPCODE,
    LIGHT_DELAY_MS,
    PALETTE,
    PROFILES,
    QUERY_MS,
    RECEIVE_EXPIRY_S,
    FlexxProfile,
)
from ...state_keys import LIGHT_TIMER_OPTION, MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_RGB
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
)
from ..lifecycle import ControllerSession
from .controller import ACK, ALARMS, SPLIT, SYNC, DreamSenseController
from .flexx_receive import FlexxReceive
from .muuegm import ACTIVE, MuuegmController
from .muuegm_receive import Alarm
from .transport import Session, select

COLOR: Final = StateKey[str | None]("flexx_motion_color")
DETAILS: Final = StateKey[dict[str, object] | None]("flexx_motion_details")
ROUTES: Final = tuple(
    (codec.TRANSPORTS[k].service_uuid, codec.TRANSPORTS[k].write_uuid, codec.TRANSPORTS[k].single)
    for k in CATALOG_TRANSPORTS
)


def select_link(client: BleakClient) -> Session:
    """Check the app's exact roles without subscribing or sending commands."""
    return select(client, 0, "", routes=ROUTES, requires_notify=True)


class FlexxMotionController(MuuegmController):
    _selection_namespace = "flexx_motion_selection"
    _receive_type = FlexxReceive
    _routes = ROUTES
    _requires_notify = True
    _menu_queries = ("CheckClock", "CheckLight")
    _cleanup_after_attempt = True
    _pace_all_writes = False
    _simple_unacknowledged = False
    _simple_ambiguous = False
    _simple_ack_connection: tuple[BleakClient, int] | None = None

    @property
    def _io_timeout_s(self) -> float:
        return IO_TIMEOUT_S

    @property
    def _tick_ms(self) -> int:
        return HOLD_MS

    @property
    def _probe_ms(self) -> int:
        return QUERY_MS

    @property
    def _expiry_ms(self) -> int:
        return round(RECEIVE_EXPIRY_S * 1000)

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def flexx_profile(self) -> FlexxProfile:
        assert isinstance(self.profile, FlexxProfile)
        return self.profile

    @property
    def receive(self) -> FlexxReceive:
        assert isinstance(self._receive, FlexxReceive)
        return self._receive

    def _matches_product(self, product: str) -> bool:
        data = self._coordinator.entry.data
        return (
            data.get(CONF_BED_TYPE) == "flexx_motion" and data.get(CONF_PROTOCOL_VARIANT) == product
        )

    @property
    def supports_single_address_pairing(self) -> bool:
        # A side selector is not evidence for a Home Assistant paired topology.
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        return sum(a.action.startswith("MemoryPosition") for a in self.profile.controls)

    @property
    def supports_memory_programming(self) -> bool:
        return any(
            a.action.startswith("MemoryPosition") and a.save is not None
            for a in self.profile.controls
        )

    @property
    def memory_slots_recalled_by_presets(self) -> frozenset[int]:
        return frozenset(range(1, self.memory_slot_count + 1))

    @property
    def memory_slots_programmed_by_presets(self) -> frozenset[int]:
        return frozenset(
            i
            for i in range(1, self.memory_slot_count + 1)
            if self._action(f"MemoryPosition{i}").save is not None
        )

    def supports_memory_recall_duration(self, slot: int) -> bool:
        return 1 <= slot <= self.memory_slot_count and self._action(f"MemoryPosition{slot}").held

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        if not self.supports_memory_recall_duration(slot):
            raise invalid("dreamsense_action")
        await self.press(f"MemoryPosition{slot}", duration_ms=hold_ms)

    @property
    def supports_light_toggle_control(self) -> bool:
        return False  # Product menu buttons own the proven toggle controls.

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    @contextmanager
    def sent_state(
        self, *updates: StateUpdate, is_current: Callable[[], bool] | None = None
    ) -> Iterator[None]:
        side = self._selection.side
        with super().sent_state(
            *updates,
            is_current=lambda: (
                self._selection.side == side and (is_current is None or is_current())
            ),
        ):
            yield

    def _notification(
        self, session: Session, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if self._notify_session is not session or not self._current(session):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        revision = self.receive.revision
        self.receive.feed(bytes(data))
        self._known.update(self.receive.capabilities)
        updates = [DETAILS(dict(self.receive.events))]
        if self.receive.acknowledgements:
            updates.append(ACK(self.receive.last_ack))
        if revision != self.receive.revision:
            self._record_token += 1
            self._alarm_event.set()
            if self.profile.repeat:
                updates.append(
                    ALARMS(
                        {
                            str(i): self._alarm_details(record)
                            for i, record in enumerate(self.receive.records)
                        }
                    )
                )
        if self.profile.clock and not self.profile.repeat:
            for ack in self.receive.acknowledgements:
                active = ack == "alarm_added"
                pending = self._simple_pending
                if not self._simple_ambiguous and pending is not None and bool(pending) == active:
                    updates.extend((ACTIVE(active), ALARMS(dict(pending) if active else None)))
                    self._simple_pending = None
                    self._simple_unacknowledged = False
        if self.profile.split and "split" in self.receive.completed:
            updates.append(SPLIT(self.receive.split))
        self.forward_controller_state_updates(*updates)
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        if self.receive.pending:
            self._expiry = asyncio.get_running_loop().call_later(
                RECEIVE_EXPIRY_S, self.receive.expire
            )
        rgb = self.receive.completed.get("rgb")
        if self.profile.light and isinstance(rgb, tuple):
            selected = next((name for name, color in PALETTE.items() if rgb == color), None)
            self.forward_controller_state_update(COLOR, selected)

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self.forward_controller_state_updates(COLOR(None), DETAILS(None))

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "model": self.profile.product,
            "current_picker": self.profile.normal,
            "capabilities": sorted(self.receive.capabilities),
            "observations": dict(self.receive.events),
            "frames": list(self.receive.frames),
            "unmapped_motion": self.flexx_profile.omitted,
            "alarm_records": [asdict(r) for r in self.receive.records],
        }

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            replace(s, hold=replace(s.hold, release_button_key="richmat_classic_release"))
            if s.hold is not None else s
            for s in super(MuuegmController, self).controller_button_specs
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return ()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            *super(MuuegmController, self).controller_select_specs,
            *(
                (
                    ControllerSelectSpec(
                        "flexx_motion_color",
                        "flexx_motion_color",
                        COLOR,
                        tuple(PALETTE),
                        _color,
                        card=CARD_LIGHTING,
                    ),
                )
                if self._has_light
                else ()
            ),
        )

    def select_side(self, value: str) -> None:
        previous = self._selection.side
        super().select_side(value)
        if previous != self._selection.side:
            self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(None), SYNC(None))

    def controller_button_available(self, key: str) -> bool:
        if key == "dreamsense_refresh_alarms":
            return self.profile.repeat and self.command_side is None and "clock" in self._known
        if key == "dreamsense_light_close":
            return self.profile.light and self.command_side is None and "light" in self._known
        return super().controller_button_available(key)

    def _simple_alarm_started(self) -> None:
        session = self._live()
        connection = self._simple_ack_connection
        if (
            connection is None
            or connection[0] is not session.client
            or connection[1] != session.generation
        ):
            self._simple_unacknowledged = self._simple_ambiguous = False
            self._simple_ack_connection = (session.client, session.generation)
        # Bare ACKs cannot distinguish two requests sent before either reply.
        # Notification restarts on a retained physical link cannot clear this.
        self._simple_ambiguous |= self._simple_unacknowledged
        self._simple_unacknowledged = True
        super()._simple_alarm_started()

    def _simple_alarm_submitted(self, pending: dict[str, object]) -> None:
        if not self._simple_ambiguous:
            super()._simple_alarm_submitted(pending)

    @property
    def supports_light_timer(self) -> bool:
        return self._has_light

    @property
    def light_timer_options(self) -> list[str]:
        return (
            [self._timer_name(n) for n in self.flexx_profile.light_seconds]
            if self._has_light
            else []
        )

    @staticmethod
    def _timer_name(seconds: int) -> str:
        return "Always on" if seconds == 0 else f"{seconds // 60} min"

    def _light_wire(self, seconds: int) -> tuple[int, str | None]:
        if type(seconds) is not int or seconds not in self.flexx_profile.light_seconds:
            raise invalid("dreamsense_action")
        return seconds, self._timer_name(seconds)

    async def set_light_timer(self, timer_option: str) -> None:
        value = next(
            (n for n in self.flexx_profile.light_seconds if self._timer_name(n) == timer_option),
            None,
        )
        if value is None:
            raise invalid("dreamsense_action")
        await self.light_settings(seconds=value)

    def validate_light(
        self, color: tuple[int, int, int] | None = None, seconds: int | None = None
    ) -> None:
        super().validate_light(color, seconds)
        if color is not None and color not in PALETTE.values():
            raise invalid("dreamsense_action")

    async def light_settings(
        self, *, color: tuple[int, int, int] | None = None, seconds: int | None = None
    ) -> None:
        self.validate_light(color, seconds)
        with self._transaction():
            self._require("light")
            cancel = self._coordinator.cancel_command
            if seconds is not None:
                await self._wait(LIGHT_DELAY_MS, cancel)
                with self.sent_state(LIGHT_TIMER_OPTION(self._timer_name(seconds))):
                    await self._send(
                        codec.light_timer(seconds >> 8, seconds)
                        if seconds
                        else codec.light_timer(255, 255),
                        cancel,
                        validate=partial(self._require, "light"),
                    )
            if color is not None:
                selected = next(name for name, rgb in PALETTE.items() if rgb == color)
                with self.sent_state(COLOR(selected), UNDER_BED_LIGHTS_RGB(color)):
                    await self._send(
                        codec.rgb(*color), cancel, validate=partial(self._require, "light")
                    )

    async def close_light(self) -> None:
        # Dedicated LightPage close defaults to side 0, independently of selection.
        self._require("light")
        with self._transaction() as session:
            await self._send(
                self.profile.frame(LIGHT_CLOSE_OPCODE, single=session.single),
                self._coordinator.cancel_command,
                validate=partial(self._require, "light"),
            )

    async def _clock(self, *, own: bool = True) -> None:
        for frame in codec.time_sync(
            dt_util.now(), dt_util.now(), build=codec.record_20_len, first_hex=True
        ):
            await self._send(frame, self._coordinator.cancel_command if own else None, own=own)

    async def sync_clock(self) -> None:
        # Startup and explicit sync require the product flag, not a capability ACK.
        await DreamSenseController.sync_clock(self)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return tuple(
            replace(s, set_fn=_box) if s.key == "dreamsense_split" else s
            for s in super().controller_switch_specs
        )

    def validate_record_update(
        self, number: int, identity: tuple[int, int] | None = None
    ) -> tuple[int, int]:
        current = self.validate_record(number, identity)
        record = next(r for r in self.receive.records if r.id == number)
        if record.mode not in self.profile.alarm.values():
            raise invalid("dreamsense_action")
        return current

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        await super().check_alarm(alarm)
        if self.profile.repeat and not alarm.enabled:
            self.validate_record_update(alarm.slot)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        with self._transaction():
            self._require("clock")
            if not self.profile.repeat:
                await self._configure_simple_alarm(alarm, self._coordinator.cancel_command)
                return
            if not 1 <= alarm.slot <= 7:
                raise invalid("dreamsense_alarm_record")
            if alarm.enabled:
                record = Alarm(
                    alarm.slot,
                    0,
                    alarm.hour,
                    alarm.minute,
                    self._alarm_code(alarm),
                    1 | sum(0x80 >> d for d in set(alarm.weekdays)),
                )
                guard = partial(self._require, "clock")
            else:
                identity = self.validate_record_update(alarm.slot, alarm.record_identity)
                previous = next(r for r in self.receive.records if r.id == alarm.slot)
                record = replace(previous, reserved=0, repeat_mask=previous.repeat_mask & 0xFE)
                guard = partial(self.validate_record_update, alarm.slot, identity)
            await self._write_record(record.frame(), guard)

    async def enable_alarm(self, number: int, enabled: bool, identity: tuple[int, int]) -> None:
        with self._transaction():
            self.validate_record_update(number, identity)
            previous = next(r for r in self.receive.records if r.id == number)
            record = replace(
                previous, reserved=0, repeat_mask=(previous.repeat_mask & 0xFE) | int(enabled)
            )
            await self._write_record(
                record.frame(), partial(self.validate_record_update, number, identity)
            )

    async def delete_alarm(self, number: int, identity: tuple[int, int]) -> None:
        with self._transaction():
            self.validate_record(number, identity)
            await self._write_record(
                codec.record_20_len(5, 2, 1, (number,)),
                partial(self.validate_record, number, identity),
            )

    def _alarm_details(self, record: Alarm) -> dict[str, object]:
        from ...alarm import WEEKDAYS
        from ...profiles.dreamsense import ALARM_NAMES

        action = None
        for name, code in self.profile.alarm.items():
            if code == record.mode:
                action = ALARM_NAMES[name]
        return {
            "slot": record.id,
            "hour": record.hour,
            "minute": record.minute,
            "wake_action": action,
            "enabled": bool(record.repeat_mask & 1),
            "weekdays": [
                day for index, day in enumerate(WEEKDAYS) if record.repeat_mask & (0x80 >> index)
            ],
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            (
                ControllerStateSensorSpec(
                    "flexx_motion_alarm",
                    "dreamsense_alarm_ack",
                    ACK,
                    "mdi:alarm",
                    attribute_keys=(ALARMS, ACTIVE),
                ),
            )
            if self.profile.clock
            else ()
        )


async def _color(controller: BedController, value: str) -> None:
    if value not in PALETTE:
        raise invalid("dreamsense_action")
    await require_controller(controller, FlexxMotionController).light_settings(color=PALETTE[value])


async def _box(controller: BedController, enabled: bool) -> None:
    ctrl = require_controller(controller, FlexxMotionController)
    ctrl._physical()
    if not ctrl.profile.split:
        raise invalid("dreamsense_action")
    with ctrl._transaction(), ctrl.sent_state(SPLIT(enabled)):
        await ctrl._send(
            codec.record_20_len(11, 2, 1, (0, BOX_SPLIT if enabled else BOX_STANDARD)),
            ctrl._coordinator.cancel_command,
        )


async def build_controller(ctx: BuildContext) -> BedController:
    if ctx.variant not in PROFILES:
        raise invalid("dreamsense_product")
    return FlexxMotionController(
        ctx.coordinator,
        product=PROFILES[ctx.variant],
        capability_snapshot=ctx.stored_capabilities("flexx_motion"),
    )
