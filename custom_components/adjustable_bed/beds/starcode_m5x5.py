"""The explicitly selected AdjustableM5X5 app's four bedding profiles."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from .base import (
    POSITION_UNIT_PERCENT,
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .starcode_m5x5_protocol import (
    StateValue,
    clock_packet,
    extended_packet,
    manufacturer_dialect,
    normal_packet,
    parse_notification,
    query_packet,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
DEVICE_INFORMATION: Final = "0000180a-0000-1000-8000-00805f9b34fb"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FIRMWARE: Final = "00002a28-0000-1000-8000-00805f9b34fb"
MANUFACTURER: Final = "00002a29-0000-1000-8000-00805f9b34fb"
PROFILES: Final = ("cb25", "f23", "kneading", "elevate")
SPECIAL_REMOTES: Final = frozenset(("252201", "254202", "352201"))
# P1/P2 keys are paired only where the frozen app implements the same action.
KEYS: Final = {
    "head_up": (1, 0x00),
    "head_down": (2, 0x01),
    "foot_up": (4, 0x02),
    "foot_down": (8, 0x03),
    "lumbar_up": (0x10, 0x04),
    "lumbar_down": (0x20, 0x05),
    "union_up": (5, 0x0C),
    "union_down": (10, 0x0D),
    "flat": (0x08000000, 0x10),
    "tv": (0x4000, 0x11),
    "zero_g": (0x1000, 0x13),
    "anti_snore": (0x8000, 0x16),
    "lounge": (0x2000, 0x17),
    "memory_1": (0x10000, 0x1A),
    "memory_2": (0x40000, 0x1B),
    "save_tv": (0x08004000, 0x92),
    "save_zero_g": (0x08001000, 0x90),
    "save_lounge": (0x08002000, 0x91),
    "save_memory_1": (0x08010000, 0x94),
    "save_memory_2": (0x08040000, 0x95),
    "reset": (0x88000000, 0x96),
    "massage_head_up": (0x0800, 0x66),
    "massage_head_down": (0x00800000, 0x67),
    "massage_foot_up": (0x0400, 0x68),
    "massage_foot_down": (0x01000000, 0x69),
    "massage_wave_up": (0x10000000, 0x58),
    "massage_wave_down": (0x04000000, 0x59),
    "massage_toggle": (0x0100, 0x5A),
    "massage_off": (0x02000000, 0x6F),
    "light_cycle": (0x040000, 0x70),
}


def profile_from_name(name: str) -> str | None:
    """Preserve the app's case-sensitive, specific-before-generic factory order."""
    if name.startswith(("STAR254205", "STAR255401")):
        return "f23"
    if name.startswith(("STAR255402", "STAR255403")):
        return "kneading"
    if name.startswith("STAR25"):
        return "cb25"
    if name.startswith("ELEVATE"):
        return "elevate"
    return None


def _app(controller: BedController) -> StarcodeM5X5Controller:
    if not isinstance(controller, StarcodeM5X5Controller):
        raise ValueError("This action requires the AdjustableM5X5 app profile")
    return controller


def _action(action: str) -> Callable[[BedController], Coroutine[object, object, None]]:
    async def run(controller: BedController) -> None:
        await _app(controller).app_action(action)

    return run


class StarcodeM5X5Controller(BedController):
    """One address and sender; accessory groups keep independent coordinators."""

    _write_with_response = False

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, profile: str, device_name: str | None = None
    ) -> None:
        super().__init__(coordinator)
        if profile not in PROFILES:
            raise ValueError("Choose an exact AdjustableM5X5 bedding class")
        self._profile = profile
        self.device_name = device_name if device_name is not None else coordinator.name
        self.dialect = "legacy"
        self._ready = False
        self._generation = 0
        self._sender_lock = asyncio.Lock()
        self._next_tick = 0.0
        self._state: dict[str, StateValue] = {}
        self._firmware = ""
        self._firmware_read_ok = False
        self._subscribed = False
        self._subscription_client: BleakClient | None = None
        self._write_session: ContextVar[tuple[BleakClient, int] | None] = ContextVar(
            f"starcode_write_session_{id(self)}", default=None
        )

    @property
    def client(self) -> BleakClient | None:
        self._require_write_session()
        return self._coordinator.client

    def _require_write_session(self) -> None:
        client = self._coordinator.client
        session = self._write_session.get()
        if session is not None:
            owned, generation = session
            # The shared writer re-reads client after waiting for the BLE lane.
            if (
                client is not owned
                or generation != self._generation
                or not self._ready
                or not owned.is_connected
            ):
                raise asyncio.CancelledError("AdjustableM5X5 write session was superseded")

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def ready(self) -> bool:
        return (
            self._ready
            and self.client is not None
            and self.client.is_connected
            and (not self._subscribed or self._subscription_client is self.client)
        )

    @property
    def session_generation(self) -> int:
        """Identify the notification session retained by a delayed group action."""
        return self._generation

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_position_feedback(self) -> bool:
        return self.profile != "elevate"

    @property
    def reports_percentage_position(self) -> bool:
        return self.supports_position_feedback

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return (
            tuple(
                build_position_number_spec(axis, max_value=100, unit=POSITION_UNIT_PERCENT)
                for axis in ("back", "legs", "lumbar")
            )
            if self.supports_position_feedback
            else ()
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs: tuple[MotorControlSpec, ...] = (
            MotorControlSpec(
                "back",
                "back",
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.move_back_stop(),
                position_key="back" if self.supports_position_feedback else None,
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda c: c.move_legs_up(),
                lambda c: c.move_legs_down(),
                lambda c: c.move_legs_stop(),
                position_key="legs" if self.supports_position_feedback else None,
            ),
            MotorControlSpec(
                "starcode_union",
                "starcode_union",
                _action("union_up"),
                _action("union_down"),
                lambda c: c.stop_all(),
            ),
        )
        if self.has_lumbar_support:
            specs += (
                MotorControlSpec(
                    "lumbar",
                    "lumbar",
                    _action("lumbar_up"),
                    _action("lumbar_down"),
                    lambda c: c.stop_all(),
                    position_key="lumbar",
                ),
            )
        return specs

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return (
            frozenset(("head", "feet", "lumbar"))
            if self.profile == "elevate"
            else frozenset(("head", "feet"))
        )

    @property
    def memory_slot_count(self) -> int:
        return 0 if self.profile == "elevate" else 2

    @property
    def supports_memory_programming(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_memory_presets(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_preset_lounge(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_massage(self) -> bool:
        return self.profile != "elevate"

    @property
    def auto_enable_massage(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_lights(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_light(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_massage_timer(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_massage_off_control(self) -> bool:
        return self.profile != "elevate"

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self.profile != "elevate"

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage else []

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return self.profile == "cb25"

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self._ready

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
            "motor_part4",
            "motor_part5",
            "motor_part6",
            "alarm_0",
            "alarm_1",
            "sonic_time_raw",
            "sonic_frequency",
            "sonic_head_level",
            "sonic_foot_level",
            "sonic_mode",
            "sonic_massage_type",
            "eq_volume",
            "eq_preset",
            "eq_low_frequency",
            "eq_high_frequency",
            "kneading_time_raw",
            "kneading_mode",
        ) + tuple(f"eq_band_{i}" for i in range(8))
        active = {spec.key for spec in self.controller_state_sensor_specs}
        return frozenset(f"starcode_{key}" for key in all_keys) - active

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        all_keys = (
            "firmware_read_ok",
            "motor_stopped",
            "massage_active",
            "light_on",
            "sonic_active",
            "usb_on",
            "kneading_on",
            "kneading_demo",
        )
        active = {spec.key for spec in self.controller_state_binary_sensor_specs}
        return frozenset(f"starcode_{key}" for key in all_keys) - active

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self.profile == "elevate":
            return ()
        return tuple(
            ControllerButtonSpec(
                f"starcode_{key}", label, _action(key), translation_key=f"starcode_{key}"
            )
            for key, label in (
                ("save_tv", "Save Ascent"),
                ("save_zero_g", "Save Zero Gravity"),
                ("save_lounge", "Save Lounge"),
                ("reset", "Reset saved positions"),
                ("light_mode", "Light mode 1"),
                ("light_cycle", "Cycle light color"),
                ("query", "Refresh massage and RGB"),
            )
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.profile == "elevate":
            return ()

        async def brightness(c: BedController, value: float) -> None:
            await _app(c).set_brightness(value)

        return (
            ControllerNumberSpec(
                "starcode_brightness",
                "starcode_brightness",
                "light_brightness",
                1,
                6,
                1,
                brightness,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.profile == "elevate":
            return ()

        async def color(c: BedController, option: str) -> None:
            await _app(c).set_color_index(int(option))

        return (
            ControllerSelectSpec(
                "starcode_color",
                "starcode_color",
                "light_color_option",
                tuple(str(i) for i in range(8)),
                color,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if self.profile == "elevate":
            return ()
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
            "motor_part4",
            "motor_part5",
            "motor_part6",
        )
        if self.profile == "cb25":
            keys += ("alarm_0",)
            if self.dialect == "star":
                keys += ("alarm_1",)
        else:
            keys += (
                "alarm_0",
                "alarm_1",
                "eq_volume",
                "eq_preset",
                "eq_low_frequency",
                "eq_high_frequency",
            ) + tuple(f"eq_band_{i}" for i in range(8))
        if self.profile == "kneading":
            keys += ("kneading_time_raw", "kneading_mode")
        return tuple(
            ControllerStateSensorSpec(
                f"starcode_{key}",
                f"starcode_{key}",
                key,
                "mdi:information-outline",
                attribute_keys=("light_rgb", "light_rgb_mode")
                if key == "light_color_index"
                else (key + "_details",),
            )
            for key in keys
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if self.profile == "elevate":
            return ()
        keys: tuple[str, ...] = (
            "motor_stopped",
            "massage_active",
            "light_on",
            "sonic_active",
            "firmware_read_ok",
        )
        if self.profile != "cb25":
            keys += ("usb_on",)
        if self.profile == "kneading":
            keys += ("kneading_on", "kneading_demo")
        return tuple(
            ControllerStateBinarySensorSpec(
                f"starcode_{key}", f"starcode_{key}", key, "mdi:information-outline"
            )
            for key in keys
        )

    def get_light_state(self) -> dict[str, object]:
        return {"is_on": self._state.get("light_on")}

    async def read_light_state(self) -> dict[str, object]:
        await self.query_status()
        return self.get_light_state()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("AdjustableM5X5 requires a connected transport")
        for uuid in (WRITE, NOTIFY, FIRMWARE):
            if client.services.get_characteristic(uuid) is None:
                raise ConnectionError(f"AdjustableM5X5 requires characteristic {uuid}")
        if (
            client.services.get_service(SERVICE) is None
            or client.services.get_service(DEVICE_INFORMATION) is None
        ):
            raise ConnectionError(
                "AdjustableM5X5 requires Nordic UART and Device Information services"
            )
        for uuid, service in ((WRITE, SERVICE), (NOTIFY, SERVICE), (FIRMWARE, DEVICE_INFORMATION)):
            role = client.services.get_characteristic(uuid)
            if role is None or role.service_uuid.lower() != service:
                raise ConnectionError("AdjustableM5X5 characteristic belongs to the wrong service")
        firmware = client.services.get_characteristic(FIRMWARE)
        if firmware is None or "read" not in firmware.properties:
            raise ConnectionError("AdjustableM5X5 requires readable firmware information")
        write = client.services.get_characteristic(WRITE)
        notify = client.services.get_characteristic(NOTIFY)
        if write is None or "write-without-response" not in write.properties:
            raise ConnectionError("AdjustableM5X5 requires write without response")
        if notify is None or not {"notify", "indicate"}.intersection(notify.properties):
            raise ConnectionError("AdjustableM5X5 requires an RX subscription")
        if self._subscribed:
            if self._subscription_client is not client:
                self._ready = False
            await self.stop_notify()
        self._ready = False
        self._notify_callback = callback
        self._generation += 1
        generation = self._generation
        pending: list[bytes] = []

        def require_owned_session() -> None:
            if (
                generation != self._generation
                or self.client is not client
                or not client.is_connected
            ):
                raise asyncio.CancelledError("AdjustableM5X5 startup session was superseded")

        def apply(data: bytes) -> None:
            updates = parse_notification(
                data, profile=self.profile, dialect=self.dialect, previous=self._state
            )
            if "light_on" in updates:
                updates["under_bed_lights_on"] = updates["light_on"]
            if isinstance(updates.get("light_color_index"), int):
                updates["light_color_option"] = str(updates["light_color_index"])
            self._state.update(updates)
            for axis in ("back", "legs", "lumbar"):
                value = updates.get(axis)
                if isinstance(value, (int, float)) and self._notify_callback is not None:
                    self._notify_callback(axis, float(value))
            if updates:
                self.forward_controller_state_updates(dict(updates))

        def receive(characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
            if generation != self._generation or self._coordinator.client is not client:
                return
            self.forward_raw_notification(NOTIFY, bytes(data))
            if not self._ready:
                pending.append(bytes(data))
            else:
                apply(bytes(data))

        await client.start_notify(NOTIFY, receive)
        if generation != self._generation:
            if self._subscription_client is not client:
                await client.stop_notify(NOTIFY)
            raise asyncio.CancelledError("AdjustableM5X5 subscription was superseded")
        self._subscribed = True
        self._subscription_client = client
        try:
            require_owned_session()
            try:
                firmware_version = "".join(
                    chr(b) for b in await asyncio.wait_for(client.read_gatt_char(FIRMWARE), 5)
                )
                firmware_read_ok = True
            except Exception:
                firmware_version = ""
                firmware_read_ok = False
            require_owned_session()
            try:
                manufacturer = (
                    await asyncio.wait_for(client.read_gatt_char(MANUFACTURER), 1)
                    if client.services.get_characteristic(MANUFACTURER) is not None
                    else b""
                )
            except Exception:
                manufacturer = b""
            require_owned_session()
            self._firmware = firmware_version
            self._firmware_read_ok = firmware_read_ok
            self.dialect = manufacturer_dialect(bytes(manufacturer))
            self._next_tick = asyncio.get_running_loop().time() + 0.1
            self._ready = True
            for payload in pending:
                apply(payload)
            pending.clear()
            self.forward_controller_state_updates(
                {"firmware": self._firmware, "firmware_read_ok": self._firmware_read_ok}
            )
            if self.dialect == "star" or self.profile == "elevate":
                await self.write_command(bytes.fromhex("5a0b00a5"))
                require_owned_session()
            if self.profile in ("f23", "kneading"):
                await self.write_command(clock_packet(dt_util.now()))
                require_owned_session()
            if self.profile != "elevate":
                await self.query_status()
                require_owned_session()
        except BaseException:
            if generation == self._generation and self._subscription_client is client:
                await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        self._generation += 1
        try:
            if self.ready and self.client is self._subscription_client:
                await self.stop_all()
        finally:
            self._ready = False
            self._notify_callback = None
            if self._state:
                self.forward_controller_state_updates(dict.fromkeys(self._state))
            self._state.clear()
            try:
                if (
                    self._subscribed
                    and self._subscription_client is not None
                    and self._subscription_client.is_connected
                ):
                    await self._subscription_client.stop_notify(NOTIFY)
            finally:
                self._subscribed = False
                self._subscription_client = None

    def motor_pulse_settings(self) -> tuple[int, int]:
        count, _ = super().motor_pulse_settings()
        return count, 100

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        return max(1, (duration_ms + 99) // 100)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "AdjustableM5X5",
            "profile": self.profile,
            "dialect": self.dialect,
            "ready": self.ready,
            "firmware": self._firmware,
            "firmware_read_ok": self._firmware_read_ok,
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
            raise ConnectionError("AdjustableM5X5 sender is not ready")
        client = self.client
        if client is None:
            raise ConnectionError("AdjustableM5X5 sender has no client")
        cancel = self._coordinator.cancel_command if cancel_event is None else cancel_event
        token = self._write_session.set((client, self._generation))
        try:
            async with self._sender_lock:
                for _ in range(repeat_count):
                    if cancel.is_set():
                        return
                    # Reject stale queued work before touching the current sender's tick.
                    self._require_write_session()
                    loop = asyncio.get_running_loop()
                    now = loop.time()
                    if self._next_tick < now:
                        self._next_tick += (math.floor((now - self._next_tick) / 0.1) + 1) * 0.1
                    await asyncio.sleep(max(0, self._next_tick - now))
                    if cancel.is_set():
                        return
                    self._require_write_session()
                    await self._write_gatt_with_retry(
                        WRITE, command, response=False, cancel_event=cancel
                    )
                    self._require_write_session()
                    self._next_tick += 0.1
        finally:
            self._write_session.reset(token)

    def packet(self, action: str, *, rgb: bool = False) -> bytes:
        dialect = "star" if rgb and self.profile in ("f23", "kneading") else self.dialect
        if self.profile == "elevate":
            keys = {
                "head_up": 0x40,
                "head_down": 0x41,
                "foot_up": 0x42,
                "foot_down": 0x43,
                "union_up": 0x44,
                "union_down": 0x45,
                "flat": 0x46,
            }
            if action not in keys:
                raise ValueError("Elevate does not support this bedding action")
            return normal_packet(0x03103000 | keys[action], "star")
        legacy, star = KEYS[action]
        return normal_packet((0x03103000 | star) if dialect == "star" else legacy, dialect)

    async def _send_stop(self) -> None:
        key = 0x0310300F if self.dialect == "star" or self.profile == "elevate" else 0
        await self.write_command(
            normal_packet(key, "star" if self.profile == "elevate" else self.dialect),
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        from ..starcode_accessory_group import cancel_group_operations

        cancel_group_operations(self._coordinator.hass, self._coordinator.entry.entry_id)
        await self._send_stop()

    async def interrupt(self) -> None:
        dialect = "star" if self.profile == "elevate" else self.dialect
        key = (0x0310304F if self.profile == "elevate" else 0x0310301F) if dialect == "star" else 0
        await self.write_command(normal_packet(key, dialect), cancel_event=asyncio.Event())

    async def app_action(self, action: str) -> None:
        if action == "query":
            await self.query_status()
            return
        if action == "light_cycle":
            await self.lights_cycle()
            return
        if action == "light_mode":
            await self.light_mode()
            return
        if self.profile == "elevate" and action not in (
            "head_up",
            "head_down",
            "foot_up",
            "foot_down",
            "union_up",
            "union_down",
            "flat",
        ):
            raise ValueError("This action is unavailable for Elevate")
        if action.startswith("save_") or action == "reset":
            await self.stop_all()
            try:
                await self.write_command(self.packet(action), repeat_count=55)
            finally:
                await self._send_stop()
            return
        held = action.endswith(("_up", "_down"))
        if (held and not action.startswith("massage_")) or action in (
            "flat",
            "tv",
            "zero_g",
            "anti_snore",
            "lounge",
            "memory_1",
            "memory_2",
        ):
            from ..starcode_accessory_group import interrupt_conflicting_group

            await interrupt_conflicting_group(self._coordinator)
        count = (
            self.motor_pulse_settings()[0]
            if held
            else 1
            if self.profile == "elevate"
            else 2
            if action.startswith("massage_")
            else 3
        )
        try:
            await self.write_command(self.packet(action), repeat_count=count)
        finally:
            if not (self.profile == "elevate" and action == "flat"):
                await self._send_stop()
            if held and action.startswith("massage_"):
                await self.write_command(query_packet(self.dialect), cancel_event=asyncio.Event())

    async def query_status(self) -> None:
        if self.profile == "elevate":
            raise ValueError("Elevate has no semantic status query")
        await self.write_command(
            query_packet("star" if self.profile in ("f23", "kneading") else self.dialect)
        )

    async def _rgb(self, command: bytes, count: int = 1, *, dialect: str | None = None) -> None:
        if self.profile == "elevate":
            raise ValueError("Elevate has no RGB controls")
        actual = dialect or ("star" if self.profile in ("f23", "kneading") else self.dialect)
        try:
            await self.write_command(command, repeat_count=count)
        finally:
            await self.write_command(
                normal_packet(0x0310300F if actual == "star" else 0, actual),
                cancel_event=asyncio.Event(),
            )

    async def lights_on(self) -> None:
        await self._light_switch(True)

    async def lights_off(self) -> None:
        await self._light_switch(False)

    async def _light_switch(self, enabled: bool) -> None:
        dialect = "star" if self.profile in ("f23", "kneading") else self.dialect
        key = (
            (0x03103073 if enabled else 0x03103074)
            if dialect == "star"
            else (0x40 if enabled else 0x80)
        )
        packet = (
            normal_packet(key, dialect)
            if dialect == "star"
            else bytes.fromhex("080200000000") + key.to_bytes(4, "big")
        )
        await self._rgb(packet, 1 if self.profile in ("f23", "kneading") else 2)

    async def lights_cycle(self) -> None:
        await self._rgb(
            self.packet("light_cycle", rgb=True), 1 if self.profile in ("f23", "kneading") else 2
        )

    async def set_brightness(self, value: float) -> None:
        if not math.isfinite(value) or value != int(value) or not 1 <= value <= 6:
            raise ValueError("AdjustableM5X5 brightness must be an integer from 1 to 6")
        dialect = "star" if self.profile in ("f23", "kneading") else self.dialect
        await self._rgb(extended_packet(0, int(value), dialect))

    async def set_color_index(self, index: int) -> None:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 7:
            raise ValueError("AdjustableM5X5 palette index must be from 0 to 7")
        dialect = "star" if self.profile in ("f23", "kneading") else self.dialect
        await self._rgb(extended_packet(1, index, dialect))

    async def light_mode(self) -> None:
        if self.profile == "elevate":
            raise ValueError("Elevate has no light mode")
        name = self.device_name
        remote = name[4:10] if len(name) > 14 else ""
        if self.profile == "cb25" and remote in SPECIAL_REMOTES:
            key = 0x0310307A if self.dialect == "star" else 0x00020004
            await self.write_command(normal_packet(key, self.dialect), repeat_count=35)
        else:
            await self._rgb(normal_packet(0x0310308A, "star"), dialect="star")

    async def set_massage_timer(self, minutes: int) -> None:
        if isinstance(minutes, bool) or minutes not in (10, 20, 30) or not self.supports_massage:
            raise ValueError("AdjustableM5X5 massage timer accepts 10, 20 or 30 minutes")
        await self._rgb(extended_packet(7, minutes // 10, self.dialect), dialect=self.dialect)

    async def move_head_up(self) -> None:
        await self.app_action("head_up")

    async def move_head_down(self) -> None:
        await self.app_action("head_down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.app_action("foot_up")

    async def move_feet_down(self) -> None:
        await self.app_action("foot_down")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_both_up(self) -> None:
        await self.app_action("union_up")

    async def move_both_down(self) -> None:
        await self.app_action("union_down")

    async def move_lumbar_up(self) -> None:
        await self.app_action("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self.app_action("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

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

    async def massage_head_up(self) -> None:
        await self.app_action("massage_head_up")

    async def massage_head_down(self) -> None:
        await self.app_action("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self.app_action("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self.app_action("massage_foot_down")

    async def massage_wave_next(self) -> None:
        await self.app_action("massage_wave_up")

    async def massage_wave_previous(self) -> None:
        await self.app_action("massage_wave_down")

    async def massage_toggle(self) -> None:
        await self.app_action("massage_toggle")

    async def massage_off(self) -> None:
        await self.app_action("massage_off")

    async def preset_memory(self, memory_num: int) -> None:
        if isinstance(memory_num, bool) or memory_num not in (1, 2):
            raise ValueError("AdjustableM5X5 has two memory slots")
        await self.app_action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if isinstance(memory_num, bool) or memory_num not in (1, 2):
            raise ValueError("AdjustableM5X5 has two programmable memory slots")
        await self.app_action(f"save_memory_{memory_num}")
