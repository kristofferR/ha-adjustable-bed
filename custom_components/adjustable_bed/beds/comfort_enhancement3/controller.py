"""Row083 app-specific gestures and wake-up sessions over the shared Okin controller."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from bleak.exc import BleakError

from ...card import CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey
from ...profiles.comfort_enhancement3 import MASSAGE_KEYS, PROFILES, REMOTES, resolve
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from ..okin_handle import OkinHandleController

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
NOTIFY_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"
SERVICE_CHANGED: Final = "00002a05-0000-1000-8000-00805f9b34fb"
MODEL_UUID: Final = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID: Final = "00002a26-0000-1000-8000-00805f9b34fb"
MASSAGE_END: Final = StateKey[str | None]("apex_local_massage_end")
FIRMWARE: Final = StateKey[str | None]("apex_firmware")


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    changed: BleakGATTCharacteristic | None
    info: tuple[BleakGATTCharacteristic, ...]


def delay_ticks(target: datetime, now: datetime) -> int:
    """Dart truncates whole seconds toward zero before checking the sign."""
    delta = target.astimezone(UTC) - now.astimezone(UTC)
    micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    seconds = abs(micros) // 1000000
    return (-seconds if micros < 0 else seconds) * 10


def selected_time(now: datetime, hour: int, minute: int, next_day: bool) -> datetime:
    """The app selects the current or next calendar day; no past-time rollover."""
    if (
        type(hour) is not int
        or type(minute) is not int
        or not 0 <= hour < 24
        or not 0 <= minute < 60
    ):
        raise ValueError("Choose a valid hour and minute")
    # DateTime in the app normalizes out-of-range fields. HA exposes only valid
    # time inputs and still normalizes the selected day across month/year ends.
    selected = now.replace(hour=0, minute=0, second=0, microsecond=0, fold=0) + timedelta(
        days=int(next_day), hours=hour, minutes=minute
    )
    return datetime.fromtimestamp(selected.timestamp(), selected.tzinfo)


def wake_frames(
    index: int,
    slot: int,
    ticks: int,
    *,
    massage: bool = False,
    duration: int = 10,
    intensity: int = 1,
    kind: str = "head",
    light: bool = False,
    preset: str = "None",
) -> tuple[bytes, ...]:
    remote = REMOTES[index]
    if type(massage) is not bool or type(light) is not bool:
        raise ValueError("Massage and light must be boolean")
    if (
        preset not in remote.wake_presets
        or light
        and not remote.light
        or massage
        and not remote.wake_massage
    ):
        raise ValueError("Wake-up effect is unavailable for this remote")
    validate_massage(duration, intensity, kind)
    frames = [codec.schedule_step(slot, 0, ticks, 0, 5)]
    words: list[tuple[int, int]] = []
    if massage:
        words += [(MASSAGE_KEYS["massage_duration"], 0)] * (duration // 10)
        for key in massage_axes(kind):
            words += [(MASSAGE_KEYS[key], 0)] * (1 if kind == "wave" else intensity)
    if light:
        words.append((0x20000, 0))
    if preset != "None":
        words.append(
            (
                {"M1": 0x1000, "M2": 0x2000, "Zero Gravity": 0x4000, "TV": 0x3000, "QS": 0x8000}[
                    preset
                ],
                5,
            )
        )
    for word, last in words:
        frames.append(codec.schedule_step(slot, len(frames), 0, 0, 5))
        frames.append(codec.schedule_step(slot, len(frames), 0, word, last))
    return tuple(frames)


def validate_massage(duration: int, intensity: int, kind: str) -> None:
    if (
        type(duration) is not int
        or duration not in (10, 20, 30)
        or type(intensity) is not int
        or intensity not in (1, 2, 3)
        or kind not in ("head", "feet", "both", "wave")
    ):
        raise ValueError("Choose 10/20/30 minutes, intensity 1/2/3 and head/feet/both/wave")


def massage_axes(kind: str) -> tuple[str, ...]:
    return {
        "head": ("massage_head",),
        "feet": ("massage_foot",),
        "both": ("massage_head", "massage_foot"),
        "wave": ("massage_wave",),
    }[kind]


class ComfortEnhancement3Controller(OkinHandleController):
    """Reuse the shared family movement/preset API, with this app's own session."""

    def __init__(self, coordinator: AdjustableBedCoordinator, index: int = 0) -> None:
        super().__init__(coordinator)
        self.index = index
        self.remote = REMOTES[index]
        self.profile = PROFILES[f"apex_{index}"]
        self._link: _Link | None = None
        self._subscriptions: list[BleakGATTCharacteristic] = []
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._callbacks: set[asyncio.Task[None]] = set()
        self._wakes: dict[str, dict[str, Any]] = {}
        self._massage_end: str | None = None

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return self.remote.flat

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.remote.zg

    @property
    def supports_preset_tv(self) -> bool:
        return self.remote.tv

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False  # QS/Zzz keeps its app label as a controller button.

    @property
    def supports_lights(self) -> bool:
        return self.remote.light

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return self.remote.massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.remote.massage

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.remote.light

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self.remote.massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.remote.massage

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return self.remote.massage

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return self.remote.massage

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = []
        # Back/legs are HA's standard routes to the app's Head/Foot. Extra
        # app groups stay labelled buttons, not invented physical axes.
        for key, up, down in (("back", "head_up", "head_down"), ("legs", "feet_up", "feet_down")):
            specs.append(
                MotorControlSpec(
                    key,
                    key,
                    lambda c, k=up: _apex(c).move(k),
                    lambda c, k=down: _apex(c).move(k),
                    lambda c: c.stop_all(),
                    scheduler_resource="*",
                    hold=ControllerMotorHoldSpec(up, down, press_hold_ms=None, stop_scope="side"),
                )
            )
        return tuple(specs)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def held_control_options(self) -> tuple[str, ...]:
        # Favorites ZG has no proven renewable wire stream. Presets are safe
        # one-shot recalls. Relative massage steps are never held controls.
        return tuple(k for k in self.profile.keys if k.endswith(("_up", "_down")))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for key, label, _, _ in self.remote.groups:
            for direction in ("up", "down"):
                control = f"{key}_{direction}"
                buttons.append(
                    ControllerButtonSpec(
                        f"apex_{control}",
                        f"{label} {direction}",
                        lambda c, k=control: _apex(c).move(k),
                        scheduler_resource="*",
                        translation_key="apex_group",
                        translation_placeholders={"action": f"{label} {direction}"},
                        hold=ControllerHoldSpec(control),
                        invalidates_position=True,
                        card=CARD_UTILITY,
                    )
                )
        if self.remote.qs or self.remote.tv:
            buttons.append(
                ControllerButtonSpec(
                    "apex_qs",
                    "QS" if self.remote.qs else "Zzz",
                    lambda c: _apex(c)._preset("qs"),
                    scheduler_resource="*",
                    translation_key="apex_qs",
                    translation_placeholders={"action": "QS" if self.remote.qs else "Zzz"},
                    invalidates_position=True,
                    card=CARD_PRESETS,
                )
            )
        if self.remote.tilt:
            buttons.append(
                ControllerButtonSpec(
                    "apex_tilt",
                    "Tilt",
                    lambda c: _apex(c)._preset("tilt"),
                    scheduler_resource="*",
                    invalidates_position=True,
                    card=CARD_PRESETS,
                    translation_key="apex_tilt",
                )
            )
        if self.remote.massage:
            buttons.append(
                ControllerButtonSpec(
                    "apex_massage_both",
                    "Step Head + Feet massage",
                    lambda c: _apex(c).massage_both_step(),
                    translation_key="apex_massage_both",
                    scheduler_resource="*",
                    card=CARD_MASSAGE,
                )
            )
            for key, label in (
                ("massage_duration", "Cycle massage duration"),
                ("massage_wave", "Wave massage"),
            ):
                buttons.append(
                    ControllerButtonSpec(
                        f"apex_{key}",
                        label,
                        lambda c, k=key: _apex(c).massage_step(k),
                        scheduler_resource="*",
                        card=CARD_MASSAGE,
                        translation_key=f"apex_{key}",
                    )
                )
        return tuple(buttons)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        firmware = ControllerStateSensorSpec("apex_firmware", "apex_firmware", FIRMWARE, "mdi:chip")
        massage = (
            (
                ControllerStateSensorSpec(
                    "apex_local_massage_end",
                    "apex_local_massage_end",
                    MASSAGE_END,
                    "mdi:timer",
                    card=CARD_MASSAGE,
                ),
            )
            if self.remote.massage
            else ()
        )
        return (firmware, *massage)

    @property
    def persisted_app_state_key(self) -> str:
        return self.profile.key

    @property
    def persisted_app_state(self) -> Mapping[str, Any]:
        return {"wakes": self._wakes, "massage_end": self._massage_end}

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        wakes = state.get("wakes", {})
        if not isinstance(wakes, dict):
            raise ValueError("Invalid saved wake-ups")
        validated: dict[str, dict[str, Any]] = {}
        for slot, wake in wakes.items():
            if not isinstance(slot, str) or not slot.isdecimal() or not isinstance(wake, dict):
                raise ValueError("Invalid saved wake-up")
            target = datetime.fromisoformat(wake["target"])
            if target.tzinfo is None:
                raise ValueError("Wake-up requires a timezone")
            wake_frames(
                self.index, int(slot), 0, **{k: v for k, v in wake.items() if k != "target"}
            )
            validated[slot] = dict(wake)
        end = state.get("massage_end")
        if end is not None:
            if not isinstance(end, str) or datetime.fromisoformat(end).tzinfo is None:
                raise ValueError("Invalid local massage end")
        self._wakes, self._massage_end = validated, end

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("Comfort Enhancement 3 BLE session changed")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("Bed is disconnected")

        def roles(service_uuid: str) -> dict[str, BleakGATTCharacteristic]:
            return {
                c.uuid.lower(): c
                for s in client.services
                if s.uuid.lower() == service_uuid
                for c in s.characteristics
            }

        standard = roles("00001801-0000-1000-8000-00805f9b34fb")
        info = roles("0000180a-0000-1000-8000-00805f9b34fb")
        bed = next((s for s in client.services if s.uuid.lower() == codec.SERVICE_UUID), None)
        exact = {c.uuid.lower(): c for c in bed.characteristics} if bed else {}
        write, notify = exact.get(codec.WRITE_UUID), exact.get(NOTIFY_UUID)
        if (
            write is None
            or "write" not in write.properties
            or notify is None
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError("Bed requires the exact writable 1525 and notifying 1625 roles")
        changed = standard.get(SERVICE_CHANGED)
        if changed and not {"notify", "indicate"}.intersection(changed.properties):
            changed = None
        self._link = _Link(
            client,
            write,
            notify,
            changed,
            tuple(
                c
                for uuid in (MODEL_UUID, FIRMWARE_UUID)
                if (c := info.get(uuid)) and "read" in c.properties
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        self._notify_callback = callback

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._link is link and self.client is link.client and link.client.is_connected:
                self.forward_raw_notification(sender.uuid, bytes(data))
                # Every app branch only logs. No ACK/notification is telemetry.

        for char in (link.changed, link.notify):
            if char is None or char in self._subscriptions:
                continue
            for attempt in range(2):
                try:
                    async with self._ble_lock:
                        self._live(link)
                        await link.client.start_notify(char, receive)
                    self._live(link)
                    self._subscriptions.append(char)
                    break
                except BleakError:
                    if attempt:
                        raise
                    await asyncio.sleep(1)

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        if link.info:
            await asyncio.sleep(1)
        for char in link.info:
            try:
                async with self._ble_lock:
                    self._live(link)
                    async with asyncio.timeout(5):
                        data = await link.client.read_gatt_char(char)
                self._live(link)
                if char.uuid.lower() == MODEL_UUID:
                    session.store_device_info(None, bytes(data).decode("latin1"))
                else:
                    self.forward_controller_state_updates(
                        FIRMWARE("V." + bytes(data).decode("latin1"))
                    )
            except BleakError, TimeoutError:
                _LOGGER.debug("Optional device information unavailable", exc_info=True)
        # MTU512 is an Android request, not a prerequisite or known negotiated
        # value. These 6/13-byte frames use HA/Bleak's normal transport sizing.
        from homeassistant.util import dt as dt_util

        for slot, wake in self._wakes.items():
            self._arm(f"wake:{slot}", datetime.fromisoformat(wake["target"]), link, wake)
        if self._massage_end and datetime.fromisoformat(self._massage_end) > dt_util.now():
            self._arm("massage", datetime.fromisoformat(self._massage_end), link)
        else:
            self._massage_end = None
        self._publish()

    def on_disconnect(self) -> None:
        self.forward_controller_state_updates(FIRMWARE(None))
        self._link = None
        self._subscriptions = []
        self._notify_callback = None
        for timer in self._timers.values():
            timer.cancel()
        self._timers.clear()
        for task in self._callbacks:
            task.cancel()
        self._callbacks.clear()

    async def stop_notify(self) -> None:
        link, subscriptions = self._link, tuple(self._subscriptions)
        self.on_disconnect()
        if link and self.client is link.client and link.client.is_connected:
            for char in subscriptions:
                async with self._ble_lock:
                    await link.client.stop_notify(char)

    async def _write(self, link: _Link, data: bytes, cancel: asyncio.Event) -> bool:
        async with self._ble_lock:
            self._live(link)
            if cancel.is_set():
                return False
            self._record_command_trace(
                link.write.uuid, data, response=True, characteristic=link.write
            )
            await link.client.write_gatt_char(link.write, data, response=True)
            return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for i in range(repeat_count):
            delay = max(0.0, started + i * repeat_delay_ms / 1000 - loop.time())
            if cancel.is_set() or i and await _pause(delay, cancel):
                return
            await self._write(link, command, cancel)

    async def _release(self, link: _Link) -> None:
        async def cleanup() -> None:
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for offset in (0.2, 0.3):
                await asyncio.sleep(max(0.0, started + offset - loop.time()))
                try:
                    await self._write(link, codec.STOP, asyncio.Event())
                except Exception as error:
                    failure = failure or error
            if failure:
                raise failure

        task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = True

    async def _send_stop(self) -> None:
        context = current_command_context()
        if context is not None and context.cleanup_stop_sent:
            return
        await self._release(self._live())

    async def _move_with_stop(self, command: bytes) -> None:
        link = self._live()
        try:
            await self.write_command(
                command, self.leased_hold_refreshes(100) or self._coordinator.motor_pulse_count
            )
        finally:
            await self._release(link)

    async def move(self, key: str) -> None:
        if key not in self.held_control_options:
            raise ValueError("Unsupported movement")
        await self._move_with_stop(self._key(key))

    async def _preset(self, name: str) -> None:
        if name not in self.profile.keys or name not in (
            "memory_1",
            "memory_2",
            "zero_g",
            "tv",
            "qs",
            "flat",
            "tilt",
        ):
            raise ValueError("Unsupported preset")
        link = self._live()
        if name == "flat":
            self._cancel_timer("massage")
            self._massage_end = None  # Source's stopMassageFlat has no massage-stop write.
            self._publish()
        try:
            await self.write_command(self._key(name))
        finally:
            await self._release(link)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Unsupported movement or hold duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        duration = self.leased_hold_ms(duration_ms)
        try:
            deadline = asyncio.timeout(duration / 1000)
            try:
                async with deadline:
                    await self.write_command(
                        self._key(control), self.timed_move_repeat_count(duration, 100)
                    )
                    await self._coordinator.cancel_command.wait()
            except TimeoutError:
                if not deadline.expired():
                    raise
        finally:
            # The captured link survives generic timed-move/card task boundaries.
            # Cleanup is awaited here; no mutable cache or delayed callbacks escape.
            await self._release(link)

    async def program_memory(self, memory_num: int) -> None:
        if type(memory_num) is not int or not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Unsupported memory slot")
        link, cancel = self._live(), self._coordinator.cancel_command
        completed = False
        loop = asyncio.get_running_loop()
        started, tick = loop.time(), 0
        try:
            for word, count in ((0x10000, 40), (self.profile.keys[f"memory_{memory_num}"], 3)):
                for _ in range(count):
                    tick += 1
                    if await _pause(max(0.0, started + tick / 10 - loop.time()), cancel):
                        return
                    await self._write(link, codec.frame(word), cancel)
            completed = True
        finally:
            if not completed or cancel.is_set():
                await self._release(link)

    async def lights_toggle(self) -> None:
        if not self.remote.light:
            raise ValueError("This remote has no UBL")
        link = self._live()
        try:
            await self.write_command(self._key("light"))
        finally:
            await self._release(link)

    async def massage_step(self, key: str, *, initial: bool = False) -> None:
        if not self.remote.massage or key not in MASSAGE_KEYS or key == "massage_stop":
            raise ValueError("Unsupported relative massage action")
        link, cancel = self._live(), self._coordinator.cancel_command
        await self._write(link, codec.STOP, cancel)
        bracket = key == "massage_duration" or initial and key != "massage_wave"
        if bracket and await _pause(0.1, cancel):
            return
        await self._write(link, codec.frame(MASSAGE_KEYS[key]), cancel)
        if bracket:
            await _pause(0.1, cancel)

    async def massage_head_toggle(self) -> None:
        await self.massage_step("massage_head")

    async def massage_foot_toggle(self) -> None:
        await self.massage_step("massage_foot")

    async def massage_both_step(self) -> None:
        if not self.remote.massage:
            raise ValueError("Main massage is unavailable")
        link, cancel = self._live(), self._coordinator.cancel_command
        await self._write(link, codec.frame(MASSAGE_KEYS["massage_head"]), cancel)
        if not await _pause(0.1, cancel):
            await self._write(link, codec.STOP, cancel)
            await self._write(link, codec.frame(MASSAGE_KEYS["massage_foot"]), cancel)

    async def massage_toggle(self) -> None:
        await self.massage_step("massage_wave")

    async def _massage_stop(self, link: _Link) -> None:
        async def cleanup() -> None:
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for i in range(2):
                if i:
                    await asyncio.sleep(max(0.0, started + 0.1 - loop.time()))
                for data in (codec.frame(0x400), codec.schedule_step(0, 0, 0, 0x400, 5)):
                    try:
                        await self._write(link, data, asyncio.Event())
                    except Exception as error:
                        failure = failure or error
            if failure:
                raise failure

        task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def massage_off(self) -> None:
        if not self.remote.massage:
            raise ValueError("Main massage is unavailable")
        self._cancel_timer("massage")
        self._massage_end = None
        await self._massage_stop(self._live())
        self._publish()

    async def start_massage(self, duration: int, intensity: int, kind: str) -> None:
        validate_massage(duration, intensity, kind)
        if not self.remote.massage:
            raise ValueError("Main massage is unavailable")
        link = self._live()
        completed = False
        try:
            for _ in range(duration // 10):
                await self.massage_step("massage_duration")
            for key in massage_axes(kind):
                for _ in range(1 if kind == "wave" else intensity):
                    await self.massage_step(key, initial=True)
            if self._coordinator.cancel_command.is_set():
                return
            from homeassistant.util import dt as dt_util

            end = dt_util.now() + timedelta(minutes=duration)
            self._cancel_timer("massage")
            self._massage_end = end.isoformat()
            self._arm("massage", end, link)
            self._publish()
            completed = True
        finally:
            if not completed or self._coordinator.cancel_command.is_set():
                await self._massage_stop(link)

    def validate_wakeup(self, slot: int, target: datetime, **effects: Any) -> tuple[bytes, ...]:
        from homeassistant.util import dt as dt_util

        if target.tzinfo is None:
            raise ValueError("Wake-up time requires a timezone")
        ticks = delay_ticks(target, dt_util.now())
        if ticks < 0:
            raise ValueError("The selected wake-up time has passed")
        return wake_frames(self.index, slot, ticks, **effects)

    async def set_wakeup(self, slot: int, target: datetime, **effects: Any) -> None:
        frames = self.validate_wakeup(slot, target, **effects)
        link, cancel = self._live(), self._coordinator.cancel_command
        if cancel.is_set():
            return
        # Editing removes the old bed program before rebuilding it.
        if not await self._write(link, codec.schedule_step(slot, 0, 0, 0, 0), cancel):
            return
        self._cancel_timer(f"wake:{slot}")
        self._wakes.pop(str(slot), None)
        if cancel.is_set():
            self._publish()
            return
        completed = False
        try:
            for frame in frames:
                if cancel.is_set():
                    return
                await self._write(link, frame, cancel)
            if cancel.is_set():
                return
            self._wakes[str(slot)] = {"target": target.isoformat(), **effects}
            self._arm(f"wake:{slot}", target, link, self._wakes[str(slot)], due_now=True)
            completed = True
        finally:
            if not completed or cancel.is_set():
                await self._write(link, codec.schedule_step(slot, 0, 0, 0, 0), asyncio.Event())
            self._publish()

    async def delete_wakeup(self, slot: int) -> None:
        frame = codec.schedule_step(slot, 0, 0, 0, 0)
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        if not await self._write(self._live(), frame, cancel):
            return
        self._cancel_timer(f"wake:{slot}")
        self._wakes.pop(str(slot), None)
        self._publish()

    def _cancel_timer(self, key: str) -> None:
        if timer := self._timers.pop(key, None):
            timer.cancel()

    def _arm(
        self,
        key: str,
        target: datetime,
        link: _Link,
        wake: Mapping[str, Any] | None = None,
        *,
        due_now: bool = False,
    ) -> None:
        from homeassistant.util import dt as dt_util

        remaining = target.timestamp() - dt_util.now().timestamp()
        if remaining < 0 and not due_now:
            return
        self._cancel_timer(key)
        handle: asyncio.TimerHandle

        async def due() -> None:
            def current() -> bool:
                return self._link is link and self._timers.get(key) is handle

            async def effect(controller: BedController) -> None:
                if not current() or controller is not self:
                    return
                # This is the retained bed effect of the app's due timer, not
                # its phone reminders/music. It cannot cross session or edit.
                await self._massage_stop(link)
                self._timers.pop(key, None)
                self._cancel_timer("massage")
                self._massage_end = None
                if wake is not None and wake.get("massage"):
                    end = target + timedelta(minutes=wake.get("duration", 10))
                    if end > dt_util.now():
                        self._massage_end = end.isoformat()
                        self._arm("massage", end, link)
                self._publish()

            if current():
                await self._coordinator.async_execute_controller_query(
                    effect, cancel_running=False, run_if=current
                )

        def fired() -> None:
            task = self._coordinator.hass.async_create_task(due())
            self._callbacks.add(task)
            task.add_done_callback(self._callbacks.discard)

        handle = asyncio.get_running_loop().call_later(max(0.0, remaining), fired)
        self._timers[key] = handle

    def _publish(self) -> None:
        self.forward_controller_state_updates(MASSAGE_END(self._massage_end))


def _apex(controller: BedController) -> ComfortEnhancement3Controller:
    if not isinstance(controller, ComfortEnhancement3Controller):
        raise TypeError("This action requires Comfort Enhancement 3")
    return controller


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


async def build_controller(ctx: BuildContext) -> BedController:
    from ...const import CONF_PROTOCOL_VARIANT
    from ...profiles.comfort_enhancement3 import REMOTE_CODE

    variant = ctx.data.get(CONF_PROTOCOL_VARIANT) if ctx.variant in (None, "auto") else ctx.variant
    index = resolve(variant, ctx.data.get(REMOTE_CODE, ""))
    return ComfortEnhancement3Controller(ctx.coordinator, index)
