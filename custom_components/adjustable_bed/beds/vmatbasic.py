"""Explicit V-MAT Basic app controls, without legacy packet or feature inference."""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from ..app_session import app_session
from ..codec import vibradorm as codec
from ..const import CONF_VMATBASIC_FLOOR_LEVEL, CONF_VMATBASIC_FLOOR_MINUTES, CONF_VMATBASIC_PROFILE
from ..execution import ExecutionCapabilities
from ..profiles import vmatbasic as vmat_profiles
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .builder import BuildContext

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from homeassistant.core import HomeAssistant

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class VMatBasicSessionIntent:
    """The selected fragment color and brightness, never measured hardware state."""

    palette: str = "col20"
    brightness: int = 100
    effect: str | None = None
    speed: int | None = None


def get_vmatbasic_session_intent(
    hass: HomeAssistant, address: str, profile: str
) -> VMatBasicSessionIntent:
    """Preserve a same-target session across BLE reconstruction, not a cold HA start."""
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address.upper()) is None:
        raise ValueError("V-MAT Basic intent requires an exact physical Bluetooth address")
    if profile not in vmat_profiles.PROFILES:
        raise ValueError("Unknown V-MAT Basic profile")
    return app_session(hass, address, ("vmatbasic", profile), VMatBasicSessionIntent)
_PREFIX = "vmatbasic_"


def _profile_characteristic(client: BleakClient, service_uuid: str, uuid: str, operation: str) -> BleakGATTCharacteristic:
    if not client.is_connected:
        raise ConnectionError("V-MAT Basic receiver is not connected")
    service = next((item for item in client.services if item.uuid.lower() == service_uuid), None)
    if service is None:
        raise ValueError(f"Missing exact V-MAT Basic service {service_uuid}")
    characteristic = next((item for item in service.characteristics if item.uuid.lower() == uuid), None)
    if characteristic is None or operation not in characteristic.properties:
        raise ValueError(f"Exact V-MAT Basic characteristic {uuid} cannot {operation}")
    return characteristic


def validate_profile_roles(client: BleakClient, profile: str) -> None:
    """Validate the selected product using the runtime's exact service roles."""
    services = {item.uuid.lower() for item in client.services}
    if not set(vmat_profiles.REQUIRED_SERVICES) <= services:
        raise ValueError("V-MAT Basic requires its control, status and GAP services")
    _profile_characteristic(client, codec.SERVICE_UUID, codec.MOTOR_CHAR_UUID, "write")
    if profile == "cbi":
        _profile_characteristic(client, codec.SERVICE_UUID, codec.LIGHT_CHAR_UUID, "write")
    elif profile == "xtbox":
        _profile_characteristic(client, codec.SERVICE_UUID, codec.CBI_CHAR_UUID, "write")


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
        if profile not in vmat_profiles.PROFILES:
            raise ValueError("Choose an explicit V-MAT Basic app profile")
        self.profile = vmat_profiles.PROFILES[profile]
        if floor_level is not None:
            vmat_profiles.integer(floor_level, *self.profile.floor_levels)
        vmat_profiles.integer(floor_minutes, *self.profile.floor_minutes)
        self._floor_level = floor_level
        self._floor_minutes = floor_minutes
        self._remember_settings = remember_settings
        self._intent = session_intent if session_intent is not None else VMatBasicSessionIntent()
        if self._intent.palette not in vmat_profiles.PALETTE_OPTIONS:
            raise ValueError("Invalid session palette")
        vmat_profiles.integer(self._intent.brightness, 0, 100)

    @property
    def execution(self) -> ExecutionCapabilities:
        """The app refreshes held motion until release, then sends STOP (#483)."""
        return ExecutionCapabilities(hold="stream")

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.MOTOR_CHAR_UUID

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
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_device_rename(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *vmat_profiles.MOTOR_ACTIONS,
            *(("floor_hold",) if self.profile.key == "xtbox" else ()),
        )

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        if self.profile.key == "basic":
            raise ValueError("Linked movement requires CBI or XT-Box receivers")
        await self.async_discover_capabilities()

    @property
    def diagnostic_poll_interval(self) -> float:
        return 3.0

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "explicit_profile": self.profile.key,
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
        return _profile_characteristic(client, service_uuid, uuid, operation)

    async def async_discover_capabilities(self) -> None:
        client = self._client()
        validate_profile_roles(client, self.profile.key)

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
                    if uuid == vmat_profiles.NAME_CHAR
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
                    codec.SERVICE_UUID,
                    codec.MOTOR_CHAR_UUID,
                    codec.motor(codec.STOP),
                    asyncio.Event(),
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
        vmat_profiles.integer(duration_ms, 100, 60000)
        event = self._coordinator.cancel_command
        if event.is_set():
            return
        is_motor = control in vmat_profiles.MOTOR_ACTIONS
        packet = (
            codec.motor(vmat_profiles.MOTOR_ACTIONS[control])
            if is_motor
            else codec.command(vmat_profiles.FLOOR)
        )
        uuid = codec.MOTOR_CHAR_UUID if is_motor else codec.CBI_CHAR_UUID
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        try:
            budget = asyncio.timeout_at(deadline)
            try:
                async with budget:
                    while not event.is_set():
                        started = asyncio.get_running_loop().time()
                        await self._write(codec.SERVICE_UUID, uuid, packet, event)
                        # Scheduling attempts, not guaranteed wire cadence.
                        elapsed = asyncio.get_running_loop().time() - started
                        delay = max(0, vmat_profiles.HOLD_INTERVAL_S - elapsed)
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
        if command == codec.motor(codec.STOP):
            await self.stop_all()
            return
        if len(command) != 1 or command[0] not in vmat_profiles.MOTOR_ACTIONS.values():
            raise ValueError("Only the six V-MAT Basic movement bytes are accepted")
        vmat_profiles.integer(repeat_count, 1, 2000)
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        if event.is_set():
            return
        try:
            for index in range(repeat_count):
                if event.is_set():
                    break
                started = asyncio.get_running_loop().time()
                await self._write(codec.SERVICE_UUID, codec.MOTOR_CHAR_UUID, command, event)
                if index + 1 < repeat_count:
                    elapsed = asyncio.get_running_loop().time() - started
                    await _cancellable(
                        asyncio.sleep(max(0, vmat_profiles.HOLD_INTERVAL_S - elapsed)), event
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
        await self.hold_control("back_up", self.leased_hold_ms(1000))

    async def move_back_down(self) -> None:
        await self.hold_control("back_down", self.leased_hold_ms(1000))

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.hold_control("legs_up", self.leased_hold_ms(1000))

    async def move_legs_down(self) -> None:
        await self.hold_control("legs_down", self.leased_hold_ms(1000))

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
        if self.profile.key != profile:
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
        if self.profile.floor_char is None:
            raise ValueError("The Basic profile has no floor controls")
        # Settings UI absence means zero; the separate CBI ON button defaults to 255.
        level = self._floor_level if self._floor_level is not None else self.profile.floor_levels[0]
        await self._write(
            codec.SERVICE_UUID,
            self.profile.floor_char,
            self.profile.floor(level, self._floor_minutes),
        )
        self.forward_controller_state_updates(
            {
                _PREFIX + "floor_level_requested": level,
                _PREFIX + "floor_minutes_requested": self._floor_minutes,
            }
        )

    async def set_floor_level(self, value: float) -> None:
        level = vmat_profiles.integer(value, *self.profile.floor_levels)
        if self.profile.floor_char is None:
            raise ValueError("The Basic profile has no floor controls")
        if self._coordinator.cancel_command.is_set():
            return
        self._setting(level=level)
        await self._send_floor_settings()

    async def set_floor_minutes(self, value: float) -> None:
        minutes = vmat_profiles.integer(value, *self.profile.floor_minutes)
        if self.profile.floor_char is None:
            raise ValueError("The Basic profile has no floor controls")
        if self._coordinator.cancel_command.is_set():
            return
        self._setting(minutes=minutes)
        await self._send_floor_settings()

    async def floor_toggle(self) -> None:
        self._require("cbi")
        status = vmat_profiles.light_status(
            await self._read(codec.SERVICE_UUID, codec.LIGHT_CHAR_UUID)
        )
        self._publish_floor(status)
        packet = (
            vmat_profiles.floor(0, 0)
            if status.level > 0
            else vmat_profiles.floor(
                255 if self._floor_level is None else self._floor_level, self._floor_minutes
            )
        )
        await self._write(codec.SERVICE_UUID, codec.LIGHT_CHAR_UUID, packet)

    async def set_mood_palette(self, option: str) -> None:
        self._require("xtbox")
        if option not in vmat_profiles.PALETTE_OPTIONS:
            raise ValueError("Choose one of the twenty shipped palette entries")
        if self._coordinator.cancel_command.is_set():
            return
        self._intent.palette = option
        packet = vmat_profiles.color_action(
            vmat_profiles.PALETTE[vmat_profiles.PALETTE_OPTIONS.index(option)],
            self._intent.brightness,
        )
        await self._write(codec.SERVICE_UUID, codec.CBI_CHAR_UUID, packet)
        self.forward_controller_state_update(_PREFIX + "mood_palette", option)

    async def set_mood_brightness(self, value: float) -> None:
        self._require("xtbox")
        brightness = vmat_profiles.integer(value, 0, 100)
        if self._coordinator.cancel_command.is_set():
            return
        self._intent.brightness = brightness
        packet = vmat_profiles.color_action(
            vmat_profiles.PALETTE[vmat_profiles.PALETTE_OPTIONS.index(self._intent.palette)],
            brightness,
        )
        await self._write(codec.SERVICE_UUID, codec.CBI_CHAR_UUID, packet)
        self.forward_controller_state_update(_PREFIX + "mood_brightness", brightness)

    async def set_mood_effect(self, option: str) -> None:
        self._require("xtbox")
        if option not in ("e1", "e2", "e3"):
            raise ValueError("Choose effect e1, e2 or e3")
        await self._write(
            codec.SERVICE_UUID, codec.CBI_CHAR_UUID, vmat_profiles.effect(int(option[1]))
        )
        self._intent.effect = option
        self.forward_controller_state_update(_PREFIX + "mood_effect", option)

    async def set_mood_speed(self, value: float) -> None:
        self._require("xtbox")
        progress = vmat_profiles.integer(value, 0, 255)
        await self._write(codec.SERVICE_UUID, codec.CBI_CHAR_UUID, vmat_profiles.speed(progress))
        self._intent.speed = progress
        self.forward_controller_state_update(_PREFIX + "mood_speed", progress)

    async def mood_toggle(self) -> None:
        self._require("xtbox")
        await self._write(
            codec.SERVICE_UUID, codec.CBI_CHAR_UUID, codec.command(vmat_profiles.MOOD)
        )

    async def mood_nightlight(self) -> None:
        self._require("xtbox")
        await self._write(codec.SERVICE_UUID, codec.CBI_CHAR_UUID, vmat_profiles.rgb(0))

    async def massage_action(self, action: str) -> None:
        self._require("xtbox")
        if action not in vmat_profiles.MASSAGE_ACTIONS:
            raise ValueError("Unknown shipped massage action")
        await self._write(
            codec.SERVICE_UUID,
            codec.CBI_CHAR_UUID,
            codec.command(vmat_profiles.MASSAGE_ACTIONS[action]),
        )

    async def rename_device(self, name: str) -> None:
        packet = vmat_profiles.rename(name)
        # A single default-MTU ATT write supports twenty bytes; no fragmentation is proven.
        if len(packet) > 20:
            raise ValueError("Encoded device name exceeds the safe twenty-byte write payload")
        await self._write(vmat_profiles.GAP_SERVICE, vmat_profiles.NAME_CHAR, packet)
        self.forward_controller_state_update(_PREFIX + "device_name", packet.decode("utf-8"))

    def _publish_floor(self, status: vmat_profiles.FloorStatus) -> None:
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
        for key, service, uuid in vmat_profiles.READ_ROLES:
            try:
                raw = await self._read(service, uuid)
                if key == "floor":
                    self._publish_floor(vmat_profiles.light_status(raw))
                else:
                    value = (
                        vmat_profiles.temperature(raw)
                        if key == "temperature"
                        else vmat_profiles.motor_status(raw)
                        if key == "ed"
                        else codec.decode_text(raw)
                    )
                    self.forward_controller_state_update(_PREFIX + key, value)
            except asyncio.CancelledError:
                self._clear_read(key)
                raise
            except Exception as error:
                self._clear_read(key)
                _LOGGER.debug("V-MAT Basic %s read failed: %s", key, error)

    def invalidate_diagnostics(self) -> None:
        for key, _, _ in vmat_profiles.READ_ROLES:
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
        if self.profile.key == "cbi":
            specs.append(
                button("floor_toggle", "Floor light toggle", lambda ctrl: ctrl.floor_toggle())
            )
        elif self.profile.key == "xtbox":
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
            for action in vmat_profiles.MASSAGE_ACTIONS:
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
        if self.profile.key != "xtbox":
            return ()
        return (
            ControllerSelectSpec(
                _PREFIX + "mood_palette",
                _PREFIX + "mood_palette",
                _PREFIX + "mood_palette",
                vmat_profiles.PALETTE_OPTIONS,
                lambda ctrl, value: ctrl.set_mood_palette(value),
            ),
            ControllerSelectSpec(
                _PREFIX + "mood_effect",
                _PREFIX + "mood_effect",
                _PREFIX + "mood_effect",
                ("e1", "e2", "e3"),
                lambda ctrl, value: ctrl.set_mood_effect(value),
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self.profile.floor_char is not None:
            specs += [
                ControllerNumberSpec(
                    _PREFIX + "floor_level",
                    _PREFIX + "floor_level",
                    _PREFIX + "floor_level_requested",
                    *self.profile.floor_levels,
                    1,
                    lambda ctrl, value: cast(VMatBasicController, ctrl).set_floor_level(value),
                ),
                ControllerNumberSpec(
                    _PREFIX + "floor_minutes",
                    _PREFIX + "floor_minutes",
                    _PREFIX + "floor_minutes_requested",
                    *self.profile.floor_minutes,
                    1,
                    lambda ctrl, value: cast(VMatBasicController, ctrl).set_floor_minutes(value),
                    "min",
                ),
            ]
        if self.profile.key == "xtbox":
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


async def build_controller(ctx: BuildContext) -> VMatBasicController:
    """Build the controller for the stored profile and floor-light settings."""
    coordinator = ctx.coordinator
    data = ctx.data
    return VMatBasicController(
        coordinator,
        profile=data[CONF_VMATBASIC_PROFILE],
        floor_level=data.get(CONF_VMATBASIC_FLOOR_LEVEL),
        floor_minutes=data.get(CONF_VMATBASIC_FLOOR_MINUTES, 0),
        remember_settings=coordinator.remember_vmatbasic_settings,
        session_intent=get_vmatbasic_session_intent(
            coordinator.hass, coordinator.address, data[CONF_VMATBASIC_PROFILE]
        ),
    )
