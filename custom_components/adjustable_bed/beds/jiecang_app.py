"""Explicit Dreamask/Dreamotion app profiles from accepted Phase 4 evidence.

These opt-in profiles preserve the older, separately tested Jiecang controller.
Transport selection and physical layout are independent of app release timing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .. import jiecang_app_protocol as protocol
from ..const import (
    COMFORT_MOTION_BTNAME_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_BTNAME_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
    COMFORT_MOTION_PEILIN_CHAR_UUID,
    COMFORT_MOTION_PEILIN_SERVICE_UUID,
    COMFORT_MOTION_READ_CHAR_UUID,
    COMFORT_MOTION_SERVICE_UUID,
    COMFORT_MOTION_WRITE_CHAR_UUID,
)
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_TRANSPORTS = {
    "g1": (
        COMFORT_MOTION_SERVICE_UUID,
        COMFORT_MOTION_WRITE_CHAR_UUID,
        COMFORT_MOTION_READ_CHAR_UUID,
        COMFORT_MOTION_BTNAME_CHAR_UUID,
    ),
    "g2": (
        COMFORT_MOTION_PEILIN_SERVICE_UUID,
        COMFORT_MOTION_PEILIN_CHAR_UUID,
        COMFORT_MOTION_PEILIN_CHAR_UUID,
        None,
    ),
    "g3": (
        COMFORT_MOTION_LIERDA3_SERVICE_UUID,
        COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID,
        COMFORT_MOTION_LIERDA3_READ_CHAR_UUID,
        COMFORT_MOTION_LIERDA3_BTNAME_CHAR_UUID,
    ),
}
_ZONES: dict[str, protocol.MassageZone] = {"head": "back", "foot": "legs", "right": "right"}
_WAKE_PRESETS: tuple[protocol.Wake, ...] = (
    "flat",
    "zero_g",
    "anti_snore",
    "memory_1",
    "memory_2",
    "yoga",
)


class JiecangAppController(BedController):
    """Control the complete artifact-proven app profiles without guessing hardware."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: str,
        layout: str,
        transport: str = "auto",
        has_light: bool = True,
    ) -> None:
        super().__init__(coordinator)
        if profile not in protocol.APP_PROFILES:
            raise ValueError("Select an explicit Dreamask or Dreamotion app profile")
        if layout not in protocol.LAYOUTS:
            raise ValueError("Select an explicit Jiecang app actuator layout")
        if transport not in ("auto", *_TRANSPORTS):
            raise ValueError("Unknown Jiecang app transport")
        self.profile: protocol.AppProfile = next(
            value for value in protocol.APP_PROFILES if value == profile
        )
        self.layout: protocol.Layout = next(value for value in protocol.LAYOUTS if value == layout)
        self._transport_preference = transport
        self._transport = ""
        self._write_uuid = ""
        self._notify_uuid = ""
        self._name_uuid: str | None = None
        self._bootstrap_ready = False
        self._has_light = has_light
        self._subscriptions: list[str] = []
        self._started = False
        self._capabilities: protocol.Capabilities | None = None
        self._capabilities_received = asyncio.Event()
        self._rgb: protocol.RGBState | None = None
        self._rgb_received = asyncio.Event()
        self._light_on: bool | None = None
        self._automatic_light: bool | None = None
        self._alarm: protocol.AlarmState | None = None
        self._alarm_visible = False
        self._massage = dict.fromkeys(protocol.massage_zones(self.layout), 0)
        self._clock_task: asyncio.Task[None] | None = None

    def _select_transport(self) -> None:
        if self.client is None or self.client.services is None:
            raise ConnectionError("Discover GATT services before using this app profile")
        candidates = (
            ("g3", "g1", "g2")
            if self._transport_preference == "auto"
            else (self._transport_preference,)
        )
        g1_or_g3 = any(
            self.client.services.get_service(_TRANSPORTS[key][0]) is not None
            for key in ("g1", "g3")
        )
        complete_profiles = set()
        for key in ("g1", "g3"):
            service_uuid, *roles = _TRANSPORTS[key]
            service = self.client.services.get_service(service_uuid)
            if service and all(
                role and service.get_characteristic(role) is not None for role in roles
            ):
                complete_profiles.add(key)
        for key in candidates:
            if key == "g2" and self.profile == "dreamask" and not g1_or_g3:
                continue
            service_uuid, write_uuid, notify_uuid, name_uuid = _TRANSPORTS[key]
            service = self.client.services.get_service(service_uuid)
            if service is None:
                continue
            characteristic = service.get_characteristic(write_uuid)
            if characteristic is None or service.get_characteristic(notify_uuid) is None:
                continue
            properties = set(characteristic.properties)
            if "write" not in properties and "write-without-response" not in properties:
                continue
            self._write_with_response = "write" in properties
            self._transport = key
            self._bootstrap_ready = (
                bool(complete_profiles) if key == "g2" else key in complete_profiles
            )
            self._write_uuid = write_uuid
            self._notify_uuid = notify_uuid
            self._name_uuid = (
                name_uuid if name_uuid and service.get_characteristic(name_uuid) else None
            )
            return
        raise ConnectionError("No supported GATT roles for the selected app and transport")

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app_profile": self.profile,
            "layout": self.layout,
            "transport": self._transport,
            "capabilities_known": self._capabilities is not None,
            "capabilities": asdict(self._capabilities) if self._capabilities else None,
            "alarm": asdict(self._alarm) if self._alarm else None,
            "alarm_visible": self._alarm_visible,
        }

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write once per application action, without inventing ACK/retry packets."""
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")
        if not self._write_uuid:
            self._select_transport()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(repeat_count):
            if cancel.is_set():
                return
            if index and await self._pause(
                index * repeat_delay_ms - (loop.time() - started) * 1000, cancel
            ):
                return
            async with self._ble_lock:
                await self.client.write_gatt_char(
                    self._write_uuid, command, response=self._write_with_response
                )

    @staticmethod
    async def _pause(milliseconds: float, cancel: asyncio.Event) -> bool:
        """Return early when a running action is stopped."""
        if cancel.is_set():
            return True
        if milliseconds <= 0:
            return False
        try:
            await asyncio.wait_for(cancel.wait(), milliseconds / 1000)
        except TimeoutError:
            return False
        return True

    async def _schedule(self, schedule: protocol.Schedule, *, cleanup: bool = False) -> bool:
        cancel = asyncio.Event() if cleanup else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        started = loop.time()
        for offset, command in schedule:
            if await self._pause(offset - (loop.time() - started) * 1000, cancel):
                return False
            await self.write_command(command, cancel_event=cancel)
        return not cancel.is_set()

    async def async_discover_capabilities(self) -> None:
        await self.start_notify()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._started:
            return
        self._select_transport()
        if self.client is None:
            raise ConnectionError("Not connected to bed")
        await self.client.start_notify(self._notify_uuid, self._handle_notification)
        self._subscriptions.append(self._notify_uuid)
        try:
            # HA awaits CCCD setup, avoiding the Android descriptor/query race.
            if self._bootstrap_ready:
                if await self._pause(1000, self._coordinator.cancel_command):
                    raise ConnectionError("Notification initialization cancelled")
                ready_time = asyncio.get_running_loop().time()
                if not await self._schedule(protocol.BOOTSTRAP_SCHEDULE):
                    raise ConnectionError("Notification initialization cancelled")
                if not self._capabilities_received.is_set():
                    try:
                        await asyncio.wait_for(self._capabilities_received.wait(), 0.5)
                    except TimeoutError:
                        pass
                if self._transport == "g3" and self._name_uuid:
                    service = self.client.services.get_service(_TRANSPORTS["g3"][0])
                    characteristic = (
                        service.get_characteristic(self._name_uuid) if service else None
                    )
                    if characteristic and "notify" in characteristic.properties:
                        elapsed = asyncio.get_running_loop().time() - ready_time
                        if await self._pause(
                            3000 - elapsed * 1000, self._coordinator.cancel_command
                        ):
                            raise ConnectionError("Notification initialization cancelled")
                        await self.client.start_notify(self._name_uuid, self._handle_notification)
                        self._subscriptions.append(self._name_uuid)
            self._started = True
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        if self._clock_task is not None:
            self._clock_task.cancel()
            self._clock_task = None
        if self.client is not None and self.client.is_connected:
            for uuid in self._subscriptions:
                await self.client.stop_notify(uuid)
        self._subscriptions.clear()
        self._started = False
        self._notify_callback = None

    def _handle_notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        update = protocol.parse_notification(bytes(data))
        if update is None:
            return
        if update.capabilities is not None:
            self._capabilities = update.capabilities
            self._capabilities_received.set()
        if update.rgb is not None:
            self._rgb = update.rgb
            self._light_on = update.rgb.on
            self._rgb_received.set()
        if update.legacy_light is not None:
            self._light_on = update.legacy_light
            if self._rgb is not None:
                self._rgb = replace(self._rgb, on=update.legacy_light)
        if update.automatic_light is not None:
            self._automatic_light = update.automatic_light
        if update.alarm_visible:
            self._alarm_visible = True
        if update.alarm is not None:
            self._alarm = update.alarm
        for zone, value in (("back", update.massage_back), ("legs", update.massage_legs)):
            mapped = "right" if zone == "legs" and protocol.is_bilateral(self.layout) else zone
            if value is not None and mapped in self._massage:
                self._massage[mapped] = protocol.WIRE_MASSAGE_LEVELS.index(value)
        self._publish_state()
        if update.clock_requested and (self._clock_task is None or self._clock_task.done()):
            self._clock_task = self._coordinator.hass.async_create_task(self._respond_with_clock())

    async def _respond_with_clock(self) -> None:
        async def send(controller: BedController) -> None:
            if controller is self:
                await self.write_command(protocol.clock_command(dt_util.now()))

        await self._coordinator.async_execute_controller_command(send, cancel_running=False)

    def _publish_state(self) -> None:
        state: dict[str, object] = {
            "jiecang_capabilities_known": self._capabilities is not None,
            "jiecang_alarm_visible": self._alarm_visible,
        }
        if self._automatic_light is not None:
            state["automatic_light"] = self._automatic_light
        if self._light_on is not None:
            state["under_bed_lights_on"] = self._light_on
        if self._rgb is not None:
            state["under_bed_lights_rgb"] = (self._rgb.red, self._rgb.green, self._rgb.blue)
            state["light_level"] = self._rgb.brightness
            state["light_timer_option"] = str(self._rgb.seconds)
        if self._alarm is not None:
            state["jiecang_alarm"] = asdict(self._alarm)
        state.update(self.get_massage_state())
        self.forward_controller_state_updates(state)

    @property
    def supports_motor_control(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        def spec(axis: protocol.Axis) -> MotorControlSpec:
            return MotorControlSpec(
                key=axis,
                translation_key="back_legs" if axis == "both" else axis,
                open_fn=lambda ctrl: JiecangAppController._dispatch_axis(ctrl, axis, True),
                close_fn=lambda ctrl: JiecangAppController._dispatch_axis(ctrl, axis, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
            )

        return tuple(spec(axis) for axis in protocol.layout_axes(self.layout))

    @staticmethod
    async def _dispatch_axis(controller: BedController, axis: protocol.Axis, up: bool) -> None:
        """A retained entity spec must operate on the newly connected controller."""
        if not isinstance(controller, JiecangAppController):
            raise ValueError("Motor controls require the configured Jiecang app profile")
        await controller._move_axis(axis, up)

    async def _move_axis(self, axis: protocol.Axis, up: bool) -> None:
        command = protocol.motion_command(self.layout, axis, up)
        try:
            await self.write_command(
                command, repeat_count=self._coordinator.motor_pulse_count, repeat_delay_ms=100
            )
            # Dreamotion's normal touch release emits one last movement frame.
            # A cancelled HA action never restarts movement to imitate that bug.
            if self.profile == "dreamotion" and not self._coordinator.cancel_command.is_set():
                await self.write_command(command)
        finally:
            await self._schedule(protocol.movement_releases(self.profile), cleanup=True)

    async def move_back_up(self) -> None:
        await self._move_axis("back", True)

    async def move_back_down(self) -> None:
        await self._move_axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self._move_axis("head", True)

    async def move_head_down(self) -> None:
        await self._move_axis("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self._move_axis("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_neck_up(self) -> None:
        await self.move_head_up()

    async def move_neck_down(self) -> None:
        await self.move_head_down()

    async def move_neck_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self._move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def move_bed_height_up(self) -> None:
        await self._move_axis("bed_height", True)

    async def move_bed_height_down(self) -> None:
        await self._move_axis("bed_height", False)

    async def move_bed_height_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        # An explicit HA stop has no UI release delay before its first frame.
        frames = protocol.movement_releases(self.profile)
        await self._schedule(
            tuple((offset - frames[0][0], command) for offset, command in frames), cleanup=True
        )

    async def _click(self, command: bytes, release_ms: int = 800) -> None:
        try:
            await self.write_command(command)
            await self._pause(release_ms, self._coordinator.cancel_command)
        finally:
            await self.write_command(protocol.LONG_RELEASE, cancel_event=asyncio.Event())

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_yoga(self) -> bool:
        return self._capabilities is not None and self._capabilities.yoga

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    async def preset_flat(self) -> None:
        await self._click(protocol.preset_command(self.layout, "flat"))

    async def preset_zero_g(self) -> None:
        await self._click(protocol.preset_command(self.layout, "zero_g"))

    async def preset_anti_snore(self) -> None:
        await self._click(protocol.preset_command(self.layout, "anti_snore"))

    async def preset_yoga(self) -> None:
        if not self.supports_preset_yoga:
            raise ValueError("Yoga requires the bed's reported capability")
        await self._click(protocol.preset_command(self.layout, "yoga"))

    async def preset_memory(self, memory_num: int) -> None:
        await self._click(protocol.memory_command(memory_num))

    async def program_memory(self, memory_num: int) -> None:
        await self.write_command(
            protocol.memory_command(memory_num, save=True), repeat_count=3, repeat_delay_ms=30
        )

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_max(self) -> int:
        return 3

    @property
    def massage_intensity_zones(self) -> list[str]:
        return [key for key, value in _ZONES.items() if value in self._massage]

    def get_massage_state(self) -> dict[str, object]:
        return {
            f"{key}_intensity": self._massage[value]
            for key, value in _ZONES.items()
            if value in self._massage
        }

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in self.massage_intensity_zones:
            raise ValueError("Massage zone unavailable for this layout")
        target = _ZONES[zone]
        command = protocol.massage_command(self.layout, target, level)
        if protocol.is_bilateral(self.layout):
            await self._click(command)
        else:
            await self.write_command(command)
        if not self._coordinator.cancel_command.is_set():
            self._massage[target] = level
            self._publish_state()

    async def massage_head_up(self) -> None:
        await self.set_massage_intensity("head", min(3, self._massage["back"] + 1))

    async def massage_head_down(self) -> None:
        await self.set_massage_intensity("head", max(0, self._massage["back"] - 1))

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return "legs" in self._massage

    async def massage_foot_up(self) -> None:
        await self.set_massage_intensity("foot", min(3, self._massage.get("legs", 0) + 1))

    async def massage_foot_down(self) -> None:
        await self.set_massage_intensity("foot", max(0, self._massage.get("legs", 0) - 1))

    async def massage_mode_step(self) -> None:
        await self._click(protocol.massage_mode_command(self.layout), 1000)

    async def massage_off(self) -> None:
        await self.write_command(protocol.massage_close_command(self.layout))
        if not self._coordinator.cancel_command.is_set():
            self._massage = dict.fromkeys(self._massage, 0)
            self._publish_state()

    @property
    def supports_lights(self) -> bool:
        return self._has_light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._has_light

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_light_color_control

    @property
    def supports_light_color_control(self) -> bool:
        return (
            self._has_light
            and not protocol.is_bilateral(self.layout)
            and self._capabilities is not None
            and self._capabilities.light_config
        )

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        return (self._rgb.red, self._rgb.green, self._rgb.blue) if self._rgb else None

    @property
    def supports_light_level_control(self) -> bool:
        return self.supports_light_color_control

    @property
    def light_level_max(self) -> int:
        return 100

    @property
    def supports_light_timer(self) -> bool:
        return self.supports_light_color_control

    @property
    def light_timer_options(self) -> list[str]:
        return [str(seconds) for seconds in protocol.LIGHT_TIMEOUTS]

    def get_light_state(self) -> dict[str, object]:
        result: dict[str, object] = {}
        if self._light_on is not None:
            result["is_on"] = self._light_on
        if self._rgb is not None:
            result.update(
                light_level=self._rgb.brightness,
                light_timer_option=str(self._rgb.seconds),
                rgb_color=(self._rgb.red, self._rgb.green, self._rgb.blue),
            )
        return result

    async def _known_rgb(self) -> protocol.RGBState:
        if self._rgb is None:
            await self.write_command(protocol.QUERY_LIGHT, repeat_count=2, repeat_delay_ms=100)
            try:
                await asyncio.wait_for(self._rgb_received.wait(), 1.0)
            except TimeoutError as error:
                raise ValueError(
                    "No light state received; preserving unknown color and timer settings"
                ) from error
        assert self._rgb is not None
        return self._rgb

    async def _write_rgb(self, state: protocol.RGBState) -> None:
        await self.write_command(
            protocol.rgb_command(
                state.red, state.green, state.blue, state.brightness, state.seconds, state.on
            )
        )
        if not self._coordinator.cancel_command.is_set():
            self._rgb = state
            self._light_on = state.on
            self._publish_state()

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise ValueError("Lighting was not configured")
        state = await self._known_rgb()
        try:
            await self._write_rgb(replace(state, on=not state.on))
            if not await self._pause(150, self._coordinator.cancel_command):
                await self.write_command(protocol.LIGHT_TOGGLE)
                await self._pause(80, self._coordinator.cancel_command)
        finally:
            await self._schedule(
                ((0, protocol.SHORT_RELEASE), (0, protocol.LONG_RELEASE)), cleanup=True
            )

    async def lights_on(self) -> None:
        if not self.supports_lights:
            raise ValueError("Lighting was not configured")
        await self._write_rgb(replace(await self._known_rgb(), on=True))

    async def lights_off(self) -> None:
        if not self.supports_lights:
            raise ValueError("Lighting was not configured")
        await self._write_rgb(replace(await self._known_rgb(), on=False))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if not self.supports_light_color_control:
            raise ValueError("Color lighting requires the bed's reported capability")
        state = await self._known_rgb()
        await self._write_rgb(
            replace(state, red=rgb_color[0], green=rgb_color[1], blue=rgb_color[2])
        )

    async def set_light_level(self, level: int) -> None:
        if not self.supports_light_level_control:
            raise ValueError("Light level requires the bed's reported capability")
        await self._write_rgb(replace(await self._known_rgb(), brightness=level))

    async def set_light_timer(self, timer_option: str) -> None:
        if not self.supports_light_timer or timer_option not in self.light_timer_options:
            raise ValueError("Unsupported light timer")
        await self._write_rgb(replace(await self._known_rgb(), seconds=int(timer_option)))

    @property
    def supports_automatic_light(self) -> bool:
        return self.supports_light_color_control

    async def set_automatic_light(self, enabled: bool) -> None:
        if not self.supports_automatic_light:
            raise ValueError("Automatic lighting requires the bed's reported capability")
        if self._automatic_light is None:
            raise ValueError("Read automatic-light state before changing its toggle")
        if self._automatic_light != enabled:
            await self.write_command(protocol.AUTOMATIC_LIGHT_TOGGLE)
            if not self._coordinator.cancel_command.is_set():
                self._automatic_light = enabled
                self._publish_state()

    @property
    def supports_device_rename(self) -> bool:
        return self._name_uuid is not None

    async def rename_device(self, name: str) -> None:
        if self.client is None or not self._name_uuid:
            raise ValueError("Selected transport has no name characteristic")
        command = protocol.rename_command(name, self._transport == "g1", self._transport == "g3")
        characteristic = self.client.services.get_characteristic(self._name_uuid)
        if characteristic is None:
            raise ValueError("Name characteristic unavailable")
        response = "write" in characteristic.properties
        for offset in (0, 500):
            if await self._pause(offset, self._coordinator.cancel_command):
                return
            async with self._ble_lock:
                await self.client.write_gatt_char(self._name_uuid, command, response=response)

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def supports_wake_routine(self) -> bool:
        return True

    @staticmethod
    def _wake_preset(preset: str) -> protocol.Wake:
        if preset not in _WAKE_PRESETS:
            raise ValueError("Unsupported wake preset")
        return next(value for value in _WAKE_PRESETS if value == preset)

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
        if any(day not in range(7) for day in weekdays) or len(set(weekdays)) != len(weekdays):
            raise ValueError("Weekdays must be distinct Monday=0 through Sunday=6")
        wake = self._wake_preset(preset)
        if wake == "yoga" and not self.supports_preset_yoga:
            raise ValueError("Yoga requires the bed's reported capability")
        selected = tuple(day in weekdays for day in range(7))
        await self.write_command(
            protocol.alarm_command(enabled, selected, hour, minute, wake, head_level, foot_level)
        )
        if not self._coordinator.cancel_command.is_set():
            self._alarm = protocol.AlarmState(
                enabled, selected, hour, minute, wake, head_level, foot_level
            )
            self._publish_state()

    async def execute_wake_routine(
        self,
        *,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        schedule = protocol.wake_schedule(
            self.layout, self._wake_preset(preset), head_level, foot_level
        )
        completed = False
        try:
            completed = await self._schedule(schedule)
        finally:
            if not completed:
                await self.write_command(protocol.LONG_RELEASE, cancel_event=asyncio.Event())

    async def stop_wake_routine(self) -> None:
        """Stop the app alarm's massage, whose packet is standard even on bilateral beds."""
        await self.write_command(
            protocol.massage_close_command("standard_2"), cancel_event=asyncio.Event()
        )
        self._massage = dict.fromkeys(self._massage, 0)
        self._publish_state()
