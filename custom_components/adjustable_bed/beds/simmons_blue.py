"""Simmons Blue session, held controls and native alarm actions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..alarm import WEEKDAYS, AlarmCapability, AlarmRequest
from ..card import CardRole, motor_card
from ..command_scheduler import note_frame_skipped, note_frame_written, note_write_not_counted
from ..const import (
    CONF_PRODUCT_TYPE,
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from ..controller_state import StateKey, StateUpdate
from ..errors import BedNotConnectedError, bluetooth_errors_translated, invalid
from ..profiles import simmons_blue as app
from ..profiles.okin_nframe import OkinNFrameProfile
from .base import BedController, ProfileExecution, require_controller
from .cancellation import cancellable, settled
from .catalog_buttons import Kind, catalog_button
from .entity_specs import ControllerButtonSpec, ControllerHoldSpec, ControllerStateSensorSpec
from .okin_nframe import OkinNFrameController

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator
    from .builder import BuildContext
    from .lifecycle import ControllerSession

_LOGGER = logging.getLogger(__name__)
_WRITE_TIMEOUT_S: Final = 15
_ALARM_REPLY_TIMEOUT_S: Final = 2
_NOTIFY_ATTEMPTS: Final = 3
_MOTORS: Final = (
    ("first", "First section"),
    ("second", "Second section"),
    ("combined", "Combined sections"),
)
_PRESETS: Final = {
    "relax": "Relax",
    "tv": "TV position",
    "anti_snore": "Anti-snore",
    "incline": "Incline",
}
_MODE_NAMES: Final = {value: app.WAKE_LABELS[key] for key, value in app.WAKE_MODES.items()}


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


@dataclass(frozen=True, slots=True)
class _AlarmKeys:
    time: StateKey[str | None]
    enabled: StateKey[bool]
    mode: StateKey[str | None]
    days: StateKey[tuple[str, ...]]


_ALARMS: Final = {
    slot: _AlarmKeys(
        StateKey(f"simmons_blue_alarm_{slot}_time"),
        StateKey(f"simmons_blue_alarm_{slot}_enabled"),
        StateKey(f"simmons_blue_alarm_{slot}_mode"),
        StateKey(f"simmons_blue_alarm_{slot}_weekdays"),
    )
    for slot in app.SLOTS
}


class SimmonsBlueController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
    """The four layouts share one write stream and alarm notification format."""

    profile = app.PROFILE

    def __init__(self, coordinator: AdjustableBedCoordinator, layout: app.Layout) -> None:
        super().__init__(coordinator)
        self._layout = layout
        self._link: _Link | None = None
        self._notifying = False
        self._reports: dict[int, app.AlarmRecord] = {}
        self._records: dict[int, app.AlarmRecord] = {}
        self._reply = asyncio.Event()

    @property
    def control_characteristic_uuid(self) -> str:
        return NORDIC_UART_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return False  # The app does not identify physical cover axes.

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return (
            "flat" not in self.held_control_options
        )  # E Balance's one-shot Flat can outlive its link.

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return self._layout.held

    def _is_live(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _live(self) -> _Link:
        link = self._link
        if link is None or not self._is_live(link):
            raise BedNotConnectedError
        return link

    def _build_command(self, command_value: int) -> bytes:
        from ..codec.okin_nframe import frame40

        return frame40(command_value)

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        roles = {
            char.uuid.lower(): char
            for service in client.services
            if service.uuid.lower() == NORDIC_UART_SERVICE_UUID
            for char in service.characteristics
        }
        write = roles.get(NORDIC_UART_WRITE_CHAR_UUID)
        notify = roles.get(NORDIC_UART_READ_CHAR_UUID)
        if (
            write is None
            or "write" not in write.properties
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise BedNotConnectedError("simmons_blue_gatt")
        self._link = _Link(client, write, notify)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()

        def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._is_live(link):
                return
            payload = bytes(data)
            self.forward_raw_notification(link.notify.uuid, payload)
            if (record := app.parse_alarm(payload)) is not None:
                self._reports[record.slot] = record
                self._publish_alarm(record)
                self._reply.set()

        async with self.ble_lock:
            for attempt in range(_NOTIFY_ATTEMPTS):
                if not self._is_live(link):
                    raise BedNotConnectedError
                try:
                    if self._notifying:
                        await link.client.stop_notify(link.notify)
                        self._notifying = False
                    await link.client.start_notify(link.notify, receive)
                except (BleakError, TimeoutError):
                    if attempt == _NOTIFY_ATTEMPTS - 1:
                        raise
                else:
                    if not self._is_live(link):
                        raise BedNotConnectedError
                    self._notifying = True
                    return

    async def stop_notify(self) -> None:
        link = self._link
        async with self.ble_lock:
            if link is not None and self._is_live(link) and self._notifying:
                await link.client.stop_notify(link.notify)
                self._notifying = False

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._reports.clear()
        self._reply.set()

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        if not session.is_current():
            raise BedNotConnectedError
        link = self._live()
        try:
            await self._write(link, app.clock_frame(dt_util.now()), asyncio.Event(), track=False)
        except BleakError, TimeoutError:
            if not self._is_live(link):
                raise
            _LOGGER.debug("Simmons Blue clock sync on connect failed", exc_info=True)

    async def _write(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        track: bool = True,
        validate: Callable[[], None] | None = None,
        deadline: float | None = None,
    ) -> bool:
        async def transmit() -> None:
            with bluetooth_errors_translated():
                async with asyncio.timeout(_WRITE_TIMEOUT_S):
                    await link.client.write_gatt_char(link.write, frame, response=True)
            if track:
                note_frame_written(cancel)
            else:
                note_write_not_counted()

        async with self.ble_lock:
            if cancel.is_set() or (
                deadline is not None and asyncio.get_running_loop().time() >= deadline
            ):
                note_frame_skipped()
                return False
            if not self._is_live(link):
                raise BedNotConnectedError
            if validate is not None:
                validate()
            self._record_command_trace(
                link.write.uuid, frame, response=True, characteristic=link.write
            )
            await settled(transmit(), eager_start=True)
            if not self._is_live(link):
                raise BedNotConnectedError
            return True

    @staticmethod
    async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
        if seconds > 0:
            try:
                async with asyncio.timeout(seconds):
                    await cancel.wait()
            except TimeoutError:
                pass
        return cancel.is_set()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event or self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        for index in range(repeat_count):
            start = loop.time()
            if not await self._write(link, command, cancel):
                return
            if index < repeat_count - 1 and await self._pause(
                cancel, start + repeat_delay_ms / 1000 - loop.time()
            ):
                note_frame_skipped()
                return

    async def _release(self, link: _Link) -> None:
        await self._write(link, app.control("stop"), asyncio.Event(), track=False)

    async def _hold(self, action: str, duration_ms: int) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        frame = app.control(action)
        pulses = (duration_ms + app.REFRESH_MS - 1) // app.REFRESH_MS
        async with self.releasing(lambda: self._release(link)):
            for index in range(pulses):
                start = loop.time()
                if index and start >= deadline:
                    note_frame_skipped()
                    return
                if not await self._write(link, frame, cancel, deadline=deadline):
                    return
                another = index < pulses - 1
                until = min(deadline, start + app.REFRESH_MS / 1000) if another else deadline
                if await self._pause(cancel, until - loop.time()):
                    if another:
                        note_frame_skipped()
                    return

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise self.not_supported(control)
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise invalid("hold_lease_duration", min=1, max=60000)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._hold(control, self.leased_hold_ms(duration_ms))

    async def press(self, control: str) -> None:
        duration = min(60000, self._coordinator.motor_pulse_count * app.REFRESH_MS)
        await self.hold_control(control, duration)

    stop_all = move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = (
        OkinNFrameController._send_stop
    )

    async def move_head_up(self) -> None:
        raise self.not_supported("head")

    async def move_head_down(self) -> None:
        raise self.not_supported("head")

    async def move_back_up(self) -> None:
        raise self.not_supported("back")

    async def move_back_down(self) -> None:
        raise self.not_supported("back")

    async def move_legs_up(self) -> None:
        raise self.not_supported("legs")

    async def move_legs_down(self) -> None:
        raise self.not_supported("legs")

    async def move_feet_up(self) -> None:
        raise self.not_supported("feet")

    async def move_feet_down(self) -> None:
        raise self.not_supported("feet")

    async def preset_flat(self) -> None:
        if "flat" in self.held_control_options:
            await self.press("flat")
        else:
            await self.write_command(app.control("flat"))

    def _memory(self, slot: int) -> str:
        if type(slot) is not int or not 1 <= slot <= self.memory_slot_count:
            raise self.not_supported(f"memory {slot}")
        return f"memory_{slot}"

    async def preset_memory(self, memory_num: int) -> None:
        await self._hold(self._memory(memory_num), app.REFRESH_MS)

    async def program_memory(self, memory_num: int) -> None:
        await self._hold(self._memory(memory_num), app.SAVE_HOLD_MS)

    async def lights_toggle(self) -> None:
        await self.write_command(app.control("light"))

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if key == "preset_flat" and "flat" in self.held_control_options:
            return ControllerHoldSpec("flat")
        return None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def action_for(control: str) -> Callable[[BedController], Coroutine[object, object, None]]:
            return lambda ctrl: require_controller(ctrl, SimmonsBlueController).press(control)

        specs = [
            ControllerButtonSpec(
                control,
                f"{'Raise' if direction == 'up' else 'Lower'} {label.lower()}",
                action_for(control),
                icon=f"mdi:chevron-{direction}",
                translation_key=f"simmons_blue_{control}",
                card=motor_card(f"{axis}_section", role),
                hold=ControllerHoldSpec(control),
                combine_sides=True,
            )
            for axis, label in _MOTORS
            for direction, role in (("up", CardRole.UP), ("down", CardRole.DOWN))
            if (control := f"{axis}_{direction}") in self.held_control_options
        ]
        for control, label in _PRESETS.items():
            if control in self.held_control_options:
                spec = catalog_button(
                    control,
                    label,
                    action_for(control),
                    kind=Kind.PRESET,
                    hold=ControllerHoldSpec(control),
                    combine_sides=True,
                )
                if spec is not None:
                    specs.append(spec)
        specs.append(
            ControllerButtonSpec(
                "refresh_alarms",
                "Refresh alarms",
                lambda ctrl: require_controller(ctrl, SimmonsBlueController).refresh_alarms(),
                icon="mdi:alarm",
                diagnostic=True,
                cancel_movement=False,
            )
        )
        return tuple(specs)

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=tuple(app.WAKE_MODES), slots=3, weekdays=True, live_check=True
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if type(alarm.slot) is not int or alarm.slot not in app.SLOTS:
            raise invalid(
                "alarm_value_out_of_range",
                device_name=self._coordinator.name,
                option="slot",
                min=1,
                max=3,
            )
        if alarm.enabled and alarm.wake_action not in app.WAKE_MODES:
            raise invalid(
                "alarm_wake_action_not_supported",
                device_name=self._coordinator.name,
                wake_action=alarm.wake_action,
                wake_actions=", ".join(app.WAKE_MODES),
            )

    async def sync_clock(self) -> None:
        await self.write_command(app.clock_frame(dt_util.now()))

    async def refresh_alarms(self) -> None:
        await self._query_alarms(self._live(), app.SLOTS, self._coordinator.cancel_command)

    async def _query_alarms(
        self, link: _Link, slots: tuple[int, ...], cancel: asyncio.Event, *, track: bool = True
    ) -> dict[int, app.AlarmRecord]:
        before: dict[int, app.AlarmRecord | None] = {}
        for slot in slots:

            def capture(slot: int = slot) -> None:
                before[slot] = self._reports.get(slot)

            if not await self._write(
                link, app.query_alarm(slot), cancel, validate=capture, track=track
            ):
                return {}

        try:
            async with asyncio.timeout(_ALARM_REPLY_TIMEOUT_S):
                while any(self._reports.get(slot) is before[slot] for slot in slots):
                    self._reply.clear()
                    if not self._is_live(link):
                        raise BedNotConnectedError
                    await cancellable(self._reply.wait(), cancel)
        except TimeoutError:
            # A GATT acknowledgement does not identify the settings stored by the bed.
            pass
        if not self._is_live(link):
            raise BedNotConnectedError
        return {
            slot: record
            for slot in slots
            if (record := self._reports.get(slot)) is not None and record is not before[slot]
        }

    async def _disable_record(self, slot: int, *, refresh: bool = False) -> app.AlarmRecord:
        link, cancel = self._live(), self._coordinator.cancel_command
        record = self._reports.get(slot)
        if refresh or record is None:
            record = (await self._query_alarms(link, (slot,), cancel, track=False)).get(slot)
        if cancel.is_set():
            raise asyncio.CancelledError
        if record is None or not (record.hour < 24 and record.minute < 60):
            raise invalid("simmons_blue_alarm_not_reported", slot=slot)
        return record

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        if not alarm.enabled:
            await self._disable_record(alarm.slot, refresh=True)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, cancel = self._live(), self._coordinator.cancel_command
        previous = None if alarm.enabled else await self._disable_record(alarm.slot)
        record = (
            app.AlarmRecord(
                alarm.slot,
                app.alarm_week(alarm.weekdays),
                app.WAKE_MODES[alarm.wake_action],
                alarm.hour,
                alarm.minute,
                1,
            )
            if previous is None
            else app.AlarmRecord(alarm.slot, 0, 9, previous.hour, previous.minute, 0)
        )

        def still_current() -> None:
            if previous is not None and self._reports.get(record.slot) != previous:
                raise invalid("simmons_blue_alarm_changed", slot=record.slot)

        reported = self._reports.get(record.slot)
        packet = app.alarm_frame(
            record.slot, record.week, record.mode, record.hour, record.minute, record.enabled
        )
        if not await self._write(link, packet, cancel, validate=still_current):
            return
        if self._reports.get(record.slot) is reported:
            # Do not re-use the old live record if the follow-up read never arrives.
            self._reports.pop(record.slot, None)
        await self._query_alarms(link, (record.slot,), cancel)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                str(keys.time),
                str(keys.time),
                keys.time,
                "mdi:alarm",
                attribute_keys=(keys.enabled, keys.mode, keys.days),
            )
            for keys in _ALARMS.values()
        )

    @staticmethod
    def _alarm_updates(record: app.AlarmRecord) -> tuple[StateUpdate, ...]:
        keys = _ALARMS[record.slot]
        valid = 0 <= record.hour <= 23 and 0 <= record.minute <= 59
        return (
            keys.time(f"{record.hour:02d}:{record.minute:02d}" if valid else None),
            keys.enabled(bool(record.enabled)),
            keys.mode(_MODE_NAMES.get(record.mode)),
            keys.days(
                tuple(
                    day
                    for index, day in enumerate(WEEKDAYS)
                    if record.week & (1 << ((index + 1) % 7))
                )
            ),
        )

    def _publish_alarm(self, record: app.AlarmRecord) -> None:
        self._records[record.slot] = record
        self.forward_controller_state_updates(*self._alarm_updates(record))

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {
            str(slot): [r.week, r.mode, r.hour, r.minute, r.enabled]
            for slot, r in self._records.items()
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        for slot in app.SLOTS:
            values = state.get(str(slot))
            if (
                not isinstance(values, list)
                or len(values) != 5
                or not all(type(value) is int and 0 <= value <= 255 for value in values)
            ):
                continue
            self._publish_alarm(app.AlarmRecord(slot, *values))


async def build_controller(ctx: BuildContext) -> SimmonsBlueController:
    selected = ctx.data.get(CONF_PRODUCT_TYPE)
    layout = app.LAYOUTS.get(selected) if isinstance(selected, str) else None
    return SimmonsBlueController(ctx.coordinator, layout or app.LAYOUTS[app.DEFAULT_LAYOUT])
