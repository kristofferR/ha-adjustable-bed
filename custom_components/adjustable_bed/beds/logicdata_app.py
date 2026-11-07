"""LOGICDATA MOTIONrelax and Sleep Smart bed apps over the Jiecang codec.

Frames and timing come from ``profiles/logicdata.py``. This controller keeps
what data cannot express: transport selection, each app's startup session and
name role, the packet-family guard and clock-request answering.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..codec import jiecang as codec
from ..const import (
    BED_TYPE_LOGICDATA_APP,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_LOGICDATA_APP_FAMILY,
    CONF_LOGICDATA_APP_LAYOUT,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_LOGICDATA_APP_TRANSPORT,
    HAS_LIGHT_DEFAULTS,
)
from ..controller_state import StateKey, StateUpdate
from ..profiles import logicdata as profiles
from ..profiles.logicdata import (
    APP_PROFILES,
    TRANSPORTS,
    WIRE_MASSAGE_LEVELS,
    Family,
    HeldPreset,
    Layout,
    MassageMode,
    TransportChoice,
)
from ..state_keys import UNDER_BED_LIGHTS_ON, massage_intensity
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .builder import BuildContext

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..codec.jiecang import Axis, MassageZone, Transport
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _motor_callback(axis: str, up: bool) -> MotorCommandCallable:
    async def move(controller: BedController) -> None:
        if not isinstance(controller, LogicdataAppController):
            raise TypeError("MOTIONrelax motor requires its app controller")
        await controller.move_axis(axis, up)

    return move


FAMILY_MATCH: Final = StateKey[bool]("logicdata_app_family_match")
MASSAGE_MODE: Final = StateKey[MassageMode | None]("logicdata_app_massage_mode")
ALARM: Final = StateKey[bool]("logicdata_app_alarm")
ALARM_CONFIG: Final = StateKey[dict[str, object]]("logicdata_app_alarm_config")


class LogicdataAppController(BedController):
    """Keep packet family, app edition, physical layout and GATT independent."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: str,
        command_family: str,
        layout: str,
        transport: str,
        has_light: bool,
        has_massage: bool,
    ) -> None:
        super().__init__(coordinator)
        app = APP_PROFILES.get(cast(profiles.AppKey, profile))
        if app is None:
            raise ValueError("Select a supported MOTIONrelax app edition and packet family")
        profiles.validate_setup(app, command_family, layout)
        if transport not in (*TRANSPORTS, "auto"):
            raise ValueError("Select a supported MOTIONrelax transport")
        self.profile = app
        self._family: Family = cast(Family, command_family)
        self._layout: Layout = cast(Layout, layout)
        self._transport_choice = transport
        self._transport_id: TransportChoice | None = (
            None if transport == "auto" else cast(TransportChoice, transport)
        )
        self._has_light = has_light
        self._has_massage = has_massage and command_family in app.massage_families
        self._subscribed: list[str] = []
        self._clock_task: asyncio.Task[None] | None = None
        self._clock_requests = 0
        self._initialized = False
        self._discovered = False
        self._has_startup_profile = False
        self._candidates: tuple[TransportChoice, ...] = ()
        self._notify_roles: tuple[TransportChoice, ...] = ()
        self._name_roles: frozenset[TransportChoice] = frozenset()
        self._family_matches: bool | None = None
        self._massage_state: dict[str, int] = {}
        self._light_state: dict[str, bool] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        if self._transport_id is None:
            return ""
        return TRANSPORTS[self._transport_id].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        """Reserve the last cadence interval for terminal movement and release."""
        cadence = self.profile.movement_repeat_ms
        return max(0, (duration_ms + cadence - 1) // cadence - 1)

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Report the app cadence to generic timed-movement planning."""
        return self._coordinator.motor_pulse_count, self.profile.movement_repeat_ms

    @property
    def _sleep_smart(self) -> bool:
        return self.profile.session == "sleep_smart"

    @property
    def _axes(self) -> tuple[Axis, ...]:
        return self.profile.layouts[self._layout]

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_preset_hold(self) -> bool:
        return bool(self.held_preset_options)

    @property
    def held_preset_options(self) -> tuple[str, ...]:
        return self.profile.held_presets[self._family]

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.profile.presets[self._family]

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self.profile.presets[self._family]

    @property
    def supports_factory_reset(self) -> bool:
        return self.profile.factory_reset

    @property
    def supports_massage(self) -> bool:
        return self._has_massage

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    @property
    def massage_intensity_max(self) -> int:
        return 3

    @property
    def massage_intensity_zones(self) -> list[str]:
        if not self.supports_massage:
            return []
        return ["head", "right"] if self._layout == "split_series" else ["head", "foot"]

    @property
    def supports_lights(self) -> bool:
        return self._has_light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_device_rename(self) -> bool:
        return self._rename_transport is not None

    @property
    def _rename_transport(self) -> TransportChoice | None:
        if not self._sleep_smart:
            return self._transport_id if self._transport_id in ("t1", "t3") else None
        if self._transport_id in self._name_roles:
            return self._transport_id
        if self._transport_id == "t2":
            # Sleep Smart keeps an earlier T3 or T1 name role when T2 supplies
            # the write role. T3 is preferred, matching its shared ready event.
            return next((key for key in ("t3", "t1") if key in self._name_roles), None)
        return None

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in self._axes

    @property
    def has_bed_height_support(self) -> bool:
        return "bed_height" in self._axes

    @property
    def supports_clock_alarm(self) -> bool:
        return self._family in self.profile.alarm_families

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=_motor_callback(axis, True),
                close_fn=_motor_callback(axis, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                # Every axis uses the global release, including combined controls.
                scheduler_resource="motor:*",
            )
            for axis in self._axes
        )

    @property
    def _reports_massage_mode(self) -> bool:
        return self.profile.massage_mode_reply and self.supports_massage

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if not self._reports_massage_mode:
            return ()
        return (
            ControllerButtonSpec(
                "logicdata_app_query_massage",
                "Refresh massage state",
                lambda ctrl: cast(LogicdataAppController, ctrl).query_massage(),
                icon="mdi:refresh",
                translation_key="logicdata_app_query_massage",
                cancel_movement=False,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self.supports_lights:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="under_bed_lights",
                translation_key="under_bed_lights",
                state_key=UNDER_BED_LIGHTS_ON,
                icon="mdi:lightbulb",
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = []
        if self.profile.family_reply:
            specs.append(
                ControllerStateSensorSpec(
                    key="logicdata_app_family_match",
                    translation_key="logicdata_app_family_match",
                    state_key=FAMILY_MATCH,
                    icon="mdi:bed",
                    entity_registry_enabled_default=False,
                )
            )
        if self._reports_massage_mode:
            specs.append(
                ControllerStateSensorSpec(
                    key="logicdata_app_massage_mode",
                    translation_key="logicdata_app_massage_mode",
                    state_key=MASSAGE_MODE,
                    icon="mdi:sine-wave",
                )
            )
        if self.supports_clock_alarm:
            specs.append(
                ControllerStateSensorSpec(
                    key="logicdata_app_alarm",
                    translation_key="logicdata_app_alarm",
                    state_key=ALARM,
                    icon="mdi:alarm",
                    attribute_keys=(ALARM_CONFIG,),
                )
            )
        return tuple(specs)

    def _get_characteristic(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        char = client.services.get_characteristic(uuid)
        if char is None:
            raise ValueError(f"MOTIONrelax characteristic {uuid} is absent")
        return char

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        self._select_transport(client)
        self._get_characteristic(self.control_characteristic_uuid)
        self._discovered = True

    def _select_transport(self, client: BleakClient) -> None:
        """Pick the selected app's transport from the link's GATT, or raise ValueError."""
        candidates = []
        notify_roles = []
        name_roles = set()
        for key, transport in TRANSPORTS.items():
            service = client.services.get_service(transport.service_uuid)
            if service is None:
                continue
            uuids = {char.uuid.lower() for char in service.characteristics}
            if transport.notify_uuid in uuids:
                notify_roles.append(key)
            required = {transport.write_uuid, transport.notify_uuid}
            if transport.name_uuid and transport.name_uuid in uuids:
                name_roles.add(key)
            elif transport.name_uuid and not self._sleep_smart:
                # MOTIONrelax readiness needs all three roles; Sleep Smart
                # assigns its name role only when the characteristic exists.
                continue
            if required <= uuids:
                candidates.append(key)
        if self._transport_choice == "auto":
            if len(candidates) != 1:
                raise ValueError(
                    "Select one MOTIONrelax transport explicitly when GATT is ambiguous"
                )
            self._transport_id = candidates[0]
        elif self._transport_choice not in candidates:
            raise ValueError("The selected MOTIONrelax transport is incomplete or absent")
        self._has_startup_profile = any(key in ("t1", "t3") for key in candidates)
        self._candidates = tuple(candidates)
        self._notify_roles = tuple(notify_roles)
        self._name_roles = frozenset(name_roles)

    async def _pause(self, seconds: float, cancel_event: asyncio.Event | None = None) -> bool:
        cancel = cancel_event or self._coordinator.cancel_command
        if seconds <= 0:
            return not cancel.is_set()
        try:
            async with asyncio.timeout(seconds):
                await cancel.wait()
        except TimeoutError:
            return True
        return False

    async def _write_to(
        self, uuid: str, packet: bytes, cancel_event: asyncio.Event | None = None
    ) -> None:
        char = self._get_characteristic(uuid)
        if not {"write", "write-without-response"}.intersection(char.properties):
            raise ValueError("Selected MOTIONrelax characteristic is not writable")
        await self._write_gatt_with_retry(
            uuid, packet, cancel_event=cancel_event, response="write" in char.properties
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._family_matches is False and command not in (
            codec.SHORT_RELEASE,
            codec.LONG_RELEASE,
        ):
            raise ValueError("MOTIONrelax bed reports a different packet family; reconfigure it")
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(repeat_count):
            await self._write_to(self.control_characteristic_uuid, command, cancel_event)
            if index < repeat_count - 1 and not await self._pause(
                max(0, started + (index + 1) * repeat_delay_ms / 1000 - loop.time()),
                cancel_event,
            ):
                return

    async def _schedule(
        self,
        schedule: Sequence[tuple[int, bytes]],
        *,
        cleanup: bool = False,
        uuid: str | None = None,
        started: float | None = None,
    ) -> bool:
        cancel = asyncio.Event() if cleanup else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        origin = loop.time() if started is None else started
        for offset, packet in schedule:
            if cancel.is_set() or not await self._pause(
                max(0, origin + offset / 1000 - loop.time()), cancel
            ):
                return False
            if uuid:
                await self._write_to(uuid, packet, cancel)
            else:
                await self.write_command(packet, cancel_event=cancel)
        return True

    async def _action(self, packet: bytes, releases: profiles.Schedule) -> None:
        if self._coordinator.cancel_command.is_set():
            return
        started = asyncio.get_running_loop().time()
        try:
            await self.write_command(packet)
        finally:
            await self._schedule(releases, cleanup=True, started=started)

    async def move_axis(self, axis: str, up: bool) -> None:
        if axis not in self._axes:
            raise ValueError("Motor axis is absent from the selected layout")
        packet = profiles.motion_command(
            self.profile, self._family, self._layout, cast("Axis", axis), up
        )
        if self._coordinator.cancel_command.is_set():
            return
        loop = asyncio.get_running_loop()
        started = loop.time()
        cadence = self.profile.movement_repeat_ms
        # A leased hold refreshes at the app's cadence until its lease ends.
        leased = self.leased_hold_refreshes(cadence)
        release_started: float | None = None
        try:
            for tick in range(leased or self._coordinator.motor_pulse_count):
                await self.write_command(packet)
                if not await self._pause(
                    max(0, started + (tick + 1) * cadence / 1000 - loop.time())
                ):
                    return
            if leased is not None:
                # A leased hold that reached its ceiling never restarts movement.
                return
            # Touch-up dispatches one terminal repeat before its delayed release.
            release_started = loop.time()
            await self.write_command(packet)
        finally:
            await self._schedule(self.profile.touch_release, cleanup=True, started=release_started)

    async def _preset(self, preset: HeldPreset) -> None:
        """Tap a preset or memory recall, or hold it when the app only holds them."""
        if self.profile.hold_only_presets:
            # A button press holds for the configured pulse count.
            pulses = max(1, self._coordinator.motor_pulse_count)
            await self.hold_preset(preset, pulses * self.profile.hold_repeat_ms[preset])
            return
        if preset in ("memory_1", "memory_2"):
            packet = profiles.memory_command(self.profile, self._family, int(preset[-1]))
        else:
            packet = profiles.preset_command(self.profile, self._family, preset)
        await self._action(packet, self.profile.touch_release)

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        profiles.check_memory_slot(self.profile, memory_num)
        await self._preset("memory_1" if memory_num == 1 else "memory_2")

    async def program_memory(self, memory_num: int) -> None:
        schedule = profiles.memory_save_schedule(self.profile, self._family, memory_num)
        if len(schedule) == 1:
            # Sleep Smart's memory dialog writes its one frame without a release.
            await self.write_command(schedule[0][1])
            return
        await self._schedule(schedule)

    async def factory_reset(self) -> None:
        if not self.profile.factory_reset:
            raise NotImplementedError("Only the Sleep Smart app exposes a factory reset")
        await self.write_command(codec.FACTORY_RESET)

    async def query_massage(self) -> None:
        """Send the massage-tab parameter query at its 100/250/450 ms offsets."""
        if not self._reports_massage_mode:
            raise NotImplementedError("Only the Sleep Smart massage tab sends this query")
        await self._schedule(self.profile.massage_query)

    async def hold_preset(self, preset: str, duration_ms: int) -> None:
        """Run a bounded held preset with the selected app's cadence and release.

        MOTIONrelax P2 holds flat or a memory. Sleep Smart presets and memory A
        are hold-only: a 200 ms refresh while held, then the release at +100 ms.
        """
        if not self.supports_preset_hold:
            raise NotImplementedError("Held presets are unavailable for this app profile")
        if preset not in self.held_preset_options:
            raise ValueError(f"Held preset must be one of {', '.join(self.held_preset_options)}")
        held = cast(HeldPreset, preset)
        cadence = self.profile.hold_repeat_ms[held]
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not cadence <= duration_ms <= 60000
        ):
            raise ValueError(f"Preset hold duration must be {cadence}..60000 milliseconds")
        packet = profiles.held_preset_command(self.profile, self._family, held)
        if self._coordinator.cancel_command.is_set():
            return
        loop = asyncio.get_running_loop()
        started = loop.time()
        release_started: float | None = None
        try:
            for tick in range((duration_ms + cadence - 1) // cadence):
                if tick and loop.time() >= started + duration_ms / 1000:
                    break
                await self.write_command(packet)
                next_offset = min(duration_ms, (tick + 1) * cadence)
                if not await self._pause(max(0, started + next_offset / 1000 - loop.time())):
                    return
            if held in self.profile.hold_final_frame:
                # The repeating-button terminal touch-up dispatch.
                release_started = loop.time()
                await self.write_command(packet)
        finally:
            await self._schedule(self.profile.touch_release, cleanup=True, started=release_started)

    async def stop_all(self) -> None:
        await self.write_command(codec.SHORT_RELEASE, cancel_event=asyncio.Event())

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise NotImplementedError("The selected layout has no light control")
        await self._action(
            profiles.light_command(self.profile, self._family), self.profile.light_releases
        )

    async def massage_off(self) -> None:
        if not self.supports_massage:
            raise NotImplementedError("The selected layout has no massage control")
        await self.write_command(codec.massage_stop())

    async def massage_mode_step(self) -> None:
        if not self.supports_massage:
            raise NotImplementedError("The selected layout has no massage control")
        await self._action(codec.massage_mode(), self.profile.massage_mode_releases)

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in self.massage_intensity_zones:
            raise ValueError("Massage zone is absent from the selected layout")
        zones: dict[str, MassageZone] = {"head": "back", "foot": "legs", "right": "right"}
        await self.write_command(profiles.massage_command(zones[zone], level))

    def get_massage_state(self) -> dict[str, int]:
        return dict(self._massage_state)

    def get_light_state(self) -> dict[str, bool]:
        if "under_bed_lights_on" not in self._light_state:
            return {}
        return {"is_on": self._light_state["under_bed_lights_on"]}

    def validate_device_rename(self, name: str) -> None:
        self.profile.name_rule.encode(name)

    async def rename_device(self, name: str) -> None:
        rename_transport = self._rename_transport
        if rename_transport is None:
            raise NotImplementedError("The selected transport has no rename characteristic")
        await self._schedule(
            profiles.rename_schedule(self.profile, rename_transport, name),
            uuid=TRANSPORTS[rename_transport].name_uuid,
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
        if not self.supports_clock_alarm:
            raise NotImplementedError("Only the phone app P1 surface exposes a BLE alarm")
        if any(isinstance(day, bool) or day not in range(7) for day in weekdays):
            raise ValueError("Alarm weekdays must use Monday=0 through Sunday=6")
        if preset not in ("flat", "zero_g", "anti_snore", "memory_1", "memory_2"):
            raise ValueError("Alarm preset is unsupported")
        packet = codec.alarm(
            enabled,
            tuple(day in weekdays for day in range(7)),
            hour,
            minute,
            cast(profiles.Wake, preset),
            head_level,
            foot_level,
        )
        await self.write_command(packet)

    async def _sync_clock(self) -> None:
        if self.profile.clock_request_length is None:
            raise NotImplementedError("The tablet app has no clock writer")
        # The phone always builds a P1 clock, including for the P2 family.
        await self._write_to(self.control_characteristic_uuid, codec.clock(dt_util.now()))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._initialized:
            return
        if not self._discovered:
            await self.async_discover_capabilities()
        assert self._transport_id is not None
        transport = TRANSPORTS[self._transport_id]
        if self._sleep_smart:
            await self._start_sleep_smart_notify(transport)
            return
        try:
            if not await self._pause(self.profile.subscribe_delay_ms / 1000):
                raise asyncio.CancelledError
            client = self.client
            if client is None:
                raise ConnectionError("Not connected to bed")
            await client.start_notify(transport.notify_uuid, self._notification_handler)
            self._subscribed.append(transport.notify_uuid)
            # Finish initialization even if a query reports a family mismatch.
            # User controls remain guarded by write_command.
            if self._has_startup_profile:
                loop = asyncio.get_running_loop()
                started = loop.time()
                if not await self._schedule(
                    self.profile.startup[self._family],
                    uuid=self.control_characteristic_uuid,
                    started=started,
                ):
                    raise asyncio.CancelledError
                clock_offsets = self.profile.clock_startup_offsets
                name_offset = self.profile.name_subscribe_ms if self._transport_id == "t3" else None
                late_offsets = sorted({*clock_offsets, *filter(None, (name_offset,))})
                for offset in late_offsets:
                    if not await self._pause(max(0, started + offset / 1000 - loop.time())):
                        raise asyncio.CancelledError
                    if offset == name_offset and transport.name_uuid:
                        await client.start_notify(transport.name_uuid, self._notification_handler)
                        self._subscribed.append(transport.name_uuid)
                    if offset in clock_offsets:
                        await self._sync_clock()
            self._initialized = True
        except BaseException:
            await self.stop_notify()
            raise

    async def _subscribe_optional(self, uuid: str) -> bool:
        client = self.client
        if client is None:
            raise ConnectionError("Not connected to bed")
        try:
            async with self._ble_lock:
                await client.start_notify(uuid, self._notification_handler)
        except BleakError:
            _LOGGER.debug("Sleep Smart subscription to %s failed", uuid, exc_info=True)
            return False
        self._subscribed.append(uuid)
        return True

    async def _start_sleep_smart_notify(self, transport: Transport) -> None:
        """Subscribe like Sleep Smart; only T3's two subscriptions start its queries.

        The app subscribes every recognized notify role, and both T3
        subscriptions emit its ready event whichever transport carries writes.
        T1 or T2 without T3 never become ready, so they stay quiet until the
        user sends a command. A failed T3 subscription likewise leaves the
        connection usable without the startup queries.
        """
        try:
            if not await self._pause(self.profile.subscribe_delay_ms / 1000):
                raise asyncio.CancelledError
            client = self.client
            if client is None:
                raise ConnectionError("Not connected to bed")
            async with self._ble_lock:
                await client.start_notify(transport.notify_uuid, self._notification_handler)
            self._subscribed.append(transport.notify_uuid)
            # Every other data notify role the app finds is subscribed too.
            for key in self._notify_roles:
                if key not in (self._transport_id, "t3"):
                    await self._subscribe_optional(TRANSPORTS[key].notify_uuid)
            ready = False
            t3 = TRANSPORTS["t3"]
            if "t3" in self._notify_roles and "t3" in self._name_roles and t3.name_uuid:
                data_ready = self._transport_id == "t3" or await self._subscribe_optional(
                    t3.notify_uuid
                )
                if not await self._pause(self.profile.name_subscribe_ms / 1000):
                    raise asyncio.CancelledError
                name_ready = await self._subscribe_optional(t3.name_uuid)
                ready = data_ready and name_ready
            if ready and not await self._schedule(
                self.profile.startup[self._family],
                uuid=self.control_characteristic_uuid,
            ):
                raise asyncio.CancelledError
            self._initialized = True
        except BaseException:
            await self.stop_notify()
            raise

    def _notification_handler(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        notification = profiles.parse_notification(self.profile, bytes(data))
        if notification is None:
            return
        updates: list[StateUpdate] = []
        if notification.middle is not None:
            self._family_matches = notification.middle == (self._family == "p2")
            updates.append(FAMILY_MATCH(self._family_matches))
        if notification.light_on is not None and self.supports_lights:
            self._light_state["under_bed_lights_on"] = notification.light_on
            updates.append(UNDER_BED_LIGHTS_ON(notification.light_on))
        if self.supports_massage:
            for zone, raw_level in (
                ("head", notification.massage_back),
                ("right" if self._layout == "split_series" else "foot", notification.massage_legs),
            ):
                if raw_level is not None and raw_level in WIRE_MASSAGE_LEVELS:
                    level = WIRE_MASSAGE_LEVELS.index(raw_level)
                    self._massage_state[f"{zone}_intensity"] = level
                    updates.append(massage_intensity(zone)(level))
        if notification.massage_mode_reported and self._reports_massage_mode:
            updates.append(MASSAGE_MODE(notification.massage_mode))
        if notification.alarm is not None and self.supports_clock_alarm:
            updates += [
                ALARM(notification.alarm.enabled),
                ALARM_CONFIG(asdict(notification.alarm)),
            ]
        if updates:
            self.forward_controller_state_updates(*updates)
        if notification.clock_requested:
            idle = self._clock_task is None or self._clock_task.done()
            # Sleep Smart answers every request; MOTIONrelax drops one that
            # arrives while an earlier request is still being answered.
            if idle or self._sleep_smart:
                self._clock_requests += 1
            if idle:
                self._clock_task = asyncio.create_task(self._answer_clock_requests())

    async def _answer_clock_requests(self) -> None:
        while self._clock_requests:
            self._clock_requests -= 1
            await self._respond_to_clock_request()

    async def _respond_to_clock_request(self) -> None:
        async def send(controller: BedController) -> None:
            if isinstance(controller, LogicdataAppController):
                await controller._sync_clock()

        try:
            await self._coordinator.async_execute_controller_command(
                send, cancel_running=False, skip_disconnect=True
            )
        except ConnectionError, ValueError:
            _LOGGER.debug("Unable to answer MOTIONrelax clock request", exc_info=True)

    async def stop_notify(self) -> None:
        if self._clock_task is not None:
            self._clock_task.cancel()
            await asyncio.gather(self._clock_task, return_exceptions=True)
            self._clock_task = None
        self._clock_requests = 0
        client = self.client
        try:
            if client is not None and client.is_connected:
                for uuid in self._subscribed:
                    try:
                        async with self._ble_lock:
                            await client.stop_notify(uuid)
                    except Exception:
                        _LOGGER.debug(
                            "Unable to unsubscribe MOTIONrelax characteristic", exc_info=True
                        )
        finally:
            self._subscribed.clear()
            self._initialized = False
            self._notify_callback = None

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self.move_axis("head", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self.move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self.move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def move_bed_height_up(self) -> None:
        await self.move_axis("bed_height", True)

    async def move_bed_height_down(self) -> None:
        await self.move_axis("bed_height", False)

    async def move_bed_height_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("MOTIONrelax has no separate feet axis")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("MOTIONrelax has no separate feet axis")

    async def move_feet_stop(self) -> None:
        await self.stop_all()


def require_app_transport(client: BleakClient, data: Mapping[str, Any]) -> None:
    """Raise ConnectionError unless the link exposes the selected app's transport.

    A guided change checks a candidate link with the controller's own transport
    selection, so the check is exactly what the runtime will require.
    """
    link = cast("AdjustableBedCoordinator", SimpleNamespace(client=client, controller_state={}))
    controller = LogicdataAppController(
        link,
        profile=data[CONF_LOGICDATA_APP_PROFILE],
        command_family=data[CONF_LOGICDATA_APP_FAMILY],
        layout=data[CONF_LOGICDATA_APP_LAYOUT],
        transport=data.get(CONF_LOGICDATA_APP_TRANSPORT, "auto"),
        has_light=False,
        has_massage=False,
    )
    try:
        controller._select_transport(client)  # noqa: SLF001 - the controller's own selection
    except ValueError as err:
        raise ConnectionError(str(err)) from err


async def build_controller(ctx: BuildContext) -> LogicdataAppController:
    """Build the controller for the stored app profile."""
    data = ctx.data
    return LogicdataAppController(
        ctx.coordinator,
        profile=data[CONF_LOGICDATA_APP_PROFILE],
        command_family=data[CONF_LOGICDATA_APP_FAMILY],
        layout=data[CONF_LOGICDATA_APP_LAYOUT],
        transport=data.get(CONF_LOGICDATA_APP_TRANSPORT, "auto"),
        has_light=data.get(CONF_HAS_LIGHT, HAS_LIGHT_DEFAULTS[BED_TYPE_LOGICDATA_APP]),
        has_massage=data.get(CONF_HAS_MASSAGE, False),
    )
