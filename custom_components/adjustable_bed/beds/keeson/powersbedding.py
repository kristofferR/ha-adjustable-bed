"""PowersBedding's three packet routes, bound to one current physical link."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_PRESET_SAVE, CARD_UTILITY
from ...codec import keeson as codec
from ...codec import okin_nframe
from ...command_scheduler import Delivery, current_command_context, delivered, note_frame_skipped
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import powersbedding as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from ..cancellation import cancellable, settled
from ..catalog_buttons import massage_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

LEVEL: Final = {z: StateKey[int | None](f"powersbedding_{z}") for z in app.LEVELS}
MASSAGE_ON: Final = StateKey[bool | None]("powersbedding_massage")
TIMER: Final = StateKey[str | None]("powersbedding_timer")
ALARM_ENABLED: Final = StateKey[bool | None]("powersbedding_alarm_enabled")
ALARM: Final = StateKey[str | None]("powersbedding_alarm")
WAKE: Final = StateKey[str | None]("powersbedding_wake")


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    route: str


class PowersBeddingController(KeesonController):
    """Share Keeson framing and generic routes, keep all app choices local."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, variant="base", char_uuid=codec.JALON_WRITE)
        snapshot = coordinator.entry.data.get("capabilities", {}).get("powersbedding", {})
        route = snapshot.get("route", "p1")
        self.profile = app.PROFILES[route if route in app.PROFILES else "p1"]
        self._link: Link | None = None
        self._session: object | None = None
        self._address = coordinator.address.upper()
        self._subscription: object | None = None
        self._levels = dict.fromkeys(app.LEVELS, 1)
        self._timer_level = -1
        self._last_preset: int | None = None
        self._alarm: app.Alarm | None = None
        self._massage: app.Massage | None = None
        self._pending_alarm_stop = False
        self._alarm_task: asyncio.Task[None] | None = None
        self._wire_lock = asyncio.Lock()
        self._alarm_received = asyncio.Event()

    def capability_snapshot(self) -> dict[str, object]:
        return {"route": self.profile.key.removeprefix("powersbedding_")}

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True)

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
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_timer(self) -> bool:
        return self.profile is app.PROFILES["p1"]

    @property
    def massage_timer_is_assumed(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        return self._live_route() != "p1" and super().supports_massage_off_control

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._live_route() != "p1" and super().supports_massage_toggle_control

    @property
    def supports_massage_intensity_control(self) -> bool:
        # The app exposes separate zone sliders, rather than a combined level.
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile is app.PROFILES["p1"]

    @property
    def supports_light_toggle_control(self) -> bool:
        return not self.supports_discrete_light_control

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.controller is self
            and self._coordinator.address.upper() == self._address
        )

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if link is None or expected is not None and link is not expected or not self._current(link):
            raise BedNotConnectedError()
        # A replaced GATT table is a new session even when the client is retained.
        for role in (link.write, link.notify):
            if link.client.services.get_characteristic(role.handle) is not role:
                raise BedNotConnectedError()
        if not {"write", "write-without-response"}.intersection(link.write.properties) or not {
            "notify",
            "indicate",
        }.intersection(link.notify.properties):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        epoch = self._session = object()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        name = (
            self._coordinator.ble_device_name
            or self._coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
            or self._coordinator.name
        ).lower()
        uart = name.startswith("smartbed")
        if not uart and not name.startswith("okin"):
            raise invalid("powersbedding_name")
        transport = codec.TRANSPORTS["ksbt" if uart else "base"]
        write_service = client.services.get_service(transport.service_uuid)
        notify_service = client.services.get_service(
            transport.service_uuid if uart else codec.JALON_NOTIFY_SERVICE
        )
        write = write_service.get_characteristic(transport.write_uuid) if write_service else None
        notify = (
            notify_service.get_characteristic(transport.notify_uuid) if notify_service else None
        )
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise BedNotConnectedError("bed_missing_service")
        route = "p3" if uart else "p1"
        manufacturer_service = client.services.get_service("0000180a-0000-1000-8000-00805f9b34fb")
        manufacturer = (
            manufacturer_service.get_characteristic("00002a29-0000-1000-8000-00805f9b34fb")
            if manufacturer_service
            else None
        )
        if manufacturer is not None:
            value = await client.read_gatt_char(manufacturer)
            if (
                self.client is not client
                or not client.is_connected
                or self._session is not epoch
                or self._coordinator.controller is not self
            ):
                raise BedNotConnectedError()
            if value is not None:
                route = "p2" if bytes(value) == b"BLE-4.0 Module" else "p1"
        self.profile = app.PROFILES[route]
        self._char_uuid, self._notify_char_uuid = write.uuid, notify.uuid
        self._link = Link(
            client, write, notify, "write-without-response" not in write.properties, route
        )

    async def async_validate_linked_readiness(self) -> None:
        self._live()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True  # The app-owned manufacturer query already selected this link's packet route.

    async def _send(self, link: Link, packet: bytes, event: asyncio.Event) -> None:
        async with self._wire_lock:
            written = False

            def sent() -> None:
                nonlocal written
                written = True

            def admit() -> None:
                self._live(link)

            await self._write_gatt_with_retry(
                link.write.uuid,
                packet,
                characteristic=link.write,
                expected_client=link.client,
                response=link.response,
                cancel_event=event,
                before_write=admit,
                on_write=sent,
                settle_write=True,
                write_timeout=5,
            )
            self._live(link)
            if event.is_set() or not written:
                raise asyncio.CancelledError

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            await self._send(link, command, event)
            if index + 1 < repeat_count:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), event)

    async def _word(self, word: int, link: Link | None = None) -> None:
        link = self._live(link)
        await self._send(link, app.normal(link.route, word), self._coordinator.cancel_command)

    async def _release(self, link: Link) -> None:
        async def release() -> None:
            # Cleanup is always sent on the captured link with independent cancellation.
            failure: Exception | None = None
            for index in range(2):
                if index:
                    await asyncio.sleep(0.1)
                try:
                    await self._send(link, app.normal(link.route, 0), asyncio.Event())
                except Exception as err:
                    failure = failure or err
            if failure is not None:
                raise failure
            context = current_command_context()
            if context is not None:
                context.cleanup_stop_sent = True

        await settled(release())

    async def stop_all(self) -> None:
        context = current_command_context()
        if context is not None and any(c.cleanup_stop_sent for c in context.preempted_contexts):
            return
        link = self._live()
        if link.route == "p1" and self._last_preset is not None:
            await self._send(link, app.normal(link.route, 0x01000000), asyncio.Event())
        else:
            await self._release(link)
        self._last_preset = None

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{axis}_{direction}" for axis in app.AXES for direction in ("up", "down"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 30000
        ):
            raise invalid("powersbedding_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        link, event = self._live(), self._coordinator.cancel_command
        self._last_preset = None
        end = asyncio.get_running_loop().time() + self.leased_hold_ms(duration_ms) / 1000
        try:
            while asyncio.get_running_loop().time() < end:
                await self._send(
                    link, app.normal(link.route, app.AXES[axis][direction == "down"]), event
                )
                await cancellable(
                    asyncio.sleep(min(0.1, max(0, end - asyncio.get_running_loop().time()))), event
                )
        finally:
            await self._release(link)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if direction is None:
            await self.stop_all()
        else:
            await self.hold_control(
                f"{motor}_{'up' if direction else 'down'}",
                self._coordinator.motor_pulse_count * 100,
            )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                lambda c, axis=axis: cast(PowersBeddingController, c)._move_motor(axis, True),
                lambda c, axis=axis: cast(PowersBeddingController, c)._move_motor(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis in app.AXES
        )

    async def _recall(self, word: int) -> None:
        link = self._live()
        last = self._last_preset
        stop = link.route == "p1" and last == word

        def remember(delivery: Delivery) -> None:
            if self._current(link) and delivery is not Delivery.NONE:
                self._last_preset = word if delivery is Delivery.SENT and not stop else None

        with delivered(remember):
            await self._word(0x01000000 if stop else word, link)

    async def preset_flat(self) -> None:
        await self._recall(self.profile.presets["flat"])

    async def preset_zero_g(self) -> None:
        await self._recall(self.profile.presets["zero_g"])

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._recall(self.profile.memory[memory_num])

    async def _program(self, word: int) -> None:
        link, event = self._live(), self._coordinator.cancel_command
        self._last_preset = None
        interval = 5 if link.route == "p1" else 0.1
        start = asyncio.get_running_loop().time()
        end = start + 6
        # Programming release only ends refresh; it never sends motor STOP.
        for index in range(2 if link.route == "p1" else 60):
            if asyncio.get_running_loop().time() >= end:
                break
            await self._send(link, app.normal(link.route, word), event)
            await cancellable(
                asyncio.sleep(
                    max(
                        0,
                        min(end, start + (index + 1) * interval)
                        - asyncio.get_running_loop().time(),
                    )
                ),
                event,
            )

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        word = (
            {1: 0x20000008, 2: 0x20000009}[memory_num]
            if self._live().route == "p1"
            else app.MEMORY[memory_num]
        )
        await self._program(word)

    async def program_zero_g(self) -> None:
        await self._program(0x20000001 if self._live().route == "p1" else app.PRESETS["zero_g"])

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    async def _light(self, enabled: bool) -> None:
        link = self._live()
        if link.route != "p1":
            raise invalid("powersbedding_control")
        with self.sent_state(UNDER_BED_LIGHTS_ON(enabled), is_current=lambda: self._current(link)):
            await self._word(0x31000000 + enabled, link)

    async def lights_toggle(self) -> None:
        if self._live().route == "p1":
            raise invalid("powersbedding_control")
        await self._word(0x20000)

    async def set_level(self, zone: str, value: int) -> None:
        link = self._live()
        if (
            link.route != "p1"
            or zone not in app.LEVELS
            or type(value) is not int
            or not 0 <= value <= 3
        ):
            raise invalid("powersbedding_control")

        def remember(delivery: Delivery) -> None:
            if self._current(link) and delivery is Delivery.SENT:
                self._levels[zone] = value

        with (
            self.sent_state(LEVEL[zone](value), is_current=lambda: self._current(link)),
            delivered(remember),
        ):
            await self._word(app.LEVELS[zone] + value, link)

    async def set_massage_timer(self, minutes: int) -> None:
        link = self._live()
        if link.route != "p1" or minutes not in (10, 20, 30):
            raise invalid("powersbedding_control")

        def remember(delivery: Delivery) -> None:
            if self._current(link) and delivery is Delivery.SENT:
                self._timer_level = minutes // 10

        with (
            self.sent_state(MASSAGE_TIMER_MINUTES(minutes), is_current=lambda: self._current(link)),
            delivered(remember),
        ):
            await self._word(0x10000030 + minutes // 10 - 1, link)

    async def massage_sequence(self, enabled: bool) -> None:
        link, event = self._live(), self._coordinator.cancel_command
        if link.route != "p1":
            raise invalid("powersbedding_control")
        needs_timer = enabled and self._timer_level <= 0
        remaining = 7 if needs_timer else 6

        def sent(delivery: Delivery) -> None:
            nonlocal remaining
            if delivery is not Delivery.NONE:
                remaining -= 1

        with self.sent_state(MASSAGE_ON(enabled), is_current=lambda: self._current(link)):
            try:
                if needs_timer:
                    with delivered(sent):
                        await self.set_massage_timer(10)
                timer_state = (
                    self.sent_state(
                        MASSAGE_TIMER_MINUTES(None), is_current=lambda: self._current(link)
                    )
                    if not enabled
                    else nullcontext()
                )
                with timer_state:
                    for index, zone in enumerate(("foot", "head", "wave")):
                        if enabled or index:
                            await cancellable(asyncio.sleep(0.1), event)
                        value = self._levels[zone] if enabled else 0
                        with self.sent_state(
                            LEVEL[zone](value), is_current=lambda: self._current(link)
                        ):
                            for _ in range(2):
                                with delivered(sent):
                                    await self._word(app.LEVELS[zone] + value, link)
            except BaseException:
                if remaining:
                    note_frame_skipped()
                raise

    async def massage_off(self) -> None:
        await self.massage_sequence(False)

    async def massage_step(self, action: str) -> None:
        link = self._live()
        if link.route == "p1":
            if action != "timer":
                raise invalid("powersbedding_control")
            level = (self._timer_level + 1) % 4

            def remember(delivery: Delivery) -> None:
                if self._current(link) and delivery is Delivery.SENT:
                    self._timer_level = level

            with delivered(remember):
                if self._timer_level + 1 >= 4:
                    await self.massage_off()
                else:
                    # Initial -1 -> 0 deliberately sends base-1.
                    with self.sent_state(
                        MASSAGE_TIMER_MINUTES(level * 10 if level else None),
                        is_current=lambda: self._current(link),
                    ):
                        await self._word(0x10000030 + level - 1, link)
            return
        if action not in app.STEPS:
            raise invalid("powersbedding_control")
        await self._word(app.STEPS[action], link)
        if link.route == "p3":
            await cancellable(asyncio.sleep(0.15), self._coordinator.cancel_command)
            await self._send(link, okin_nframe.request(0xB0), self._coordinator.cancel_command)

    async def massage_toggle(self) -> None:
        await self.massage_step("toggle")

    async def massage_head_up(self) -> None:
        await self.massage_step("head_up")

    async def massage_head_down(self) -> None:
        await self.massage_step("head_down")

    async def massage_foot_up(self) -> None:
        await self.massage_step("foot_up")

    async def massage_foot_down(self) -> None:
        await self.massage_step("foot_down")

    async def massage_mode_step(self) -> None:
        await self.massage_step("timer")

    async def massage_wave_next(self) -> None:
        await self.massage_step("wave")

    async def massage_intensity_up(self) -> None:
        raise invalid("powersbedding_control")

    async def massage_intensity_down(self) -> None:
        raise invalid("powersbedding_control")

    async def massage_head_toggle(self) -> None:
        raise invalid("powersbedding_control")

    async def massage_foot_toggle(self) -> None:
        raise invalid("powersbedding_control")

    async def massage_wave_previous(self) -> None:
        raise invalid("powersbedding_control")

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            weekdays=True,
            wake_actions=app.WAKE,
            massage=self.profile is app.PROFILES["p1"],
            cancel_running=True,
            resource=None,
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if (
            type(alarm.enabled) is not bool
            or type(alarm.hour) is not int
            or type(alarm.minute) is not int
            or not 0 <= alarm.hour <= 23
            or not 0 <= alarm.minute <= 59
            or alarm.wake_action not in app.WAKE
            or len(set(alarm.weekdays)) != len(alarm.weekdays)
            or any(type(d) is not int or not 0 <= d <= 6 for d in alarm.weekdays)
            or alarm.massage
            and self.profile is not app.PROFILES["p1"]
        ):
            raise invalid("powersbedding_alarm")

    async def sync_clock(self) -> None:
        link = self._live()
        await self._send(
            link, app.clock(link.route, dt_util.now()), self._coordinator.cancel_command
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, event = self._live(), self._coordinator.cancel_command
        now = dt_util.now()
        week = app.week_mask(
            tuple((day + 1) % 7 for day in alarm.weekdays), now, alarm.hour, alarm.minute
        )
        massage, mode = app.wake_mode(link.route, alarm.wake_action, alarm.massage)
        started = asyncio.get_running_loop().time()
        for _ in range(2):
            current = dt_util.now()
            packet = (
                app.alarm_fields(link.route, alarm.hour, alarm.minute, week, massage, mode, current)
                if alarm.enabled
                else app.cancel(link.route, current)
            )
            await self._send(link, packet, event)
        await cancellable(asyncio.sleep(0.1), event)
        await self.sync_clock()
        await cancellable(
            asyncio.sleep(max(0, started + 0.4 - asyncio.get_running_loop().time())), event
        )
        await self.query_alarm()

    async def query_alarm(self) -> None:
        link = self._live()
        packet = app.alarm_query(link.route)
        if packet is not None:
            self._pending_alarm_stop = True
            self._alarm_received.clear()
            try:
                await self._send(link, packet, self._coordinator.cancel_command)
                # HA bounds the read ownership window, so a delayed reply cannot
                # stop a later gesture. This is not an app response timeout.
                try:
                    async with asyncio.timeout(1):
                        await cancellable(
                            self._alarm_received.wait(), self._coordinator.cancel_command
                        )
                except TimeoutError:
                    pass
            finally:
                self._pending_alarm_stop = False
                if self._alarm_task is not None:
                    task, self._alarm_task = self._alarm_task, None
                    await settled(task_result(task))

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self._live()
        await session.async_start_notify()
        await self.sync_clock()
        await self.sync_clock()
        if link.route == "p3":
            await self._send(link, okin_nframe.request(0xB0), self._coordinator.cancel_command)
        self._live(link)
        session.persist_capability_snapshot()

    async def _reply_stop(self, link: Link) -> None:
        try:
            await self._send(link, app.normal(link.route, 0), asyncio.Event())
        except ConnectionError:
            pass

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscription is not None:
            return
        token = self._subscription = object()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._subscription is not token
                or not self._current(link)
                or sender.handle != link.notify.handle
            ):
                return
            try:
                self._live(link)
            except ConnectionError:
                return
            raw = bytes(data)
            self.forward_raw_notification(link.notify.uuid, raw)
            alarm_reply = app.is_alarm(link.route, raw)
            # P1 has no header and the app parses only while viewing its alarm tab.
            if alarm_reply:
                parsed = app.parse_alarm(link.route, raw, self._alarm)
                if parsed is not None:
                    self._alarm = parsed
                    valid = 0 <= parsed.hour <= 23 and 0 <= parsed.minute <= 59
                    wake = (
                        ", ".join(
                            label
                            for flag, label in (
                                (parsed.memory_a, "Memory A"),
                                (parsed.memory_b, "Memory B"),
                                (parsed.massage, "Massage"),
                            )
                            if flag
                        )
                        or "None"
                    )
                    self.forward_controller_state_updates(
                        ALARM(f"{parsed.hour:02}:{parsed.minute:02}" if valid else None),
                        ALARM_ENABLED(parsed.enabled),
                        WAKE(wake),
                    )
                # Only a requested alarm read owns the app's parser STOP side effect.
                if link.route != "p1" and self._pending_alarm_stop:
                    self._pending_alarm_stop = False
                    self._alarm_task = asyncio.create_task(self._reply_stop(link))
                    self._alarm_received.set()
                return
            parsed_massage = app.parse_massage(link.route, raw)
            if parsed_massage is not None:
                self._massage = parsed_massage
                active = parsed_massage.head > 0 or parsed_massage.foot > 0
                self.forward_controller_state_updates(
                    *(
                        LEVEL[z](max(0, min(4 if z == "wave" else 3, value)) if active else 0)
                        for z, value in (
                            ("head", parsed_massage.head),
                            ("foot", parsed_massage.foot),
                            ("wave", parsed_massage.wave),
                        )
                    ),
                    TIMER(
                        {0: "Off", 1: "10 min", 2: "20 min", 3: "30 min", 4: "Full"}.get(
                            parsed_massage.arc
                        )
                        if active
                        else "Off"
                    ),
                )

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
        except BaseException:
            if self._subscription is token:
                self._subscription = None
            raise

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscription is not None
        self._subscription = None
        self._pending_alarm_stop = False
        self._alarm = None
        self._massage = None
        self._clear_state()
        if self._alarm_task is not None:
            self._alarm_task.cancel()
            await asyncio.gather(self._alarm_task, return_exceptions=True)
            self._alarm_task = None
        if subscribed and link is not None and self._current(link):
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._session = None
        self._link = None
        self._subscription = None
        self._pending_alarm_stop = False
        self._last_preset = None
        self._alarm = None
        self._massage = None
        if self._alarm_task is not None:
            self._alarm_task.cancel()
        self._clear_state()

    def _clear_state(self) -> None:
        if self._coordinator.controller is not self:
            return
        self.forward_controller_state_updates(
            *(key(None) for key in LEVEL.values()),
            MASSAGE_ON(None),
            TIMER(None),
            ALARM(None),
            ALARM_ENABLED(None),
            WAKE(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_ON(None),
        )

    async def async_resume_session(self) -> None:
        self._live()
        await self.start_notify()

    @property
    def persisted_app_state(self):
        return dict(self._levels)

    def restore_persisted_app_state(self, state) -> None:
        if set(state) - set(app.LEVELS) or any(
            type(v) is not int or not 0 <= v <= 3 for v in state.values()
        ):
            raise invalid("powersbedding_control")
        self._levels.update(state)

    async def read_positions(self, motor_count: int = 2) -> None:
        """No motor-position or sensor feedback exists in this app."""

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.supports_massage_timer:
            return ()
        return tuple(
            ControllerNumberSpec(
                f"powersbedding_{zone}",
                f"massage_{zone}_intensity",
                LEVEL[zone],
                0,
                3,
                1,
                lambda c, value, zone=zone: cast(PowersBeddingController, c).set_level(
                    zone, int(value)
                ),
                card=CARD_MASSAGE,
                assumed_state=True,
            )
            for zone in app.LEVELS
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = [
            ControllerButtonSpec(
                "powersbedding_save_zero_g",
                "Save zero gravity",
                lambda c: cast(PowersBeddingController, c).program_zero_g(),
                translation_key="powersbedding_save_zero_g",
                requires_confirmation=True,
                card=CARD_PRESET_SAVE,
                scheduler_resource="*",
            )
        ]
        actions = ("timer",) if self.supports_massage_timer else tuple(app.STEPS)
        labels = {
            "toggle": "Toggle massage",
            "head_up": "Increase head massage",
            "head_down": "Decrease head massage",
            "foot_up": "Increase foot massage",
            "foot_down": "Decrease foot massage",
            "wave": "Next massage wave",
            "timer": "Cycle massage timer",
        }
        for action in actions:
            buttons.append(
                massage_button(
                    f"powersbedding_{action}",
                    labels[action],
                    lambda c, action=action: cast(PowersBeddingController, c).massage_step(action),
                    scheduler_resource="*",
                )
            )
        if self._live_route() != "p1":
            buttons.append(
                ControllerButtonSpec(
                    "powersbedding_query_alarm",
                    "Refresh bed alarm",
                    lambda c: cast(PowersBeddingController, c).query_alarm(),
                    translation_key="powersbedding_query_alarm",
                    diagnostic=True,
                    scheduler_resource="*",
                )
            )
        return tuple(buttons)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if self._live_route() != "p1":
            return ()
        return (
            ControllerSwitchSpec(
                "powersbedding_massage",
                "massage",
                lambda c, enabled: cast(PowersBeddingController, c).massage_sequence(enabled),
                state_key=MASSAGE_ON,
                assumed_state=True,
                card=CARD_MASSAGE,
            ),
        )

    def _live_route(self) -> str:
        return self.profile.key.removeprefix("powersbedding_")

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "powersbedding_alarm_enabled",
                "powersbedding_alarm_enabled",
                ALARM_ENABLED,
                "mdi:alarm",
                card=CARD_UTILITY,
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [
            ControllerStateSensorSpec(
                "powersbedding_alarm",
                "powersbedding_alarm",
                ALARM,
                "mdi:alarm",
                attribute_keys=(WAKE,),
                card=CARD_UTILITY,
                entity_registry_enabled_default=True,
                entity_category=None,
            )
        ]
        if not self.supports_massage_timer:
            specs.extend(
                ControllerStateSensorSpec(
                    f"powersbedding_{zone}_report",
                    f"powersbedding_{zone}_report",
                    LEVEL[zone],
                    "mdi:vibrate",
                    card=CARD_MASSAGE,
                    entity_registry_enabled_default=True,
                    entity_category=None,
                )
                for zone in app.LEVELS
            )
            specs.append(
                ControllerStateSensorSpec(
                    "powersbedding_timer",
                    "powersbedding_timer",
                    TIMER,
                    "mdi:timer-outline",
                    card=CARD_MASSAGE,
                    entity_registry_enabled_default=True,
                    entity_category=None,
                )
            )
        return tuple(specs)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "PowersBedding 1.1.0 (2)",
            "route": self._live_route(),
            "alarm_raw": repr(self._alarm),
            "massage_raw": repr(self._massage),
            "timer_selection": self._timer_level,
        }


async def task_result(task: asyncio.Task[None]) -> None:
    await task
