"""Hestia's gestures and local choices, fenced to one physical BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import time
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY
from ...command_scheduler import current_command_context
from ...const import KEESON_BASE_NOTIFY_CHAR_UUID, KEESON_BASE_WRITE_CHAR_UUID
from ...errors import BedNotConnectedError
from ...profiles import hestia as app
from ...profiles.keeson import KeesonProfile, encode
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from ..base import BedController, ProfileExecution, require_controller
from ..cancellation import cancellable, settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .state import ALARM, CHOICE, MASSAGE

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


def _action(control: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await require_controller(controller, HestiaController).move(control)

    return run


def _select(key: str) -> Callable[[BedController, str], Awaitable[None]]:
    async def run(controller: BedController, value: str) -> None:
        require_controller(controller, HestiaController).choose(key, value)

    return run


class HestiaController(ProfileExecution[KeesonProfile], BedController):
    """Use exact discovered roles, immutable buffers and cancellation-safe release."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = app.PROFILE
        self._link: Link | None = None
        self._subscription: object | None = None
        self._retired = False
        self._choices = dict(app.DEFAULTS)
        self._last_preset: int | None = None
        self._preset_may_run = False
        self._lamp: bool | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return KEESON_BASE_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

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
            raise BedNotConnectedError
        return link

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.controller is self
        )

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        write = notify = None
        # The app keeps the last matching role, regardless of service UUID.
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.lower() == KEESON_BASE_WRITE_CHAR_UUID:
                    write = char
                elif char.uuid.lower() == KEESON_BASE_NOTIFY_CHAR_UUID:
                    notify = char
        if write is None or notify is None:
            raise BleakError("Hestia requires FFE9 write and FFE4 notification characteristics")
        if not {"write", "write-without-response"}.intersection(write.properties):
            raise BleakError("Hestia FFE9 has no writable property")
        if not {"notify", "indicate"}.intersection(notify.properties):
            raise BleakError("Hestia FFE4 has no subscription property")
        self._link = Link(client, write, notify, "write-without-response" not in write.properties)

    async def async_validate_linked_readiness(self) -> None:
        self._live()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True  # No Device Information reads exist in this app.

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscription is not None:
            return
        token = self._subscription = object()

        def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if data and self._subscription is token and self._current(link):
                self.forward_raw_notification(link.notify.uuid, bytes(data))

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
        except BaseException:
            if self._subscription is token:
                self._subscription = None
            raise
        self._publish_choices()

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscription is not None
        self._subscription = None
        if subscribed and link is not None and self._current(link):
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._subscription = None
        self._last_preset = None
        self._preset_may_run = False
        self._lamp = None
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None), MASSAGE(None), ALARM(None), MASSAGE_TIMER_MINUTES(None)
        )

    async def _send(
        self,
        link: Link,
        frame: bytes,
        cancel: asyncio.Event,
        on_start: Callable[[], None] | None = None,
    ) -> None:
        def admit() -> None:
            self._live(link)
            if on_start is not None:
                on_start()

        written = False

        def sent() -> None:
            nonlocal written
            written = True

        await self._write_gatt_with_retry(
            link.write.uuid,
            frame,
            cancel_event=cancel,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            before_write=admit,
            on_write=sent,
            settle_write=True,
            write_timeout=5,
        )
        self._live(link)
        if not written or cancel.is_set():
            raise asyncio.CancelledError

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            await self._send(link, command, cancel)
            if index + 1 < repeat_count:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)

    async def _keys(self, *words: int, on_start: Callable[[], None] | None = None) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        for word in words:
            await cancellable(asyncio.sleep(self.profile.tap_wait_ms / 1000), cancel)
            await self._send(link, encode(self.profile, word), cancel, on_start)

    async def _release(self, link: Link, *, preset: bool = False) -> None:
        async def cleanup() -> None:
            await asyncio.sleep(0.1)
            if not self._current(link):
                return
            await self._send(
                link, encode(self.profile, app.PRESET_CANCEL if preset else 0), asyncio.Event()
            )
            context = current_command_context()
            if context is not None:
                context.cleanup_stop_sent = True

        await settled(cleanup())

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{axis}_{direction}" for axis in app.AXES for direction in ("up", "down"))

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        word = app.AXES[axis][direction == "down"]
        link, cancel = self._live(), self._coordinator.cancel_command
        deadline = asyncio.get_running_loop().time() + self.leased_hold_ms(duration_ms) / 1000
        try:
            while not cancel.is_set() and deadline - asyncio.get_running_loop().time() > 0.000001:
                await self._send(link, encode(self.profile, word), cancel)
                self._preset_may_run = False
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining > 0:
                    await cancellable(asyncio.sleep(min(0.1, remaining)), cancel)
        finally:
            await self._release(link)

    async def move(self, control: str) -> None:
        count, delay = self.motor_pulse_settings()
        await self.hold_control(control, count * delay)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=_action(f"{axis}_up"),
                close_fn=_action(f"{axis}_down"),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis in app.AXES
        )

    async def move_head_up(self) -> None:
        await self.move("back_up")

    async def move_head_down(self) -> None:
        await self.move("back_down")

    async def move_legs_up(self) -> None:
        await self.move("legs_up")

    async def move_legs_down(self) -> None:
        await self.move("legs_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        link = self._live()
        preset = self._preset_may_run
        await self._release(link, preset=preset)
        if preset:
            self._last_preset = None
            self._preset_may_run = False

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def _preset(self, word: int) -> None:
        if self._last_preset == word:
            await self.cancel_preset()
            return

        def started() -> None:
            self._last_preset = None
            self._preset_may_run = True

        await self._keys(word, on_start=started)
        self._last_preset = word

    async def cancel_preset(self) -> None:
        await self._release(self._live(), preset=True)
        self._last_preset = None
        self._preset_may_run = False

    async def preset_flat(self) -> None:
        await self._preset(self.profile.presets["flat"])

    async def preset_zero_g(self) -> None:
        await self._preset(self.profile.presets["zero_g"])

    async def preset_anti_snore(self) -> None:
        await self._preset(self.profile.presets["anti_snore"])

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._preset(self.profile.memory[memory_num])

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        assert self.profile.memory_save is not None
        await self._keys(self.profile.memory_save.words[memory_num])

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def _light(self, on: bool) -> None:
        self._live()
        self._lamp = None
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))
        await self._keys(app.LIGHTS[on])
        self._lamp = on
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(on))

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    async def lights_toggle(self) -> None:
        await self._light(not self._lamp)

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    async def massage_start(self) -> None:
        self._live()
        wave, intensity = (int(self._choices[key]) for key in ("wave", "intensity"))
        self.forward_controller_state_updates(MASSAGE(None))
        await self._keys(app.WAVE + wave, app.INTENSITY + intensity)
        self.forward_controller_state_updates(MASSAGE(intensity > 0))

    async def massage_off(self) -> None:
        self._live()
        self.forward_controller_state_updates(MASSAGE(None))
        await self._keys(app.INTENSITY)
        self.forward_controller_state_updates(MASSAGE(False))

    @property
    def supports_massage_off_control(self) -> bool:
        return False  # The native switch owns on/off.

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return list(app.TIMERS)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in app.TIMERS:
            raise ValueError("Choose 10, 20 or 30 minutes")
        self._live()
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(None))
        await self._keys(app.TIMERS[minutes])
        self._choices["timer"] = str(minutes)
        self._publish_choices()
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(minutes))

    def choose(self, key: str, value: str) -> None:
        if self._retired:
            raise BedNotConnectedError
        if key not in app.CHOICES or value not in app.CHOICES[key]:
            raise ValueError("Invalid Hestia local choice")
        self._choices[key] = value
        self._publish_choices()

    def _enhancement(self, on: bool) -> None:
        if self._retired:
            raise BedNotConnectedError
        self._choices["enhancement"] = "on" if on else "off"
        self._publish_choices()

    def _publish_choices(self) -> None:
        self.forward_controller_state_updates(
            *(CHOICE[key](value) for key, value in self._choices.items())
        )

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    def on_app_state_replaced(self) -> None:
        self._retired = True

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return dict(self._choices)

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        choices = dict(app.DEFAULTS)
        for key, value in state.items():
            allowed = ("on", "off") if key == "enhancement" else app.CHOICES.get(key, ())
            if not isinstance(value, str) or value not in allowed:
                raise ValueError("Invalid Hestia saved choice")
            choices[key] = value
        self._choices = choices
        self._publish_choices()

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=("none", "memory_1", "memory_2"),
            massage=True,
            massage_intensities=3,
            massage_durations=(10, 20, 30),
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if (
            alarm.wake_action not in app.CHOICES["memory"]
            or type(alarm.hour) is not int
            or not 0 <= alarm.hour < 24
            or type(alarm.minute) is not int
            or not 0 <= alarm.minute < 60
            or type(alarm.massage_intensity) is not int
            or not 0 <= alarm.massage_intensity <= 3
            or alarm.massage_duration is not None
            and alarm.massage_duration not in app.TIMERS
        ):
            raise ValueError("Invalid Hestia alarm settings")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, cancel = self._live(), self._coordinator.cancel_command
        frame = app.alarm(
            dt_util.now(),
            time(alarm.hour, alarm.minute) if alarm.enabled else None,
            enhancement=alarm.massage,
            intensity=alarm.massage_intensity,
            wave=int(self._choices["wave"]),
            timer=alarm.massage_duration or int(self._choices["timer"]),
            memory=alarm.wake_action,
        )
        self.forward_controller_state_updates(ALARM(None))
        await self._send(link, frame, cancel)
        self.forward_controller_state_updates(ALARM(alarm.enabled))

    async def _native_alarm(self, enabled: bool) -> None:
        await self.configure_alarm(
            AlarmRequest(
                enabled=enabled,
                hour=int(self._choices["hour"]),
                minute=int(self._choices["minute"]),
                wake_action=self._choices["memory"],
                massage=self._choices["enhancement"] == "on",
                massage_intensity=int(self._choices["intensity"]),
                massage_duration=int(self._choices["timer"]),
                reference_time=dt_util.now(),
            )
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return tuple(
            ControllerSelectSpec(
                key=f"hestia_{key}",
                translation_key=f"hestia_{key}",
                state_key=CHOICE[key],
                options=app.CHOICES[key],
                select_fn=_select(key),
                local_select_fn=lambda value, key=key: self.choose(key, value),
                card=CARD_MASSAGE if key in ("wave", "intensity") else CARD_UTILITY,
            )
            for key in ("wave", "intensity", "hour", "minute", "memory")
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        async def massage(ctrl: BedController, on: bool) -> None:
            bed = require_controller(ctrl, HestiaController)
            await (bed.massage_start() if on else bed.massage_off())

        async def alarm(ctrl: BedController, on: bool) -> None:
            await require_controller(ctrl, HestiaController)._native_alarm(on)

        async def enhancement(ctrl: BedController, on: bool) -> None:
            require_controller(ctrl, HestiaController)._enhancement(on)

        return (
            ControllerSwitchSpec(
                "hestia_massage",
                "hestia_massage",
                massage,
                state_key=MASSAGE,
                assumed_state=True,
                card=CARD_MASSAGE,
            ),
            ControllerSwitchSpec(
                "hestia_alarm",
                "hestia_alarm",
                alarm,
                state_key=ALARM,
                assumed_state=True,
                card=CARD_UTILITY,
            ),
            ControllerSwitchSpec(
                "hestia_enhancement",
                "hestia_enhancement",
                enhancement,
                state_key=CHOICE["enhancement"],
                on_value="on",
                local_set_fn=self._enhancement,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        async def cancel(ctrl: BedController) -> None:
            await require_controller(ctrl, HestiaController).cancel_preset()

        return (
            ControllerButtonSpec(
                "hestia_cancel_preset",
                "Cancel preset",
                cancel,
                translation_key="hestia_cancel_preset",
                icon="mdi:stop",
                card=CARD_PRESETS,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "com.ore.yorkfeng.hestiamotion 1.2 (3)",
            "hardware": "UNVERIFIED",
            "feedback": "Raw FFE4 only; entity states are local choices or last-sent intent",
            "transport": "FFE9/FFE4 across any service; live properties choose write mode",
        }
