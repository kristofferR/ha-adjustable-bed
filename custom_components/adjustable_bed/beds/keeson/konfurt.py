"""KONFURT's Keeson profile with a captured link, release and notification state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_UTILITY
from ...codec import keeson as codec
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import konfurt as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, massage_intensity
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
    massage_timer_sensor_spec,
)
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MASSAGE: Final = StateKey[bool | None]("konfurt_massage")
WAVE: Final = StateKey[int | None]("konfurt_wave")
ALARM_ON: Final = StateKey[bool | None]("konfurt_alarm_on")
ALARM_HOUR: Final = StateKey[int | None]("konfurt_alarm_hour")
ALARM_MINUTE: Final = StateKey[int | None]("konfurt_alarm_minute")
ALARM_REPEAT: Final = StateKey[int | None]("konfurt_alarm_repeat")
ALARM_TYPE: Final = StateKey[int | None]("konfurt_alarm_type")


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


def select_link(client: BleakClient) -> Link:
    """Fixed service/characteristic roles, never a UUID-based app inference."""
    tx_service = next((s for s in client.services if s.uuid.lower() == app.WRITE_SERVICE), None)
    rx_service = next((s for s in client.services if s.uuid.lower() == app.NOTIFY_SERVICE), None)
    tx = tx_service.get_characteristic(app.WRITE) if tx_service else None
    rx = rx_service.get_characteristic(app.NOTIFY) if rx_service else None
    if (
        tx is None or rx is None
        or not {"write", "write-without-response"}.intersection(tx.properties)
        or "notify" not in rx.properties
    ):
        raise BedNotConnectedError("konfurt_gatt")
    # No setWriteType in the app: respect the discovered characteristic's modes.
    return Link(client, tx, rx, "write-without-response" not in tx.properties)


def _press(control: str) -> MotorCommandCallable:
    async def press(controller: BedController) -> None:
        await cast(KonfurtController, controller).perform(control)
    return press


class KonfurtController(KeesonController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, variant: str = "2") -> None:
        if variant not in app.LAYOUTS:
            raise invalid("konfurt_layout")
        super().__init__(coordinator, variant="base", char_uuid=app.WRITE)
        self.layout = app.LAYOUTS[variant]
        self.profile = self.layout.profile
        self._variant = variant
        self._address = coordinator.address.upper()
        self._link: Link | None = None
        self._subscribed = False
        self._parser = codec.KonfurtParser()
        self._revision = 0

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"app": "KONFURT 1.0", "layout": self._variant,
                "hardware": "UNVERIFIED", "write_mode": "discovered characteristic properties"}

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def reports_massage_state(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return self._variant == "2"

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_capability(self) -> AlarmCapability:
        # Source always selects today's weekday, even if its time has passed.
        return AlarmCapability(wake_actions=tuple(app.ALARM_TYPES), cancel_running=True)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.weekdays or alarm.wake_action not in app.ALARM_TYPES:
            raise invalid("konfurt_alarm")

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (link is None or expected is not None and link is not expected
            or self.client is not link.client or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != self._address):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        self._link = select_link(client)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed:
            return
        self._notify_callback = callback

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self._live(link)
            except ConnectionError:
                return
            if sender.handle != link.notify.handle or sender.uuid.lower() != link.notify.uuid.lower():
                return
            self.forward_raw_notification(link.notify.uuid, bytes(data))
            result = self._parser.feed(bytes(data))
            if isinstance(result, codec.KonfurtAlarm):
                self.forward_controller_state_updates(
                    ALARM_ON(result.on), ALARM_HOUR(result.hour), ALARM_MINUTE(result.minute),
                    ALARM_REPEAT(result.repeat), ALARM_TYPE(result.type),
                )
            elif isinstance(result, codec.KonfurtStatus):
                self._revision += 1
                self.forward_controller_state_updates(
                    UNDER_BED_LIGHTS_ON(result.light), massage_intensity("head")(result.head),
                    massage_intensity("foot")(result.foot), MASSAGE(result.head > 0 or result.foot > 0),
                    MASSAGE_TIMER_MINUTES(result.time * 10), WAVE(result.wave),
                )

        await link.client.start_notify(link.notify, receive)
        self._live(link)
        self._subscribed = True
        # No app startup write/query. Alarm refresh is an explicit HA action.

    def invalidate_diagnostics(self) -> None:
        self._revision += 1
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None), MASSAGE(None), WAVE(None), MASSAGE_TIMER_MINUTES(None),
            massage_intensity("head")(None), massage_intensity("foot")(None), ALARM_ON(None),
            ALARM_HOUR(None), ALARM_MINUTE(None), ALARM_REPEAT(None), ALARM_TYPE(None),
        )

    def on_disconnect(self) -> None:
        self._link, self._subscribed = None, False
        self._parser = codec.KonfurtParser()
        self._notify_callback = None
        self._motor_state.clear()
        self.invalidate_diagnostics()

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscribed
        self.on_disconnect()
        if link is not None and subscribed and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    async def _write(self, link: Link, frame: bytes, cancel: asyncio.Event) -> None:
        async def send() -> None:
            async with self._ble_lock:
                self._live(link)
                if cancel.is_set():
                    note_frame_skipped()
                    return
                self._record_command_trace(link.write.uuid, frame, response=link.response,
                                           characteristic=link.write)
                await link.client.write_gatt_char(link.write, frame, response=link.response)
                note_frame_written(cancel)
        await settled(send())

    async def write_command(self, command: bytes, repeat_count: int = 1,
                            repeat_delay_ms: int = 300,
                            cancel_event: asyncio.Event | None = None) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if cancel.is_set():
                note_frame_skipped()
                return
            if index:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)
            await self._write(link, command, cancel)

    async def _release(self, link: Link) -> None:
        async def release() -> None:
            started = asyncio.get_running_loop().time()
            failure: Exception | None = None
            for at in app.RELEASE_MS:
                await asyncio.sleep(max(0, started + at / 1000 - asyncio.get_running_loop().time()))
                try:
                    await self._write(link, app.frame("stop", self.layout), asyncio.Event())
                except Exception as err:
                    failure = failure or err
            if failure is not None:
                raise failure
            context = current_command_context()
            if context is not None:
                context.cleanup_stop_sent = True
        await settled(release())

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return self.layout.controls

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.layout.controls or type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise invalid("konfurt_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link, frame = self._live(), app.frame(control, self.layout)
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            note_frame_skipped()
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        try:
            while not cancel.is_set() and loop.time() < deadline:
                next_at = loop.time() + app.REFRESH_MS / 1000
                await self._write(link, frame, cancel)
                await cancellable(asyncio.sleep(max(0, min(next_at, deadline) - loop.time())), cancel)
        finally:
            await self._release(link)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    async def perform(self, control: str) -> None:
        await self.hold_control(control, max(1, self._coordinator.motor_pulse_count * app.REFRESH_MS))

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
        else:
            axis = {"head": "back", "tilt": "head", "feet": "feet", "lumbar": "lumbar"}.get(motor, motor)
            await self.perform(f"{axis}_{'up' if direction else 'down'}")

    async def _preset(self, preset: str) -> None:
        await self.perform(preset)

    async def preset_reading(self) -> None:
        await self.perform("reading")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num != 1:
            raise invalid("konfurt_control")
        await self.perform("memory_1")

    async def stop_all(self) -> None:
        await self._release(self._live())

    async def lights_toggle(self) -> None:
        await self.perform("light")

    def _current_revision(self, link: Link, revision: int) -> bool:
        return (self._link is link and self._revision == revision
                and self.client is link.client and link.client.is_connected
                and self._coordinator.controller is self
                and self._coordinator.address.upper() == self._address)

    async def _move_back_legs(self, direction: bool | None) -> None:
        raise invalid("konfurt_control")

    async def _toggle_light_to(self, on: bool) -> None:
        link, revision = self._live(), self._revision
        reported = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
        if reported is None:
            raise invalid("light_state_unknown")
        if reported != on:
            with self.sent_state(UNDER_BED_LIGHTS_ON(on), is_current=lambda: self._current_revision(link, revision)):
                await self.lights_toggle()

    async def set_massage(self, on: bool) -> None:
        # On/off are the SAME source frame. Refuse unknown state rather than
        # claiming that this is an independently proven absolute off command.
        link, revision = self._live(), self._revision
        reported = self._coordinator.controller_state.get(MASSAGE)
        if reported is None:
            raise invalid("konfurt_massage_unknown")
        if reported != on:
            with self.sent_state(MASSAGE(on), is_current=lambda: self._current_revision(link, revision)):
                await self.perform("massage")

    async def sync_clock(self) -> None:
        await self.write_command(codec.clock(dt_util.now()))

    async def query_alarm(self) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        started = asyncio.get_running_loop().time()
        for at in app.QUERY_MS:
            await cancellable(asyncio.sleep(max(0, started + at / 1000 - asyncio.get_running_loop().time())), cancel)
            await self._write(link, app.ALARM_QUERY, cancel)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, cancel = self._live(), self._coordinator.cancel_command
        now = dt_util.now()
        if alarm.enabled:
            started = asyncio.get_running_loop().time()
            await self._write(link, codec.clock(now), cancel)
            await cancellable(asyncio.sleep(max(0, started + app.ALARM_DELAY_MS / 1000 - asyncio.get_running_loop().time())), cancel)
            frame = app.alarm(alarm.hour, alarm.minute, 1 << ((now.weekday() + 1) % 7),
                              app.ALARM_TYPES[alarm.wake_action])
        else:
            frame = app.alarm(0, 0, 0, 0)
        # Stored alarm state is readback only, never a fabricated acknowledgement.
        await self._write(link, frame, cancel)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [ControllerButtonSpec(
            f"konfurt_{key}", name, _press(key), translation_key=f"konfurt_{key}", card=card, combine_sides=True,
            hold=ControllerHoldSpec(key),
        ) for key, name, card in (
            ("massage", "Toggle massage", CARD_MASSAGE),
            ("massage_head", "Cycle head massage", CARD_MASSAGE),
            ("massage_foot", "Cycle feet massage", CARD_MASSAGE),
            ("massage_wave", "Cycle massage wave", CARD_MASSAGE),
            ("massage_timer", "Cycle massage timer", CARD_MASSAGE_TIMER),
        )]
        async def query(controller: BedController) -> None:
            await cast(KonfurtController, controller).query_alarm()
        specs.append(ControllerButtonSpec("konfurt_query_alarm", "Refresh bed alarm", query,
                                         translation_key="konfurt_query_alarm", card=CARD_UTILITY, combine_sides=True))
        return tuple(specs)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        async def toggle(controller: BedController, on: bool) -> None:
            await cast(KonfurtController, controller).set_massage(on)
        return (ControllerSwitchSpec("konfurt_massage", "konfurt_massage", toggle, state_key=MASSAGE,
                                     card=CARD_MASSAGE),)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            massage_timer_sensor_spec("konfurt_timer", "konfurt_timer", MASSAGE_TIMER_MINUTES,
                                      card=CARD_MASSAGE_TIMER),
            *(ControllerStateSensorSpec(str(key), str(key), key, "mdi:alarm") for key in
              (WAVE, ALARM_ON, ALARM_HOUR, ALARM_MINUTE, ALARM_REPEAT, ALARM_TYPE)),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # The four-motor artwork says all, but the source writes lumbar only.
        return tuple(MotorControlSpec(
            axis, "legs" if axis == "feet" else axis, _press(f"{axis}_up"), _press(f"{axis}_down"),
            _stop, hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", stop_scope="side"),
        ) for axis in self.layout.axes)


async def _stop(controller: BedController) -> None:
    await controller.stop_all()


async def build_controller(ctx: BuildContext) -> KonfurtController:
    variant = ctx.variant or ctx.data.get("protocol_variant", "2")
    return KonfurtController(ctx.coordinator, variant="2" if variant == "auto" else variant)
