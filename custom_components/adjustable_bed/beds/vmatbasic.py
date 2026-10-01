"""Explicit V-MAT Basic app controls, without legacy packet or feature inference."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, cast

from ..vmatbasic_state import VMatBasicSessionIntent
from . import vmatbasic_protocol as protocol
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_PREFIX = "vmatbasic_"


async def _cancellable[T](operation: Coroutine[Any, Any, T], event: asyncio.Event) -> T:
    if event.is_set():
        operation.close()
        raise asyncio.CancelledError
    task = asyncio.create_task(operation)
    cancellation = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait((task, cancellation), return_when=asyncio.FIRST_COMPLETED)
        if cancellation in done:
            raise asyncio.CancelledError
        return task.result()
    finally:
        for pending in (task, cancellation):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, cancellation, return_exceptions=True)


class VMatBasicController(BedController):
    """Immutable profile, primary accessory state and cancellable held movement."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: str,
        floor_level: int | None = None,
        floor_minutes: int = 0,
        remember_settings: Callable[[dict[str, int]], None] | None = None,
        session_intent: VMatBasicSessionIntent | None = None,
    ) -> None:
        super().__init__(coordinator)
        if profile not in protocol.PROFILES:
            raise ValueError("Choose an explicit V-MAT Basic app profile")
        if floor_level is not None:
            protocol.integer(
                floor_level, 1 if profile == "xtbox" else 0, 6 if profile == "xtbox" else 255
            )
        protocol.integer(floor_minutes, 0, 255 if profile == "xtbox" else 1439)
        self.profile = profile
        self._floor_level = floor_level
        self._floor_minutes = floor_minutes
        self._remember_settings = remember_settings
        self._intent = session_intent if session_intent is not None else VMatBasicSessionIntent()
        if self._intent.palette not in protocol.PALETTE_OPTIONS:
            raise ValueError("Invalid session palette")
        protocol.integer(self._intent.brightness, 0, 100)

    @property
    def control_characteristic_uuid(self) -> str:
        return protocol.MOTOR_CHAR

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            MotorControlSpec(
                "back",
                "back",
                lambda ctrl: ctrl.move_back_up(),
                lambda ctrl: ctrl.move_back_down(),
                lambda ctrl: ctrl.stop_all(),
                scheduler_resource="motor:*",
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda ctrl: ctrl.move_legs_up(),
                lambda ctrl: ctrl.move_legs_down(),
                lambda ctrl: ctrl.stop_all(),
                scheduler_resource="motor:*",
            ),
        )

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"head", "feet", "lumbar", "tilt", "bed_height"})

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def supports_device_rename(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*protocol.MOTOR_ACTIONS, *(("floor_hold",) if self.profile == "xtbox" else ()))

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        if self.profile == "basic":
            raise ValueError("Linked movement requires CBI or XT-Box receivers")
        await self.async_discover_capabilities()

    @property
    def diagnostic_poll_interval(self) -> float:
        return 3.0

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "explicit_profile": self.profile,
            "floor_requested": {"level": self._floor_level, "minutes": self._floor_minutes},
            "mood_session_intent": {
                "palette": self._intent.palette,
                "brightness": self._intent.brightness,
            },
            "hardware_acknowledgment": False,
            "observed": {
                key: self._coordinator.controller_state.get(_PREFIX + key)
                for key in (
                    "model",
                    "firmware",
                    "temperature",
                    "floor_level_observed",
                    "floor_minutes_observed",
                    "floor_percent_observed",
                    "ed",
                    "rssi",
                    "rssi_source",
                    "rssi_seen_at",
                    "rssi_representation",
                )
            },
        }

    @property
    def diagnostic_advertisement_interval(self) -> float:
        return 2.0

    def update_advertisement_diagnostics(
        self, rssi: int | None, source: str | None, seen_at: float | None
    ) -> None:
        self.forward_controller_state_updates(
            {
                _PREFIX + "rssi": rssi,
                _PREFIX + "rssi_source": source,
                _PREFIX + "rssi_seen_at": seen_at,
                _PREFIX
                + "rssi_representation": "HA advertisement history; remote RSSI read unavailable",
            }
        )

    def _client(self) -> BleakClient:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("V-MAT Basic receiver is not connected")
        return client

    def _characteristic(
        self, service_uuid: str, uuid: str, operation: str
    ) -> BleakGATTCharacteristic:
        client = self._client()
        service = next(
            (item for item in client.services if item.uuid.lower() == service_uuid), None
        )
        if service is None:
            raise ValueError(f"Missing exact V-MAT Basic service {service_uuid}")
        characteristic = next(
            (item for item in service.characteristics if item.uuid.lower() == uuid), None
        )
        if characteristic is None or operation not in characteristic.properties:
            raise ValueError(f"Exact V-MAT Basic characteristic {uuid} cannot {operation}")
        return characteristic

    async def async_discover_capabilities(self) -> None:
        client = self._client()
        services = {item.uuid.lower() for item in client.services}
        if not set(protocol.REQUIRED_SERVICES) <= services:
            raise ValueError("V-MAT Basic requires its control, status and GAP services")
        self._characteristic(protocol.CONTROL_SERVICE, protocol.MOTOR_CHAR, "write")
        if self.profile == "cbi":
            self._characteristic(protocol.CONTROL_SERVICE, protocol.FLOOR_CHAR, "write")
        elif self.profile == "xtbox":
            self._characteristic(protocol.CONTROL_SERVICE, protocol.XT_CHAR, "write")

    async def _write(
        self,
        service: str,
        uuid: str,
        packet: bytes,
        event: asyncio.Event | None = None,
    ) -> None:
        event = event if event is not None else self._coordinator.cancel_command

        async def operation() -> None:
            async with self._ble_lock:
                if event.is_set():
                    raise asyncio.CancelledError
                client = self._client()
                characteristic = self._characteristic(service, uuid, "write")
                payload = (
                    {"hex": "**REDACTED**", "length": len(packet)}
                    if uuid == protocol.NAME_CHAR
                    else self._format_command_trace_payload(packet)
                )
                if payload is not None:
                    self._coordinator.record_command_trace(
                        payload=payload,
                        characteristic_uuid=uuid,
                        characteristic_handle=characteristic.handle,
                        response=True,
                        repeat_count=1,
                        repeat_delay_ms=0,
                        command_origin="_write",
                        controller_class=type(self).__name__,
                    )
                await client.write_gatt_char(characteristic, packet, response=True)

        async with asyncio.timeout(0.8):
            await _cancellable(operation(), event)

    async def _read(self, service: str, uuid: str) -> bytes:
        event = self._coordinator.cancel_command

        async def operation() -> bytes:
            async with self._ble_lock:
                if event.is_set():
                    raise asyncio.CancelledError
                client = self._client()
                characteristic = self._characteristic(service, uuid, "read")
                return bytes(await client.read_gatt_char(characteristic))

        async with asyncio.timeout(0.8):
            return await _cancellable(operation(), event)

    async def _release(self) -> None:
        async def release() -> None:
            async with asyncio.timeout(2):
                await self._write(
                    protocol.CONTROL_SERVICE, protocol.MOTOR_CHAR, b"\xff", asyncio.Event()
                )

        task = asyncio.create_task(release())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def stop_all(self) -> None:
        await self._release()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Control is unavailable for this V-MAT Basic profile")
        protocol.integer(duration_ms, 100, 60000)
        event = self._coordinator.cancel_command
        if event.is_set():
            return
        is_motor = control in protocol.MOTOR_ACTIONS
        packet = bytes((protocol.MOTOR_ACTIONS[control],)) if is_motor else b"\x00\x11"
        uuid = protocol.MOTOR_CHAR if is_motor else protocol.XT_CHAR
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        try:
            budget = asyncio.timeout_at(deadline)
            try:
                async with budget:
                    while not event.is_set():
                        started = asyncio.get_running_loop().time()
                        await self._write(protocol.CONTROL_SERVICE, uuid, packet, event)
                        # Scheduling attempts, not guaranteed wire cadence.
                        delay = max(0, 0.03 - (asyncio.get_running_loop().time() - started))
                        await _cancellable(asyncio.sleep(delay), event)
            except TimeoutError:
                if not budget.expired():
                    raise
            except asyncio.CancelledError:
                if not event.is_set():
                    raise
        finally:
            if is_motor:
                original = sys.exception()
                try:
                    await self._release()
                except Exception:
                    if original is None:
                        raise
                    _LOGGER.debug("STOP failed after earlier operation failure", exc_info=True)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 30,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if command == b"\xff":
            await self.stop_all()
            return
        if len(command) != 1 or command[0] not in protocol.MOTOR_ACTIONS.values():
            raise ValueError("Only the six V-MAT Basic movement bytes are accepted")
        protocol.integer(repeat_count, 1, 2000)
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        if event.is_set():
            return
        try:
            for index in range(repeat_count):
                if event.is_set():
                    break
                started = asyncio.get_running_loop().time()
                await self._write(protocol.CONTROL_SERVICE, protocol.MOTOR_CHAR, command, event)
                if index + 1 < repeat_count:
                    await _cancellable(
                        asyncio.sleep(max(0, 0.03 - (asyncio.get_running_loop().time() - started))),
                        event,
                    )
        finally:
            original = sys.exception()
            try:
                await self._release()
            except Exception:
                if original is None:
                    raise
                _LOGGER.debug("STOP failed after earlier operation failure", exc_info=True)

    async def move_head_up(self) -> None:
        await self.move_back_up()

    async def move_head_down(self) -> None:
        await self.move_back_down()

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.hold_control("back_up", 1000)

    async def move_back_down(self) -> None:
        await self.hold_control("back_down", 1000)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.hold_control("legs_up", 1000)

    async def move_legs_down(self) -> None:
        await self.hold_control("legs_down", 1000)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        raise NotImplementedError("Combined down is held movement, not a flat preset")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("The V-MAT Basic app has no memory recall")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("The V-MAT Basic app has no memory programming")

    def _require(self, profile: str) -> None:
        if self.profile != profile:
            raise ValueError(f"This control requires the {profile} app profile")

    def _setting(self, level: int | None = None, minutes: int | None = None) -> None:
        if level is not None:
            self._floor_level = level
        if minutes is not None:
            self._floor_minutes = minutes
        if self._remember_settings is not None:
            self._remember_settings(
                {
                    **({"floor_level": self._floor_level} if self._floor_level is not None else {}),
                    "floor_minutes": self._floor_minutes,
                }
            )

    async def _send_floor_settings(self) -> None:
        if self.profile == "basic":
            raise ValueError("The Basic profile has no floor controls")
        # Settings UI absence means zero; the separate CBI ON button defaults to 255.
        level = (
            self._floor_level
            if self._floor_level is not None
            else (1 if self.profile == "xtbox" else 0)
        )
        packet = (
            protocol.xt_floor(level, self._floor_minutes)
            if self.profile == "xtbox"
            else protocol.floor(level, self._floor_minutes)
        )
        await self._write(
            protocol.CONTROL_SERVICE,
            protocol.XT_CHAR if self.profile == "xtbox" else protocol.FLOOR_CHAR,
            packet,
        )
        self.forward_controller_state_updates(
            {
                _PREFIX + "floor_level_requested": level,
                _PREFIX + "floor_minutes_requested": self._floor_minutes,
            }
        )

    async def set_floor_level(self, value: float) -> None:
        level = protocol.integer(
            value, 1 if self.profile == "xtbox" else 0, 6 if self.profile == "xtbox" else 255
        )
        if self.profile == "basic":
            raise ValueError("The Basic profile has no floor controls")
        if self._coordinator.cancel_command.is_set():
            return
        self._setting(level=level)
        await self._send_floor_settings()

    async def set_floor_minutes(self, value: float) -> None:
        minutes = protocol.integer(value, 0, 255 if self.profile == "xtbox" else 1439)
        if self.profile == "basic":
            raise ValueError("The Basic profile has no floor controls")
        if self._coordinator.cancel_command.is_set():
            return
        self._setting(minutes=minutes)
        await self._send_floor_settings()

    async def floor_toggle(self) -> None:
        self._require("cbi")
        status = protocol.light_status(
            await self._read(protocol.CONTROL_SERVICE, protocol.FLOOR_CHAR)
        )
        self._publish_floor(status)
        packet = (
            protocol.floor(0, 0)
            if status.level > 0
            else protocol.floor(
                255 if self._floor_level is None else self._floor_level, self._floor_minutes
            )
        )
        await self._write(protocol.CONTROL_SERVICE, protocol.FLOOR_CHAR, packet)

    async def set_mood_palette(self, option: str) -> None:
        self._require("xtbox")
        if option not in protocol.PALETTE_OPTIONS:
            raise ValueError("Choose one of the twenty shipped palette entries")
        if self._coordinator.cancel_command.is_set():
            return
        self._intent.palette = option
        packet = protocol.color_action(
            protocol.PALETTE[protocol.PALETTE_OPTIONS.index(option)], self._intent.brightness
        )
        await self._write(protocol.CONTROL_SERVICE, protocol.XT_CHAR, packet)
        self.forward_controller_state_update(_PREFIX + "mood_palette", option)

    async def set_mood_brightness(self, value: float) -> None:
        self._require("xtbox")
        brightness = protocol.integer(value, 0, 100)
        if self._coordinator.cancel_command.is_set():
            return
        self._intent.brightness = brightness
        packet = protocol.color_action(
            protocol.PALETTE[protocol.PALETTE_OPTIONS.index(self._intent.palette)], brightness
        )
        await self._write(protocol.CONTROL_SERVICE, protocol.XT_CHAR, packet)
        self.forward_controller_state_update(_PREFIX + "mood_brightness", brightness)

    async def set_mood_effect(self, option: str) -> None:
        self._require("xtbox")
        if option not in ("E1", "E2", "E3"):
            raise ValueError("Choose effect E1, E2 or E3")
        await self._write(
            protocol.CONTROL_SERVICE, protocol.XT_CHAR, protocol.effect(int(option[1]))
        )
        self._intent.effect = option
        self.forward_controller_state_update(_PREFIX + "mood_effect", option)

    async def set_mood_speed(self, value: float) -> None:
        self._require("xtbox")
        progress = protocol.integer(value, 0, 255)
        await self._write(protocol.CONTROL_SERVICE, protocol.XT_CHAR, protocol.speed(progress))
        self._intent.speed = progress
        self.forward_controller_state_update(_PREFIX + "mood_speed", progress)

    async def mood_toggle(self) -> None:
        self._require("xtbox")
        await self._write(protocol.CONTROL_SERVICE, protocol.XT_CHAR, b"\x00\x77")

    async def mood_nightlight(self) -> None:
        self._require("xtbox")
        await self._write(protocol.CONTROL_SERVICE, protocol.XT_CHAR, protocol.rgb(0))

    async def massage_action(self, action: str) -> None:
        self._require("xtbox")
        if action not in protocol.MASSAGE_ACTIONS:
            raise ValueError("Unknown shipped massage action")
        await self._write(
            protocol.CONTROL_SERVICE, protocol.XT_CHAR, bytes((0, protocol.MASSAGE_ACTIONS[action]))
        )

    async def rename_device(self, name: str) -> None:
        packet = protocol.rename(name)
        # A single default-MTU ATT write supports twenty bytes; no fragmentation is proven.
        if len(packet) > 20:
            raise ValueError("Encoded device name exceeds the safe twenty-byte write payload")
        await self._write(protocol.GAP_SERVICE, protocol.NAME_CHAR, packet)
        self.forward_controller_state_update(_PREFIX + "device_name", packet.decode("utf-8"))

    def _publish_floor(self, status: protocol.FloorStatus) -> None:
        self.forward_controller_state_updates(
            {
                _PREFIX + "floor_level_observed": status.level,
                _PREFIX + "floor_minutes_observed": status.timer_minutes,
                _PREFIX + "floor_percent_observed": status.display_percent,
            }
        )

    def _clear_read(self, key: str) -> None:
        keys = (
            ("floor_level_observed", "floor_minutes_observed", "floor_percent_observed")
            if key == "floor"
            else (key,)
        )
        self.forward_controller_state_updates({_PREFIX + item: None for item in keys})

    async def async_refresh_diagnostics(self) -> None:
        for key, service, uuid in protocol.READ_ROLES:
            try:
                raw = await self._read(service, uuid)
                if key == "floor":
                    self._publish_floor(protocol.light_status(raw))
                else:
                    value = (
                        protocol.temperature(raw)
                        if key == "temperature"
                        else protocol.motor_status(raw)
                        if key == "ed"
                        else protocol.decode_string(raw)
                    )
                    self.forward_controller_state_update(_PREFIX + key, value)
            except asyncio.CancelledError:
                self._clear_read(key)
                raise
            except Exception as error:
                self._clear_read(key)
                _LOGGER.debug("V-MAT Basic %s read failed: %s", key, error)

    def invalidate_diagnostics(self) -> None:
        for key, _, _ in protocol.READ_ROLES:
            self._clear_read(key)
        self.forward_controller_state_updates(
            {
                _PREFIX + "rssi": None,
                _PREFIX + "rssi_source": None,
                _PREFIX + "rssi_seen_at": None,
                _PREFIX + "rssi_representation": None,
            }
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def button(
            key: str,
            name: str,
            callback: Callable[[VMatBasicController], Coroutine[Any, Any, None]],
        ) -> ControllerButtonSpec:
            return ControllerButtonSpec(
                _PREFIX + key,
                name,
                lambda ctrl: callback(cast(VMatBasicController, ctrl)),
                translation_key=_PREFIX + key,
            )

        specs = [
            button("all_up", "All up", lambda ctrl: ctrl.hold_control("all_up", 1000)),
            button("all_down", "All down", lambda ctrl: ctrl.hold_control("all_down", 1000)),
            button(
                "refresh_info",
                "Refresh device information",
                lambda ctrl: ctrl.async_refresh_diagnostics(),
            ),
        ]
        if self.profile == "cbi":
            specs.append(
                button("floor_toggle", "Floor light toggle", lambda ctrl: ctrl.floor_toggle())
            )
        elif self.profile == "xtbox":
            specs += [
                button(
                    "floor_hold",
                    "Floor light held action",
                    lambda ctrl: ctrl.hold_control("floor_hold", 1000),
                ),
                button("mood_toggle", "Mood light toggle", lambda ctrl: ctrl.mood_toggle()),
                button(
                    "mood_nightlight",
                    "Mood nightlight command",
                    lambda ctrl: ctrl.mood_nightlight(),
                ),
            ]
            for action in protocol.MASSAGE_ACTIONS:
                specs.append(
                    button(
                        "massage_" + action,
                        "Massage " + action.replace("_", " "),
                        lambda ctrl, action=action: ctrl.massage_action(action),
                    )
                )
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.profile != "xtbox":
            return ()
        return (
            ControllerSelectSpec(
                _PREFIX + "mood_palette",
                _PREFIX + "mood_palette",
                _PREFIX + "mood_palette",
                protocol.PALETTE_OPTIONS,
                lambda ctrl, value: ctrl.set_mood_palette(value),
            ),
            ControllerSelectSpec(
                _PREFIX + "mood_effect",
                _PREFIX + "mood_effect",
                _PREFIX + "mood_effect",
                ("E1", "E2", "E3"),
                lambda ctrl, value: ctrl.set_mood_effect(value),
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self.profile != "basic":
            specs += [
                ControllerNumberSpec(
                    _PREFIX + "floor_level",
                    _PREFIX + "floor_level",
                    _PREFIX + "floor_level_requested",
                    1 if self.profile == "xtbox" else 0,
                    6 if self.profile == "xtbox" else 255,
                    1,
                    lambda ctrl, value: cast(VMatBasicController, ctrl).set_floor_level(value),
                ),
                ControllerNumberSpec(
                    _PREFIX + "floor_minutes",
                    _PREFIX + "floor_minutes",
                    _PREFIX + "floor_minutes_requested",
                    0,
                    255 if self.profile == "xtbox" else 1439,
                    1,
                    lambda ctrl, value: cast(VMatBasicController, ctrl).set_floor_minutes(value),
                    "min",
                ),
            ]
        if self.profile == "xtbox":
            specs += [
                ControllerNumberSpec(
                    _PREFIX + "mood_brightness",
                    _PREFIX + "mood_brightness",
                    _PREFIX + "mood_brightness",
                    0,
                    100,
                    1,
                    lambda ctrl, value: cast(VMatBasicController, ctrl).set_mood_brightness(value),
                    "%",
                ),
                ControllerNumberSpec(
                    _PREFIX + "mood_speed",
                    _PREFIX + "mood_speed",
                    _PREFIX + "mood_speed",
                    0,
                    255,
                    1,
                    lambda ctrl, value: ctrl.set_mood_speed(value),
                ),
            ]
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            *tuple(
                ControllerStateSensorSpec(
                    _PREFIX + key,
                    _PREFIX + key,
                    _PREFIX + key,
                    "mdi:information-outline",
                    native_unit_of_measurement=unit,
                )
                for key, unit in (
                    ("model", None),
                    ("firmware", None),
                    ("temperature", "°C"),
                    ("floor_level_observed", None),
                    ("floor_minutes_observed", "min"),
                    ("floor_percent_observed", "%"),
                )
            ),
            ControllerStateSensorSpec(
                _PREFIX + "rssi",
                _PREFIX + "rssi",
                _PREFIX + "rssi",
                "mdi:signal",
                "dBm",
                attribute_keys=tuple(
                    _PREFIX + key for key in ("rssi_source", "rssi_seen_at", "rssi_representation")
                ),
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                _PREFIX + "ed", _PREFIX + "ed", _PREFIX + "ed", "mdi:information-outline"
            ),
        )
