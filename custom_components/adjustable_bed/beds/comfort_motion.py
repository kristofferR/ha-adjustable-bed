"""Comfort Motion 2.2.1 direct BLE behavior, accepted row115 evidence.

The explicit app profile owns this controller. Shared UUIDs do not identify it.
Only reachable fixed literals are sent; no general checksum builder is inferred.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..const import (
    COMFORT_MOTION_BTNAME_CHAR_UUID,
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

LAYOUT_AXES = {
    "standard_2": ("back", "both", "legs"),
    "standard_3_neck": ("head", "back", "legs"),
    "standard_4_legacy": ("head", "back", "lumbar", "legs"),
}
MOTION = {
    "back": (bytes.fromhex("f1f1010101037e"), bytes.fromhex("f1f1020101047e")),
    "legs": (bytes.fromhex("f1f1030101057e"), bytes.fromhex("f1f1040101067e")),
    "both": (bytes.fromhex("f1f1050101077e"), bytes.fromhex("f1f1060101087e")),
    "head": (bytes.fromhex("f1f11901011b7e"), bytes.fromhex("f1f11a01011c7e")),
    "lumbar": (bytes.fromhex("f1f11b01011d7e"), bytes.fromhex("f1f11c01011e7e")),
}
RELEASE = bytes.fromhex("f1f14e004e7e")
PRESETS = {
    "zero_g": bytes.fromhex("f1f1070101097e"),
    "flat": bytes.fromhex("f1f10801010a7e"),
    "anti_snore": bytes.fromhex("f1f10901010b7e"),
    "memory_1": bytes.fromhex("f1f10b01010d7e"),
    "memory_2": bytes.fromhex("f1f10d01010f7e"),
}
MEMORY_SAVE = (bytes.fromhex("f1f10a01010c7e"), bytes.fromhex("f1f10c01010e7e"))
MASSAGE = {
    "head": tuple(
        bytes.fromhex(value)
        for value in (
            "f1f1120208001c7e",
            "f1f1120208021e7e",
            "f1f1120208031f7e",
            "f1f112020804207e",
        )
    ),
    "foot": tuple(
        bytes.fromhex(value)
        for value in (
            "f1f1140208001e7e",
            "f1f114020802207e",
            "f1f114020803217e",
            "f1f114020804227e",
        )
    ),
}
WIRE_LEVELS = (0, 2, 3, 4)
MASSAGE_MODE = bytes.fromhex("f1f116010a217e")
MASSAGE_STOP = bytes.fromhex("f1f11101081a7e")
LIGHT = bytes.fromhex("f1f10f000f7e")
SETUP = (
    (200, bytes.fromhex("f1f1000101027e")),
    (300, bytes.fromhex("f1f1000101027e")),
    (400, bytes.fromhex("f1f1000140417e")),
    (500, bytes.fromhex("f1f1000140417e")),
    (600, bytes.fromhex("f1f1000108097e")),
    (700, bytes.fromhex("f1f1000108097e")),
)
TRANSPORTS = {
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
}


class ComfortMotionController(BedController):
    """Control explicit physical axes, retaining reported state across layout replies."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str,
        transport: str = "auto",
        has_light: bool = True,
    ) -> None:
        super().__init__(coordinator)
        if layout not in LAYOUT_AXES or transport not in ("auto", *TRANSPORTS):
            raise ValueError("Comfort Motion supports 2/3/4-motor layouts and G1/G2 only")
        self.layout = layout
        self._preference = transport
        self._has_light = has_light
        self._write_uuid = ""
        self._name_uuid: str | None = None
        self._name_response = True
        self._subscriptions: list[str] = []
        self._started = False
        self._transport = ""
        state = coordinator.controller_state
        self._reported_layout = state.get("comfort_motion_layout")
        self._levels = {zone: state.get(f"comfort_motion_{zone}_wire", 0) for zone in MASSAGE}
        self._light = state.get("under_bed_lights_on")

    def _select_transport(self) -> list[str]:
        if self.client is None or self.client.services is None:
            raise ConnectionError("Discover GATT services before controlling Comfort Motion")
        subscriptions: list[str] = []
        self._write_uuid = ""
        self._name_uuid = None
        # The app's independent service branches use enumeration order. Keep all
        # matching subscriptions, but never retain a name role from an old link.
        for service in self.client.services:
            for key, (service_uuid, write_uuid, notify_uuid, name_uuid) in TRANSPORTS.items():
                if service.uuid.lower() != service_uuid or self._preference not in ("auto", key):
                    continue
                write = service.get_characteristic(write_uuid)
                notify = service.get_characteristic(notify_uuid)
                if write is None or notify is None:
                    continue
                if not {"write", "write-without-response"}.intersection(write.properties):
                    continue
                self._write_uuid = write_uuid
                self._write_with_response = "write" in write.properties
                self._transport = key
                subscriptions.append(notify_uuid)
                name = service.get_characteristic(name_uuid) if name_uuid else None
                if name and {"write", "write-without-response"}.intersection(name.properties):
                    self._name_uuid = name_uuid
                    self._name_response = "write" in name.properties
        if not self._write_uuid:
            raise ConnectionError("No Comfort Motion G1/G2 write and notification roles")
        return subscriptions

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_uuid

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

    @staticmethod
    async def _pause(milliseconds: float, cancel: asyncio.Event) -> bool:
        if cancel.is_set():
            return True
        if milliseconds > 0:
            try:
                await asyncio.wait_for(cancel.wait(), milliseconds / 1000)
            except TimeoutError:
                return False
            return True
        return False

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")
        if not self._write_uuid:
            self._select_transport()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if await self._pause(repeat_delay_ms if index else 0, cancel):
                return
            async with self._ble_lock:
                await self.client.write_gatt_char(
                    self._write_uuid, command, response=self._write_with_response
                )

    async def async_discover_capabilities(self) -> None:
        await self.start_notify()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._started:
            return
        subscriptions = self._select_transport()
        assert self.client is not None
        cancel = self._coordinator.cancel_command
        started = asyncio.get_running_loop().time()
        try:
            if await self._pause(100, cancel):
                raise ConnectionError("Comfort Motion setup cancelled")
            for uuid in subscriptions:
                await self.client.start_notify(uuid, self._handle_notification)
                self._subscriptions.append(uuid)
            # Await HA's subscription, then preserve the source query offsets.
            # No layout, massage, ACK or descriptor-result gate suppresses queries.
            for offset, command in SETUP:
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
        self.forward_raw_notification(sender.uuid, bytes(data))
        if len(data) >= 7 and data[2] == 0x0F:
            self._reported_layout = data[4] if data[4] in range(1, 7) else 0
        elif len(data) >= 9 and data[2] in (0x05, 0x06):
            self._light = bool(data[8] & 0x40)
            if data[2] == 0x06:
                self._levels.update(head=data[4], foot=data[6])
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

    @property
    def supports_motor_control(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key="back_legs" if axis == "both" else axis,
                open_fn=lambda ctrl, axis=axis: ComfortMotionController._dispatch(ctrl, axis, True),
                close_fn=lambda ctrl, axis=axis: ComfortMotionController._dispatch(
                    ctrl, axis, False
                ),
                stop_fn=lambda ctrl: ctrl.stop_all(),
            )
            for axis in LAYOUT_AXES[self.layout]
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset(MOTION)

    @staticmethod
    async def _dispatch(controller: BedController, axis: str, up: bool) -> None:
        if not isinstance(controller, ComfortMotionController):
            raise ValueError("Comfort Motion motor requires its explicit app profile")
        await controller._move(axis, up)

    async def _move(self, axis: str, up: bool) -> None:
        if axis not in LAYOUT_AXES[self.layout]:
            raise ValueError("Motor is not in the selected physical layout")
        try:
            await self.write_command(
                MOTION[axis][0 if up else 1], self._coordinator.motor_pulse_count
            )
        finally:
            # HA also releases on cancellation, unlike the app's ACTION_CANCEL bug.
            await self._pause(100, asyncio.Event())
            await self.stop_all()

    async def move_head_up(self) -> None:
        await self._move("head", True)

    async def move_head_down(self) -> None:
        await self._move("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._move("back", True)

    async def move_back_down(self) -> None:
        await self._move("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move("legs", True)

    async def move_legs_down(self) -> None:
        await self._move("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        await self.write_command(RELEASE, cancel_event=asyncio.Event())

    async def _recall(self, preset: str) -> None:
        try:
            await self.write_command(PRESETS[preset])
            await self._pause(100, self._coordinator.cancel_command)
        finally:
            await self.stop_all()

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

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
        await self._recall("flat")

    async def preset_zero_g(self) -> None:
        await self._recall("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._recall("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Comfort Motion has two reachable memory slots")
        await self._recall(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Comfort Motion has two reachable memory slots")
        await self.write_command(MEMORY_SAVE[memory_num - 1])

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
        return list(MASSAGE)

    def get_massage_state(self) -> dict[str, object]:
        return {
            f"{zone}_intensity": WIRE_LEVELS.index(value) if value in WIRE_LEVELS else None
            for zone, value in self._levels.items()
        }

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in MASSAGE or level not in range(4):
            raise ValueError("Comfort Motion massage accepts head/foot levels 0..3")
        await self.write_command(MASSAGE[zone][level])
        # Only tag06 changes stored levels, never a speculative write result.

    async def _massage_step(self, zone: str, up: bool) -> None:
        value = self._levels[zone]
        if value in WIRE_LEVELS:
            index = WIRE_LEVELS.index(value) + (1 if up else -1)
            if index in range(4):
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
        await self.write_command(MASSAGE_MODE)

    async def massage_off(self) -> None:
        await self.write_command(MASSAGE_STOP)

    @property
    def supports_lights(self) -> bool:
        return self._has_light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._has_light

    async def lights_toggle(self) -> None:
        if not self._has_light:
            raise ValueError("Enable the local light option for this bed")
        await self.write_command(LIGHT)

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

    @property
    def supports_device_rename(self) -> bool:
        return self._name_uuid is not None

    def validate_device_rename(self, name: str) -> None:
        if re.fullmatch(r"[._0-9A-Za-z]{1,18}", name) is None:
            raise ValueError(
                "Comfort Motion names use 1..18 ASCII letters, digits, dot or underscore"
            )

    async def rename_device(self, name: str) -> None:
        self.validate_device_rename(name)
        if self.client is None or not self.client.is_connected or self._name_uuid is None:
            raise ValueError("Comfort Motion rename requires a discovered writable G1 name role")
        async with self._ble_lock:
            await self.client.write_gatt_char(
                self._name_uuid, name.encode("ascii"), response=self._name_response
            )

    @property
    def supports_wake_routine(self) -> bool:
        return True

    async def execute_wake_routine(
        self, *, preset: str, head_level: int = 0, foot_level: int = 0
    ) -> None:
        if preset not in PRESETS or any(
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
                await self.write_command(PRESETS[preset])
                completed = True
        finally:
            if not completed:
                await self.stop_all()

    async def stop_wake_routine(self) -> None:
        await self.massage_off()
