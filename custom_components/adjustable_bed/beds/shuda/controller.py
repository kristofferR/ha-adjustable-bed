"""Shuda's per-bed Nordic UART session, held controls and stored alarms."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from math import ceil
from typing import TYPE_CHECKING, Any, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...command_scheduler import CommandContext, current_command_context
from ...const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import shuda as p
from ...profiles.okin_nframe import OkinNFrameProfile
from ..base import CONTROLLER_GESTURE_RELEASE, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from ..okin_nframe import OkinNFrameController

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

_RELEASE_BUTTON: Final = "shuda_release"
_ALARM_REPLY_TIMEOUT_S: Final = 2.0  # Integration wait bound.
_ALARM: Final = AlarmCapability(
    wake_actions=tuple(p.ALARM_MODES),
    weekdays=True,
    slots=len(p.ORDINARY_SLOTS),
    requires_wake_action=True,
    confirm_actions=frozenset({"memory_1"}),
    live_check=True,
    resource="*",
)


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


@dataclass(frozen=True, slots=True)
class _AlarmKeys:
    time: StateKey[str | None]
    enabled: StateKey[bool | None]
    week: StateKey[int | None]
    mode: StateKey[str | None]


_ALARM_KEYS: Final = {
    slot: _AlarmKeys(
        StateKey(f"shuda_alarm_{slot}"),
        StateKey(f"shuda_alarm_{slot}_enabled"),
        StateKey(f"shuda_alarm_{slot}_week"),
        StateKey(f"shuda_alarm_{slot}_mode"),
    )
    for slot in p.ORDINARY_SLOTS
}


class _HoldEnded(Exception):
    """The hold expired while waiting for the GATT write lane."""


class ShudaController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
    """Operate a single ready receiver using its exact discovered handles."""

    profile = p.SHUDA

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, manufacturer_identity: str | None = None
    ) -> None:
        super().__init__(coordinator)
        self._manufacturer_identity = manufacturer_identity
        self._link: _Link | None = None
        self._pending_stop: _Link | None = None
        self._released_command: CommandContext | None = None
        self._subscription: object | None = None
        self._notifying = False
        self._alarms: dict[int, codec.ShortAlarmReport] = {}
        self._received: dict[int, codec.ShortAlarmReport] = {}
        self._alarm_events = {slot: asyncio.Event() for slot in p.ORDINARY_SLOTS}

    @property
    def control_characteristic_uuid(self) -> str:
        return NORDIC_UART_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"manufacturer_identity_available": self._manufacturer_identity is not None}

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and expected is not link
            or self.client is not link.client
            or not link.client.is_connected
        ):
            raise BedNotConnectedError
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        for service in client.services:
            if service.uuid.lower() != NORDIC_UART_SERVICE_UUID:
                continue
            write = service.get_characteristic(NORDIC_UART_WRITE_CHAR_UUID)
            notify = service.get_characteristic(NORDIC_UART_READ_CHAR_UUID)
            if (
                write is not None
                and "write" in write.properties
                and notify is not None
                and {"notify", "indicate"}.intersection(notify.properties)
            ):
                self._link = _Link(client, write, notify)
                return
        raise BedNotConnectedError("shuda_gatt_roles")

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True  # Shuda does not read the Device Information service.

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return

        async with self._ble_lock:
            self._live(link)
            if self._notifying:
                return
            for attempt in range(2):
                subscription = object()
                self._subscription = subscription

                def receive(
                    sender: BleakGATTCharacteristic, data: bytearray, token: object = subscription
                ) -> None:
                    if (
                        self._link is link
                        and self._subscription is token
                        and self.client is link.client
                        and link.client.is_connected
                        and sender.handle == link.notify.handle
                    ):
                        self._receive(sender.uuid, bytes(data))

                try:
                    await link.client.start_notify(link.notify, receive)
                except BleakError:
                    self._subscription = None
                    self._live(link)
                    if attempt:
                        raise
                else:
                    self._live(link)
                    self._notifying = True
                    return

    async def stop_notify(self) -> None:
        link = self._link
        if link is None:
            return
        async with self._ble_lock:
            if self._link is link and self.client is link.client and link.client.is_connected:
                notifying = self._notifying
                self._retire_notifications()
                if notifying:
                    await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = self._pending_stop = None
        self._released_command = None
        self._retire_notifications()

    def _retire_notifications(self) -> None:
        self._subscription = None
        self._notifying = False
        self._received.clear()
        for event in self._alarm_events.values():
            event.set()

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        cancel = asyncio.Event()
        await self._write(link, p.clock_frame(dt_util.now()), cancel, counted=False)
        await self._refresh_alarms(link, cancel, counted=False)

    def _build_command(self, command_value: int) -> bytes:
        return codec.frame40(command_value)

    async def _write(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        before_write: Callable[[], None] | None = None,
        build: Callable[[], bytes] | None = None,
        on_write: Callable[[], None] | None = None,
        counted: bool = True,
    ) -> None:
        def guard() -> None:
            self._live(link)
            if before_write is not None:
                before_write()

        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            frame,
            cancel_event=cancel,
            characteristic=link.write,
            expected_client=link.client,
            before_write=guard,
            command_factory=build,
            on_write=on_write,
            track_command_write=counted,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = p.REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event or self._coordinator.cancel_command
        for pulse in range(repeat_count):
            if pulse and await _cancelled(cancel, repeat_delay_ms / 1000):
                return
            await self._write(link, command, cancel)

    def _arm_stop(self, link: _Link) -> None:
        # A failed ATT write can still have reached the receiver.
        self._pending_stop = link
        self._released_command = None

    async def _release(self, link: _Link) -> None:
        # An interrupted old gesture cannot STOP a replacement GATT session.
        if (
            self._pending_stop is link
            and self._link is link
            and self.client is link.client
            and link.client.is_connected
        ):
            await self._stop_link(link)
            if self._link is link and (context := current_command_context()) is not None:
                context.cleanup_stop_sent = True
                self._released_command = context

    async def _stop_link(self, link: _Link) -> None:
        await self._write(link, self._build_command(0), asyncio.Event())
        if self._pending_stop is link:
            self._pending_stop = None

    async def _send_stop(self) -> None:
        await self._stop_link(self._live())

    async def stop_all(self) -> None:
        link = self._live()
        context, released = current_command_context(), self._released_command
        if context is not None and released is not None and released.cleanup_stop_sent:
            if any(released is preempted for preempted in context.preempted_contexts):
                released.cleanup_stop_sent = False
                self._released_command = None
                return
        if not CONTROLLER_GESTURE_RELEASE.get() or self._pending_stop is link:
            await self._stop_link(link)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self.profile.keys)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.profile.keys:
            raise self.not_supported(control)
        if not 100 <= duration_ms <= 60_000:
            raise invalid("shuda_hold_duration")
        if control in p.SAVE_KEYS and duration_ms >= p.RECALL_LIMIT_MS:
            raise invalid("shuda_recall_duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if self.execution.hold_for(control) is not None:
            duration_ms = self.leased_hold_ms(duration_ms)
        await self._press(control, duration_ms)

    async def _press(self, control: str, duration_ms: int) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        frame = self._build_command(self.profile.keys[control])
        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = start + duration_ms / 1000
        interval = p.REFRESH_MS / 1000

        def in_time() -> None:
            if loop.time() >= deadline:
                raise _HoldEnded
            self._arm_stop(link)

        async with self.releasing(lambda: self._release(link)):
            tick = 0
            while not cancel.is_set():
                if loop.time() >= deadline:
                    break
                try:
                    await settled(self._write(link, frame, cancel, before_write=in_time))
                except _HoldEnded:
                    break
                # Skip ticks lost to a delayed ATT response instead of replaying them.
                tick = max(tick + 1, ceil((loop.time() - start) / interval))
                if await _cancelled(cancel, min(deadline, start + tick * interval) - loop.time()):
                    break

    async def _tap(self, control: str) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        async with self.releasing(lambda: self._release(link)):
            await settled(
                self._write(
                    link,
                    self._build_command(self.profile.keys[control]),
                    cancel,
                    before_write=lambda: self._arm_stop(link),
                )
            )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, p.REFRESH_MS

    async def _move(self, control: str) -> None:
        count, interval = self.motor_pulse_settings()
        await self.hold_control(control, count * interval)

    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_feet_up(self) -> None:
        await self._move("feet_up")

    async def move_feet_down(self) -> None:
        await self._move("feet_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_head_stop = move_feet_stop = move_back_stop = move_legs_stop = stop_all

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    release_button_key=_RELEASE_BUTTON,
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                ),
            )
            for spec, axis in zip(super().motor_control_specs[:2], ("head", "feet"), strict=True)
        )

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    async def preset_flat(self) -> None:
        await self._tap("flat")

    async def preset_zero_g(self) -> None:
        await self._tap("zero_g")

    async def preset_tv(self) -> None:
        await self._tap("tv")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._tap("memory_1")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._press("memory_1", p.SAVE_HOLD_MS)

    async def lights_toggle(self) -> None:
        await self._tap("light")

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if control := {"preset_flat": "flat", "toggle_light": "light"}.get(key):
            return ControllerHoldSpec(control, release_button_key=_RELEASE_BUTTON)
        return None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *(
                save_button(
                    f"shuda_save_{control}",
                    label,
                    lambda ctrl, key=control: require_controller(ctrl, ShudaController)._press(
                        key, p.SAVE_HOLD_MS
                    ),
                    scheduler_resource="*",
                )
                for control, label in (("zero_g", "Save zero gravity"), ("tv", "Save TV"))
            ),
            ControllerButtonSpec(
                _RELEASE_BUTTON,
                "Release held control",
                lambda ctrl: ctrl.stop_all(),
                translation_key=_RELEASE_BUTTON,
                release_only=True,
                card=CARD_HIDDEN,
            ),
            ControllerButtonSpec(
                "shuda_refresh_alarms",
                "Refresh alarms",
                lambda ctrl: require_controller(ctrl, ShudaController).refresh_alarms(),
                "mdi:alarm",
                translation_key="shuda_refresh_alarms",
                cancel_movement=False,
                scheduler_resource="*",
                diagnostic=True,
                entity_registry_enabled_default=False,
                card=CARD_HIDDEN,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                keys.time,
                keys.time,
                keys.time,
                "mdi:alarm",
                attribute_keys=(keys.enabled, keys.week, keys.mode),
                entity_registry_enabled_default=True,
                entity_category=None,
                card=CARD_UTILITY,
            )
            for keys in _ALARM_KEYS.values()
        )

    def _receive(self, uuid: str, data: bytes) -> None:
        self.forward_raw_notification(uuid, data)
        if (row := p.alarm_model(data)) is None:
            return
        self._received[row.slot] = self._alarms[row.slot] = row
        if event := self._alarm_events.get(row.slot):
            event.set()
        if (keys := _ALARM_KEYS.get(row.slot)) is None:
            self._coordinator.save_app_state(self)
            return
        time = f"{row.hour:02d}:{row.minute:02d}" if row.hour < 24 and row.minute < 60 else None
        mode = next((name for name, value in p.ALARM_MODES.items() if row.mode == value), None)
        self.forward_controller_state_updates(
            keys.time(time), keys.enabled(bool(row.enabled)), keys.week(row.week), keys.mode(mode)
        )

    @property
    def persisted_app_state(self) -> Mapping[str, Any]:
        return {
            "alarms": {
                str(slot): [row.week, row.mode, row.hour, row.minute, row.enabled]
                for slot, row in self._alarms.items()
            }
        }

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        rows = state.get("alarms")
        if not isinstance(rows, dict):
            return
        for slot in (1, 2, 3):
            fields = rows.get(str(slot))
            if (
                isinstance(fields, list)
                and len(fields) == 5
                and all(type(value) is int and 0 <= value <= 255 for value in fields)
            ):
                self._alarms[slot] = codec.ShortAlarmReport(slot, *fields)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self._write(
            self._live(), p.clock_frame(dt_util.now()), self._coordinator.cancel_command
        )

    @property
    def alarm_capability(self) -> AlarmCapability:
        return _ALARM

    async def refresh_alarms(self) -> None:
        await self._refresh_alarms(self._live(), self._coordinator.cancel_command)

    async def _refresh_alarms(
        self, link: _Link, cancel: asyncio.Event, *, counted: bool = True
    ) -> None:
        third = self._alarms.get(3)
        slots = (
            (*p.ORDINARY_SLOTS, 3) if third is not None and third.week < 128 else p.ORDINARY_SLOTS
        )
        for slot in slots:
            await self._write(link, p.query_frame(slot), cancel, counted=counted)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.slot not in p.ORDINARY_SLOTS:
            raise invalid("shuda_alarm_slot")
        if alarm.enabled and alarm.wake_action not in p.ALARM_MODES:
            raise invalid("shuda_alarm_mode")

    def _check_conflict(self, alarm: AlarmRequest, week: int) -> None:
        other_slot = 3 - alarm.slot
        if other_slot not in self._received:
            raise invalid("shuda_alarm_no_reply", slot=other_slot)
        if any(
            row.slot != alarm.slot
            and row.enabled
            and (row.hour, row.minute) == (alarm.hour, alarm.minute)
            and (not (week & 0x7F) or not (row.week & 0x7F) or week & row.week & 0x7F)
            for row in self._alarms.values()
        ):
            raise invalid("shuda_alarm_conflict", slot=alarm.slot)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link = self._live()
        # An enable must see the competing ordinary slot before deciding
        # it is safe. A disable needs its own slot's actual schedule.
        await self._ensure_alarm_report(link, 3 - alarm.slot if alarm.enabled else alarm.slot)
        if alarm.enabled and not self._coordinator.cancel_command.is_set():
            self._check_conflict(alarm, p.edited_week(alarm.weekdays))

    async def _ensure_alarm_report(self, link: _Link, slot: int) -> None:
        if slot in self._received:
            return
        event = self._alarm_events[slot]
        event.clear()
        cancel = self._coordinator.cancel_command
        await self._write(link, p.query_frame(slot), cancel, counted=False)
        if cancel.is_set():
            return
        try:
            async with asyncio.timeout(_ALARM_REPLY_TIMEOUT_S):
                await cancellable(event.wait(), cancel)
        except TimeoutError as err:
            raise invalid("shuda_alarm_no_reply", slot=slot) from err
        self._live(link)
        if slot not in self._received and not cancel.is_set():
            raise invalid("shuda_alarm_no_reply", slot=slot)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        link, cancel = self._live(), self._coordinator.cancel_command
        week = p.edited_week(alarm.weekdays)
        row: codec.ShortAlarmReport
        previous: codec.ShortAlarmReport | None

        def build() -> bytes:
            nonlocal row, previous
            previous = self._received.get(alarm.slot)
            if alarm.enabled:
                self._check_conflict(alarm, week)
                row = codec.ShortAlarmReport(
                    alarm.slot, week, p.ALARM_MODES[alarm.wake_action], alarm.hour, alarm.minute, 1
                )
            else:
                if previous is None:
                    raise invalid("shuda_alarm_no_reply", slot=alarm.slot)
                row = replace(previous, enabled=0)
            return p.alarm_frame(row)

        def remember() -> None:
            # A notification arriving during the write wins over the local model.
            if self._link is link and self._received.get(alarm.slot) is previous:
                self._received.pop(alarm.slot, None)
                self._alarms[alarm.slot] = row
                self._coordinator.save_app_state(self)

        await self._write(link, b"", cancel, build=build, on_write=remember)
        await self._write(link, p.query_frame(alarm.slot), cancel, counted=False)


async def _cancelled(event: asyncio.Event, delay: float) -> bool:
    if event.is_set() or delay <= 0:
        return event.is_set()
    try:
        await asyncio.wait_for(event.wait(), delay)
    except TimeoutError:
        return False
    return True


async def build_controller(ctx: BuildContext) -> ShudaController:
    return ShudaController(
        ctx.coordinator, manufacturer_identity=p.manufacturer_identity(ctx.manufacturer_data or {})
    )
