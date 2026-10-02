"""Adjustable bed (Lumbar) app profile (com.okin.bedding.adjustablelumbar 1.2.2).

Accepted as APK audit row054. The app ships three command tables and picks one
from the lowercase Bluetooth name: ``okin`` selects ``36_33_04a`` (OKIN service,
write with response); ``star`` selects ``25_42_02`` (Nordic UART, write without
response), upgraded to ``35_22_01`` when the Device Information manufacturer
characteristic returns exactly the four bytes ``STAR``. Any other name has no
table. All tables expose the same controls. Hardware is unverified.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Final, Literal

from bleak.exc import BleakError

from ..const import (
    ADJUSTABLE_LUMBAR_VARIANT_OKIN,
    ADJUSTABLE_LUMBAR_VARIANT_STAR,
    CONF_BLE_DEVICE_NAME,
)
from ..detection import is_mac_like_name
from .base import (
    BedController,
    ControllerButtonSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

Table = Literal["25_42_02", "35_22_01", "36_33_04a"]
Branch = Literal["okin", "star"]

NUS_SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
OKIN_SERVICE: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
OKIN_WRITE: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
OKIN_NOTIFY: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"
DEVICE_INFO_SERVICE: Final = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_CHAR: Final = "00002a29-0000-1000-8000-00805f9b34fb"
STAR_MANUFACTURER: Final = b"STAR"  # Exact, case-sensitive; a trailing NUL fails.

REFRESH_MS: Final = 100  # Held controls write immediately, then every 100 ms.
RELEASE_STOP_OFFSETS_S: Final = (0.0, 0.3)  # Release: STOP now and at +300 ms.
EXTRA_WRITE_S: Final = 0.1  # One-repeat commands write at 0 and +100 ms.
# The app reports "Setup" after a Flat+preset chord is held for 6 s (its help
# text says 5 s). The save frame itself starts at once; storage is unverified.
SAVE_HOLD_MS: Final = 6000
# Integration guard, not a protocol value: bounds the manufacturer read.
MANUFACTURER_READ_TIMEOUT_S: Final = 5.0

# 25_42_02 and 36_33_04a frames: 08 02 + the table's eight payload bytes.
_LONG_PAYLOADS: Final[dict[str, str]] = {
    "head_up": "00 00 00 01 00 00 00 00",
    "head_down": "00 00 00 02 00 00 00 00",
    "feet_up": "00 00 00 04 00 00 00 00",
    "feet_down": "00 00 00 08 00 00 00 00",
    "lumbar_up": "00 00 00 10 00 00 00 00",
    "lumbar_down": "00 00 00 20 00 00 00 00",
    "stop": "00 00 00 00 00 00 00 00",
    "flat": "08 00 00 00 00 00 00 00",
    "anti_snore": "00 00 80 00 00 00 00 00",
    "lounge": "00 00 20 00 00 00 00 00",  # App label LEISURE (memoryLounge).
    "incline": "00 00 40 00 00 00 00 00",  # App label INCLINE (memoryTvpc).
    "zero_g": "00 00 10 00 00 00 00 00",
    "save_anti_snore": "08 00 80 00 00 00 00 00",
    "save_lounge": "08 00 20 00 00 00 00 00",
    "save_incline": "08 00 40 00 00 00 00 00",
    "save_zero_g": "08 00 10 00 00 00 00 00",
    "light": "00 02 00 00 00 00 00 00",
    "wave_1": "00 00 00 00 00 08 00 00",
    "wave_2": "00 00 00 00 00 10 00 00",
    "wave_3": "00 00 00 00 00 20 00 00",
    "massage_stop": "02 00 00 00 00 00 00 00",
    "massage_up": "00 00 0c 00 00 00 00 00",
    "massage_down": "01 80 00 00 00 00 00 00",
    "massage_on": "00 00 01 00 00 00 00 00",  # Reachable only through voice.
    "voice_stop": "00 00 00 00 00 00 00 00",  # Voice pre-STOP is the ordinary STOP.
}
# 35_22_01 frames: 5a 01 + four payload bytes + a5.
_STAR_PAYLOADS: Final[dict[str, str]] = {
    "head_up": "03 10 30 00",
    "head_down": "03 10 30 01",
    "feet_up": "03 10 30 02",
    "feet_down": "03 10 30 03",
    "lumbar_up": "03 10 30 06",
    "lumbar_down": "03 10 30 07",
    "stop": "03 10 30 0f",
    "flat": "03 10 30 10",
    "anti_snore": "03 10 30 16",
    "lounge": "03 10 30 12",
    "incline": "03 10 30 11",
    "zero_g": "03 10 30 13",
    "save_anti_snore": "03 10 30 93",
    "save_lounge": "03 10 30 91",
    "save_incline": "03 10 30 92",
    "save_zero_g": "03 10 30 90",
    "light": "03 10 30 71",
    "wave_1": "03 10 30 52",
    "wave_2": "03 10 30 53",
    "wave_3": "03 10 30 54",
    "massage_stop": "03 10 30 6f",
    "massage_up": "03 10 40 60",
    "massage_down": "03 10 40 61",
    "massage_on": "03 10 30 52",  # The voice massage-on entry equals wave 1.
    "voice_stop": "03 10 30 1f",  # stopVoice, the voice path's pre-STOP.
}
# The massage-page query is written raw, without the table prefix or suffix.
_CHECK_MASSAGE: Final[dict[Table, bytes]] = {
    "25_42_02": bytes.fromhex("0204"),
    "35_22_01": bytes.fromhex("5ab000a5"),
    "36_33_04a": bytes.fromhex("0204"),
}

# Controls the app streams while the finger is down, then releases with STOPs.
HELD_CONTROLS: Final = (
    "head_up",
    "head_down",
    "feet_up",
    "feet_down",
    "lumbar_up",
    "lumbar_down",
    "flat",
    "zero_g",
    "lounge",
    "incline",
    "anti_snore",
    "save_zero_g",
    "save_lounge",
    "save_incline",
    "save_anti_snore",
    "light",
    "wave_1",
    "wave_2",
    "wave_3",
    "massage_up",
    "massage_down",
)
_SAVE_LABELS: Final = {
    "save_zero_g": "Save Zero Gravity",
    "save_lounge": "Save Lounge",
    "save_incline": "Save Incline",
    "save_anti_snore": "Save Anti-Snore",
}
_WAVE_LABELS: Final = {"wave_1": "Wave 1", "wave_2": "Wave 2", "wave_3": "Wave 3"}


def control_frame(table: Table, action: str) -> bytes:
    """Return the exact frame the app writes for ``action`` on ``table``."""
    if table == "35_22_01":
        return b"\x5a\x01" + bytes.fromhex(_STAR_PAYLOADS[action]) + b"\xa5"
    return b"\x08\x02" + bytes.fromhex(_LONG_PAYLOADS[action])


def check_massage_frame(table: Table) -> bytes:
    """Return the raw massage-page query for ``table``."""
    return _CHECK_MASSAGE[table]


def resolve_branch(name: object) -> Branch | None:
    """Apply the app's lowercase prefix rule: ``okin`` first, then ``star``."""
    lowered = name.lower() if isinstance(name, str) else ""
    if lowered.startswith("okin"):
        return "okin"
    if lowered.startswith("star"):
        return "star"
    return None  # e.g. "smartbed": the app has no table for it.


def star_table(manufacturer: bytes | None) -> Table:
    """A ``star`` name uses 35_22_01 only for the exact four-byte ``STAR`` reply."""
    return "35_22_01" if manufacturer == STAR_MANUFACTURER else "25_42_02"


def _protocol_name(live: str | None, stored: object) -> str | None:
    """Use the live name unless it is address-like, then the stored raw name."""
    if not is_mac_like_name(live):
        return live
    return stored if isinstance(stored, str) and not is_mac_like_name(stored) else None


def _action(name: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        target = (
            controller._controller if isinstance(controller, SideBoundController) else controller
        )
        if not isinstance(target, AdjustableLumbarController):
            raise TypeError("This action requires the Adjustable bed (Lumbar) app profile")
        await target.execute_app_action(name)

    return invoke


class AdjustableLumbarController(BedController):
    """Faithful Adjustable bed (Lumbar) app controls for all three tables."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        protocol_variant: str | None = None,
        device_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        branch: Branch | None
        if protocol_variant == ADJUSTABLE_LUMBAR_VARIANT_OKIN:
            branch = "okin"
        elif protocol_variant == ADJUSTABLE_LUMBAR_VARIANT_STAR:
            branch = "star"
        else:
            data = getattr(getattr(coordinator, "entry", None), "data", None)
            stored = data.get(CONF_BLE_DEVICE_NAME) if isinstance(data, Mapping) else None
            branch = resolve_branch(_protocol_name(device_name, stored))
        self._branch = branch
        # Star beds start on 25_42_02; the manufacturer read may upgrade them.
        self._table: Table | None = (
            "36_33_04a" if branch == "okin" else "25_42_02" if branch == "star" else None
        )
        self._manufacturer: bytes | None = None
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None

    # ------------------------------------------------------------------ profile

    @property
    def table(self) -> Table | None:
        return self._table

    @property
    def control_characteristic_uuid(self) -> str:
        if self._write_char is not None:
            return self._write_char.uuid
        return OKIN_WRITE if self._branch == "okin" else NUS_WRITE

    @property
    def requires_notification_channel(self) -> bool:
        # The app only allows control after notifications are enabled.
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "adjustable_lumbar_branch": self._branch,
            "adjustable_lumbar_table": self._table,
            "adjustable_lumbar_manufacturer": (
                self._manufacturer.hex(" ") if self._manufacturer is not None else None
            ),
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Every release writes the global STOP, so the axes share one resource.
        specs = (
            MotorControlSpec(
                key=key,
                translation_key=key,
                open_fn=lambda ctrl, key=key: getattr(ctrl, f"move_{key}_up")(),
                close_fn=lambda ctrl, key=key: getattr(ctrl, f"move_{key}_down")(),
                stop_fn=lambda ctrl, key=key: getattr(ctrl, f"move_{key}_stop")(),
                max_angle=max_angle,
            )
            for key, max_angle in (("head", 68), ("feet", 45), ("lumbar", 68))
        )
        return tuple(replace(spec, scheduler_resource="*") for spec in specs)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, REFRESH_MS

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_incline(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        # The app shows its massage page for every table.
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return HELD_CONTROLS

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        labels = {
            **_SAVE_LABELS,
            **_WAVE_LABELS,
            "massage_on": "Massage On",
            "check_massage": "Check Massage",
        }
        return tuple(
            ControllerButtonSpec(
                f"adjustable_lumbar_{key}",
                label,
                _action(key),
                translation_key=f"adjustable_lumbar_{key}",
                icon="mdi:content-save" if key.startswith("save_") else "mdi:gesture-tap",
            )
            for key, label in labels.items()
        )

    # --------------------------------------------------------------- transport

    async def async_discover_capabilities(self) -> None:
        """Resolve the app's GATT roles and run its manufacturer read."""
        client = self.client
        if client is None:
            raise ConnectionError("Adjustable bed (Lumbar) is not connected")
        if self._branch is None:
            raise ValueError(
                "The Bluetooth name does not start with OKIN or Star, so the app has no "
                "command table for it; choose the OKIN or Star protocol variant"
            )
        service_uuid, write_uuid, notify_uuid = (
            (OKIN_SERVICE, OKIN_WRITE, OKIN_NOTIFY)
            if self._branch == "okin"
            else (NUS_SERVICE, NUS_WRITE, NUS_NOTIFY)
        )
        services = list(client.services or ())
        # The app takes the first matching service and characteristic.
        primary = next((s for s in services if s.uuid.lower() == service_uuid), None)
        chars = list(primary.characteristics) if primary is not None else []
        write = next((c for c in chars if c.uuid.lower() == write_uuid), None)
        notify = next((c for c in chars if c.uuid.lower() == notify_uuid), None)
        if write is None or notify is None:
            raise ValueError("Adjustable bed (Lumbar) requires its write and notify roles")
        required = "write" if self._branch == "okin" else "write-without-response"
        if required not in write.properties:
            raise ValueError(f"The Adjustable bed (Lumbar) write role lacks '{required}'")
        if not {"notify", "indicate"} & set(notify.properties):
            raise ValueError("The Adjustable bed (Lumbar) notify role cannot notify")
        info = next((s for s in services if s.uuid.lower() == DEVICE_INFO_SERVICE), None)
        if info is None:
            # The app fails before enabling notifications without this service.
            raise ValueError("Adjustable bed (Lumbar) requires the Device Information service")
        manufacturer = next(
            (c for c in info.characteristics if c.uuid.lower() == MANUFACTURER_CHAR), None
        )
        if manufacturer is None and self._branch == "okin":
            raise ValueError("Adjustable bed (Lumbar) requires the manufacturer characteristic")
        self._write_char, self._notify_char = write, notify
        self._manufacturer = None
        if manufacturer is not None:
            try:
                async with asyncio.timeout(MANUFACTURER_READ_TIMEOUT_S):
                    async with self._ble_lock:
                        self._manufacturer = bytes(await client.read_gatt_char(manufacturer))
            except (BleakError, OSError, TimeoutError) as error:
                # An absent reply keeps a star bed on 25_42_02; okin ignores it.
                _LOGGER.debug("Manufacturer read failed: %s", error)
        if self._branch == "star":
            self._table = star_table(self._manufacturer)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._write_char is None:
            raise ConnectionError("Adjustable bed (Lumbar) write role is not resolved")
        await self._write_gatt_with_retry(
            self._write_char.uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            # 36_33_04a writes with response; both Nordic UART tables without.
            response=self._table == "36_33_04a",
            wall_clock_pacing=True,
            characteristic=self._write_char,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        client = self.client
        if client is None or self._notify_char is None:
            return
        async with self._ble_lock:
            await client.start_notify(self._notify_char, self._handle_notification)

    async def stop_notify(self) -> None:
        self._notify_callback = None
        client = self.client
        if client is None or not client.is_connected or self._notify_char is None:
            return
        async with self._ble_lock:
            await client.stop_notify(self._notify_char)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        # Every shipped dispatch is dead, log-only or fans out to empty
        # callbacks, so replies are kept for diagnostics but never parsed.
        if self._notify_char is not None:
            self.forward_raw_notification(self._notify_char.uuid, bytes(data))

    # --------------------------------------------------------------- controls

    def _frame(self, action: str) -> bytes:
        if self._table is None:
            raise ConnectionError("Adjustable bed (Lumbar) command table is not resolved")
        return control_frame(self._table, action)

    async def _release(self) -> None:
        """Send STOP now and at +300 ms, both attempted and never cancelled."""

        async def release() -> None:
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for offset in RELEASE_STOP_OFFSETS_S:
                await asyncio.sleep(max(0, started + offset - loop.time()))
                try:
                    await self.write_command(self._frame("stop"), cancel_event=asyncio.Event())
                except Exception as error:
                    failure = failure or error
            if failure is not None:
                raise failure

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001 - re-raised below unless cancelled
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    async def _move(self, action: str) -> None:
        count, delay = self.motor_pulse_settings()
        try:
            await self.write_command(self._frame(action), repeat_count=count, repeat_delay_ms=delay)
        finally:
            await self._release()

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in HELD_CONTROLS:
            raise ValueError(f"'{control}' is not an Adjustable bed (Lumbar) held control")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Duration must be a positive integer, at most 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Stream a control every 100 ms for the hold, then release it."""
        self.validate_hold_control(control, duration_ms)
        deadline = asyncio.timeout(duration_ms / 1000)
        write_timeout = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            self._frame(control),
                            repeat_count=self.timed_move_repeat_count(duration_ms, REFRESH_MS),
                            repeat_delay_ms=REFRESH_MS,
                        )
                    except TimeoutError:
                        write_timeout = True
                        raise
            except TimeoutError:
                if write_timeout or not deadline.expired():
                    raise
        finally:
            await self._release()

    async def tap(self, control: str) -> None:
        """An app tap: the button-down write, then the release STOPs."""
        if control not in HELD_CONTROLS:
            raise ValueError(f"'{control}' is not an Adjustable bed (Lumbar) control")
        try:
            await self.write_command(self._frame(control))
        finally:
            await self._release()

    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_head_stop(self) -> None:
        await self._release()

    async def move_back_up(self) -> None:
        await self._move("head_up")

    async def move_back_down(self) -> None:
        await self._move("head_down")

    async def move_back_stop(self) -> None:
        await self._release()

    async def move_feet_up(self) -> None:
        await self._move("feet_up")

    async def move_feet_down(self) -> None:
        await self._move("feet_down")

    async def move_feet_stop(self) -> None:
        await self._release()

    async def move_legs_up(self) -> None:
        await self._move("feet_up")

    async def move_legs_down(self) -> None:
        await self._move("feet_down")

    async def move_legs_stop(self) -> None:
        await self._release()

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self._release()

    async def stop_all(self) -> None:
        await self._release()

    async def preset_flat(self) -> None:
        await self.tap("flat")

    async def preset_zero_g(self) -> None:
        await self.tap("zero_g")

    async def preset_lounge(self) -> None:
        await self.tap("lounge")

    async def preset_incline(self) -> None:
        await self.tap("incline")

    async def preset_anti_snore(self) -> None:
        await self.tap("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        # M1/M2 table constants have no reachable recall path in the app.
        raise NotImplementedError("The Adjustable bed (Lumbar) app has no numbered memories")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError(
            "Use the Save Zero Gravity/Lounge/Incline/Anti-Snore buttons instead"
        )

    async def lights_toggle(self) -> None:
        await self.tap("light")

    async def massage_intensity_up(self) -> None:
        await self.tap("massage_up")

    async def massage_intensity_down(self) -> None:
        await self.tap("massage_down")

    async def massage_off(self) -> None:
        """Tap massage stop: its +100 ms repeat is replaced by the release STOPs."""
        try:
            await self.write_command(self._frame("massage_stop"))
        finally:
            await self._release()

    async def massage_on(self) -> None:
        """The voice massage-on action: one pre-STOP, then two writes 100 ms apart."""
        await self.write_command(self._frame("voice_stop"))
        await self.write_command(
            self._frame("massage_on"), repeat_count=2, repeat_delay_ms=int(EXTRA_WRITE_S * 1000)
        )

    async def check_massage(self) -> None:
        """Write the massage page's raw query once; no reply is parsed."""
        if self._table is None:
            raise ConnectionError("Adjustable bed (Lumbar) command table is not resolved")
        await self.write_command(check_massage_frame(self._table))

    async def execute_app_action(self, action: str) -> None:
        if action in _SAVE_LABELS:
            await self.hold_control(action, SAVE_HOLD_MS)
        elif action in _WAVE_LABELS:
            await self.tap(action)
        elif action == "massage_on":
            await self.massage_on()
        elif action == "check_massage":
            await self.check_massage()
        else:
            raise ValueError(f"Unknown Adjustable bed (Lumbar) action '{action}'")
