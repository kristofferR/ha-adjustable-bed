"""My Side's explicitly selected products, with a fenced physical BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ...app_session import app_session
from ...codec import richmat as codec
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import myside as app
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from ..richmat.transport import AppLink, select_app_link
from ..richmat_app.receive import FrameBuffer
from .protocol import ALARM_QUERY, NAME_QUERY, Alarm, parse, repeat_mask

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext
    from ..lifecycle import ControllerSession

CAPABILITIES: Final = StateKey[list[str]]("myside_capabilities")
ALARMS: Final = StateKey[list[dict[str, int | bool]]]("myside_alarms")
SLEEP_NAME: Final = StateKey[str | None]("myside_sleep_name")


@dataclass(slots=True)
class Owner:
    token: object | None = None


@dataclass(frozen=True, slots=True)
class AlarmAdmission:
    link: AppLink
    generation: int


async def _press(controller: BedController, *, control: str, save: bool = False) -> None:
    await require_controller(controller, MySideController).press(control, save=save)


class MySideController(ProfileExecution[app.MySideProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator)
        if product not in app.PROFILES:
            raise invalid("myside_invalid_product")
        self.profile = app.PROFILES[product]
        self._owner = app_session(coordinator.hass, coordinator.address, "myside", Owner)
        self._token: object | None = None
        self._link: AppLink | None = None
        self._buffer = FrameBuffer()
        self._last_write: float | None = None
        self.features: set[str] = set()
        self.alarms: list[Alarm] = []
        self._alarm_generation = 0
        self._alarm_query_started = False
        self._alarm_queried = False
        # A partial refresh cannot prove an old or pending slot is empty.
        self._occupied_alarm_ids: set[int] = set()
        self._pending_alarm_ids: set[int] = set()
        self._free_alarm_ids: set[int] = set()
        self._alarm_slot_tokens: dict[int, object] = {}
        self.sleep_name: str | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def position_number_specs(self) -> tuple[()]:
        return ()

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.coaxing

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memories

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.profile.coaxing

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.profile.coaxing

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile.coaxing

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        return self.profile.coaxing

    @property
    def auto_enable_massage(self) -> bool:
        return self.profile.coaxing

    @property
    def supports_massage_timer(self) -> bool:
        return self.profile.coaxing

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.profile.coaxing else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    def _live(self, link: AppLink | None = None) -> AppLink:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self._token is None
            or self._owner.token is not self._token
            or self._coordinator.controller is not self
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise BedNotConnectedError("myside_session_ended")
        if self.command_side is not None:
            raise invalid("myside_side_unsupported")
        return current

    def _ordinary(self, code: int, link: AppLink) -> bytes:
        return codec.function(code, single=link.query_single)

    async def _send(
        self,
        data: bytes,
        link: AppLink,
        event: asyncio.Event,
        *,
        deadline: float | None = None,
        before_write: Callable[[], None] | None = None,
    ) -> bool:
        async with self._ble_lock:
            if self._last_write is not None:
                await asyncio.sleep(
                    max(0, self._last_write + self.profile.tick_ms / 1000 - monotonic())
                )
            self._live(link)
            if event.is_set() or deadline is not None and monotonic() > deadline + 1e-9:
                note_frame_skipped()
                return False
            if before_write is not None:
                try:
                    before_write()
                except BaseException:
                    note_frame_skipped()
                    raise
            response = "write-without-response" not in link.tx.properties
            self._coordinator.record_command_trace(
                payload={"hex": data.hex()},
                characteristic_uuid=link.tx.uuid,
                characteristic_handle=link.tx.handle,
                response=response,
                repeat_count=1,
                repeat_delay_ms=self.profile.tick_ms,
                command_origin="myside",
                controller_class=type(self).__name__,
            )
            self._last_write = monotonic()
            # The app removes FIFO items before writing, without a retransmission.
            await settled(link.client.write_gatt_char(link.tx, data, response=response))
            self._live(link)
            note_frame_written(event)
            return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        for _ in range(repeat_count):
            if not await self._send(
                command, link, cancel_event or self._coordinator.cancel_command
            ):
                break

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError("myside_disconnected")
        try:
            link = select_app_link(client, app.TRANSPORTS)
        except ValueError as err:
            raise invalid("myside_write_route_missing") from err
        if link.rx is None:
            raise invalid("myside_notify_required")
        self._link = link
        self._token = self._owner.token = object()
        try:
            await client.start_notify(link.rx, partial(self._notification, link))
            self._live(link)
            await asyncio.sleep(self.profile.startup_ms / 1000)
            event = self._coordinator.cancel_command
            for action in ("CheckClock", "CheckLight", "CheckMusic"):
                await self._send(
                    codec.function(
                        1, action="deviceFunctionItem" + action, single=link.query_single
                    ),
                    link,
                    event,
                )
            if self.profile.coaxing:
                await self._send(codec.calendar(dt_util.now()), link, event)
            if self.profile.sleep:
                await self._send(NAME_QUERY, link, event)
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        link = self._link
        owns = self._token is not None and self._owner.token is self._token
        self.on_disconnect()
        if owns and link is not None and link.rx is not None and link.client.is_connected:
            await link.client.stop_notify(link.rx)

    def on_disconnect(self) -> None:
        owns = self._token is not None and self._owner.token is self._token
        self._link = None
        self._token = None
        self._buffer.pending.clear()
        self._last_write = None
        self.features.clear()
        self.alarms.clear()
        self._alarm_generation += 1
        self._alarm_query_started = self._alarm_queried = False
        self._occupied_alarm_ids.clear()
        self._pending_alarm_ids.clear()
        self._free_alarm_ids.clear()
        self._alarm_slot_tokens.clear()
        self.sleep_name = None
        if owns:
            self._owner.token = None
            self._publish()

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            CAPABILITIES(sorted(self.features)),
            ALARMS([alarm.attributes() for alarm in self.alarms]),
            SLEEP_NAME(self.sleep_name),
        )

    def _notification(
        self, link: AppLink, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        try:
            self._live(link)
        except ConnectionError, ServiceValidationError:
            return
        assert link.rx is not None
        self.forward_raw_notification(link.rx.uuid, bytes(data))
        try:
            for frame in self._buffer.frames(bytes(data)):
                # Capability replies cannot override the product's gates.
                if frame == bytes.fromhex("6e09010078") and self.profile.coaxing:
                    self.features.add("alarm")
                reply = parse(frame)
                if reply is None:
                    continue
                if reply.event == "sleep_name" and self.profile.sleep:
                    self.sleep_name = reply.name
                if reply.alarm is not None and self.profile.coaxing:
                    alarm = reply.alarm
                    # Any fresh same-slot report revokes a deletion's free-slot
                    # proof, even an update that has no displayed record yet.
                    self._free_alarm_ids.discard(alarm.number)
                    self._occupied_alarm_ids.add(alarm.number)
                    self._alarm_slot_tokens[alarm.number] = object()
                    self._alarm_generation += 1
                    known = any(old.number == alarm.number for old in self.alarms)
                    if (
                        reply.event == "alarm_list"
                        or known
                        or alarm.number in self._pending_alarm_ids
                    ):
                        self.alarms = [old for old in self.alarms if old.number != alarm.number]
                        self.alarms.append(alarm)
                        self._pending_alarm_ids.discard(alarm.number)
                        if reply.event == "alarm_list" and self._alarm_query_started:
                            self._alarm_queried = True
        except ValueError:
            self._buffer.pending.clear()
        self._publish()

    def _motors(self) -> tuple[str, ...]:
        return tuple(app.MOTORS) if self.profile.coaxing else tuple(app.MOTORS)[:4]

    def _validate_control(self, control: str, save: bool = False) -> None:
        if control not in (
            *self._motors(),
            *app.presets(self.profile),
            *(app.MASSAGE if self.profile.coaxing else ()),
        ):
            raise invalid("myside_control_unsupported")
        if save and (control not in app.presets(self.profile) or app.PRESETS[control][1] is None):
            raise invalid("myside_save_unsupported")

    @staticmethod
    async def _wait(event: asyncio.Event, seconds: float) -> bool:
        if event.is_set():
            return False
        try:
            await asyncio.wait_for(event.wait(), max(0, seconds))
        except TimeoutError:
            return not event.is_set()
        return False

    async def _release(self, link: AppLink) -> None:
        await self._send(self._ordinary(codec.STOP, link), link, asyncio.Event())
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    async def press(self, control: str, *, save: bool = False, duration_ms: int = 1000) -> None:
        self._validate_control(control, save)
        link, event = self._live(), self._coordinator.cancel_command
        if control in self._motors():
            start = monotonic()
            end = start + self.leased_hold_ms(duration_ms) / 1000
            tick = 1
            fired = False
            try:
                while start + tick * 0.1 <= end + 1e-6:
                    if not await self._wait(event, start + tick * 0.1 - monotonic()):
                        break
                    fired = True
                    if not await self._send(self._ordinary(app.MOTORS[control], link), link, event):
                        break
                    tick = max(tick + 1, int((monotonic() - start + 1e-9) / 0.1) + 1)
            finally:
                if fired:
                    await settled(self._release(link))
            return
        code = app.PRESETS[control][int(save)] if control in app.PRESETS else app.MASSAGE[control]
        assert code is not None
        strength = control in ("massage_head_strengthen", "massage_foot_strengthen")
        try:
            await self._send(self._ordinary(code, link), link, event)
        finally:
            if strength:
                await settled(self._release(link))

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            self._motors()
            + ("flat",)
            + (
                tuple(k for k in app.MASSAGE if k.startswith("massage_timer"))
                if self.profile.coaxing
                else ()
            )
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("myside_hold_invalid")
        if (
            (context := current_command_context()) is not None
            and context.lease is not None
            and control not in self._motors()
        ):
            raise invalid("myside_renewable_hold_unsupported")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control in self._motors():
            await self.press(control, duration_ms=duration_ms)
            return
        link, event = self._live(), self._coordinator.cancel_command
        # Text up/cancel before three seconds invokes the short action. Expiry
        # emits the missing long opcode zero, and suppresses short and STOP.
        expired = await self._wait(event, min(duration_ms, self.profile.long_ms) / 1000)
        if event.is_set():
            return
        if expired and duration_ms >= self.profile.long_ms:
            await self._send(self._ordinary(0, link), link, event)
        else:
            code = app.PRESETS[control][0] if control == "flat" else app.MASSAGE[control]
            await self._send(self._ordinary(code, link), link, event)

    async def stop_all(self) -> None:
        if not CONTROLLER_GESTURE_RELEASE.get():
            await self._release(self._live())

    async def move_head_up(self) -> None:
        await self.press("head_up")

    async def move_head_down(self) -> None:
        await self.press("head_down")

    async def move_feet_up(self) -> None:
        await self.press("foot_up")

    async def move_feet_down(self) -> None:
        await self.press("foot_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down

    async def move_head_stop(self) -> None:
        await self.stop_all()

    move_back_stop = move_head_stop
    move_feet_stop = move_head_stop
    move_legs_stop = move_head_stop

    async def preset_flat(self) -> None:
        await self.press("flat")

    async def preset_zero_g(self) -> None:
        await self.press("zero_gravity")

    async def preset_anti_snore(self) -> None:
        await self.press("anti_snoring")

    async def preset_tv(self) -> None:
        await self.press("tv_position")

    async def preset_memory(self, memory_num: int) -> None:
        await self.press(f"memory{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self.press(f"memory{memory_num}", save=True)

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise invalid("myside_massage_timer_invalid")
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self.press(f"massage_timer{minutes}")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                partial(_press, control=up),
                partial(_press, control=down),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(up, down, press_is_native=True, stop_scope="side"),
            )
            for axis, up, down in (
                ("back", "head_up", "head_down"),
                ("legs", "foot_up", "foot_down"),
            )
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for key in app.presets(self.profile):
            if key in ("anti_snoring", "zero_gravity", "tv_position"):
                buttons.append(
                    catalog_button(
                        f"myside_save_{key}",
                        "Save " + key.replace("_", " "),
                        partial(_press, control=key, save=True),
                        kind=Kind.SAVE,
                        requires_confirmation=True,
                    )
                )
            elif key == "coaxing_mode":
                buttons.append(
                    catalog_button(
                        "myside_coaxing",
                        "Coaxing mode",
                        partial(_press, control=key),
                        kind=Kind.PRESET,
                    )
                )
        if self.profile.coaxing:
            for key in ("head_and_foot_up", "head_and_foot_down"):
                buttons.append(
                    catalog_button(
                        "myside_" + key,
                        key.replace("_", " ").capitalize(),
                        partial(_press, control=key),
                        kind=Kind.MOTOR,
                        invalidates_position=True,
                        scheduler_resource="*",
                        hold=ControllerHoldSpec(key),
                    )
                )
            for key in (
                "massage_head_strengthen",
                "massage_foot_strengthen",
                "massage_mode_change",
                "massage_all_off",
            ):
                buttons.append(
                    catalog_button(
                        "myside_" + key,
                        key.replace("_", " ").capitalize(),
                        partial(_press, control=key),
                        kind=Kind.MASSAGE,
                        scheduler_resource="*",
                    )
                )
        return unique_buttons(buttons)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            str(CAPABILITIES): sorted(self.features),
            str(ALARMS): [alarm.attributes() for alarm in self.alarms],
            str(SLEEP_NAME): self.sleep_name,
        }

    def validate_operation(
        self,
        operation: str,
        *,
        alarm_id: int = 0,
        hour: int = 0,
        minute: int = 0,
        mode: str = "",
        weekdays: tuple[int, ...] = (),
    ) -> None:
        if operation not in ("query", "add", "edit", "delete", "enable", "name"):
            raise invalid("myside_operation_unknown")
        if operation == "name":
            if not self.profile.sleep:
                raise invalid("myside_sleep_unsupported")
            return
        if not self.profile.coaxing:
            raise invalid("myside_alarms_unsupported")
        if operation in ("edit", "delete", "enable") and not self._alarm_queried:
            raise invalid("myside_alarm_query_required")
        if operation in ("edit", "delete", "enable") and not any(
            a.number == alarm_id for a in self.alarms
        ):
            raise invalid("myside_alarm_missing")
        if operation in ("add", "edit"):
            if (
                mode not in app.ALARM_MODES
                or not 0 <= hour <= 23
                or not 0 <= minute <= 59
                or any(type(d) is not int or not 0 <= d <= 6 for d in weekdays)
            ):
                raise invalid("myside_alarm_invalid")
            if operation == "add" and not self._free_alarm_ids:
                raise invalid("myside_alarm_delete_required")

    def alarm_admission(self) -> AlarmAdmission:
        return AlarmAdmission(self._live(), self._alarm_generation)

    def _check_alarm_admission(self, admission: AlarmAdmission) -> None:
        self._live(admission.link)
        if self._alarm_generation != admission.generation:
            raise invalid("myside_alarm_changed")

    async def operation(
        self,
        operation: str,
        *,
        alarm_id: int = 0,
        hour: int = 0,
        minute: int = 0,
        mode: str = "",
        weekdays: tuple[int, ...] = (),
        enabled: bool = True,
        admission: AlarmAdmission | None = None,
    ) -> None:
        self.validate_operation(
            operation, alarm_id=alarm_id, hour=hour, minute=minute, mode=mode, weekdays=weekdays
        )
        link = self._live()
        mutation = operation in ("add", "edit", "delete", "enable")
        if mutation:
            admission = admission or self.alarm_admission()
            self._check_alarm_admission(admission)
        if operation == "query":
            data = ALARM_QUERY
        elif operation == "name":
            data = NAME_QUERY
        elif operation == "delete":
            data = codec.record(5, 2, 1, (alarm_id,))
        elif operation == "enable":
            data = next(a for a in self.alarms if a.number == alarm_id).enabled(enabled).frame()
        else:
            if operation == "add":
                alarm_id = min(self._free_alarm_ids)
            data = Alarm(
                alarm_id, 0, hour, minute, app.PRESETS[mode][0], repeat_mask(weekdays, enabled)
            ).frame()
        mutation_token = object()

        def admit() -> None:
            if operation == "query":
                self._occupied_alarm_ids.update(alarm.number for alarm in self.alarms)
                self.alarms.clear()
                self._alarm_query_started = True
                self._alarm_queried = False
            elif mutation:
                assert admission is not None
                self._check_alarm_admission(admission)
                # Invalidate at the wire boundary: a failed/cancelled write may
                # still reach the bed. Only a fresh report makes it safe to copy.
                self.alarms = [alarm for alarm in self.alarms if alarm.number != alarm_id]
                self._free_alarm_ids.discard(alarm_id)
                self._occupied_alarm_ids.add(alarm_id)
                self._pending_alarm_ids.add(alarm_id)
                self._alarm_slot_tokens[alarm_id] = mutation_token
            else:
                return
            self._alarm_generation += 1
            self._publish()

        sent = await self._send(data, link, self._coordinator.cancel_command, before_write=admit)
        if (
            sent
            and operation == "delete"
            and self._alarm_slot_tokens.get(alarm_id) is mutation_token
        ):
            # Only a newer report for this ID can overrule the delivered delete.
            self._occupied_alarm_ids.discard(alarm_id)
            self._pending_alarm_ids.discard(alarm_id)
            if 1 <= alarm_id <= 7:  # The app's admitted alarm-number bounds.
                self._free_alarm_ids.add(alarm_id)
            self._alarm_generation += 1

    def validate_clock_sync(self) -> None:
        if not self.supports_clock_sync:
            raise invalid("myside_alarms_unsupported")

    async def sync_clock(self) -> None:
        self.validate_clock_sync()
        await self._send(codec.calendar(dt_util.now()), self._live(), self._coordinator.cancel_command)


async def build_controller(ctx: BuildContext) -> MySideController:
    return MySideController(ctx.coordinator, product=ctx.variant or "")
