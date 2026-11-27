"""Amada Smart's bounded direct BLE session over the shared Okin controller."""
from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_PRESET_SAVE, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...profiles.amada import (
    ALARM_MODES,
    AMADA,
    MOTOR_KEYS,
    NOTIFY_UUID,
    PRESETS,
    RECALL_MS,
    REFRESH_MS,
    SAVE_MS,
    SAVES,
    SELECTORS,
    SERVICE_UUID,
    UTILITY_TAILS,
    WRITE_UUID,
    alarm_frame,
    alarm_week,
    clock_frame,
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
from ..okin_64bit import Okin64BitController
from . import state as s
from .receive import Alarm, Massage, parse

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


@dataclass(frozen=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class AmadaController(Okin64BitController):
    """Explicit app selector, one serialized stream, no physical side inference."""

    def __init__(self, coordinator: AdjustableBedCoordinator, selector: str) -> None:
        if selector not in SELECTORS:
            raise ValueError("Choose the Amada app target A, AB or B")
        super().__init__(coordinator, char_uuid=WRITE_UUID, profile=AMADA)
        self._selector = SELECTORS[selector]
        self._link: _Link | None = None
        self._is_current: Callable[[], bool] = lambda: True
        self._notifying = False
        self._alarm: Alarm | None = None
        self._alarm_has_marker = False
        self._alarm_revision = 0
        self._disable_checked: tuple[_Link, Alarm, int] | None = None
        self._reply = asyncio.Event()
        self._last_alarm: tuple[bytes, float] | None = None

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
    def supports_massage(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"amada_selector": self._selector, "source_status": "PARTIAL (B1/B2)",
                "hardware_status": "UNVERIFIED"}

    def _build_command(self, word: int) -> bytes:
        return codec.frame40(word, self._selector)

    def _current(self, link: _Link) -> bool:
        return (self._link is link and self.client is link.client
                and link.client.is_connected and self._is_current())

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if link is None or expected is not None and link is not expected or not self._current(link):
            raise ConnectionError("Amada BLE session changed or disconnected")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Amada is not connected")
        roles = {c.uuid.lower(): c for service in client.services
                 if service.uuid.lower() == SERVICE_UUID for c in service.characteristics}
        write, notify = roles.get(WRITE_UUID), roles.get(NOTIFY_UUID)
        if (write is None or "write-without-response" not in write.properties
                or notify is None or not {"notify", "indicate"}.intersection(notify.properties)):
            raise ValueError("Amada requires its no-response write and notification roles")
        self._link = _Link(client, write, notify)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._current(link):
                return
            raw = bytes(data)
            self.forward_raw_notification(sender.uuid, raw)
            report = parse(raw, self._selector)
            if isinstance(report, Massage):
                self.forward_controller_state_updates(
                    s.MASSAGE_TIME(report.time), s.MASSAGE_HEAD(report.head),
                    s.MASSAGE_FOOT(report.foot), s.MASSAGE_MODE(report.mode),
                    s.MASSAGE_ON(report.on), s.LIGHT(report.light),
                )
            elif isinstance(report, Alarm):
                now = asyncio.get_running_loop().time()
                if self._last_alarm and self._last_alarm[0] == raw and now - self._last_alarm[1] < 0.5:
                    return
                self._last_alarm = raw, now
                self._alarm = report
                self._alarm_has_marker = any(
                    len(raw) >= offset + 7 and raw[offset] in (0xAA, 0xBB)
                    for offset in (3, 10)
                )
                self._alarm_revision += 1
                self.forward_controller_state_updates(
                    s.ALARM_TIME(f"{report.hour:02d}:{report.minute:02d}"),
                    s.ALARM_ENABLED(report.enabled), s.ALARM_REPEAT(report.repeat),
                    s.ALARM_KIND(report.kind),
                )
                self._reply.set()

        for attempt in range(2):
            try:
                async with self._ble_lock:
                    self._live(link)
                    await link.client.start_notify(link.notify, receive)
                self._live(link)
                self._notifying = True
                return
            except BleakError:
                if attempt:
                    raise
                await asyncio.sleep(1)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._alarm = None
        self._alarm_has_marker = False
        self._disable_checked = None
        self._last_alarm = None
        self._reply.set()
        self.forward_controller_state_updates(
            s.MASSAGE_TIME(None), s.MASSAGE_HEAD(None), s.MASSAGE_FOOT(None),
            s.MASSAGE_MODE(None), s.MASSAGE_ON(None), s.LIGHT(None),
            s.ALARM_TIME(None), s.ALARM_ENABLED(None), s.ALARM_REPEAT(None),
            s.ALARM_KIND(None), s.ALARM_SENT(None),
        )

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if link and notifying and self.client is link.client and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    async def async_on_connect(self, session: ControllerSession) -> None:
        self._is_current = session.is_current
        await session.async_start_notify()
        await self.sync_clock()

    async def _write(self, link: _Link, frame: bytes, cancel: asyncio.Event,
                     *, before_write: Callable[[], None] | None = None,
                     on_write: Callable[[], None] | None = None) -> bool:
        self._live(link)
        written = False

        def check() -> None:
            self._live(link)
            if before_write:
                before_write()

        def delivered() -> None:
            nonlocal written
            written = True
            if on_write:
                on_write()

        await self._write_gatt_with_retry(
            WRITE_UUID, frame, cancel_event=cancel, response=False,
            characteristic=link.write, expected_client=link.client, before_write=check,
            on_write=delivered, settle_write=True,
        )
        self._live(link)
        return written

    async def write_command(self, command: bytes, repeat_count: int = 1,
                            repeat_delay_ms: int = REFRESH_MS,
                            cancel_event: asyncio.Event | None = None) -> None:
        link, cancel = self._live(), cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if not await self._write(link, command, cancel):
                return
            if index + 1 < repeat_count and await self._wait(cancel, repeat_delay_ms / 1000):
                return

    @staticmethod
    async def _wait(cancel: asyncio.Event, seconds: float) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
            return True
        except TimeoutError:
            return False

    async def _release(self, link: _Link) -> None:
        await self._write(link, self._build_command(0), asyncio.Event())

    async def _send_stop(self) -> None:
        await self._release(self._live())

    async def _stream(self, key: str, duration_ms: int, *, save: bool = False) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        completed = False

        async def cleanup() -> None:
            # Source save completion ends refresh only. An interrupted save still releases.
            if not save or not completed:
                await self._release(link)

        async with self.releasing(cleanup):
            started = asyncio.get_running_loop().time()
            for _ in range(math.ceil(duration_ms / REFRESH_MS)):
                tick = asyncio.get_running_loop().time()
                if cancel.is_set() or not await self._write(link, self._build_command(AMADA.keys[key]), cancel):
                    return
                delay = max(0, min(started + duration_ms / 1000, tick + REFRESH_MS / 1000) - asyncio.get_running_loop().time())
                if await self._wait(cancel, delay):
                    return
                if asyncio.get_running_loop().time() >= started + duration_ms / 1000:
                    break
            completed = not cancel.is_set() and self._current(link)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, REFRESH_MS

    async def _move_with_stop(self, command: bytes) -> None:
        key = next(key for key in MOTOR_KEYS if self._build_command(AMADA.keys[key]) == command)
        await self.hold_control(key, self._coordinator.motor_pulse_count * REFRESH_MS)

    async def move_head_up(self) -> None:
        await self.hold_control("tilt_up", self._coordinator.motor_pulse_count * REFRESH_MS)

    async def move_head_down(self) -> None:
        await self.hold_control("tilt_down", self._coordinator.motor_pulse_count * REFRESH_MS)

    async def move_back_up(self) -> None:
        await self.hold_control("head_up", self._coordinator.motor_pulse_count * REFRESH_MS)

    async def move_back_down(self) -> None:
        await self.hold_control("head_down", self._coordinator.motor_pulse_count * REFRESH_MS)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(MotorControlSpec(
            axis, label,
            lambda c, key=up: require_controller(c, AmadaController).hold_control(key, 1000),
            lambda c, key=down: require_controller(c, AmadaController).hold_control(key, 1000),
            lambda c: c.stop_all(), scheduler_resource="*",
            hold=ControllerMotorHoldSpec(up, down, stop_scope="side"),
        ) for axis, label, up, down in (
            ("back", "back", "head_up", "head_down"),
            ("legs", "legs", "foot_up", "foot_down"),
            ("head", "head", "tilt_up", "tilt_down"),
            ("combined", "head_feet", "combined_up", "combined_down"),
        ))

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*MOTOR_KEYS, *PRESETS)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        maximum = 5999 if control in SAVES else 30000
        if control not in self.held_control_options or type(duration_ms) is not int or not 1 <= duration_ms <= maximum:
            raise ValueError("Choose an Amada control and a safe bounded duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        duration = self.leased_hold_ms(duration_ms) if control in MOTOR_KEYS else duration_ms
        await self._stream(control, duration)

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        return ControllerHoldSpec(key) if key in PRESETS else None

    async def _press(self, word: int) -> None:
        key = next(key for key, value in AMADA.keys.items() if value == word)
        if key in UTILITY_TAILS:
            await self.utility(key)
        else:
            await self.hold_control(key, RECALL_MS)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("Amada has one memory slot")
        await self.hold_control("memory_1", RECALL_MS)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise ValueError("Amada has one memory slot")
        await self.save_preset("memory_1")

    async def save_preset(self, key: str) -> None:
        if key not in SAVES:
            raise ValueError("This preset has no save gesture")
        await self._stream(key, SAVE_MS, save=True)

    async def reset_memory(self) -> None:
        await self._stream("reset_memory", SAVE_MS)

    async def utility(self, key: str) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        frames = (self._build_command(AMADA.keys[key]),) * 4 + (codec.request(0xB0),) * UTILITY_TAILS[key]
        await self._batch(link, frames, cancel)

    async def _batch(self, link: _Link, frames: tuple[bytes, ...], cancel: asyncio.Event) -> None:
        for index, frame in enumerate(frames):
            tick = asyncio.get_running_loop().time()
            if not await self._write(link, frame, cancel):
                return
            if index + 1 < len(frames) and await self._wait(cancel, max(0, tick + REFRESH_MS / 1000 - asyncio.get_running_loop().time())):
                return

    async def sync_clock(self) -> None:
        link = self._live()
        clock = clock_frame(dt_util.now())
        await self._batch(link, (clock,) * 4 + (codec.request(0xB0),) * 2 + (codec.request(0xC0),) * 2,
                          self._coordinator.cancel_command)

    async def query(self, code: int) -> None:
        if code not in (0xB0, 0xC0):
            raise ValueError("Unknown Amada query")
        await self._batch(self._live(), (codec.request(code),) * 4, self._coordinator.cancel_command)

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(wake_actions=tuple(ALARM_MODES), weekdays=True, resource="*", live_check=True)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if (alarm.slot != 1 or alarm.wake_action not in ALARM_MODES
                or not 0 <= alarm.hour <= 23 or not 0 <= alarm.minute <= 59):
            raise ValueError("Invalid Amada alarm")
        alarm_week(alarm.weekdays, alarm.hour, alarm.minute, dt_util.now())

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        self._disable_checked = None
        if alarm.enabled:
            return
        link = self._live()
        revision = self._alarm_revision
        self._reply.clear()
        self._last_alarm = None
        await self.query(0xC0)
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        async with asyncio.timeout(2):  # HA wait bound, not a protocol timing claim.
            while self._alarm_revision == revision:
                await self._reply.wait()
                self._live(link)
                self._reply.clear()
        report = self._alarm
        assert report is not None
        if not self._alarm_has_marker or not 0 <= report.hour <= 23 or not 0 <= report.minute <= 59 or report.kind not in ALARM_MODES.values():
            raise ValueError("Amada reported an unsupported alarm")
        self._disable_checked = link, report, self._alarm_revision

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, cancel = self._live(), self._coordinator.cancel_command
        if not alarm.enabled:
            if self._disable_checked is None:
                await self.check_alarm(alarm)
            assert self._disable_checked is not None
            checked_link, report, revision = self._disable_checked
            self._disable_checked = None
            self._live(checked_link)
            frame = alarm_frame(report.hour, report.minute, report.repeat, report.kind, False, self._selector)
        else:
            frame = alarm_frame(alarm.hour, alarm.minute,
                                alarm_week(alarm.weekdays, alarm.hour, alarm.minute, alarm.reference_time),
                                ALARM_MODES[alarm.wake_action], True, self._selector)
            revision = self._alarm_revision

        def unchanged() -> None:
            if self._alarm_revision != revision:
                raise ValueError("Amada alarm changed before dispatch")

        submitted = False

        def sent() -> None:
            nonlocal submitted
            submitted = True

        with self.sent_state(s.ALARM_SENT(frame.hex()), is_current=lambda: submitted and self._current(link)):
            await self._write(link, frame, cancel, before_write=unchanged, on_write=sent)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *(ControllerButtonSpec(
                "amada_save_" + key, "Save " + key.replace("_", " "),
                lambda c, key=key: require_controller(c, AmadaController).save_preset(key),
                translation_key="catalog_save", translation_placeholders={"preset": key.replace("_", " ")},
                card=CARD_PRESET_SAVE, requires_confirmation=True,
            ) for key in SAVES if key != "memory_1"),
            ControllerButtonSpec("amada_reset", "Reset saved positions",
                lambda c: require_controller(c, AmadaController).reset_memory(),
                translation_key="amada_reset", requires_confirmation=True, card=CARD_UTILITY),
            *(ControllerButtonSpec("amada_" + key, key.replace("_", " "),
                lambda c, key=key: require_controller(c, AmadaController).utility(key),
                translation_key="amada_" + key, card=CARD_MASSAGE,
            ) for key in ("foot_strength_up", "foot_strength_down", "timer_step")),
            *(ControllerButtonSpec("amada_query_" + str(code), label,
                lambda c, code=code: require_controller(c, AmadaController).query(code),
                translation_key=translation, card=CARD_UTILITY,
            ) for code, label, translation in ((0xB0, "Refresh massage and light", "amada_refresh"),
                                               (0xC0, "Refresh alarm", "amada_refresh_alarm"))),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(ControllerStateSensorSpec(str(key), str(key), key, "mdi:bed") for key in (
            s.MASSAGE_TIME, s.MASSAGE_HEAD, s.MASSAGE_FOOT, s.MASSAGE_MODE,
            s.MASSAGE_ON, s.LIGHT, s.ALARM_TIME, s.ALARM_ENABLED,
            s.ALARM_REPEAT, s.ALARM_KIND, s.ALARM_SENT,
        ))


async def build_controller(ctx: BuildContext) -> AmadaController:
    selector = ctx.data.get("product_type")
    if not isinstance(selector, str) or selector not in SELECTORS:
        raise ValueError("Choose the Amada app target A, AB or B")
    return AmadaController(ctx.coordinator, selector)
