"""FurniMove 2.2.0 BLE consumers and pinned, explicitly selected layouts.

Transport follows discovered characteristics, independently of the handset ID.
HA serializes the app's delayed work and cancels obsolete commands; it does not
reproduce the Android global-handler races or unbounded held-command refresh.
"""

from __future__ import annotations

import asyncio
import math
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from ..furnimove_profiles import FurniMoveAction, get_furnimove_profile
from .base import (
    POSITION_AXIS_COMMANDS,
    BedController,
    ControllerActionSpec,
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

WRITE = "62741525-52f9-8864-b1ab-3b3a8d65950b"
FEEDBACK = "62741625-52f9-8864-b1ab-3b3a8d65950b"
DOT_WRITE = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
DOT_FEEDBACK = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CSS_WRITE = "90311625-25fa-3346-12ef-3cfb7a2556ac"
CSS_FEEDBACK = "90311725-25fa-3346-12ef-3cfb7a2556ac"
GAP_NAME = "00002a00-0000-1000-8000-00805f9b34fb"
RF_NAME = "92111422-72ab-4564-62ef-2a881286a6b0"
INFO = {
    "model": "00002a24-0000-1000-8000-00805f9b34fb",
    "hardware": "00002a27-0000-1000-8000-00805f9b34fb",
    "software": "00002a28-0000-1000-8000-00805f9b34fb",
    "firmware": "00002a26-0000-1000-8000-00805f9b34fb",
}
_AXES = {"head": "M1", "back": "M2", "legs": "M3", "feet": "M4"}
_WIDGET = frozenset(
    {"TV", "Flat", "Memo1", "Memo2", "Memo3", "Memo4", "Snore", "ZeroGravity", "QuietSleep", "UBL"}
)
_DEAD_MASSAGE = frozenset({"MassagerHead", "MassagerFeet", "MassageAll"})
_MAIN_NAMES = frozenset({"Flat", "UBL", "ResetIn", "ResetOut"}) | frozenset(
    prefix + direction for prefix in _AXES.values() for direction in ("In", "Out")
)
_MASSAGE_NAMES = frozenset(
    {
        "MassagerHeadPlus",
        "MassagerHeadMinus",
        "MassagerFeetPlus",
        "MassagerFeetMinus",
        "MassagerStop",
        "Massager1",
        "Massager2",
        "Massager3",
        "MassagerWave",
    }
)


def _java_hex_digit(character: str) -> int:
    """Character.digit(char, 16), including decimal and fullwidth hex digits."""
    if "a" <= character <= "f":
        return ord(character) - ord("a") + 10
    if "A" <= character <= "F":
        return ord(character) - ord("A") + 10
    if "\uff21" <= character <= "\uff26":
        return ord(character) - ord("\uff21") + 10
    if "\uff41" <= character <= "\uff46":
        return ord(character) - ord("\uff41") + 10
    return unicodedata.decimal(character, -1)


def build_furnimove_command(keycode: str | None, *, old: bool = False, dot: bool = False) -> bytes:
    """Literal HexValueConverter behavior, including nullable factory keys."""
    frame = bytearray(
        b"\xe5\xfe\x16" + bytes(5)
        if old
        else (b"\x05\x02" + bytes(5) if dot else b"\x04\x02" + bytes(4))
    )
    offset = 3 if old else 2
    if keycode is not None:
        encoded = keycode.encode("utf-16-le", errors="surrogatepass")
        units = [
            chr(int.from_bytes(encoded[i : i + 2], "little")) for i in range(0, len(encoded), 2)
        ]
        for index in range(2, len(units), 2):
            frame[offset] = (
                (_java_hex_digit(units[index]) << 4) + _java_hex_digit(units[index + 1])
            ) & 255
            offset += 1
    if old:
        frame[7] = ~sum(frame) & 255
    elif dot:
        frame[6] = 0
    return bytes(frame)


def combine_furnimove_commands(frames: Sequence[bytes], *, old: bool = False) -> bytes | None:
    """BLEHelper's elementwise OR, followed by its composite gateway checksum."""
    if not frames:
        return None
    combined = bytearray(frames[0])
    for frame in frames[1:]:
        for index in range(len(combined)):
            combined[index] |= frame[index]
    if old and len(frames) >= 2 and len(combined) == 8:
        combined[7] = ~sum(combined[:7]) & 255
    return bytes(combined)


def validate_furnimove_name(name: str) -> None:
    """Validate the app's trimmed-copy UTF-16 limit without altering wire text."""
    trimmed = name.strip(" \t\n\r\f\v")
    if not trimmed or len(trimmed.encode("utf-16-le", errors="surrogatepass")) // 2 > 18:
        raise ValueError("FurniMove name must contain 1–18 UTF-16 units after trimming")


def _action_callback(row_index: int) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        await controller.async_execute_furnimove_action(row_index)

    return invoke


class FurniMoveController(BedController):
    """A complete app profile without cloud credentials or transport guesses."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, handset_id: str) -> None:
        super().__init__(coordinator)
        self.profile = get_furnimove_profile(handset_id)
        self._write_characteristic: BleakGATTCharacteristic | None = None
        self._feedback_characteristic: BleakGATTCharacteristic | None = None
        self._rf_name: BleakGATTCharacteristic | None = None
        self._gap_name: BleakGATTCharacteristic | None = None
        self._info: dict[str, BleakGATTCharacteristic] = {}
        self._notifying: list[BleakGATTCharacteristic] = []
        self._dot = False
        self._massage_busy_until = 0.0
        self._widget_pending = False
        self._widget_last: bytes | None = None
        self._widget_before_last: bytes | None = None
        self._cleanup_kind: str | None = None
        self._cleanup_dot = True
        self._cleanup_query = False
        self._cleanup_done = False
        self._state: dict[str, object] = {
            "furnimove_ubl": False,
            "furnimove_sync": False,
            "furnimove_child_lock": False,
            "furnimove_model": "HE150",
            "furnimove_hardware": "",
            "furnimove_software": "",
            "furnimove_firmware": "",
            "furnimove_control_mode": "press_and_hold",
            "furnimove_massage_running": False,
            "furnimove_massage_type": "not_selected",
            "furnimove_massage_intensity": 1,
            "furnimove_massage_program": 0,
            "furnimove_massage_timer_minutes": 15,
            "furnimove_function_result": "idle",
        }
        retained = getattr(coordinator, "controller_state", None)
        if isinstance(retained, Mapping):
            for key in ("furnimove_ubl", "furnimove_sync", "furnimove_child_lock"):
                value = retained.get(key)
                if type(value) is bool:
                    self._state[key] = value
            program = retained.get("furnimove_massage_program")
            if type(program) is int and 0 <= program <= 4:
                self._state["furnimove_massage_program"] = program

    @property
    def control_characteristic_uuid(self) -> str:
        if self._write_characteristic is None:
            raise ValueError("FurniMove has no discovered command characteristic")
        return self._write_characteristic.uuid.lower()

    @property
    def auto_stops_on_idle(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True  # State/info/query startup is independent of angle sensing.

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **self._state,
            "handset_id": self.profile.handset_id,
            "profile_source": self.profile.source,
            "object_sha256": self.profile.object_sha256,
            "button_sha256": self.profile.button_sha256,
            "old_protocol": self._rf_name is not None,
            "dot_protocol": self._dot,
            "actions": [
                {
                    "row_index": i,
                    "action": row.action,
                    "type": row.type,
                    "keycode": row.keycode,
                    "duration_ms": row.duration_ms,
                    "frequency_ms": row.frequency_ms,
                }
                for i, row in enumerate(self.profile.actions)
            ],
            "local_state_keys": [
                key for key in self._state if "massage" in key or "control_mode" in key
            ],
        }

    def _publish(self, key: str, value: object) -> None:
        self._state[key] = value
        self.forward_controller_state_update(key, value)

    def _clear_session(self) -> None:
        self._write_characteristic = self._feedback_characteristic = None
        self._rf_name = self._gap_name = None
        self._info.clear()
        self._dot = False
        for key, value in {
            "model": "HE150",
            "hardware": "",
            "software": "",
            "firmware": "",
        }.items():
            self._publish("furnimove_" + key, value)

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("FurniMove is not connected")
        self._clear_session()
        for service in client.services or ():
            for characteristic in service.characteristics:
                uuid = characteristic.uuid.lower()
                if uuid == WRITE:
                    self._write_characteristic = characteristic
                elif uuid == DOT_WRITE:
                    self._write_characteristic = characteristic
                    self._dot = True
                elif uuid in (FEEDBACK, DOT_FEEDBACK):
                    self._feedback_characteristic = characteristic
                elif uuid in (CSS_WRITE, CSS_FEEDBACK):
                    self._rf_name = None
                elif uuid == RF_NAME:
                    self._rf_name = characteristic
                elif uuid == GAP_NAME:
                    self._gap_name = characteristic
                for key, info_uuid in INFO.items():
                    if uuid == info_uuid:
                        self._info[key] = characteristic
        self._response_mode(self._write_characteristic)

    @staticmethod
    def _response_mode(characteristic: BleakGATTCharacteristic | None) -> bool:
        if characteristic is None:
            raise ValueError("FurniMove requires a discovered writable characteristic")
        # App inherits Android's default write type. HA chooses a supported mode.
        if "write" in characteristic.properties:
            return True
        if "write-without-response" in characteristic.properties:
            return False
        raise ValueError("FurniMove command characteristic is not writable")

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object]:
        return {"hex": command.hex()}

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._response_mode(self._write_characteristic),
            characteristic=self._write_characteristic,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._notifying:
            await self.stop_notify()
        await self.async_discover_capabilities()
        self._notify_callback = callback
        client = self.client
        if client is None:
            return
        supported = {
            WRITE,
            FEEDBACK,
            DOT_FEEDBACK,
            CSS_WRITE,
            CSS_FEEDBACK,
            RF_NAME,
            GAP_NAME,
            *INFO.values(),
        }
        for service in client.services or ():
            for characteristic in service.characteristics:
                if characteristic.uuid.lower() in supported and {"notify", "indicate"}.intersection(
                    characteristic.properties
                ):
                    async with self._ble_lock:
                        await client.start_notify(characteristic, self._handle_notification)
                    self._notifying.append(characteristic)
        # Device info reads are staggered by the app, with a DOT query at 400ms.
        for index, key in enumerate(INFO):
            if index:
                await asyncio.sleep(0.2)
            await self._read_info(key)
            if index == 2 and self._dot:
                await self.write_command(b"\x00\xb0")
        if not self._dot:
            await asyncio.sleep(0.1)
            await self._read_feedback()

    async def stop_notify(self) -> None:
        client = self.client
        try:
            if client is not None and client.is_connected:
                for characteristic in self._notifying:
                    async with self._ble_lock:
                        await client.stop_notify(characteristic)
        finally:
            self._notifying.clear()
            self._clear_session()

    async def _read_info(self, key: str) -> None:
        characteristic = self._info.get(key)
        client = self.client
        if characteristic is None or client is None or not client.is_connected:
            return
        async with self._ble_lock:
            data = await client.read_gatt_char(characteristic)
        self._publish("furnimove_" + key, bytes(data).decode("utf-8", errors="replace"))

    async def _read_feedback(self) -> None:
        client = self.client
        if self._feedback_characteristic is None or client is None or not client.is_connected:
            return
        async with self._ble_lock:
            data = await client.read_gatt_char(self._feedback_characteristic)
        self._parse_feedback(bytes(data))

    async def read_positions(self, motor_count: int = 2) -> None:
        # The app exposes state feedback, never position measurements.
        if self._dot:
            await self.write_command(b"\x00\xb0")
        else:
            await self._read_feedback()

    def _handle_notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        uuid = sender.uuid.lower()
        self.forward_raw_notification(uuid, bytes(data))
        for key, characteristic in self._info.items():
            if sender == characteristic:
                self._publish("furnimove_" + key, bytes(data).decode("utf-8", errors="replace"))
        if sender == self._feedback_characteristic:
            self._parse_feedback(bytes(data))

    def _parse_feedback(self, data: bytes) -> None:
        if len(data) < 10:
            return
        if self._dot and len(data) > 14:
            self._publish("furnimove_ubl", data[13] == 1)
        for key, mask in (("ubl", 0x00020000), ("sync", 0x10000000), ("child_lock", 0x04000000)):
            state_key = "furnimove_" + key
            if self._state["furnimove_model"] == "CU170":
                if key == "sync" and data[9] == 4:
                    continue
                first, second, bit = (
                    (4, 8, 2) if key == "ubl" else (5, 9, 16 if key == "sync" else 4)
                )
                self._publish(state_key, bool(data[first] & data[second] & bit))
                continue
            value: bool | None = None
            if self._rf_name is None and data[0] in (8, 9) and data[1] == 11:
                value = bool(
                    int.from_bytes(data[2:6], "big") & int.from_bytes(data[6:10], "big") & mask
                )
            elif self._rf_name is not None and data[1] == 254 and data[0] & 15 in (5, 6):
                start = 3 if data[0] & 15 == 5 else 4
                if int.from_bytes(data[start : start + 4], "big") & mask and data[2] in (6, 7):
                    value = data[2] == 6
            if value is not None and value != self._state[state_key]:
                self._publish(state_key, value)

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                key, "under_bed_lights" if key == "furnimove_ubl" else key, key, icon
            )
            for key, icon in (
                ("furnimove_ubl", "mdi:led-strip-variant"),
                ("furnimove_sync", "mdi:sync"),
                ("furnimove_child_lock", "mdi:lock"),
                ("furnimove_massage_running", "mdi:vibrate"),
            )
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                "furnimove_" + key,
                "furnimove_" + key,
                "furnimove_" + key,
                "mdi:information-outline",
            )
            for key in (
                *INFO,
                "control_mode",
                "massage_type",
                "massage_intensity",
                "massage_program",
                "massage_timer_minutes",
                "function_result",
            )
        )

    def _frame(self, row: FurniMoveAction | None, *, dot: bool = True) -> bytes:
        return build_furnimove_command(
            row.keycode if row else None, old=self._rf_name is not None, dot=self._dot and dot
        )

    def _require(self, name: str) -> FurniMoveAction:
        row = self.profile.first(name)
        if row is None:
            raise ValueError(f"The selected handset has no {name} action")
        return row

    async def _pause(self, milliseconds: int, event: asyncio.Event | None = None) -> bool:
        cancel = event or self._coordinator.cancel_command
        if cancel.is_set():
            return False
        if milliseconds > 0:
            try:
                await asyncio.wait_for(cancel.wait(), milliseconds / 1000)
                return False
            except TimeoutError:
                pass
        return not cancel.is_set()

    async def _release(
        self, consumer: str = "main", *, dot: bool = True, query: bool = False
    ) -> None:
        fresh = asyncio.Event()
        started = asyncio.get_running_loop().time()
        row = self.profile.first("DisobeyStandbyTime")
        if row is not None:
            await self.write_command(self._frame(row, dot=dot), cancel_event=fresh)
        # End refresh even with no release row. Delay work stays inside HA's lock.
        if consumer in ("main", "favorites", "function"):
            elapsed = int((asyncio.get_running_loop().time() - started) * 1000)
            await self._pause(max(0, 100 - elapsed), fresh)
        if consumer == "main" and (not self._dot or query):
            elapsed = max(100, int((asyncio.get_running_loop().time() - started) * 1000))
            await self._pause(max(0, 200 - elapsed), fresh)
            if self._dot:
                await self.write_command(b"\x00\xb0", cancel_event=fresh)
            elif row is not None:
                await self.write_command(self._frame(row), cancel_event=fresh)

    def _begin_cleanup(self, kind: str, *, dot: bool = True, query: bool = False) -> None:
        self._cleanup_kind = kind
        self._cleanup_dot = dot
        self._cleanup_query = query
        self._cleanup_done = False

    async def _finish_cleanup(self) -> None:
        """Complete the current consumer's cleanup, retaining failed work for STOP."""
        if self._cleanup_kind == "massage":
            await self.write_command(
                self._frame(self.profile.first("DisobeyStandbyTime"), dot=False),
                cancel_event=asyncio.Event(),
            )
        elif self._cleanup_kind == "massage_stop":
            row = self.profile.first("MassagerStop")
            if row is not None:
                await self.write_command(self._frame(row, dot=False), cancel_event=asyncio.Event())
        elif self._cleanup_kind not in (None, "once"):
            await self._release(
                self._cleanup_kind, dot=self._cleanup_dot, query=self._cleanup_query
            )
        self._cleanup_done = True

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @staticmethod
    def _validate_duration(duration_ms: int | None) -> None:
        if duration_ms is not None and (
            isinstance(duration_ms, bool) or not 1 <= duration_ms <= 120000
        ):
            raise ValueError("FurniMove hold duration must be 1–120000ms")

    async def _hold(
        self,
        rows: Sequence[FurniMoveAction],
        *,
        duration_ms: int | None = None,
        consumer: str = "main",
    ) -> None:
        self._validate_duration(duration_ms)
        frame = combine_furnimove_commands(
            [self._frame(row) for row in rows], old=self._rf_name is not None
        )
        if frame is None:
            return
        self._begin_cleanup(consumer, query=any(row.action == "UBL" for row in rows))
        count = (
            max(1, math.ceil(duration_ms / 100))
            if duration_ms
            else self._coordinator.motor_pulse_count
        )
        try:
            for index in range(count):
                if self._coordinator.cancel_command.is_set():
                    break
                await self.write_command(frame)
                wait = min(100, duration_ms - index * 100) if duration_ms else 100
                if index < count - 1 or duration_ms is not None:
                    if not await self._pause(wait):
                        break
        finally:
            await self._finish_cleanup()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(axis, axis, *POSITION_AXIS_COMMANDS[axis], scheduler_resource="*")
            for axis, prefix in _AXES.items()
            if self.profile.first(prefix + "Out") is not None
            and self.profile.first(prefix + "In") is not None
        )

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.motor_control_specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"stair"})

    @property
    def supports_simultaneous_movement(self) -> bool:
        return len(self.motor_control_specs) >= 2

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.motor_control_specs)

    def validate_furnimove_simultaneous(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        self._validate_duration(duration_ms)
        if (
            first_axis == second_axis
            or first_axis not in self.simultaneous_movement_axes
            or second_axis not in self.simultaneous_movement_axes
        ):
            raise ValueError("Select two different axes present in the handset table")
        self._require(_AXES[first_axis] + ("Out" if first_up else "In"))
        self._require(_AXES[second_axis] + ("Out" if second_up else "In"))

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        self.validate_furnimove_simultaneous(
            first_axis, first_up, second_axis, second_up, duration_ms
        )
        await self._hold(
            [
                self._require(_AXES[first_axis] + ("Out" if first_up else "In")),
                self._require(_AXES[second_axis] + ("Out" if second_up else "In")),
            ],
            duration_ms=duration_ms,
        )

    async def _axis(self, axis: str, up: bool) -> None:
        await self._hold([self._require(_AXES[axis] + ("Out" if up else "In"))])

    async def move_head_up(self) -> None:
        await self._axis("head", True)

    async def move_head_down(self) -> None:
        await self._axis("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._axis("back", True)

    async def move_back_down(self) -> None:
        await self._axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._axis("legs", True)

    async def move_legs_down(self) -> None:
        await self._axis("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._axis("feet", True)

    async def move_feet_down(self) -> None:
        await self._axis("feet", False)

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        if not self._cleanup_done:
            if self._cleanup_kind is None:
                await self._release()
            else:
                await self._finish_cleanup()
        # STOP follows the cancelled operation's owned cleanup. Do not append a
        # main-format release after a different consumer has already released.
        self._cleanup_kind = None
        self._cleanup_done = False

    async def _send_stop(self) -> None:
        await self.stop_all()

    @property
    def supports_preset_flat(self) -> bool:
        return self.profile.first("Flat") is not None

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.profile.first("ZeroGravity") is not None

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.profile.first("Snore") is not None

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile.first("TV") is not None

    async def preset_flat(self) -> None:
        await self._hold([self._require("Flat")])

    async def preset_zero_g(self) -> None:
        await self._hold([self._require("ZeroGravity")], consumer="favorites")

    async def preset_anti_snore(self) -> None:
        await self._hold([self._require("Snore")], consumer="favorites")

    async def preset_tv(self) -> None:
        await self._hold([self._require("TV")], consumer="favorites")

    @property
    def memory_slot_count(self) -> int:
        return len(self.profile.by_type("memory"))

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return tuple(row.action for row in self.profile.by_type("memory"))

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets and self.profile.first("MemoSave") is not None

    def _memory(self, slot: int) -> FurniMoveAction:
        if isinstance(slot, bool) or not 1 <= slot <= self.memory_slot_count:
            raise ValueError("Memory slot is absent from the selected handset")
        return self.profile.by_type("memory")[slot - 1]

    async def preset_memory(self, memory_num: int) -> None:
        await self._hold([self._memory(memory_num)], consumer="favorites")

    async def _timer(self, row: FurniMoveAction, *, dot: bool) -> bool:
        # Android CountDownTimer skips a tick when less than one interval remains.
        if row.duration_ms <= 0:
            return not self._coordinator.cancel_command.is_set()
        if row.frequency_ms <= 0:
            raise ValueError("The captured timer interval cannot be executed safely")
        started = asyncio.get_running_loop().time()
        elapsed = 0
        while row.duration_ms - elapsed >= row.frequency_ms:
            if self._coordinator.cancel_command.is_set():
                return False
            elapsed = max(elapsed, int((asyncio.get_running_loop().time() - started) * 1000))
            if row.duration_ms - elapsed < row.frequency_ms:
                break
            tick_started = asyncio.get_running_loop().time()
            await self.write_command(self._frame(row, dot=dot))
            write_elapsed = int((asyncio.get_running_loop().time() - tick_started) * 1000)
            if not await self._pause(max(0, row.frequency_ms - write_elapsed)):
                return False
            elapsed += row.frequency_ms
        elapsed = max(elapsed, int((asyncio.get_running_loop().time() - started) * 1000))
        return await self._pause(max(0, row.duration_ms - elapsed))

    async def program_memory(self, memory_num: int) -> None:
        slot = self._memory(memory_num)
        save = self._require("MemoSave")
        if save.duration_ms > 0 and save.frequency_ms <= 0:
            raise ValueError("The captured save timer has no valid interval")
        self._begin_cleanup("once", dot=False)
        # All writes are once-mode; ending this cancellable sequence is cleanup.
        # No background timer remains, and cancellation never writes the slot.
        try:
            await self.write_command(self._frame(save, dot=False))
            if not await self._timer(save, dot=False):
                return
            if await self._pause(2 * save.frequency_ms):
                await self.write_command(self._frame(slot, dot=False))
                await self._pause(save.frequency_ms)
        finally:
            await self._finish_cleanup()

    @property
    def supports_sync(self) -> bool:
        return self.profile.first("Sync") is not None

    @property
    def supports_child_lock(self) -> bool:
        return self.profile.first("ChildLock") is not None

    @property
    def supports_control_mode_configuration(self) -> bool:
        return self.profile.first("SwitchToPH") is not None

    async def _function(self, row: FurniMoveAction, *, mode: bool = False) -> None:
        finished = False
        self._begin_cleanup(
            "function" if mode or self.profile.first("Sync") is not None else "once", dot=not mode
        )
        original_sync = self._state["furnimove_sync"]
        try:
            if await self._timer(row, dot=not mode):
                finished = await self._pause(300)
        finally:
            # Missing Sync skips the bed-functions finish callback, even for lock.
            await self._finish_cleanup()
        if mode and finished:
            self._publish(
                "furnimove_control_mode",
                "press_and_hold" if row.action == "SwitchToPH" else "press_and_release",
            )
        elif finished:
            sync = self.profile.first("Sync")
            if sync is not None:
                unchanged = (
                    self._frame(row) == self._frame(sync, dot=False)
                    and self._state["furnimove_sync"] == original_sync
                )
                self._publish(
                    "furnimove_function_result", "feedback_unchanged" if unchanged else "completed"
                )

    async def sync_positions(self) -> None:
        await self._function(self._require("Sync"))

    async def child_lock_toggle(self) -> None:
        await self._function(self._require("ChildLock"))

    async def set_control_mode_press_and_hold(self) -> None:
        await self._function(self._require("SwitchToPH"), mode=True)

    async def set_control_mode_press_and_release(self) -> None:
        if not self.supports_control_mode_configuration:
            raise ValueError("SwitchToPH is required to expose the mode section")
        await self._function(self._require("SwitchToPR"), mode=True)

    @property
    def supports_lights(self) -> bool:
        return self.profile.first("UBL") is not None

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    async def lights_toggle(self) -> None:
        await self._hold([self._require("UBL")])

    async def lights_on(self) -> None:
        if not self._state["furnimove_ubl"]:
            await self.lights_toggle()

    async def lights_off(self) -> None:
        if self._state["furnimove_ubl"]:
            await self.lights_toggle()

    def get_light_state(self) -> dict[str, object]:
        return {"is_on": self._state["furnimove_ubl"]}

    @property
    def supports_massage(self) -> bool:
        return bool(self.profile.by_type("massage-function"))

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self.supports_massage

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["head", "foot", "all", "wave"] if self.supports_massage else []

    @property
    def massage_intensity_max(self) -> int:
        return self.profile.massage_max_intensity

    @property
    def supports_massage_timer(self) -> bool:
        # Generic HA timer entities promise a hardware timer. App choice is local.
        return False

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 15, 20, 30]

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage or minutes not in self.massage_timer_options:
            raise ValueError("Unsupported local massage countdown")
        # App display preference only. No hardware timer or expiry STOP exists.
        self._publish("furnimove_massage_timer_minutes", minutes)

    def _massage_frames(self, names: Sequence[str]) -> list[bytes]:
        return [self._frame(self.profile.first(name), dot=False) for name in names]

    def build_massage_queue(
        self, zone: str, intensity: int, *, direction: int | None = None
    ) -> list[bytes]:
        if zone == "all":
            zone = "both"
        if zone not in ("head", "foot", "both", "wave"):
            raise ValueError("Unknown massage zone")
        names: list[str] = []
        if zone == "wave":
            repeats = 1 if direction is not None else intensity if 1 <= intensity <= 4 else 0
            names = ["Massager3", "DisobeyStandbyTime"] * repeats
        else:
            for prefix in (
                ["Head", "Feet"] if zone == "both" else ["Head" if zone == "head" else "Feet"]
            ):
                if direction is not None:
                    suffix, repeats = ("Plus" if direction == 1 else "Minus"), 1
                else:
                    suffix, repeats = (
                        ("Plus", 1)
                        if intensity == 1
                        else ("Minus", 5 - intensity)
                        if 2 <= intensity <= 4
                        else ("Minus", 0)
                    )
                names.extend(["Massager" + prefix + suffix, "DisobeyStandbyTime"] * repeats)
        return self._massage_frames(names)

    async def _massage_queue(self, frames: Sequence[bytes]) -> None:
        self._begin_cleanup("massage", dot=False)
        self._massage_busy_until = asyncio.get_running_loop().time() + 0.15
        completed = False
        try:
            for index, frame in enumerate(frames):
                if self._coordinator.cancel_command.is_set():
                    break
                await self.write_command(frame)
                if index < len(frames) - 1 and not await self._pause(150):
                    break
            else:
                completed = True
        finally:
            if not completed and frames:
                # Do not strand a factory press if STOP preempts its queued release.
                await self._finish_cleanup()
            else:
                self._cleanup_done = True

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone == "all":
            zone = "both"
        if (
            not self.supports_massage
            or isinstance(level, bool)
            or not 0 <= level <= self.massage_intensity_max
        ):
            raise ValueError("Unsupported massage intensity")
        if level == 0:
            await self.massage_off()
            return
        frames = self.build_massage_queue(zone, level)
        if self._massage_busy_until > asyncio.get_running_loop().time():
            if not await self._pause(150):
                return
        await self._massage_queue(frames)
        if self._coordinator.cancel_command.is_set():
            return
        self._publish("furnimove_massage_type", zone)
        self._publish("furnimove_massage_intensity", level)
        self._publish("furnimove_massage_running", True)

    async def massage_off(self) -> None:
        self._begin_cleanup("massage_stop", dot=False)
        row = self.profile.first("MassagerStop")
        busy = self._massage_busy_until > asyncio.get_running_loop().time()
        over_max = int(str(self._state["furnimove_massage_intensity"])) > self.massage_intensity_max
        self._massage_busy_until = asyncio.get_running_loop().time() + 0.15
        if row is not None:
            fresh = asyncio.Event()
            if over_max:
                await self._pause(250, fresh)
                await self.write_command(self._frame(row, dot=False), cancel_event=fresh)
            else:
                await self.write_command(self._frame(row, dot=False), cancel_event=fresh)
                if busy:
                    await self._pause(150, fresh)
                await self.write_command(self._frame(row, dot=False), cancel_event=fresh)
        self._cleanup_done = True
        self._publish("furnimove_massage_running", False)
        self._publish("furnimove_massage_intensity", 0)

    async def massage_toggle(self) -> None:
        if self._state["furnimove_massage_running"]:
            await self.massage_off()
        else:
            await self.set_massage_intensity("both", 1)

    async def massage_head_toggle(self) -> None:
        if (
            self._state["furnimove_massage_running"]
            and self._state["furnimove_massage_type"] == "head"
        ):
            await self.massage_off()
        else:
            await self.set_massage_intensity("head", 1)

    async def massage_foot_toggle(self) -> None:
        if (
            self._state["furnimove_massage_running"]
            and self._state["furnimove_massage_type"] == "foot"
        ):
            await self.massage_off()
        else:
            await self.set_massage_intensity("foot", 1)

    async def _massage_step(self, zone: str, direction: int) -> None:
        if not self.supports_massage:
            raise ValueError("The handset does not expose massage")
        if not self._state["furnimove_massage_running"]:
            return
        level = int(str(self._state["furnimove_massage_intensity"]))
        if direction == 1 and level >= self.massage_intensity_max or direction != 1 and level <= 1:
            return
        self._publish("furnimove_massage_intensity", level + (1 if direction == 1 else -1))
        if zone not in ("head", "foot", "both", "wave"):
            return  # Program-only modes hide intensity arrows in the app.
        if await self._pause(250):
            await self._massage_queue(self.build_massage_queue(zone, 1, direction=direction))

    async def massage_intensity_up(self) -> None:
        await self._massage_step(str(self._state["furnimove_massage_type"]), 1)

    async def massage_intensity_down(self) -> None:
        await self._massage_step(str(self._state["furnimove_massage_type"]), -1)

    async def massage_head_up(self) -> None:
        await self._massage_step("head", 1)

    async def massage_head_down(self) -> None:
        await self._massage_step("head", -1)

    async def massage_foot_up(self) -> None:
        await self._massage_step("foot", 1)

    async def massage_foot_down(self) -> None:
        await self._massage_step("foot", -1)

    async def set_furnimove_massage_program(self, program: int) -> None:
        if not self.supports_massage or isinstance(program, bool) or program not in (1, 2, 3, 4):
            raise ValueError("FurniMove massage program must be 1–4")
        over_max = False
        if program == self._state["furnimove_massage_program"]:
            level = int(str(self._state["furnimove_massage_intensity"])) + 1
            self._publish("furnimove_massage_intensity", level)
            over_max = level > self.massage_intensity_max
            if over_max:
                await self.massage_off()
        else:
            await self.massage_off()
            self._publish("furnimove_massage_intensity", 1)
        if await self._pause(0 if over_max else 250):
            await self._massage_queue(
                self._massage_frames(
                    [f"Massager{program}" if program < 4 else "MassagerWave", "DisobeyStandbyTime"]
                )
            )
            self._publish("furnimove_massage_program", program)
            self._publish(
                "furnimove_massage_type", "wave" if program == 4 else f"program_{program}"
            )
            if not over_max:
                self._publish("furnimove_massage_running", True)

    async def massage_mode_step(self) -> None:
        program = int(str(self._state["furnimove_massage_program"]))
        await self.set_furnimove_massage_program(program % 4 + 1)

    @property
    def supports_massage_intensity_preset_control(self) -> bool:
        return self.supports_massage

    async def set_massage_intensity_preset(self, level: int) -> None:
        zone = str(self._state["furnimove_massage_type"])
        await self.set_massage_intensity(
            zone if zone in ("head", "foot", "both", "wave") else "both", level
        )

    def get_massage_state(self) -> dict[str, object]:
        zone = self._state["furnimove_massage_type"]
        level = (
            self._state["furnimove_massage_intensity"]
            if self._state["furnimove_massage_running"]
            else 0
        )
        return {
            "is_on": self._state["furnimove_massage_running"],
            "intensity": self._state["furnimove_massage_intensity"],
            "zone": self._state["furnimove_massage_type"],
            "mode": self._state["furnimove_massage_program"],
            "timer": self._state["furnimove_massage_timer_minutes"],
            "source": "local_app_state",
            "head_intensity": level if zone in ("head", "both") else 0,
            "foot_intensity": level if zone in ("foot", "both") else 0,
            "wave_intensity": level if zone == "wave" else 0,
        }

    @property
    def furnimove_local_state(self) -> dict[str, int | str | bool]:
        """Persist local app state; inactive snapshots discard the active record."""
        state: dict[str, int | str | bool] = {
            "duration_minutes": int(str(self._state["furnimove_massage_timer_minutes"]))
        }
        if self._state["furnimove_massage_running"]:
            state.update(
                running=True,
                zone=str(self._state["furnimove_massage_type"]),
                intensity=int(str(self._state["furnimove_massage_intensity"])),
            )
        return state

    def restore_furnimove_local_state(self, state: Mapping[str, int | str | bool]) -> None:
        """Restore validated local selection without asserting hardware state."""
        duration = state.get("duration_minutes", 15)
        running = state.get("running", False)
        zone = state.get("zone", "not_selected")
        intensity = state.get("intensity", 1)
        if type(duration) is not int or duration not in self.massage_timer_options:
            raise ValueError("Invalid saved FurniMove countdown preference")
        if type(running) is not bool:
            raise ValueError("Invalid saved FurniMove running selection")
        if running and (
            not self.supports_massage
            or zone not in ("head", "foot", "both", "wave", "program_1", "program_2", "program_3")
            or type(intensity) is not int
            or not 1 <= intensity <= self.massage_intensity_max
        ):
            raise ValueError("Invalid saved FurniMove massage selection")
        self._publish("furnimove_massage_timer_minutes", duration)
        self._publish("furnimove_massage_type", zone if running else "not_selected")
        self._publish("furnimove_massage_intensity", intensity if running else 1)
        self._publish("furnimove_massage_running", running)

    def _reachable(self, row: FurniMoveAction) -> bool:
        if row.action in _DEAD_MASSAGE or row.action in ("MemoSave", "DisobeyStandbyTime"):
            return False
        return (
            row.type in ("actuator", "actuator-init", "memory", "memory-preset")
            or row.action in _MAIN_NAMES | _MASSAGE_NAMES | {"Sync", "ChildLock", "SwitchToPH"}
            or (row.action == "SwitchToPR" and self.supports_control_mode_configuration)
        )

    @property
    def furnimove_action_specs(self) -> tuple[ControllerActionSpec, ...]:
        return tuple(
            ControllerActionSpec(i, row.action, row.type, row.duration_ms, row.frequency_ms)
            for i, row in enumerate(self.profile.actions)
            if self._reachable(row)
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Indexed keys preserve arbitrary names and duplicate memory labels.
        return tuple(
            ControllerButtonSpec(
                f"furnimove_action_{spec.row_index}", spec.name, _action_callback(spec.row_index)
            )
            for spec in self.furnimove_action_specs
            if self.profile.actions[spec.row_index].type != "actuator"
        )

    def validate_furnimove_action(
        self, row_index: int, *, duration_ms: int | None = None, consumer: str = "app"
    ) -> None:
        if isinstance(row_index, bool) or not 0 <= row_index < len(self.profile.actions):
            raise ValueError("Unknown FurniMove action row")
        row = self.profile.actions[row_index]
        self._validate_duration(duration_ms)
        if consumer not in ("app", "widget"):
            raise ValueError("Unknown FurniMove consumer")
        if consumer == "widget":
            if row.action not in _WIDGET or duration_ms is not None:
                raise ValueError("Widget action uses the exact whitelist and fixed duration")
        elif not self._reachable(row):
            raise ValueError("This row has no direct reachable app action")
        elif (
            duration_ms is not None
            and row.type not in ("actuator", "actuator-init", "memory", "memory-preset")
            and row.action not in _MAIN_NAMES
        ):
            raise ValueError("This consumer uses its captured duration")
        if (
            row.action in {"Sync", "ChildLock", "SwitchToPH", "SwitchToPR"}
            and row.duration_ms > 0
            and row.frequency_ms <= 0
        ):
            raise ValueError("The captured timer cannot be safely executed")

    async def async_execute_furnimove_action(
        self, row_index: int, *, duration_ms: int | None = None, consumer: str = "app"
    ) -> None:
        self.validate_furnimove_action(row_index, duration_ms=duration_ms, consumer=consumer)
        row = self.profile.actions[row_index]
        if consumer == "widget":
            await self._widget(row)
        elif row.type in ("memory", "memory-preset"):
            await self._hold([row], duration_ms=duration_ms, consumer="favorites")
        elif row.action in ("Sync", "ChildLock"):
            await self._function(self._require(row.action))
        elif row.action in ("SwitchToPH", "SwitchToPR"):
            await self._function(self._require(row.action), mode=True)
        elif row.action == "MassagerStop":
            await self.massage_off()
        elif row.action in ("Massager1", "Massager2", "Massager3", "MassagerWave"):
            await self.set_furnimove_massage_program(
                4 if row.action == "MassagerWave" else int(row.action[-1])
            )
        elif row.action in _MASSAGE_NAMES:
            await self._massage_step(
                "head" if "Head" in row.action else "foot", 1 if row.action.endswith("Plus") else -1
            )
        else:
            # Main named lookup takes the first match, independently of row type.
            selected = self._require(row.action) if row.action in _MAIN_NAMES else row
            await self._hold([selected], duration_ms=duration_ms)

    async def _widget(self, row: FurniMoveAction) -> None:
        selected = self._require(row.action)
        frame = self._frame(selected, dot=False)
        self._begin_cleanup("widget", dot=False)
        completed = False
        try:
            if self._widget_pending:
                if not await self._pause(100):
                    return
                await self._release("widget", dot=False)
            self._widget_pending = row.action != "UBL"
            if (
                row.action != "UBL"
                and frame == self._widget_last
                and frame != self._widget_before_last
            ):
                self._widget_before_last = frame
                await self._pause(100, asyncio.Event())
                return
            self._widget_before_last = None
            self._widget_last = frame
            count = 1 if row.action == "UBL" else 100
            for _index in range(count):
                if self._coordinator.cancel_command.is_set():
                    break
                await self.write_command(frame)
                if not await self._pause(100 if row.action == "UBL" else 200):
                    break
            else:
                completed = True
        finally:
            await self._finish_cleanup()
            if completed:
                self._widget_before_last = frame

    @property
    def supports_device_rename(self) -> bool:
        return self._rf_name is not None or self._gap_name is not None

    def validate_furnimove_rename(self, name: str) -> None:
        validate_furnimove_name(name)

    async def rename_device(self, name: str) -> None:
        self.validate_furnimove_rename(name)
        characteristic = self._rf_name or self._gap_name
        if characteristic is None:
            raise ValueError("No FurniMove rename characteristic was discovered")
        await self._write_gatt_with_retry(
            characteristic.uuid,
            name.encode("utf-8"),
            response=self._response_mode(characteristic),
            characteristic=characteristic,
        )
