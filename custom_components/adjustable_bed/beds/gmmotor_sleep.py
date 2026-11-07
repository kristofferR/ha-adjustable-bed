"""GM Control MM/SXB direct BLE sleep-module sessions.

Request/state ownership is per physical HA target. This avoids sharing the
app's singleton active-command state across unrelated configured modules.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ..controller_state import StateKey, StateUpdate
from ..gmmotor_notifications import Value
from ..gmmotor_protocol import MalformedNotification
from ..gmmotor_requests import Operation, Request
from ..gmmotor_sessions import sleep_intent
from ..gmmotor_sleep_protocol import (
    LiveState,
    ReceiveBuffer,
    Requests,
    SleepCommand,
    normal_live,
    sxb_live,
)
from ..gmmotor_sleep_reports import decode_report
from ..gmmotor_sleep_state import ClockUpdate, Followup, ReportSize, Stream, dispatch, fields
from ..gmmotor_transport import Transport, native_write_lock, select_sleep
from .base import BedController, ControllerButtonSpec, ControllerStateSensorSpec, MotorControlSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_QUEUE_TICK = 0.1
_LIVE_INTERVAL = 2.0
_STALE_INTERVAL = 5.0
_REPORT_BUDGET = 8 * 1024 * 1024
_STREAM_NAMES = {
    "0x7": "realtime",
    "0xb": "time",
    "0xf": "part",
    "0x13": "report_size",
    "0x17": "month_report",
    "0x1b": "day_report",
    "0x2f": "time",
    "0x33": "clock",
    "0x37": "part",
    "0x3b": "realtime",
    "0x3f": "report_size",
    "0x43": "month_report",
    "0x47": "day_report",
    "0x4b": "day_report_new",
    "0x57": "initialization",
    "0x5f": "sensitivity",
    "0x63": "anti_snore",
}


EVENT: Final = StateKey[str]("gmmotor_sleep_event")
STREAMS: Final = StateKey[dict[str, Value]]("gmmotor_sleep_streams")
CLOCK: Final = StateKey[dict[str, Value]]("gmmotor_sleep_clock")
REPORTS: Final = StateKey[dict[str, Value]]("gmmotor_sleep_reports")
INVALID: Final = StateKey[int]("gmmotor_sleep_invalid")


def _live_key(side: str) -> StateKey[dict[str, object]]:
    return StateKey[dict[str, object]]("gmmotor_sleep_" + side)


class GmmotorSleepController(BedController):
    """One explicitly selected GM Control sleep module, independent of the bed."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, sxb: bool) -> None:
        super().__init__(coordinator)
        self._sxb = sxb
        self._requests = Requests(sxb=sxb)
        self._receive_buffer = ReceiveBuffer(sxb=sxb)
        self._transport: Transport | None = None
        self._subscriptions: list[BleakGATTCharacteristic] = []
        self._write_lock = native_write_lock(coordinator.hass)
        self._clock: dict[str, Value] = dict.fromkeys(("0x7", "0xb", "0xf", "0x13", "0x17", "0x1b"))
        self._streams: dict[str, Value] = {}
        self._cache: dict[str, Value] = {}
        self._report_date = dt_util.now().date()
        self._report_part = 1
        self._report_type = 1
        self._device_part = 12 if sxb else 2
        self._reported_part: Value = None
        self._session_side = 1
        self._generation = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._poll_timer: asyncio.TimerHandle | None = None
        self._stale_timer: asyncio.TimerHandle | None = None
        self._live_seen = {"left": 0, "right": 0}
        self._intent = sleep_intent(coordinator.hass, str(coordinator.address), sxb=sxb)
        self._invalid = 0

    @property
    def _live_enabled(self) -> bool:
        return self._intent.live_enabled

    @_live_enabled.setter
    def _live_enabled(self, enabled: bool) -> None:
        self._intent.live_enabled = enabled

    @property
    def control_characteristic_uuid(self) -> str:
        return self._transport.write.uuid if self._transport else ""

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_gmmotor_controls(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        operations: tuple[tuple[str, Operation], ...] = (
            ("Time", "sensor_time"),
            ("Query part", "sensor_query_part"),
            ("Start live data", "sensor_live"),
            ("Stop live data", "sensor_stop"),
        )
        return tuple(
            ControllerButtonSpec(
                key="gmmotor_" + operation,
                name=name,
                press_fn=lambda ctrl, op=operation: ctrl.async_execute_gmmotor_request(Request(op)),
                cancel_movement=False,
            )
            for name, operation in operations
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                key="gmmotor_sleep_state",
                translation_key="gmmotor_sleep_state",
                state_key=EVENT,
                icon="mdi:sleep",
                attribute_keys=(
                    STREAMS,
                    CLOCK,
                    REPORTS,
                    _live_key("left"),
                    _live_key("right"),
                    INVALID,
                ),
            ),
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        transport, client = self._transport, self.client
        if transport is None or client is None or not client.is_connected:
            raise ConnectionError("GM Control sleep session is not ready")
        chunk_size = client.mtu_size - 3
        if chunk_size <= 0:
            raise ValueError("Invalid negotiated sleep-module MTU")
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if index:
                await asyncio.sleep(repeat_delay_ms / 1000)
            for start in range(0, len(command), chunk_size):
                chunk = command[start : start + chunk_size]
                if len(chunk) > min(chunk_size, 512):
                    raise ValueError("Sleep write exceeds the source native payload limit")
                async with self._write_lock:
                    async with asyncio.timeout(15):
                        await self._write_gatt_with_retry(
                            transport.write.uuid,
                            chunk,
                            cancel_event=cancel,
                            response=transport.response,
                            characteristic=transport.write,
                        )

    async def _send(self, command: SleepCommand) -> None:
        now = dt_util.now()
        request = self._requests.build(
            command,
            now=now,
            zone=self._coordinator.hass.config.time_zone,
            part=self._report_part if command != "s_part" else self._device_part,
            report_type=self._report_type,
            year=self._report_date.year,
            month=self._report_date.month,
            day=self._report_date.day,
        )
        self._receive_buffer.start(command)
        if not request.packet:
            return
        # Every reachable framed bean is pressType5: removed before one send.
        # Chunks are sequential SDK writes, without a per-chunk queue delay.
        await asyncio.sleep(_QUEUE_TICK)
        await self.write_command(request.packet)

    def _queue(self, command: SleepCommand, *, delayed: bool = False) -> None:
        generation = self._generation

        async def run() -> None:
            if delayed:
                await asyncio.sleep(0)  # Source zero-duration Future callback.
            if (
                generation != self._generation
                or self._transport is None
                or self._coordinator.controller is not self
            ):
                return
            if command == "q_report_allow" and self._report_type not in (1, 2):
                return

            async def execute(_controller: BedController) -> None:
                if (
                    generation == self._generation
                    and self._transport is not None
                    and self._coordinator.controller is self
                ):
                    await self._send(command)

            try:
                await self._coordinator.async_execute_controller_command(
                    execute, cancel_running=False, resource="configuration"
                )
            except Exception:
                _LOGGER.debug("GM Control sleep follow-up failed", exc_info=True)

        task = self._coordinator.hass.async_create_task(run(), "gmmotor_sleep_followup")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _poll(self) -> None:
        self._poll_timer = None
        if not self._live_enabled or self._transport is None:
            return
        if self._receive_buffer.command not in ("q_report", "q_report_allow"):
            self._queue("q_realtime")
        self._poll_timer = asyncio.get_running_loop().call_later(_LIVE_INTERVAL, self._poll)

    def _stale_tick(self) -> None:
        """SXB 0x801cfc clears a side after an empty five-second display window."""
        self._stale_timer = None
        if not self._sxb or not self._live_enabled or self._transport is None:
            return
        if self._receive_buffer.command not in ("q_report", "q_report_allow"):
            updates: list[StateUpdate] = []
            for side, seen in self._live_seen.items():
                if seen:
                    self._live_seen[side] = 0
                else:
                    updates.append(
                        _live_key(side)(asdict(LiveState(None, None, None, None, None, False)))
                    )
            if updates:
                self.forward_controller_state_updates(*updates)
        self._stale_timer = asyncio.get_running_loop().call_later(_STALE_INTERVAL, self._stale_tick)

    def _cancel_live_timers(self) -> None:
        for timer in (self._poll_timer, self._stale_timer):
            if timer:
                timer.cancel()
        self._poll_timer = self._stale_timer = None

    def _start_live_timers(self) -> None:
        if self._poll_timer is None:
            self._poll_timer = asyncio.get_running_loop().call_later(_LIVE_INTERVAL, self._poll)
        if self._sxb and self._stale_timer is None:
            self._stale_timer = asyncio.get_running_loop().call_later(
                _STALE_INTERVAL, self._stale_tick
            )

    def _publish(self, stream: Stream) -> None:
        name = _STREAM_NAMES[stream.field]
        self._streams[name] = stream.value
        updates = [EVENT(name), STREAMS(dict(self._streams)), CLOCK(dict(self._clock))]
        if name == "part":
            self._reported_part = fields(stream.value)["0x13"]
        if name == "realtime":
            root = fields(stream.value)
            val = fields(root["0xf"])
            for side, key in (("left", "0x7"), ("right", "0xb")):
                value = val[key]
                if self._sxb:
                    if value is None:
                        continue
                    if not isinstance(value, list) or any(
                        type(v) not in (int, float) for v in value
                    ):
                        raise MalformedNotification("SXB live data expects numeric lists")
                    state = sxb_live([v for v in value if isinstance(v, (int, float))])
                else:
                    if not isinstance(value, str):
                        raise MalformedNotification("MM live data expects a string")
                    state = normal_live(value)
                if state is not None:
                    if self._sxb:
                        self._live_seen[side] += 1
                    updates.append(_live_key(side)(asdict(state)))
        self.forward_controller_state_updates(*updates)

    def _receive(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._transport is None or self._coordinator.controller is not self:
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        try:
            payload = self._receive_buffer.feed(bytes(data))
            if len(self._receive_buffer.pending) > _REPORT_BUDGET:
                raise MalformedNotification("Sleep assembly exceeds the HA memory budget")
            if payload is None:
                return
            if self._receive_buffer.command == "q_report_allow":
                report = decode_report(
                    payload,
                    sxb=self._sxb,
                    kind=self._report_type,
                    side=self._report_part,
                    session_side=self._session_side,
                    requested_date=self._report_date,
                )
                if report is not None:
                    if report.cache_key is not None:
                        self._cache[report.cache_key] = report.wrapper
                    self.forward_controller_state_update(REPORTS, dict(self._cache))
                    self._publish(Stream(report.stream, report.wrapper))
                # HA owns one finite transfer and may resume an earlier live
                # intent. The source leaves this command active for its page.
                self._receive_buffer.clear()
                return
            report_finished = False
            for effect in dispatch(
                payload,
                sxb=self._sxb,
                active=self._receive_buffer.command,
                clock=self._clock,
                session_side=self._session_side,
                report_type=self._report_type,
            ):
                if isinstance(effect, ClockUpdate):
                    self._clock.update(effect.fields)
                    self.forward_controller_state_update(CLOCK, dict(self._clock))
                elif isinstance(effect, ReportSize):
                    if effect.size > _REPORT_BUDGET:
                        raise MalformedNotification("Sleep report exceeds the HA receive budget")
                    self._receive_buffer.report_size = effect.size
                    report_finished = effect.size <= 0
                elif isinstance(effect, Stream):
                    self._publish(effect)
                elif isinstance(effect, Followup):
                    self._queue(effect.command, delayed=effect.delayed)
            if report_finished:
                self._receive_buffer.clear()
        except (MalformedNotification, ValueError, TypeError) as err:
            self._invalid += 1
            self._receive_buffer.pending.clear()
            self.forward_controller_state_update(INVALID, self._invalid)
            _LOGGER.debug("Rejected GM Control sleep response: %s", err)

    def validate_gmmotor_request(self, request: Request) -> None:
        if request.operation not in (
            "sensor_time",
            "sensor_part",
            "sensor_query_part",
            "sensor_live",
            "sensor_report",
            "sensor_sensitivity",
            "sensor_stop",
        ):
            raise ValueError("This action requires a GM Control bed, not a sleep module")
        if request.operation == "sensor_sensitivity" and not self._sxb:
            raise ValueError("Sensitivity query is unavailable in the normal sleep branch")
        if request.operation == "sensor_part" and request.value not in (
            (11, 12, 13) if self._sxb else (1, 2)
        ):
            raise ValueError("Select a part setting admitted by this sleep module's app page")

    async def async_execute_gmmotor_request(self, request: Request) -> None:
        self.validate_gmmotor_request(request)
        self._generation += 1
        op = request.operation
        if op == "sensor_part":
            if self._sxb and self._reported_part == request.value:
                return
            self._device_part = request.value
        if op == "sensor_stop":
            self._live_enabled = False
            self._cancel_live_timers()
            self._receive_buffer.clear()
            return  # The source has no outbound STOP frame.
        if op == "sensor_report":
            self._report_date = request.report_date or dt_util.now().date()
            self._report_part = request.part
            self._session_side = request.part
            self._report_type = request.report_type
            await self._send("q_report")
        elif op == "sensor_live":
            self._live_enabled = request.enabled
            if not request.enabled:
                self._cancel_live_timers()
                self._receive_buffer.clear()
                return
            await self._send("q_realtime")
            self._start_live_timers()
        else:
            commands: dict[Operation, SleepCommand] = {
                "sensor_time": "s_time",
                "sensor_part": "s_part",
                "sensor_query_part": "q_part",
                "sensor_sensitivity": "q_sens",
            }
            await self._send(commands[op])

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._subscriptions:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to GM Control sleep module")
        self._transport = select_sleep(client.services, sxb=self._sxb)
        self._receive_buffer.clear()
        try:
            for characteristic in self._transport.notifications:
                async with self.ble_lock:
                    await client.start_notify(characteristic, self._receive)
                self._subscriptions.append(characteristic)
            # Source 150 microseconds truncates to zero in its platform timer.
            await asyncio.sleep(0)
            if self._sxb:
                # The host's DOUBLE_USE readiness consumer selects part 12.
                self._device_part = 12
                await self._send("s_part")
            await self._send("s_time")
            if self._live_enabled:
                self._start_live_timers()
        except BaseException as err:
            if isinstance(err, asyncio.CancelledError) and self._coordinator.controller is self:
                self._live_enabled = False
            await self.stop_notify()
            raise

    def on_disconnect(self) -> None:
        self._generation += 1
        self._receive_buffer.clear()
        self._transport = None
        self._subscriptions.clear()
        self._cancel_live_timers()
        self._live_seen = {"left": 0, "right": 0}
        for task in tuple(self._tasks):
            task.cancel()

    async def stop_notify(self) -> None:
        client = self.client
        subscriptions = tuple(self._subscriptions)
        self.on_disconnect()
        if client is not None and client.is_connected:
            for characteristic in subscriptions:
                async with self.ble_lock:
                    await client.stop_notify(characteristic)
        tasks = tuple(task for task in self._tasks if task is not asyncio.current_task())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _unmapped_axis(self) -> None:
        raise NotImplementedError("A GM Control sleep module has no bed motors")

    move_head_up = move_head_down = move_back_up = move_back_down = _unmapped_axis
    move_legs_up = move_legs_down = move_feet_up = move_feet_down = _unmapped_axis
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all = _unmapped_axis
    preset_flat = _unmapped_axis

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("A sleep module has no bed memories")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("A sleep module has no bed memories")
