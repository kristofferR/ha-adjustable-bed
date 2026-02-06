"""Limoss / Stawett bed controller implementation.

Protocol reverse-engineered from:
- com.limoss.limossremote
- com.stawett

Protocol summary:
- Service/characteristic: FFE0 / FFE1 (shared with other bed protocols)
- Command payload: 5 bytes [cmd, p1, p2, p3, p4]
- Transport packet: 10 bytes [0xDD, encrypted(8), checksum]
- Encryption: TEA (16 rounds) over 8-byte inner packet
- Position feedback: AskPos commands (0x10/0x20/0x30/0x40) return 32-bit values
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import LIMOSS_CHAR_UUID, LIMOSS_SERVICE_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# TEA constants from Limoss/Stawett APKs (BleService.KEY / CmdFormater.e)
_TEA_KEY: tuple[int, int, int, int] = (1431639188, 1949848917, 1431639188, 1949848917)
_TEA_DELTA = 0x9E3779B9
_TEA_ROUNDS = 16
_U32_MASK = 0xFFFFFFFF

_DEFAULT_MAX_RAW_ESTIMATE: dict[str, int] = {
    "back": 16000,
    "legs": 12000,
    "head": 16000,
    "feet": 12000,
}
_MAX_ESTIMATE_SHRINK_TRIGGER_RATIO = 0.7
_MAX_ESTIMATE_SHRINK_STREAK = 6
_MAX_ESTIMATE_SHRINK_DECAY = 0.9
_MAX_ESTIMATE_MIN_SHRINK_SAMPLE = 500


class LimossCommands:
    """Limoss command constants."""

    # Motor movement (hold-style commands)
    MOTOR_1_UP = 0x12  # Head/Back up
    MOTOR_1_DOWN = 0x13  # Head/Back down
    MOTOR_2_UP = 0x22  # Legs/Feet up
    MOTOR_2_DOWN = 0x23  # Legs/Feet down
    MOTOR_3_UP = 0x32
    MOTOR_3_DOWN = 0x33
    MOTOR_4_UP = 0x42
    MOTOR_4_DOWN = 0x43

    # Stop
    STOP_ALL = 0xFF

    # Preset-like movement
    PRESET_FLAT = 0x51  # Both motors down

    # Query/capability commands
    QUERY_CAPABILITIES = 0x02
    ASK_MOTOR_1_POS = 0x10
    ASK_MOTOR_2_POS = 0x20
    ASK_MOTOR_3_POS = 0x30
    ASK_MOTOR_4_POS = 0x40

    # SetPos commands (for memory recall)
    SET_MOTOR_1_POS = 0x11
    SET_MOTOR_2_POS = 0x21
    SET_MOTOR_3_POS = 0x31
    SET_MOTOR_4_POS = 0x41

    # Vibration zone commands
    VIBRATION_1 = 0x60
    VIBRATION_2 = 0x61
    VIBRATION_3 = 0x62
    VIBRATION_4 = 0x63
    VIBRATION_5 = 0x64
    VIBRATION_6 = 0x65

    # Optional feature commands
    LIGHT_TOGGLE = 0x70


POSITION_MAP: dict[int, str] = {
    LimossCommands.ASK_MOTOR_1_POS: "back",
    LimossCommands.ASK_MOTOR_2_POS: "legs",
    LimossCommands.ASK_MOTOR_3_POS: "head",
    LimossCommands.ASK_MOTOR_4_POS: "feet",
}


class LimossController(BedController):
    """Controller for Limoss / Stawett TEA-encrypted protocol."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._write_with_response: bool = True
        self._counter: int = 0
        self._capabilities_received: asyncio.Event | None = None
        self._memory_slot_count: int = 0
        self._reported_motor_count: int | None = None
        self._last_positions_raw: dict[str, int] = {}
        self._memory_positions: dict[int, dict[str, int]] = {}
        self._vibration_count: int = 0
        # Position normalization state (raw 32-bit samples -> estimated angles).
        self._max_raw_estimate: dict[str, int] = _DEFAULT_MAX_RAW_ESTIMATE.copy()
        self._low_sample_streak: dict[str, int] = dict.fromkeys(
            _DEFAULT_MAX_RAW_ESTIMATE, 0
        )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LIMOSS_CHAR_UUID

    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Limoss supports a flat movement command."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return reported memory slot count (fallback: 0)."""
        return self._memory_slot_count if self._memory_slot_count > 0 else 0

    def reset_max_raw_estimate(self) -> None:
        """Reset raw-position normalization estimates.

        Called by the coordinator on connection/reconnection to avoid carrying
        stale calibration state across sessions.
        """
        self._max_raw_estimate = _DEFAULT_MAX_RAW_ESTIMATE.copy()
        self._low_sample_streak = dict.fromkeys(_DEFAULT_MAX_RAW_ESTIMATE, 0)
        _LOGGER.debug(
            "Reset Limoss max raw position estimates for %s",
            self._coordinator.address,
        )

    @staticmethod
    def _tea_encrypt(block: bytes) -> bytes:
        """Encrypt an 8-byte block with TEA (16 rounds)."""
        if len(block) != 8:
            raise ValueError("TEA block must be exactly 8 bytes")

        v0 = int.from_bytes(block[:4], byteorder="big")
        v1 = int.from_bytes(block[4:], byteorder="big")
        k0, k1, k2, k3 = _TEA_KEY
        sum_value = 0

        for _ in range(_TEA_ROUNDS):
            sum_value = (sum_value + _TEA_DELTA) & _U32_MASK
            v0 = (
                v0 + (((v1 << 4) + k0) ^ (v1 + sum_value) ^ ((v1 >> 5) + k1))
            ) & _U32_MASK
            v1 = (
                v1 + (((v0 << 4) + k2) ^ (v0 + sum_value) ^ ((v0 >> 5) + k3))
            ) & _U32_MASK

        return v0.to_bytes(4, byteorder="big") + v1.to_bytes(4, byteorder="big")

    @staticmethod
    def _tea_decrypt(block: bytes) -> bytes:
        """Decrypt an 8-byte block with TEA (16 rounds)."""
        if len(block) != 8:
            raise ValueError("TEA block must be exactly 8 bytes")

        v0 = int.from_bytes(block[:4], byteorder="big")
        v1 = int.from_bytes(block[4:], byteorder="big")
        k0, k1, k2, k3 = _TEA_KEY
        sum_value = (_TEA_DELTA * _TEA_ROUNDS) & _U32_MASK

        for _ in range(_TEA_ROUNDS):
            v1 = (
                v1 - (((v0 << 4) + k2) ^ (v0 + sum_value) ^ ((v0 >> 5) + k3))
            ) & _U32_MASK
            v0 = (
                v0 - (((v1 << 4) + k0) ^ (v1 + sum_value) ^ ((v1 >> 5) + k1))
            ) & _U32_MASK
            sum_value = (sum_value - _TEA_DELTA) & _U32_MASK

        return v0.to_bytes(4, byteorder="big") + v1.to_bytes(4, byteorder="big")

    def _next_counter(self) -> int:
        """Return the current sequence counter and increment it."""
        value = self._counter
        self._counter = (self._counter + 1) & 0xFF
        return value

    def _build_packet(self, cmd: int, p1: int = 0, p2: int = 0, p3: int = 0, p4: int = 0) -> bytes:
        """Build a full 10-byte encrypted Limoss packet."""
        inner = bytearray(8)
        inner[0] = 0xAA
        inner[1] = cmd & 0xFF
        inner[2] = p1 & 0xFF
        inner[3] = p2 & 0xFF
        inner[4] = p3 & 0xFF
        inner[5] = p4 & 0xFF
        inner[6] = self._next_counter()
        inner[7] = sum(inner[0:7]) & 0xFF

        encrypted = self._tea_encrypt(bytes(inner))

        outer = bytearray(10)
        outer[0] = 0xDD
        outer[1:9] = encrypted
        outer[9] = sum(outer[0:9]) & 0xFF
        return bytes(outer)

    def _decode_packet(self, packet: bytes) -> tuple[int, bytes] | None:
        """Decode and validate a Limoss packet.

        Returns:
            Tuple of (command, params[4]) if valid, otherwise None.
        """
        if len(packet) < 10:
            return None

        frame = packet[:10]
        if frame[0] != 0xDD:
            return None

        if (sum(frame[0:9]) & 0xFF) != frame[9]:
            _LOGGER.debug("Invalid Limoss outer checksum: %s", frame.hex())
            return None

        inner = self._tea_decrypt(frame[1:9])
        if inner[0] != 0xAA:
            _LOGGER.debug("Invalid Limoss inner header after decrypt: %s", inner.hex())
            return None

        if (sum(inner[0:7]) & 0xFF) != inner[7]:
            _LOGGER.debug("Invalid Limoss inner checksum: %s", inner.hex())
            return None

        return inner[1], bytes(inner[2:6])

    def _raw_to_angle(self, raw_value: int, motor: str) -> float:
        """Convert raw Limoss 32-bit position value to an estimated angle."""
        current_max = self._max_raw_estimate.get(motor, 16000)
        if raw_value > current_max:
            current_max = raw_value
            self._max_raw_estimate[motor] = raw_value
            self._low_sample_streak[motor] = 0
        else:
            current_max = self._maybe_shrink_max_raw_estimate(
                motor=motor,
                raw_value=raw_value,
                current_max=current_max,
            )

        if current_max <= 0:
            return 0.0

        percent = min(100.0, max(0.0, (raw_value / current_max) * 100.0))
        max_angle = self._coordinator.get_max_angle(motor)
        return (percent / 100.0) * max_angle

    def _maybe_shrink_max_raw_estimate(
        self,
        motor: str,
        raw_value: int,
        current_max: int,
    ) -> int:
        """Shrink overestimated max-raw values after repeated low samples."""
        if current_max <= 0:
            return current_max

        if (
            raw_value >= _MAX_ESTIMATE_MIN_SHRINK_SAMPLE
            and raw_value < (current_max * _MAX_ESTIMATE_SHRINK_TRIGGER_RATIO)
        ):
            streak = self._low_sample_streak.get(motor, 0) + 1
            self._low_sample_streak[motor] = streak

            if streak >= _MAX_ESTIMATE_SHRINK_STREAK:
                previous_max = current_max
                shrunk_max = max(
                    int(current_max * _MAX_ESTIMATE_SHRINK_DECAY),
                    1,
                )
                if shrunk_max < current_max:
                    self._max_raw_estimate[motor] = shrunk_max
                    current_max = shrunk_max
                    _LOGGER.info(
                        "Shrank Limoss max raw estimate for %s on %s: %d -> %d (streak=%d)",
                        motor,
                        self._coordinator.address,
                        previous_max,
                        shrunk_max,
                        streak,
                    )

                self._low_sample_streak[motor] = 0
        else:
            self._low_sample_streak[motor] = 0

        return current_max

    def _effective_motor_count(self) -> int:
        """Return the best available motor count for runtime command routing."""
        if self._reported_motor_count is not None:
            return max(2, min(4, self._reported_motor_count))
        return max(2, min(4, self._coordinator.motor_count))

    async def _send_command(
        self,
        cmd: int,
        p1: int = 0,
        p2: int = 0,
        p3: int = 0,
        p4: int = 0,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Send a Limoss command payload [cmd, p1, p2, p3, p4]."""
        await self.write_command(
            bytes([cmd & 0xFF, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF, p4 & 0xFF]),
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command to the bed.

        Accepts:
        - 5-byte logical payload: [cmd, p1, p2, p3, p4]
        - 10-byte pre-built encrypted packet starting with 0xDD
        """
        if len(command) == 5:
            packet = self._build_packet(command[0], command[1], command[2], command[3], command[4])
        elif len(command) == 10 and command[0] == 0xDD:
            packet = command
        else:
            raise ValueError(
                "Limoss command must be 5-byte payload or 10-byte encrypted packet"
            )

        _LOGGER.debug(
            "Writing Limoss packet: %s (repeat=%d, delay=%dms, response=%s)",
            packet.hex(),
            repeat_count,
            repeat_delay_ms,
            self._write_with_response,
        )

        await self._write_gatt_with_retry(
            LIMOSS_CHAR_UUID,
            packet,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    def _handle_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle Limoss notification packets."""
        raw = bytes(data)
        self.forward_raw_notification(LIMOSS_CHAR_UUID, raw)
        decoded = self._decode_packet(raw)
        if decoded is None:
            return

        cmd, params = decoded

        if cmd == LimossCommands.QUERY_CAPABILITIES:
            button_count = params[0]
            system_type = params[1]
            vibration_count = params[2]
            main_and_memory = params[3]
            motor_count = system_type & 0x0F
            memory_count = main_and_memory & 0x0F

            self._reported_motor_count = motor_count if motor_count > 0 else None
            self._memory_slot_count = memory_count
            self._vibration_count = vibration_count

            _LOGGER.info(
                "Limoss capabilities: buttons=%d motors=%d vibration=%d memory=%d",
                button_count,
                motor_count,
                vibration_count,
                memory_count,
            )

            if self._capabilities_received is not None:
                self._capabilities_received.set()
            return

        position_key = POSITION_MAP.get(cmd)
        if position_key is None:
            return

        raw_position = int.from_bytes(params, byteorder="big", signed=False)
        self._last_positions_raw[position_key] = raw_position
        angle = self._raw_to_angle(raw_position, position_key)

        _LOGGER.debug(
            "Limoss position update: %s raw=%d estimated=%.1f",
            position_key,
            raw_position,
            angle,
        )

        if self._notify_callback is not None:
            self._notify_callback(position_key, angle)

    async def _query_capabilities(self) -> None:
        """Query runtime capabilities from the controller."""
        if self.client is None or not self.client.is_connected:
            return

        self._capabilities_received = asyncio.Event()
        try:
            # Matches app payload: [0x02, 0x00, 0x00, 0x00, 0x03]
            await self._send_command(LimossCommands.QUERY_CAPABILITIES, 0, 0, 0, 3)
            await asyncio.wait_for(self._capabilities_received.wait(), timeout=2.0)
        except TimeoutError:
            _LOGGER.debug("Timed out waiting for Limoss capability response")
        finally:
            self._capabilities_received = None

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for notifications."""
        self._notify_callback = callback

        if self.client is None or not self.client.is_connected:
            _LOGGER.warning("Cannot start Limoss notifications: not connected")
            return

        # Prefer write-with-response when available, fallback to write-without-response.
        if self.client.services is not None:
            service = self.client.services.get_service(LIMOSS_SERVICE_UUID)
            if service is not None:
                char = service.get_characteristic(LIMOSS_CHAR_UUID)
                if char is not None:
                    props = {prop.lower() for prop in char.properties}
                    if "write" in props:
                        self._write_with_response = True
                    elif "write-without-response" in props:
                        self._write_with_response = False
                    _LOGGER.debug(
                        "Limoss GATT write properties for %s: %s (write_with_response=%s)",
                        self._coordinator.address,
                        sorted(props),
                        self._write_with_response,
                    )

        await self.client.start_notify(LIMOSS_CHAR_UUID, self._handle_notification)
        _LOGGER.info("Started Limoss notifications")

        await self._query_capabilities()

        if callback is not None:
            await self.read_positions()

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        self._notify_callback = None
        if self.client is None or not self.client.is_connected:
            return

        with contextlib.suppress(BleakError):
            await self.client.stop_notify(LIMOSS_CHAR_UUID)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Query current motor positions.

        Position responses are returned via notifications.

        The caller-supplied ``motor_count`` is treated as a hint. If
        ``self._reported_motor_count`` is available from a capability response,
        that device-reported value takes precedence over ``motor_count``.
        The effective count is then clamped to the 2-4 range and used to build
        the query command list before sending each query via ``_send_command``.
        """
        if self.client is None or not self.client.is_connected:
            return

        effective_motor_count = motor_count
        if self._reported_motor_count is not None:
            effective_motor_count = self._reported_motor_count

        effective_motor_count = max(2, min(4, effective_motor_count))
        query_commands = [
            LimossCommands.ASK_MOTOR_1_POS,
            LimossCommands.ASK_MOTOR_2_POS,
        ]
        if effective_motor_count >= 3:
            query_commands.append(LimossCommands.ASK_MOTOR_3_POS)
        if effective_motor_count >= 4:
            query_commands.append(LimossCommands.ASK_MOTOR_4_POS)

        for cmd in query_commands:
            await self._send_command(cmd)
            await asyncio.sleep(0.03)

    async def _send_stop(self) -> None:
        """Send stop command with a fresh cancel event."""
        await self._send_command(
            LimossCommands.STOP_ALL,
            cancel_event=asyncio.Event(),
        )

    async def _move_with_stop(self, cmd: int) -> None:
        """Send a hold-style movement command and then stop."""
        try:
            await self._send_command(
                cmd,
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
            )
        finally:
            with contextlib.suppress(BleakError, ConnectionError):
                await self._send_stop()

    # Motor control methods
    async def move_head_up(self) -> None:
        # For 3+ motor beds, head is motor 3. For 2-motor beds, alias head to motor 1.
        cmd = (
            LimossCommands.MOTOR_3_UP
            if self._effective_motor_count() >= 3
            else LimossCommands.MOTOR_1_UP
        )
        await self._move_with_stop(cmd)

    async def move_head_down(self) -> None:
        cmd = (
            LimossCommands.MOTOR_3_DOWN
            if self._effective_motor_count() >= 3
            else LimossCommands.MOTOR_1_DOWN
        )
        await self._move_with_stop(cmd)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self._move_with_stop(LimossCommands.MOTOR_1_UP)

    async def move_back_down(self) -> None:
        await self._move_with_stop(LimossCommands.MOTOR_1_DOWN)

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(LimossCommands.MOTOR_2_UP)

    async def move_legs_down(self) -> None:
        await self._move_with_stop(LimossCommands.MOTOR_2_DOWN)

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        # For 4-motor beds, feet is motor 4. For 2/3-motor beds, alias feet to motor 2.
        cmd = (
            LimossCommands.MOTOR_4_UP
            if self._effective_motor_count() >= 4
            else LimossCommands.MOTOR_2_UP
        )
        await self._move_with_stop(cmd)

    async def move_feet_down(self) -> None:
        cmd = (
            LimossCommands.MOTOR_4_DOWN
            if self._effective_motor_count() >= 4
            else LimossCommands.MOTOR_2_DOWN
        )
        await self._move_with_stop(cmd)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        """Send both-down movement command and then stop."""
        await self._move_with_stop(LimossCommands.PRESET_FLAT)

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if positions have been saved to recall."""
        return len(self._memory_positions) > 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Limoss supports saving positions via SetPos."""
        return True

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a saved memory position via SetPos commands.

        Sends stored position data to each motor at 300ms intervals.
        """
        positions = self._memory_positions.get(memory_num)
        if not positions:
            _LOGGER.warning(
                "No positions saved in Limoss memory slot %d (save first)", memory_num
            )
            return

        set_pos_commands = {
            "back": LimossCommands.SET_MOTOR_1_POS,
            "legs": LimossCommands.SET_MOTOR_2_POS,
            "head": LimossCommands.SET_MOTOR_3_POS,
            "feet": LimossCommands.SET_MOTOR_4_POS,
        }

        for motor_name, raw_pos in positions.items():
            cmd = set_pos_commands.get(motor_name)
            if cmd is None:
                continue
            p1 = (raw_pos >> 24) & 0xFF
            p2 = (raw_pos >> 16) & 0xFF
            p3 = (raw_pos >> 8) & 0xFF
            p4 = raw_pos & 0xFF
            await self._send_command(cmd, p1, p2, p3, p4)
            await asyncio.sleep(0.3)

    async def program_memory(self, memory_num: int) -> None:
        """Save current motor positions to a memory slot."""
        if not self._last_positions_raw:
            _LOGGER.warning("No position data available to save to Limoss memory slot %d", memory_num)
            return
        self._memory_positions[memory_num] = dict(self._last_positions_raw)
        _LOGGER.info(
            "Saved Limoss positions to memory slot %d: %s", memory_num, self._memory_positions[memory_num]
        )

    # Massage/vibration methods
    async def massage_toggle(self) -> None:
        """Toggle vibration zone 1."""
        await self._send_command(LimossCommands.VIBRATION_1)

    async def massage_zone(self, zone: int) -> None:
        """Toggle a specific vibration zone (1-6)."""
        zone_commands = {
            1: LimossCommands.VIBRATION_1,
            2: LimossCommands.VIBRATION_2,
            3: LimossCommands.VIBRATION_3,
            4: LimossCommands.VIBRATION_4,
            5: LimossCommands.VIBRATION_5,
            6: LimossCommands.VIBRATION_6,
        }
        if cmd := zone_commands.get(zone):
            await self._send_command(cmd)
        else:
            _LOGGER.warning("Invalid Limoss vibration zone: %d (valid: 1-6)", zone)

    # Optional light helper (not exposed as capability by default)
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self._send_command(LimossCommands.LIGHT_TOGGLE)
