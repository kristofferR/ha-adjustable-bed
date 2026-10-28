"""Session-safe transport for the explicitly selected cluster033 app profiles.

The profile tables carry caller gates and timing. Shared arithmetic is covered
by each package's frozen vectors; a shared UUID never selects an app profile.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from homeassistant.util import dt as dt_util

from ..alarm_table import AlarmTableSchedule, AlarmTableScheduleSpec
from ..cluster033_profiles import AppAction, AppProfile
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

FFE4 = "0000ffe4-0000-1000-8000-00805f9b34fb"
FFE9 = "0000ffe9-0000-1000-8000-00805f9b34fb"
NUS_RX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"


def finish(data: bytes) -> bytes:
    """Java signed sum and unsigned sum have the same low-byte complement."""
    return data + bytes((~sum(data) & 255,))


def control_frame(mask: int, side: str = "both") -> bytes:
    payload = (mask & 0xFFFFFFFF).to_bytes(4, "little")
    if side == "both":
        return finish(b"\xe5\xfe\x16" + payload)
    return finish(b"\xe6\xfe\x16" + payload + bytes(({"side_a": 1, "side_b": 2}.get(side, 0),)))


def mx_frame(mask: int) -> bytes:
    """The sparse source builder is private; it grants no arbitrary-mask API."""
    allowed = {
        1,
        2,
        4,
        8,
        16,
        32,
        0x200,
        0x400,
        0x800,
        0x2000,
        0x4000,
        0x8000,
        0x10000,
        0x20000,
        0x800000,
        0x1000000,
        0x2000000,
        0x4000000,
        0x8000000,
        0x40000000,
    }
    return b"\x04\x02" + (mask if mask in allowed else 0).to_bytes(4, "big")


def name_frame(name: str, *, max_units: int = 15) -> bytes:
    """Preserve Java's code-unit-count copy using the documented UTF-8 model.

    Android's unnamed default charset is not a firmware encoding declaration.
    Non-ASCII names can end with an incomplete encoded character, as in source.
    """
    units = len(name.encode("utf-16-le")) // 2
    if not name or units > min(max_units, 15):
        raise ValueError(f"Use a nonempty device name of at most {min(max_units, 15)} UTF-16 units")
    return finish(b"\xef\x02" + name.encode("utf-8")[:units].ljust(15, b"\0"))


class AppController(BedController):
    """One current GATT session, existing coordinator scheduling and bounded holds."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: AppProfile, *, side: str = "both"
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._side = side
        self._session_client = None
        self._tx: BleakGATTCharacteristic | None = None
        self._rx: BleakGATTCharacteristic | None = None
        self._session_cancel = asyncio.Event()
        self._timer_status: int | None = None
        self._next_query: float | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._tx.uuid if self._tx is not None else FFE9

    @property
    def alarm_table_schedule_spec(self) -> AlarmTableScheduleSpec | None:
        return self.profile.alarm

    @property
    def supports_device_rename(self) -> bool:
        return self.profile.rename

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.clock

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def diagnostic_poll_interval(self) -> float | None:
        # The existing query scheduler performs the first poll immediately.
        # A five-second check retains the app's first5/then30-second cadence.
        return 5 if self.profile.parser == "qplus" and self.profile.layout == "MX" else None

    async def async_refresh_diagnostics(self) -> None:
        if self._next_query is None:
            return
        now = asyncio.get_running_loop().time()
        if now < self._next_query:
            return
        await self.write_command(b"\x00\xb0")
        self._next_query = now + 30

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(a.key for a in self.profile.actions if a.mode in ("held", "held_zeros"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60000:
            raise ValueError("Choose a declared held control and a duration of 1 through 60000 ms")

    def _action(self, key: str) -> AppAction:
        for action in self.profile.actions:
            if action.key == key:
                return action
        raise ValueError(
            f"Control '{key}' is unavailable on {self.profile.app} {self.profile.layout}"
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def press(key: str):
            async def run(controller: BedController) -> None:
                await cast(AppController, controller)._run_action(key)

            return run

        specs = tuple(
            ControllerButtonSpec(
                a.key,
                a.name,
                press(a.key),
                hold=ControllerHoldSpec(a.key, 0, self._hold_release_delay_ms)
                if a.mode in ("held", "held_zeros")
                else None,
            )
            for a in self.profile.actions
            if a.key not in {"head_up", "head_down", "foot_up", "foot_down"}
        )
        if self.profile.shutdown_count:

            async def dismiss(controller: BedController) -> None:
                await controller.stop_wake_routine()

            specs += (
                ControllerButtonSpec(
                    "dismiss_alarm",
                    "Dismiss wake vibration",
                    dismiss,
                    cancel_movement=False,
                    scheduler_resource="configuration",
                ),
            )
        return specs

    def controller_button_available(self, key: str) -> bool:
        """Old layout entities cannot keep a control admitted after reload."""
        return any(spec.key == key for spec in self.controller_button_specs)

    @property
    def _hold_release_delay_ms(self) -> int:
        # MX's first release query is delayed300ms; its release has no zero or
        # STOP packet. All other held keys release with an immediate zero.
        return 300 if self.profile.parser == "qplus" and self.profile.layout == "MX" else 0

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        def move(key: str):
            async def run(controller: BedController) -> None:
                await cast(AppController, controller)._run_action(key)

            return run

        return (
            MotorControlSpec(
                "back",
                "back",
                move("head_up"),
                move("head_down"),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec(
                    "head_up", "head_down", 0, self._hold_release_delay_ms
                ),
            ),
            MotorControlSpec(
                "legs",
                "legs",
                move("foot_up"),
                move("foot_down"),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec(
                    "foot_up", "foot_down", 0, self._hold_release_delay_ms
                ),
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if self.profile.parser == "row" and self.profile.layout == "Zero-G Box":
            return ()
        return (
            ControllerStateSensorSpec(
                "app_timer_status", "app_timer_status", "app_timer_status", "mdi:timer-outline"
            ),
        )

    async def _wait(self, milliseconds: int, *, cleanup: bool = False) -> bool:
        """Return true when cancelled; never leave a disconnected session waiting."""
        if self._session_cancel.is_set():
            return True
        event = asyncio.Event() if cleanup else self._coordinator.cancel_command
        try:
            async with asyncio.timeout(milliseconds / 1000):
                await event.wait()
            return True
        except TimeoutError:
            return self._session_cancel.is_set()

    def _ready(self) -> None:
        if (
            self.client is None
            or self.client is not self._session_client
            or not self.client.is_connected
            or self._tx is None
            or self._rx is None
            or self._session_cancel.is_set()
        ):
            raise ConnectionError("Both current-session app characteristics must be ready")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._ready()
        session = self._session_cancel
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            async with self.ble_lock:
                # Resolve and validate inside the BLE lane too. A reconnect
                # while this task waited cannot transplant an old handle.
                self._ready()
                if session is not self._session_cancel:
                    raise ConnectionError("App write belongs to an expired session")
                if event.is_set():
                    return
                assert self._tx is not None and self.client is not None
                response = "write" in self._tx.properties
                payload = self._format_command_trace_payload(command)
                if payload is not None:
                    self._coordinator.record_command_trace(
                        payload=payload,
                        characteristic_uuid=self._tx.uuid,
                        characteristic_handle=self._tx.handle,
                        response=response,
                        repeat_count=repeat_count,
                        repeat_delay_ms=repeat_delay_ms,
                        command_origin="app_profile",
                        controller_class=type(self).__name__,
                    )
                await self.client.write_gatt_char(self._tx, command, response=response)
            if index + 1 < repeat_count and await self._wait(repeat_delay_ms):
                return

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if (
            self.client is self._session_client
            and self.client is not None
            and self.client.is_connected
            and self._rx is not None
            and self._tx is not None
            and not self._session_cancel.is_set()
        ):
            self._notify_callback = callback
            return
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("App session is disconnected")
        tx_uuids = {FFE9, NUS_TX} if self.profile.parser == "qplus" else {FFE9}
        rx_uuids = {FFE4, NUS_RX} if self.profile.parser == "qplus" else {FFE4}
        # Exact source selector: independent last match, with no service filter.
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.lower() in tx_uuids:
                    self._tx = char
                if char.uuid.lower() in rx_uuids:
                    self._rx = char
        if self._tx is None or self._rx is None:
            self.on_disconnect()
            raise ConnectionError(
                "The selected app requires both write and notification characteristics"
            )
        self._session_client = client
        self._session_cancel = asyncio.Event()
        self._notify_callback = callback
        if self.profile.parser == "qplus" and self.profile.layout == "MX":
            self._next_query = asyncio.get_running_loop().time() + 5
        session_cancel = self._session_cancel

        def notify(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if client is self._session_client and not session_cancel.is_set():
                self._on_notification(sender, data)

        await client.start_notify(self._rx, notify)
        if self.profile.parser == "qplus":
            if self.profile.layout == "MX":
                await self._queries((300, 600, 900))
            else:
                await self.write_command(control_frame(0, self._side))
        elif self.profile.clock_init_delay_ms is not None:
            if not await self._wait(self.profile.clock_init_delay_ms):
                await self.sync_clock()

    def on_disconnect(self) -> None:
        self._session_cancel.set()
        self._session_client = None
        self._tx = self._rx = None
        self._notify_callback = None
        self._next_query = None

    async def stop_notify(self) -> None:
        rx, client = self._rx, self._session_client
        self.on_disconnect()
        if client is not None and client.is_connected and rx is not None:
            await client.stop_notify(rx)

    async def _queries(self, offsets: tuple[int, ...], *, cleanup: bool = False) -> None:
        previous = 0
        for offset in offsets:
            if await self._wait(offset - previous, cleanup=cleanup):
                return
            await self.write_command(b"\x00\xb0", cancel_event=asyncio.Event() if cleanup else None)
            previous = offset

    def _frame(self, mask: int) -> bytes:
        if self.profile.parser == "qplus" and self.profile.layout == "MX":
            return mx_frame(mask)
        # Only Q-Plus P1 has an accepted A/B/Both wire selector. It is not a
        # guessed physical left/right identity and never follows command_side.
        return control_frame(mask, self._side if self.profile.parser == "qplus" else "both")

    async def _release(self) -> None:
        if self._session_client is not self.client or self._session_cancel.is_set():
            return
        if self.profile.parser == "qplus" and self.profile.layout == "MX":
            await self._queries((300, 600, 900), cleanup=True)
        else:
            await self.write_command(self._frame(0), cancel_event=asyncio.Event())

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = self._action(control)
        self._ready()
        elapsed = 0
        started = asyncio.get_running_loop().time()
        zeros = [300, 400, 500] if action.mode == "held_zeros" else []
        try:
            while elapsed < duration_ms:
                elapsed = max(elapsed, int((asyncio.get_running_loop().time() - started) * 1000))
                if elapsed >= duration_ms:
                    break
                if self._coordinator.cancel_command.is_set() or self._session_cancel.is_set():
                    break
                await self.write_command(self._frame(action.mask))
                for offset in tuple(zeros):
                    if offset <= elapsed:
                        await self.write_command(self._frame(0))
                        zeros.remove(offset)
                elapsed = max(elapsed, int((asyncio.get_running_loop().time() - started) * 1000))
                step = min(100, duration_ms - elapsed)
                if step <= 0 or await self._wait(step):
                    break
                elapsed += step
        finally:
            await self._release()
        # Source down-scheduled zeros remain after an ordinary early release.
        # Cancelled/disconnected sessions never retain background callbacks.
        for offset in zeros:
            if await self._wait(max(0, offset - elapsed)):
                return
            await self.write_command(self._frame(0))
            elapsed = max(elapsed, offset)

    async def _run_action(self, key: str) -> None:
        action = self._action(key)
        if action.mode in ("held", "held_zeros"):
            await self.hold_control(
                key, max(1, min(60000, self._coordinator.motor_pulse_count * 100))
            )
            return
        if action.mode == "pulse":
            try:
                await self.write_command(self._frame(action.mask))
                await self._wait(300)
            finally:
                await self._release()
        elif action.mode == "tap_zeros":
            complete = False
            try:
                await self.write_command(self._frame(action.mask))
                for delay in (300, 100, 100):
                    if await self._wait(delay):
                        break
                    await self.write_command(self._frame(0))
                else:
                    complete = True
            finally:
                if not complete:
                    await self._release()
        else:
            await self.write_command(self._frame(action.mask))
            if self.profile.parser == "qplus" and self.profile.layout == "MX":
                await self._queries((500, 800))

    async def stop_all(self) -> None:
        await self._release()

    async def move_head_up(self) -> None:
        await self._run_action("head_up")

    async def move_head_down(self) -> None:
        await self._run_action("head_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._run_action("foot_up")

    async def move_legs_down(self) -> None:
        await self._run_action("foot_down")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self._run_action("flat")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("App-labelled opaque keys are not physical memory slots")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("No physical memory save command is established")

    def validate_device_rename(self, name: str) -> None:
        self._device_name_frame(name)

    def _device_name_frame(self, name: str) -> bytes:
        if not self.profile.rename:
            raise ValueError("This app has no reachable device-name writer")
        # Caller domains are package-owned, not inferred from a shared EF02
        # builder. Java trim removes only code points <= U+0020.
        if self.profile.parser in ("curve", "serta", "ergomotion", "row", "slim", "au"):
            name = name.strip("".join(chr(value) for value in range(33)))
        elif name != name.strip():
            # Q-Plus has a14-unit editor, but its accepted report does not
            # establish the other apps' trimmed caller behavior.
            raise ValueError("Use a device name without outer spaces")
        max_units = 15 if self.profile.parser in ("row", "ergomotion") else 14
        return name_frame(name, max_units=max_units)

    async def rename_device(self, name: str) -> None:
        await self.write_command(self._device_name_frame(name))

    async def sync_clock(self) -> None:
        if not self.profile.clock:
            raise ValueError("This app has no clock writer")
        now = dt_util.now()
        await self.write_command(
            finish(
                bytes(
                    (
                        0xE7,
                        0x80,
                        1,
                        (now.year - 1900) & 255,
                        now.month - 1,
                        now.day,
                        now.hour,
                        now.minute,
                        now.second,
                    )
                )
            )
        )
        await self._wait(500)

    async def configure_alarm_table_schedule(self, schedule: AlarmTableSchedule) -> None:
        spec = self.alarm_table_schedule_spec
        if spec is None:
            raise ValueError("This app has no alarm-table contract")
        weekly, one_time = spec.encode(schedule)
        frames = (
            (weekly, one_time)
            if schedule.dispatch == "both"
            else (weekly,)
            if schedule.dispatch == "weekly"
            else (one_time,)
        )
        for frame in frames:
            await self.write_command(frame)
            if await self._wait(spec.dispatch_delay_ms):
                return

    async def stop_wake_routine(self) -> None:
        if not self.profile.shutdown_count:
            raise ValueError("This profile has no direct BLE alarm dismissal action")
        for _ in range(self.profile.shutdown_count):
            await self.write_command(b"\xe1\x80\x04\x9a")
            if await self._wait(self.profile.shutdown_delay_ms):
                return

    def _timer_byte(self, data: bytes) -> int | None:
        parser = self.profile.parser
        if len(data) == 16:
            if parser == "qplus" and data[:3] == b"\xa5\x0b\x0d":
                value = int.from_bytes(data[3:5], "big")
                return (value - 1) // 600 + 1 if 1 <= value <= 1800 else 255
            if data[13] & 32:
                return None
            if parser in ("qplus", "slim") and any(data[7:10]):
                return None
            return data[14]
        if len(data) == 19:
            if parser in ("omazz", "serta"):
                return None
            if parser == "ergomotion":
                return data[14] if data[0] == 0xF1 else data[15]
            if parser == "slim":
                return data[14] if data[0] == 0xF1 else data[15] if data[0] == 0xF4 else None
            if parser == "qplus":
                if any(data[7:10]):
                    return None
                return None if data[16] & 2 else data[15]
            return None if data[14] & 32 else data[15]
        if len(data) == 20 and parser != "serta":
            return data[14]
        if len(data) == 23 and parser in ("omazz", "qplus"):
            return data[15]
        return None

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(self._rx.uuid if self._rx is not None else FFE4, bytes(data))
        self._parse_notification(bytes(data))

    def _parse_notification(self, data: bytes | None) -> None:
        if not data:
            return
        if self.profile.parser == "row" and self.profile.layout == "Zero-G Box":
            return
        status = self._timer_byte(data)
        if status in (255, 1, 2, 3):
            self._timer_status = -1 if status == 255 else status
            self.forward_controller_state_updates({"app_timer_status": self._timer_status})
