"""Ormatek's app session over the proven Keeson word carriers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmError, AlarmRequest
from ...app_session import app_session
from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_UTILITY
from ...codec import keeson
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...profiles import ormatek as app
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..catalog_buttons import massage_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .controller import KeesonController, _wait_unless_cancelled
from .ormatek_state import Alarm, Massage, Parser

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MASSAGE: Final = StateKey[bool | None]("ormatek_massage")
HEAD: Final = StateKey[int | None]("ormatek_head_massage")
FOOT: Final = StateKey[int | None]("ormatek_foot_massage")
WAVE: Final = StateKey[int | None]("ormatek_massage_wave")
ALARM: Final = StateKey[bool | None]("ormatek_alarm_enabled")
TIME: Final = StateKey[str | None]("ormatek_alarm_time")
_KEYS: Final = (MASSAGE, HEAD, FOOT, WAVE, ALARM, TIME)
NUS: Final = keeson.TRANSPORTS["ksbt"]
CONTROLS: Final = {
    "head_up": "headUp",
    "head_down": "headDown",
    "feet_up": "footUp",
    "feet_down": "footDown",
    "both_up": "hfUp",
    "both_down": "hfDown",
}


@dataclass
class Owner:
    token: object | None = None


@dataclass(frozen=True)
class Link:
    client: BleakClient
    writer: BleakGATTCharacteristic
    reader: BleakGATTCharacteristic
    token: object
    write_service: str
    read_service: str


class OrmatekController(KeesonController):
    """Explicit New/Lite layout, independent name catalog and discovered GATT roles."""

    read_positions = BedController.read_positions

    def __init__(
        self, coordinator: AdjustableBedCoordinator, wire: str = "okin15", layout: str = "new"
    ) -> None:
        if wire not in app.PROFILES or layout not in app.LAYOUTS:
            raise ValueError("Choose the Ormatek bed model and remote")
        super().__init__(coordinator, char_uuid=keeson.JALON_WRITE)
        self.wire, self.layout = wire, layout
        profile = app.PROFILES[wire]
        self.profile = replace(
            profile,
            presets={
                **profile.presets,
                **({"lounge": app.WORDS["memoryLounge"]} if layout == "new" else {}),
            },
            memory={1: app.WORDS["memory1M5"]} if layout == "new" else {},
            memory_slots=int(layout == "new"),
        )
        self._owner = app_session(coordinator.hass, coordinator.address, "ormatek", Owner)
        self._link: Link | None = None
        self._parser = Parser(wire)
        self._timer: int | None = None
        self._massage_received = asyncio.Event()
        self._raw_state: Massage | Alarm | None = None
        self._alarm_time: str | None = None
        self._notifying = False

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
    def supports_massage(self) -> bool:
        return self.layout == "new"

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def control_characteristic_uuid(self) -> str:
        return str(self._link.writer.uuid) if self._link else keeson.JALON_WRITE

    def _live(self, captured: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or captured is not None
            and link is not captured
            or self._owner.token is not link.token
            or self.client is not link.client
            or not link.client.is_connected
            or not self._notifying
        ):
            raise ConnectionError("Ormatek session has ended")
        for service_uuid, characteristic in (
            (link.write_service, link.writer),
            (link.read_service, link.reader),
        ):
            service = link.client.services.get_service(service_uuid)
            if (
                service is None
                or service.get_characteristic(characteristic.uuid) is not characteristic
            ):
                raise ConnectionError("Ormatek Bluetooth roles have changed")
        return link

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._live()

    def validate_command(self) -> None:
        self._live()

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Ormatek is disconnected")
        # The last supported WRITE service chooses a complete tuple, independently of wire.
        selected = None
        for service in client.services:
            uuid = str(service.uuid).lower()
            if uuid in (keeson.JALON_WRITE_SERVICE, NUS.service_uuid):
                selected = uuid
        if selected is None:
            raise ConnectionError("Ormatek requires a supported Bluetooth service")
        write_service = client.services.get_service(selected)
        read_service = client.services.get_service(
            keeson.JALON_NOTIFY_SERVICE
            if selected == keeson.JALON_WRITE_SERVICE
            else NUS.service_uuid
        )
        writer = (
            write_service.get_characteristic(
                keeson.JALON_WRITE if selected == keeson.JALON_WRITE_SERVICE else NUS.write_uuid
            )
            if write_service
            else None
        )
        reader = (
            read_service.get_characteristic(
                keeson.JALON_NOTIFY if selected == keeson.JALON_WRITE_SERVICE else NUS.notify_uuid
            )
            if read_service
            else None
        )
        if (
            writer is None
            or reader is None
            or "write-without-response" not in writer.properties
            or not {"notify", "indicate"}.intersection(reader.properties)
        ):
            raise ConnectionError("Ormatek requires writable and notification characteristics")
        assert read_service is not None
        token = object()
        self._owner.token = token
        self._link = Link(client, writer, reader, token, selected, str(read_service.uuid))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is None:
            await self.async_discover_capabilities()
        link = self._link
        assert link is not None
        await link.client.start_notify(
            link.reader, lambda _sender, data: self._receive(link, bytes(data))
        )
        if self._link is link and self.client is link.client and self._owner.token is link.token:
            self._notifying = True

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected and self._owner.token is None:
            await link.client.stop_notify(link.reader)

    def on_disconnect(self) -> None:
        publish = self._link is not None and self._owner.token is self._link.token
        if publish:
            self._owner.token = None
        self._link, self._notifying = None, False
        self._parser, self._timer, self._raw_state, self._alarm_time = (
            Parser(self.wire),
            None,
            None,
            None,
        )
        self._massage_received.set()
        if publish:
            for key in _KEYS:
                self.forward_controller_state_updates(key(None))

    def _receive(self, link: Link, packet: bytes) -> None:
        try:
            self._live(link)
        except ConnectionError:
            return
        self.forward_raw_notification(str(link.reader.uuid), packet)
        try:
            result = self._parser.feed(packet)
        except IndexError:
            return
        self._raw_state = result or self._raw_state
        if isinstance(result, Massage):
            self._timer = result.timer
            self._massage_received.set()
            if self.supports_massage:
                self.forward_controller_state_updates(
                    MASSAGE(result.timer > 0),
                    HEAD(result.head if 0 <= result.head <= 3 else None),
                    FOOT(result.foot if 0 <= result.foot <= 3 else None),
                    WAVE(result.wave if 0 <= result.wave <= 4 else None),
                )
        elif isinstance(result, Alarm) and result.slot == 1:
            if result.enabled and 0 <= result.hour <= 23 and 0 <= result.minute <= 59:
                self._alarm_time = f"{result.hour:02}:{result.minute:02}"
            self.forward_controller_state_updates(ALARM(result.enabled), TIME(self._alarm_time))

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "wire": self.wire,
            "layout": self.layout,
            "massage_timer": self._timer,
            "notification": repr(self._raw_state),
        }

    async def _send(self, link: Link, frame: bytes, event: asyncio.Event) -> None:
        self._live(link)

        def guard() -> None:
            self._live(link)

        await self._write_gatt_with_retry(
            str(link.writer.uuid),
            frame,
            response=False,
            cancel_event=event,
            characteristic=link.writer,
            expected_client=link.client,
            before_write=guard,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = app.HOLD_INTERVAL_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = self._coordinator.cancel_command if cancel_event is None else cancel_event
        for index in range(repeat_count):
            if event.is_set():
                return
            if index:
                await _wait_unless_cancelled(event, repeat_delay_ms / 1000)
            await self._send(link, command, event)

    async def _finish(
        self,
        link: Link,
        delay: float,
        query_at: float | None = None,
        *,
        release_at: float | None = None,
    ) -> None:
        edge = asyncio.get_running_loop().time() if release_at is None else release_at

        async def cleanup() -> None:
            now = asyncio.get_running_loop().time
            stop_at = edge + delay
            sequence = [
                (stop_at, app.normal(self.wire, "stop")),
                (stop_at + app.STOP_INTERVAL_MS / 1000, app.normal(self.wire, "stop")),
            ]
            if query_at is not None:
                sequence.append((query_at, app.massage_query(self.wire)))
            failure: Exception | None = None
            for when, frame in sorted(sequence, key=lambda item: item[0]):
                await asyncio.sleep(max(0, when - now()))
                try:
                    self._live(link)
                except ConnectionError:
                    return
                try:
                    await self._send(link, frame, asyncio.Event())
                except Exception as error:
                    failure = failure or error
            if failure is not None:
                raise failure

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

    async def _run(
        self, action: str, duration_ms: int = 0, *, massage: bool = False, repeats: int = 1
    ) -> None:
        link, event = self._live(), self._coordinator.cancel_command
        now = asyncio.get_running_loop().time
        start = now()
        deadline, query_at = (
            start + duration_ms / 1000,
            start + (app.MASSAGE_UI_DELAY_MS + app.MASSAGE_HELPER_DELAY_MS) / 1000
            if massage
            else None,
        )
        frame = app.normal(self.wire, action)
        next_write, count = start, 0
        release_at = max(deadline, start + (repeats - 1) * app.HOLD_INTERVAL_MS / 1000)
        completed = False
        try:
            while not event.is_set():
                when = min(next_write, query_at) if query_at is not None else next_write
                if count and when >= deadline and count >= repeats:
                    await _wait_unless_cancelled(event, max(0, deadline - now()))
                    completed = not event.is_set()
                    break
                await _wait_unless_cancelled(event, max(0, when - now()))
                if event.is_set():
                    break
                if count >= repeats and now() >= deadline:
                    completed = True
                    break
                if query_at is not None and query_at <= next_write:
                    await self._send(link, app.massage_query(self.wire), event)
                    query_at = None
                else:
                    await self._send(link, frame, event)
                    count += 1
                    next_write += app.HOLD_INTERVAL_MS / 1000
                    if count >= repeats:
                        # A slow write consumes ticks; never replay them as a burst.
                        while next_write < now():
                            next_write += app.HOLD_INTERVAL_MS / 1000
        finally:
            await self._finish(
                link,
                0 if massage else app.RELEASE_DELAY_MS / 1000,
                query_at,
                release_at=release_at if completed else None,
            )

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
            return
        action = {"head": ("headUp", "headDown"), "feet": ("footUp", "footDown")}.get(motor)
        if action is None:
            raise NotImplementedError("Ormatek supports head and feet movement")
        await self._run(action[0 if direction else 1], self.leased_hold_ms(1000))

    async def stop_all(self) -> None:
        await self._finish(self._live(), 0)

    async def _write_single_shot(self, command: bytes) -> None:
        action = next(key for key in app.WORDS if app.normal(self.wire, key) == command)
        await self._run(action, 0 if action != "memory1M5" else 1000)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *CONTROLS,
            *(
                ("memory_1", "light_toggle", "head_massage", "foot_massage")
                if self.layout == "new"
                else ()
            ),
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        return (
            ControllerHoldSpec("memory_1")
            if key == "preset_memory_1" and self.layout == "new"
            else None
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or isinstance(duration_ms, bool)
            or not 100 <= duration_ms <= 30000
        ):
            raise ValueError("Choose a movement and a duration from 100 to 30000 milliseconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = {
            **CONTROLS,
            "memory_1": "memory1M5",
            "light_toggle": "lightSwitch",
            "head_massage": "strengthHeadUp",
            "foot_massage": "strengthFootUp",
        }[control]
        await self._run(
            action,
            self.leased_hold_ms(duration_ms),
            massage=control in ("head_massage", "foot_massage"),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        def spec(key: str, label: str, up: str, down: str) -> MotorControlSpec:
            return MotorControlSpec(
                key,
                label,
                lambda c: selected(c).hold_control(up, 1000),
                lambda c: selected(c).hold_control(down, 1000),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec(up, down, press_is_native=True, stop_scope="side"),
            )

        return (
            spec("head", "head", "head_up", "head_down"),
            spec("feet", "feet", "feet_up", "feet_down"),
            spec("both", "ormatek_both", "both_up", "both_down"),
        )

    async def _step(self, word: int) -> None:
        raise NotImplementedError("Use this model's declared massage controls")

    async def _resolve_massage_timer(self) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        self._massage_received.clear()
        await self._send(link, app.massage_query(self.wire), cancel)
        received = asyncio.create_task(self._massage_received.wait())
        cancelled = asyncio.create_task(cancel.wait())
        try:
            # HA response budget, not a firmware timing or acknowledgement claim.
            await asyncio.wait(
                (received, cancelled), timeout=2, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            received.cancel()
            cancelled.cancel()
            await asyncio.gather(received, cancelled, return_exceptions=True)
        if cancel.is_set():
            raise asyncio.CancelledError
        self._live(link)
        if self._timer is None:
            raise ValueError("Massage state is unavailable; try again")

    async def massage_action(self, action: str) -> None:
        if not self.supports_massage or action not in (
            "massageSwitch",
            "massageTimeSwitch",
            "massageWaveSwitch",
            "strengthHeadUp",
            "strengthFootUp",
        ):
            raise ValueError("This bed model has no requested massage control")
        if action in ("massageTimeSwitch", "massageWaveSwitch"):
            if self._timer is None:
                await self._resolve_massage_timer()
            if self._timer == 0:
                action = "massageSwitch"
        await self._run(
            action,
            200 if action.startswith("strength") else 0,
            massage=True,
            repeats=2 if action == "massageSwitch" else 1,
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if not self.supports_massage:
            return ()
        labels = {
            "massageSwitch": "Toggle massage",
            "massageTimeSwitch": "Cycle massage timer",
            "massageWaveSwitch": "Cycle massage wave",
            "strengthHeadUp": "Cycle head massage strength",
            "strengthFootUp": "Cycle foot massage strength",
        }
        return (
            ControllerButtonSpec(
                "ormatek_light",
                "Toggle light",
                lambda c: selected(c)._run("lightSwitch", 100),
                translation_key="ormatek_light",
                card=CARD_LIGHTING,
                hold=ControllerHoldSpec("light_toggle"),
            ),
            *(
                massage_button(
                    f"ormatek_{action}",
                    label,
                    lambda c, action=action: selected(c).massage_action(action),
                    hold=ControllerHoldSpec(
                        "head_massage" if action == "strengthHeadUp" else "foot_massage"
                    )
                    if action in ("strengthHeadUp", "strengthFootUp")
                    else None,
                )
                for action, label in labels.items()
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "ormatek_alarm_time",
                "ormatek_alarm_time",
                TIME,
                "mdi:alarm",
                attribute_keys=(ALARM,),
                card=CARD_UTILITY,
                entity_registry_enabled_default=True,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            (
                ControllerStateBinarySensorSpec(
                    "ormatek_massage",
                    "ormatek_massage",
                    MASSAGE,
                    "mdi:vibrate",
                    attribute_keys=(HEAD, FOOT, WAVE),
                    entity_registry_enabled_default=True,
                    card=CARD_MASSAGE,
                ),
            )
            if self.supports_massage
            else ()
        )

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=app.WAKE_CHOICES[self.layout],
            cancel_running=True,
            resource=None,
            live_check=True,
            requires_wake_action=self.layout == "lite",
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.wake_action not in app.WAKE_CHOICES[self.layout]:
            raise AlarmError(
                "alarm_wake_action_not_supported",
                "Choose an available alarm wake action",
                device_name=self._coordinator.name,
                wake_action=alarm.wake_action,
                wake_actions=", ".join(app.WAKE_CHOICES[self.layout]),
            )
        if alarm.weekdays or alarm.slot != 1:
            raise AlarmError(
                "alarm_option_not_supported",
                "This bed supports one daily alarm",
                device_name=self._coordinator.name,
                option="weekdays" if alarm.weekdays else "slot",
            )
        for option, value, maximum in (("hour", alarm.hour, 23), ("minute", alarm.minute, 59)):
            if not 0 <= value <= maximum:
                raise AlarmError(
                    "alarm_value_out_of_range",
                    "Choose a valid alarm time",
                    device_name=self._coordinator.name,
                    option=option,
                    min=0,
                    max=maximum,
                )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self._live()

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, event = self._live(), self._coordinator.cancel_command
        now = asyncio.get_running_loop().time
        started = now()
        await self._send(
            link,
            app.alarm(
                self.wire,
                enabled=alarm.enabled,
                hour=alarm.hour,
                minute=alarm.minute,
                wake=alarm.wake_action,
            ),
            event,
        )
        for index in range(3 if self.wire == "okin15" else 1):
            when = (
                started + (1 if self.wire == "okin24" else index) * app.ALARM_QUERY_DELAY_MS / 1000
            )
            await _wait_unless_cancelled(event, max(0, when - now()))
            for frame in app.alarm_queries(self.wire, after_set=True):
                await self._send(link, frame, event)

    async def query_alarm(self) -> None:
        link, event = self._live(), self._coordinator.cancel_command
        for frame in app.alarm_queries(self.wire):
            await self._send(link, frame, event)

    async def sync_clock(self) -> None:
        await self.write_command(app.clock(self.wire, dt_util.now()))

    async def async_after_connect(self, session: ControllerSession) -> None:
        link, event = self._live(), self._coordinator.cancel_command
        if session.is_current():
            await self._send(link, app.clock(self.wire, dt_util.now()), event)
            # Opening the alarm page sends these same queries after clock sync.
            for frame in app.alarm_queries(self.wire):
                if not session.is_current():
                    return
                await self._send(link, frame, event)


def selected(controller: BedController) -> OrmatekController:
    return require_controller(controller, OrmatekController)


async def build_controller(ctx: BuildContext) -> OrmatekController:
    wire = ctx.variant
    if not wire or wire == "auto":
        from ...const import CONF_BLE_DEVICE_NAME

        wire = app.match_name(ctx.live_device_name or str(ctx.data.get(CONF_BLE_DEVICE_NAME, "")))
        if wire is None:
            raise ValueError("Select the Ormatek remote explicitly for an unknown Bluetooth name")
    layout = str(ctx.data.get(CONF_PRODUCT_TYPE, "new"))
    return OrmatekController(ctx.coordinator, wire if wire != "auto" else "okin15", layout)
