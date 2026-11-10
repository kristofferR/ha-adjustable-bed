"""OkinComfortBed II: app gates, session, timed cleanup and local alarm over Keeson."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, Final, cast

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_UTILITY
from ...codec import keeson as codec
from ...const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...profiles import jalon as app
from ...profiles import keeson as profiles
from ..builder import BuildContext
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec, MotorControlSpec
from .controller import KeesonController, _wait_unless_cancelled
from .jalon_state import AlarmStatus, MassageStatus, parse_notification

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

TIMER: Final = StateKey[int | None]("jalon_massage_timer")
WAVE: Final = StateKey[int | None]("jalon_massage_wave")
HEAD: Final = StateKey[int | None]("jalon_head_strength")
FOOT: Final = StateKey[int | None]("jalon_foot_strength")
ALARM: Final = StateKey[str | None]("jalon_alarm")
WEEK: Final = StateKey[int | None]("jalon_alarm_week")
WAKE: Final = StateKey[int | None]("jalon_alarm_type")
HOUR: Final = StateKey[int | None]("jalon_alarm_hour")
MINUTE: Final = StateKey[int | None]("jalon_alarm_minute")
FIRST: Final = StateKey[int | None]("jalon_alarm_first")
STATE_KEYS: Final = (TIMER, WAVE, HEAD, FOOT, ALARM, WEEK, WAKE, HOUR, MINUTE, FIRST)


class JalonController(KeesonController):
    """Extend the shared word controller with this app's proven behavior only."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, protocol: str, layout: str
    ) -> None:
        if protocol not in app.PROFILES or layout not in app.LAYOUTS:
            raise ValueError("Choose a supported OkinComfortBed II protocol and layout")
        super().__init__(coordinator, variant=app.PROFILES[protocol].key)
        self.layout = layout
        self._timer: int | None = None
        self._notifying = False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # The layout is independent of wire protocol, including a lumbar-only
        # third actuator. Give the neck its app label, not Keeson's tilt label.
        from dataclasses import replace

        specs = super().motor_control_specs
        return tuple(
            replace(
                spec,
                translation_key="neck" if spec.key == "tilt" else spec.translation_key,
                scheduler_resource="*",
            )
            for spec in specs
            if spec.key in app.LAYOUTS[self.layout]
        )

    @property
    def has_tilt_support(self) -> bool:
        return "tilt" in app.LAYOUTS[self.layout]

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in app.LAYOUTS[self.layout]

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def _role(self, *, notify: bool = False) -> BleakGATTCharacteristic:
        client = self.client
        transport = codec.TRANSPORTS[self.profile.notify if notify else self.profile.transport]
        service_uuid = (
            "0000ffe0-0000-1000-8000-00805f9b34fb"
            if notify and self.profile.key != "jalon_24"
            else transport.service_uuid
        )
        char_uuid = transport.notify_uuid if notify else transport.write_uuid
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to OkinComfortBed II")
        service = client.services.get_service(service_uuid)
        characteristic = service.get_characteristic(char_uuid) if service is not None else None
        if characteristic is None:
            raise BleakError(f"OkinComfortBed II requires {char_uuid} in {service_uuid}")
        return characteristic

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=not self.profile.no_response,
            characteristic=self._role(),
        )

    async def _release_frames(self) -> None:
        failure: Exception | None = None
        for index in range(2):
            if index:
                await asyncio.sleep(app.REFRESH_MS / 1000)
            try:
                await self.write_command(self._build_command(0), cancel_event=asyncio.Event())
            except Exception as err:
                failure = failure or err
        if failure is not None:
            raise failure

    async def _release_motion(self, *, delay: bool = True) -> None:
        # Own and await cleanup inside the coordinator lane, including repeated
        # task cancellation. A failed first STOP never suppresses the second.
        task = asyncio.create_task(self._release_frames())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _hold(self, word: int, duration_ms: int) -> None:
        event = self._coordinator.cancel_command
        deadline = monotonic_ns() + duration_ms * 1_000_000
        try:
            while not event.is_set() and monotonic_ns() < deadline:
                next_write = monotonic_ns() + app.REFRESH_MS * 1_000_000
                await self.write_command(self._build_command(word))
                await _wait_unless_cancelled(
                    event, (min(next_write, deadline) - monotonic_ns()) / 1_000_000_000
                )
        finally:
            await self._release_motion()

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in app.LAYOUTS[self.layout]:
            raise ValueError(f"This app layout has no {motor} actuator")
        if direction is None:
            await self.stop_all()
            return
        words = {"head": (1, 2), "feet": (4, 8), "tilt": (16, 32), "lumbar": (64, 128)}
        count = self.leased_hold_refreshes(app.REFRESH_MS) or self._coordinator.motor_pulse_count
        await self._hold(words[motor][not direction], count * app.REFRESH_MS)

    async def _preset(self, preset: profiles.Preset) -> None:
        await self._hold(self.profile.presets[preset], app.PRESET_MS)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in self.profile.memory:
            raise ValueError("This app has memory slots 1 and 2")
        await self._hold(self.profile.memory[memory_num], app.REFRESH_MS)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in self.profile.memory:
            raise ValueError("This app has memory slots 1 and 2")
        await self._hold(self.profile.memory[memory_num], app.MEMORY_SAVE_MS)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return ("flat", "memory_1", "memory_2")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 100 <= duration_ms <= 30000:
            raise ValueError("Unknown app control or hold duration outside 100..30000 ms")
        if control != "flat" and duration_ms >= app.MEMORY_SAVE_MS:
            raise ValueError("Use save_preset for memory programming")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        word = (
            self.profile.presets["flat"]
            if control == "flat"
            else self.profile.memory[int(control[-1])]
        )
        await self._hold(word, duration_ms)

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    async def query_massage(self) -> None:
        await asyncio.sleep(app.QUERY_DELAY_MS / 1000)
        await self.write_command(app.massage_query(self.profile))

    async def massage_toggle(self) -> None:
        # The app's 100ms query cancels its scheduled second toggle at 300ms.
        await self.write_command(self._build_command(app.COMMANDS["massageSwitch"]))
        await self.query_massage()

    async def _massage_action(self, action: str) -> None:
        if not self._timer:
            raise ValueError("Refresh massage state and turn massage on first")
        await self.write_command(self._build_command(app.COMMANDS[action]))

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_clock_alarm(self) -> bool:
        return self.profile.key in app.WAKE_TYPES

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(app.WAKE_TYPES.get(self.profile.key, {}))

    async def sync_clock(self) -> None:
        await self.write_command(
            app.clock(self.profile, dt_util.now()), repeat_count=2, repeat_delay_ms=app.REFRESH_MS
        )

    async def query_alarm(self, *, after_set: bool = False) -> None:
        packet = app.alarm_query(self.profile)
        await asyncio.sleep(app.QUERY_DELAY_MS / 1000)
        count = (3 if after_set else 1) if self.profile.key == "jalon_24" else 2
        await self.write_command(
            packet,
            repeat_count=count,
            repeat_delay_ms=app.ALARM_FOLLOWUP_MS if after_set else app.REFRESH_MS,
        )

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        modes = app.WAKE_TYPES.get(self.profile.key, {})
        if (
            preset not in modes
            or head_level
            or foot_level
            or any(day not in range(1, 8) for day in weekdays)
        ):
            raise ValueError("Invalid app alarm mode, weekday or massage level")
        # App bits are Sunday=0 through Saturday=6; bit7 marks recurrence.
        week = (
            0x80 | sum(1 << (day % 7) for day in set(weekdays))
            if weekdays
            else app.alarm_week(0, hour, minute, dt_util.now())
        )
        packet = app.alarm(
            self.profile,
            hour=hour,
            minute=minute,
            week=week,
            wake_type=modes[preset],
            enabled=enabled,
        )
        await self.write_command(packet)
        await self.query_alarm(after_set=True)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def button(
            key: str,
            name: str,
            action: Callable[[JalonController], Coroutine[Any, Any, None]],
            *,
            massage: bool = False,
        ) -> ControllerButtonSpec:
            return ControllerButtonSpec(
                key,
                name,
                lambda ctrl: action(cast(JalonController, ctrl)),
                "mdi:vibrate" if massage else "mdi:refresh",
                translation_key=key,
                card=CARD_MASSAGE if massage else CARD_UTILITY,
            )

        buttons = [
            button(
                "jalon_massage_toggle", "Toggle massage", lambda c: c.massage_toggle(), massage=True
            ),
            button("jalon_query_massage", "Refresh massage", lambda c: c.query_massage()),
        ]
        for action, label in (
            ("massageTimeSwitch", "Massage timer"),
            ("massageWaveSwitch", "Massage wave"),
            ("strengthHeadUp", "Head massage intensity"),
            ("strengthFootUp", "Foot massage intensity"),
        ):
            buttons.append(
                button(
                    f"jalon_{action}",
                    label,
                    lambda c, action=action: c._massage_action(action),
                    massage=True,
                )
            )
        if self.supports_clock_alarm:
            buttons.append(button("jalon_query_alarm", "Refresh alarm", lambda c: c.query_alarm()))
        return tuple(buttons)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "jalon_massage",
                "jalon_massage",
                TIMER,
                "mdi:vibrate",
                attribute_keys=(WAVE, HEAD, FOOT),
                card=CARD_MASSAGE_TIMER,
            ),
            ControllerStateSensorSpec(
                "jalon_alarm",
                "jalon_alarm",
                ALARM,
                "mdi:alarm",
                attribute_keys=(WEEK, WAKE, HOUR, MINUTE, FIRST),
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.invalidate_diagnostics()
        self._notify_callback = callback
        char = self._role(notify=True)
        client = self.client
        assert client is not None
        for attempt in range(2):
            try:
                await client.start_notify(char, self._on_notification)
                self._notifying = True
                return
            except BleakError:
                if attempt:
                    raise
                await client.stop_notify(char)

    async def stop_notify(self) -> None:
        if self._notifying and self.client is not None and self.client.is_connected:
            await self.client.stop_notify(self._role(notify=True))
        self._notifying = False
        self.invalidate_diagnostics()

    async def async_after_connect(self, session: ControllerSession) -> None:
        await self.sync_clock()

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        packet = bytes(data)
        self.forward_raw_notification(self._notify_char_uuid, packet)
        status = parse_notification(self.profile.key, packet)
        if isinstance(status, MassageStatus):
            self._timer = status.time if status.time <= 4 else 0
            self.forward_controller_state_updates(
                TIMER(self._timer),
                WAVE(status.wave),
                HEAD(status.headStrength),
                FOOT(status.footStrength),
            )
        elif isinstance(status, AlarmStatus):
            self.forward_controller_state_updates(
                ALARM("on" if status.isOpen else "off"),
                WEEK(status.week),
                WAKE(status.type),
                HOUR(status.hour),
                MINUTE(status.minute),
                FIRST(status.isFirst),
            )

    def invalidate_diagnostics(self) -> None:
        self._timer = None
        self.forward_controller_state_updates(*(key(None) for key in STATE_KEYS))


async def build_controller(ctx: BuildContext) -> JalonController:
    """Resolve this entry's app profile from its raw name and this link's ff20."""
    name = ctx.live_device_name or ctx.data.get(CONF_BLE_DEVICE_NAME, "")
    name = name.lower()
    if name.startswith("smartbed"):
        protocol = "P3"
    elif name.startswith("okin-ble"):
        protocol = (
            "P2"
            if ctx.client is not None
            and ctx.client.services.get_service("0000ff20-0000-1000-8000-00805f9b34fb") is not None
            else "P1"
        )
    elif ctx.client is None:
        protocol = "P1"  # Client-free capabilities; live connection must prove the route.
    else:
        raise ValueError("OkinComfortBed II requires an okin-ble or smartbed Bluetooth name")
    layout = ctx.data.get(CONF_PRODUCT_TYPE, "0")
    return JalonController(ctx.coordinator, protocol=protocol, layout=layout)
