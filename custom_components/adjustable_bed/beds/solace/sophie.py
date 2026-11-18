"""Sophie app behavior over the proven FFFF codec and shared Solace controller."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Collection
from dataclasses import replace
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_PRESET_SAVE
from ...codec import ff_frame as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateUpdate
from ...profiles import sophie as app
from ...profiles.ff_frame import SOLACE_PROFILES, SolaceProfile
from ...profiles.ff_frame import SolaceCommands as C
from ...state_keys import (
    LIGHT_LEVEL,
    LIGHT_TIMER_OPTION,
    MASSAGE_TIMER_MINUTES,
    SYNCHRO_MODE,
    UNDER_BED_LIGHTS_ON,
)
from ..base import BedController, require_controller
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .controller import SolaceController, preset_selected
from .sophie_state import (
    ALARM_ENABLED,
    ALARM_MASSAGE,
    ALARM_MODE,
    ALARM_RING,
    ALARM_SUPPORTED,
    ALARM_TIME,
    ALARM_WEEKDAYS,
    FOOT_LEVEL,
    HEAD_LEVEL,
    SYNC_SUPPORTED,
    WAVE,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


_PRESET_LABELS = {"tv": "TV", "zero_g": "zero gravity", "anti_snore": "anti-snore"}
# The app's alarm modes as shared wake actions; side models' "both" is zero gravity.
_WAKE_ACTIONS = {
    "no_action": "none",
    "zero_g": "zero_g",
    "memory_1": "memory_1",
    "zero_g_both": "zero_g",
    "zero_g_left": "zero_g_left",
    "zero_g_right": "zero_g_right",
}


def _alarm_modes(name: str) -> tuple[str, ...]:
    """Return the model's alarm modes with no action first, the default."""
    modes = app.alarm_modes(name)
    return ("no_action", *(mode for mode in modes if mode != "no_action"))


class SophieController(SolaceController):
    """One latched motor command, conditional alarm/sync and per-link startup."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._generation = 0
        self._notify_client: BleakClient | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._startup_task: asyncio.Task[None] | None = None

    @property
    def profile(self) -> SolaceProfile:
        return SOLACE_PROFILES["sophie"]

    @property
    def _query_family(self) -> str:
        return "q2" if app.named_queries(self._coordinator.ble_device_name) else "q1"

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            replace(
                spec,
                hold=ControllerMotorHoldSpec(
                    f"{spec.key}_up",
                    f"{spec.key}_down",
                    stop_scope="side",
                    press_is_native=True,
                ),
            )
            for spec in super().motor_control_specs
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return ("back_up", "back_down", "legs_up", "legs_down")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control not in self.held_control_options:
            raise ValueError("Unsupported Sophie held control")
        command = {
            "back_up": C.MOTOR_BACK_UP,
            "back_down": C.MOTOR_BACK_DOWN,
            "legs_up": C.MOTOR_LEGS_UP,
            "legs_down": C.MOTOR_LEGS_DOWN,
        }[control]
        await self._run_motor(command, duration_ms)

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Brightness is queried on every connection. The app's movement/massage
        # header literal has no proven effect, so it is not exposed.
        return tuple(
            ControllerButtonSpec(
                f"sophie_program_{key}",
                f"Save or clear {label} position",
                lambda c, key=key: require_controller(c, SophieController).save_preset(key),
                translation_key=f"sophie_program_{key}",
                requires_confirmation=True,
                card=CARD_PRESET_SAVE,
            )
            for key, label in _PRESET_LABELS.items()
        )

    @property
    def supports_synchro(self) -> bool:
        # Keep the switch stable before the support reply; execution is gated.
        return True

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(key, key, state, icon)
            for key, state, icon in (
                ("sophie_head_level", HEAD_LEVEL, "mdi:massage"),
                ("sophie_foot_level", FOOT_LEVEL, "mdi:massage"),
                ("sophie_wave", WAVE, "mdi:waveform"),
            )
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "sophie_alarm_enabled",
                "sophie_alarm_enabled",
                ALARM_ENABLED,
                "mdi:alarm",
                attribute_keys=(
                    ALARM_SUPPORTED,
                    ALARM_TIME,
                    ALARM_WEEKDAYS,
                    ALARM_MODE,
                    ALARM_MASSAGE,
                    ALARM_RING,
                ),
            ),
            *(
                ControllerStateBinarySensorSpec(
                    f"sophie_{key}_saved",
                    f"sophie_{key}_saved",
                    preset_selected(key),
                    "mdi:content-save",
                )
                for key in app.PRESET_KEYS
            ),
        )

    def _link(self) -> tuple[BleakClient, BleakGATTCharacteristic]:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Sophie is disconnected")
        # The app retains the last FFE1 under any service. Never infer FFE0.
        chars = [
            char
            for service in client.services
            for char in service.characteristics
            if char.uuid.lower() == codec.CHARACTERISTIC_UUID
        ]
        if not chars:
            raise ConnectionError("Sophie FFE1 characteristic is missing")
        return client, chars[-1]

    async def _write_link(
        self,
        client: BleakClient,
        char: BleakGATTCharacteristic,
        command: bytes,
        generation: int,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        async with self._ble_lock:
            if cancel_event is not None and cancel_event.is_set():
                raise asyncio.CancelledError
            if (
                generation != self._generation
                or client is not self.client
                or not client.is_connected
            ):
                raise ConnectionError("Sophie session changed")
            response = "write" in char.properties
            self._record_command_trace(char.uuid, command, response=response, characteristic=char)
            # No app repeat, retry or fixed write type is proven.
            await client.write_gatt_char(char, command, response=response)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        event = self._coordinator.cancel_command if cancel_event is None else cancel_event
        if event.is_set():
            raise asyncio.CancelledError
        client, char = self._link()
        await self._write_link(client, char, command, self._generation, event)

    async def _move_with_stop(self, command: bytes) -> None:
        await self._run_motor(command, self.leased_hold_ms(5000))

    async def _run_motor(self, command: bytes, duration_ms: int) -> None:
        client, char = self._link()
        generation, cancel = self._generation, self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        try:
            if cancel.is_set():
                return
            await self._write_link(client, char, command, generation, cancel)
            remaining = deadline - loop.time()
            if remaining > 0:
                try:
                    await asyncio.wait_for(cancel.wait(), remaining)
                except TimeoutError:
                    pass
        finally:
            # Never redirect a delayed release to a newly connected bed/side.
            if generation == self._generation and client is self.client and client.is_connected:
                release = asyncio.create_task(
                    self._write_link(client, char, codec.STOP, generation)
                )
                interrupted = False
                while not release.done():
                    try:
                        await asyncio.shield(release)
                    except asyncio.CancelledError:
                        interrupted = True
                release.result()
                if interrupted:
                    raise asyncio.CancelledError
                if (context := current_command_context()) is not None:
                    context.cleanup_stop_sent = True

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        if not self._preset_is_selected(f"memory_{memory_num}"):
            raise ValueError("Sophie memory has not been reported saved")

    async def _send_preset(self, command: bytes) -> None:
        await self.write_command(command)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Sophie has two memory slots")
        self.validate_memory_recall(memory_num)
        await super().preset_memory(memory_num)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Sophie has two memory slots")
        await self.save_preset(f"memory_{memory_num}")

    async def save_preset(self, key: str) -> None:
        index = app.PRESET_KEYS.index(key)
        code = app.PRESET_CODES[index]
        arg = ((code << 4) | (0x0F if self._preset_is_selected(key) else 0)) & 0xFF
        # HA has explicit, confirmed save actions instead of Android's uncancelled
        # 2-second delayed callback. Only replies establish receiver saved state.
        await self.write_command(codec.control(code, arg=arg))

    async def sync_clock(self) -> None:
        now = dt_util.now()
        await self.write_command(codec.clock(now, now.isoweekday()))

    async def set_synchro(self, enabled: bool) -> None:
        if not self._coordinator.controller_state.get(SYNC_SUPPORTED, False):
            raise ValueError("Sophie synchronization support has not been reported")
        await self.write_command(app.SYNC_ON if enabled else app.SYNC_OFF)
        self.forward_controller_state_updates(SYNCHRO_MODE(enabled))

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        # Offered only once this bed has reported alarm support.
        if not self._coordinator.controller_state.get(ALARM_SUPPORTED, False):
            return None
        name = self._coordinator.ble_device_name
        return AlarmCapability(
            wake_actions=tuple(_WAKE_ACTIONS[mode] for mode in _alarm_modes(name)),
            weekdays=True,
            massage=app.alarm_massage_allowed(name),
            sounds=("none", "alarm"),
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        modes = {
            _WAKE_ACTIONS[mode]: mode for mode in app.alarm_modes(self._coordinator.ble_device_name)
        }
        # The app numbers Monday 1 through Sunday 7.
        await self.set_alarm(
            enabled=alarm.enabled,
            hour=alarm.hour,
            minute=alarm.minute,
            weekdays=tuple(day + 1 for day in alarm.weekdays),
            mode=modes[alarm.wake_action],
            massage=alarm.massage,
            ring=alarm.sound == "alarm",
        )

    def _validate_alarm_mode(self, mode: str, massage: bool) -> None:
        if not self._coordinator.controller_state.get(ALARM_SUPPORTED, False):
            raise ValueError("Sophie alarm support has not been reported")
        name = self._coordinator.ble_device_name
        if mode not in app.alarm_modes(name):
            raise ValueError("This Sophie model does not expose the selected alarm mode")
        if massage and not app.alarm_massage_allowed(name):
            raise ValueError("QMS2 does not expose alarm massage")

    async def set_alarm(
        self,
        *,
        enabled: bool,
        hour: int,
        minute: int,
        weekdays: Collection[int],
        mode: str,
        massage: bool,
        ring: bool,
    ) -> None:
        self._validate_alarm_mode(mode, massage)
        await self.write_command(
            codec.alarm(
                switch=1 if enabled else 0xA1,
                hour=hour,
                minute=minute,
                weekday_mask=sum(1 << day for day in set(weekdays)),
                repeat=bool(weekdays),
                mode=app.ALARM_MODES[mode],
                massage=massage,
                sound=int(ring),
            )
        )
        # An unsuccessful or skipped write must not persist an Android-style
        # local alarm. Reported state remains authoritative.

    async def massage_off(self) -> None:
        await super().massage_off()
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(0))

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in (0, 10, 20, 30):
            raise ValueError("Invalid Sophie massage timer")
        selected = self._coordinator.controller_state.get(MASSAGE_TIMER_MINUTES)
        value = 0 if minutes == selected else minutes
        await super().set_massage_timer(value)
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(value))

    @property
    def light_timer_options(self) -> list[str]:
        return ["10 min", "8 hours", "10 hours"]

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option not in self.light_timer_options:
            raise ValueError("Invalid Sophie light timer")
        await super().set_light_timer(timer_option)
        self.forward_controller_state_updates(LIGHT_TIMER_OPTION(timer_option))

    async def set_light_level(self, level: int) -> None:
        if LIGHT_LEVEL not in self._coordinator.controller_state:
            raise ValueError(
                "Sophie has not reported brightness support yet; try again in a moment"
            )
        await super().set_light_level(level)
        if 0 <= level <= 10:
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(level > 0))
            if level == 0:
                self.forward_controller_state_updates(LIGHT_TIMER_OPTION("Off"))

    async def lights_on(self) -> None:
        await self.set_light_level(10)

    async def lights_off(self) -> None:
        await self.set_light_level(0)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        self._generation += 1
        client, char = self._link()
        generation = self._generation
        self._notify_client, self._notify_char = client, char

        def receive(sender: object, data: bytearray) -> None:
            if generation == self._generation and client is self.client and client.is_connected:
                self._handle_notification(sender, data)

        await client.start_notify(char, receive)

    async def async_after_connect(self, session: ControllerSession) -> None:
        self._cancel_startup()
        generation = self._generation
        self._startup_task = asyncio.create_task(self._startup(session, generation))

    async def _startup(self, session: ControllerSession, generation: int) -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        queries = C.QUERY_Q2 if self._query_family == "q2" else C.QUERY_Q1
        schedule: list[tuple[int, bytes | None]] = [
            (app.QUERY_DELAY_MS + i * app.QUERY_SPACING_MS, frame)
            for i, frame in enumerate(queries)
        ]
        schedule += [
            (app.CLOCK_DELAY_MS, None),
            (app.CLOCK_DELAY_MS + app.SYNC_AFTER_CLOCK_MS, app.SYNC_QUERY),
            (app.LIGHT_QUERY_DELAY_MS, C.LIGHT_STATUS_QUERY),
        ]
        try:
            for offset, frame in sorted(schedule, key=lambda row: row[0]):
                await asyncio.sleep(max(0, start + offset / 1000 - loop.time()))
                if generation != self._generation or not session.is_current():
                    return

                async def query(controller: BedController, frame: bytes | None = frame) -> None:
                    if (
                        controller is self
                        and generation == self._generation
                        and session.is_current()
                    ):
                        if frame is None:
                            await self.sync_clock()
                        else:
                            await self.write_command(frame)

                try:
                    await self._coordinator.async_execute_controller_query(
                        query,
                        skip_disconnect=True,
                        preemptible=True,
                        run_if=lambda: generation == self._generation and session.is_current(),
                    )
                except asyncio.CancelledError:
                    # Command preemption ends this query, not the remaining startup.
                    task = asyncio.current_task()
                    if (
                        task is None
                        or task.cancelling()
                        or generation != self._generation
                        or not session.is_current()
                    ):
                        raise
        except (BleakError, ConnectionError, RuntimeError) as err:
            _LOGGER.debug("Sophie startup query ended: %s", err)

    def _cancel_startup(self) -> None:
        if self._startup_task is not None:
            self._startup_task.cancel()
            self._startup_task = None

    async def stop_notify(self) -> None:
        self._generation += 1
        self._cancel_startup()
        client, char = self._notify_client, self._notify_char
        self._notify_client = self._notify_char = None
        if client is not None and char is not None and client.is_connected:
            await client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._generation += 1
        self._cancel_startup()
        self._notify_client = self._notify_char = None
        # Support replies describe this physical bed, not the lifetime of its
        # BLE link. Offline preflight must retain them across idle disconnects.
        self.forward_controller_state_updates(SYNCHRO_MODE(None))

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    def _parse_notification(self, data: bytes) -> None:
        updates: list[StateUpdate] = []
        for code, key in zip(app.PRESET_CODES, app.PRESET_KEYS, strict=True):
            if self._query_family == "q2" and codec.HEADER + bytes((3, 6, 0, code)) in data:
                updates.append(preset_selected(key)(True))
            fallback = {0x0A: 0xAA, 0x0B: 0xAB, 0x05: 0xAB, 0x09: 0xA9, 0x0F: 0xAF}[code]
            if self._query_family == "q1" and codec.HEADER + bytes((3, 0x12, 0, fallback)) in data:
                updates.append(preset_selected(key)(True))
            for arg, saved in (((code << 4) & 0xFF, True), (((code << 4) | 15) & 0xFF, False)):
                if codec.control(code, arg=arg) in data:
                    updates.append(preset_selected(key)(saved))
        for zone in ("head", "foot", "wave"):
            # Preserve the app's outer head > foot > wave priority.
            prefix = codec.HEADER + bytes((5, 0, 0, {"head": 1, "foot": 2, "wave": 3}[zone]))
            if prefix in data:
                for level, frame in enumerate(app.MASSAGE_REPLIES[zone]):
                    if frame in data:
                        if zone == "head":
                            updates.append(HEAD_LEVEL(level))
                        elif zone == "foot":
                            updates.append(FOOT_LEVEL(level))
                        else:
                            updates.append(WAVE(level + 1))
                break
        light = codec.HEADER + bytes((5, 0, 1))
        if data.startswith(light) and len(data) >= 8:
            value = data[7]
            # Keep the raw reported byte; do not invent an absolute massage or
            # brightness command from out-of-range received state.
            updates += [LIGHT_LEVEL(value), UNDER_BED_LIGHTS_ON(value > 0)]
            if value == 0:
                updates.append(LIGHT_TIMER_OPTION("Off"))
        for frame in (C.LIGHT_TIMER_10_MIN, C.LIGHT_TIMER_8_HOURS, C.LIGHT_TIMER_10_HOURS):
            if frame + bytes.fromhex("FFFFFF0500050000C701") in data:
                updates.append(LIGHT_TIMER_OPTION("Off"))
        none = codec.HEADER + bytes((1, 0, 3, 0x0B, 0))
        present = codec.HEADER + bytes((1, 0, 4, 0x13))
        if data.startswith(none):
            updates += [
                ALARM_SUPPORTED(True),
                ALARM_ENABLED(False),
                ALARM_TIME(None),
                ALARM_WEEKDAYS(""),
                ALARM_MODE("no_action"),
                ALARM_MASSAGE(False),
                ALARM_RING(False),
            ]
        elif data.startswith(present) and len(data) >= 17:
            updates += [
                ALARM_SUPPORTED(True),
                ALARM_ENABLED(data[8] == 0x0F),
                ALARM_TIME(f"{data[9]:02x}:{data[10]:02x}"),
                ALARM_WEEKDAYS(",".join(str(day) for day in range(1, 8) if data[12] & 1 << day)),
                ALARM_MODE(
                    next(
                        (key for key, value in app.ALARM_MODES.items() if value == data[14]),
                        f"unknown_{data[14]:02x}",
                    )
                ),
                ALARM_MASSAGE(data[15] == 1),
                ALARM_RING(data[16] == 1),
            ]
        elif (
            present not in data
            and len(data) >= 9
            and any(data.startswith(codec.HEADER + bytes((1, 0, op, 0x0B))) for op in (9, 10))
        ):
            updates += [SYNC_SUPPORTED(True), SYNCHRO_MODE(data[8] == 1)]
        if updates:
            self.forward_controller_state_updates(*updates)
