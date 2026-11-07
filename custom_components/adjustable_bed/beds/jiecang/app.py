"""Dreamask, Dreamotion and Dream Motion HD app profiles, from accepted APK reports.

Movement, presets and memory come from the shared Jiecang glue. This module
keeps what these apps add: their transport choice and startup queries,
capability-gated RGB lighting, the bed alarm and wake executor, and rename.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from homeassistant.util import dt as dt_util

from ...codec import jiecang as codec
from ...codec.jiecang import Notification, TransportKey, Wake
from ...const import (
    BED_TYPE_JIECANG_APP,
    CONF_HAS_LIGHT,
    CONF_JIECANG_APP_LAYOUT,
    CONF_JIECANG_APP_PROFILE,
    CONF_JIECANG_APP_TRANSPORT,
    HAS_LIGHT_DEFAULTS,
)
from ...controller_state import StateKey, StateUpdate
from ...profiles.jiecang import (
    APP_LAYOUT_AXES,
    APP_PROFILES,
    COMFORT_MOTION,
    DREAMHD,
    QUERY_LIGHT,
    Layout,
    Tap,
    automatic_light_on,
    is_bilateral,
    light_toggle_command,
    massage_command,
    massage_zones,
    wake_schedule,
)
from ...state_keys import (
    AUTOMATIC_LIGHT,
    LIGHT_LEVEL,
    LIGHT_TIMER_OPTION,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
    massage_intensity,
)
from ..base import BedController
from ..builder import BuildContext
from ..family_actions import YogaPresetActions
from .controller import JiecangProfileController

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...codec.jiecang import MassageZone
    from ...coordinator import AdjustableBedCoordinator

_ZONES: dict[str, MassageZone] = {"head": "back", "foot": "legs", "right": "right"}
CAPABILITIES_KNOWN: Final = StateKey[bool]("jiecang_capabilities_known")
ALARM_VISIBLE: Final = StateKey[bool]("jiecang_alarm_visible")
ALARM: Final = StateKey[dict[str, object]]("jiecang_alarm")
_WAKE_PRESETS: tuple[Wake, ...] = (
    "flat",
    "zero_g",
    "anti_snore",
    "memory_1",
    "memory_2",
    "yoga",
)
LIGHT_TIMEOUTS: Final = (0, 60, 120, 180, 240, 300, 600, 900, 1200, 1500, 1800)


@dataclass
class DreamHDLightControls:
    """E18 consumer state, distinct from a physical RGB/sensor capability claim.

    Android visibility constants are retained in diagnostics: 0 visible, 4 hidden,
    8 gone. A positive feature reply deliberately does not clear suppression.
    HA additionally honors the user's explicit has_light gate.
    """

    picker: int = 4
    human: int = 4
    container: int = 4
    suppressed: bool = False

    def connected(self) -> None:
        self.picker = self.human = self.container = 4
        self.suppressed = False

    def receive(self, update: Notification, *, has_light: bool, split_series: bool) -> None:
        if update.rgb is not None and not self.suppressed:
            self.picker = 0
        if update.capabilities is not None and has_light:
            if update.capabilities.light_config:
                self.picker = self.human = self.container = 0
            else:
                self.picker = 8
                self.human = self.container = 4
                self.suppressed = True
        if update.reapply_layout and not has_light and not split_series:
            self.picker = self.human = self.container = 4


class JiecangAppController(JiecangProfileController, YogaPresetActions):
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
        app = APP_PROFILES.get(profile)
        if app is None or app is COMFORT_MOTION:
            raise ValueError("Select an explicit Jiecang app profile")
        if layout not in APP_LAYOUT_AXES:
            raise ValueError("Select an explicit Jiecang app actuator layout")
        selected: Layout | None = next((key for key in app.layouts if key == layout), None)
        if selected is None:
            raise ValueError("Layout unavailable in Dream Motion HD")
        if transport not in ("auto", *app.transports):
            raise ValueError("Unknown Jiecang app transport")
        super().__init__(coordinator, app, selected)
        self._layout: Layout = selected
        self.dreamhd = app is DREAMHD
        self._candidates: tuple[TransportKey, ...] = tuple(
            key for key in app.transports if transport in ("auto", key)
        )
        self._transport = ""
        self._notify_uuid = ""
        self._name_uuid: str | None = None
        self._bootstrap_ready = False
        self._has_light = has_light
        self._subscriptions: list[str] = []
        self._started = False
        self._capabilities: codec.Capabilities | None = None
        self._capabilities_received = asyncio.Event()
        self._rgb: codec.RGBState | None = None
        self._rgb_received = asyncio.Event()
        self._light_on: bool | None = None
        self._automatic_light: bool | None = None
        self._alarm: codec.AlarmState | None = None
        self._alarm_visible = False
        self._massage = dict.fromkeys(massage_zones(self._layout), 0)
        self.forward_controller_state_updates(*self._massage_levels())
        self._clock_task: asyncio.Task[None] | None = None
        self._hd_light = DreamHDLightControls()

    def _select_transport(self) -> None:
        if self.client is None or self.client.services is None:
            raise ConnectionError("Discover GATT services before using this app profile")
        services = self.client.services
        g1_or_g3 = any(
            services.get_service(codec.TRANSPORTS[key].service_uuid) is not None
            for key in ("g1", "g3")
        )
        complete_profiles = set()
        for key in ("g1", "g3"):
            transport = codec.TRANSPORTS[key]
            service = services.get_service(transport.service_uuid)
            if service and all(
                role and service.get_characteristic(role) is not None
                for role in (transport.write_uuid, transport.notify_uuid, transport.name_uuid)
            ):
                complete_profiles.add(key)
        for key in self._candidates:
            if key == "g2" and self.profile.key == "dreamask" and not g1_or_g3:
                continue
            transport = codec.TRANSPORTS[key]
            service = services.get_service(transport.service_uuid)
            if service is None:
                continue
            characteristic = service.get_characteristic(transport.write_uuid)
            if characteristic is None or service.get_characteristic(transport.notify_uuid) is None:
                continue
            properties = set(characteristic.properties)
            if "write" not in properties and "write-without-response" not in properties:
                continue
            self._write_with_response = "write" in properties
            self._transport = key
            self._bootstrap_ready = (
                bool(complete_profiles) if key == "g2" else key in complete_profiles
            )
            self._write_uuid = transport.write_uuid
            self._notify_uuid = transport.notify_uuid
            self._name_uuid = (
                transport.name_uuid
                if transport.name_uuid and service.get_characteristic(transport.name_uuid)
                else None
            )
            return
        raise ConnectionError("No supported GATT roles for the selected app and transport")

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return self.dreamhd

    @property
    def controller_entity_discovery_complete(self) -> bool:
        """Return whether any expected capability response was received."""
        return not self._bootstrap_ready or self._capabilities_received.is_set()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app_profile": self.profile.key,
            "layout": self.layout,
            "transport": self._transport,
            "capabilities_known": self._capabilities is not None,
            "capabilities": asdict(self._capabilities) if self._capabilities else None,
            "alarm": asdict(self._alarm) if self._alarm else None,
            "alarm_visible": self._alarm_visible,
            "dreamhd_light_controls": asdict(self._hd_light) if self.dreamhd else None,
        }

    async def async_discover_capabilities(self) -> None:
        await self.start_notify()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._started:
            return
        self._select_transport()
        if self.client is None:
            raise ConnectionError("Not connected to bed")
        if self.dreamhd:
            self._hd_light.connected()
            # Retain Yoga, but never reuse stale light state after reconnecting.
            self._rgb = None
            self._rgb_received.clear()
            self._light_on = None
            self._automatic_light = None
        await self.client.start_notify(self._notify_uuid, self._handle_notification)
        self._subscriptions.append(self._notify_uuid)
        try:
            # HA awaits CCCD setup, avoiding the Android descriptor/query race.
            if self._bootstrap_ready:
                if await self._pause(1000, self._coordinator.cancel_command):
                    raise ConnectionError("Notification initialization cancelled")
                ready_time = asyncio.get_running_loop().time()
                if not await self._schedule(self.profile.bootstrap):
                    raise ConnectionError("Notification initialization cancelled")
                if not self._capabilities_received.is_set():
                    try:
                        await asyncio.wait_for(self._capabilities_received.wait(), 0.5)
                    except TimeoutError:
                        pass
                if self._transport == "g3" and self._name_uuid:
                    service = self.client.services.get_service(codec.TRANSPORTS["g3"].service_uuid)
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
        levels = self.profile.massage_levels
        update = codec.parse_notification(bytes(data), massage_levels=levels)
        if update is None:
            return
        if self.dreamhd:
            self._hd_light.receive(
                update, has_light=self._has_light, split_series=self.layout == "split_series"
            )
        if update.capabilities is not None:
            self._capabilities = update.capabilities
            self._capabilities_received.set()
        if update.rgb is not None:
            self._rgb = update.rgb
            self._light_on = update.rgb.on
            self._rgb_received.set()
        if update.legacy_light is not None and (
            not self.dreamhd or update.legacy_light or self._has_light
        ):
            self._light_on = update.legacy_light
            if self._rgb is not None:
                self._rgb = replace(self._rgb, on=update.legacy_light)
        if update.automatic_light is not None:
            self._automatic_light = automatic_light_on(self.profile, update.automatic_light)
        if update.alarm_visible:
            self._alarm_visible = True
        if update.alarm is not None:
            self._alarm = (
                replace(update.alarm, wake=self._alarm.wake)
                if self.dreamhd and update.alarm.wake is None and self._alarm
                else update.alarm
            )
        for zone, value in (("back", update.massage_back), ("legs", update.massage_legs)):
            mapped = "right" if zone == "legs" and is_bilateral(self._layout) else zone
            if value is not None and mapped in self._massage:
                self._massage[mapped] = levels.index(value)
        if self.dreamhd and update.massage_legs is not None and "right" in self._massage:
            # The app consumes byte 6 for both legs and right back, not a third offset.
            self._massage["right"] = levels.index(update.massage_legs)
        self._publish_state()
        if update.clock_requested and (self._clock_task is None or self._clock_task.done()):
            self._clock_task = self._coordinator.hass.async_create_task(self._respond_with_clock())

    async def _respond_with_clock(self) -> None:
        async def send(controller: BedController) -> None:
            if controller is self:
                await self.write_command(codec.clock(dt_util.now()))

        await self._coordinator.async_execute_controller_command(send, cancel_running=False)

    def _publish_state(self) -> None:
        state = [
            CAPABILITIES_KNOWN(self._capabilities is not None),
            ALARM_VISIBLE(self._alarm_visible),
        ]
        if self._automatic_light is not None:
            state.append(AUTOMATIC_LIGHT(self._automatic_light))
        if self._light_on is not None:
            state.append(UNDER_BED_LIGHTS_ON(self._light_on))
        if self._rgb is not None:
            state += [
                UNDER_BED_LIGHTS_RGB((self._rgb.red, self._rgb.green, self._rgb.blue)),
                LIGHT_LEVEL(self._rgb.brightness),
                LIGHT_TIMER_OPTION(str(self._rgb.seconds)),
            ]
        if self._alarm is not None:
            state.append(ALARM(asdict(self._alarm)))
        self.forward_controller_state_updates(*state, *self._massage_levels())

    def _massage_levels(self) -> list[StateUpdate]:
        return [
            massage_intensity(key)(self._massage[value])
            for key, value in _ZONES.items()
            if value in self._massage
        ]

    async def move_lumbar_up(self) -> None:
        await self._move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def move_neck_up(self) -> None:
        await self.move_head_up()

    async def move_neck_down(self) -> None:
        await self.move_head_down()

    async def move_neck_stop(self) -> None:
        await self.stop_all()

    async def move_bed_height_up(self) -> None:
        await self._move_axis("bed_height", True)

    async def move_bed_height_down(self) -> None:
        await self._move_axis("bed_height", False)

    async def move_bed_height_stop(self) -> None:
        await self.stop_all()

    async def _click(self, command: bytes, release_after_ms: int | None = None) -> None:
        """Tap with the app's release; Dream Motion HD always releases after 100 ms."""
        tap = self.profile.recall
        if release_after_ms is not None and not self.dreamhd:
            tap = Tap(release_after_ms=release_after_ms, release=tap.release)
        await self._tap(command, tap)

    @property
    def supports_preset_yoga(self) -> bool:
        return self._capabilities is not None and self._capabilities.yoga

    async def preset_yoga(self) -> None:
        if not self.supports_preset_yoga:
            raise ValueError("Yoga requires the bed's reported capability")
        await self._preset("yoga")

    # Massage

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_max(self) -> int:
        return len(self.profile.massage_levels) - 1

    @property
    def massage_intensity_zones(self) -> list[str]:
        return [key for key, value in _ZONES.items() if value in self._massage]

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in self.massage_intensity_zones:
            raise ValueError("Massage zone unavailable for this layout")
        target = _ZONES[zone]
        command = massage_command(self.profile, self._layout, target, level)
        if is_bilateral(self._layout):
            await self._click(command)
        else:
            await self.write_command(command)
        if not self.dreamhd and not self._coordinator.cancel_command.is_set():
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
        command = codec.massage_mode(bilateral=is_bilateral(self._layout))
        if self.dreamhd:
            await self.write_command(command)
        else:
            await self._click(command, 1000)

    async def massage_off(self) -> None:
        await self.write_command(codec.massage_stop(bilateral=is_bilateral(self._layout)))
        if not self._coordinator.cancel_command.is_set():
            self._massage = dict.fromkeys(self._massage, 0)
            self._publish_state()

    # Lights

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
        if self.dreamhd:
            return self._has_light and self._hd_light.picker == 0
        return (
            self._has_light
            and not is_bilateral(self._layout)
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
        return [str(seconds) for seconds in LIGHT_TIMEOUTS]

    async def _known_rgb(self) -> codec.RGBState:
        if self._rgb is None:
            await self.write_command(
                codec.query() if self.dreamhd else QUERY_LIGHT,
                repeat_count=2,
                repeat_delay_ms=100,
            )
            try:
                await asyncio.wait_for(self._rgb_received.wait(), 1.0)
            except TimeoutError as error:
                raise ValueError(
                    "No light state received; preserving unknown color and timer settings"
                ) from error
        assert self._rgb is not None
        return self._rgb

    async def _write_rgb(self, state: codec.RGBState) -> None:
        if state.seconds not in LIGHT_TIMEOUTS:
            raise ValueError("Unsupported light timeout")
        await self.write_command(
            codec.rgb(state.red, state.green, state.blue, state.brightness, state.seconds, state.on)
        )
        if not self._coordinator.cancel_command.is_set():
            self._rgb = state
            self._light_on = state.on
            self._publish_state()

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise ValueError("Lighting was not configured")
        state = await self._known_rgb()
        if self.dreamhd:
            try:
                await self._write_rgb(replace(state, on=not state.on))
                if await self._pause(100, self._coordinator.cancel_command):
                    return
                await self.write_command(codec.SHORT_RELEASE)
                if await self._pause(100, self._coordinator.cancel_command):
                    return
                await self.write_command(light_toggle_command(self.profile))
                await self._pause(100, self._coordinator.cancel_command)
            finally:
                await self.write_command(codec.SHORT_RELEASE, cancel_event=asyncio.Event())
            return
        try:
            await self._write_rgb(replace(state, on=not state.on))
            if not await self._pause(150, self._coordinator.cancel_command):
                await self.write_command(light_toggle_command(self.profile))
                await self._pause(80, self._coordinator.cancel_command)
        finally:
            await self._schedule(((0, codec.SHORT_RELEASE), (0, codec.LONG_RELEASE)), cleanup=True)

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
        if self.dreamhd:
            return self._has_light and self._hd_light.human == 0
        return self.supports_light_color_control

    async def set_automatic_light(self, enabled: bool) -> None:
        if not self.supports_automatic_light:
            raise ValueError("Automatic lighting requires the bed's reported capability")
        if self._automatic_light is None:
            raise ValueError("Read automatic-light state before changing its toggle")
        if self._automatic_light != enabled:
            if self.dreamhd:
                await self._click(codec.AUTOMATIC_LIGHT_TOGGLE)
            else:
                await self.write_command(codec.AUTOMATIC_LIGHT_TOGGLE)
            if not self._coordinator.cancel_command.is_set():
                self._automatic_light = enabled
                self._publish_state()

    # Rename

    @property
    def supports_device_rename(self) -> bool:
        return self._name_uuid is not None

    def validate_device_rename(self, name: str) -> None:
        self._name_rule.encode(name)

    async def rename_device(self, name: str) -> None:
        if self.client is None or not self._name_uuid:
            raise ValueError("Selected transport has no name characteristic")
        payload = self._name_rule.encode(name)
        if self._transport == "g1":
            command = payload
        elif self._transport == "g3":
            command = codec.g3_name(payload)
        else:
            raise ValueError("The selected transport has no name characteristic")
        characteristic = self.client.services.get_characteristic(self._name_uuid)
        if characteristic is None:
            raise ValueError("Name characteristic unavailable")
        response = "write" in characteristic.properties
        for offset in (0, 500):
            if await self._pause(offset, self._coordinator.cancel_command):
                return
            self._record_command_trace(
                self._name_uuid,
                command,
                response=response,
                characteristic=characteristic,
            )
            async with self._ble_lock:
                await self.client.write_gatt_char(self._name_uuid, command, response=response)

    # Alarm and wake

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def supports_wake_routine(self) -> bool:
        return True

    @staticmethod
    def _wake_preset(preset: str) -> Wake:
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
            codec.alarm(enabled, selected, hour, minute, wake, head_level, foot_level)
        )
        if not self._coordinator.cancel_command.is_set():
            self._alarm = codec.AlarmState(
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
        schedule = wake_schedule(
            self.profile, self._layout, self._wake_preset(preset), head_level, foot_level
        )
        completed = False
        try:
            completed = await self._schedule(schedule)
        finally:
            if self.dreamhd:
                # Android's broadcast executor omits preset release and cancellation.
                try:
                    await self.write_command(codec.SHORT_RELEASE, cancel_event=asyncio.Event())
                finally:
                    if not completed:
                        await self.stop_wake_routine()
            elif not completed:
                await self.write_command(codec.LONG_RELEASE, cancel_event=asyncio.Event())

    async def stop_wake_routine(self) -> None:
        """Stop the app alarm's massage, whose packet is standard even on bilateral beds."""
        await self.write_command(codec.massage_stop(), cancel_event=asyncio.Event())
        self._massage = dict.fromkeys(self._massage, 0)
        self._publish_state()


def require_app_transport(client: BleakClient, data: Mapping[str, Any]) -> None:
    """Raise ConnectionError unless the link exposes the selected app's GATT roles.

    A guided change checks a candidate link with the controller's own transport
    selection, so the check is exactly what the runtime will require.
    """
    from ...const import (
        CONF_JIECANG_APP_LAYOUT,
        CONF_JIECANG_APP_PROFILE,
        CONF_JIECANG_APP_TRANSPORT,
    )

    # The probe link discards the state a controller publishes at construction.
    link = cast(
        "AdjustableBedCoordinator",
        SimpleNamespace(
            client=client,
            controller_state={},
            handle_controller_state_updates=lambda *_updates: None,
        ),
    )
    profile = data[CONF_JIECANG_APP_PROFILE]
    layout = data[CONF_JIECANG_APP_LAYOUT]
    transport = data.get(CONF_JIECANG_APP_TRANSPORT, "auto")
    controller: JiecangProfileController
    if profile == COMFORT_MOTION.key:
        from ..comfort_motion import ComfortMotionController

        controller = ComfortMotionController(link, layout=layout, transport=transport)
    else:
        controller = JiecangAppController(link, profile=profile, layout=layout, transport=transport)
    controller._select_transport()  # noqa: SLF001 - the controller's own selection


async def build_controller(ctx: BuildContext) -> BedController:
    """Build the controller for the stored app profile."""
    data = ctx.data
    if data[CONF_JIECANG_APP_PROFILE] == "comfort_motion":
        await ctx.preload("comfort_motion")
        from ..comfort_motion import ComfortMotionController

        return ComfortMotionController(
            ctx.coordinator,
            layout=data[CONF_JIECANG_APP_LAYOUT],
            transport=data.get(CONF_JIECANG_APP_TRANSPORT, "auto"),
            has_light=data.get(CONF_HAS_LIGHT, True),
        )
    return JiecangAppController(
        ctx.coordinator,
        profile=data[CONF_JIECANG_APP_PROFILE],
        layout=data[CONF_JIECANG_APP_LAYOUT],
        transport=data.get(CONF_JIECANG_APP_TRANSPORT, "auto"),
        has_light=data.get(CONF_HAS_LIGHT, HAS_LIGHT_DEFAULTS[BED_TYPE_JIECANG_APP]),
    )
