"""Adjustable Comfort M1X12 controller and explicit ELEVATE app variant.

The main controller is selected as an M1X12 app profile. Its independently
addressed ELEVATE accessories keep the existing ``star_elevate`` bed type and
select this controller only through the explicit M1X12 variant.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import math
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from .base import (
    POSITION_UNIT_PERCENT,
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .star_elevate import (
    NORDIC_UART_READ_CHAR_UUID,
    StarElevateCommands,
    StarElevateController,
)
from .starcode_m1x12_protocol import (
    PROFILES,
    StateValue,
    clock_packet,
    extended_packet,
    keep_open_packet,
    long_packet,
    manufacturer_dialect,
    normal_packet,
    parse_notification,
    position_packet,
    query_packet,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
DEVICE_INFORMATION: Final = "0000180a-0000-1000-8000-00805f9b34fb"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FIRMWARE: Final = "00002a28-0000-1000-8000-00805f9b34fb"
MANUFACTURER: Final = "00002a29-0000-1000-8000-00805f9b34fb"
SENDER_INTERVAL = 0.1
MAX_HOLD_MS = 60_000

# The accepted app selects independent parts. Only Parts 1, 2, and 4 have
# artifact-proven Home labels; the remaining labels stay as raw Part numbers.
_PARTS: Final = (
    (1, "starcode_m1x12_part_1", "part_1_up", "part_1_down"),
    (2, "starcode_m1x12_part_2", "part_2_up", "part_2_down"),
    (4, "starcode_m1x12_part_4", "part_4_up", "part_4_down"),
    (8, "starcode_m1x12_part_8", "part_8_up", "part_8_down"),
    (16, "starcode_m1x12_part_16", "part_16_up", "part_16_down"),
)
_KEYS: Final[dict[str, tuple[int, int]]] = {
    "part_1_up": (0x00000001, 0x03103000),
    "part_1_down": (0x00000002, 0x03103001),
    "part_2_up": (0x00000004, 0x03103002),
    "part_2_down": (0x00000008, 0x03103003),
    "part_4_up": (0x00000010, 0x03103004),
    "part_4_down": (0x00000020, 0x03103005),
    "part_8_up": (0x00000040, 0x03103008),
    "part_8_down": (0x00000080, 0x03103009),
    "part_16_up": (0, 0x0310300A),
    "part_16_down": (0, 0x0310300B),
    "union_up": (0x00000005, 0x0310300C),
    "union_down": (0x0000000A, 0x0310300D),
    "flat": (0x08000000, 0x03103010),
    "tv": (0x00004000, 0x03103011),
    "zero_g": (0x00001000, 0x03103013),
    "anti_snore": (0x00008000, 0x03103016),
    "lounge": (0x00002000, 0x03103017),
    "memory_8": (0x00004000, 0x03103018),
    "memory_1": (0x00010000, 0x0310301A),
    "memory_2": (0x00040000, 0x0310301B),
    "stop": (0, 0x0310300F),
    "interrupt": (0, 0x0310301F),
    "save_tv": (0x08004000, 0x03103092),
    "save_zero_g": (0x08001000, 0x03103090),
    "save_lounge": (0x08002000, 0x03103091),
    "save_memory_1": (0x08010000, 0x03103094),
    "save_memory_2": (0x08040000, 0x03103095),
    "reset": (0x88000000, 0x03103096),
    "massage_wave_up": (0x10000000, 0x03103058),
    "massage_wave_down": (0x04000000, 0x03103059),
    "massage_toggle": (0x00000100, 0x0310305A),
    "massage_head_up": (0x00000800, 0x03103066),
    "massage_head_down": (0x00800000, 0x03103067),
    "massage_foot_up": (0x00000400, 0x03103068),
    "massage_foot_down": (0x01000000, 0x03103069),
    "massage_both_up": (0x00000C00, 0),
    "massage_both_down": (0x01800000, 0),
    "massage_off": (0x02000000, 0x0310306F),
    "light_cycle": (0x00040000, 0x03103070),
    "light_on": (0x00000040, 0x03103073),
    "light_off": (0x00000080, 0x03103074),
    "light_mode_special": (0x00020004, 0x03103079),
}
_SAVE_ACTIONS: Final = {
    "save_tv",
    "save_zero_g",
    "save_lounge",
    "save_memory_1",
    "save_memory_2",
    "reset",
}
_PRESET_ACTIONS: Final = {
    "flat",
    "tv",
    "zero_g",
    "anti_snore",
    "lounge",
    "memory_8",
    "memory_1",
    "memory_2",
}
_HELD_ACTIONS: Final = tuple(
    [f"part_{part}_{direction}" for part, *_ in _PARTS for direction in ("up", "down")]
    + [
        "union_up",
        "union_down",
        "massage_wave_up",
        "massage_wave_down",
        "massage_head_up",
        "massage_head_down",
        "massage_foot_up",
        "massage_foot_down",
        "massage_both_up",
        "massage_both_down",
    ]
)


def _action(name: str) -> Callable[[BedController], Coroutine[object, object, None]]:
    async def run(controller: BedController) -> None:
        if not isinstance(controller, StarcodeM1X12Controller):
            raise TypeError("This action requires the explicit M1X12 app profile")
        await controller.app_action(name)

    return run


class StarcodeM1X12Controller(BedController):
    """Controller for one explicitly configured Adjustable Comfort M1X12 address."""

    _write_with_response = False

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: str,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        if profile not in PROFILES:
            raise ValueError("Choose an exact Adjustable Comfort M1X12 app profile")
        self._profile = profile
        self.device_name = device_name if device_name is not None else coordinator.name
        self.dialect = "legacy"
        self._ready = False
        self._generation = 0
        self._sender_lock = asyncio.Lock()
        self._next_tick = 0.0
        self._state: dict[str, StateValue] = {}
        self._firmware: str | None = None
        self._subscribed = False
        self._subscription_client: BleakClient | None = None
        self._write_session: contextvars.ContextVar[tuple[BleakClient, int] | None] = (
            contextvars.ContextVar(f"starcode_m1x12_session_{id(self)}", default=None)
        )
        self._pending_notifications: list[bytes] = []
        self._progress_queue: list[tuple[int, int]] = []
        self._progress_generation = 0

    @property
    def client(self) -> BleakClient | None:
        self._require_write_session()
        return self._coordinator.client

    def _require_write_session(self) -> None:
        client = self._coordinator.client
        session = self._write_session.get()
        if session is None:
            return
        owner, generation = session
        if (
            client is not owner
            or generation != self._generation
            or not self._ready
            or not owner.is_connected
        ):
            raise asyncio.CancelledError("M1X12 write session was superseded")

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def ready(self) -> bool:
        client = self._coordinator.client
        return (
            self._ready
            and client is not None
            and client.is_connected
            and (not self._subscribed or self._subscription_client is client)
        )

    @property
    def session_generation(self) -> int:
        return self._generation

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return True

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return True

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return True

    @property
    def supports_massage_off_control(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def supports_light_cycle(self) -> bool:
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

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self._ready

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=key,
                translation_key=translation_key,
                open_fn=_action(up),
                close_fn=_action(down),
                stop_fn=lambda controller: controller.stop_all(),
                hold=ControllerMotorHoldSpec(
                    up_control=up,
                    down_control=down,
                    start_delay_ms=100,
                    release_delay_ms=100,
                ),
            )
            for part, translation_key, up, down in _PARTS
            for key in (f"m1x12_part_{part}",)
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"back", "legs", "head", "feet", "lumbar", "starcode_union"})

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = (
            ("memory_8", "MemoryType 8"),
            ("save_tv", "Save TV"),
            ("save_zero_g", "Save zero gravity"),
            ("save_lounge", "Save reading/lounge"),
            ("reset", "Reset saved positions"),
            ("light_mode_0", "Light mode 0"),
            ("light_mode_1", "Light mode 1"),
            ("query", "Refresh bed state"),
        )
        one_shot = tuple(
            ControllerButtonSpec(
                key=f"starcode_m1x12_{key}",
                name=name,
                press_fn=_action(key),
                translation_key=f"starcode_m1x12_{key}",
            )
            for key, name in buttons
        )
        held = (
            ("massage_wave_up", "Hold to increase massage wave"),
            ("massage_wave_down", "Hold to decrease massage wave"),
            ("massage_head_up", "Hold to increase head massage"),
            ("massage_head_down", "Hold to decrease head massage"),
            ("massage_foot_up", "Hold to increase foot massage"),
            ("massage_foot_down", "Hold to decrease foot massage"),
            ("massage_both_up", "Hold to increase both-zone massage"),
            ("massage_both_down", "Hold to decrease both-zone massage"),
        )
        return one_shot + tuple(
            ControllerButtonSpec(
                key=f"starcode_m1x12_hold_{key}",
                name=name,
                press_fn=_action(key),
                translation_key=f"starcode_m1x12_hold_{key}",
                hold=ControllerHoldSpec(
                    control=key,
                    start_delay_ms=100,
                    release_delay_ms=100,
                ),
            )
            for key, name in held
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:

        async def brightness(controller: BedController, value: float) -> None:
            if not isinstance(controller, StarcodeM1X12Controller):
                raise TypeError("Brightness needs the explicit M1X12 profile")
            await controller.set_brightness(value)

        return (
            ControllerNumberSpec(
                key="starcode_m1x12_brightness",
                translation_key="starcode_m1x12_brightness",
                state_key="light_brightness",
                native_min_value=1,
                native_max_value=6,
                native_step=1,
                set_fn=brightness,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        keys: tuple[str, ...] = (
            "firmware",
            "massage_time_raw",
            "massage_head_level",
            "massage_foot_level",
            "massage_mode",
            "light_brightness",
            "light_color_index",
            "light_rgb_mode",
            "light_mode",
            "sonic_time_raw",
            "sonic_frequency",
            "sonic_head_level",
            "sonic_foot_level",
            "sonic_mode",
            "sonic_massage_type",
            *(f"part_{part}_position" for part in (1, 2, 4, 8, 16, 32)),
        )
        if self.profile == "cb25":
            keys += ("alarm_0", "alarm_1")
        else:
            keys += (
                "alarm_0",
                "alarm_1",
                "eq_volume",
                "eq_preset",
                "eq_low_frequency",
                "eq_high_frequency",
                *(f"eq_band_{index}" for index in range(8)),
            )
        if self.profile == "kneading":
            keys += ("kneading_time_raw", "kneading_mode")
        return tuple(
            ControllerStateSensorSpec(
                key=f"starcode_m1x12_{key}",
                translation_key=f"starcode_m1x12_{key}",
                state_key=key,
                icon="mdi:information-outline",
                native_unit_of_measurement=POSITION_UNIT_PERCENT
                if key.endswith("_position")
                else None,
                attribute_keys=("light_rgb", "light_rgb_mode")
                if key == "light_color_index"
                else ((key + "_details",) if key.startswith("alarm_") else ()),
            )
            for key in keys
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        keys: tuple[str, ...] = (
            "motor_stopped",
            "massage_active",
            "light_on",
            "sonic_active",
        )
        if self.profile != "cb25":
            keys += ("usb_on",)
        if self.profile == "kneading":
            keys += ("kneading_on", "kneading_demo")
        return tuple(
            ControllerStateBinarySensorSpec(
                key=f"starcode_m1x12_{key}",
                translation_key=f"starcode_m1x12_{key}",
                state_key=key,
                icon="mdi:information-outline",
            )
            for key in keys
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        all_keys = (
            "firmware",
            "massage_time_raw",
            "massage_head_level",
            "massage_foot_level",
            "massage_mode",
            "light_brightness",
            "light_color_index",
            "light_rgb_mode",
            "light_mode",
            "sonic_time_raw",
            "sonic_frequency",
            "sonic_head_level",
            "sonic_foot_level",
            "sonic_mode",
            "sonic_massage_type",
            *(f"part_{part}_position" for part in (1, 2, 4, 8, 16, 32)),
            "alarm_0",
            "alarm_1",
            "eq_volume",
            "eq_preset",
            "eq_low_frequency",
            "eq_high_frequency",
            *(f"eq_band_{index}" for index in range(8)),
            "kneading_time_raw",
            "kneading_mode",
        )
        active = {spec.key for spec in self.controller_state_sensor_specs}
        return frozenset(f"starcode_m1x12_{key}" for key in all_keys) - active

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        all_keys = (
            "motor_stopped",
            "massage_active",
            "light_on",
            "sonic_active",
            "usb_on",
            "kneading_on",
            "kneading_demo",
        )
        active = {spec.key for spec in self.controller_state_binary_sensor_specs}
        return frozenset(f"starcode_m1x12_{key}" for key in all_keys) - active

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return _HELD_ACTIONS

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported M1X12 held control: {control}")
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= MAX_HOLD_MS:
            raise ValueError("M1X12 held controls require 100 ms to 60000 ms")

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self._coordinator.client
        if client is None or not client.is_connected:
            raise ConnectionError("Adjustable Comfort M1X12 requires a connected transport")
        self._validate_characteristics(client)
        if self._subscribed:
            await self.stop_notify()

        self._ready = False
        self._notify_callback = callback
        self._generation += 1
        self._clear_progress_queue()
        generation = self._generation
        self._pending_notifications.clear()

        def receive(characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
            if generation != self._generation or self._coordinator.client is not client:
                return
            payload = bytes(data)
            self.forward_raw_notification(NOTIFY, payload)
            if self._ready:
                self._apply_notification(payload)
            else:
                self._pending_notifications.append(payload)

        self._firmware = None
        try:
            try:
                firmware_bytes = await asyncio.wait_for(client.read_gatt_char(FIRMWARE), 5)
                firmware = "".join(chr(value) for value in firmware_bytes)
            except Exception:
                firmware = ""
                _LOGGER.debug("M1X12 software revision read failed", exc_info=True)
            if generation != self._generation or self._coordinator.client is not client:
                raise asyncio.CancelledError("M1X12 firmware read belongs to an old session")
            if firmware:
                self._firmware = firmware
                self._state["firmware"] = firmware
                self.forward_controller_state_update("firmware", firmware)

            await client.start_notify(NOTIFY, receive)
            if generation != self._generation:
                await client.stop_notify(NOTIFY)
                raise asyncio.CancelledError("M1X12 notification session was superseded")
            self._subscribed = True
            self._subscription_client = client

            manufacturer = b""
            if client.services.get_characteristic(MANUFACTURER) is not None:
                try:
                    manufacturer = await asyncio.wait_for(client.read_gatt_char(MANUFACTURER), 1)
                except Exception:
                    _LOGGER.debug("M1X12 manufacturer read failed; using C framing", exc_info=True)
            if generation != self._generation or self._coordinator.client is not client:
                raise asyncio.CancelledError("M1X12 manufacturer read belongs to an old session")
            self.dialect = manufacturer_dialect(bytes(manufacturer))
            self._next_tick = asyncio.get_running_loop().time() + SENDER_INTERVAL
            self._ready = True
            for payload in self._pending_notifications:
                self._apply_notification(payload)
            self._pending_notifications.clear()
            if self.dialect == "star":
                await self.write_command(keep_open_packet())
            if self.profile in ("f23", "kneading"):
                await self.write_command(clock_packet(dt_util.now()))
            await self.query_status()
        except BaseException:
            if generation == self._generation:
                await self.stop_notify()
            raise

    @staticmethod
    def _validate_characteristics(client: BleakClient) -> None:
        services = client.services
        if (
            services.get_service(SERVICE) is None
            or services.get_service(DEVICE_INFORMATION) is None
        ):
            raise ConnectionError("M1X12 requires Nordic UART and Device Information services")
        required = ((WRITE, SERVICE), (NOTIFY, SERVICE), (FIRMWARE, DEVICE_INFORMATION))
        for uuid, expected_service in required:
            characteristic = services.get_characteristic(uuid)
            if characteristic is None:
                raise ConnectionError(f"M1X12 requires characteristic {uuid}")
            if characteristic.service_uuid.lower() != expected_service:
                raise ConnectionError("M1X12 characteristic belongs to the wrong service")
        write = services.get_characteristic(WRITE)
        notify = services.get_characteristic(NOTIFY)
        firmware = services.get_characteristic(FIRMWARE)
        if write is None or "write-without-response" not in write.properties:
            raise ConnectionError("M1X12 requires write without response")
        if notify is None or not {"notify", "indicate"}.intersection(notify.properties):
            raise ConnectionError("M1X12 requires an RX notification channel")
        if firmware is None or "read" not in firmware.properties:
            raise ConnectionError("M1X12 requires readable software revision 2A28")

    def _apply_notification(self, payload: bytes) -> None:
        updates = parse_notification(
            payload, profile=self.profile, dialect=self.dialect, previous=self._state
        )
        self._state.update(updates)
        if updates:
            self.forward_controller_state_updates(dict(updates))
        if updates.get("motor_stopped") is True and self._progress_queue:
            axis, target = self._progress_queue.pop(0)
            asyncio.create_task(
                self._send_progress_target(
                    axis,
                    target,
                    session_generation=self._generation,
                    progress_generation=self._progress_generation,
                )
            )

    def _on_notification(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Keep a simple handler for direct notification tests and diagnostics."""
        payload = bytes(data)
        self.forward_raw_notification(NOTIFY, payload)
        self._apply_notification(payload)

    async def stop_notify(self) -> None:
        self._generation += 1
        client = self._subscription_client
        was_ready = self._ready and client is not None and client.is_connected
        self._pending_notifications.clear()
        self._clear_progress_queue()
        if was_ready:
            try:
                await self._send_stop()
            except BleakError, ConnectionError, asyncio.CancelledError:
                _LOGGER.debug("Could not release M1X12 on session teardown", exc_info=True)
        self._ready = False
        if self._state:
            cleared_keys = dict.fromkeys(self._state)
            self._state.clear()
            self.forward_controller_state_updates(cleared_keys)
        self._firmware = None
        try:
            if self._subscribed and client is not None and client.is_connected:
                await client.stop_notify(NOTIFY)
        finally:
            self._subscribed = False
            self._subscription_client = None

    def motor_pulse_settings(self) -> tuple[int, int]:
        count, _ = super().motor_pulse_settings()
        return count, 100

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        del pulse_delay_ms
        return max(1, (duration_ms + 99) // 100)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "Adjustable Comfort M1X12",
            "profile": self.profile,
            "dialect": self.dialect,
            "ready": self.ready,
            "firmware": self._firmware,
            "hardware_verified": False,
        }

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if not self.ready:
            raise ConnectionError("M1X12 sender is not ready")
        client = self._coordinator.client
        if client is None:
            raise ConnectionError("M1X12 sender has no client")
        cancel = self._coordinator.cancel_command if cancel_event is None else cancel_event
        token = self._write_session.set((client, self._generation))
        try:
            async with self._sender_lock:
                for _ in range(max(0, repeat_count)):
                    if cancel.is_set():
                        return
                    self._require_write_session()
                    loop = asyncio.get_running_loop()
                    now = loop.time()
                    if self._next_tick < now:
                        skipped = math.floor((now - self._next_tick) / SENDER_INTERVAL) + 1
                        self._next_tick += skipped * SENDER_INTERVAL
                    await asyncio.sleep(max(0, self._next_tick - now))
                    if cancel.is_set():
                        return
                    self._require_write_session()
                    await self._write_gatt_with_retry(
                        WRITE, command, response=False, cancel_event=cancel
                    )
                    self._require_write_session()
                    self._next_tick += max(1, repeat_delay_ms) / 1000
        finally:
            self._write_session.reset(token)

    def _normal(self, key: str, *, intensity: bool = False) -> bytes | None:
        legacy, star = _KEYS[key]
        if key in {"part_16_up", "part_16_down"}:
            # These two accepted selector calls construct S framing directly,
            # even when the manufacturer selector chose the C dialect.
            return normal_packet(star, "star")
        if intensity and self.dialect == "star" and key in ("massage_both_up", "massage_both_down"):
            return None
        if intensity and self.dialect == "legacy":
            # Accepted C-maker intensity controls keep the S packet family.
            return normal_packet(legacy, "star")
        return normal_packet(star if self.dialect == "star" else legacy, self.dialect)

    async def _send_stop(self) -> None:
        await self.write_command(self._normal("stop") or b"", cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        from ..starcode_accessory_group import cancel_group_operations

        cancel_group_operations(self._coordinator.hass, self._coordinator.entry.entry_id)
        self._clear_progress_queue()
        await self._send_stop()

    async def interrupt(self) -> None:
        self._clear_progress_queue()
        await self.write_command(self._normal("interrupt") or b"", cancel_event=asyncio.Event())

    async def _interrupt_group(self) -> None:
        from ..starcode_accessory_group import interrupt_conflicting_group

        await interrupt_conflicting_group(self._coordinator)

    async def _move(self, action: str) -> None:
        await self._interrupt_group()
        self._clear_progress_queue()
        pulse_count, _ = self.motor_pulse_settings()
        try:
            await self.write_command(self._normal(action) or b"", repeat_count=pulse_count)
        finally:
            await self._send_stop()

    async def _sequence(self, action: str, count: int, *, release: bool = True) -> None:
        try:
            await self.write_command(self._normal(action) or b"", repeat_count=count)
        finally:
            if release:
                await self._send_stop()

    async def app_action(self, action: str) -> None:
        if action == "query":
            await self.query_status()
            return
        if action == "light_mode_0":
            await self.light_mode(0)
            return
        if action == "light_mode_1":
            await self.light_mode(1)
            return
        if action in _SAVE_ACTIONS:
            await self.stop_all()
            await self._sequence(action, 55, release=False)
            return
        if action == "light_cycle":
            packet = self._normal(action)
            target_profile = self.profile in ("f23", "kneading")
            if target_profile:
                packet = normal_packet(0x03103070, "star")
                await self._rgb(packet, dialect="star")
            else:
                await self._send_finite(packet or b"", 2)
            return
        if action == "light_on" or action == "light_off":
            packet = self._normal(action)
            target_profile = self.profile in ("f23", "kneading")
            if target_profile:
                key = 0x03103073 if action == "light_on" else 0x03103074
                packet = normal_packet(key, "star")
                await self._rgb(packet, dialect="star")
                return
            if self.dialect == "legacy":
                packet = long_packet(_KEYS[action][0])
            await self._send_finite(packet or b"", 2)
            return
        if action == "massage_toggle" or action == "massage_off":
            await self._sequence(action, 2)
            return
        if action in _PRESET_ACTIONS:
            await self._interrupt_group()
            self._clear_progress_queue()
            await self._sequence(action, 3)
            return
        if action in {
            "part_1_up",
            "part_1_down",
            "part_2_up",
            "part_2_down",
            "part_4_up",
            "part_4_down",
            "part_8_up",
            "part_8_down",
            "part_16_up",
            "part_16_down",
            "union_up",
            "union_down",
        }:
            await self._move(action)
            return
        if action.startswith("massage_wave_"):
            await self._send_finite(self._normal(action) or b"", 1)
            return
        if action in {
            "massage_head_up",
            "massage_head_down",
            "massage_foot_up",
            "massage_foot_down",
            "massage_both_up",
            "massage_both_down",
        }:
            packet = self._normal(action, intensity=True)
            if packet is not None:
                await self._send_finite(packet, 1)
            return
        raise ValueError(f"Unknown M1X12 action: {action}")

    async def _send_finite(self, packet: bytes, repeat_count: int) -> None:
        try:
            await self.write_command(packet, repeat_count=repeat_count)
        finally:
            await self._send_stop()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        packet = self._normal(
            control,
            intensity=control
            in {
                "massage_head_up",
                "massage_head_down",
                "massage_foot_up",
                "massage_foot_down",
                "massage_both_up",
                "massage_both_down",
            },
        )
        if packet is None:
            return
        await self._interrupt_group()
        self._clear_progress_queue()
        cancel = self._coordinator.cancel_command
        generation = self._generation
        client = self._coordinator.client
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        try:
            while not cancel.is_set() and asyncio.get_running_loop().time() < deadline:
                if generation != self._generation or self._coordinator.client is not client:
                    break
                await self.write_command(packet, repeat_count=1, cancel_event=cancel)
        finally:
            if (
                generation == self._generation
                and self._coordinator.client is client
                and client
                and client.is_connected
            ):
                await self._send_stop()

    async def query_status(self) -> None:
        dialect = "star" if self.profile in ("f23", "kneading") else self.dialect
        await self.write_command(query_packet(dialect))

    async def _rgb(self, packet: bytes, *, dialect: str | None = None) -> None:
        try:
            await self.write_command(packet)
        finally:
            actual = dialect or ("star" if self.profile in ("f23", "kneading") else self.dialect)
            await self.write_command(
                normal_packet(0x0310300F if actual == "star" else 0, actual),
                cancel_event=asyncio.Event(),
            )

    async def lights_on(self) -> None:
        await self.app_action("light_on")

    async def lights_off(self) -> None:
        await self.app_action("light_off")

    async def lights_cycle(self) -> None:
        await self.app_action("light_cycle")

    async def set_brightness(self, value: float) -> None:
        if (
            isinstance(value, bool)
            or not math.isfinite(value)
            or value != int(value)
            or not 1 <= value <= 6
        ):
            raise ValueError("M1X12 brightness must be an integer from 1 to 6")
        dialect = "star" if self.profile in ("f23", "kneading") else self.dialect
        await self._rgb(extended_packet(0, int(value), dialect), dialect=dialect)

    async def light_mode(self, mode: int) -> None:
        if mode not in (0, 1):
            raise ValueError("M1X12 light mode must be 0 or 1")
        special_model = self.device_name[4:10] if len(self.device_name) > 14 else ""
        special = special_model in {"252201", "254202", "352201"}
        if self.profile in ("f23", "kneading"):
            packet = normal_packet(0x03103089, "star")
            await self._rgb(packet, dialect="star")
        elif special:
            if self.dialect == "star":
                key = 0x03103079 if mode == 0 else 0x0310307A
                packet = normal_packet(key, "star")
            else:
                packet = self._normal("light_mode_special") or b""
            await self.write_command(packet, repeat_count=35)
        else:
            key = 0x03103089 if mode == 0 else 0x0310308A
            packet = normal_packet(key, "star")
            try:
                await self.write_command(packet)
            finally:
                if mode == 1:
                    await self.write_command(
                        normal_packet(0x0310300F, "star"), cancel_event=asyncio.Event()
                    )

    async def set_massage_timer(self, minutes: int) -> None:
        if isinstance(minutes, bool) or minutes not in (0, 10, 20, 30):
            raise ValueError("M1X12 massage timer accepts 0, 10, 20 or 30 minutes")
        if minutes == 0:
            await self.app_action("massage_off")
            return
        # Massage duration follows the manufacturer selector for every profile;
        # only the F23/kneading lighting controls force S framing.
        dialect = self.dialect
        await self._rgb(extended_packet(7, minutes // 10, dialect), dialect=dialect)

    def queue_position_target(self, axis: int, target: int) -> None:
        """Queue an internal progress target without assigning a physical axis name."""
        self.queue_position_targets((*self._progress_queue, (axis, target)))

    def queue_position_targets(self, targets: tuple[tuple[int, int], ...]) -> None:
        """Replace the finite internal queue after validating every raw Part target."""
        if len(targets) > 5 or len({axis for axis, _ in targets}) != len(targets):
            raise ValueError("M1X12 progress queue accepts up to five distinct Part selectors")
        for axis, target in targets:
            self._validate_position_target(axis, target)
        self._progress_generation += 1
        self._progress_queue = list(targets)

    @staticmethod
    def _validate_position_target(axis: int, target: int) -> None:
        if isinstance(axis, bool) or not isinstance(axis, int) or not 0 <= axis <= 4:
            raise ValueError("M1X12 progress axis must be an accepted selector from 0 to 4")
        if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target <= 255:
            raise ValueError("M1X12 progress target must fit the protocol byte")

    def _clear_progress_queue(self) -> None:
        self._progress_generation += 1
        self._progress_queue.clear()

    async def _send_progress_target(
        self,
        axis: int,
        target: int,
        *,
        session_generation: int,
        progress_generation: int,
    ) -> None:
        if (
            self.ready
            and session_generation == self._generation
            and progress_generation == self._progress_generation
        ):
            await self.write_command(position_packet(axis, target, self.dialect))

    async def move_head_up(self) -> None:
        await self._move("part_1_up")

    async def move_head_down(self) -> None:
        await self._move("part_1_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._move("part_2_up")

    async def move_feet_down(self) -> None:
        await self._move("part_2_down")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self._move("part_4_up")

    async def move_lumbar_down(self) -> None:
        await self._move("part_4_down")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def move_both_up(self) -> None:
        await self._move("union_up")

    async def move_both_down(self) -> None:
        await self._move("union_down")

    async def preset_flat(self) -> None:
        await self.app_action("flat")

    async def preset_tv(self) -> None:
        await self.app_action("tv")

    async def preset_zero_g(self) -> None:
        await self.app_action("zero_g")

    async def preset_anti_snore(self) -> None:
        await self.app_action("anti_snore")

    async def preset_lounge(self) -> None:
        await self.app_action("lounge")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num == 8:
            await self.app_action("memory_8")
        elif memory_num in (1, 2):
            await self.app_action(f"memory_{memory_num}")
        else:
            raise ValueError("M1X12 recall memory accepts 1, 2 or raw MemoryType 8")

    async def program_memory(self, memory_num: int) -> None:
        actions = {1: "save_memory_1", 2: "save_memory_2"}
        if memory_num not in actions:
            raise ValueError("M1X12 programming supports memory slots 1 and 2")
        await self.app_action(actions[memory_num])

    async def massage_head_up(self) -> None:
        await self.app_action("massage_head_up")

    async def massage_head_down(self) -> None:
        await self.app_action("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self.app_action("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self.app_action("massage_foot_down")

    async def massage_wave_up(self) -> None:
        await self.app_action("massage_wave_up")

    async def massage_wave_down(self) -> None:
        await self.app_action("massage_wave_down")

    async def massage_wave_next(self) -> None:
        await self.massage_wave_up()

    async def massage_wave_previous(self) -> None:
        await self.massage_wave_down()

    async def massage_toggle(self) -> None:
        await self.app_action("massage_toggle")

    async def massage_off(self) -> None:
        await self.app_action("massage_off")

    async def massage_both_intensity_up(self) -> None:
        await self.app_action("massage_both_up")

    async def massage_both_intensity_down(self) -> None:
        await self.app_action("massage_both_down")

    async def read_light_state(self) -> dict[str, object]:
        await self.query_status()
        return self.get_light_state()

    def get_light_state(self) -> dict[str, object]:
        """Return the latest parsed light telemetry for the HA light entity."""
        return {"is_on": self._state.get("light_on")}


class StarElevateM1X12Controller(StarElevateController):
    """Target-profile ELEVATE controller with required firmware readiness state."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._firmware: str | None = None
        self._firmware_client: BleakClient | None = None

    def on_disconnect(self) -> None:
        """Invalidate target-profile writes and firmware state for this link."""
        self._generation += 1
        self._initialized = False
        if self._firmware is not None:
            self.forward_controller_state_update("firmware", None)
        self._firmware = None
        self._firmware_client = None

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=spec.key,
                translation_key=spec.translation_key,
                open_fn=spec.open_fn,
                close_fn=spec.close_fn,
                stop_fn=spec.stop_fn,
                position_key=spec.position_key,
                max_angle=spec.max_angle,
                scheduler_resource=spec.scheduler_resource,
                hold=ControllerMotorHoldSpec(
                    up_control=control_pair[0],
                    down_control=control_pair[1],
                    start_delay_ms=100,
                    release_delay_ms=100,
                ),
            )
            for spec, control_pair in zip(
                super().motor_control_specs,
                (
                    ("actuator_1_up", "actuator_1_down"),
                    ("actuator_2_up", "actuator_2_down"),
                    ("both_up", "both_down"),
                ),
                strict=True,
            )
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            "actuator_1_up",
            "actuator_1_down",
            "actuator_2_up",
            "actuator_2_down",
            "both_up",
            "both_down",
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported M1X12 ELEVATE held control: {control}")
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= MAX_HOLD_MS:
            raise ValueError("M1X12 ELEVATE holds require 100 ms to 60000 ms")

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "starcode_m1x12_elevate_firmware",
                "starcode_m1x12_elevate_firmware",
                "firmware",
                "mdi:information-outline",
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self._coordinator.client
        if client is None or not client.is_connected:
            raise ConnectionError("M1X12 ELEVATE requires a connected transport")
        StarcodeM1X12Controller._validate_characteristics(client)
        self._notify_callback = callback
        self._generation += 1
        generation = self._generation
        self._initialized = False
        self._firmware = None
        self._firmware_client = client
        try:
            firmware_bytes = await asyncio.wait_for(client.read_gatt_char(FIRMWARE), 5)
            firmware = "".join(chr(value) for value in firmware_bytes)
        except Exception:
            firmware = ""
            _LOGGER.debug("M1X12 ELEVATE software revision read failed", exc_info=True)
        if (
            generation != self._generation
            or self._coordinator.client is not client
            or not client.is_connected
        ):
            raise asyncio.CancelledError("M1X12 ELEVATE firmware read belongs to an old session")
        if firmware:
            self._firmware = firmware
            self.forward_controller_state_update("firmware", firmware)
        # The target app requires 2A28 and recognizes 2A29 without reading it.
        manufacturer_present = client.services.get_characteristic(MANUFACTURER) is not None
        _LOGGER.debug(
            "M1X12 ELEVATE manufacturer characteristic present: %s",
            manufacturer_present,
        )
        # A failed subscription is a readiness failure for this explicit profile.
        await client.start_notify(NOTIFY, self._on_notification)
        if generation != self._generation or self._coordinator.client is not client:
            await client.stop_notify(NOTIFY)
            raise asyncio.CancelledError("M1X12 ELEVATE subscription belongs to an old session")
        try:
            await self._ensure_initialized()
        except BaseException:
            try:
                await client.stop_notify(NOTIFY)
            except BleakError:
                _LOGGER.debug("Could not unwind M1X12 ELEVATE subscription", exc_info=True)
            self._initialized = False
            raise
        if not self.ready:
            raise ConnectionError("M1X12 ELEVATE did not complete required initialization")

    async def stop_notify(self) -> None:
        client = self._firmware_client or self._coordinator.client
        generation = self._generation
        was_ready = (
            self._initialized
            and client is not None
            and client is self._coordinator.client
            and client.is_connected
        )
        if was_ready and client is not None:
            try:
                await self._write_owned_command(
                    StarElevateCommands.STOP,
                    client=client,
                    generation=generation,
                    cancel_event=asyncio.Event(),
                )
            except BleakError, ConnectionError, asyncio.CancelledError:
                _LOGGER.debug("Could not release M1X12 ELEVATE on session teardown", exc_info=True)
        self._notify_callback = None
        if client is not None and client.is_connected:
            try:
                await client.stop_notify(NORDIC_UART_READ_CHAR_UUID)
            except BleakError:
                _LOGGER.debug("Could not stop M1X12 ELEVATE notifications", exc_info=True)
        self._generation += 1
        self._initialized = False
        if self._firmware is not None:
            self.forward_controller_state_update("firmware", None)
        self._firmware = None
        self._firmware_client = None

    async def _write_owned_command(
        self,
        command: bytes,
        *,
        client: BleakClient,
        generation: int,
        cancel_event: asyncio.Event,
    ) -> None:
        """Write one held frame only to the captured, still-current BLE session."""
        if cancel_event.is_set():
            return
        if (
            generation != self._generation
            or self._coordinator.client is not client
            or not client.is_connected
        ):
            raise asyncio.CancelledError("M1X12 ELEVATE write session was superseded")

        characteristic = client.services.get_characteristic(self.control_characteristic_uuid)
        payload = self._format_command_trace_payload(command)
        if payload is not None:
            self._coordinator.record_command_trace(
                payload=payload,
                characteristic_uuid=self.control_characteristic_uuid,
                characteristic_handle=getattr(characteristic, "handle", None),
                response=False,
                repeat_count=1,
                repeat_delay_ms=100,
                command_origin="_write_owned_command",
                controller_class=type(self).__name__,
            )

        async with self._ble_lock:
            if cancel_event.is_set():
                return
            if (
                generation != self._generation
                or self._coordinator.client is not client
                or not client.is_connected
            ):
                raise asyncio.CancelledError("M1X12 ELEVATE write session was superseded")
            await client.write_gatt_char(
                self.control_characteristic_uuid,
                command,
                response=False,
            )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        command = {
            "actuator_1_up": StarElevateCommands.ACTUATOR_1_UP,
            "actuator_1_down": StarElevateCommands.ACTUATOR_1_DOWN,
            "actuator_2_up": StarElevateCommands.ACTUATOR_2_UP,
            "actuator_2_down": StarElevateCommands.ACTUATOR_2_DOWN,
            "both_up": StarElevateCommands.BOTH_UP,
            "both_down": StarElevateCommands.BOTH_DOWN,
        }[control]
        from ..starcode_accessory_group import interrupt_conflicting_group

        await interrupt_conflicting_group(self._coordinator)
        cancel = self._coordinator.cancel_command
        generation = self.session_generation
        client = self._coordinator.client
        if client is None or not client.is_connected or not self.ready:
            raise ConnectionError("M1X12 ELEVATE sender is not ready")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        next_tick = loop.time() + SENDER_INTERVAL
        try:
            while not cancel.is_set() and loop.time() < deadline:
                if (
                    generation != self.session_generation
                    or self._coordinator.client is not client
                    or not client.is_connected
                ):
                    break
                await asyncio.sleep(max(0, next_tick - loop.time()))
                if (
                    cancel.is_set()
                    or generation != self.session_generation
                    or self._coordinator.client is not client
                    or not client.is_connected
                ):
                    break
                await self._write_owned_command(
                    command,
                    client=client,
                    generation=generation,
                    cancel_event=cancel,
                )
                next_tick += SENDER_INTERVAL
                now = loop.time()
                if next_tick <= now:
                    skipped = math.floor((now - next_tick) / SENDER_INTERVAL) + 1
                    next_tick += skipped * SENDER_INTERVAL
        except asyncio.CancelledError:
            if (
                generation == self.session_generation
                and self._coordinator.client is client
                and client.is_connected
            ):
                raise
        finally:
            if (
                generation == self.session_generation
                and self._coordinator.client is client
                and client is not None
                and client.is_connected
            ):
                await self._write_owned_command(
                    StarElevateCommands.STOP,
                    client=client,
                    generation=generation,
                    cancel_event=asyncio.Event(),
                )
