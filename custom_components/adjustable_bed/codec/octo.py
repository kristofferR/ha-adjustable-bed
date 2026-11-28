"""OCTO 40-delimited packets, escaping, additive checksum and capability records.

Extracted unchanged from the standard OCTO runtime. Cosyworld 1.0.09's 105
frozen literals reproduce byte for byte; its receive/session policy is separate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OctoCapabilityRecord:
    """One complete, immutable advertised OCTO capability record."""

    feature_id: int
    readonly: int
    characteristic: bytes
    value_type: int
    value: bytes

    def with_value(self, value: bytes) -> OctoCapabilityRecord:
        """Return a write record preserving all advertised metadata."""
        return OctoCapabilityRecord(
            self.feature_id,
            self.readonly,
            self.characteristic,
            self.value_type,
            value,
        )


def _encode_capability_value(record: OctoCapabilityRecord, value: bytes) -> list[int]:
    """Build the app's record payload, changing only the value field."""
    return [
        (record.feature_id >> 16) & 0xFF,
        (record.feature_id >> 8) & 0xFF,
        record.feature_id & 0xFF,
        record.readonly,
        len(record.characteristic),
        *record.characteristic,
        record.value_type,
        *value,
    ]


# Maximum encoded OCTO packet size: two delimiters plus the worst case where
# every byte in the five-byte header and 16-bit-length data field is escaped.
# This retains every protocol-valid packet while bounding a missing delimiter.
OCTO_MAX_RESPONSE_BUFFER_SIZE = 2 + (2 * (5 + 0xFFFF))

# Byte stuffing constants
OCTO_PACKET_CHAR = 0x40
OCTO_ESCAPE_CHAR = 0x3C
OCTO_ESCAPE_MAP: dict[int, int] = {
    0x40: 0x01,
    0x3C: 0x02,
    0x4F: 0x03,
    0x41: 0x04,
}
OCTO_UNESCAPE_MAP: dict[int, int] = {v: k for k, v in OCTO_ESCAPE_MAP.items()}


class OctoPacketCodec:
    """Packet encoding and stream decoding shared by setup and runtime."""

    def __init__(self) -> None:
        self._response_buffer = bytearray()
        self.invalid_response_received = False

    def _calculate_checksum(self, packet: list[int]) -> int:
        """Calculate the Octo checksum.

        The checksum is: ((sum_of_bytes XOR 0xff) + 1) & 0xff
        """
        total = sum(packet) & 0xFF
        return ((total ^ 0xFF) + 1) & 0xFF

    def _escape_bytes(self, data: list[int]) -> list[int]:
        """Apply byte stuffing to escape special characters.

        Bytes 0x40, 0x3C, 0x4F, 0x41 are escaped as 0x3C followed by mapped value.
        """
        result: list[int] = []
        for byte in data:
            if byte in OCTO_ESCAPE_MAP:
                result.append(OCTO_ESCAPE_CHAR)
                result.append(OCTO_ESCAPE_MAP[byte])
            else:
                result.append(byte)
        return result

    def _unescape_bytes(self, data: list[int]) -> list[int]:
        """Remove byte stuffing from escaped data.

        Escape sequences (0x3C followed by mapped value) are converted back.
        """
        result: list[int] = []
        i = 0
        while i < len(data):
            if data[i] == OCTO_ESCAPE_CHAR and i + 1 < len(data):
                next_byte = data[i + 1]
                if next_byte in OCTO_UNESCAPE_MAP:
                    result.append(OCTO_UNESCAPE_MAP[next_byte])
                    i += 2
                    continue
            result.append(data[i])
            i += 1
        return result

    def _build_packet(self, command: list[int], data: list[int] | None = None) -> bytes:
        """Build an Octo command packet with byte stuffing.

        Format: [0x40, escaped(cmd[0], cmd[1], len_hi, len_lo, checksum, ...data), 0x40]

        The checksum is calculated on unescaped data, then the entire payload
        (excluding start/end markers) is escaped before transmission.
        """
        data = data or []
        data_len = len(data)

        # Build unescaped packet for checksum calculation
        unescaped = [
            OCTO_PACKET_CHAR,  # Start byte (included in checksum)
            command[0],
            command[1],
            (data_len >> 8) & 0xFF,
            data_len & 0xFF,
            0x00,  # Placeholder for checksum
            *data,
            OCTO_PACKET_CHAR,  # End byte (included in checksum)
        ]

        # Calculate checksum on unescaped data
        unescaped[5] = self._calculate_checksum(unescaped)

        # Escape the payload (everything except start/end markers)
        payload = unescaped[1:-1]  # cmd, len, checksum, data
        escaped_payload = self._escape_bytes(payload)

        # Build final packet with unescaped delimiters
        return bytes([OCTO_PACKET_CHAR, *escaped_payload, OCTO_PACKET_CHAR])

    def _parse_response_packet(self, message: bytes) -> dict[str, list[int]] | None:
        """Parse a response packet from the bed.

        Format: [0x40, escaped(...), 0x40]
        Response checksum is calculated with 0x80 as the first byte on unescaped data.
        """
        if len(message) < 7:
            return None

        if message[0] != OCTO_PACKET_CHAR or message[-1] != OCTO_PACKET_CHAR:
            return None

        # Unescape the payload (everything between start/end markers)
        escaped_payload = list(message[1:-1])
        payload = self._unescape_bytes(escaped_payload)

        if len(payload) < 5:
            return None

        wire_command = [payload[0], payload[1]]
        command = list(wire_command)
        data_len = (payload[2] << 8) + payload[3]
        checksum = payload[4]
        data = payload[5:]

        if len(data) != data_len:
            _LOGGER.debug(
                "Packet data length mismatch: expected %d, got %d",
                data_len,
                len(data),
            )
            return None

        # Verify checksum on unescaped data (response uses 0x80 as first byte)
        check_data = [0x80, *command, payload[2], payload[3], *data]
        expected_checksum = self._calculate_checksum(check_data)
        if checksum != expected_checksum:
            _LOGGER.debug(
                "Checksum mismatch: expected 0x%02x, got 0x%02x",
                expected_checksum,
                checksum,
            )
            return None

        # The low command nibble carries optional destination/source flags.
        # Each present address is exactly six bytes. Reject a truncated field
        # before normalizing so arbitrary bytes cannot be shifted into a
        # capability, PIN, or device-info payload.
        address_flags = command[0] & 0x0C
        address_size = 6 * ((1 if address_flags & 0x08 else 0) + (1 if address_flags & 0x04 else 0))
        if len(data) < address_size:
            _LOGGER.debug(
                "Addressed OCTO packet needs %d address bytes, got %d",
                address_size,
                len(data),
            )
            return None
        if address_size:
            data = data[address_size:]
            command[0] &= 0xF3

        return {"command": command, "data": data, "wire_command": wire_command}

    def _extract_response_packets(self, data: bytes) -> list[dict[str, list[int]]]:
        """Buffer notified values and return every complete, valid response packet.

        BLE notification boundaries are not OCTO packet boundaries. In particular,
        the controller may emit a protocol packet across multiple notifications when
        it does not fit in one notified characteristic value. Raw ``0x40`` bytes
        cannot occur inside a packet because the OCTO serializer escapes them, so
        delimiter pairs provide an unambiguous framing boundary.
        """
        self._response_buffer.extend(data)
        packets: list[dict[str, list[int]]] = []
        buffer = self._response_buffer
        trim_at = 0

        while True:
            start = buffer.find(OCTO_PACKET_CHAR, trim_at)
            if start < 0:
                # Bytes before a start delimiter cannot become part of a later packet.
                trim_at = len(buffer)
                break

            end = buffer.find(OCTO_PACKET_CHAR, start + 1)
            if end < 0:
                # Discard leading noise but retain the incomplete packet.
                trim_at = start
                break

            packet = self._parse_response_packet(bytes(buffer[start : end + 1]))
            if packet is None:
                if end > start + 1:
                    self.invalid_response_received = True
                # The end delimiter may also be the start of the next valid packet.
                # Scan from it without shifting the bytearray on every candidate.
                trim_at = end
                continue

            packets.append(packet)
            trim_at = end + 1

        # Front-delete at most once per callback. Repeated bytearray shifts during
        # malformed-stream resynchronization would otherwise have quadratic cost.
        del buffer[:trim_at]

        if len(buffer) > OCTO_MAX_RESPONSE_BUFFER_SIZE:
            _LOGGER.debug(
                "Discarding oversized incomplete Octo response (%d bytes)",
                len(buffer),
            )
            buffer.clear()

        return packets

    def _extract_feature_value_pair(self, data: list[int]) -> OctoCapabilityRecord | None:
        """Decode a complete advertised capability without discarding metadata."""
        if len(data) < 6:
            return None

        feature_id = (data[0] << 16) + (data[1] << 8) + data[2]
        characteristic_length = data[4]
        value_type_index = 5 + characteristic_length
        if value_type_index >= len(data):
            return None
        return OctoCapabilityRecord(
            feature_id=feature_id,
            readonly=data[3],
            characteristic=bytes(data[5:value_type_index]),
            value_type=data[value_type_index],
            value=bytes(data[value_type_index + 1 :]),
        )
