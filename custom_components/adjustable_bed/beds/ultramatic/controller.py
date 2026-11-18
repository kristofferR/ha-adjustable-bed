"""Ultramatic's session and gestures over the proven shared N-frame codec."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmError
from ...card import CARD_HIDDEN, CARD_LIGHTING, CARD_MASSAGE, CARD_PRESET_SAVE, CARD_UTILITY
from ...codec.okin_nframe import SideRecordParser
from ...command_scheduler import note_frame_skipped, note_frame_written
from ...const import CONF_CB24_BED_SELECTION, SIDE_BOTH, SIDE_LEFT, SIDE_RIGHT
from ...profiles import ultramatic as app
from ...profiles.okin_nframe import OkinNFrameProfile
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..okin_nframe import OkinNFrameController
from .state import SIDES, AlarmSettings

# The app's wake choices: Vibrate, ZG and M1 (types 1 to 3). Days are a weekday mask.
ALARM_CAPABILITY = AlarmCapability(
    wake_actions=tuple(app.WAKE_TYPES),
    weekdays=True,
    requires_wake_action=True,
    cancel_running=True,
    resource="*",
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

MOVEMENT = tuple(
    f"{axis}{direction}"
    for axis in (
        "HEAD",
        "FOOT",
        "HEADTILT",
        "LUMBAR",
        "HIPS",
    )
    for direction in ("UP", "DOWN")
)
PRESETS = ("FLAT", "ZG", "ANTI", "M1", "M2")
SAVE_PRESETS = ("ZG", "ANTI", "M1", "M2")
MASSAGE = (
    "timerSwitch",
    "headStrengthAdd",
    "headStrengthReduce",
    "footStrengthAdd",
    "footStrengthReduce",
    "waveAdd",
    "waveReduce",
    "massageOnOff",
)


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


@dataclass(frozen=True, slots=True)
class AlarmPlan:
    link: Link
    side: str
    frame: bytes


class _Elapsed(Exception):
    """A finite hold expired while its write waited for BLE ownership."""


async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
    if cancel.is_set():
        return True
    try:
        await asyncio.wait_for(cancel.wait(), max(0, seconds))
    except TimeoutError:
        return False
    return True


class UltramaticController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
    """One physical UART, one command stream, independent A/AB/B addressing."""

    def __init__(self, coordinator: AdjustableBedCoordinator, selector: int = 0) -> None:
        super().__init__(coordinator)
        if isinstance(selector, bool) or selector not in (0, 1, 2):
            raise ValueError("Ultramatic selector must be AB (0), A (1) or B (2)")
        self.profile = app.PROFILE
        self._default_side = {0: "AB", 1: "A", 2: "B"}[selector]
        self._write_with_response = False
        self._link: Link | None = None
        self._notifying = False
        self._parser = SideRecordParser(app.HEADERS)
        self._alarms: dict[str, AlarmSettings] = {}
        self._operation_generation = 0

    @property
    def session_token(self) -> Link | None:
        return self._link

    @property
    def operation_generation(self) -> int:
        return self._operation_generation

    @property
    def control_characteristic_uuid(self) -> str:
        return app.WRITE_UUID

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._live()
        if not self._notifying:
            raise ConnectionError("Ultramatic notifications are not ready")

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True  # This app performs no Device Information reads.

    def _side(self) -> str:
        if self.command_side is None:
            return self._default_side
        return {SIDE_LEFT: "A", SIDE_RIGHT: "B", SIDE_BOTH: "AB"}.get(
            self.command_side, self._default_side
        )

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
            raise ConnectionError("Ultramatic connection changed or disconnected")
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Ultramatic is not connected")
        roles = {
            c.uuid.lower(): c
            for service in client.services
            if service.uuid.lower() == app.SERVICE_UUID
            for c in service.characteristics
        }
        write, notify = roles.get(app.WRITE_UUID), roles.get(app.NOTIFY_UUID)
        if (
            write is None
            or "write-without-response" not in write.properties
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError(
                "Ultramatic requires its exact UART write-without-response and notify roles"
            )
        self._link = Link(client, write, notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._parser = SideRecordParser(app.HEADERS)
        self._alarms.clear()
        self._operation_generation += 1
        for side in SIDES.values():
            self.forward_controller_state_updates(
                side.timer(None),
                side.wave(None),
                side.head(None),
                side.foot(None),
                side.alarm(None),
                side.days(None),
                side.wake_type(None),
                side.position(None),
                side.enabled(None),
                side.standalone(None),
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
                or self._coordinator.controller is not self
            ):
                return
            self.forward_raw_notification(link.notify.uuid, bytes(data))
            records = self._parser.feed(bytes(data))
            if records is not None:
                self._receive(records)

        for attempt in range(2):
            try:
                async with self._ble_lock:
                    self._live(link)
                    await link.client.start_notify(link.notify, received)
                self._live(link)
                self._notifying = True
                return
            except BleakError, TimeoutError:
                if attempt:
                    raise
                await _pause(asyncio.Event(), app.NOTIFY_RETRY_MS / 1000)
                self._live(link)

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._notifying
        self.on_disconnect()
        if link is not None and link.client.is_connected and subscribed:
            async with self._ble_lock:
                if self._link is None:
                    await link.client.stop_notify(link.notify)

    def _receive(self, records: tuple[bytes, bytes, bytes]) -> None:
        now = dt_util.now()
        for name, keys in SIDES.items():
            state = app.state(records, name, now)
            standalone = state["standalone"] is True
            self.forward_controller_state_updates(keys.standalone(standalone))
            if state["kind"] == "massage":
                self.forward_controller_state_updates(
                    keys.timer(int(state["timer_bucket"]) * 10),
                    keys.wave(int(state["wave"])),
                    keys.head(int(state["head"])),
                    keys.foot(int(state["foot"])),
                )
            else:
                hour, minute = int(state["hour"]), int(state["minute"])
                type_code = (
                    1 if state["wake_type"] == "Vibrate" else int(state["position_index"]) + 2
                )
                row = AlarmSettings(
                    hour, minute, int(state["days"]), type_code, state["enabled"] is True
                )
                # Display fallback is not permission to overwrite a physical alarm.
                first, second = records[1:]
                if name == "AB":
                    selected = (
                        first
                        if {first[0], second[0]} == {1, 2}
                        and app.equivalent(first, second, massage=False)
                        else None
                    )
                else:
                    selected = next(
                        (r for r in (first, second) if r[0] == app.SELECTORS[name]), None
                    )
                raw_hour = (selected[3] >> 4) * 10 + (selected[3] & 15) if selected else -1
                raw_minute = (selected[4] >> 4) * 10 + (selected[4] & 15) if selected else -1
                if (
                    selected is not None
                    and selected[1] != 0
                    and selected[2] in (1, 2, 3)
                    and selected[6] in (0, 1)
                    and all(value >> 4 <= 9 and value & 15 <= 9 for value in selected[3:5])
                    and 0 <= raw_hour <= 23
                    and 0 <= raw_minute <= 59
                ):
                    self._alarms[name] = AlarmSettings(
                        raw_hour,
                        raw_minute,
                        selected[1],
                        selected[2],
                        selected[6] == 1,
                    )
                else:
                    self._alarms.pop(name, None)
                self.forward_controller_state_updates(
                    keys.alarm(f"{hour:02}:{minute:02}"),
                    keys.days(row.days),
                    keys.wake_type(str(state["wake_type"])),
                    keys.position(type_code - 2 if type_code != 1 else None),
                    keys.enabled(row.enabled),
                )

    async def _write(
        self,
        link: Link,
        command: bytes,
        cancel: asyncio.Event,
        *,
        deadline: float | None = None,
        generation: int | None = None,
        validate: Callable[[], None] | None = None,
    ) -> None:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                note_frame_skipped()
                return
            if generation is not None and self._operation_generation != generation:
                raise ConnectionError("Ultramatic alarm or query was superseded")
            if deadline is not None and asyncio.get_running_loop().time() + 1e-9 >= deadline:
                raise _Elapsed
            if validate is not None:
                validate()
            self._record_command_trace(
                link.write.uuid, command, response=False, characteristic=link.write
            )
            await link.client.write_gatt_char(link.write, command, response=False)
            note_frame_written(cancel)
            self._live(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        self._operation_generation += 1
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if index and await _pause(cancel, repeat_delay_ms / 1000):
                note_frame_skipped()
                return
            await self._write(link, command, cancel)

    async def _release(self, link: Link) -> None:
        async def finish() -> None:
            await _pause(asyncio.Event(), self.profile.hold.release_after_ms / 1000)
            # A release belongs only to the captured connection, even on cancellation.
            if self._link is link and self.client is link.client and link.client.is_connected:
                await self._write(link, app.control("STOP"), asyncio.Event())

        task = asyncio.create_task(finish())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*MOVEMENT, *PRESETS)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unsupported Ultramatic held control")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError("Hold duration must be an integer from 1 to 60000 ms")

    async def _hold(self, action: str, duration_ms: int) -> None:
        link, side = self._live(), self._side()
        self._operation_generation += 1
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        interval = self.profile.hold.repeat_ms
        assert interval is not None
        window = asyncio.timeout_at(deadline)
        try:
            async with window:
                while not cancel.is_set() and loop.time() + 1e-9 < deadline:
                    try:
                        await self._write(
                            link, app.control(action, side), cancel, deadline=deadline
                        )
                    except _Elapsed:
                        break
                    # Pace from completion. Slow writes never create backfill bursts.
                    if await _pause(cancel, min(interval / 1000, max(0, deadline - loop.time()))):
                        break
        except TimeoutError:
            if not window.expired():
                raise
        finally:
            await self._release(link)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._hold(control, self.leased_hold_ms(duration_ms))

    async def _press(self, action: str) -> None:
        interval = self.profile.hold.repeat_ms
        assert interval is not None
        await self.hold_control(action, min(60000, self._coordinator.motor_pulse_count * interval))

    async def _sequence(
        self,
        link: Link,
        sequence: tuple[tuple[float, bytes], ...],
        *,
        validate: Callable[[], None] | None = None,
    ) -> None:
        self._operation_generation += 1
        generation = self._operation_generation
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for offset, command in sequence:
            if await _pause(cancel, max(0, started + offset - loop.time())):
                return
            if self._operation_generation != generation:
                raise ConnectionError("Ultramatic alarm or query was superseded")
            if validate is not None:
                validate()
            await self._write(link, command, cancel, generation=generation, validate=validate)
            if self._operation_generation != generation:
                raise ConnectionError("Ultramatic alarm or query was superseded")

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        clock = app.clock(dt_util.now())
        await self._sequence(
            link,
            tuple(
                (ms / 1000, clock if kind == "clock" else app.QUERY_MASSAGE)
                for ms, kind in app.STARTUP
            ),
        )

    async def sync_clock(self) -> None:
        command = app.clock(dt_util.now())
        await self._sequence(
            self._live(), tuple((ms / 1000, command) for ms, _kind in app.CLOCK_SYNC)
        )

    async def query(self, kind: str, *, validate: Callable[[], None] | None = None) -> None:
        if kind not in ("alarm", "massage"):
            raise ValueError("Query must be alarm or massage")
        command = app.QUERY_ALARM if kind == "alarm" else app.QUERY_MASSAGE
        sequence = (
            tuple((ms / 1000, command) for ms, _kind in app.ALARM_QUERY)
            if kind == "alarm"
            else ((0, command),)
        )
        await self._sequence(self._live(), sequence, validate=validate)

    async def action(self, action: str) -> None:
        if action in MASSAGE:
            await self._sequence(
                self._live(),
                (
                    (0, app.control(action, self._side())),
                    *((ms / 1000, app.QUERY_MASSAGE) for ms in app.MASSAGE_QUERIES),
                ),
            )
        elif action == "LIGHT":
            link = self._live()
            self._operation_generation += 1
            if self._coordinator.cancel_command.is_set():
                return
            try:
                await self._write(
                    link, app.control(action, self._side()), self._coordinator.cancel_command
                )
            finally:
                await self._release(link)
        else:
            raise ValueError("Unsupported Ultramatic one-shot action")

    async def save_preset(self, preset: str) -> None:
        if preset not in SAVE_PRESETS:
            raise ValueError("Only ZG, ANTI, M1 and M2 have the app's save gesture")
        await self._hold(preset, app.SAVE_HOLD_MS)

    async def reset_memory(self) -> None:
        await self._hold("reset_memory", app.SAVE_HOLD_MS)

    @property
    def alarm_capability(self) -> AlarmCapability:
        return ALARM_CAPABILITY

    def prepare_alarm(self, settings: AlarmSettings | None, *, disable: bool = False) -> AlarmPlan:
        if disable and self._link is None:
            # Offline there is no reported alarm to turn off.
            raise AlarmError(
                "alarm_refresh_needed",
                "Refresh alarms on this connection before turning the alarm off",
            )
        link, side = self._live(), self._side()
        if disable:
            # Only the alarm reported on this connection is known; it keeps its fields.
            cached = self._alarms.get(side)
            if cached is None:
                raise AlarmError(
                    "alarm_refresh_needed",
                    "Refresh alarms on this connection before turning the alarm off",
                )
            if not cached.enabled:
                raise AlarmError(
                    "alarm_already_off", "The alarm is already off, so nothing was sent"
                )
            settings = AlarmSettings(cached.hour, cached.minute, cached.days, cached.type_code, False)
        if settings is None:
            raise ValueError("Alarm settings are required")
        return AlarmPlan(
            link,
            side,
            app.alarm(
                settings.hour,
                settings.minute,
                settings.days,
                settings.type_code,
                settings.enabled,
                side,
                now=dt_util.now(),
            ),
        )

    def validate_plan(self, plan: AlarmPlan) -> None:
        self._live(plan.link)
        if self._side() != plan.side:
            raise ValueError("Ultramatic alarm side changed after validation")

    async def set_alarm(
        self, plan: AlarmPlan, *, validate: Callable[[], None] | None = None
    ) -> None:
        self.validate_plan(plan)
        # Source mutable-buffer quirk: the 500 ms query replaces the 600 ms retry.
        await self._sequence(
            plan.link,
            tuple(
                (ms / 1000, plan.frame if kind == "alarm" else app.QUERY_ALARM)
                for ms, kind in app.ALARM_SET
            ),
            validate=validate,
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                f"ultramatic_{axis}",
                lambda c, a=axis: require_controller(c, UltramaticController)._press(
                    a.upper() + "UP"
                ),
                lambda c, a=axis: require_controller(c, UltramaticController)._press(
                    a.upper() + "DOWN"
                ),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    axis.upper() + "UP",
                    axis.upper() + "DOWN",
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                    release_button_key="ultramatic_release",
                ),
            )
            for axis in self.profile.axes
        )

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    def standard_button_requires_confirmation(self, key: str) -> bool:
        return key in ("program_memory_1", "program_memory_2")  # The 6 s save gesture.

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = {
            "preset_flat": "FLAT",
            "preset_zero_g": "ZG",
            "preset_anti_snore": "ANTI",
            "preset_memory_1": "M1",
            "preset_memory_2": "M2",
        }.get(key)
        return (
            ControllerHoldSpec(action, release_button_key="ultramatic_release") if action else None
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *(
                ControllerButtonSpec(
                    f"ultramatic_{action}",
                    label,
                    lambda c, a=action: require_controller(c, UltramaticController).action(a),
                    translation_key=f"ultramatic_{action.lower()}",
                    scheduler_resource="*",
                    card=CARD_MASSAGE,
                )
                for action, label in (
                    ("timerSwitch", "Cycle massage timer"),
                    ("headStrengthAdd", "Increase head massage"),
                    ("headStrengthReduce", "Decrease head massage"),
                    ("footStrengthAdd", "Increase foot massage"),
                    ("footStrengthReduce", "Decrease foot massage"),
                    ("waveAdd", "Increase massage wave"),
                    ("waveReduce", "Decrease massage wave"),
                    # massageOnOff is the generic massage toggle (massage_toggle).
                )
            ),
            ControllerButtonSpec(
                "ultramatic_light",
                "Toggle light",
                lambda c: require_controller(c, UltramaticController).action("LIGHT"),
                translation_key="ultramatic_light",
                scheduler_resource="*",
                card=CARD_LIGHTING,
            ),
            # M1/M2 saves are the generic "Save to Memory" buttons (program_memory).
            *(
                ControllerButtonSpec(
                    f"ultramatic_save_{preset.lower()}",
                    label,
                    lambda c, p=preset: require_controller(c, UltramaticController).save_preset(p),
                    translation_key=f"ultramatic_save_{preset.lower()}",
                    scheduler_resource="*",
                    requires_confirmation=True,
                    card=CARD_PRESET_SAVE,
                )
                for preset, label in (
                    ("ZG", "Save zero gravity position"),
                    ("ANTI", "Save anti-snore position"),
                )
            ),
            ControllerButtonSpec(
                "ultramatic_reset_memory",
                "Reset saved positions",
                lambda c: require_controller(c, UltramaticController).reset_memory(),
                translation_key="ultramatic_reset_memory",
                scheduler_resource="*",
                requires_confirmation=True,
                card=CARD_PRESET_SAVE,
            ),
            *(
                ControllerButtonSpec(
                    f"ultramatic_query_{kind}",
                    f"Refresh {kind}",
                    lambda c, k=kind: require_controller(c, UltramaticController).query(k),
                    translation_key=f"ultramatic_query_{kind}",
                    scheduler_resource="*",
                    diagnostic=True,
                    card=CARD_UTILITY,
                )
                for kind in ("massage", "alarm")
            ),
            ControllerButtonSpec(
                "ultramatic_clock",
                "Sync bed clock",
                lambda c: require_controller(c, UltramaticController).sync_clock(),
                translation_key="ultramatic_clock",
                scheduler_resource="*",
                card=CARD_UTILITY,
            ),
            ControllerButtonSpec(
                "ultramatic_release",
                "Release held control",
                lambda c: c.stop_all(),
                translation_key="ultramatic_release",
                release_only=True,
                card=CARD_HIDDEN,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            spec
            for name, keys in SIDES.items()
            for spec in (
                ControllerStateSensorSpec(
                    f"ultramatic_{name.lower()}_timer",
                    f"ultramatic_{name.lower()}_timer",
                    keys.timer,
                    "mdi:timer",
                    "min",
                    (keys.wave, keys.head, keys.foot, keys.standalone),
                    card=CARD_MASSAGE,
                ),
                ControllerStateSensorSpec(
                    f"ultramatic_{name.lower()}_alarm",
                    f"ultramatic_{name.lower()}_alarm",
                    keys.alarm,
                    "mdi:alarm",
                    attribute_keys=(
                        keys.days,
                        keys.wake_type,
                        keys.position,
                        keys.enabled,
                        keys.standalone,
                    ),
                    card=CARD_UTILITY,
                ),
            )
        )

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    async def move_head_up(self) -> None:
        await self._press("HEADUP")

    async def move_head_down(self) -> None:
        await self._press("HEADDOWN")

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_legs_up(self) -> None:
        await self._press("FOOTUP")

    async def move_legs_down(self) -> None:
        await self._press("FOOTDOWN")

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        self._operation_generation += 1
        if not CONTROLLER_GESTURE_RELEASE.get():
            await self._release(self._live())

    async def preset_flat(self) -> None:
        await self._press("FLAT")

    async def preset_zero_g(self) -> None:
        await self._press("ZG")

    async def preset_anti_snore(self) -> None:
        await self._press("ANTI")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._press(f"M{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.save_preset(f"M{memory_num}")

    async def massage_toggle(self) -> None:
        await self.action("massageOnOff")


async def build_controller(ctx: BuildContext) -> BedController:
    return UltramaticController(ctx.coordinator, selector=ctx.data.get(CONF_CB24_BED_SELECTION, 0))
