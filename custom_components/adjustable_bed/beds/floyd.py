"""Floyd Home 1.0.7, product 139. See the row117 disposition ledger.

Only transport primitives proven equivalent to the accepted report are reused
from Kaidi. Commands and capabilities come from this app's reachable paths.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic

from ..const import (
    CONF_KAIDI_ROOM_ID,
    KAIDI_NOTIFY_CHAR_UUID,
    KAIDI_VARIANT_FLOYD,
    KAIDI_WRITE_CHAR_UUID,
)
from ..kaidi_protocol import extract_kaidi_advertisement, is_floyd_advertisement
from .base import ControllerStateBinarySensorSpec, MotorControlSpec
from .kaidi import KaidiCommandProfile, KaidiController, KaidiProductFamily

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

FLOYD_VARIANT = KAIDI_VARIANT_FLOYD
# E7 normal UI, E16 independently reachable exported Android receiver.
FLOYD_PRESETS = {
    "first": {"zero_g": 0x62, "flat": 0x1C, "anti_snore": 0x65,
              "memory_1": 0x29, "memory_2": 0x2A, "memory_3": 0x2B},
    "both": {"zero_g": 0x64, "flat": 0x1E, "anti_snore": 0x67,
             "memory_1": 0x39, "memory_2": 0x3A, "memory_3": 0x3B},
    "second": {"zero_g": 0x63, "flat": 0x1D, "anti_snore": 0x66,
               "memory_1": 0x31, "memory_2": 0x32, "memory_3": 0x33},
}
FLOYD_HOLDS = {
    "head_up": (1, 3), "head_down": (2, 3),
    "feet_up": (4, 6), "feet_down": (5, 6),
    "head_feet_up": (7, 9), "head_feet_down": (8, 9),
}
_FLOYD_PROFILE = KaidiCommandProfile(
    variant=FLOYD_VARIANT,
    head_up=1, head_down=2, head_stop=3,
    foot_up=4, foot_down=5, foot_stop=6,
    stop_all=9, preset_flat=0x1C, preset_zero_g=0x62, preset_anti_snore=0x65,
    memory_save={1: 0x25, 2: 0x26, 3: 0x27},
    memory_recall={1: 0x29, 2: 0x2A, 3: 0x2B},
    light_on=0x5C, light_off=0x5D,
)


class FloydController(KaidiController):
    """A bounded start/hold/release controller for one physical Floyd node."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *,
        device_name: str | None = None,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> None:
        super().__init__(coordinator, device_name=device_name, manufacturer_data=manufacturer_data)
        if self._product_id not in (None, 139):
            raise ValueError("Floyd Home requires advertised product 139")
        saved_room = coordinator.entry.data.get(CONF_KAIDI_ROOM_ID)
        if not self._room_id and isinstance(saved_room, int) and saved_room:
            # Assignment ACK precedes advertisement refresh on reconnect.
            self._room_id = saved_room
        self._variant = FLOYD_VARIANT
        self._configured_command_profile = _FLOYD_PROFILE
        self._own_vaddr = 0
        # Stored zero is offline. Only a matching live ping may authorize zero.
        self._target_vaddr = None
        parameter = getattr(coordinator, "controller_state", {}).get("floyd_retained_parameter")
        self._parameter = parameter if isinstance(parameter, int) and 0 <= parameter <= 255 else 0
        self._battery_mode: bool | None = None
        self._assignment_event = asyncio.Event()
        self._assignment_status: int | None = None
        self._device_count: int | None = None
        self._next_write_at = 0.0

    @property
    def _product_family(self) -> KaidiProductFamily:
        return KaidiProductFamily(bed_ui=2, has_lights=True)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            MotorControlSpec("back", "back", lambda c: c.move_back_up(),
                             lambda c: c.move_back_down(), lambda c: c.move_back_stop()),
            MotorControlSpec("legs", "legs", lambda c: c.move_legs_up(),
                             lambda c: c.move_legs_down(), lambda c: c.move_legs_stop()),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **super().protocol_diagnostics,
            "app_profile": "floyd_1.0.7_product_139",
            "retained_parameter": self._parameter,
            "battery_mode": self._battery_mode,
            "session_ready": self._session_ready,
            "device_count": self._device_count,
            "authentication_status": self._join_status,
        }

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(FLOYD_HOLDS)

    @property
    def supports_floyd_actions(self) -> bool:
        return True

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (ControllerStateBinarySensorSpec(
            key="floyd_battery_mode", translation_key="floyd_battery_mode",
            state_key="floyd_battery_mode", icon="mdi:battery",
        ),)

    def on_disconnect(self) -> None:
        self._session_ready = False
        self._notify_started = False
        self._target_vaddr = None
        self._own_vaddr = 0
        self._join_event.clear()
        self._target_vaddr_event.clear()
        self._battery_mode = None
        self.forward_controller_state_update("floyd_battery_mode", None)

    def _handle_notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        payload = bytes(data)
        self.forward_raw_notification(KAIDI_NOTIFY_CHAR_UUID, payload)
        if len(payload) < 3:
            return
        if payload[:2] == b"\x02\x03":
            self._assignment_status = payload[2]
            self._assignment_event.set()
        elif payload[:2] == b"\x02\x16":
            self._join_status = payload[2]
            self._join_event.set()
        elif payload[:2] == b"\x01\x0a" and len(payload) >= 6:
            own = int.from_bytes(payload[2:6], "little")
            self._own_vaddr = own or 0xFFFFFFFF
            if own == 0:
                self._device_count = 1
            self._own_vaddr_event.set()
        elif payload[:2] == b"\x01\x02" and len(payload) >= 10:
            self._device_count = int.from_bytes(payload[8:10], "little")
            self._target_vaddr = None
            self._target_vaddr_event.clear()
            self._session_ready = False
        elif payload[0] == 3 and len(payload) >= 6:
            channel = payload[5]
            if channel == 0xFF and len(payload) >= 16:
                from ..kaidi_protocol import format_kaidi_node_address

                if format_kaidi_node_address(payload[6:12]) == self._coordinator.address.upper():
                    raw = int.from_bytes(payload[12:16], "little", signed=True)
                    self._target_vaddr = raw if raw else -2
                    self._target_vaddr_event.set()
            elif channel == 0x20 and len(payload) >= 14 and payload[11] == 166:
                self._battery_mode = payload[12] == 1
                self.forward_controller_state_update("floyd_battery_mode", self._battery_mode)
        # Other incoming routes have no bed-state consumer. Raw diagnostics retain
        # them, without interpreting SDK product/group fields as capabilities.

    async def _send(self, packet: bytes, cancel_event: asyncio.Event | None = None) -> None:
        """Serialize with the coordinator; retain the app's 50 ms queue spacing."""
        delay = self._next_write_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        await self._write_gatt_with_retry(
            KAIDI_WRITE_CHAR_UUID, packet, response=self._write_with_response,
            cancel_event=cancel_event,
        )
        self._next_write_at = time.monotonic() + 0.05

    def _build_control_packet(self, command_id: int, param: int | None = None) -> bytes:
        if self._target_vaddr is None or self._target_vaddr == 0:
            raise RuntimeError("Floyd target has not answered a live ping")
        target = 0 if self._target_vaddr == -2 else self._target_vaddr
        parameter = self._parameter if param is None else param
        return (b"\x03" + (target & 0xFFFFFFFF).to_bytes(4, "little") + b"\x20"
                + (self._own_vaddr or 0).to_bytes(4, "little")
                + bytes((1, command_id, parameter, 0)))

    async def _ensure_session_ready(self) -> None:
        if self._session_ready:
            return
        async with self._session_lock:
            if self._session_ready:
                return
            if self._room_id is None:
                self._try_resolve_room_id_from_ha()
            if not self._room_id:
                raise ValueError("Assign this unassigned bed to a BLE room with floyd_action first")
            await self._ensure_notify_started()
            self._join_event.clear()
            self._join_status = None
            await self._send(self._build_join_packet(self._room_id))
            await self._wait_for_event(self._join_event, 5, "authentication")
            if self._join_status != 0:
                raise ValueError("Floyd BLE room authentication was rejected")
            self._target_vaddr = None
            self._target_vaddr_event.clear()
            await self._send(self._build_ping_packet())
            await self._wait_for_event(self._target_vaddr_event, 5, "matching node ping")
            self._session_ready = True

    async def _write_control_command(
        self, command_id: int, *, param: int | None = None,
        repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._ensure_session_ready()
        if param is not None:
            self._parameter = param
            self.forward_controller_state_update("floyd_retained_parameter", param)
        await self._send(self._build_control_packet(command_id), cancel_event)

    async def prepare_for_movement(self) -> None:
        """Finish authentication before the caller starts its movement deadline."""
        await self._ensure_session_ready()

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        axis = {"back": "head", "legs": "feet"}.get(motor)
        self.validate_hold_control(f"{axis}_{direction}", duration_ms)

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        return max(1, (duration_ms + pulse_delay_ms - 1) // pulse_delay_ms)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in FLOYD_HOLDS or not 1 <= duration_ms <= 30000:
            raise ValueError("Choose a Floyd held control and a duration of 1 to 30000 ms")
        if self._battery_mode and control.endswith("_up"):
            raise ValueError("Floyd reports battery mode; raising is disabled")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._ensure_session_ready()
        # Authentication may have delivered a new battery event.
        self.validate_hold_control(control, duration_ms)
        move, stop = FLOYD_HOLDS[control]
        release_packet = self._build_control_packet(stop)
        try:
            await self._write_control_command(move)
            try:
                await asyncio.wait_for(self._coordinator.cancel_command.wait(), duration_ms / 1000)
            except TimeoutError:
                pass
        finally:
            # Never let a cancellation signal suppress the release frame.
            await self._send(release_packet, cancel_event=asyncio.Event())

    async def _move_with_stop_command(self, move_command: int, stop_command: int) -> None:
        control = next(key for key, pair in FLOYD_HOLDS.items() if pair == (move_command, stop_command))
        count, delay = self.motor_pulse_settings()
        await self.hold_control(control, max(1, min(30000, count * delay)))

    def validate_floyd_action(
        self, action: str, internal_side: str, confirm: bool, room_id: int | None,
    ) -> None:
        if internal_side not in FLOYD_PRESETS:
            raise ValueError("Unknown Floyd internal preset selector")
        if action in {"save_zero_g", "save_anti_snore", "assign_room", "confirm_add"}:
            if not confirm or internal_side != "first":
                raise ValueError("Configuration requires confirm: true and internal_side: first")
        elif action not in FLOYD_PRESETS[internal_side]:
            raise ValueError("Unknown Floyd action")
        if action == "assign_room":
            if room_id is None or not 1 <= room_id <= 0xFFFFFFFF:
                raise ValueError("Choose a nonzero 32-bit BLE room ID")
            payload = self._manufacturer_data.get(0xFFFF)
            advertisement = extract_kaidi_advertisement({0xFFFF: payload}) if payload else None
            if self._room_id not in (None, 0) or not (
                is_floyd_advertisement(advertisement)
                and advertisement is not None
                and (advertisement.adv_type == 9 or advertisement.room_id == 0)
            ):
                raise ValueError("Room assignment requires an advertisement proving an unassigned bed")
        elif room_id is not None:
            raise ValueError("room_id is only valid for assign_room")

    async def floyd_action(
        self, action: str, internal_side: str, confirm: bool, room_id: int | None,
    ) -> None:
        self.validate_floyd_action(action, internal_side, confirm, room_id)
        if action == "assign_room":
            assert room_id is not None
            await self._ensure_notify_started()
            self._assignment_event.clear()
            self._assignment_status = None
            await self._send(b"\x01\x03" + room_id.to_bytes(4, "little") + b"1122\x00\x00\x00\x00")
            await self._wait_for_event(self._assignment_event, 5, "room assignment")
            if self._assignment_status != 0:
                raise ValueError("Floyd BLE room assignment failed")
            self._room_id = room_id
            self._session_ready = False
            self._target_vaddr = None
            # The app disconnects after assignment. HA closes through its owner.
            return
        if action == "confirm_add":
            await self._write_control_command(0x45)
        elif action.startswith("save_"):
            await self._write_control_command(0xA7, param=1 if action == "save_zero_g" else 4)
        else:
            await self._ensure_session_ready()
            if internal_side != "first" and self._target_vaddr is not None and self._target_vaddr < 0 and self._target_vaddr != -2:
                raise ValueError("Conditional alarm selectors require a positive target or live zero sentinel")
            await self._write_control_command(FLOYD_PRESETS[internal_side][action])
