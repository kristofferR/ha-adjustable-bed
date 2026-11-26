"""Jerome's Adjustable Base over Richmat Nordic and WiLinke transports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_CONTROLLED_SIDE
from ...codec import richmat as codec
from ...command_scheduler import (
    CommandContext,
    current_command_context,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ...command_target import admitted_command_target
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import jerome_adjustable_base as profile
from ...state_keys import LIGHT_TIMER_OPTION, MASSAGE_TIMER_MINUTES
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, massage_button, save_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..richmat_app import protocol
from ..richmat_app.receive import EXACT, FrameBuffer
from .jerome_alarm import RepeatAlarm
from .transport import AppLink, select_app_link

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

SIDE = StateKey[str | None]("jerome_adjustable_base_side")
CLOCK = StateKey[str | None]("jerome_adjustable_base_clock")
RECORDS = StateKey[list[dict[str, object]]]("jerome_adjustable_base_records")
LIGHT = StateKey[bool]("jerome_adjustable_base_light_available")

TICK_S: Final = profile.TICK_MS / 1000
PREFIX: Final = "jerome_adjustable_base_"
ALARM_REPLY_WAIT_S: Final = 1.0
PRESET_NAMES: Final = {
    "tv": "TV",
    "anti_snore": "Anti-snore",
    "zero_g": "Zero gravity",
    "memory_1": "Memory 1",
    "lounge": "Lounge",
    "memory_2": "Memory 2",
}
HELD_CONTROLS: Final = {
    f"{PREFIX}{motor}_{direction}": code
    for motor, codes in profile.MOTORS.items()
    for direction, code in zip(("up", "down"), codes, strict=True)
}


async def _press(controller: BedController, code: int, *, save: bool = False) -> None:
    await require_controller(controller, JeromeAdjustableBaseController).press(code, save=save)


async def _move(controller: BedController, control: str) -> None:
    await controller.hold_control(control, 1000)


async def _select_side(controller: BedController, side: str) -> None:
    require_controller(controller, JeromeAdjustableBaseController)._select_side(side)


@dataclass(frozen=True, slots=True)
class PreparedRepeatAlarm:
    link: AppLink
    operation: str
    record: RepeatAlarm | None


class JeromeAdjustableBaseController(ProfileExecution[profile.Product], BedController):
    """One explicitly selected product and one physical BLE session."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator)
        if product not in profile.PRODUCTS:
            raise invalid("jerome_model_required")
        self.profile = profile.PRODUCTS[product]
        self._link: AppLink | None = None
        self._cleanup_context: CommandContext | None = None
        self._next_write = 0.0
        self._side = "left"
        self._side_supported = False
        self._clock_ready = asyncio.Event()
        self._clock_status: str | None = None
        self._light_ready = False
        self._records: list[RepeatAlarm] = []
        self._edited_schedules: dict[int, RepeatAlarm] = {}
        self._deleted_slots: set[int] = set()
        self._buffer = FrameBuffer()
        self._record_changed = asyncio.Event()
        self._expiry: asyncio.TimerHandle | None = None

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def retain_live_controller_offline(self) -> bool:
        return self.profile.split_head

    @property
    def persisted_app_state(self) -> Mapping[str, object] | None:
        if not self.profile.split_head:
            return None
        return {"side": self._side, "framed": self._side_supported}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self._side = "right" if self.profile.split_head and state.get("side") == "right" else "left"
        self._side_supported = self.profile.split_head and state.get("framed") is True
        self.forward_controller_state_update(SIDE, self._side)

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def _is_current(self, link: AppLink) -> bool:
        return (
            link is self._link
            and link.client is self.client
            and link.client.is_connected
            and self._coordinator.controller is self
        )

    def _current_link(self) -> AppLink:
        link = self._link
        if link is None or not self._is_current(link):
            raise BedNotConnectedError("jerome_session_ended")
        return link

    async def _send(
        self,
        link: AppLink,
        frame: bytes,
        cancel: asyncio.Event | None,
        *,
        expires_at: float | None = None,
        admit_write: Callable[[], bool] | None = None,
        on_delivery: Callable[[], None] | None = None,
        after_write: Callable[[], None] | None = None,
    ) -> bool:
        async with self.ble_lock:
            await asyncio.sleep(max(0, self._next_write - monotonic()))
            if not self._is_current(link):
                raise BedNotConnectedError("jerome_session_ended")
            if (cancel is not None and cancel.is_set()) or (
                expires_at is not None and monotonic() >= expires_at
            ):
                note_frame_skipped()
                return False
            if admit_write is not None and not admit_write():
                note_frame_skipped()
                return False
            response = "write-without-response" not in link.tx.properties
            self._next_write = monotonic() + TICK_S
            self._record_command_trace(
                link.tx.uuid, frame, characteristic=link.tx, response=response
            )

            async def write() -> None:
                # Cancellation can arrive while the backend still owns the write.
                await link.client.write_gatt_char(link.tx, frame, response=response)
                if cancel is None:
                    note_write_not_counted()
                else:
                    note_frame_written(cancel)
                if on_delivery is not None:
                    on_delivery()
                if after_write is not None and self._is_current(link):
                    after_write()

            await settled(write(), eager_start=True)
            return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = profile.TICK_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._current_link()
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and not await self._wait(repeat_delay_ms / 1000, cancel):
                break
            if not await self._send(link, command, cancel):
                break

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        self.on_disconnect()
        try:
            link = select_app_link(client, profile.TRANSPORTS, unique_service=True)
        except ValueError as err:
            raise invalid("jerome_gatt_route") from err
        self._link = link
        self._side_supported = not link.query_single
        self.forward_controller_state_update(SIDE, self._side)
        try:
            if link.rx is not None:
                await client.start_notify(link.rx, partial(self._notification, link))
            action, code = profile.EXIT_MODE
            await self._send(
                link, codec.function(code, action=action, single=link.query_single), None
            )
            await asyncio.sleep(profile.PROBE_DELAY_S)
            for action, code in profile.PROBES:
                await self._send(
                    link, codec.function(code, action=action, single=link.query_single), None
                )
            await self._send(link, codec.calendar(dt_util.now(), build=codec.record_20_len), None)
        except BaseException:
            self.on_disconnect()
            raise

    def _notification(
        self, link: AppLink, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if not self._is_current(link):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        try:
            for frame in self._buffer.frames(bytes(data)):
                self._accept(frame)
        except ValueError, IndexError:
            self._buffer.pending.clear()
        if self._buffer.pending:
            self._expiry = asyncio.get_running_loop().call_later(
                profile.RECEIVE_EXPIRY_S, self._buffer.pending.clear
            )

    def _accept(self, frame: bytes) -> None:
        event = EXACT.get(frame.hex())
        if event == "clock_available":
            self._clock_ready.set()
            if self._clock_status is None:
                self._clock_status = "available"
                self.forward_controller_state_update(CLOCK, self._clock_status)
        elif event == "light_available" and self.profile.wave:
            self._light_ready = True
            self.forward_controller_state_update(LIGHT, True)
        elif event in ("alarm_saved", "alarm_cancelled") and not self.profile.split_head:
            self._clock_status = "saved" if event == "alarm_saved" else "cancelled"
            self.forward_controller_state_update(CLOCK, self._clock_status)
        elif self.profile.split_head and (decoded := RepeatAlarm.decode(frame)) is not None:
            direction, record = decoded
            if record.slot in self._deleted_slots:
                return
            if (expected := self._edited_schedules.get(record.slot)) is not None:
                # Earlier replies can still arrive after the new schedule is confirmed.
                # Keep matching by schedule while the receiver reports the enabled
                # bit and opaque byte.
                schedule = replace(record.with_enabled(False), raw_7=expected.raw_7)
                if schedule != expected:
                    return
                self._records = [cached for cached in self._records if cached.slot != record.slot]
                self._records.append(record)
            elif direction == 2:
                if record not in self._records:
                    self._records.append(record)
            else:
                for i, old in enumerate(self._records):
                    if old.slot == record.slot:
                        self._records[i] = record
                        break
            self._record_changed.set()
            self._publish_records()

    def _publish_records(self) -> None:
        self.forward_controller_state_update(
            RECORDS, [record.attributes() for record in self._records]
        )

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.rx is not None and link.client.is_connected:
            await link.client.stop_notify(link.rx)

    def on_disconnect(self) -> None:
        self._link = None
        self._cleanup_context = None
        self._next_write = 0.0
        self._clock_ready.clear()
        self._clock_status = None
        self._light_ready = False
        self._buffer.pending.clear()
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        self._records.clear()
        self._edited_schedules.clear()
        self._deleted_slots.clear()
        self._record_changed.set()
        self.forward_controller_state_updates(
            CLOCK(None),
            LIGHT(False),
            RECORDS([]),
            LIGHT_TIMER_OPTION(None),
            MASSAGE_TIMER_MINUTES(None),
        )

    def _select_side(self, side: str) -> None:
        if not self.profile.split_head or side not in self._side_options:
            raise invalid("jerome_side_unavailable")
        self._side = side
        self.forward_controller_state_update(SIDE, side)

    @property
    def _side_options(self) -> tuple[str, ...]:
        return ("left", "right") if self._side_supported else ("left",)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.profile.split_head:
            return ()
        return (
            ControllerSelectSpec(
                PREFIX + "side",
                PREFIX + "side",
                SIDE,
                self._side_options,
                _select_side,
                local_select_fn=self._select_side,
                card=CARD_CONTROLLED_SIDE,
            ),
        )

    @property
    def selected_command_target(self) -> str | None:
        return self._side if self.profile.split_head else None

    def _wire_side(self, link: AppLink) -> int:
        side = admitted_command_target(self._coordinator) or self._side
        if link.query_single and side == "right":
            raise invalid("jerome_select_left")
        return int(side == "right")

    @staticmethod
    async def _wait(seconds: float, cancel: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), timeout=seconds)
        except TimeoutError:
            return not cancel.is_set()
        return False

    async def press(self, code: int, *, save: bool = False) -> None:
        link = self._current_link()
        side = self._wire_side(link)
        cancel = self._coordinator.cancel_command
        if save and not await self._wait(profile.PRESET_SAVE_S, cancel):
            note_frame_skipped()
            return
        await self._send(link, codec.function(code, side, single=link.query_single), cancel)

    async def _hold(self, code: int, duration_ms: int = 1000) -> None:
        link = self._current_link()
        side = self._wire_side(link)
        cancel = self._coordinator.cancel_command
        frame = codec.function(code, side, single=link.query_single)
        start = monotonic()
        duration_ms = self.leased_hold_ms(duration_ms)
        tick = 1
        context = current_command_context()
        try:
            while tick * profile.TICK_MS <= duration_ms:
                scheduled = start + tick * TICK_S
                if not await self._wait(max(0, scheduled - monotonic()), cancel):
                    note_frame_skipped()
                    break
                if not await self._send(link, frame, cancel, expires_at=scheduled + TICK_S):
                    break
                tick = max(tick + 1, int((monotonic() - start) / TICK_S) + 1)
        finally:
            if self._is_current(link):
                # Even a release before the first direction tick sends one END.
                await settled(self._stop(link, side, owner=context), eager_start=True)

    async def _stop(self, link: AppLink, side: int, *, owner: CommandContext | None = None) -> None:
        def acknowledge() -> None:
            if owner is not None:
                owner.cleanup_stop_sent = True
                self._cleanup_context = owner

        await self._send(
            link,
            codec.function(codec.STOP, side, single=link.query_single),
            None,
            after_write=acknowledge,
        )

    async def stop_all(self) -> None:
        link = self._current_link()
        context = current_command_context()
        owner = self._cleanup_context
        if (
            context is not None
            and owner is not None
            and any(previous is owner for previous in context.preempted_contexts)
            and owner.cleanup_stop_sent
        ):
            owner.cleanup_stop_sent = False
            self._cleanup_context = None
            return
        await self._stop(link, self._wire_side(link))

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                motor,
                motor,
                partial(_move, control=f"{PREFIX}{motor}_up"),
                partial(_move, control=f"{PREFIX}{motor}_down"),
                lambda controller: controller.stop_all(),
                hold=ControllerMotorHoldSpec(
                    f"{PREFIX}{motor}_up",
                    f"{PREFIX}{motor}_down",
                    stop_scope="side",
                    press_is_native=True,
                ),
            )
            for motor in profile.MOTORS
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(HELD_CONTROLS)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in HELD_CONTROLS
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("jerome_hold_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._hold(HELD_CONTROLS[control], duration_ms)

    async def move_head_up(self) -> None:
        await self._hold(profile.MOTORS["head"][0])

    async def move_head_down(self) -> None:
        await self._hold(profile.MOTORS["head"][1])

    async def move_feet_up(self) -> None:
        await self._hold(profile.MOTORS["feet"][0])

    async def move_feet_down(self) -> None:
        await self._hold(profile.MOTORS["feet"][1])

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2 if self.profile.wave else 1

    @property
    def supports_preset_lounge(self) -> bool:
        return self.profile.wave

    async def _preset(self, name: str, *, save: bool = False) -> None:
        if name not in self.profile.preset_names:
            raise invalid("jerome_preset_unavailable")
        await self.press(profile.PRESETS[name][int(save)], save=save)

    async def preset_flat(self) -> None:
        await self.press(profile.FLAT)

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_lounge(self) -> None:
        await self._preset("lounge")

    async def preset_memory(self, memory_num: int) -> None:
        await self._preset(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self._preset(f"memory_{memory_num}", save=True)

    @property
    def supports_massage_timer(self) -> bool:
        return self.profile.wave

    @property
    def auto_enable_massage(self) -> bool:
        return self.profile.wave

    @property
    def massage_timer_options(self) -> list[int]:
        return list(profile.MASSAGE_TIMERS) if self.profile.wave else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.profile.wave or minutes not in profile.MASSAGE_TIMERS:
            raise invalid("jerome_massage_duration")
        link = self._current_link()
        frame = codec.function(
            profile.MASSAGE_TIMERS[minutes], self._wire_side(link), single=link.query_single
        )
        with self.sent_state(
            MASSAGE_TIMER_MINUTES(minutes), is_current=lambda: self._is_current(link)
        ):
            await self._send(link, frame, self._coordinator.cancel_command)

    @property
    def supports_light_timer(self) -> bool:
        return self.profile.wave

    @property
    def light_timer_available_fn(self) -> Callable[[BedController], bool]:
        return lambda controller: (
            isinstance(controller, JeromeAdjustableBaseController) and controller._light_ready
        )

    @property
    def light_timer_options(self) -> list[str]:
        return list(profile.LIGHT_TIMERS) if self.profile.wave else []

    async def set_light_timer(self, timer_option: str) -> None:
        self._require_light()
        if timer_option not in profile.LIGHT_TIMERS:
            raise invalid("jerome_light_timeout")
        link = self._current_link()
        with self.sent_state(
            LIGHT_TIMER_OPTION(timer_option), is_current=lambda: self._is_current(link)
        ):
            await self._send(
                link,
                protocol.light_timer(profile.LIGHT_TIMERS[timer_option]),
                self._coordinator.cancel_command,
            )

    def _require_light(self) -> None:
        if not self._light_ready:
            raise invalid("jerome_light_not_reported")

    async def toggle_light(self) -> None:
        self._require_light()
        await self.press(profile.LIGHT_TOGGLE)

    async def white_light(self) -> None:
        self._require_light()
        await self.write_command(codec.rgb(255, 255, 255))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            save_button(
                PREFIX + "save_" + name,
                "Save " + PRESET_NAMES[name],
                partial(_press, code=profile.PRESETS[name][1], save=True),
            )
            for name in self.profile.preset_names
            if not name.startswith("memory_")
        ]
        if not self.profile.wave:
            return tuple(specs)
        specs.extend(
            massage_button(PREFIX + f"massage_{code:02x}", name, partial(_press, code=code))
            for name, code in profile.WAVE_MASSAGE.items()
        )
        return unique_buttons(
            [
                *specs,
                catalog_button(
                    PREFIX + "light_toggle",
                    "Toggle under-bed light",
                    lambda controller: require_controller(controller, type(self)).toggle_light(),
                    kind=Kind.LIGHT,
                ),
                catalog_button(
                    PREFIX + "light_white",
                    "Select white light",
                    lambda controller: require_controller(controller, type(self)).white_light(),
                    kind=Kind.LIGHT,
                ),
            ]
        )

    @property
    def has_dynamic_buttons(self) -> bool:
        return self.profile.wave

    def controller_button_available(self, key: str) -> bool:
        return not key.startswith(PREFIX + "light_") or self._light_ready

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                PREFIX + "clock",
                PREFIX + "clock",
                CLOCK,
                "mdi:alarm",
                attribute_keys=(RECORDS,) if self.profile.split_head else (),
            ),
        )

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=self.profile.preset_names,
            weekdays=self.profile.split_head,
            slots=7 if self.profile.split_head else 1,
            requires_slot=self.profile.split_head,
            confirm_actions=frozenset(
                name for name in self.profile.preset_names if name.startswith("memory_")
            ),
            live_check=True,
        )

    async def _require_clock(self, link: AppLink) -> None:
        try:
            await asyncio.wait_for(self._clock_ready.wait(), timeout=ALARM_REPLY_WAIT_S)
        except TimeoutError:
            raise invalid("jerome_clock_not_reported") from None
        if not self._is_current(link):
            raise BedNotConnectedError("jerome_session_ended")

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        link = self._current_link()
        await self._require_clock(link)
        if self.profile.split_head and not alarm.enabled:
            await self._read_record(link, alarm.slot)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        link = self._current_link()
        await self._require_clock(link)
        cancel = self._coordinator.cancel_command
        if self.profile.split_head:
            record = (
                RepeatAlarm.edited(
                    alarm.slot,
                    alarm.hour,
                    alarm.minute,
                    profile.PRESETS[alarm.wake_action][0],
                    alarm.weekdays,
                )
                if alarm.enabled
                else (await self._read_record(link, alarm.slot)).with_enabled(False)
            )
            written = await self._send(
                link,
                record.encode(),
                cancel,
                after_write=(
                    partial(self._invalidate_record, alarm.slot, edited=record)
                    if alarm.enabled
                    else None
                ),
            )
            if alarm.enabled and written and self._is_current(link) and not cancel.is_set():
                await self._send(link, protocol.QUERY["alarms"], cancel)
            return
        minutes = alarm.minutes_until(dt_util.now()) if alarm.enabled else 0
        code = profile.PRESETS[alarm.wake_action][0] if alarm.enabled else 0
        for frame in codec.countdown(minutes, code):
            if not await self._send(link, frame, cancel):
                break

    def _first_record(self, slot: int) -> RepeatAlarm | None:
        return next((record for record in self._records if record.slot == slot), None)

    def _invalidate_record(self, slot: int, *, edited: RepeatAlarm | None = None) -> None:
        if edited is None:
            self._edited_schedules.pop(slot, None)
            self._deleted_slots.add(slot)
        else:
            self._deleted_slots.discard(slot)
            self._edited_schedules[slot] = edited.with_enabled(False)
        self._records = [record for record in self._records if record.slot != slot]
        self._publish_records()

    async def _read_record(self, link: AppLink, slot: int) -> RepeatAlarm:
        if (record := self._first_record(slot)) is not None:
            return record
        cancel = self._coordinator.cancel_command
        if await self._send(link, protocol.QUERY["alarms"], cancel):
            try:
                async with asyncio.timeout(ALARM_REPLY_WAIT_S):
                    while self._is_current(link) and not cancel.is_set():
                        if (record := self._first_record(slot)) is not None:
                            return record
                        self._record_changed.clear()
                        await self._record_changed.wait()
            except TimeoutError:
                pass
        raise invalid("jerome_alarm_slot_not_reported")

    async def prepare_repeat_alarm(self, operation: str, slot: int | None) -> PreparedRepeatAlarm:
        link = self._current_link()
        await self._require_clock(link)
        record = await self._read_record(link, slot) if slot is not None else None
        return PreparedRepeatAlarm(link, operation, record)

    def repeat_alarm_plan_is_current(self, plan: PreparedRepeatAlarm) -> bool:
        record = plan.record
        return self._is_current(plan.link) and (
            record is None or self._first_record(record.slot) == record
        )

    async def _refresh_repeat_alarms(self, link: AppLink, cancel: asyncio.Event) -> None:
        controller = self
        if self._edited_schedules or self._deleted_slots:
            # List records have no request ID or end marker. A full BLE reconnect
            # is the only way to retire delayed replies to the old requests.
            if cancel.is_set():
                return
            coordinator = self._coordinator
            generation = coordinator.connection_generation
            edits, deleted = self._edited_schedules.copy(), self._deleted_slots.copy()

            async def retire() -> None:
                try:
                    released = await coordinator.async_disconnect("jerome_alarm_refresh")
                finally:
                    # A failed release can restart notifications on the old BLE link.
                    if link.client.is_connected:
                        live = coordinator.controller
                        if isinstance(live, JeromeAdjustableBaseController):
                            live._edited_schedules.update(edits)
                            live._deleted_slots.update(deleted)
                            blocked = edits.keys() | deleted
                            live._records = [r for r in live._records if r.slot not in blocked]
                            live._publish_records()
                if not released or link.client.is_connected:
                    raise BedNotConnectedError("jerome_alarm_refresh_needs_link")

            await settled(retire())
            if cancel.is_set():
                return
            if not await coordinator.async_ensure_connected(reset_timer=False):
                raise BedNotConnectedError
            if coordinator.connection_generation == generation:
                raise BedNotConnectedError("jerome_alarm_refresh_needs_link")
            live = coordinator.controller
            if not isinstance(live, JeromeAdjustableBaseController) or not live.profile.split_head:
                raise invalid("bed_changed")
            controller = live
            link = controller._current_link()
            await controller._require_clock(link)

        def begin_query() -> bool:
            # A notification can arrive within the write, so clear before it.
            controller._records.clear()
            controller._publish_records()
            return True

        await controller._send(link, protocol.QUERY["alarms"], cancel, admit_write=begin_query)

    async def execute_repeat_alarm(
        self,
        plan: PreparedRepeatAlarm,
        *,
        admit_write: Callable[[], bool] | None = None,
        on_delivery: Callable[[], None] | None = None,
    ) -> None:
        def current() -> bool:
            if not self.repeat_alarm_plan_is_current(plan):
                raise invalid("bed_changed")
            return admit_write is None or admit_write()

        link, record = plan.link, plan.record
        cancel = self._coordinator.cancel_command
        if record is None:
            if current():
                await self._refresh_repeat_alarms(link, cancel)
        elif plan.operation == "delete":
            await self._send(
                link,
                protocol.delete_alarm(record.slot),
                cancel,
                admit_write=current,
                on_delivery=on_delivery,
                after_write=partial(self._invalidate_record, record.slot),
            )
        else:
            await self._send(
                link,
                record.with_enabled(True).encode(),
                cancel,
                admit_write=current,
                on_delivery=on_delivery,
            )

    async def sync_clock(self) -> None:
        await self.write_command(codec.calendar(dt_util.now(), build=codec.record_20_len))


async def build_controller(ctx: BuildContext) -> JeromeAdjustableBaseController:
    return JeromeAdjustableBaseController(ctx.coordinator, product=ctx.variant or "")
