"""Comfort Motion 2.2.1 app profile, from accepted row115 evidence.

The explicit app profile owns this controller; shared UUIDs do not identify
it. Movement, presets and memory come from the shared Jiecang glue. This
module keeps what the app does differently: enumeration-order transport
selection, header-independent status replies, desired-state lights, rename
and its wake routine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from ..codec import jiecang as codec
from ..profiles.jiecang import COMFORT_MOTION, memory_command, preset_command
from .jiecang import JiecangProfileController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator
    from ..profiles.jiecang import Layout

MassageKey = Literal["head", "foot"]
# The app's head and foot massage drive the back and legs zones.
_MASSAGE_ZONES: dict[MassageKey, codec.MassageZone] = {"head": "back", "foot": "legs"}
_WAKE_PRESETS = ("zero_g", "flat", "anti_snore", "memory_1", "memory_2")


class ComfortMotionController(JiecangProfileController):
    """Control explicit physical axes, retaining reported state across layout replies."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str,
        transport: str = "auto",
        has_light: bool = True,
    ) -> None:
        selected: Layout | None = next(
            (key for key in COMFORT_MOTION.layouts if key == layout), None
        )
        if selected is None or transport not in ("auto", *COMFORT_MOTION.transports):
            raise ValueError("Comfort Motion supports 2/3/4-motor layouts and G1/G2 only")
        super().__init__(coordinator, COMFORT_MOTION, selected)
        self._preference = transport
        self._has_light = has_light
        self._name_uuid: str | None = None
        self._name_response = True
        self._notify_uuids: list[str] = []
        self._subscriptions: list[str] = []
        self._started = False
        self._transport = ""
        state = coordinator.controller_state
        self._reported_layout = state.get("comfort_motion_layout")
        self._levels: dict[MassageKey, int] = {
            zone: state.get(f"comfort_motion_{zone}_wire", 0) for zone in _MASSAGE_ZONES
        }
        self._light = state.get("under_bed_lights_on")

    def _select_transport(self) -> None:
        if self.client is None or self.client.services is None:
            raise ConnectionError("Discover GATT services before controlling Comfort Motion")
        self._notify_uuids = []
        self._write_uuid = ""
        self._name_uuid = None
        # The app's independent service branches use enumeration order. Keep all
        # matching subscriptions, but never retain a name role from an old link.
        for service in self.client.services:
            for key in self.profile.transports:
                transport = codec.TRANSPORTS[key]
                if service.uuid.lower() != transport.service_uuid or self._preference not in (
                    "auto",
                    key,
                ):
                    continue
                write = service.get_characteristic(transport.write_uuid)
                notify = service.get_characteristic(transport.notify_uuid)
                if write is None or notify is None:
                    continue
                if not {"write", "write-without-response"}.intersection(write.properties):
                    continue
                self._write_uuid = transport.write_uuid
                self._write_with_response = "write" in write.properties
                self._transport = key
                self._notify_uuids.append(transport.notify_uuid)
                name = (
                    service.get_characteristic(transport.name_uuid) if transport.name_uuid else None
                )
                if name and {"write", "write-without-response"}.intersection(name.properties):
                    self._name_uuid = transport.name_uuid
                    self._name_response = "write" in name.properties
        if not self._write_uuid:
            raise ConnectionError("No Comfort Motion G1/G2 write and notification roles")

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app_profile": "comfort_motion",
            "layout": self.layout,
            "reported_layout": self._reported_layout,
            "transport": self._transport,
            "massage_wire_levels": dict(self._levels),
        }

    async def async_discover_capabilities(self) -> None:
        await self.start_notify()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._started:
            return
        self._select_transport()
        assert self.client is not None
        cancel = self._coordinator.cancel_command
        started = asyncio.get_running_loop().time()
        try:
            if await self._pause(100, cancel):
                raise ConnectionError("Comfort Motion setup cancelled")
            for uuid in self._notify_uuids:
                await self.client.start_notify(uuid, self._handle_notification)
                self._subscriptions.append(uuid)
            # Await HA's subscription, then preserve the source query offsets.
            # No layout, massage, ACK or descriptor-result gate suppresses queries.
            for offset, command in self.profile.bootstrap:
                elapsed = (asyncio.get_running_loop().time() - started) * 1000
                if await self._pause(offset - elapsed, cancel):
                    raise ConnectionError("Comfort Motion setup cancelled")
                await self.write_command(command)
            self._started = True
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        error: Exception | None = None
        try:
            if self.client is not None and self.client.is_connected:
                for uuid in self._subscriptions:
                    try:
                        await self.client.stop_notify(uuid)
                    except Exception as exc:
                        error = error or exc
        finally:
            self._subscriptions.clear()
            self._started = False
            self._notify_callback = None
        if error is not None:
            raise error

    def _handle_notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """The app dispatches on byte 2 under any header, keeping raw massage bytes."""
        self.forward_raw_notification(sender.uuid, bytes(data))
        if len(data) >= 7 and data[2] == 0x0F:
            self._reported_layout = data[4] if data[4] in range(1, 7) else 0
        elif len(data) >= 9 and data[2] in (0x05, 0x06):
            self._light = bool(data[8] & 0x40)
            if data[2] == 0x06:
                self._levels["head"] = data[4]
                self._levels["foot"] = data[6]
        else:
            return
        # Layout replies do not reset selected axes, zone state or intensities.
        updates: dict[str, object] = {"comfort_motion_layout": self._reported_layout}
        updates.update(
            {f"comfort_motion_{zone}_wire": value for zone, value in self._levels.items()}
        )
        if self._light is not None:
            updates["under_bed_lights_on"] = self._light
        updates.update(self.get_massage_state())
        self.forward_controller_state_updates(updates)

    async def move_lumbar_up(self) -> None:
        await self._move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

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
        return list(_MASSAGE_ZONES)

    def get_massage_state(self) -> dict[str, object]:
        levels = self.profile.massage_levels
        return {
            f"{zone}_intensity": levels.index(value) if value in levels else None
            for zone, value in self._levels.items()
        }

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in _MASSAGE_ZONES or level not in range(len(self.profile.massage_levels)):
            raise ValueError("Comfort Motion massage accepts head/foot levels 0..3")
        await self.write_command(
            codec.massage(_MASSAGE_ZONES[zone], self.profile.massage_levels[level])
        )
        # Only tag06 changes stored levels, never a speculative write result.

    async def _massage_step(self, zone: MassageKey, up: bool) -> None:
        levels = self.profile.massage_levels
        value = self._levels[zone]
        if value in levels:
            index = levels.index(value) + (1 if up else -1)
            if index in range(len(levels)):
                await self.set_massage_intensity(zone, index)

    async def massage_head_up(self) -> None:
        await self._massage_step("head", True)

    async def massage_head_down(self) -> None:
        await self._massage_step("head", False)

    async def massage_foot_up(self) -> None:
        await self._massage_step("foot", True)

    async def massage_foot_down(self) -> None:
        await self._massage_step("foot", False)

    async def massage_mode_step(self) -> None:
        await self.write_command(codec.massage_mode())

    async def massage_off(self) -> None:
        await self.write_command(codec.massage_stop())

    # Lights

    @property
    def supports_lights(self) -> bool:
        return self._has_light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._has_light

    async def lights_toggle(self) -> None:
        if not self._has_light:
            raise ValueError("Enable the local light option for this bed")
        await self.write_command(codec.light_toggle())

    @property
    def supports_light_state_feedback(self) -> bool:
        return self._has_light

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def _set_light(self, desired: bool) -> None:
        if self._light is None:
            raise ValueError("Read light state before using a desired-state light action")
        if self._light != desired:
            await self.lights_toggle()

    def get_light_state(self) -> dict[str, object]:
        return {"is_on": self._light} if self._light is not None else {}

    # Rename

    @property
    def supports_device_rename(self) -> bool:
        return self._name_uuid is not None

    def validate_device_rename(self, name: str) -> None:
        self._name_rule.encode(name)

    async def rename_device(self, name: str) -> None:
        payload = self._name_rule.encode(name)
        if self.client is None or not self.client.is_connected or self._name_uuid is None:
            raise ValueError("Comfort Motion rename requires a discovered writable G1 name role")
        async with self._ble_lock:
            await self.client.write_gatt_char(
                self._name_uuid, payload, response=self._name_response
            )

    # Wake routine

    @property
    def supports_wake_routine(self) -> bool:
        return True

    def _wake_command(self, preset: str) -> bytes:
        if preset in ("memory_1", "memory_2"):
            return memory_command(self.profile, int(preset[-1]))
        if preset == "zero_g":
            return preset_command(self.layout, "zero_g")
        if preset == "anti_snore":
            return preset_command(self.layout, "anti_snore")
        return preset_command(self.layout, "flat")

    async def execute_wake_routine(
        self, *, preset: str, head_level: int = 0, foot_level: int = 0
    ) -> None:
        if preset not in _WAKE_PRESETS or any(
            level not in range(4) for level in (head_level, foot_level)
        ):
            raise ValueError("Comfort Motion wake requires a supported preset and levels 0..3")
        if (head_level or foot_level) and not self._coordinator.has_massage:
            raise ValueError("Enable massage before starting a massage wake routine")
        cancel = self._coordinator.cancel_command
        started = asyncio.get_running_loop().time()
        completed = False
        try:
            for offset, zone, level in ((0, "head", head_level), (200, "foot", foot_level)):
                elapsed = (asyncio.get_running_loop().time() - started) * 1000
                if await self._pause(offset - elapsed, cancel):
                    return
                if level:
                    await self.set_massage_intensity(zone, level)
                    if await self._pause(100, cancel):
                        return
                    await self.stop_all()
            elapsed = (asyncio.get_running_loop().time() - started) * 1000
            if not await self._pause(500 - elapsed, cancel):
                await self.write_command(self._wake_command(preset))
                completed = True
        finally:
            if not completed:
                await self.stop_all()

    async def stop_wake_routine(self) -> None:
        await self.massage_off()
