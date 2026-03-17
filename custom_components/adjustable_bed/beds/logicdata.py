"""Logicdata SimplicityFrame bed controller implementation.

Protocol reverse-engineered from:
- at.silvermotion (SILVERmotion app, Flutter/Dart)

Protocol summary:
- Service: b9934c43-5c91-462b-80a1-30fccc29d758 (LogicLink)
- Characteristic: b9934c44-5c91-462b-80a1-30fccc29d758
- TX pipeline: payload -> pad to 8 bytes -> XXTEA encrypt -> CRC16 -> SLIP frame
- Encryption: Corrected Block TEA (XXTEA) with 16-byte static key
- Integrity: CRC-CCITT (0xFFFF initial, polynomial 0x1021)
- Framing: SLIP (RFC 1055) with 0xC0 delimiters
- BLE pairing required (encrypted characteristic)
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import TYPE_CHECKING

from ..const import LOGICDATA_CHAR_UUID
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# XXTEA constants
# Key extracted from SILVERmotion APK (SF_GetPipelineTx encryption config)
# Raw bytes: 6C 4F 42 F5 67 68 02 E2 53 AC 9A 27 02 A6 37 AB
# Packed as little-endian uint32s:
_XXTEA_KEY: tuple[int, int, int, int] = (
    0xF5424F6C,
    0xE2026867,
    0x279AAC53,
    0xAB37A602,
)
_XXTEA_DELTA = 0x9E3779B9
_U32_MASK = 0xFFFFFFFF

# CRC-CCITT constants
_CRC_INIT = 0xFFFF
_CRC_POLY = 0x1021

# SLIP framing constants (RFC 1055)
_SLIP_END = 0xC0
_SLIP_ESC = 0xDB
_SLIP_ESC_END = 0xDC
_SLIP_ESC_ESC = 0xDD

# Minimum payload size for XXTEA (2x uint32 = 8 bytes)
_XXTEA_MIN_BYTES = 8


class LogicdataCommands:
    """Logicdata command byte constants.

    Command format: [opcode, param1, param2]
    Extracted from SILVERmotion APK (SF_Controller command methods).
    """

    # Motor movement (hold-style, requires repeated sends)
    HEAD_UP = bytes([0x51, 0x00, 0x00])
    HEAD_DOWN = bytes([0x52, 0x00, 0x00])
    LEGS_UP = bytes([0x51, 0x01, 0x00])
    LEGS_DOWN = bytes([0x52, 0x01, 0x00])

    # Stop
    STOP = bytes([0xB0, 0x00, 0x01])

    # AnyKey pressed (preamble for presets)
    ANY_KEY_PRESSED = bytes([0xB0, 0x00, 0x00])

    # Preset recall
    MEMORY_1 = bytes([0x5C, 0x00, 0x00])
    MEMORY_2 = bytes([0x5C, 0x01, 0x00])
    FLAT = bytes([0x5C, 0x04, 0x00])

    # Preset save
    SAVE_MEMORY_1 = bytes([0x5B, 0x00, 0x00])
    SAVE_MEMORY_2 = bytes([0x5B, 0x01, 0x00])

    # Under-bed light
    LIGHT_ON = bytes([0x95, 0x00, 0x0F])
    LIGHT_OFF = bytes([0x95, 0x00, 0x00])

    # Massage intensity
    MASSAGE_INTENSITY_UP = bytes([0x81, 0x00, 0x00])
    MASSAGE_INTENSITY_DOWN = bytes([0x82, 0x00, 0x00])
    MASSAGE_OFF = bytes([0x86, 0x00, 0x00])


def _xxtea_encrypt(data: bytes, key: tuple[int, int, int, int]) -> bytes:
    """Encrypt data using Corrected Block TEA (XXTEA).

    Input must be a multiple of 4 bytes (at least 8 bytes).
    Uses little-endian word packing per standard XXTEA.
    """
    if len(data) < _XXTEA_MIN_BYTES or len(data) % 4 != 0:
        raise ValueError(
            f"XXTEA input must be >= {_XXTEA_MIN_BYTES} bytes and multiple of 4, got {len(data)}"
        )

    n = len(data) // 4
    v = list(struct.unpack(f"<{n}I", data))

    rounds = 6 + 52 // n
    total = 0

    for _ in range(rounds):
        total = (total + _XXTEA_DELTA) & _U32_MASK
        e = (total >> 2) & 3
        for p in range(n):
            y = v[(p + 1) % n]
            z = v[(p - 1) % n]
            mx = (
                ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4))
                ^ ((total ^ y) + (key[(p & 3) ^ e] ^ z))
            ) & _U32_MASK
            v[p] = (v[p] + mx) & _U32_MASK

    return struct.pack(f"<{n}I", *v)


def _xxtea_decrypt(data: bytes, key: tuple[int, int, int, int]) -> bytes:
    """Decrypt data using Corrected Block TEA (XXTEA)."""
    if len(data) < _XXTEA_MIN_BYTES or len(data) % 4 != 0:
        raise ValueError(
            f"XXTEA input must be >= {_XXTEA_MIN_BYTES} bytes and multiple of 4, got {len(data)}"
        )

    n = len(data) // 4
    v = list(struct.unpack(f"<{n}I", data))

    rounds = 6 + 52 // n
    total = (rounds * _XXTEA_DELTA) & _U32_MASK

    for _ in range(rounds):
        e = (total >> 2) & 3
        for p in range(n - 1, -1, -1):
            y = v[(p + 1) % n]
            z = v[(p - 1) % n]
            mx = (
                ((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4))
                ^ ((total ^ y) + (key[(p & 3) ^ e] ^ z))
            ) & _U32_MASK
            v[p] = (v[p] - mx) & _U32_MASK
        total = (total - _XXTEA_DELTA) & _U32_MASK

    return struct.pack(f"<{n}I", *v)


def _crc16_ccitt(data: bytes) -> int:
    """Compute CRC-CCITT (0xFFFF initial, polynomial 0x1021)."""
    crc = _CRC_INIT
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _slip_encode(data: bytes) -> bytes:
    """Apply SLIP framing to data.

    Wraps data with END bytes and escapes END/ESC within the data.
    """
    out = bytearray([_SLIP_END])
    for byte in data:
        if byte == _SLIP_END:
            out.extend([_SLIP_ESC, _SLIP_ESC_END])
        elif byte == _SLIP_ESC:
            out.extend([_SLIP_ESC, _SLIP_ESC_ESC])
        else:
            out.append(byte)
    out.append(_SLIP_END)
    return bytes(out)


class LogicdataController(BedController):
    """Controller for Logicdata SimplicityFrame (SILVERmotion) beds.

    Uses XXTEA encryption with CRC16 integrity and SLIP framing.
    BLE pairing is required.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the controller."""
        super().__init__(coordinator)

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return LOGICDATA_CHAR_UUID

    @property
    def supports_preset_flat(self) -> bool:
        """Return True - Logicdata supports flat preset."""
        return True

    @property
    def memory_slot_count(self) -> int:
        """Return number of memory slots (2)."""
        return 2

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - Logicdata supports on/off light commands."""
        return True

    @staticmethod
    def _pad_payload(payload: bytes) -> bytes:
        """Pad payload to minimum 8 bytes for XXTEA (packet clip stage)."""
        if len(payload) >= _XXTEA_MIN_BYTES:
            # Pad to next multiple of 4 if needed
            remainder = len(payload) % 4
            if remainder:
                return payload + b"\x00" * (4 - remainder)
            return payload
        return payload + b"\x00" * (_XXTEA_MIN_BYTES - len(payload))

    @staticmethod
    def _build_packet(payload: bytes) -> bytes:
        """Build a complete packet from a command payload.

        Pipeline: pad -> XXTEA encrypt -> CRC16 -> length prefix -> SLIP frame.
        """
        # Step 1: Pad to 8 bytes minimum for XXTEA
        padded = LogicdataController._pad_payload(payload)

        # Step 2: XXTEA encrypt
        encrypted = _xxtea_encrypt(padded, _XXTEA_KEY)

        # Step 3: CRC16 over encrypted data
        crc = _crc16_ccitt(encrypted)
        with_crc = encrypted + struct.pack(">H", crc)

        # Step 4: Length prefix (1 byte for payload length)
        framed = bytes([len(with_crc)]) + with_crc

        # Step 5: SLIP frame
        return _slip_encode(framed)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 30,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command through the XXTEA+CRC16+SLIP pipeline."""
        packet = self._build_packet(command)

        _LOGGER.debug(
            "Writing Logicdata packet: payload=%s encrypted=%s (repeat=%d, delay=%dms)",
            command.hex(),
            packet.hex(),
            repeat_count,
            repeat_delay_ms,
        )

        await self._write_gatt_with_retry(
            LOGICDATA_CHAR_UUID,
            packet,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    async def _send_feature_command(self, command: bytes) -> None:
        """Send a non-motor command (3 sends, 30ms delay)."""
        await self.write_command(command, repeat_count=3, repeat_delay_ms=30)

    async def _send_stop(self) -> None:
        """Send stop command with a fresh cancel event."""
        await self.write_command(
            LogicdataCommands.STOP,
            repeat_count=1,
            cancel_event=asyncio.Event(),
        )

    async def _move_with_stop(self, command: bytes) -> None:
        """Send a hold-style movement command and then stop."""
        try:
            await self.write_command(
                command,
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
            )
        finally:
            await self._send_stop()

    # Motor control methods
    async def move_head_up(self) -> None:
        await self._move_with_stop(LogicdataCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        await self._move_with_stop(LogicdataCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self._move_with_stop(LogicdataCommands.HEAD_UP)

    async def move_back_down(self) -> None:
        await self._move_with_stop(LogicdataCommands.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop(LogicdataCommands.LEGS_UP)

    async def move_legs_down(self) -> None:
        await self._move_with_stop(LogicdataCommands.LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._move_with_stop(LogicdataCommands.LEGS_UP)

    async def move_feet_down(self) -> None:
        await self._move_with_stop(LogicdataCommands.LEGS_DOWN)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # Preset methods
    async def preset_flat(self) -> None:
        """Move bed to flat position (with AnyKey preamble)."""
        await self._send_feature_command(LogicdataCommands.ANY_KEY_PRESSED)
        await asyncio.sleep(0.05)
        await self._send_feature_command(LogicdataCommands.FLAT)

    async def preset_memory(self, memory_num: int) -> None:
        """Recall a memory preset (1 or 2)."""
        commands = {
            1: LogicdataCommands.MEMORY_1,
            2: LogicdataCommands.MEMORY_2,
        }
        cmd = commands.get(memory_num)
        if cmd is None:
            _LOGGER.warning("Invalid Logicdata memory slot: %d (valid: 1-2)", memory_num)
            return
        await self._send_feature_command(LogicdataCommands.ANY_KEY_PRESSED)
        await asyncio.sleep(0.05)
        await self._send_feature_command(cmd)

    async def program_memory(self, memory_num: int) -> None:
        """Save current position to a memory slot (1 or 2)."""
        commands = {
            1: LogicdataCommands.SAVE_MEMORY_1,
            2: LogicdataCommands.SAVE_MEMORY_2,
        }
        cmd = commands.get(memory_num)
        if cmd is None:
            _LOGGER.warning("Invalid Logicdata save slot: %d (valid: 1-2)", memory_num)
            return
        await self._send_feature_command(cmd)

    # Light control
    async def lights_on(self) -> None:
        """Turn under-bed light on."""
        await self._send_feature_command(LogicdataCommands.LIGHT_ON)

    async def lights_off(self) -> None:
        """Turn under-bed light off."""
        await self._send_feature_command(LogicdataCommands.LIGHT_OFF)

    # Massage control
    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        await self._send_feature_command(LogicdataCommands.MASSAGE_INTENSITY_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        await self._send_feature_command(LogicdataCommands.MASSAGE_INTENSITY_DOWN)

    async def massage_off(self) -> None:
        """Turn off massage."""
        await self._send_feature_command(LogicdataCommands.MASSAGE_OFF)
