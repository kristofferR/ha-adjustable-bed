"""Symphony Sleep's session and gesture behavior over the shared Keeson controller."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...app_session import app_session
from ...card import CARD_MASSAGE_TIMER, CARD_UTILITY
from ...codec import keeson as codec
from ...codec import okin_nframe
from ...command_scheduler import current_command_context
from ...const import CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...profiles import symphony_sleep as app
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .controller import KeesonController, _wait_unless_cancelled

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
TIMER: Final = StateKey[int | None]("symphony_massage_minutes")
ALARM_TIME: Final = StateKey[str | None]("symphony_alarm_time")
ALARM_ENABLED: Final = StateKey[bool | None]("symphony_alarm_enabled")
ALARM_WAKE: Final = StateKey[str | None]("symphony_alarm_wake")


@dataclass(slots=True)
class _AppState:
    publisher: object | None = None
    minutes: int = 0
    alarm: codec.SymphonyAlarm | None = None


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    owner: object


class SymphonySleepController(KeesonController):
    """Five explicit app models, three independent dispatch outcomes, one receiver."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        self.route = str(coordinator.entry.data.get(CONF_PROTOCOL_VARIANT, ""))
        self.model = str(coordinator.entry.data.get(CONF_PRODUCT_TYPE, ""))
        if self.route not in app.PROFILES or self.model not in app.MODELS:
            raise ValueError("Choose the Symphony Sleep model and Box 1, Box 2 or fallback transport")
        super().__init__(coordinator, char_uuid=codec.TRANSPORTS[app.PROFILES[self.route].transport].write_uuid)
        self.profile = app.PROFILES[self.route]
        self._char_uuid = codec.TRANSPORTS[self.profile.transport].write_uuid
        self._notify_char_uuid = codec.TRANSPORTS[self.profile.transport].notify_uuid
        self._app_state = app_session(coordinator.hass, coordinator.address,
                                      "symphony_sleep", _AppState)
        self._link: _Link | None = None
        self._notifying = False
        self._parser = codec.SymphonyParser(p2=self.route == "box2")
        self._jobs: set[asyncio.Task[None]] = set()

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    @property
    def supports_lights(self) -> bool:
        return app.MODELS[self.model].accessories

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_massage(self) -> bool:
        return app.MODELS[self.model].accessories

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return False

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_intensity_preset_control(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage

    @property
    def has_lumbar_support(self) -> bool:
        return self.model == "SS600"

    @property
    def has_tilt_support(self) -> bool:
        return self.model == "600E"

    def _role(self, service_uuid: str, char_uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Symphony Sleep is disconnected")
        service = client.services.get_service(service_uuid)
        char = service.get_characteristic(char_uuid) if service is not None else None
        if char is None:
            raise BleakError(f"Symphony Sleep requires {char_uuid} under {service_uuid}")
        return char

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        transport = codec.TRANSPORTS[self.profile.transport]
        write = self._role(transport.service_uuid, transport.write_uuid)
        notify = self._role(transport.service_uuid if self.route == "box2" else codec.JALON_NOTIFY_SERVICE,
                            transport.notify_uuid)
        if not {"write", "write-without-response"}.intersection(write.properties):
            raise BleakError("Symphony Sleep control characteristic is not writable")
        if not {"notify", "indicate"}.intersection(notify.properties):
            raise BleakError("Symphony Sleep notification characteristic cannot subscribe")
        client = self.client
        assert client is not None
        owner = object()
        self._app_state.publisher = owner
        self._link = _Link(client, write, notify, owner)

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (current is None or link is not None and current is not link
            or current.owner is not self._app_state.publisher
            or self.client is not current.client or not current.client.is_connected):
            raise ConnectionError("Symphony Sleep command belongs to an ended BLE session")
        transport = codec.TRANSPORTS[self.profile.transport]
        if (self._role(transport.service_uuid, current.write.uuid) is not current.write
            or self._role(transport.service_uuid if self.route == "box2" else codec.JALON_NOTIFY_SERVICE, current.notify.uuid) is not current.notify
            or not {"write", "write-without-response"}.intersection(current.write.properties)
            or not {"notify", "indicate"}.intersection(current.notify.properties)):
            raise ConnectionError("Symphony Sleep live GATT roles changed")
        return current

    def validate_clock_sync(self) -> None:
        try:
            self._live()
        except (ConnectionError, BleakError) as err:
            raise ValueError(str(err)) from err

    async def _send(self, link: _Link, command: bytes, cancel: asyncio.Event) -> None:
        def check_session() -> None:
            self._live(link)

        check_session()
        await self._write_gatt_with_retry(
            link.write.uuid, command, cancel_event=cancel,
            response="write" in link.write.properties, characteristic=link.write,
            expected_client=link.client, before_write=check_session,
        )

    async def write_command(self, command: bytes, repeat_count: int = 1,
                            repeat_delay_ms: int = 300,
                            cancel_event: asyncio.Event | None = None) -> None:
        link = self._live()
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if event.is_set():
                return
            await self._send(link, command, event)
            if index < repeat_count - 1:
                await _wait_unless_cancelled(event, repeat_delay_ms / 1000)

    async def _release(self, link: _Link) -> None:
        """Keep all three STOPs inside the admitted lane on the captured link."""
        packet = self._build_command(0)
        context = current_command_context()

        async def cleanup() -> None:
            failure: Exception | None = None
            start = asyncio.get_running_loop().time()
            for delay in (0, 0.3, 0.6):
                await asyncio.sleep(max(0, start + delay - asyncio.get_running_loop().time()))
                try:
                    await self._send(link, packet, asyncio.Event())
                except (ConnectionError, BleakError) as err:
                    failure = failure or err
            if failure is not None:
                raise failure
            if context is not None:
                context.cleanup_stop_sent = True

        task = asyncio.create_task(cleanup())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    def _queries(self, link: _Link, packet: bytes, delays: tuple[float, ...], *, start: float) -> None:
        async def run() -> None:
            try:
                for delay in delays:
                    await asyncio.sleep(max(0, start + delay - asyncio.get_running_loop().time()))
                    await self._send(link, packet, asyncio.Event())
            except (ConnectionError, BleakError):
                _LOGGER.debug("Symphony Sleep follow-up ended with its BLE session", exc_info=True)

        task = asyncio.create_task(run())
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    async def _gesture(self, word: int, duration_ms: int, *, massage: bool = False) -> None:
        link = self._live()
        packet = self._build_command(word)
        event = self._coordinator.cancel_command
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        queried = False
        try:
            while not event.is_set() and asyncio.get_running_loop().time() < deadline:
                write_started = asyncio.get_running_loop().time()
                next_write = write_started + app.REFRESH_MS / 1000
                await self._send(link, packet, event)
                if massage and self.route == "box2" and not queried:
                    self._queries(link, okin_nframe.request(0xB0), (0.3, 0.6), start=write_started)
                    queried = True
                await _wait_unless_cancelled(event, min(next_write, deadline) - asyncio.get_running_loop().time())
        finally:
            await self._release(link)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    async def move_axis(self, axis: str, up: bool) -> None:
        if axis not in app.MODELS[self.model].axes:
            raise ValueError("This Symphony Sleep model has no such control")
        count = self.leased_hold_refreshes(app.REFRESH_MS) or self._coordinator.motor_pulse_count
        _, up_word, down_word = app.AXES[axis]
        await self._gesture(up_word if up else down_word, count * app.REFRESH_MS)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
        else:
            await self.move_axis(motor, direction)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(MotorControlSpec(
            axis, app.AXES[axis][0],
            lambda c, axis=axis: cast(SymphonySleepController, c).move_axis(axis, True),
            lambda c, axis=axis: cast(SymphonySleepController, c).move_axis(axis, False),
            lambda c: c.stop_all(), scheduler_resource="*",
            hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None),
        ) for axis in app.MODELS[self.model].axes)

    async def stop_all(self) -> None:
        link = self._live()
        context = current_command_context()
        if context is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await self._release(link)

    async def _write_single_shot(self, command: bytes) -> None:
        # Shared Keeson preset/light dispatch already selected the app's frame.
        word = int.from_bytes(command[2:6], "big") if self.route == "box2" else int.from_bytes(command[3:7], "little")
        await self._gesture(word, app.REFRESH_MS)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        await self.hold_control(f"memory_{slot}", hold_ms)

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._gesture(app.MEMORY[memory_num], app.SAVE_MS)

    async def massage_intensity_up(self) -> None:
        await self.hold_control("massage_intensity_up", app.REFRESH_MS)

    async def massage_intensity_down(self) -> None:
        await self.hold_control("massage_intensity_down", app.REFRESH_MS)

    async def massage_off(self) -> None:
        await self.hold_control("massage_off", app.REFRESH_MS)

    async def massage_mode_step(self) -> None:
        await self.hold_control("massage_timer", app.REFRESH_MS)

    async def massage_wave_next(self) -> None:
        await self.hold_control("massage_wave_next", app.REFRESH_MS)

    async def massage_wave_previous(self) -> None:
        await self.hold_control("massage_wave_previous", app.REFRESH_MS)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in app.HELD if (
            key in app.PRESETS or key in ("memory_1", "memory_2")
            or key.removesuffix("_up").removesuffix("_down") in app.MODELS[self.model].axes
            or self.supports_massage and key in app.MASSAGE
            or self.supports_lights and key == "light_toggle"
        ))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or type(duration_ms) is not int or not 1 <= duration_ms <= 30000:
            raise ValueError("Choose an available Symphony Sleep control and 1–30000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._gesture(app.HELD[control], self.leased_hold_ms(duration_ms), massage=control in app.MASSAGE)

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {"preset_flat": "flat", "preset_zero_g": "zero_g", "preset_anti_snore": "anti_snore",
                   "preset_memory_1": "memory_1", "preset_memory_2": "memory_2", "toggle_light": "light_toggle",
                   "massage_mode_step": "massage_timer", "massage_all_up": "massage_intensity_up",
                   "massage_all_down": "massage_intensity_down", "massage_all_off": "massage_off"}.get(key, key)
        return ControllerHoldSpec(control) if control in self.held_control_options else None

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(app.WAKE)

    async def sync_clock(self) -> None:
        link = self._live()
        await self._send(link, app.clock(self.route, dt_util.now()), self._coordinator.cancel_command)

    async def query_alarm(self) -> None:
        link = self._live()
        packet = app.alarm_query(self.route)
        started = asyncio.get_running_loop().time()
        await self._send(link, packet, self._coordinator.cancel_command)
        self._queries(link, packet, (0.2,), start=started)

    async def configure_clock_alarm(self, *, enabled: bool, weekdays: Sequence[int], hour: int,
                                    minute: int, preset: str, head_level: int = 0, foot_level: int = 0) -> None:
        app.validate_alarm(weekdays=weekdays, head_level=head_level, foot_level=foot_level)
        packet = app.alarm(self.route, enabled=enabled, hour=hour, minute=minute, wake=preset)
        link = self._live()
        event = self._coordinator.cancel_command
        rtc_started = asyncio.get_running_loop().time()
        await self._send(link, app.clock(self.route, dt_util.now()), event)
        await _wait_unless_cancelled(event, rtc_started + 0.3 - asyncio.get_running_loop().time())
        if event.is_set():
            return
        alarm_started = asyncio.get_running_loop().time()
        await self._send(link, packet, event)
        if self.route == "box2":
            self._queries(link, app.alarm_query(self.route), (0.3, 0.5), start=alarm_started)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec("symphony_query_alarm", "Refresh bed alarm", lambda c: cast(SymphonySleepController, c).query_alarm(),
                                 translation_key="symphony_query_alarm", card=CARD_UTILITY, scheduler_resource="*"),
            ControllerButtonSpec("symphony_sync_clock", "Sync bed clock", lambda c: c.sync_clock(),
                                 translation_key="symphony_sync_clock", card=CARD_UTILITY, scheduler_resource="*"),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            *((ControllerStateSensorSpec("symphony_massage_minutes", "symphony_massage_minutes", TIMER,
                                        "mdi:timer", native_unit_of_measurement="min", card=CARD_MASSAGE_TIMER),)
              if self.supports_massage else ()),
            ControllerStateSensorSpec("symphony_alarm_time", "symphony_alarm_time", ALARM_TIME, "mdi:alarm",
                                      attribute_keys=(ALARM_ENABLED, ALARM_WAKE), card=CARD_UTILITY),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (ControllerStateBinarySensorSpec("symphony_alarm_enabled", "symphony_alarm_enabled",
                                                ALARM_ENABLED, "mdi:alarm", card=CARD_UTILITY),)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is None:
            await self.async_discover_capabilities()
        link = self._live()
        try:
            await link.client.start_notify(link.notify, lambda sender, data: self._notification(link, sender, data))
            self._live(link)
        except BaseException:
            self.on_disconnect()
            raise
        self._notifying = True

    def _notification(self, link: _Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            self._live(link)
        except ConnectionError:
            return
        if sender.handle != link.notify.handle:
            return
        raw = bytes(data)
        self.forward_raw_notification(link.notify.uuid, raw)
        if self.route == "fallback":
            return
        status = self._parser.feed(raw, self._app_state.minutes)
        if isinstance(status, codec.SymphonyTimer):
            self._app_state.minutes = status.minutes
            if self.supports_massage:
                self.forward_controller_state_updates(TIMER(status.minutes))
        elif isinstance(status, codec.SymphonyAlarm):
            self._app_state.alarm = status
            self.forward_controller_state_updates(ALARM_TIME(f"{status.hour:02}:{status.minute:02}"),
                                                   ALARM_ENABLED(status.enabled), ALARM_WAKE(status.wake))

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if link is not None and notifying and self.client is link.client and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        link, self._link = self._link, None
        self._notifying = False
        self._parser = codec.SymphonyParser(p2=self.route == "box2")
        for task in self._jobs:
            task.cancel()
        self._jobs.clear()
        if link is not None and self._app_state.publisher is link.owner:
            self._app_state.publisher = None
            self.forward_controller_state_updates(TIMER(None), ALARM_TIME(None), ALARM_ENABLED(None), ALARM_WAKE(None))
