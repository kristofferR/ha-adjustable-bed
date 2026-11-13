"""N32 Motion Bed: a fixed Okin N-frame profile with three persistent alarms.

Accepted com.okin.simmonskorea 1.1.14 (38), row080. The inherited family
controller supplies the named motor/preset dispatch; this app owns its GATT
session, 200 ms held schedule, three UI groups and alarm callback semantics.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_PRESETS, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from ...profiles.n32_motion_bed import (
    ALARM_MODES,
    CLOCK_DELAY_S,
    FRAME_HOLD_MS,
    N32,
    PRESET_LABELS,
    REFRESH_MS,
    SLOTS,
    alarm_frame,
    clock_frame,
    effective_week,
    manufacturer_identity,
    query_frame,
)
from ..base import require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from ..okin_64bit import Okin64BitController
from .state import ALARM_KEYS, AlarmRow, callback_row

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

# Integration wait bound, not a firmware response-time claim.
ALARM_REPLY_TIMEOUT_S: Final = 2.0


@dataclass(frozen=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class N32MotionBedController(Okin64BitController):
    """No inferred individual upper motors, angles, accessories or side routing."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        manufacturer_data: Mapping[int, bytes] | None = None,
    ) -> None:
        super().__init__(coordinator, char_uuid=NORDIC_UART_WRITE_CHAR_UUID, profile=N32)
        self._manufacturer_identity = manufacturer_identity(manufacturer_data or {})
        self._link: _Link | None = None
        self._notifying = False
        self._seen: dict[int, codec.AlarmReport] = {}
        self._revisions: dict[int, int] = dict.fromkeys(SLOTS, 0)
        self._reply = asyncio.Event()
        self._rows: dict[int, AlarmRow | None] = {}
        for slot, keys in ALARM_KEYS.items():
            stored = coordinator.controller_state.get(keys.record)
            self._rows[slot] = (
                AlarmRow(*stored)
                if isinstance(stored, tuple)
                and len(stored) == 5
                and all(type(v) is int for v in stored)
                else None
            )

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False  # The source enum's literal UI label is M3.

    @property
    def memory_slot_count(self) -> int:
        return 3

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return ("M1", "M2", "M3")

    @property
    def supports_preset_lounge(self) -> bool:
        return False  # Exposed under the app's exact Relax label below.

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "n32_protocol": "P1 enum2",
            "n32_hardware": "UNVERIFIED",
            "manufacturer_identity_available": self._manufacturer_identity is not None,
        }

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                label,
                lambda c, key=up: require_controller(c, N32MotionBedController)._move_key(key),
                lambda c, key=down: require_controller(c, N32MotionBedController)._move_key(key),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(up, down, stop_scope="side", press_hold_ms=None),
            )
            for axis, label, up, down in (
                ("back", "n32_upper", "head_up", "head_down"),
                ("legs", "n32_lower", "foot_up", "foot_down"),
                ("head", "n32_cervical", "cervical_up", "cervical_down"),
            )
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in N32.keys if key != "stop")

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_tv": "tv_pc",
            "preset_lounge": "lounge",
            **{f"preset_memory_{s}": f"memory_{s}" for s in SLOTS},
        }.get(key)
        return ControllerHoldSpec(control) if control else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "n32_relax",
                "Relax",
                lambda c: c.preset_lounge(),
                translation_key="n32_relax",
                hold=ControllerHoldSpec("lounge"),
                scheduler_resource="*",
                card=CARD_PRESETS,
            ),
            ControllerButtonSpec(
                "n32_refresh_alarms",
                "Refresh alarms",
                lambda c: require_controller(c, N32MotionBedController).refresh_alarms(),
                icon="mdi:alarm",
                translation_key="n32_refresh_alarms",
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                f"n32_alarm_{slot}",
                f"n32_alarm_{slot}",
                keys.time,
                "mdi:alarm",
                attribute_keys=(keys.enabled, keys.mode, keys.week, keys.ab, keys.soft, keys.fresh),
                card=CARD_UTILITY,
            )
            for slot, keys in ALARM_KEYS.items()
        )

    def _build_command(self, word: int) -> bytes:
        return codec.frame40(word)

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("N32 BLE session changed or disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("N32 is not connected")
        roles = {
            c.uuid.lower(): c
            for s in client.services
            if s.uuid.lower() == NORDIC_UART_SERVICE_UUID
            for c in s.characteristics
        }
        write, notify = (
            roles.get(u) for u in (NORDIC_UART_WRITE_CHAR_UUID, NORDIC_UART_READ_CHAR_UUID)
        )
        if (
            write is None
            or "write" not in write.properties
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError("N32 requires its Nordic write-with-response and notification roles")
        self._link = _Link(client, write, notify)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            report = codec.parse_alarm(bytes(data))
            if report is None:
                return
            self._seen[report.slot] = report
            self._revisions[report.slot] += 1
            row = callback_row(report, self._rows[report.slot])
            self._rows[report.slot] = row
            keys = ALARM_KEYS[report.slot]
            mode = next((k for k, v in ALARM_MODES.items() if row and v == row.mode), None)
            self.forward_controller_state_updates(
                keys.time(f"{row.hour:02d}:{row.minute:02d}" if row else None),
                keys.enabled(bool(row and row.enabled)),
                keys.mode(mode),
                keys.week(row.week if row else 0),
                keys.ab(report.ab),
                keys.soft(report.soft),
                keys.fresh(True),
                keys.record(row),
            )
            self._reply.set()

        for attempt in range(2):
            try:
                async with self._ble_lock:
                    self._live(link)
                    if self._notifying:
                        await link.client.stop_notify(link.notify)
                        self._notifying = False
                    await link.client.start_notify(link.notify, receive)
                self._live(link)
                self._notifying = True
                return
            except BleakError:
                if attempt:
                    raise

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._seen.clear()
        self._reply.set()
        self.forward_controller_state_updates(*(keys.fresh(False) for keys in ALARM_KEYS.values()))

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if link and notifying and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        # All three source-proven UI slot queries are safe to request. Unlike
        # Android's signed stored-week<128 filter, do not mistake local rows
        # for a complete peripheral inventory or skip recurring slots.
        started = asyncio.get_running_loop().time()
        await self.refresh_alarms()
        await asyncio.sleep(max(0, started + CLOCK_DELAY_S - asyncio.get_running_loop().time()))
        self._live(link)
        await self.sync_clock()  # Fresh time at dispatch, never a cached frame.

    async def _write(
        self,
        link: _Link,
        frame: bytes | Callable[[], bytes],
        cancel: asyncio.Event,
        *,
        revision: tuple[int, int] | None = None,
        on_dispatch: Callable[[], None] | None = None,
    ) -> bool:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                return False
            if revision and self._revisions[revision[0]] != revision[1]:
                raise ValueError("N32 alarm changed while waiting to write; refresh and retry")
            if on_dispatch is not None:
                on_dispatch()
            frame = frame() if callable(frame) else frame
            self._record_command_trace(
                link.write.uuid, frame, response=True, characteristic=link.write
            )
            await link.client.write_gatt_char(link.write, frame, response=True)
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        await self._repeat(link, command, cancel, repeat_count, repeat_delay_ms)

    async def _repeat(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        count: int,
        interval_ms: int,
        duration_ms: int | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        started = loop.time()
        interval = interval_ms / 1000
        deadline = started + (duration_ms / 1000 if duration_ms is not None else count * interval)
        index = 0
        while index < count and not cancel.is_set():
            if index:
                delay = max(0, min(deadline, started + index * interval) - loop.time())
                try:
                    await asyncio.wait_for(cancel.wait(), delay)
                    return
                except TimeoutError:
                    pass
            if loop.time() >= deadline or cancel.is_set():
                return
            await self._write(link, frame, cancel)
            # Missed ticks are skipped, never replayed as a burst after a slow ACK.
            index = max(index + 1, math.ceil((loop.time() - started) / interval))
        if duration_ms is not None and not cancel.is_set() and loop.time() < deadline:
            try:
                await asyncio.wait_for(cancel.wait(), deadline - loop.time())
            except TimeoutError:
                pass

    async def _release(self, link: _Link) -> None:
        task = asyncio.create_task(self._write(link, self._build_command(0), asyncio.Event()))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                break
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _send_stop(self) -> None:
        await self._release(self._live())

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, REFRESH_MS

    async def _move_with_stop(self, command: bytes) -> None:
        link = self._live()
        count = self.leased_hold_refreshes(REFRESH_MS) or self._coordinator.motor_pulse_count
        cancel = self._coordinator.cancel_command
        try:
            await self._repeat(link, command, cancel, count, REFRESH_MS)
        finally:
            await self._release(link)

    async def _move_key(self, key: str) -> None:
        await self._move_with_stop(self._build_command(N32.keys[key]))

    async def move_back_up(self) -> None:
        await self._move_key("head_up")

    async def move_back_down(self) -> None:
        await self._move_key("head_down")

    async def move_head_up(self) -> None:
        await self._move_key("cervical_up")

    async def move_head_down(self) -> None:
        await self._move_key("cervical_down")

    async def _press(self, word: int) -> None:
        await self.hold_control(next(key for key, value in N32.keys.items() if value == word), 200)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in SLOTS:
            raise ValueError("N32 has M1, M2 and M3")
        await self._press(N32.keys[f"memory_{memory_num}"])

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unknown N32 held control")
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise ValueError("Hold duration must be 1 through 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link, cancel = self._live(), self._coordinator.cancel_command
        duration = self.leased_hold_ms(duration_ms)
        if control in PRESET_LABELS:
            duration = min(duration, FRAME_HOLD_MS)
        try:
            await self._repeat(
                link,
                self._build_command(N32.keys[control]),
                cancel,
                self.timed_move_repeat_count(duration, REFRESH_MS),
                REFRESH_MS,
                duration,
            )
        finally:
            await self._release(link)

    async def sync_clock(self) -> None:
        await self._write(
            self._live(), lambda: clock_frame(dt_util.now()), self._coordinator.cancel_command
        )

    async def refresh_alarms(self) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        for slot in SLOTS:
            await self._write(link, query_frame(slot), cancel)

    @staticmethod
    def validate_alarm(slot: int, operation: str, row: AlarmRow | None) -> None:
        if type(slot) is not int or slot not in SLOTS:
            raise ValueError("N32 has app alarm slots 1, 2 and 3")
        if operation not in ("set", "disable", "delete", "query"):
            raise ValueError("Unknown N32 alarm operation")
        if operation == "set":
            if (
                row is None
                or not all(type(v) is int for v in row)
                or not 0 <= row.hour <= 23
                or not 0 <= row.minute <= 59
                or row.mode not in ALARM_MODES.values()
                or row.enabled != 1
                or row.week != 0
                and not 128 <= row.week <= 255
            ):
                raise ValueError("Supply a complete N32 alarm time, UI weekdays and mode")

    async def _query_slot(self, slot: int) -> codec.AlarmReport:
        link = self._live()
        revision = -1

        def dispatched() -> None:
            nonlocal revision
            revision = self._revisions[slot]
            self._reply.clear()

        if not await self._write(
            link, query_frame(slot), self._coordinator.cancel_command, on_dispatch=dispatched
        ):
            raise ValueError("N32 alarm query was cancelled")
        self._live(link)
        async with asyncio.timeout(ALARM_REPLY_TIMEOUT_S):
            while self._revisions[slot] == revision:
                await self._reply.wait()
                self._live(link)
                self._reply.clear()
        self._live(link)
        return self._seen[slot]

    async def check_alarm(self, slot: int, operation: str, row: AlarmRow | None) -> None:
        self.validate_alarm(slot, operation, row)
        self._live()
        if operation == "disable":
            report = await self._query_slot(slot)
            current = callback_row(report, None)
            if (
                current is not None
                and current.enabled
                and (
                    report.mode not in ALARM_MODES.values()
                    or not 0 <= report.hour <= 23
                    or not 0 <= report.minute <= 59
                )
            ):
                raise ValueError("N32 reported an unsupported alarm; nothing was changed")

    async def apply_alarm(self, slot: int, operation: str, row: AlarmRow | None) -> None:
        await self.check_alarm(slot, operation, row)
        link, cancel = self._live(), self._coordinator.cancel_command
        revision: tuple[int, int] | None = None
        if operation == "query":
            await self._write(link, query_frame(slot), cancel)
            return
        if operation == "delete":
            frame: bytes | Callable[[], bytes] = alarm_frame(slot, 0, 0, 0, 0, 0)
            owned = None
        else:
            if operation == "disable":
                report = self._seen[slot]
                row = callback_row(report, None)
                if row is None or not row.enabled:
                    return  # Already disabled; never fill missing fields from a stale cache.
                revision = (slot, self._revisions[slot])
            assert row is not None
            planned = row

            def build_alarm() -> bytes:
                week = effective_week(planned.week, planned.hour, planned.minute, dt_util.now())
                return alarm_frame(
                    slot, planned.hour, planned.minute, week, planned.mode, int(operation == "set")
                )

            frame = build_alarm

            owned = row._replace(enabled=int(operation == "set"))
        before = self._revisions[slot]
        if await self._write(link, frame, cancel, revision=revision):
            # Keep app-owned fields across per-link controller recreation,
            # without reporting requested values as observed telemetry. A
            # callback delivered during the write always wins.
            if self._revisions[slot] == before:
                self._rows[slot] = owned
                keys = ALARM_KEYS[slot]
                self.forward_controller_state_updates(keys.record(owned), keys.fresh(False))
            await self._write(link, query_frame(slot), cancel)


async def build_controller(ctx: BuildContext) -> N32MotionBedController:
    """Keep optional manufacturer identity separate from HA's physical address."""
    return N32MotionBedController(ctx.coordinator, manufacturer_data=ctx.manufacturer_data)
