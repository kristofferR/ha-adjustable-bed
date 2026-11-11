"""Resident Adjustable Base's fixed 36_33_01a profile and BLE session.

APK Protocol Audit unit160, com.okin.resident.release 1.0.0 (1).
Hardware remains unverified. The similarly named Rize Resident app is separate.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import sleep
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...controller_state import StateKey
from ...profiles.okin_nframe import (
    RESIDENT,
    RESIDENT_CLOCK_DELAY_MS,
    RESIDENT_CLOCK_QUERY_DELAY_MS,
    RESIDENT_INFO_DELAY_MS,
    RESIDENT_NOTIFY_RETRIES_MS,
    RESIDENT_QUERY_DELAY_MS,
)
from ..base import BedController
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from ..okin_64bit import Okin64BitController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
NOTIFY_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"
INFO_SERVICE: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MODEL_UUID: Final = "00002a24-0000-1000-8000-00805f9b34fb"
MASSAGE_TIMER: Final = StateKey[int | None]("resident_massage_timer")
QUERY_MASSAGE: Final = codec.request(4)
QUERY_CLOCK: Final = codec.prefixed_query((0xE1, 0x80, 0x01))
_MASSAGE_KEYS: Final = frozenset(
    {"massage_switch", "massage_off", "strength_up", "strength_down", "massage_timer"}
)


@dataclass(frozen=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    info: BleakGATTCharacteristic


class ResidentController(Okin64BitController):
    """Drive the shared 64-bit controller with Resident's own profile/session."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, char_uuid=codec.WRITE_UUID, profile=RESIDENT)
        self._link: _Link | None = None
        self._notifying = False
        self._parser = codec.MassageTimerParser()

    @property
    def has_lumbar_support(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return False

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_simultaneous_movement(self) -> bool:
        return True

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        return ("back", "legs")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Both axes use a global release, so they share a scheduling resource.
        return tuple(replace(s, scheduler_resource="*") for s in super().motor_control_specs[:2])

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 300

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in self.profile.keys if key != "stop")

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_tv": "tv_pc",
            "preset_lounge": "lounge",
            "preset_anti_snore": "anti_snore",
            "preset_memory_1": "memory_1",
            "preset_memory_2": "memory_2",
            "toggle_light": "light_toggle",
            "massage_toggle": "massage_switch",
            "massage_off": "massage_off",
            "massage_intensity_up": "strength_up",
            "massage_intensity_down": "strength_down",
            "massage_mode_step": "massage_timer",
        }.get(key)
        return ControllerHoldSpec(control) if control else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "resident_check_massage",
                "Refresh massage timer",
                lambda c: _resident(c).check_massage(),
                card=CARD_MASSAGE,
                translation_key="resident_check_massage",
                icon="mdi:refresh",
            ),
            ControllerButtonSpec(
                "resident_sync_clock",
                "Sync bed clock",
                lambda c: _resident(c).sync_clock(),
                card=CARD_UTILITY,
                translation_key="resident_sync_clock",
                icon="mdi:clock-check",
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "resident_massage_timer",
                "resident_massage_timer",
                MASSAGE_TIMER,
                "mdi:timer",
                native_unit_of_measurement="min",
                card=CARD_MASSAGE,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"resident_catalog": "36_33_01a", "resident_notifying": self._notifying}

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("Resident BLE session changed or disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("Resident is not connected")
        services = {s.uuid.lower(): s for s in client.services}
        control, info = services.get(codec.SERVICE_UUID), services.get(INFO_SERVICE)
        roles = {c.uuid.lower(): c for s in (control, info) if s for c in s.characteristics}
        write, notify, model = (
            roles.get(uuid) for uuid in (codec.WRITE_UUID, NOTIFY_UUID, MODEL_UUID)
        )
        if (
            write is None
            or "write" not in write.properties
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
            or model is None
            or "read" not in model.properties
        ):
            raise ValueError("Resident requires its exact write, notification and model-read roles")
        self._link = _Link(client, write, notify, model)

    async def _write(self, link: _Link, command: bytes, cancel: asyncio.Event) -> None:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                return
            self._record_command_trace(
                link.write.uuid, command, response=True, characteristic=link.write
            )
            await link.client.write_gatt_char(link.write, command, response=True)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(repeat_count):
            delay_ms = max(0.0, (started + index * repeat_delay_ms / 1000 - loop.time()) * 1000)
            if cancel.is_set() or index and await _pause(delay_ms, cancel):
                return
            await self._write(link, command, cancel)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            if (selector := self._parser.feed(bytes(data))) is not None:
                self.forward_controller_state_updates(
                    MASSAGE_TIMER({1: 10, 2: 20, 3: 30}.get(selector))
                )

        for attempt in range(len(RESIDENT_NOTIFY_RETRIES_MS) + 1):
            self._live(link)
            try:
                async with self._ble_lock:
                    self._live(link)
                    await link.client.start_notify(link.notify, receive)
                self._live(link)
                self._notifying = True
                return
            except BleakError:
                if attempt == len(RESIDENT_NOTIFY_RETRIES_MS):
                    raise
                await sleep(RESIDENT_NOTIFY_RETRIES_MS[attempt] / 1000)

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()  # Invalidate callbacks and delayed writes before awaiting.
        if notifying and link is not None and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._notify_callback = None
        self._parser = codec.MassageTimerParser()
        self.forward_controller_state_updates(MASSAGE_TIMER(None))

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()

        async def clock() -> None:
            await sleep(RESIDENT_CLOCK_DELAY_MS / 1000)
            self._live(link)
            await self.sync_clock()

        async def info() -> None:
            await sleep(RESIDENT_INFO_DELAY_MS / 1000)
            async with self._ble_lock:
                self._live(link)
                try:
                    async with asyncio.timeout(5):  # Integration guard, no app capability gate.
                        await link.client.read_gatt_char(link.info)
                except BleakError, TimeoutError:
                    _LOGGER.debug("Resident model-info read failed", exc_info=True)

        # Await startup so commands cannot race its clock/query writes. Each
        # branch stays bound to this link; no Android UI callback tasks survive it.
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(clock())
            tasks.create_task(info())
            tasks.create_task(self.check_massage())

    async def sync_clock(self) -> None:
        link = self._live()
        now = dt_util.now()
        loop = asyncio.get_running_loop()
        query_at = loop.time() + RESIDENT_CLOCK_QUERY_DELAY_MS / 1000
        await self._write(
            link,
            codec.calendar_record(
                0xE7,
                (
                    now.year - 1900,
                    now.month - 1,
                    now.day,
                    now.hour,
                    now.minute,
                    now.second,
                ),
            ),
            self._coordinator.cancel_command,
        )
        if not await _pause(
            max(0.0, (query_at - loop.time()) * 1000), self._coordinator.cancel_command
        ):
            await self._write(link, QUERY_CLOCK, self._coordinator.cancel_command)

    async def check_massage(self) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        query_at = loop.time() + RESIDENT_QUERY_DELAY_MS / 1000
        await self._write(link, QUERY_MASSAGE, cancel)
        if not await _pause(max(0.0, (query_at - loop.time()) * 1000), cancel):
            await self._write(link, QUERY_MASSAGE, cancel)

    async def _release(self, link: _Link, *, massage: bool = False) -> None:
        async def send() -> None:
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for index in range(self.profile.hold.releases):
                if index:
                    await sleep(
                        max(
                            0.0, started + index * self.profile.hold.release_ms / 1000 - loop.time()
                        )
                    )
                # Attempt the second STOP even when the first write fails.
                frames = (
                    (self._build_command(0), QUERY_MASSAGE)
                    if massage
                    else (self._build_command(0),)
                )
                for frame in frames:
                    try:
                        await self._write(link, frame, asyncio.Event())
                    except Exception as error:
                        failure = failure or error
            if failure:
                raise failure

        task = asyncio.create_task(send())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001 - propagated below.
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    async def _send_stop(self) -> None:
        await self._release(self._live())

    async def _move_with_stop(self, command: bytes, *, count: int | None = None) -> None:
        link = self._live()
        massage = command in {self._build_command(self.profile.keys[k]) for k in _MASSAGE_KEYS}
        if count is None:
            count = self.leased_hold_refreshes(300) or self._coordinator.motor_pulse_count
        try:
            await self.write_command(command, repeat_count=count)
        finally:
            await self._release(link, massage=massage)

    async def _press(self, word: int) -> None:
        await self._move_with_stop(
            self._build_command(word), count=self.leased_hold_refreshes(300) or 1
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        write_timeout = False
        deadline = asyncio.timeout(self.leased_hold_ms(duration_ms) / 1000)
        try:
            async with deadline:
                try:
                    await self._move_with_stop(
                        self._build_command(self.profile.keys[control]),
                        count=self.timed_move_repeat_count(self.leased_hold_ms(duration_ms), 300),
                    )
                except TimeoutError:
                    write_timeout = True
                    raise
        except TimeoutError:
            if write_timeout or not deadline.expired():
                raise

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unknown Resident held control")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Hold duration must be an integer from 1 to 60000 ms")

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        if {first_axis, second_axis} != {"back", "legs"} or first_up != second_up:
            raise ValueError("Resident combines back and legs only in the same direction")
        control = "head_foot_up" if first_up else "head_foot_down"
        if duration_ms is not None:
            await self.hold_control(control, duration_ms)
        else:
            await self._move_with_stop(self._build_command(self.profile.keys[control]))

    async def massage_off(self) -> None:
        await self._press(self.profile.keys["massage_off"])

    async def massage_intensity_up(self) -> None:
        await self._press(self.profile.keys["strength_up"])

    async def massage_intensity_down(self) -> None:
        await self._press(self.profile.keys["strength_down"])

    async def massage_mode_step(self) -> None:
        await self._press(self.profile.keys["massage_timer"])

    @property
    def massage_mode_step_is_timer(self) -> bool:
        return True


def _resident(controller: BedController) -> ResidentController:
    if not isinstance(controller, ResidentController):
        raise TypeError("This action requires Resident Adjustable Base")
    return controller


async def _pause(milliseconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    try:
        await asyncio.wait_for(cancel.wait(), milliseconds / 1000)
    except TimeoutError:
        return False
    return True
