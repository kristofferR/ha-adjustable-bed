"""Bed Tech's selected Android controls over the shared Richmat MH runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...codec import richmat as codec
from ...command_scheduler import command_frames_counted, current_command_context, note_frame_skipped
from ...controller_state import StateKey
from ...errors import failed, invalid
from ...profiles.bedtech_classic import CALENDAR_MODELS, INIT_INTERVAL_S, RELEASE_S
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
)
from ..richmat_mh import protocol as p
from ..richmat_mh.app_catalog import catalog
from ..richmat_mh.app_controller import LAST_REPLY, RichmatMHAppController, _HoldElapsed
from ..richmat_mh.controller import (
    INTENSITY_KEYS,
    LIGHT_TIMER_KEY,
    LIGHT_TIMER_MINUTES_KEY,
    MOTOR_MODE_KEY,
    SMART_LIGHT_LOCK_KEY,
    SMART_SET_LOCK_KEY,
    SNORE_KEY,
    SNORE_OPTIONS,
    Control,
    SessionFlags,
)
from ..ruf_richmat.controller import waist_init
from ..ruf_richmat.protocol import calendar_clock

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

SNORE_ENABLED: Final = StateKey[bool | None]("bedtech_snore_enabled")
CALENDAR_ROWS: Final = StateKey[list[dict[str, int]]]("bedtech_calendar_rows")
ACCESSORY: Final = StateKey[dict[str, int]]("bedtech_accessory_state")


class Classifier(p.Classifier):
    """Keep Bed Tech's whole-buffer parser and its separate calendar branch."""

    def __init__(self) -> None:
        super().__init__("revive")

    def feed(self, data: bytes) -> list[p.Event]:
        # The app calls its calendar parser immediately, without a length or sum
        # check. HA drops a truncated record instead of crashing the callback.
        combined = self.buffer + data.hex()
        if len(combined) > 2048:
            self.buffer = ""
            self.rx_type = "NONE"
            return []
        if combined.startswith("6e20"):
            self.buffer = ""
            return [p.Event("calendar", combined)] if len(combined) >= 24 else []
        if combined.startswith("6e90b") or self.rx_type == "MUSIC_VIBRATOR":
            self.buffer = ""
            return [p.Event("accessory", combined)]
        return super().feed(data)


@dataclass(frozen=True)
class Owner:
    client: BleakClient
    generation: int
    entry: object
    entry_data: Mapping[str, object]
    stop_epoch: int
    mode: int


_OPERATION: ContextVar[Owner | None] = ContextVar("bedtech_operation", default=None)
_CALENDAR_TARGET: ContextVar[tuple[int, int] | None] = ContextVar(
    "bedtech_calendar_target", default=None
)


@dataclass
class RequiredFrames:
    remaining: int

    def written(self) -> None:
        self.remaining -= 1


_REQUIRED: ContextVar[RequiredFrames | None] = ContextVar("bedtech_required_frames", default=None)


@contextmanager
def required_frames(count: int) -> Iterator[None]:
    if _REQUIRED.get() is not None:
        yield
        return
    pending = RequiredFrames(count)
    token = _REQUIRED.set(pending)
    try:
        yield
    except asyncio.CancelledError:
        if pending.remaining > 0:
            note_frame_skipped()
        raise
    finally:
        _REQUIRED.reset(token)


async def _press(controller: BedController, *, code: int) -> None:
    if not isinstance(controller, BedTechClassicController):
        raise invalid("option_unavailable")
    await controller.tap(code)


async def _refresh_alarms(controller: BedController) -> None:
    if not isinstance(controller, BedTechClassicController):
        raise invalid("option_unavailable")
    await controller.refresh_alarms()


async def _delete_alarm(controller: BedController, *, slot: int) -> None:
    if not isinstance(controller, BedTechClassicController):
        raise invalid("option_unavailable")
    await controller.delete_alarm(slot)


class BedTechClassicController(RichmatMHAppController):
    """An explicit Bed Tech surface, never inferred from the newer app's models."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, variant: str, name: str | None = None
    ) -> None:
        super().__init__(
            coordinator, app="bedtech_classic", protocol_variant=variant, device_name=name
        )
        self._classifier = Classifier()
        self._calendar_rows: list[dict[str, int]] = []
        self._calendar_records: dict[tuple[int, int], dict[str, int]] = {}
        self._preparing = False
        self._accessory: dict[str, int] = {}
        self._notification_entry = coordinator.entry
        self._notification_data = self._entry_data()
        saved = self._stored_snapshot.get("snore_enabled")
        self._snore_enabled = saved if type(saved) is bool else None
        saved_slots = self._stored_snapshot.get("calendar_slots")
        self._known_calendar_slots = (
            {slot for slot in saved_slots if type(slot) is int and slot >= 0}
            if isinstance(saved_slots, list)
            else set[int]()
        )

    def _entry_data(self) -> dict[str, object]:
        # Persisting this session's capability/readback state cannot change its
        # command identity. App/profile/roster/settings changes still invalidate it.
        return {
            key: value
            for key, value in self._coordinator.entry.data.items()
            if key != "capabilities"
        }

    def capability_snapshot(self) -> dict[str, object] | None:
        snapshot = super().capability_snapshot()
        if snapshot is not None:
            snapshot["snore_enabled"] = self._snore_enabled
            snapshot["calendar_slots"] = sorted(self._known_calendar_slots)
        return snapshot

    def _owner(self) -> Owner:
        client = self._owner_client
        if client is None:
            raise failed("bed_changed")
        return Owner(
            client,
            self._session_generation,
            self._coordinator.entry,
            self._entry_data(),
            self._coordinator.stop_epoch,
            self._transmit_mode,
        )

    def _check(self, owner: Owner, *, cleanup: bool = False) -> None:
        if (
            self.client is not owner.client
            or not owner.client.is_connected
            or self._session_generation != owner.generation
            or self._coordinator.controller is not self
            or self.command_side is not None
        ):
            raise failed("bed_changed")
        if not cleanup:
            if self._coordinator.entry is not owner.entry or self._entry_data() != owner.entry_data:
                raise failed("bed_changed")
            if self._coordinator.stop_epoch != owner.stop_epoch:
                raise asyncio.CancelledError

    @contextmanager
    def _operation(self) -> Iterator[Owner]:
        owner = _OPERATION.get() or self._owner()
        self._check(owner)
        token = _OPERATION.set(owner)
        try:
            yield owner
        finally:
            _OPERATION.reset(token)

    async def _dispatch(
        self,
        frame: bytes,
        *,
        cancel_event: asyncio.Event | None = None,
        factory: Callable[[], bytes] | None = None,
        deadline: float | None = None,
        cleanup: bool = False,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        owner = _OPERATION.get() or self._owner()
        self._check(owner, cleanup=cleanup)
        characteristic = self._write_char
        if characteristic is None:
            raise failed("bed_changed")
        cancel = cancel_event or self._coordinator.cancel_command

        def validate() -> None:
            self._check(owner, cleanup=cleanup)
            if (
                frame[:2] == b"\x6e\x20"
                and frame[3:4] in (b"\x05", b"\x08")
                and not self._calendar_page()
            ):
                raise failed("bed_changed")
            if (target := _CALENDAR_TARGET.get()) is not None:
                current = self._calendar_alarms.get(target[0])
                if not self._calendar_page() or current is None or current["bed"] != target[1]:
                    raise failed("bed_changed")
            context = current_command_context()
            if not cleanup and (cancel.is_set() or context and context.cancel_event.is_set()):
                if not self._preparing:
                    note_frame_skipped()
                raise asyncio.CancelledError
            limit = context.hold_deadline if context and context.lease and not cleanup else deadline
            if limit is not None and asyncio.get_running_loop().time() >= limit:
                note_frame_skipped()
                raise _HoldElapsed

        # Mode belongs to this admitted operation. A picker cannot redirect a
        # queued frame or its release to another mode while BLE is busy.
        if factory is not None and len(frame) == 5 and frame[:2] == b"\x6e\x01":
            frame = codec.command(frame[3], owner.mode)
            factory = None
        with command_frames_counted() if not (cleanup or self._preparing) else nullcontext():
            required = _REQUIRED.get() if not (cleanup or self._preparing) else None

            def written() -> None:
                if required is not None:
                    required.written()
                if on_write is not None:
                    on_write()

            await settled(
                self._write_gatt_with_retry(
                    characteristic.uuid,
                    frame,
                    cancel_event=cancel_event,
                    response="write" in characteristic.properties,
                    characteristic=characteristic,
                    expected_client=owner.client,
                    before_write=validate,
                    command_factory=factory,
                    on_write=written,
                    track_command_write=not (cleanup or self._preparing),
                )
            )
        self._check(owner, cleanup=True)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        with self._operation() as owner, required_frames(repeat_count):
            cancel = cancel_event or self._coordinator.cancel_command
            if len(command) == 5 and command[:2] == b"\x6e\x01":
                command = codec.command(command[3], owner.mode)
            for index in range(repeat_count):
                if cancel.is_set():
                    note_frame_skipped()
                    return
                started = asyncio.get_running_loop().time()
                await self._dispatch(command, cancel_event=cancel_event)
                if index + 1 < repeat_count:
                    await self._wait_cancel(
                        max(
                            0,
                            repeat_delay_ms / 1000 - (asyncio.get_running_loop().time() - started),
                        ),
                        cancel,
                    )

    async def _write_sequence(self, frames: Sequence[bytes], sleep_s: float) -> None:
        with self._operation(), required_frames(len(frames)):
            for index, frame in enumerate(frames):
                if index:
                    await asyncio.sleep(sleep_s)
                await self.write_command(frame)

    async def _release(self, delay: float = RELEASE_S) -> None:
        owner = _OPERATION.get() or self._owner()

        async def release() -> None:
            await asyncio.sleep(delay)
            # Do not send an old operation's release to a replacement link.
            if self.client is not owner.client or self._session_generation != owner.generation:
                return
            await self._dispatch(
                codec.command(codec.STOP, owner.mode), cancel_event=asyncio.Event(), cleanup=True
            )
            if context := current_command_context():
                context.cleanup_stop_sent = True

        await settled(release())

    @property
    def _fixed_remote(self) -> bool:
        # This app's selected widgets use the shared KEEP/ONCE queue. A sibling's
        # attached handset timings do not select its execution policy.
        return False

    @property
    def route(self) -> str:
        session = self._pending
        if session is not None:
            return "C" if session.version == "0001" and session.call_page else "L"
        return super().route

    @property
    def has_dynamic_buttons(self) -> bool:
        return self._calendar_page() or super().has_dynamic_buttons

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return self._calendar_page() or super().has_dynamic_controller_entities

    @property
    def supports_stop_all(self) -> bool:
        return any(c.keep_ms for c in self._controls()) or super().supports_stop_all

    @property
    def commands_share_timer(self) -> bool:
        return True

    def _controls(self) -> tuple[Control, ...]:
        controls = super()._controls()
        if self._light_page() == "btn_led" and self.model:
            controls += tuple(c for c in self.model.controls if c.route == "B")
        return controls

    async def _held(self, control: Control, duration_ms: int | None = None) -> None:
        with self._operation():
            loop = asyncio.get_running_loop()
            interval = control.keep_ms / 1000
            count, _ = self.motor_pulse_settings()
            deadline = loop.time() + (
                duration_ms / 1000 if duration_ms is not None else count * interval
            )
            cancel = self._coordinator.cancel_command
            try:
                while True:
                    context = current_command_context()
                    limit = context.hold_deadline if context and context.lease else deadline
                    if limit is None or loop.time() >= limit:
                        break
                    if cancel.is_set():
                        note_frame_skipped()
                        break
                    started = loop.time()
                    try:
                        await self._dispatch(
                            codec.command(control.code),
                            factory=lambda: codec.command(control.code, self._transmit_mode),
                            deadline=limit,
                        )
                    except _HoldElapsed:
                        break
                    await self._wait_cancel(
                        max(0, min(interval - (loop.time() - started), limit - loop.time())), cancel
                    )
            finally:
                await self._release()

    async def tap(self, code: int) -> None:
        self.validate_control(code)
        with self._operation():
            await super().tap(code)

    async def stop_all(self) -> None:
        # The scheduler owns cancellation. This only releases the current lane.
        with self._operation():
            await self._release(0)

    def _snore_options(self) -> tuple[str, ...]:
        f = self._features
        if self.route != "L" or not f or not f.snore:
            return ()
        base = self.model.model_id.removesuffix("_mattress") if self.model else ""
        if not self._dev.get("snore") and base not in ("a5rn", "garm", "afrn"):
            return ()
        return ("off", *(SNORE_OPTIONS[c] for c in f.snore_list if c in SNORE_OPTIONS))

    def _smart_light_lock(self) -> bool:
        # Feedback is real even though the visible cfrm sender is unwired.
        return bool(self._features and self._features.smart_light_lock and self._light_page())

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec | None] = [
            replace(spec, hold=None) if spec.requires_confirmation else spec
            for spec in super().controller_button_specs
            if spec.key != "richmat_mh_toggle_smart_light_lock"
        ]
        covered = {c.code for axis in self._axes() for c in (axis.up, axis.down)}
        for control in self._controls():
            if control.area == "motor" and control.code not in covered:
                specs.append(
                    catalog_button(
                        f"bedtech_{control.code:02x}",
                        f"{'Head and feet' if control.group in ('HEAD_FOOT_BOTH', 'Back Foot Both') else control.label} {control.kind}",
                        partial(_press, code=control.code),
                        kind=Kind.MOTOR,
                        hold=ControllerHoldSpec(f"mh_{control.code:02x}"),
                        invalidates_position=True,
                    )
                )
        if self._calendar_page():
            specs.append(
                catalog_button(
                    "bedtech_refresh_alarms",
                    "Refresh alarms",
                    _refresh_alarms,
                    kind=Kind.EXTRA,
                    cancel_movement=False,
                )
            )
            for slot in sorted(self._known_calendar_slots):
                specs.append(
                    catalog_button(
                        f"bedtech_delete_alarm_{slot}",
                        f"Delete alarm {slot}",
                        partial(_delete_alarm, slot=slot),
                        kind=Kind.EXTRA,
                        requires_confirmation=True,
                        cancel_movement=False,
                    )
                )
        return unique_buttons(specs)

    def controller_button_available(self, key: str) -> bool:
        if key.startswith("bedtech_delete_alarm_"):
            return self._calendar_page() and any(
                key == f"bedtech_delete_alarm_{slot}" for slot in self._calendar_alarms
            )
        return super().controller_button_available(key)

    async def toggle_smart_light_lock(self) -> None:
        raise invalid(
            "feature_not_supported",
            device_name=self._coordinator.name,
            feature="smart light lock control",
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                key, str(key), key, "mdi:lock", entity_registry_enabled_default=False
            )
            for key, available in (
                (SMART_SET_LOCK_KEY, self._smart_set_lock()),
                (SMART_LIGHT_LOCK_KEY, self._smart_light_lock()),
            )
            if available
        )

    def _calendar_page(self) -> bool:
        return bool(
            self.model
            and self.route == "L"
            and self.model.model_id.removesuffix("_mattress") in CALENDAR_MODELS
            and self._features
            and self._features.alarm
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            replace(
                spec, attribute_keys=(*spec.attribute_keys, SNORE_ENABLED, CALENDAR_ROWS, ACCESSORY)
            )
            if spec.key == str(LAST_REPLY)
            else spec
            for spec in super().controller_state_sensor_specs
        )

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self._calendar_page():
            return super().alarm_capability
        sides = (
            ("left", "right") if self._normal_ready else tuple(p.WAIST_SIDES) if self._waist else ()
        )
        from ..richmat_mh.controller import _ALARM_POSITIONS

        features = self._features
        assert features is not None
        options = tuple(
            name
            for name, value in _ALARM_POSITIONS.items()
            if p.ALARM_OPTION_CODES[value] in features.alarm
        )
        return AlarmCapability(
            wake_actions=options,
            live_slots=True,
            weekdays=True,
            requires_wake_action=True,
            live_check=True,
            mattress_sides=sides,
            massage_intensities=3 if sides else 0,
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.record_identity is not None and (
            not self._calendar_page() or alarm.mattress_side is not None
        ):
            raise failed("bed_changed")
        if not self._calendar_page() or alarm.mattress_side is not None:
            return super().validate_alarm(alarm)
        capability = self.alarm_capability
        if capability is None:
            raise invalid("alarm_refresh_needed")
        if alarm.massage_intensity != 1:
            raise invalid(
                "alarm_option_not_supported",
                device_name=self._coordinator.name,
                option="massage_intensity",
            )
        if (
            alarm.slot < 0
            or alarm.massage
            or alarm.enabled
            and alarm.wake_action not in capability.wake_actions
        ):
            raise invalid("option_unavailable")

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        if not self._calendar_page() or alarm.mattress_side is not None:
            return
        with self._operation():
            await self._read_calendar_slot(alarm)
            if (
                alarm.record_identity is not None
                and self.alarm_record_identity(alarm) != alarm.record_identity
            ):
                raise failed("bed_changed")

    def alarm_record_identity(self, alarm: AlarmRequest) -> tuple[int, int] | None:
        if not self._calendar_page() or alarm.mattress_side is not None:
            return None
        return alarm.slot, self._calendar_row(alarm.slot)["bed"]

    async def refresh_alarms(self) -> None:
        if not self._calendar_page():
            raise invalid("option_unavailable")
        with self._operation():
            await self.write_command(codec.record_20_len(5, 1, 0, (0,)))

    def _calendar_row(self, slot: int) -> dict[str, int]:
        row = self._calendar_alarms.get(slot)
        if row is None:
            raise invalid("alarm_refresh_needed")
        return row

    def _publish_calendar_records(self) -> None:
        # The app stores (slot, bed), while the shared native action takes a
        # slot. Only an unambiguous slot can authorize a native write.
        unique: dict[int, dict[str, int]] = {}
        ambiguous: set[int] = set()
        for (slot, _bed), row in self._calendar_records.items():
            if slot in unique:
                ambiguous.add(slot)
            unique[slot] = row
        self._calendar_alarms = {slot: row for slot, row in unique.items() if slot not in ambiguous}
        self._known_calendar_slots.update(unique)
        self._persist_snapshot()
        self._publish_calendar_alarms()

    async def delete_alarm(self, slot: int) -> None:
        if not self._calendar_page():
            raise invalid("option_unavailable")
        row = self._calendar_row(slot)
        with self._operation():
            written = False

            def withdraw() -> None:
                nonlocal written
                written = True
                self._calendar_records = {
                    key: value for key, value in self._calendar_records.items() if key[0] != slot
                }
                self._publish_calendar_records()

            token = _CALENDAR_TARGET.set((slot, row["bed"]))
            try:
                await self._dispatch(codec.record_20_len(5, 2, 1, (slot,)), on_write=withdraw)
            finally:
                _CALENDAR_TARGET.reset(token)
            if not written:
                return
            await asyncio.sleep(0.3)
            await self._write_query(codec.record_20_len(5, 1, 0, (0,)))

    async def _read_calendar_slot(self, alarm: AlarmRequest) -> None:
        if not self._calendar_page() or alarm.mattress_side is not None:
            return
        if any(key[0] == alarm.slot for key in self._calendar_records):
            self._calendar_row(alarm.slot)
            return
        await self._write_query(codec.record_20_len(5, 1, 0, (0,)))
        for _ in range(30):
            if any(key[0] == alarm.slot for key in self._calendar_records):
                self._calendar_row(alarm.slot)
                return
            await asyncio.sleep(0.1)
            self._check(_OPERATION.get() or self._owner())
        raise invalid("alarm_refresh_needed")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        with self._operation():
            if not self._calendar_page() or alarm.mattress_side is not None:
                await super().configure_alarm(alarm)
                return
            await self.check_alarm(alarm)
            from ..richmat_mh.controller import _ALARM_POSITIONS

            identity = alarm.record_identity or self.alarm_record_identity(alarm)
            await self._write_query(codec.record_20_len(5, 1, 0, (0,)))
            for frame in calendar_clock(dt_util.now()):
                await asyncio.sleep(0.2)
                await self._write_query(frame)
            self._classifier.rx_type = "ALARM"

            def packet() -> bytes:
                # Disable preserves the latest reported fields, including any
                # readback received while this operation waited for BLE.
                current = self._calendar_row(alarm.slot)
                return codec.record_20_len(
                    5,
                    1,
                    1,
                    (
                        alarm.slot,
                        current["bed"],
                        alarm.hour if alarm.enabled else current["hour"],
                        alarm.minute if alarm.enabled else current["minute"],
                        p.ALARM_OPTION_CODES[_ALARM_POSITIONS[alarm.wake_action]]
                        if alarm.enabled
                        else current["mode"],
                        int(alarm.enabled)
                        | (
                            sum(1 << (7 - day) for day in alarm.weekdays)
                            if alarm.enabled
                            else current["week"] & 0xFE
                        ),
                    ),
                )

            token = _CALENDAR_TARGET.set(identity)
            try:
                await self._dispatch(packet(), factory=packet)
            finally:
                _CALENDAR_TARGET.reset(token)
            await asyncio.sleep(0.3)
            await self._write_query(codec.record_20_len(5, 1, 0, (0,)))

    @property
    def supports_clock_sync(self) -> bool:
        return self._calendar_page() or (self.route == "C" and self._alarm_page())

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise invalid("clock_sync_not_supported", device_name=self._coordinator.name)
        with self._operation():
            now = dt_util.now()
            frames = (
                calendar_clock(now)
                if self._calendar_page()
                else p.clock_frames(now.hour, now.minute, now.second)
            )
            await self._write_sequence(frames, 0)

    async def _send_clock(self) -> None:
        now = dt_util.now()
        for frame in p.clock_frames(now.hour, now.minute, now.second):
            await self._write_query(frame)

    async def set_snore(self, option: str) -> None:
        if option not in self._snore_options():
            raise invalid("option_unavailable")
        with self._operation() as owner:
            self._classifier.rx_type = "SNORE"
            with self.sent_state(SNORE_KEY(option)):
                await self._dispatch(
                    p.snore_frame(
                        0
                        if option == "off"
                        else next(c for c, name in SNORE_OPTIONS.items() if name == option),
                        owner.mode,
                    )
                )

    async def write_light_timer(self, seconds: int, shown: int) -> None:
        page = self._light_page()
        if page is None or not 0 <= seconds <= (900 if page == "btn_led" else 300):
            raise invalid("option_unavailable")
        key = LIGHT_TIMER_MINUTES_KEY if page == "btn_led" else LIGHT_TIMER_KEY
        with self._operation(), self.sent_state(key(shown)):
            await self._dispatch(p.light_timer_frame(seconds))

    async def set_motor_mode(self, option: str) -> None:
        if option not in self.motor_mode_options:
            raise invalid("option_unavailable")
        name = {"left": "LEFT", "right": "RIGHT"}.get(option, option.capitalize())
        with self._operation(), self.sent_state(MOTOR_MODE_KEY(option)):
            await self.write_command(p.motor_mode_frame(p.MOTOR_MODE_BITS[name]))

    async def set_angle(self, bits: int, angle: int) -> None:
        spec = next((x for x in self._angles() if x[0] == bits), None)
        if spec is None or not spec[2] <= angle <= spec[3]:
            raise invalid("option_unavailable")
        with self._operation():
            await asyncio.sleep(0.1)
            await self.write_command(p.angle_frame(bits, angle))

    async def write_massage_intensity(self, zone: str, value: int) -> None:
        spec = next((x for x in self._intensities() if x[0] == zone), None)
        if spec is None or not spec[2] <= value <= spec[3]:
            raise invalid("option_unavailable")
        values = {**self._intensity, zone: value}
        with self._operation(), self.sent_state(INTENSITY_KEYS[zone](value)):
            await asyncio.sleep(0.1)
            await self.write_command(p.massage_intensity_frame(values["head"], values["foot"]))
        self._intensity = values

    async def normal_pillow(self, side: str, direction: int) -> None:
        with self._operation():
            await super().normal_pillow(side, direction)

    async def normal_pillow_stop(self, side: str) -> None:
        if not self._normal_ready or side not in ("left", "right"):
            raise invalid("option_unavailable")
        owner = _OPERATION.get() or self._owner()
        if self.client is not owner.client or self._session_generation != owner.generation:
            return
        await self._dispatch(
            p.mattress_frame(1 if side == "left" else 2, 6, 0),
            cancel_event=asyncio.Event(),
            cleanup=True,
        )

    async def richmat_mh_aroma(
        self, mode2_startup_minutes: int, mode3_startup_minutes: int, mode3_pause_hours: int
    ) -> None:
        with self._operation():
            await super().richmat_mh_aroma(
                mode2_startup_minutes, mode3_startup_minutes, mode3_pause_hours
            )

    async def _write_query(self, frame: bytes) -> None:
        previous = self._preparing
        self._preparing = True
        try:
            await self._dispatch(frame, cancel_event=asyncio.Event())
        finally:
            self._preparing = previous

    async def _run_session_setup(self) -> None:
        pending = self._pending = SessionFlags()
        self._preparing = True
        try:
            with self._operation():
                await asyncio.sleep(0.3)
                await self._write_query(p.TX_VERSION)
                await asyncio.sleep(0.3)
                self._classifier.rx_type = "INIT"
                frames = (
                    *(p.INIT_VER1 if pending.version == "0001" else p.INIT_VER0),
                    codec.function(1, action="deviceFunctionItemCheckMusic"),
                )
                interval = INIT_INTERVAL_S[pending.version]
                for frame in frames:
                    # Network/media/recognizer capabilities have no bed control.
                    if frame not in (
                        p.TX_SPEECH,
                        codec.function(1, action="deviceFunctionItemCheckMusic"),
                    ):
                        await self._write_query(frame)
                    await asyncio.sleep(interval)
                self._version, self._call_page = pending.version, pending.call_page
                self._dev, self._waist, self._detection = (
                    pending.dev,
                    pending.waist,
                    pending.detection,
                )
                if self._calendar_page():
                    await self._write_query(codec.record_20_len(5, 1, 0, (0,)))
                self._persist_snapshot()
        finally:
            self._pending = None
            self._preparing = False

    def _handle_notification(self, sender: object, data: bytearray) -> None:
        if (
            self._coordinator.controller is not self
            or self.client is not self._owner_client
            or self._coordinator.entry is not self._notification_entry
            or self._entry_data() != self._notification_data
        ):
            return
        super()._handle_notification(sender, data)

    def _apply_init(self, rx: str) -> None:
        local = self._pending is None
        if local:
            self._pending = SessionFlags(
                self._version, self._call_page, dict(self._dev), self._detection, self._waist
            )
        try:
            super()._apply_init(rx)
            if local and self._pending is not None:
                self._dev, self._call_page = self._pending.dev, self._pending.call_page
        finally:
            if local:
                self._pending = None
                self._persist_snapshot()

    def _apply(self, event: p.Event) -> None:
        if event.kind == "calendar":
            frame = bytes.fromhex(event.data)
            if frame[3:6] not in (b"\x05\x01\x02", b"\x05\x01\x03"):
                return
            try:
                slot, bed = int(event.data[12:14]), int(event.data[14:16])
            except ValueError:
                return
            row = {
                "bed": bed,
                "hour": int.from_bytes(frame[8:9], signed=True),
                "minute": int.from_bytes(frame[9:10], signed=True),
                "mode": frame[10],
                "week": frame[11],
            }
            if self._calendar_page():
                self._calendar_rows.append({"slot": slot, **row})
                self._calendar_rows = self._calendar_rows[-64:]
                if 0 <= row["hour"] <= 23 and 0 <= row["minute"] <= 59:
                    self._calendar_records[slot, bed] = row
                else:
                    self._calendar_records.pop((slot, bed), None)
                self.forward_controller_state_update(CALENDAR_ROWS, list(self._calendar_rows))
                self._publish_calendar_records()
            return
        if event.kind == "accessory":
            for offset in range(0, len(event.data) - 9, 10):
                raw = bytes.fromhex(event.data[offset : offset + 10])
                if raw[2] >> 4 == 11:
                    self._accessory.update({"mode": (raw[3] >> 6) & 1, "power": (raw[3] >> 5) & 1})
                elif raw[2] == 0xD2:
                    self._accessory["intensity"] = int.from_bytes(raw[3:4], signed=True)
            self.forward_controller_state_update(ACCESSORY, dict(self._accessory))
            return
        if event.kind in ("mattress_init", "mattress", "waist_init", "waist"):
            if event.kind == "mattress_init" and self._normal_selected:
                self._normal_init(bytes.fromhex(event.data))
            elif event.kind == "mattress" and self._normal_ready:
                self._normal_reply(bytes.fromhex(event.data))
            elif event.kind == "waist_init":
                if self._pending:
                    self._pending.waist = True
                else:
                    self._waist = True
                self._apply_waist({**p.parse_waist_init(event.data), **waist_init(event.data)})
            elif event.kind == "waist" and self._waist:
                self._apply_waist(p.parse_waist_piece(event.data))
            self._persist_snapshot()
            return
        if event.kind == "snore" and self._snore_options():
            if event.data == p.RX_ALARM_SET_SUCCESS:
                self._snore_enabled = True
                self.forward_controller_state_update(SNORE_ENABLED, True)
            elif event.data == p.RX_ALARM_DEL_SUCCESS:
                self._snore_enabled = False
                self.forward_controller_state_updates(SNORE_ENABLED(False), SNORE_KEY("off"))
            self._persist_snapshot()
        if event.kind == "init" and event.data.startswith("6e23"):
            # Reported LED state has its own consumer, independent of c0's dead listener.
            self._apply_lock(event.data[6:8], event.data[4:6])
        # The 6e21 INIT handler compares byte1, so it never selects a snore value.
        super()._apply(event)

    def on_disconnect(self) -> None:
        self._calendar_rows.clear()
        self._calendar_records.clear()
        self._calendar_alarms.clear()
        self._accessory.clear()
        super().on_disconnect()
        self._publish_calendar_alarms()


async def build_classic_controller(ctx: BuildContext) -> BedController:
    if ctx.variant == "sleep":
        await ctx.preload("bedtech.sleep")
        from .sleep import BedTechSleepController

        return BedTechSleepController(ctx.coordinator)
    await ctx.coordinator.hass.async_add_executor_job(catalog, "bedtech_classic")
    return BedTechClassicController(
        ctx.coordinator, variant=ctx.variant or "auto", name=ctx.live_device_name
    )
