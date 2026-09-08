"""MOTIONrelax phone/tablet app protocols with explicit layout and transport."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import asdict
from typing import TYPE_CHECKING, cast

from homeassistant.util import dt as dt_util

from .. import logicdata_app_protocol as protocol
from .base import (
    BedController,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _motor_callback(axis: str, up: bool) -> MotorCommandCallable:
    async def move(controller: BedController) -> None:
        if not isinstance(controller, LogicdataAppController):
            raise TypeError("MOTIONrelax motor requires its app controller")
        await controller.move_axis(axis, up)

    return move


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
        if profile not in protocol.APP_PROFILES or command_family not in protocol.FAMILIES:
            raise ValueError("Select a supported MOTIONrelax app edition and packet family")
        if layout not in protocol.LAYOUTS or (command_family == "p2") != (layout == "middle"):
            raise ValueError("The middle layout requires P2; other layouts require P1")
        if transport not in (*protocol.TRANSPORTS, "auto"):
            raise ValueError("Select a supported MOTIONrelax transport")
        self._profile: protocol.AppProfile = profile
        self._family: protocol.Family = command_family
        self._layout: protocol.Layout = layout
        self._transport_choice = transport
        self._transport_id: protocol.TransportProfile | None = (
            None if transport == "auto" else cast(protocol.TransportProfile, transport)
        )
        self._has_light = has_light
        self._has_massage = has_massage and command_family == "p1"
        self._subscribed: list[str] = []
        self._clock_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._discovered = False
        self._has_startup_profile = False
        self._family_matches: bool | None = None
        self._massage_state: dict[str, int] = {}
        self._light_state: dict[str, bool] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        if self._transport_id is None:
            return ""
        return protocol.TRANSPORTS[self._transport_id].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        """Reserve the last cadence interval for terminal movement and release."""
        cadence = protocol.MOVEMENT_REPEAT_MS
        return max(0, (duration_ms + cadence - 1) // cadence - 1)

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Report the app cadence to generic timed-movement planning."""
        return self._coordinator.motor_pulse_count, protocol.MOVEMENT_REPEAT_MS

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_preset_hold(self) -> bool:
        return self._family == "p2"

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._family == "p1"

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._family == "p1"

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
        return self._transport_id in ("t1", "t3")

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in protocol.layout_axes(self._layout)

    @property
    def has_bed_height_support(self) -> bool:
        return "bed_height" in protocol.layout_axes(self._layout)

    @property
    def supports_clock_alarm(self) -> bool:
        return self._profile == "phone" and self._family == "p1"

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
            for axis in protocol.layout_axes(self._layout)
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        active = set(protocol.layout_axes(self._layout))
        return frozenset(
            axis
            for layout in protocol.LAYOUTS
            for axis in protocol.layout_axes(layout)
            if axis not in active
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset() if self.supports_clock_alarm else frozenset({"logicdata_app_alarm"})

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self.supports_lights:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="under_bed_lights",
                translation_key="under_bed_lights",
                state_key="under_bed_lights_on",
                icon="mdi:lightbulb",
            ),
        )

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset() if self.supports_lights else frozenset({"under_bed_lights"})

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [
            ControllerStateSensorSpec(
                key="logicdata_app_family_match",
                translation_key="logicdata_app_family_match",
                state_key="logicdata_app_family_match",
                icon="mdi:bed",
                entity_registry_enabled_default=False,
            ),
        ]
        if self.supports_clock_alarm:
            specs.append(
                ControllerStateSensorSpec(
                    key="logicdata_app_alarm",
                    translation_key="logicdata_app_alarm",
                    state_key="logicdata_app_alarm",
                    icon="mdi:alarm",
                    attribute_keys=("logicdata_app_alarm_config",),
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
        candidates = []
        for key, transport in protocol.TRANSPORTS.items():
            service = client.services.get_service(transport.service_uuid)
            if service is None:
                continue
            uuids = {char.uuid.lower() for char in service.characteristics}
            required = {transport.write_uuid, transport.notify_uuid}
            if transport.rename_uuid:
                required.add(transport.rename_uuid)
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
        self._get_characteristic(self.control_characteristic_uuid)
        self._has_startup_profile = any(key in ("t1", "t3") for key in candidates)
        self._discovered = True

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
            protocol.P1_RELEASE,
            protocol.P2_RELEASE,
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

    async def _action(self, packet: bytes, action: protocol.Action) -> None:
        if self._coordinator.cancel_command.is_set():
            return
        started = asyncio.get_running_loop().time()
        try:
            await self.write_command(packet)
        finally:
            await self._schedule(
                protocol.release_schedule(action, self._family, self._profile),
                cleanup=True,
                started=started,
            )

    async def move_axis(self, axis: str, up: bool) -> None:
        if axis not in protocol.layout_axes(self._layout):
            raise ValueError("Motor axis is absent from the selected layout")
        packet = protocol.motion_command(self._family, self._layout, axis, up)
        if self._coordinator.cancel_command.is_set():
            return
        loop = asyncio.get_running_loop()
        started = loop.time()
        release_started: float | None = None
        try:
            for tick in range(self._coordinator.motor_pulse_count):
                await self.write_command(packet)
                if not await self._pause(
                    max(0, started + (tick + 1) * protocol.MOVEMENT_REPEAT_MS / 1000 - loop.time())
                ):
                    return
            # Touch-up dispatches one terminal repeat before its delayed release.
            release_started = loop.time()
            await self.write_command(packet)
        finally:
            await self._schedule(
                protocol.release_schedule("movement", self._family, self._profile),
                cleanup=True,
                started=release_started,
            )

    async def preset_flat(self) -> None:
        await self._action(protocol.preset_command(self._family, "flat"), "flat")

    async def preset_zero_g(self) -> None:
        await self._action(protocol.preset_command(self._family, "zero_g"), "preset")

    async def preset_anti_snore(self) -> None:
        await self._action(protocol.preset_command(self._family, "anti_snore"), "preset")

    async def preset_memory(self, memory_num: int) -> None:
        await self._action(protocol.memory_command(self._family, memory_num), "memory")

    async def program_memory(self, memory_num: int) -> None:
        packet = protocol.memory_command(self._family, memory_num, save=True)
        await self._schedule(((0, packet), (30, packet), (60, packet)))

    async def hold_preset(self, preset: str, duration_ms: int) -> None:
        """Run the P2 app's bounded flat or memory hold with its own cadence."""
        if not self.supports_preset_hold:
            raise NotImplementedError("Held presets belong to the P2 app surface")
        if preset not in ("flat", "memory_1", "memory_2"):
            raise ValueError("Held preset must be flat, memory_1, or memory_2")
        cadence = (
            protocol.MOVEMENT_REPEAT_MS if preset == "flat" else protocol.MEMORY_HOLD_REPEAT_MS
        )
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not cadence <= duration_ms <= 60000
        ):
            raise ValueError(f"Preset hold duration must be {cadence}..60000 milliseconds")
        packet = (
            protocol.preset_command(self._family, "flat")
            if preset == "flat"
            else protocol.memory_command(self._family, 1 if preset == "memory_1" else 2)
        )
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
            if preset == "flat":
                # Flat uses the repeating-button terminal touch-up dispatch.
                release_started = loop.time()
                await self.write_command(packet)
        finally:
            await self._schedule(
                ((100, protocol.P1_RELEASE),), cleanup=True, started=release_started
            )

    async def stop_all(self) -> None:
        await self.write_command(protocol.P1_RELEASE, cancel_event=asyncio.Event())

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise NotImplementedError("The selected layout has no light control")
        await self._action(protocol.light_command(self._family), "light")

    async def massage_off(self) -> None:
        if not self.supports_massage:
            raise NotImplementedError("The selected layout has no massage control")
        await self.write_command(protocol.MASSAGE_STOP)

    async def massage_mode_step(self) -> None:
        if not self.supports_massage:
            raise NotImplementedError("The selected layout has no massage control")
        await self._action(protocol.MASSAGE_MODE, "massage_mode")

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in self.massage_intensity_zones:
            raise ValueError("Massage zone is absent from the selected layout")
        zones: dict[str, protocol.MassageZone] = {"head": "back", "foot": "legs", "right": "right"}
        protocol_zone = zones[zone]
        await self.write_command(protocol.massage_command(protocol_zone, level))

    def get_massage_state(self) -> dict[str, int]:
        return dict(self._massage_state)

    def get_light_state(self) -> dict[str, bool]:
        if "under_bed_lights_on" not in self._light_state:
            return {}
        return {"is_on": self._light_state["under_bed_lights_on"]}

    async def rename_device(self, name: str) -> None:
        if not self.supports_device_rename or self._transport_id is None:
            raise NotImplementedError("The selected transport has no rename characteristic")
        transport = protocol.TRANSPORTS[self._transport_id]
        await self._schedule(
            protocol.rename_schedule(self._profile, self._transport_id, name),
            uuid=transport.rename_uuid,
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
        packet = protocol.alarm_command(
            enabled,
            tuple(day in weekdays for day in range(7)),
            hour,
            minute,
            cast(protocol.Wake, preset),
            head_level,
            foot_level,
        )
        await self.write_command(packet)

    async def _sync_clock(self) -> None:
        if self._profile != "phone":
            raise NotImplementedError("The tablet app has no clock writer")
        await self._write_to(self.control_characteristic_uuid, protocol.clock_command(dt_util.now()))

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._initialized:
            return
        if not self._discovered:
            await self.async_discover_capabilities()
        assert self._transport_id is not None
        transport = protocol.TRANSPORTS[self._transport_id]
        try:
            if not await self._pause(1.0):
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
                    protocol.startup_schedule(self._profile, self._family),
                    uuid=self.control_characteristic_uuid,
                    started=started,
                ):
                    raise asyncio.CancelledError
                late_offsets = (
                    protocol.CLOCK_STARTUP_OFFSETS
                    if self._profile == "phone"
                    else ((3000,) if self._transport_id == "t3" else ())
                )
                for offset in late_offsets:
                    if not await self._pause(max(0, started + offset / 1000 - loop.time())):
                        raise asyncio.CancelledError
                    if offset == 3000 and self._transport_id == "t3" and transport.rename_uuid:
                        await client.start_notify(transport.rename_uuid, self._notification_handler)
                        self._subscribed.append(transport.rename_uuid)
                    if self._profile == "phone":
                        await self._sync_clock()
            self._initialized = True
        except BaseException:
            await self.stop_notify()
            raise

    def _notification_handler(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        notification = protocol.parse_notification(self._profile, bytes(data))
        if notification is None:
            return
        updates: dict[str, object] = {}
        if notification.middle is not None:
            self._family_matches = notification.middle == (self._family == "p2")
            updates["logicdata_app_family_match"] = self._family_matches
        if notification.light_on is not None and self.supports_lights:
            self._light_state["under_bed_lights_on"] = notification.light_on
            updates.update(self._light_state)
        if self.supports_massage:
            for zone, raw_level in (
                ("head", notification.massage_back),
                ("right" if self._layout == "split_series" else "foot", notification.massage_legs),
            ):
                if raw_level is not None and raw_level in protocol.WIRE_MASSAGE_LEVELS:
                    level = protocol.WIRE_MASSAGE_LEVELS.index(raw_level)
                    self._massage_state[f"{zone}_intensity"] = level
                    updates[f"{zone}_intensity"] = level
        if notification.alarm is not None and self.supports_clock_alarm:
            updates["logicdata_app_alarm"] = notification.alarm.enabled
            updates["logicdata_app_alarm_config"] = asdict(notification.alarm)
        if updates:
            self.forward_controller_state_updates(updates)
        if notification.clock_requested and (self._clock_task is None or self._clock_task.done()):
            self._clock_task = asyncio.create_task(self._respond_to_clock_request())

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
        client = self.client
        try:
            if client is not None and client.is_connected:
                for uuid in self._subscribed:
                    try:
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
