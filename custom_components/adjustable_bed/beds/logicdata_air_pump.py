"""LOGICDATA Sleep Smart Air Mattress pump, from the accepted 1.0.0 app report.

The pump is a separate BLE device with LF-terminated text commands. A tap sends
one command and the pump keeps running until its own logic or ``C>STOPN``; the
app has no hold or release frame. Pressure replies are decoded independently of
the query that requested them.
"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

STOP = b"C>STOPN\n"
SAVE_MEMORY = b"C>MEM_S>0\n"
QUERY_PRESSURE = b"R>SP>0\n"
# The "60" mode button sends the same FILL text as inflate.
COMMANDS: dict[str, bytes] = {
    "inflate": b"C>FILL>0\n",
    "deflate": b"C>EXCAPE>0\n",
    "firmness_30": b"C>SETP>0>30\n",
    "recall_memory": b"C>MEMORY>0\n",
}
_LABELS = {
    "inflate": "Inflate",
    "deflate": "Deflate",
    "firmness_30": "Firmness 30",
    "recall_memory": "Recall pressure memory",
    "save_memory": "Save pressure memory",
}
_ICONS = {
    "inflate": "mdi:arrow-up-bold",
    "deflate": "mdi:arrow-down-bold",
    "firmness_30": "mdi:gauge",
    "recall_memory": "mdi:gauge-full",
    "save_memory": "mdi:content-save",
}
# Taps are accepted at most every 500 ms; the pressure query bypasses that.
CLICK_INTERVAL_MS = 500
QUERY_DELAY_MS = 800
QUERY_INTERVAL_MS = 500
RENAME_OFFSETS_MS = (0, 50, 100)
NAME_ALPHABET = frozenset("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZäöüÄÖÜß")
NAME_MAX_CHARS = 20
NAME_MAX_BYTES = 40
PRESSURE_STATE = "logicdata_air_pump_pressure"
_PREFIX = "logicdata_air_pump_"


def rename_frames(name: str) -> tuple[bytes, bytes, bytes]:
    """Validate the app's edit-field rule and build its three AT phases."""
    encoded = name.encode("utf-8")
    if (
        not 1 <= len(name) <= NAME_MAX_CHARS
        or len(encoded) > NAME_MAX_BYTES
        or not set(name) <= NAME_ALPHABET
    ):
        raise ValueError("Name must contain 1..20 letters, digits, ä, ö, ü or ß")
    return b"AT+ENAT\r\n", b"AT+LENA" + encoded + b"\r\n", b"AT+REST\r\n"


def _java_hex_digit(unit: int) -> int | None:
    """Character.digit(c, 16) for one UTF-16 unit; surrogates are not digits."""
    if 0xD800 <= unit <= 0xDFFF:
        return None
    char = chr(unit)
    decimal = unicodedata.decimal(char, None)
    if decimal is not None:
        return decimal
    for base in (ord("A"), ord("a"), 0xFF21, 0xFF41):
        if base <= unit < base + 6:
            return 10 + unit - base
    return None


def parse_pressure(data: bytes) -> int | None:
    """Decode ``RET>SP>`` like the app: UTF-16 chars 13..14 as signed radix-16.

    Java's parser rejects whitespace and accepts one leading sign followed by a
    digit. Short, unprefixed or invalid replies return None; no unit is known.
    """
    text = data.decode("utf-8", errors="replace")
    if "RET>SP" not in text or not text.startswith("RET>SP>"):
        return None
    encoded = text.encode("utf-16-le", errors="surrogatepass")
    units = [int.from_bytes(encoded[i : i + 2], "little") for i in range(0, len(encoded), 2)]
    if len(units) < 15:
        return None
    field = units[13:15]
    sign = 1
    if field[0] in (ord("+"), ord("-")):
        sign = -1 if field[0] == ord("-") else 1
        field = field[1:]
    value = 0
    for unit in field:
        digit = _java_hex_digit(unit)
        if digit is None:
            return None
        value = value * 16 + digit
    return sign * value


def _action(key: str) -> MotorCommandCallable:
    async def press(controller: BedController) -> None:
        await cast(LogicdataAirPumpController, controller).press(key)

    return press


class LogicdataAirPumpController(BedController):
    """Air pump controls, pressure polling and rename, with no motors."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._last_click: float | None = None
        self._next_query: float | None = None
        self._subscribed = False

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_device_rename(self) -> bool:
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"{_PREFIX}{key}",
                label,
                _action(key),
                icon=_ICONS[key],
                translation_key=f"{_PREFIX}{key}",
            )
            for key, label in _LABELS.items()
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                key=PRESSURE_STATE,
                translation_key=PRESSURE_STATE,
                state_key=PRESSURE_STATE,
                icon="mdi:gauge",
            ),
        )

    @property
    def diagnostic_poll_interval(self) -> float | None:
        """Poll on a live link; ``async_refresh_diagnostics`` keeps the app cadence."""
        return QUERY_INTERVAL_MS / 1000

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to the air pump")
        service = client.services.get_service(SERVICE_UUID)
        if service is None or service.get_characteristic(WRITE_UUID) is None:
            raise ValueError("The air pump's ffe0 service or ffe1 write characteristic is absent")

    async def _wait(self, seconds: float, event: asyncio.Event) -> bool:
        """Sleep unless cancelled; return False when the event fires first."""
        if seconds <= 0:
            return not event.is_set()
        try:
            async with asyncio.timeout(seconds):
                await event.wait()
        except TimeoutError:
            return True
        return False

    async def _write(self, packet: bytes, cancel_event: asyncio.Event | None = None) -> None:
        # The app forces WRITE_TYPE_DEFAULT, a write with response.
        await self._write_gatt_with_retry(
            WRITE_UUID, packet, cancel_event=cancel_event, response=True
        )

    async def _click(self, packet: bytes) -> bool:
        """Keep the app's 500 ms tap spacing, waiting instead of dropping the tap."""
        event = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        if self._last_click is not None and not await self._wait(
            self._last_click + CLICK_INTERVAL_MS / 1000 - loop.time(), event
        ):
            return False
        if event.is_set():
            return False
        self._last_click = loop.time()
        await self._write(packet)
        return True

    async def press(self, key: str) -> None:
        if key == "save_memory":
            # The app stops, asks for confirmation, then saves; the shared
            # throttle keeps the save at least 500 ms after the stop.
            if await self._click(STOP):
                await self._click(SAVE_MEMORY)
            return
        if key not in COMMANDS:
            raise ValueError(f"Unknown air pump action {key}")
        await self._click(COMMANDS[key])

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            WRITE_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=True,
        )

    async def stop_all(self) -> None:
        """Send the app's STOPN at once; a stop is never delayed by the tap throttle."""
        self._last_click = asyncio.get_running_loop().time()
        await self._write(STOP, asyncio.Event())

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to the air pump")
        if not self._subscribed:
            if client.services.get_characteristic(NOTIFY_UUID) is None:
                _LOGGER.debug("Air pump has no ffe2 notification characteristic")
            else:
                async with self._ble_lock:
                    await client.start_notify(NOTIFY_UUID, self._notification_handler)
                self._subscribed = True
        self._next_query = asyncio.get_running_loop().time() + QUERY_DELAY_MS / 1000

    async def stop_notify(self) -> None:
        client = self.client
        try:
            if self._subscribed and client is not None and client.is_connected:
                async with self._ble_lock:
                    await client.stop_notify(NOTIFY_UUID)
        except Exception:
            _LOGGER.debug("Unable to unsubscribe air pump notifications", exc_info=True)
        finally:
            self._subscribed = False
            self._next_query = None
            self._notify_callback = None

    async def async_refresh_diagnostics(self) -> None:
        """Query pressure 800 ms after setup, then 500 ms after each query."""
        if self._next_query is None:
            return
        loop = asyncio.get_running_loop()
        await asyncio.sleep(max(0, self._next_query - loop.time()))
        self._next_query = loop.time() + QUERY_INTERVAL_MS / 1000
        await self._write(QUERY_PRESSURE, asyncio.Event())

    def invalidate_diagnostics(self) -> None:
        # The coordinator also calls this when it (re)schedules polling right
        # after start_notify, so keep the 800 ms anchor; stop_notify clears it.
        self._last_click = None
        self.forward_controller_state_updates({PRESSURE_STATE: None})

    def _notification_handler(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        pressure = parse_pressure(bytes(data))
        if pressure is not None:
            self.forward_controller_state_updates({PRESSURE_STATE: pressure})

    def validate_device_rename(self, name: str) -> None:
        rename_frames(name)

    async def rename_device(self, name: str) -> None:
        """Send AT+ENAT, AT+LENA<name> at 50 ms and AT+REST at 100 ms."""
        frames = rename_frames(name)
        event = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        if self._last_click is not None and not await self._wait(
            self._last_click + CLICK_INTERVAL_MS / 1000 - loop.time(), event
        ):
            return
        started = loop.time()
        self._last_click = started
        for offset, frame in zip(RENAME_OFFSETS_MS, frames, strict=True):
            if not await self._wait(started + offset / 1000 - loop.time(), event):
                return
            await self._write(frame)

    async def _unsupported(self) -> None:
        raise NotImplementedError("The air pump has no motors or bed presets")

    async def move_head_up(self) -> None:
        await self._unsupported()

    async def move_head_down(self) -> None:
        await self._unsupported()

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._unsupported()

    async def move_back_down(self) -> None:
        await self._unsupported()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._unsupported()

    async def move_legs_down(self) -> None:
        await self._unsupported()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._unsupported()

    async def move_feet_down(self) -> None:
        await self._unsupported()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self._unsupported()

    async def preset_memory(self, memory_num: int) -> None:
        await self._unsupported()

    async def program_memory(self, memory_num: int) -> None:
        await self._unsupported()
