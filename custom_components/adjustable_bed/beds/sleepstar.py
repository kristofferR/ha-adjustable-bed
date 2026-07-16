"""SleepSpa S9000AI / SLEEPSTAR controller.

The SleepSpa app does not treat ``SLEEPSTAR`` as a normal CB25 controller.
It creates a CB37 sleep-monitor session over Nordic UART and tunnels StarCode
bed actions inside an ``AA 00 00 09 02`` transparent-transmission envelope.

Static behavior was recovered from SleepSpa 1.3.7
(``com.dot.bedding.sleepspa.sleep_spa``). Physical hardware validation remains
deferred, so the app's generic Part 4/Part 5 actuator labels are preserved.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    SLEEPSTAR_DUAL_SUBTYPE,
    SLEEPSTAR_MANUFACTURER_ID,
    SLEEPSTAR_SINGLE_SUBTYPE,
)
from .base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_SENDER_CADENCE_SECONDS = 0.1
_CONFIG_RETRY_SECONDS = 12.0
_DUPLICATE_NOTIFICATION_SECONDS = 0.2
_PRESET_REPEAT_COUNT = 3
_MEMORY_STORE_REPEAT_COUNT = 55


def star_normal(key: int) -> bytes:
    """Build the app's seven-byte StarCode normal frame."""
    return b"\x5a\x01" + int(key).to_bytes(4, "big") + b"\xa5"


def star_extended(key: int, value: int, value2: int = 0, value3: int = 0) -> bytes:
    """Build the app's StarCode extended-value frame."""
    return bytes([0x5A, 0xE0, 0x04, key & 0xFF, value & 0xFF, value2 & 0xFF, value3 & 0xFF, 0xA5])


def star_motor_position(zone: int, position: int) -> bytes:
    """Build a StarCode progress-motor frame for zone 0..4."""
    return bytes([0x5A, 0xF0, 0x03, zone & 0xFF, max(0, min(100, position)), 0x00, 0xA5])


def star_query(key: int) -> bytes:
    """Build a StarCode query frame."""
    return bytes([0x5A, key & 0xFF, 0x00, 0xA5])


def wrap_control_box(payload: bytes) -> bytes:
    """Wrap a StarCode payload for the SLEEPSTAR control-box route."""
    if len(payload) > 0xFF:
        raise ValueError("SLEEPSTAR control-box payload is too long")
    return bytes([0xAA, 0x00, 0x00, 0x09, 0x02, len(payload)]) + payload


def wrap_environment(payload: bytes) -> bytes:
    """Wrap a MODBUS payload for the SLEEPSTAR environment route."""
    if len(payload) > 0xFF:
        raise ValueError("SLEEPSTAR environment payload is too long")
    return bytes([0xAA, 0x00, 0x00, 0x09, 0x03, len(payload)]) + payload


def build_cb37_config_query(page: int) -> bytes:
    """Build the CB37 control-box configuration page query."""
    if not 1 <= page <= 8:
        raise ValueError("CB37 config page must be in range 1..8")
    return bytes([0x2A, 0, 0, 5, 0x81, 9, page, 0xFF, 0xFF, 0, 0, 0x22, 0x25, 0x12, 0x4B])


def build_cb37_time(now: datetime) -> bytes:
    """Build the unwrapped CB37 date/time calibration frame."""
    local = now.astimezone()
    offset = local.utcoffset()
    timezone_hours = int(offset.total_seconds() / 3600) if offset is not None else 0
    return bytes(
        [
            0xAA,
            0,
            0,
            3,
            1,
            8,
            (local.year - 2000) & 0xFF,
            local.month,
            local.day,
            local.hour,
            local.minute,
            local.second,
            local.isoweekday(),
            timezone_hours & 0xFF,
        ]
    )


def build_wrapped_star_time(now: datetime) -> bytes:
    """Build the demo device's transparent StarCode time calibration frame."""
    local = now.astimezone()
    inner = bytes(
        [
            0x5A,
            0x14,
            7,
            (local.year - 2000) & 0xFF,
            local.month,
            local.day,
            local.hour,
            local.minute,
            local.second,
            local.isoweekday(),
            0xA5,
        ]
    )
    return wrap_control_box(inner)


def build_sleep_query_config() -> bytes:
    """Build the sleep-monitor configuration query."""
    return bytes.fromhex("2A0000078100")


def build_sensor_version_query() -> bytes:
    """Build the sleep-sensor firmware-version query."""
    return bytes.fromhex("2A0000088100")


def build_environment_duration_query() -> bytes:
    """Build the environment-sensor working-duration query."""
    return bytes.fromhex("2A000009810101")


def build_anti_snore_config(*, enabled: bool, sensitivity: int, motor: int, duration: int) -> bytes:
    """Build the app's anti-snore configuration frame."""
    return bytes(
        [
            0xAA,
            0,
            0,
            7,
            1,
            8,
            sensitivity & 0xFF,
            duration & 0xFF,
            int(enabled),
            motor & 0xFF,
            0,
            0,
            0,
            0,
        ]
    )


def build_sleep_zone_config(*, zone_type: int, left: int, right: int) -> bytes:
    """Build the app's sleep-zone configuration frame."""
    return bytes([0xAA, 0, 0, 7, 4, 3, right & 0xFF, zone_type & 0xFF, left & 0xFF])


def build_monthly_report_query(*, side: int, year: int, month: int) -> bytes:
    """Build a left (0) or right (1) monthly sleep-report query."""
    if side not in (0, 1):
        raise ValueError("Sleep report side must be 0 (left) or 1 (right)")
    return bytes([0x2A, 0, 0, 7, 0x86 if side == 0 else 0x87, 2, year - 2000, month])


def build_daily_report_query(*, side: int, year: int, month: int, day: int) -> bytes:
    """Build a left (0) or right (1) daily sleep-report query."""
    if side not in (0, 1):
        raise ValueError("Sleep report side must be 0 (left) or 1 (right)")
    return bytes([0x2A, 0, 0, 7, 0x84 if side == 0 else 0x85, 3, year - 2000, month, day])


def crc16_modbus(data: bytes) -> int:
    """Return the CRC-16/MODBUS used only by the inner environment protocol."""
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc >> 1) ^ 0xA001) if crc & 1 else crc >> 1
    return crc & 0xFFFF


def _with_modbus_crc(data: bytes) -> bytes:
    crc = crc16_modbus(data)
    return data + bytes([crc & 0xFF, crc >> 8])


def build_environment_address_query() -> bytes:
    """Build the broadcast query for the environment-sensor MODBUS address."""
    return wrap_environment(_with_modbus_crc(bytes.fromhex("000200000001")))


def build_environment_register_query(address: int) -> bytes:
    """Build the seven-register environment query for a discovered address."""
    return wrap_environment(_with_modbus_crc(bytes([address & 0xFF, 3, 0, 2, 0, 7])))


def resolve_sleepstar_variant(manufacturer_data: dict[int, bytes] | None) -> str:
    """Resolve the app's single/dual class, including its dual fallback."""
    payload = (manufacturer_data or {}).get(SLEEPSTAR_MANUFACTURER_ID, b"")
    if len(payload) >= 7 and payload[6] == SLEEPSTAR_SINGLE_SUBTYPE:
        return "single"
    if len(payload) >= 7 and payload[6] == SLEEPSTAR_DUAL_SUBTYPE:
        return "dual"
    return "dual_fallback"


class SleepStarCommands:
    """Final SLEEPSTAR packets for integration-facing bed actions."""

    STOP = wrap_control_box(star_normal(0x0310300F))

    HEAD_UP = wrap_control_box(star_normal(0x03103000))
    HEAD_DOWN = wrap_control_box(star_normal(0x03103001))
    FEET_UP = wrap_control_box(star_normal(0x03103002))
    FEET_DOWN = wrap_control_box(star_normal(0x03103003))
    LUMBAR_UP = wrap_control_box(star_normal(0x03103004))
    LUMBAR_DOWN = wrap_control_box(star_normal(0x03103005))
    PART4_UP = wrap_control_box(star_normal(0x03103008))
    PART4_DOWN = wrap_control_box(star_normal(0x03103009))
    PART5_UP = wrap_control_box(star_normal(0x0310300A))
    PART5_DOWN = wrap_control_box(star_normal(0x0310300B))
    HEAD_FEET_UP = wrap_control_box(star_normal(0x0310300C))
    HEAD_FEET_DOWN = wrap_control_box(star_normal(0x0310300D))

    PRESET_FLAT = wrap_control_box(star_normal(0x03103010))
    PRESET_TV = wrap_control_box(star_normal(0x03103011))
    PRESET_ZERO_G = wrap_control_box(star_normal(0x03103013))
    PRESET_ANTI_SNORE = wrap_control_box(star_normal(0x03103016))
    PRESET_LOUNGE = wrap_control_box(star_normal(0x03103017))
    PRESET_MEMORY_1 = wrap_control_box(star_normal(0x0310301A))
    PRESET_MEMORY_2 = wrap_control_box(star_normal(0x0310301B))
    MEMORY_PRESETS = (PRESET_MEMORY_1, PRESET_MEMORY_2)

    STORE_MEMORY_1 = wrap_control_box(star_normal(0x03103094))
    STORE_MEMORY_2 = wrap_control_box(star_normal(0x03103095))
    MEMORY_STORE = (STORE_MEMORY_1, STORE_MEMORY_2)

    LIGHT_TOGGLE = wrap_control_box(star_normal(0x03103070))
    LIGHT_ON = wrap_control_box(star_normal(0x03103073))
    LIGHT_OFF = wrap_control_box(star_normal(0x03103074))

    QUERY_LIGHT = wrap_control_box(star_query(0xB0))
    QUERY_MOTORS = wrap_control_box(star_query(0xD0))


class SleepStarController(BedController):
    """Controller for SleepSpa S9000AI ``SLEEPSTAR`` devices."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.sleep_monitor_variant = resolve_sleepstar_variant(manufacturer_data)
        self._session_lock = asyncio.Lock()
        self._session_initialized = False
        self._notify_started = False
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._config_retry_task: asyncio.Task[None] | None = None
        self._config_pages_task: asyncio.Task[Any] | None = None
        self._config_bitmap: int | None = None
        self._config_pages: dict[int, bytes] = {}
        self._received_config_pages: set[int] = set()
        self._config_loaded = False
        self._motor_mask: int | None = None
        self._motor_type_mask: int | None = None
        self._soft_start_mask: int | None = None
        self._peripheral_info: tuple[int, int] | None = None
        self._positions: dict[str, float] = {}
        self._last_notification: bytes | None = None
        self._last_notification_time = 0.0
        self._massage_mode = -1
        self._massage_intensities = {"head": 0, "foot": 0, "all": 0}
        self._massage_timer_minutes = 0
        self._light_level = 0

    @property
    def control_characteristic_uuid(self) -> str:
        return NORDIC_UART_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_position_feedback(self) -> bool:
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        return True

    @property
    def allow_position_polling_during_commands(self) -> bool:
        return False

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
    def supports_preset_both_up(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_level_control(self) -> bool:
        return True

    @property
    def light_level_max(self) -> int:
        return 6

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["head", "foot", "all"]

    @property
    def massage_intensity_max(self) -> int:
        return 6

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose only app-addressable motors, retaining unproven Part labels."""
        return (
            MotorControlSpec(
                key="head",
                translation_key="head",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
                position_key="head",
                max_angle=100,
            ),
            MotorControlSpec(
                key="feet",
                translation_key="feet",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                position_key="feet",
                max_angle=100,
            ),
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                position_key="lumbar",
                max_angle=100,
            ),
            MotorControlSpec(
                key="sleepstar_part4",
                translation_key="auxiliary_1",
                open_fn=lambda ctrl: ctrl.move_neck_up(),
                close_fn=lambda ctrl: ctrl.move_neck_down(),
                stop_fn=lambda ctrl: ctrl.move_neck_stop(),
                position_key="sleepstar_part4",
                max_angle=100,
            ),
            MotorControlSpec(
                key="sleepstar_part5",
                translation_key="auxiliary_2",
                open_fn=lambda ctrl: ctrl.move_pillow_up(),
                close_fn=lambda ctrl: ctrl.move_pillow_down(),
                stop_fn=lambda ctrl: ctrl.move_pillow_stop(),
                position_key="sleepstar_part5",
                max_angle=100,
            ),
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"back", "legs"})

    def _track_task(self, coroutine: Any, *, name: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _write_frame(
        self,
        frame: bytes,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            frame,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    async def _initialize_session_locked(self) -> None:
        if self._session_initialized:
            return

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Cannot initialize SLEEPSTAR while disconnected")

        if not self._notify_started:
            await client.start_notify(NORDIC_UART_READ_CHAR_UUID, self._on_notification)
            self._notify_started = True

        fresh_event = asyncio.Event()
        now = datetime.now().astimezone()
        # Cb37BaseBleDevice startup followed by the demo subclass startup.
        startup_frames = (
            build_cb37_config_query(1),
            build_cb37_time(now),
            build_wrapped_star_time(now),
            build_sensor_version_query(),
        )
        for index, frame in enumerate(startup_frames):
            await self._write_frame(frame, cancel_event=fresh_event)
            if index < len(startup_frames) - 1:
                await asyncio.sleep(_SENDER_CADENCE_SECONDS)

        self._session_initialized = True
        self.forward_controller_state_update("sleepstar_variant", self.sleep_monitor_variant)
        self._config_retry_task = self._track_task(
            self._retry_config_once(), name="sleepstar_config_retry"
        )

        # These are the app's view-state queries. They hydrate all reachable
        # protocol families while the notification route is already active.
        await asyncio.sleep(_SENDER_CADENCE_SECONDS)
        await self.refresh_protocol_state()

    async def _ensure_session(self) -> None:
        async with self._session_lock:
            await self._initialize_session_locked()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        await self._ensure_session()

    async def stop_notify(self) -> None:
        self._notify_callback = None
        if self._config_retry_task is not None:
            self._config_retry_task.cancel()
            self._config_retry_task = None
        for task in tuple(self._background_tasks):
            task.cancel()
        for task in tuple(self._background_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._background_tasks.clear()
        self._config_pages_task = None

        client = self.client
        if self._notify_started and client is not None and client.is_connected:
            with contextlib.suppress(BleakError):
                await client.stop_notify(NORDIC_UART_READ_CHAR_UUID)
        self._notify_started = False
        self._session_initialized = False

    async def stop_keepalive(self) -> None:
        """Cancel session-owned tasks during an unexpected disconnect."""
        for task in tuple(self._background_tasks):
            task.cancel()
        for task in tuple(self._background_tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._background_tasks.clear()
        self._config_retry_task = None
        self._config_pages_task = None

    async def _retry_config_once(self) -> None:
        try:
            await asyncio.sleep(_CONFIG_RETRY_SECONDS)
            client = self.client
            if client is not None and client.is_connected:
                await self._query_device_config(reset=True)
        except BleakError, ConnectionError:
            _LOGGER.debug("SLEEPSTAR config recovery query failed", exc_info=True)

    async def _query_device_config(self, *, reset: bool) -> None:
        if reset:
            self._config_bitmap = None
            self._config_pages.clear()
            self._received_config_pages.clear()
            self._config_loaded = False
            self.forward_controller_state_update("sleepstar_config_loaded", False)
        await self._write_frame(build_cb37_config_query(1), cancel_event=asyncio.Event())

    async def refresh_protocol_state(self) -> None:
        """Query motor, RGB, sleep, and environment state using proven frames."""
        frames = (
            SleepStarCommands.QUERY_MOTORS,
            SleepStarCommands.QUERY_LIGHT,
            build_sleep_query_config(),
            build_environment_duration_query(),
            build_environment_address_query(),
        )
        for index, frame in enumerate(frames):
            await self._write_frame(frame, cancel_event=asyncio.Event())
            if index < len(frames) - 1:
                await asyncio.sleep(_SENDER_CADENCE_SECONDS)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._ensure_session()
        await self._write_frame(
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    def _on_notification(
        self, characteristic: BleakGATTCharacteristic | int, data: bytearray
    ) -> None:
        raw = bytes(data)
        uuid = getattr(characteristic, "uuid", NORDIC_UART_READ_CHAR_UUID)
        self.forward_raw_notification(str(uuid), raw)

        now = time.monotonic()
        if (
            raw == self._last_notification
            and now - self._last_notification_time < _DUPLICATE_NOTIFICATION_SECONDS
        ):
            return
        self._last_notification = raw
        self._last_notification_time = now

        if len(raw) >= 20 and raw[0] == 0x2A and raw[3] == 5 and raw[4] == 0x81:
            self._handle_config_response(raw)
            return

        inner: bytes | None = None
        if len(raw) >= 3 and raw[0] == 0xA5:
            inner = raw
        elif (
            len(raw) >= 9
            and raw[0] == 0xAA
            and raw[4] == 2
            and len(raw) >= 6 + raw[5]
            and raw[6] == 0xA5
        ):
            inner = raw[6 : 6 + raw[5]]
        if inner is not None:
            self._handle_star_notification(inner)
            return

        if len(raw) >= 9 and raw[0] == 0x2A and raw[6] == 9 and raw[8] in (3, 0x81):
            self.forward_controller_state_update("sleepstar_environment_response", raw.hex())
            return

        if len(raw) >= 5 and raw[0] in (0x2A, 0xEA):
            command = raw[4]
            key = (
                "sleepstar_daily_report_response"
                if command in (0x84, 0x85)
                else "sleepstar_monthly_report_response"
                if command in (0x86, 0x87)
                else "sleepstar_config_response"
                if command == 0x81
                else "sleepstar_ota_response"
                if command in (1, 3)
                else "sleepstar_protocol_response"
            )
            self.forward_controller_state_update(key, raw.hex())

    def _handle_config_response(self, raw: bytes) -> None:
        bitmap = raw[6]
        page = raw[7]
        self._config_bitmap = bitmap
        self._config_pages[page] = raw
        self._received_config_pages.add(page)

        updates: dict[str, Any] = {
            "sleepstar_config_bitmap": bitmap,
            "sleepstar_config_pages": sorted(self._received_config_pages),
        }
        if page in (0, 1):
            self._motor_mask = raw[8]
            self._motor_type_mask = raw[9]
            self._soft_start_mask = raw[10]
            self._peripheral_info = (raw[11], raw[12])
            updates.update(
                {
                    "sleepstar_motor_mask": self._motor_mask,
                    "sleepstar_motor_type_mask": self._motor_type_mask,
                    "sleepstar_soft_start_mask": self._soft_start_mask,
                    "sleepstar_peripheral_info": list(self._peripheral_info),
                }
            )

            missing_pages = [
                bit + 1
                for bit in range(1, 8)
                if bitmap & (1 << bit) and bit + 1 not in self._received_config_pages
            ]
            if missing_pages and (
                self._config_pages_task is None or self._config_pages_task.done()
            ):
                self._config_pages_task = self._track_task(
                    self._query_missing_config_pages(missing_pages),
                    name="sleepstar_config_pages",
                )

        expected_pages = bitmap.bit_count()
        self._config_loaded = len(self._received_config_pages) >= expected_pages
        updates["sleepstar_config_loaded"] = self._config_loaded
        self.forward_controller_state_updates(updates)

    async def _query_missing_config_pages(self, pages: list[int]) -> None:
        for index, page in enumerate(pages):
            if page not in self._received_config_pages:
                await self._write_frame(build_cb37_config_query(page), cancel_event=asyncio.Event())
            if index < len(pages) - 1:
                await asyncio.sleep(_SENDER_CADENCE_SECONDS)

    def _handle_star_notification(self, data: bytes) -> None:
        if len(data) < 3 or data[0] != 0xA5:
            return

        state_key = {
            0x0B: "sleepstar_sonic_response",
            0x0C: "sleepstar_alarm_response",
            0x0E: "sleepstar_eq_response",
        }.get(data[2])
        if state_key is not None:
            self.forward_controller_state_update(state_key, data.hex())
            return

        if len(data) < 11 or data[2] != 0x0D:
            return

        values = {
            "head": float(min(100, data[4])),
            "feet": float(min(100, data[6])),
            "lumbar": float(min(100, data[8])),
            "sleepstar_part4": float(min(100, data[10])),
            "sleepstar_part5": float(min(100, data[5])),
        }
        self._positions.update(values)
        if self._notify_callback is not None:
            for key, value in values.items():
                self._notify_callback(key, value)
        self.forward_controller_state_updates(
            {
                "sleepstar_part6_position": min(100, data[7]),
                "sleepstar_positions": {key: int(value) for key, value in values.items()},
            }
        )

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        await self.write_command(SleepStarCommands.QUERY_MOTORS)

    async def set_motor_position(self, motor: str, position: int) -> None:
        zone_map = {
            "head": 0,
            "back": 0,
            "feet": 1,
            "legs": 1,
            "lumbar": 2,
            "sleepstar_part4": 3,
            "sleepstar_part5": 4,
        }
        try:
            zone = zone_map[motor]
        except KeyError as err:
            raise ValueError(f"Unknown SLEEPSTAR motor: {motor}") from err
        await self.write_command(
            wrap_control_box(star_motor_position(zone, max(0, min(100, int(position)))))
        )

    def angle_to_native_position(self, motor: str, angle: float) -> int:  # noqa: ARG002
        return int(max(0, min(100, angle)))

    async def _send_stop(self) -> None:
        await self.write_command(SleepStarCommands.STOP, cancel_event=asyncio.Event())

    async def move_head_up(self) -> None:
        await self._move_with_stop(SleepStarCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        await self._move_with_stop(SleepStarCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(SleepStarCommands.FEET_UP)

    async def move_feet_down(self) -> None:
        await self._move_with_stop(SleepStarCommands.FEET_DOWN)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_lumbar_up(self) -> None:
        await self._move_with_stop(SleepStarCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        await self._move_with_stop(SleepStarCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    async def move_part4_up(self) -> None:
        await self._move_with_stop(SleepStarCommands.PART4_UP)

    async def move_part4_down(self) -> None:
        await self._move_with_stop(SleepStarCommands.PART4_DOWN)

    async def move_part4_stop(self) -> None:
        await self._send_stop()

    async def move_part5_up(self) -> None:
        await self._move_with_stop(SleepStarCommands.PART5_UP)

    async def move_part5_down(self) -> None:
        await self._move_with_stop(SleepStarCommands.PART5_DOWN)

    async def move_part5_stop(self) -> None:
        await self._send_stop()

    # Use base-class optional method names for generic motor entity dispatch,
    # without claiming physical neck/pillow semantics in the exposed labels.
    async def move_neck_up(self) -> None:
        await self.move_part4_up()

    async def move_neck_down(self) -> None:
        await self.move_part4_down()

    async def move_neck_stop(self) -> None:
        await self.move_part4_stop()

    async def move_pillow_up(self) -> None:
        await self.move_part5_up()

    async def move_pillow_down(self) -> None:
        await self.move_part5_down()

    async def move_pillow_stop(self) -> None:
        await self.move_part5_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    async def preset_both_up(self) -> None:
        await self._move_with_stop(SleepStarCommands.HEAD_FEET_UP)

    async def _send_preset(self, command: bytes) -> None:
        try:
            await self.write_command(
                command,
                repeat_count=_PRESET_REPEAT_COUNT,
                repeat_delay_ms=100,
            )
            await asyncio.sleep(_SENDER_CADENCE_SECONDS)
        finally:
            with contextlib.suppress(BleakError, ConnectionError):
                await self._send_stop()

    async def preset_flat(self) -> None:
        await self._send_preset(SleepStarCommands.PRESET_FLAT)

    async def preset_tv(self) -> None:
        await self._send_preset(SleepStarCommands.PRESET_TV)

    async def preset_zero_g(self) -> None:
        await self._send_preset(SleepStarCommands.PRESET_ZERO_G)

    async def preset_anti_snore(self) -> None:
        await self._send_preset(SleepStarCommands.PRESET_ANTI_SNORE)

    async def preset_lounge(self) -> None:
        await self._send_preset(SleepStarCommands.PRESET_LOUNGE)

    async def preset_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= len(SleepStarCommands.MEMORY_PRESETS):
            raise ValueError("SLEEPSTAR memory slot must be 1 or 2")
        await self._send_preset(SleepStarCommands.MEMORY_PRESETS[memory_num - 1])

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= len(SleepStarCommands.MEMORY_STORE):
            raise ValueError("SLEEPSTAR memory slot must be 1 or 2")
        await self.write_command(
            SleepStarCommands.MEMORY_STORE[memory_num - 1],
            repeat_count=_MEMORY_STORE_REPEAT_COUNT,
            repeat_delay_ms=100,
        )

    async def lights_on(self) -> None:
        await self.write_command(SleepStarCommands.LIGHT_ON)
        self.forward_controller_state_update("under_bed_lights_on", True)

    async def lights_off(self) -> None:
        await self.write_command(SleepStarCommands.LIGHT_OFF)
        self._light_level = 0
        self.forward_controller_state_updates({"under_bed_lights_on": False, "light_level": 0})

    async def lights_toggle(self) -> None:
        await self.write_command(SleepStarCommands.LIGHT_TOGGLE)

    async def _send_twice_then_stop(self, command: bytes) -> None:
        try:
            await self.write_command(command, repeat_count=2, repeat_delay_ms=100)
            await asyncio.sleep(_SENDER_CADENCE_SECONDS)
        finally:
            with contextlib.suppress(BleakError, ConnectionError):
                await self._send_stop()

    async def set_light_level(self, level: int) -> None:
        normalized = max(0, min(self.light_level_max, int(level)))
        if normalized == 0:
            await self.lights_off()
            return
        await self._send_twice_then_stop(wrap_control_box(star_extended(0x00, normalized)))
        self._light_level = normalized
        self.forward_controller_state_updates(
            {"under_bed_lights_on": True, "light_level": normalized}
        )

    async def set_light_color_index(self, index: int) -> None:
        """Set one of the app's eight palette indices (0..7)."""
        if not 0 <= index <= 7:
            raise ValueError("SLEEPSTAR color index must be in range 0..7")
        await self._send_twice_then_stop(wrap_control_box(star_extended(0x01, index)))

    async def massage_off(self) -> None:
        await self.set_massage_timer(0)

    async def massage_mode_step(self) -> None:
        self._massage_mode = (self._massage_mode + 1) % 5
        await self._send_twice_then_stop(wrap_control_box(star_extended(0x08, self._massage_mode)))

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        normalized = max(0, min(self.massage_intensity_max, int(level)))
        if zone == "head":
            command = star_extended(0x0F, normalized)
        elif zone == "foot":
            command = star_extended(0x10, normalized)
        elif zone == "all":
            command = star_extended(0x11, normalized, normalized)
        else:
            raise ValueError(f"Unsupported SLEEPSTAR sonic zone: {zone}")
        await self._send_twice_then_stop(wrap_control_box(command))
        self._massage_intensities[zone] = normalized
        self.forward_controller_state_update(f"massage_{zone}_intensity", normalized)

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes == 0:
            encoded = 0
        else:
            try:
                encoded = self.massage_timer_options.index(int(minutes)) + 1
            except ValueError as err:
                raise ValueError("SLEEPSTAR sonic timer must be 0, 10, 20, or 30 minutes") from err
        await self._send_twice_then_stop(wrap_control_box(star_extended(0x0B, encoded)))
        self._massage_timer_minutes = int(minutes)
        self.forward_controller_state_updates(
            {
                "massage_timer": int(minutes),
                "massage_active": int(minutes) > 0,
            }
        )

    def get_massage_state(self) -> dict[str, object]:
        return {
            **{f"{zone}_intensity": value for zone, value in self._massage_intensities.items()},
            "timer_mode": str(self._massage_timer_minutes),
            "active": self._massage_timer_minutes > 0,
        }

    async def query_sleep_config(self) -> None:
        await self.write_command(build_sleep_query_config())

    async def set_anti_snore_config(
        self, *, enabled: bool, sensitivity: int, motor: int, duration: int
    ) -> None:
        await self.write_command(
            build_anti_snore_config(
                enabled=enabled,
                sensitivity=sensitivity,
                motor=motor,
                duration=duration,
            )
        )

    async def set_sleep_zone_config(self, *, zone_type: int, left: int, right: int) -> None:
        await self.write_command(
            build_sleep_zone_config(zone_type=zone_type, left=left, right=right)
        )

    async def query_monthly_report(self, *, side: int, year: int, month: int) -> None:
        await self.write_command(build_monthly_report_query(side=side, year=year, month=month))

    async def query_daily_report(self, *, side: int, year: int, month: int, day: int) -> None:
        await self.write_command(
            build_daily_report_query(side=side, year=year, month=month, day=day)
        )

    async def query_environment_address(self) -> None:
        await self.write_command(build_environment_address_query())

    async def query_environment_registers(self, address: int) -> None:
        await self.write_command(build_environment_register_query(address))

    async def media_previous(self) -> None:
        await self.write_command(wrap_control_box(star_normal(0x03104018)))

    async def media_play_pause(self) -> None:
        await self.write_command(wrap_control_box(star_normal(0x0310401A)))

    async def media_next(self) -> None:
        await self.write_command(wrap_control_box(star_normal(0x03104019)))

    async def media_volume_up(self) -> None:
        await self.write_command(wrap_control_box(star_normal(0x03104016)))

    async def media_volume_down(self) -> None:
        await self.write_command(wrap_control_box(star_normal(0x03104017)))

    async def usb_play(self) -> None:
        await self.write_command(wrap_control_box(star_normal(51400707)))

    async def usb_exit(self) -> None:
        await self.write_command(wrap_control_box(star_normal(51396657)))

    async def play_noise(self, index: int) -> None:
        if index not in (1, 2, 3):
            raise ValueError("SLEEPSTAR noise index must be 1, 2, or 3")
        await self.write_command(wrap_control_box(star_normal(0x0310401F + index)))

    async def stop_noise(self) -> None:
        await self.write_command(wrap_control_box(star_normal(0x03104023)))

    async def set_noise_volume(self, level: int) -> None:
        """Set the app's raw noise-volume value."""
        await self.write_command(wrap_control_box(star_extended(10, max(0, min(255, int(level))))))

    async def set_sonic_type(self, sonic_type: int) -> None:
        """Select one of the two app-proven sonic types."""
        if sonic_type not in (0, 1):
            raise ValueError("SLEEPSTAR sonic type must be 0 or 1")
        await self.write_command(wrap_control_box(star_normal((51396626, 51396627)[sonic_type])))

    async def reset_sound(self) -> None:
        await self.write_command(wrap_control_box(star_normal(51396661)))

    async def select_sound_preset(self, preset: int) -> None:
        """Select one of the six EQ presets in app order."""
        keys = (51396659, 51396666, 51396658, 51396660, 51396667, 51396668)
        if not 0 <= preset < len(keys):
            raise ValueError("SLEEPSTAR sound preset must be in range 0..5")
        await self.write_command(wrap_control_box(star_normal(keys[preset])))

    async def set_sound_cutoff(self, value: int) -> None:
        await self.write_command(wrap_control_box(star_extended(14, max(0, min(255, int(value))))))

    async def set_eq_profile_value(self, value: int) -> None:
        """Set one of the app's eight EQ brands or two band selectors."""
        if not 1 <= value <= 10:
            raise ValueError("SLEEPSTAR EQ profile value must be in range 1..10")
        await self.write_command(wrap_control_box(star_extended(13, value)))
