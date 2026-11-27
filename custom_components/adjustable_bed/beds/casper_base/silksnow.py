"""S&S Base product policies over the shared Richmat controller and codec."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...codec import richmat as codec
from ...errors import BedNotConnectedError, invalid
from ...profiles.silksnow import ACTIONS, EXCLUDED_ACTIONS, MASSAGE_TEXT, PROFILES
from ...state_keys import LIGHT_TIMER_OPTION, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import ControllerButtonSpec, ControllerHoldSpec
from .controller import (
    CASPER_BASE_ALARMS,
    CASPER_BASE_EVENTS,
    CASPER_BASE_MODEL,
    GATT,
    CasperBaseController,
)
from .protocol import RGB_TIMERS, Event, MainReceive, decode_main

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic | None
    single: bool


@dataclass
class Operation:
    link: Link
    attempted: set[int] = field(default_factory=set)
    side: int | None = None


class Receive(MainReceive):
    """The app consumes common fragments and validates length-bearing frames."""

    def feed(self, chunk: bytes) -> list[bytes]:
        self.pending.extend(chunk)
        out: list[bytes] = []
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            extended = self.pending[1] == 0x20
            size = self.pending[2] if extended else self.pending.find(0x6E, 1)
            if extended and size < 7:
                self.pending.clear()
                raise ValueError("Invalid extended notification length")
            if extended and len(self.pending) < size:
                break
            if size < 0:
                size = len(self.pending)
            packet = bytes(self.pending[:size])
            del self.pending[:size]
            if not extended or codec.is_valid(packet):
                out.append(packet)
        return out


def decode(packet: bytes) -> Event | None:
    event = decode_main(packet)
    if event is None or event.name in {
        "aroma_available",
        "music_available",
        "snore_available",
        "desk",
        "desk_extra",
        "accessories",
        "music_volume",
        "shake_gear",
        "snore_detection",
        "bed_exit",
        "sleep_name",
        "music_play",
        "music_bluetooth",
        "music_follow_intensity",
    }:
        return None
    if event.name == "detection_details":
        return Event("detection_details", {"details": {}})
    if event.name == "music_follow_power":
        return Event("massage_power", event.values)
    return event


async def invoke(controller, action: str) -> None:
    assert isinstance(controller, SilkSnowController)
    await controller.light_effect(action)


async def refresh(controller) -> None:
    assert isinstance(controller, SilkSnowController)
    await controller.refresh_alarms()


class SilkSnowController(CasperBaseController):
    """Keep the app's catalog, physical session, and live permissions separate."""

    profiles = PROFILES
    action_catalog = ACTIONS

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        if product not in PROFILES:
            raise invalid("silksnow_product")
        super().__init__(coordinator, product=product)
        self._link: Link | None = None
        self._operation: ContextVar[Operation | None] = ContextVar(
            "silksnow_operation", default=None
        )
        self._receive = Receive()

    @property
    def supports_casper_base_controls(self) -> bool:
        return False

    @property
    def actions(self) -> dict[str, tuple[int, int | None]]:
        return {
            self.action_catalog[i][0]: self.action_catalog[i][1:]
            for group in (self.product[1], self.product[2], self.product[3], self.product[5])
            for i in group
            if self.action_catalog[i][0] not in EXCLUDED_ACTIONS
        }

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
        ):
            raise BedNotConnectedError()
        return link

    @contextmanager
    def _transaction(self) -> Iterator[Operation]:
        existing = self._operation.get()
        if existing is not None:
            self._live(existing.link)
            yield existing
            return
        operation = Operation(self._live())
        token = self._operation.set(operation)
        try:
            yield operation
        finally:
            self._operation.reset(token)

    async def _send(self, packet: bytes, *, cleanup: bool = False) -> None:
        operation = self._operation.get()
        link = self._live(operation.link if operation else None)
        await asyncio.sleep(0.1)
        self._live(link)

        def attempted() -> None:
            self._live(link)
            if operation is not None and operation.side is not None and not cleanup:
                operation.attempted.add(operation.side)

        await self._write_gatt_with_retry(
            link.write.uuid,
            packet,
            response="write-without-response" not in link.write.properties,
            characteristic=link.write,
            expected_client=link.client,
            before_write=attempted,
            settle_write=True,
            cancel_event=asyncio.Event() if cleanup else self._coordinator.cancel_command,
        )

    async def _opcode(self, opcode: int, *, cleanup: bool = False) -> None:
        operation = self._operation.get()
        for side in self._sides():
            if operation is not None:
                operation.side = side
            await self._send(codec.function(opcode, side, single=self._single), cleanup=cleanup)

    async def _release(self, operation: Operation) -> None:
        async def release() -> None:
            for side in sorted(operation.attempted):
                if (
                    self._link is not operation.link
                    or self.client is not operation.link.client
                    or not operation.link.client.is_connected
                ):
                    return
                await self._send(
                    codec.function(codec.STOP, side, single=operation.link.single), cleanup=True
                )

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None:
            raise BedNotConnectedError()
        write = notify = None
        single = False
        # Matching selects the first writer. Every service separately overwrites encoding.
        for service in client.services:
            match = GATT.get(service.uuid.lower())
            single = match[1] if match else False
            for characteristic in service.characteristics:
                if (
                    write is None
                    and match
                    and characteristic.uuid.lower() == match[0]
                    and "write" in characteristic.properties
                ):
                    write = characteristic
                if notify is None and "notify" in characteristic.properties:
                    notify = characteristic
        if write is None:
            raise invalid("silksnow_gatt")
        link = Link(client, write, notify, single)
        self._link = link
        self._write_char, self._notify_char, self._single = write, notify, single
        self._write_with_response = "write-without-response" not in write.properties
        self.events.clear()
        self.alarms.clear()
        self._receive = Receive()
        if notify is not None:

            def receive(sender, data):
                if self._link is link and self.client is client and client.is_connected:
                    self._on_notification(sender, data)

            await client.start_notify(notify, receive)
        with self._transaction():
            for action, code in (
                ("deviceFunctionItemExitLimit", 0),
                ("deviceFunctionItemCheckClock", 1),
                ("deviceFunctionItemCheckLight", 1),
            ):
                await self._send(codec.function(code, action=action, single=single))
            if self.product[10]:
                await self._send(codec.calendar(dt_util.now()))
        self._publish()

    def on_disconnect(self) -> None:
        self._link = None
        super().on_disconnect()
        self.events.clear()
        self.alarms.clear()
        self._receive = Receive()
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None), UNDER_BED_LIGHTS_RGB(None), LIGHT_TIMER_OPTION(None)
        )
        self._publish()

    async def stop_notify(self) -> None:
        link = self._link
        try:
            if (
                link is not None
                and self.client is link.client
                and link.client.is_connected
                and link.notify is not None
            ):
                await link.client.stop_notify(link.notify)
        finally:
            if self._link is link:
                self.on_disconnect()

    @property
    def controller_state_sensor_specs(self):
        return tuple(
            replace(
                spec,
                key="silksnow",
                translation_key="silksnow",
                attribute_keys=(),
            )
            for spec in super().controller_state_sensor_specs
        )

    @property
    def protocol_diagnostics(self):
        return {
            "product": self.product[0],
            "events": dict(self.events),
            "alarms": list(self.alarms),
        }

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            CASPER_BASE_MODEL(self.product[0]),
            CASPER_BASE_EVENTS(dict(self.events)),
            CASPER_BASE_ALARMS(list(self.alarms)),
        )

    def _decode_notification(self, packet: bytes) -> Event | None:
        return decode(packet)

    def _consume(self, event: Event) -> None:
        super()._consume(event)
        if event.name in ("rgb_power", "white_led_power"):
            self.forward_controller_state_update(UNDER_BED_LIGHTS_ON, event.values["value"] is True)
        elif event.name == "rgb_color":
            rgb = event.values["rgb"]
            if isinstance(rgb, list) and len(rgb) == 3 and all(type(x) is int for x in rgb):
                self.forward_controller_state_update(UNDER_BED_LIGHTS_RGB, (rgb[0], rgb[1], rgb[2]))
        elif event.name == "rgb_timer" and self.product[7]:
            option = next(
                (
                    name
                    for name, value in self._light_timers.items()
                    if value == event.values["minutes"]
                ),
                None,
            )
            self.forward_controller_state_update(LIGHT_TIMER_OPTION, option)

    async def async_perform_casper_base_action(
        self, action: str, *, save: bool = False, music_page: bool = False
    ) -> None:
        item = self.actions.get(action)
        if music_page or item is None or save and item[1] is None:
            raise invalid("silksnow_action")
        opcode = item[1] if save else item[0]
        assert opcode is not None
        moving = action.endswith(("Up", "Down"))
        with self._transaction() as operation:
            try:
                for _ in range(self._coordinator.motor_pulse_count if moving else 1):
                    if self._coordinator.cancel_command.is_set():
                        break
                    await self._opcode(opcode)
            finally:
                if moving:
                    await self._release(operation)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(name for name in self.actions if name in MASSAGE_TEXT)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid("silksnow_action")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        with self._transaction():
            long = duration_ms >= 3000
            cancelled = False
            try:
                await asyncio.wait_for(
                    self._coordinator.cancel_command.wait(), min(duration_ms, 3000) / 1000
                )
                long = False
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                long = False
                cancelled = True
            # Early tap-up/cancel sends the short control; after 3s, one null-long fallback.
            await self._opcode(0 if long else self.actions[control][0], cleanup=True)
            if cancelled:
                raise asyncio.CancelledError

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = tuple(
            replace(s, hold=ControllerHoldSpec("MassageModeAllOff"))
            if s.key == "casper_massagemodealloff"
            else s
            for s in super().controller_button_specs
            if not s.key.startswith("casper_music_page_")
        )
        effects = (
            (
                "cycling",
                "flowing_water",
                "multicolor",
                "breathe",
                "spectrum",
                "energy",
                "rhythm",
                "scroll",
            )
            if self.product[7]
            else ()
        )
        extra = [
            catalog_button(
                "silksnow_" + action,
                action.replace("_", " "),
                partial(invoke, action=action),
                kind=Kind.LIGHT,
            )
            for action in effects
        ]
        if self.product[10]:
            extra.append(
                catalog_button("silksnow_alarm_refresh", "Refresh alarms", refresh, diagnostic=True)
            )
        return (*specs, *(spec for spec in extra if spec is not None))

    async def stop_all(self) -> None:
        with self._transaction():
            await self._opcode(codec.STOP, cleanup=True)

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    @property
    def supports_lights(self) -> bool:
        return self.product[6]

    @property
    def supports_light_color_control(self) -> bool:
        return self.supports_lights

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return True

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.product[7]

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self.product[7]

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        # A first white-light turn-on chooses white; it does not claim received color or power.
        return (255, 255, 255) if self.supports_lights and not self.product[7] else None

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_lights

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int] | None:
        return self._coordinator.controller_state.get(UNDER_BED_LIGHTS_RGB)

    def _light_permission(self) -> None:
        self._live()
        self._global_control()
        if not self.supports_lights or "light_available" not in self.events:
            raise invalid("silksnow_light")

    async def lights_on(self) -> None:
        self._light_permission()
        if not self.product[7]:
            raise invalid("silksnow_action")
        with self._transaction():
            await self._send(codec.record(4, 4, 1, (0, 1)))

    async def lights_off(self) -> None:
        self._light_permission()
        with self._transaction():
            await self._send(
                codec.record(4, 4, 1, (0, 0))
                if self.product[7]
                else codec.function(0x75, single=self._single)
            )

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        self._light_permission()
        if any(type(x) is not int or not 0 <= x <= 255 for x in rgb_color):
            raise invalid("silksnow_action")
        with (
            self._transaction() as operation,
            self.sent_state(
                UNDER_BED_LIGHTS_RGB(rgb_color),
                is_current=lambda: (
                    self._link is operation.link
                    and self.client is operation.link.client
                    and operation.link.client.is_connected
                    and self._coordinator.controller is self
                ),
            ),
        ):
            await self._send(
                codec.record(4, 1, 1, (0, *rgb_color)) if self.product[7] else codec.rgb(*rgb_color)
            )

    @property
    def supports_light_timer(self) -> bool:
        return self.supports_lights

    @property
    def _light_timers(self) -> dict[str, int]:
        values = (
            RGB_TIMERS
            if self.product[7]
            else (
                300,
                450,
                600,
                750,
                900,
                1080,
                1260,
                1440,
                1620,
                1800,
                7200,
                12600,
                18000,
                23400,
                28800,
            )
        )
        return {
            **{f"{value if self.product[7] else value / 60:g} min": value for value in values},
            **({} if self.product[7] else {"Always on": 0}),
        }

    @property
    def light_timer_options(self) -> list[str]:
        return list(self._light_timers)

    async def set_light_timer(self, timer_option: str) -> None:
        self._light_permission()
        if timer_option not in self.light_timer_options:
            raise invalid("silksnow_action")
        value = self._light_timers[timer_option]
        with (
            self._transaction() as operation,
            self.sent_state(
                LIGHT_TIMER_OPTION(timer_option),
                is_current=lambda: (
                    self._link is operation.link
                    and self.client is operation.link.client
                    and operation.link.client.is_connected
                    and self._coordinator.controller is self
                ),
            ),
        ):
            if self.product[7]:
                await self._send(codec.record(4, 2, 1, (0, value >> 8, value & 255)))
            else:
                await asyncio.sleep(0.2)
                seconds = value or 65535
                await self._send(codec.light_timer(seconds >> 8, seconds & 255))

    async def light_effect(self, effect: str) -> None:
        self._light_permission()
        if not self.product[7]:
            raise invalid("silksnow_action")
        modes = {
            "cycling": (1, 3),
            "flowing_water": (1, 5),
            "multicolor": (1, 2),
            "spectrum": (2, 1),
            "energy": (2, 2),
            "rhythm": (2, 3),
            "scroll": (2, 4),
        }
        if effect != "breathe" and effect not in modes:
            raise invalid("silksnow_action")
        with self._transaction():
            await self._send(
                codec.record(4, 6, 1, (0,))
                if effect == "breathe"
                else codec.record(4, 5, 1, (0, *modes[effect]))
            )

    def _global_control(self) -> None:
        if self.command_side in ("left", "right"):
            raise invalid("silksnow_global_control")

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if self.command_side in ("left", "right"):
            return None
        # G1 leaves wake-position list selection unproved. Cancellation is proven independently.
        return AlarmCapability(
            weekdays=self.product[10], slots=7 if self.product[10] else 1, live_check=True
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self._global_control()
        if alarm.enabled:
            raise invalid("silksnow_alarm_selection")

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        self._live()
        if "clock_available" not in self.events:
            raise invalid("alarm_refresh_needed")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        # Repeat preflight on the dispatch link, including after a sequential reconnect.
        await self.check_alarm(alarm)
        with self._transaction():
            packets = (
                (codec.record(5, 2, 1, (alarm.slot,)),)
                if self.product[10]
                else codec.countdown(0, 0)
            )
            for packet in packets:
                await self._send(packet)

    async def refresh_alarms(self) -> None:
        self._live()
        self._global_control()
        if not self.product[10] or "clock_available" not in self.events:
            raise invalid("alarm_refresh_needed")
        with self._transaction():
            self.alarms.clear()
            self._publish()
            await self._send(codec.record(5, 1, 0, (0,)))

    @property
    def supports_clock_sync(self) -> bool:
        return self.product[10]

    def validate_clock_sync(self) -> None:
        self._global_control()
        if not self.supports_clock_sync:
            raise invalid("silksnow_action")

    async def sync_clock(self) -> None:
        self.validate_clock_sync()
        with self._transaction():
            await self._send(codec.calendar(dt_util.now()))


async def build_controller(ctx: BuildContext) -> SilkSnowController:
    return SilkSnowController(ctx.coordinator, product=ctx.variant or "")
