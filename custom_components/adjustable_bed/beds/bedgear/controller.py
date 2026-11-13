"""Bedgear's direct BED session and source-specific held gestures."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from math import isfinite
from time import monotonic
from typing import TYPE_CHECKING

from ...card import CARD_HIDDEN, CARD_LIGHT_TOGGLE, CARD_MASSAGE
from ...codec import motomotion as codec
from ...command_scheduler import current_command_context
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...profiles.bedgear import BedgearProfile, Control
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .protocol import Receiver, color_parameters, token_fields

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator

RGB = StateKey[str | None]("bedgear_rgb")
TIMER = StateKey[int | None]("bedgear_light_minutes")
ALARM = StateKey[str | None]("bedgear_alarm")
STRENGTH = StateKey[int | None]("bedgear_alarm_strength")
SYNC = StateKey[int | None]("bedgear_sync_type")
BIND = StateKey[str | None]("bedgear_sync_state")


@dataclass(frozen=True, eq=False)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: tuple[BleakGATTCharacteristic, ...]


class _HoldElapsed(Exception):
    """A queued finite hold has expired before transmission."""


def select_transport(client: BleakClient) -> Link:
    chars = tuple(
        char
        for service in client.services
        if "FFE0" in service.uuid.upper()
        for char in service.characteristics
        if "FFE1" in char.uuid.upper()
    )
    if not chars:
        raise ValueError(
            "Bedgear needs a service containing FFE0 and characteristic containing FFE1"
        )
    return Link(client, chars[-1], chars)


async def press(controller: BedController, *, key: str) -> None:
    await require_controller(controller, BedgearController).press(key)


class BedgearController(ProfileExecution[BedgearProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, name: str) -> None:
        super().__init__(coordinator)
        self.profile = BedgearProfile(name)
        self._address = coordinator.address
        self._link: Link | None = None
        self._receiver = Receiver()
        self._rgb: tuple[int, int, int] | None = None
        self._timer: int | None = None
        self._alarm: tuple[str, str, str] | None = None
        self._bind: tuple[bool, bool] | None = None
        self._sync: int | None = None
        self._gesture_up = False
        self._cleanup_context: CommandContext | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else "0000ffe1-0000-1000-8000-00805f9b34fb"

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return True  # Gesture cleanup owns release; do not add a generic STOP to presets.

    @property
    def supports_memory_presets(self) -> bool:
        return self.profile.memory_slots > 0

    @property
    def supports_held_memory_recall(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_preset_flat(self) -> bool:
        return "flat" in dict(self.profile.presets)

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in dict(self.profile.presets)

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in dict(self.profile.presets)

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in dict(self.profile.presets)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = []
        if self.profile.rgb:
            specs.append(
                ControllerStateSensorSpec("bedgear_rgb", "bedgear_rgb", RGB, "mdi:palette")
            )
        if self.profile.timer:
            specs.append(
                ControllerStateSensorSpec(
                    "bedgear_light_minutes", "bedgear_light_minutes", TIMER, "mdi:timer", "min"
                )
            )
        if self.profile.alarm:
            specs.extend(
                (
                    ControllerStateSensorSpec("bedgear_alarm", "bedgear_alarm", ALARM, "mdi:alarm"),
                    ControllerStateSensorSpec(
                        "bedgear_alarm_strength", "bedgear_alarm_strength", STRENGTH, "mdi:vibrate"
                    ),
                )
            )
        specs.extend(
            (
                ControllerStateSensorSpec(
                    "bedgear_sync_type", "bedgear_sync_type", SYNC, "mdi:sync"
                ),
                ControllerStateSensorSpec(
                    "bedgear_sync_state", "bedgear_sync_state", BIND, "mdi:link"
                ),
            )
        )
        return tuple(specs)

    @property
    def _observed_strength(self) -> int | None:
        raw = self._alarm[2] if self._alarm else ""
        if raw.isascii() and raw.isdecimal() and len(raw) <= 10:
            value = int(raw)
            if value in (0, 1, 2):
                return value
        return None

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            RGB(",".join(str(channel) for channel in self._rgb) if self._rgb is not None else None),
            TIMER(self._timer),
            ALARM(":".join(self._alarm[:2]) if self._alarm else None),
            STRENGTH(self._observed_strength),
            SYNC(self._sync),
            BIND(
                None
                if self._bind is None
                else "unavailable"
                if not self._bind[0]
                else "active"
                if self._bind[1]
                else "inactive"
            ),
        )

    def _current(self) -> Link:
        link = self._link
        if (
            link is None
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address != self._address
            or self._coordinator.controller is not self
        ):
            raise ConnectionError("Bedgear BLE session changed")
        return link

    def _notification(self, link: Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if (
            self._link is not link
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address != self._address
            or self._coordinator.controller is not self
        ):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        for text in self._receiver.feed(bytes(data)):
            fields = token_fields(text)
            rgb_timer = fields.get("rgb_timer")
            if isinstance(rgb_timer, list):
                values = [
                    int(v)
                    if isinstance(v, str) and v.isascii() and v.isdecimal() and len(v) <= 10
                    else None
                    for v in rgb_timer
                ]
                r, g, b = values[:3]
                self._rgb = (
                    (min(255, int(r * 2.125)), min(255, int(g * 2.125)), min(255, int(b * 2.125)))
                    if r is not None and g is not None and b is not None
                    else None
                )
                self._timer = min(65535, values[3]) if values[3] is not None else None
            alarm = fields.get("alarm")
            if isinstance(alarm, list) and all(isinstance(v, str) for v in alarm):
                self._alarm = (alarm[0], alarm[1], alarm[2])
            bind = fields.get("bind")
            if isinstance(bind, dict):
                self._bind = (bind["available"] is True, bind["active"] is True)
                value = fields.get("sync_type")
                self._sync = value if isinstance(value, int) else None
            self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Bedgear is disconnected")
        link = select_transport(client)
        self._link = link
        self._receiver = Receiver()
        self._cleanup_context = None
        self._rgb = None
        self._timer = None
        self._alarm = None
        self._bind = None
        self._sync = None
        self._publish()
        started = []
        try:
            for char in link.notify:
                await client.start_notify(char, partial(self._notification, link))
                started.append(char)
                if self._current() is not link:
                    raise ConnectionError("Bedgear session changed during subscription")
        except BaseException:
            self._link = None
            for char in started:
                if client.is_connected:
                    await client.stop_notify(char)
            raise

    async def stop_notify(self) -> None:
        link, self._link = self._link, None
        self._receiver = Receiver()
        self._cleanup_context = None
        self._rgb = None
        self._timer = None
        self._alarm = None
        self._bind = None
        self._sync = None
        self._publish()
        if link and link.client.is_connected:
            for char in link.notify:
                await link.client.stop_notify(char)

    async def _send(
        self,
        command: bytes | None,
        link: Link,
        cancel: asyncio.Event,
        *,
        deadline: float | None = None,
    ) -> None:
        if command is None or cancel.is_set():
            return

        def before_write() -> None:
            self._check_link(link)
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                raise _HoldElapsed

        await self._write_gatt_with_retry(
            link.write.uuid,
            command,
            cancel_event=cancel,
            response=False,
            characteristic=link.write,
            expected_client=link.client,
            before_write=before_write,
        )

    def _check_link(self, link: Link) -> None:
        if self._current() is not link:
            raise ConnectionError("Bedgear command belongs to an old session")

    def _letter(self, letter: str) -> bytes | None:
        return codec.short_transport("$" + letter, wrapped=self.profile.wrapped)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link, cancel = self._current(), cancel_event or self._coordinator.cancel_command
        for tick in range(repeat_count):
            if tick and not await self._wait(repeat_delay_ms / 1000, cancel):
                break
            await self._send(command, link, cancel)

    async def _wait(self, seconds: float, cancel: asyncio.Event) -> bool:
        if cancel.is_set():
            return False
        if seconds <= 0:
            return True
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
            return False
        except TimeoutError:
            return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple("bedgear_" + control.key for control in self.profile.controls if control.held)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError("Choose an available Bedgear control and 1..60000 ms duration")

    def on_gesture_release(self) -> None:
        self._gesture_up = True

    async def _stop(self, link: Link) -> None:
        started = monotonic()
        for tick in range(self.profile.stop_count):
            if tick:
                await asyncio.sleep(
                    max(0, started + tick * self.profile.stop_interval_ms / 1000 - monotonic())
                )
            await self._send(self._letter("b"), link, asyncio.Event())

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        binding = next(c for c in self.profile.controls if "bedgear_" + c.key == control)
        link, cancel = self._current(), self._coordinator.cancel_command
        count, self._gesture_up = 0, False
        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = start + duration_ms / 1000
        interval = self.profile.refresh_ms
        leased = self.leased_hold_refreshes(interval) is not None
        # Finite HA windows start with a pulse, rather than making their only
        # pulse race the deadline. Native leased gestures keep the first tick.
        ticks = (
            range(1, duration_ms // interval + 1)
            if leased
            else range((duration_ms + interval - 1) // interval)
        )
        try:
            for tick in ticks:
                if not await self._wait(
                    max(0, start + tick * interval / 1000 - loop.time()), cancel
                ):
                    break
                if loop.time() >= deadline:
                    break
                try:
                    await self._send(
                        self._letter(binding.letter),
                        link,
                        cancel,
                        deadline=None if leased else deadline,
                    )
                except _HoldElapsed:
                    break
                if not cancel.is_set():
                    count += 1
            if not cancel.is_set():
                await self._wait(max(0, start + duration_ms / 1000 - loop.time()), cancel)
        finally:
            # Cleanup is pinned to the captured link and uses a fresh event.
            # Cancellation without an up gesture never sends the short-up fallback.
            if (
                self._link is link
                and self.client is link.client
                and link.client.is_connected
                and self._coordinator.address == self._address
                and self._coordinator.controller is self
            ):
                up = not cancel.is_set() or self._gesture_up
                await self._release(binding, link, count, up=up)

    async def _release(self, binding: Control, link: Link, count: int, *, up: bool) -> None:
        if binding.release == "none" or (binding.release == "fallback" and (count >= 5 or not up)):
            return

        async def release() -> None:
            if binding.release == "stop":
                await self._stop(link)
            else:
                started = monotonic()
                for tick in range(self.profile.fallback_count):
                    if tick:
                        await asyncio.sleep(max(0, started + tick * 0.1 - monotonic()))
                    await self._send(self._letter(binding.letter), link, asyncio.Event())

        # Drain the complete source release before freeing the command lane,
        # even if STOP also cancels the coroutine while it is cleaning up.
        task = asyncio.create_task(release())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if binding.release == "stop" and (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True
            self._cleanup_context = context
        if interrupted:
            raise asyncio.CancelledError

    async def press(self, key: str) -> None:
        control = next((c for c in self.profile.controls if c.key == key), None)
        if control is None:
            raise NotImplementedError("Unavailable Bedgear control")
        if control.held:
            await self.hold_control("bedgear_" + key, self.leased_hold_ms(1000))
        else:
            await self._send(
                self._letter(control.letter), self._current(), self._coordinator.cancel_command
            )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                {"foot": "feet", "actuator": "head", "combined": "both"}.get(axis, axis),
                {
                    "foot": "feet",
                    "actuator": "bedgear_actuator",
                    "combined": "bedgear_combined",
                }.get(axis, axis),
                partial(press, key=axis + "_up"),
                partial(press, key=axis + "_down"),
                lambda ctrl: ctrl.stop_all(),
                scheduler_resource="bedgear",
                hold=ControllerMotorHoldSpec(
                    "bedgear_" + axis + "_up",
                    "bedgear_" + axis + "_down",
                    stop_scope="side",
                    press_is_native=True,
                    release_button_key="bedgear_release",
                ),
            )
            for axis, _up, _down in self.profile.axes
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                "bedgear_" + c.key,
                c.key.replace("_", " ").capitalize(),
                partial(press, key=c.key),
                translation_key="bedgear_massage"
                if c.key.startswith("massage_")
                else "bedgear_light_toggle",
                translation_placeholders={"action": c.key.replace("_", " ").capitalize()},
                hold=ControllerHoldSpec("bedgear_" + c.key, release_button_key="bedgear_release")
                if c.held
                else None,
                card=CARD_MASSAGE if c.key.startswith("massage_") else CARD_LIGHT_TOGGLE,
            )
            for c in self.profile.controls
            if c.key.startswith(("massage_", "light_"))
        ) + (
            ControllerButtonSpec(
                "bedgear_release",
                "Release control",
                lambda ctrl: ctrl.stop_all(),
                translation_key="bedgear_release",
                release_only=True,
                card=CARD_HIDDEN,
            ),
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = key.removeprefix("preset_") if key.startswith("preset_memory_") else key
        if "bedgear_" + control in self.held_control_options:
            return ControllerHoldSpec("bedgear_" + control, release_button_key="bedgear_release")
        return None

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        context = current_command_context()
        if context is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent and preempted is self._cleanup_context:
                    preempted.cleanup_stop_sent = False
                    self._cleanup_context = None
                    return
        await self._stop(self._current())

    async def _move(self, axis: str, up: bool) -> None:
        await self.press(axis + ("_up" if up else "_down"))

    async def move_head_up(self) -> None:
        await self._move(
            "actuator" if self.profile.panel in ("PanelE", "PanelFive") else "head", True
        )

    async def move_head_down(self) -> None:
        await self._move(
            "actuator" if self.profile.panel in ("PanelE", "PanelFive") else "head", False
        )

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move("foot", True)

    async def move_legs_down(self) -> None:
        await self._move("foot", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self.press("preset_flat")

    async def preset_zero_g(self) -> None:
        await self.press("preset_zero_g")

    async def preset_tv(self) -> None:
        await self.press("preset_tv")

    async def preset_anti_snore(self) -> None:
        await self.press("preset_anti_snore")

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def move_neck_up(self) -> None:
        await self._move("neck", True)

    async def move_neck_down(self) -> None:
        await self._move("neck", False)

    async def move_neck_stop(self) -> None:
        await self.stop_all()

    async def move_tilt_up(self) -> None:
        await self._move("tilt", True)

    async def move_tilt_down(self) -> None:
        await self._move("tilt", False)

    async def move_tilt_stop(self) -> None:
        await self.stop_all()

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        await self.hold_control(f"bedgear_memory_{slot}", hold_ms)

    async def preset_memory(self, memory_num: int) -> None:
        await self.press(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise NotImplementedError("Unavailable Bedgear memory slot")
        await self._send(
            self._letter("Za"[memory_num - 1]), self._current(), self._coordinator.cancel_command
        )

    async def configure(self, request: Request) -> None:
        self.validate_request(request)
        link, cancel = self._current(), self._coordinator.cancel_command
        op = request.operation
        if op == "rgb":
            assert request.rgb is not None
            for command, parameter in zip(
                (315, 316, 317), color_parameters(request.rgb, request.brightness), strict=True
            ):
                await self._send(self._letter("z"), link, cancel)
                if not await self._wait(0 if self.profile.wrapped else 0.1, cancel):
                    return
                await self._send(codec.ascii_command(command, parameter), link, cancel)
                if not await self._wait(0.1, cancel):
                    return
        elif op in ("light_timer", "alarm"):
            if op == "light_timer":
                frame = codec.ascii_command(319, request.minutes)
            else:
                hour, minute = (
                    request.time.split(":")
                    if request.time is not None
                    else self._alarm[:2]
                    if self._alarm
                    else ("", "")
                )
                strength = (
                    request.strength if request.strength is not None else self._observed_strength
                )
                assert strength is not None
                frame = codec.decimal_fields(
                    hour + minute + "00", ("0017", "0118", "0219")[strength]
                )
            await self._send(self._letter("z"), link, cancel)
            if await self._wait(0.05, cancel):
                await self._send(frame, link, cancel)
        elif op == "sync_mode":
            await self._send(codec.ascii_command(33049, int(request.wired)), link, cancel)
        elif op == "toggle_sync":
            assert self._bind is not None
            await self._send(codec.ascii_command(15 if self._bind[1] else 12), link, cancel)
        elif op == "save_snore":
            await self._send(self._letter("W"), link, cancel)
        elif op == "save_memory":
            await self.program_memory(request.slot)
            if request.recall_on_release:
                await self._send(self._letter("UV"[request.slot - 1]), link, cancel)

    def validate_request(self, request: Request) -> None:
        op = request.operation
        allowed = {
            "rgb": self.profile.rgb,
            "light_timer": self.profile.timer,
            "alarm": self.profile.alarm,
            "sync_mode": self.profile.sync and request.confirm,
            "toggle_sync": self._bind is not None and self._bind[0],
            "save_snore": self.profile.panel == "PanelE",
            "save_memory": 1 <= request.slot <= self.memory_slot_count,
        }
        if op == "save_snore" and request.recall_on_release:
            raise ValueError("Panel E snore save has no release recall; use the held snore preset")
        if op == "rgb" and request.rgb is None:
            raise ValueError("RGB needs three color channels")
        if op == "alarm" and request.strength is None and self._observed_strength is None:
            raise ValueError("Set an alarm strength or receive its current strength first")
        if not allowed.get(op, False):
            raise ValueError("Bedgear control unavailable, unconfirmed, or received state missing")
        if (
            op == "alarm"
            and request.time is None
            and (
                self._alarm is None
                or any(not x.isascii() or not x.isdecimal() for x in self._alarm[:2])
            )
        ):
            raise ValueError("Set an alarm time or receive its current time first")


@dataclass(frozen=True, kw_only=True)
class Request:
    operation: str
    rgb: tuple[int, int, int] | None = None
    brightness: float = 1
    minutes: int = 0
    time: str | None = None
    strength: int | None = None
    wired: bool = False
    confirm: bool = False
    slot: int = 1
    recall_on_release: bool = False

    def __post_init__(self) -> None:
        if not isfinite(self.brightness) or not 0 <= self.brightness <= 1:
            raise ValueError("Brightness must be from 0 to 1")
        if self.rgb is not None and (
            len(self.rgb) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in self.rgb)
        ):
            raise ValueError("RGB needs three channels from 0 to 255")
        if type(self.minutes) is not int or not 0 <= self.minutes <= 1439:
            raise ValueError("Light timer must be from 0 to 1439 minutes")
        if self.strength is not None and (
            type(self.strength) is not int or self.strength not in (0, 1, 2)
        ):
            raise ValueError("Alarm strength must be 0, 1 or 2")
        if (
            self.time is not None
            and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", self.time) is None
        ):
            raise ValueError("Alarm time must be HH:MM")
        if type(self.slot) is not int or self.slot not in (1, 2):
            raise ValueError("Choose memory slot 1 or 2")


async def build_controller(ctx: BuildContext) -> BedgearController:
    stored = ctx.data.get(CONF_BLE_DEVICE_NAME)
    return BedgearController(
        ctx.coordinator, name=stored if isinstance(stored, str) else ctx.live_device_name or ""
    )
