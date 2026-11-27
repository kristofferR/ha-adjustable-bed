"""Explicit Meisemobell routes, with session-bound GATT and alarm admission."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
)
from ...controller_state import StateUpdate
from ...errors import BedNotConnectedError, invalid
from ...profiles import meisemobell as app
from ...profiles.okin_nframe import OkinNFrameProfile
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..okin_nframe import OkinNFrameController
from . import state_keys as s

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


@dataclass(slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    listener: object | None = None
    ready: bool = False
    last: bytes = b""
    fragment_pending: bool = False


async def _pause(cancel: asyncio.Event, seconds: float) -> None:
    try:
        async with asyncio.timeout(seconds):
            await cancel.wait()
    except TimeoutError:
        pass


class MeisemobellController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
    def __init__(self, coordinator: AdjustableBedCoordinator, route: app.Route) -> None:
        super().__init__(coordinator)
        self.route: app.Route = route
        self.profile = app.PROFILES[route]
        self._link: _Link | None = None
        self._alarms: dict[int, app.Alarm] = {}
        self._reply = asyncio.Event()

    @property
    def control_characteristic_uuid(self) -> str:
        return app.TRANSPORTS[self.route].write

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    def _live(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _current(self, *, ready: bool = True) -> _Link:
        link = self._link
        if link is None or not self._live(link) or (ready and not link.ready):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        transport = app.TRANSPORTS[self.route]
        write = notify = None
        for service in client.services or ():
            for char in service.characteristics:
                # UUID canonicalization here is HA/Bleak transport handling, not
                # a claim about the app's unresolved String GDT normalization.
                if (
                    service.uuid.lower() == transport.service
                    and char.uuid.lower() == transport.write
                    and write is None
                ):
                    write = char
                if (
                    service.uuid.lower() == transport.notify_service
                    and char.uuid.lower() == transport.notify
                    and notify is None
                ):
                    notify = char
        if (
            write is None
            or notify is None
            or "write-without-response" not in write.properties
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise invalid("meisemobell_gatt")
        self._link = _Link(client, write, notify)

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._current()
        if not session.is_current():
            raise BedNotConnectedError()
        await self._write(link, app.clock(self.route, dt_util.now()), asyncio.Event(), track=False)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._current(ready=False)
        if link.listener is not None:
            return
        listener = object()
        link.listener = listener

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._live(link) and link.ready and link.listener is listener:
                self._receive(link, bytes(data))

        try:
            for attempt in range(2):
                try:
                    await link.client.start_notify(link.notify, received)
                    break
                except BleakError, TimeoutError:
                    if attempt:
                        raise
                    if not self._live(link):
                        raise BedNotConnectedError() from None
            if not self._live(link):
                raise BedNotConnectedError()
            link.ready = True
        except BaseException:
            link.listener = None
            raise

    async def stop_notify(self) -> None:
        link = self._link
        if link is None:
            return
        subscribed = link.listener is not None
        link.listener, link.ready = None, False
        if subscribed and self._live(link):
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._alarms.clear()
        self._reply.set()
        self.forward_controller_state_updates(
            s.ALARM_1(None), s.ALARM_2(None), s.MASSAGE_TIME(None)
        )

    async def _write(
        self, link: _Link, frame: bytes, cancel: asyncio.Event, *, track: bool = True
    ) -> None:
        def validate() -> None:
            if not self._live(link) or not link.ready:
                raise BedNotConnectedError()

        await settled(
            self._write_gatt_with_retry(
                link.write.uuid,
                frame,
                cancel_event=cancel,
                response=False,
                characteristic=link.write,
                expected_client=link.client,
                before_write=validate,
                track_command_write=track,
            )
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._current()
        cancel = cancel_event or self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(repeat_count):
            if index:
                await _pause(cancel, max(0, started + index * repeat_delay_ms / 1000 - loop.time()))
            if cancel.is_set():
                return
            await self._write(link, command, cancel)

    async def _release_link(self, link: _Link) -> None:
        cancel = asyncio.Event()
        error: Exception | None = None
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(2):
            if index:
                await asyncio.sleep(max(0, started + app.STOP_MS / 1000 - loop.time()))
            if not self._live(link):
                return
            try:
                await self._write(link, app.control(self.route, "stop"), cancel, track=False)
            except (BleakError, TimeoutError) as err:
                error = err
        if error:
            raise error
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    async def stop_all(self) -> None:
        if not CONTROLLER_GESTURE_RELEASE.get():
            await self._release_link(self._current())

    move_back_stop = move_head_stop = move_feet_stop = move_legs_stop = stop_all

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in self.profile.keys if key not in ("stop", "reset_memories"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("meisemobell_hold")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        link = self._current()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.leased_hold_ms(duration_ms) / 1000
        async with self.releasing(lambda: self._release_link(link)):
            while not cancel.is_set() and loop.time() < deadline:
                started = loop.time()
                await self._write(link, app.control(self.route, control), cancel)
                await _pause(
                    cancel, max(0, min(started + app.REFRESH_MS / 1000, deadline) - loop.time())
                )

    async def _move(self, action: str) -> None:
        await self.hold_control(
            action, min(60000, self._coordinator.motor_pulse_count * app.REFRESH_MS)
        )

    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    move_back_up = move_head_up
    move_back_down = move_head_down

    async def move_feet_up(self) -> None:
        await self._move("foot_up")

    async def move_feet_down(self) -> None:
        await self._move("foot_down")

    move_legs_up = move_feet_up
    move_legs_down = move_feet_down

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=lambda ctrl, a=action: require_controller(
                    ctrl, MeisemobellController
                )._move(f"{a}_up"),
                close_fn=lambda ctrl, a=action: require_controller(
                    ctrl, MeisemobellController
                )._move(f"{a}_down"),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{action}_up",
                    f"{action}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                ),
            )
            for axis, action in (("back", "head"), ("legs", "foot"))
        )

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    async def preset_flat(self) -> None:
        await self._move("flat")

    async def preset_zero_g(self) -> None:
        await self._move("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._move("anti_snore")

    async def preset_tv(self) -> None:
        await self._move("tv")

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return True

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._move(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.hold_control(f"memory_{memory_num}", app.SAVE_MS)

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    async def lights_toggle(self) -> None:
        await self._move("light")

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self.write_command(app.clock(self.route, dt_util.now()))

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=app.WAKE_ACTIONS,
            weekdays=True,
            slots=2,
            live_check=True,
            cancel_running=True,
            resource="*",
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.slot not in (1, 2) or (
            alarm.enabled and alarm.wake_action not in app.WAKE_ACTIONS
        ):
            raise invalid("meisemobell_alarm")

    def _assert_link(self, link: _Link) -> None:
        if self._current() is not link:
            raise BedNotConnectedError()

    async def _query(self, link: _Link, cancel: asyncio.Event, *, after_set: bool = False) -> None:
        started = asyncio.get_running_loop().time()
        for frame in app.queries(self.route):
            await self._write(link, frame, cancel)
        if self.route == "15_22_15a":
            await _pause(
                cancel,
                max(0, started + (0.35 if after_set else 0.3) - asyncio.get_running_loop().time()),
            )
            await self._write(link, app.queries(self.route)[0], cancel)

    async def refresh_alarms(self) -> None:
        await self._query(self._current(), self._coordinator.cancel_command)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link = self._current()
        if self.route != "15_22_15a" or len(self._alarms) == 2:
            return
        self._reply.clear()
        await self._query(link, self._coordinator.cancel_command)
        try:
            await asyncio.wait_for(self._reply.wait(), 2)
        except TimeoutError:
            pass
        self._assert_link(link)
        if len(self._alarms) != 2:
            raise invalid("meisemobell_alarm_not_reported")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link = self._current()
        await self.check_alarm(alarm)
        self._assert_link(link)
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        value = app.alarm_request(self.route, alarm)
        if self.route == "15_22_15a":
            records = {**self._alarms, alarm.slot: value}
            frame = app.alarm_pair(records[1], records[2])
        else:
            frame = app.alarm_slot(alarm.slot, value)
        await self._write_alarms(link, frame, cancel, {alarm.slot: value})
        self._assert_link(link)
        if cancel.is_set():
            return
        await _pause(cancel, 0.35 if self.route == "15_22_15a" else 0.1)
        await self._query(link, cancel, after_set=True)

    async def _write_alarms(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        values: dict[int, app.Alarm],
        *,
        previous: dict[int, app.Alarm | None] | None = None,
    ) -> None:
        if cancel.is_set():
            note_frame_skipped()
            return
        prior = (
            previous if previous is not None else {slot: self._alarms.get(slot) for slot in values}
        )

        def current(slot: int) -> bool:
            return self._live(link) and link.ready and self._alarms.get(slot) is prior[slot]

        def invalidate(result: Delivery) -> None:
            if result is not Delivery.NONE:
                for slot in values:
                    if current(slot):
                        self._alarms.pop(slot, None)
                        # Allow an identical query reply to restore raw authority.
                        link.last = b""

        with ExitStack() as finalizers:
            finalizers.enter_context(delivered(invalidate))
            for slot, value in values.items():
                finalizers.enter_context(
                    self.sent_state(
                        *self._alarm_updates(slot, value, "sent"),
                        is_current=lambda slot=slot: current(slot),
                    )
                )
            await self._write(link, frame, cancel)

    async def close_alarms(self) -> None:
        link = self._current()
        cancel = self._coordinator.cancel_command
        if self.route == "15_22_15a":
            await self._write_alarms(
                link,
                app.alarm_pair(app.Alarm(), app.Alarm()),
                cancel,
                {1: app.Alarm(), 2: app.Alarm()},
            )
        else:
            # The two writes share one mutation's readback checkpoint. A new
            # report for either slot takes precedence over its assumed result.
            previous = {slot: self._alarms.get(slot) for slot in (1, 2)}
            try:
                await self._write_alarms(
                    link,
                    app.alarm_slot(1, app.Alarm()),
                    cancel,
                    {1: app.Alarm()},
                    previous=previous,
                )
                await _pause(cancel, 0.1)
            except asyncio.CancelledError:
                # The second mandatory slot write has not been attempted.
                note_frame_skipped()
                raise
            await self._write_alarms(
                link, app.alarm_slot(2, app.Alarm()), cancel, {2: app.Alarm()}, previous=previous
            )
        self._assert_link(link)
        if cancel.is_set():
            return
        if self.route == "15_22_15a":
            await _pause(cancel, 0.35)
            await self._query(link, cancel, after_set=True)

    async def reset_memories(self) -> None:
        # The app streams this combined flat/ZG frame, then ends the refresh.
        # There is no reset-specific terminal STOP; cancellation still releases.
        link = self._current()
        try:
            await self.write_command(
                app.control(self.route, "reset_memories"), app.RESET_COPIES, app.RESET_MS
            )
            await _pause(self._coordinator.cancel_command, app.RESET_MS / 1000)
        except BaseException:
            await settled(self._release_link(link))
            raise
        if self._coordinator.cancel_command.is_set():
            await self._release_link(link)

    async def reset_settings(self) -> None:
        link = self._current()
        deadline = asyncio.get_running_loop().time() + 2
        await self.close_alarms()
        await _pause(
            self._coordinator.cancel_command, max(0, deadline - asyncio.get_running_loop().time())
        )
        self._assert_link(link)
        if not self._coordinator.cancel_command.is_set():
            await self.reset_memories()

    def _alarm_updates(self, slot: int, alarm: app.Alarm, source: str) -> tuple[StateUpdate, ...]:
        time, enabled, week, kind, origin = (
            (s.ALARM_1, s.ENABLED_1, s.WEEK_1, s.TYPE_1, s.SOURCE_1)
            if slot == 1
            else (s.ALARM_2, s.ENABLED_2, s.WEEK_2, s.TYPE_2, s.SOURCE_2)
        )
        return (
            time(f"{alarm.hour:02d}:{alarm.minute:02d}"),
            enabled(alarm.enabled),
            week(alarm.week),
            kind(alarm.kind),
            origin(source),
        )

    def _publish(self, slot: int, alarm: app.Alarm, source: str) -> None:
        self.forward_controller_state_updates(*self._alarm_updates(slot, alarm, source))

    def _receive(self, link: _Link, data: bytes) -> None:
        self.forward_raw_notification(link.notify.uuid, data)
        if len(data) < 3:
            return
        # D2: discard the ambiguous pair, rather than inventing assembly behavior.
        pending, link.fragment_pending = link.fragment_pending, len(data) == 20
        if pending or link.fragment_pending or data == link.last:
            return
        link.last = data
        for slot, alarm in app.parse_alarms(self.route, data):
            self._alarms[slot] = alarm
            self._publish(slot, alarm, "reported")
        if len(self._alarms) == 2:
            self._reply.set()
        if (massage := app.parse_massage(self.route, data)) is not None:
            self.forward_controller_state_updates(
                s.MASSAGE_TIME(massage[0]),
                s.MASSAGE_WAVE(massage[1]),
                s.MASSAGE_HEAD(massage[2]),
                s.MASSAGE_FOOT(massage[3]),
            )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "meisemobell_alarm_1",
                "meisemobell_alarm_1",
                s.ALARM_1,
                icon="mdi:alarm",
                attribute_keys=(s.ENABLED_1, s.WEEK_1, s.TYPE_1, s.SOURCE_1),
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
            ControllerStateSensorSpec(
                "meisemobell_alarm_2",
                "meisemobell_alarm_2",
                s.ALARM_2,
                icon="mdi:alarm",
                attribute_keys=(s.ENABLED_2, s.WEEK_2, s.TYPE_2, s.SOURCE_2),
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
            ControllerStateSensorSpec(
                "meisemobell_massage_time",
                "meisemobell_massage_time",
                s.MASSAGE_TIME,
                icon="mdi:timer",
                attribute_keys=(s.MASSAGE_WAVE, s.MASSAGE_HEAD, s.MASSAGE_FOOT),
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"meisemobell_{name}",
                label,
                lambda ctrl, method=name: getattr(
                    require_controller(ctrl, MeisemobellController), method
                )(),
                translation_key=f"meisemobell_{name}",
                requires_confirmation=name.startswith("reset"),
                diagnostic=True,
                scheduler_resource="*",
            )
            for name, label in (
                ("refresh_alarms", "Refresh alarms"),
                ("close_alarms", "Turn off both alarms"),
                ("reset_memories", "Reset memories"),
                ("reset_settings", "Reset settings"),
            )
        )


async def build_controller(ctx: BuildContext) -> BedController:
    route = ctx.variant
    if route not in app.PROFILES:
        raise invalid("meisemobell_route")
    return MeisemobellController(
        ctx.coordinator, "15_22_15a" if route == "15_22_15a" else "24_xx_xx"
    )
