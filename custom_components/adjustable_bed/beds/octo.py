"""Octo bed controller implementation.

Reverse engineering by _pm, goedh452, Murp, and Brokkert.

References:
- https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790
- https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10

Octo beds use a packet-based BLE protocol with the following format:
[0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]

The checksum is calculated as: ((sum_of_bytes XOR 0xff) + 1) & 0xff

Response packets use 0x80 as the first byte for checksum calculation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    OCTO_CHAR_UUID,
    OCTO_LIGHT_AUTO_OFF_SECONDS,
    OCTO_PIN_KEEPALIVE_INTERVAL,
    OCTO_STAR2_CHAR_UUID,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# Capability fields discovered post-connect (from CAP notifications) that gate
# which entities exist. They are captured into a per-side snapshot at pairing and
# restored when minting a client-free controller for an OFFLINE paired Octo side,
# so its light/RGBW/memory/synchro entities match the live bed without a link.
# Keys are the field names without the leading underscore (JSON-serialisable).
_CAPABILITY_SNAPSHOT_KEYS: tuple[str, ...] = (
    "pin_feature_active",
    "has_pin",
    "pin_locked",
    "has_lights",
    "has_rgbwi",
    "rgbwi_value_type",
    "has_rgb",
    "rgb_value_type",
    "memory_count",
    "discovered_motor_count",
    "has_synchro",
    "remote_lock_active",
    "light_duration_minutes",
    "automatic_light_active",
    "light_sensitivity",
    "capability_records",
    "device_info",
)

# SYSTEM packet bytes for the PIN state machine (command[0] for a from-device
# SYSTEM packet is 0x21 = SYSTEM 0x20 | from-device).
OCTO_SYSTEM_FROM_DEVICE = 0x21
OCTO_SYSTEM_PIN_NEED = 0x40
OCTO_SYSTEM_PIN_SET = 0x41
OCTO_SYSTEM_PIN_CLEARED = 0x42
OCTO_SYSTEM_PIN_AUTH = 0x43
OCTO_SYSTEM_PIN_STATE = 0x43  # data[0] == 1 -> unlocked
OCTO_SYSTEM_PIN_LOCK = 0x44  # delayed one second, then retry PIN
OCTO_SYSTEM_GET_DEVICEINFO = 0x70
OCTO_SYSTEM_GET_CAPS = 0x71
OCTO_SYSTEM_SET_CAPS = 0x72
OCTO_SYSTEM_PING = 0x7F
OCTO_SYSTEM_SET_DEFAULT_CONFIG = 0xAE

OCTO_SESSION_RESPONSE_TIMEOUT = 3.0  # Host-side response bound, not app timing.
OCTO_PIN_ACCEPTANCE_TIMEOUT = 5.0  # Host-side readiness bound, not app timing.
OCTO_PIN_LOCK_RETRY_DELAY_SECONDS = 1.0
OCTO_PROTOCOL_HOLD_INTERVAL_MS = 350
OCTO_CARD_HOLD_MAX_SECONDS = 60


# Motor bit masks
OCTO_MOTOR_HEAD = 0x02
OCTO_MOTOR_LEGS = 0x04
OCTO_MOTOR_3 = 0x08  # Third motor (lumbar/tilt) - for beds with CAP_MOTORCOUNT > 2
OCTO_MOTOR_4 = 0x10  # Fourth motor - for beds with CAP_MOTORCOUNT > 3
OCTO_MOTOR_34 = OCTO_MOTOR_3 | OCTO_MOTOR_4  # CD_MOTOR34 - 4-motor combined step

# CAP_MEMINFO description IDs. Source: accepted analysis of OCTO Smart
# Control 1.03.02; the app resolves these through translation keys md00-md04
# and renders the raw key ("md07") for anything unmapped, so unknown IDs are
# treated as unnamed here instead.
OCTO_MEMORY_DESCRIPTIONS: dict[int, str] = {
    0x01: "Anti-Snore",
    0x02: "Zero-G",
    0x03: "Lordose",
    0x04: "Flat",
}

# Feature IDs
OCTO_FEATURE_MOTORCOUNT = 0x000001  # Number of motors (CAP_MOTORCOUNT)
OCTO_FEATURE_MEMCOUNT = 0x000002  # Number of memory positions
OCTO_FEATURE_MEMINFO = 0x000004  # Per-slot classes and description IDs (CAP_MEMINFO)
OCTO_FEATURE_PIN = 0x000003
OCTO_FEATURE_REMOTE_TEACH = 0x000010
OCTO_FEATURE_REMOTE_CONTROL_LOCK = 0x000011
OCTO_FEATURE_SYNCHRO = 0x000101  # Synchro/linked mode capability (CAP_SYNCHRO)
OCTO_FEATURE_LIGHT = 0x000102
OCTO_FEATURE_LIGHT_DURATION = 0x000103
OCTO_FEATURE_LIGHT_RGBWI = 0x000104
OCTO_FEATURE_LIGHT_AUTO = 0x000105
OCTO_FEATURE_LIGHT_SENSITIVITY = 0x000106
OCTO_FEATURE_LIGHT_RGB = 0x000107
OCTO_FEATURE_END = 0xFFFFFF  # End-of-features sentinel

# Feature discovery timeout
OCTO_FEATURE_TIMEOUT = 5.0


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


# This finite duration is the host-safety bound for a standalone preset button.
# The card uses bounded hold_control calls and releases with STOP.
OCTO_DEFAULT_PRESET_HOLD_MS = 30_000

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


class OctoController(BedController, OctoPacketCodec):
    """Controller for Octo beds."""

    _write_with_response = False
    requires_ordered_discovery = True

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        pin: str = "",
        capability_snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the Octo controller.

        Args:
            coordinator: The bed coordinator.
            pin: Optional PIN for authentication. Required for some Octo beds.
            capability_snapshot: Capabilities captured at pairing, used to mint a
                client-free controller for an OFFLINE paired side (no live
                discovery). Ignored once a live discovery overwrites the fields.
        """
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._pin: str = pin
        self._keepalive_task: asyncio.Task[None] | None = None
        self._keepalive_generation = 0
        self._keepalive_session_generation = 0
        self._pin_resend_task: asyncio.Task[None] | None = None
        self._notifications_started: bool = False  # Track if BLE notifications are active
        OctoPacketCodec.__init__(self)

        # Only a complete CAP_END list replaces the last authoritative state.
        # A reconnect that times out therefore retains prior known entities.
        self._capability_records: dict[int, OctoCapabilityRecord] = {}
        self._pending_capability_records: dict[int, OctoCapabilityRecord] = {}
        self._device_info: dict[str, int] | None = None
        self._ping_event = asyncio.Event()
        self._ping_invalid = False
        self._device_info_event = asyncio.Event()
        self._device_info_invalid = False
        self._capability_response_invalid = False
        self._feature_discovery_event = asyncio.Event()
        self._session_ready = False
        self._session_generation = 0
        self._pin_state_event = asyncio.Event()
        self._pin_state_accepted: bool | None = None
        self._pin_retry_pending = False
        self._pin_retry_authorized = False
        self._pin_retry_auth_sent = False
        self._pin_lock_generation = 0

        # Derived live state. None means it has not yet been authoritatively
        # resolved; completed discovery converts absent capabilities to False.
        self._pin_feature_active: bool | None = None
        self._has_pin: bool | None = None  # None = not yet discovered
        self._pin_locked: bool | None = None
        self._has_lights: bool | None = None  # None = not yet discovered
        self._has_rgbwi: bool = False  # True if CAP_LIGHT_RGBWI (0x000104) detected
        self._rgbwi_value_type: int | None = None  # valueType byte from discovery response
        self._has_rgb: bool = False
        self._rgb_value_type: int | None = None
        self._remote_lock_active: bool = False
        self._light_duration_minutes: int | None = None
        self._light_duration_invalid = False
        self._legacy_assumed_lights = False
        self._legacy_motor_layout_available = False
        self._automatic_light_active: bool = False
        self._light_sensitivity: int | None = None
        self._memory_count: int | None = None  # None = not yet discovered
        # CAP_MEMINFO: slot classes and per-slot description IDs
        self._memory_mem_count: int = 0  # memCount as reported by CAP_MEMINFO
        self._memory_fix_count: int = 0
        self._memory_lock_count: int = 0
        self._memory_descriptions: tuple[int, ...] = ()
        self._discovered_motor_count: int | None = None  # None = not yet discovered
        self._motor_count_invalid = False
        self._has_synchro: bool | None = None  # None = not yet discovered
        self._synchro_active: bool | None = None  # None = unknown
        self._features_loaded: asyncio.Event = asyncio.Event()
        self._features_complete: asyncio.Event = (
            asyncio.Event()
        )  # Set once a complete list has ever been received/restored
        self._capability_records_authoritative = False
        self._pin_sent: bool = False  # True once a PIN packet was written this session

        if capability_snapshot:
            # Legacy snapshots lack the records needed for authoritative entity
            # reconciliation. Preserve their registry entries until live discovery.
            self._apply_capability_snapshot(capability_snapshot)
            self._features_loaded.set()
            self._features_complete.set()
            self._capability_records_authoritative = isinstance(
                capability_snapshot.get("capability_records"), Mapping
            )

        _LOGGER.debug(
            "OctoController initialized (PIN %s%s)",
            "configured" if pin else "not configured",
            ", from capability snapshot" if capability_snapshot else "",
        )

    def capability_snapshot(self) -> dict[str, Any] | None:
        """Return discovered capabilities as a JSON-serialisable snapshot to
        persist for a paired side, or None if feature discovery has not
        COMPLETED.

        Discovery is only complete once the 0xFFFFFF CAP_END sentinel arrives
        (``_features_complete`` is set, see ``_on_notification``) or the
        controller was minted from a prior complete snapshot. The
        ``discover_features`` timeout path fills compatibility defaults (e.g.
        ``_has_lights=True``) but deliberately never sets ``_features_complete``
        — so guarding on it prevents those fallback values from being persisted
        over a real snapshot (or minting a reduced offline profile on reload).
        """
        if not self.controller_entity_discovery_complete:
            return None
        snap = {
            key: (
                {
                    str(feature_id): {
                        "readonly": record.readonly,
                        "characteristic": list(record.characteristic),
                        "value_type": record.value_type,
                        "value": list(record.value),
                    }
                    for feature_id, record in self._capability_records.items()
                }
                if key == "capability_records"
                else self._device_info
                if key == "device_info"
                else getattr(self, f"_{key}")
            )
            for key in _CAPABILITY_SNAPSHOT_KEYS
        }
        if all(value is None or value is False for value in snap.values()):
            return None
        return snap

    @property
    def controller_entity_discovery_complete(self) -> bool:
        """Return whether current, complete capability records are authoritative."""
        return self._features_complete.is_set() and self._capability_records_authoritative

    @property
    def _motor_control_surface_ready(self) -> bool:
        """Allow known layouts from snapshots or a successful legacy fallback."""
        return self.effective_motor_count is not None and (
            self._features_complete.is_set() or self._legacy_motor_layout_available
        )

    @property
    def has_dynamic_controller_entities(self) -> bool:
        """Octo capabilities are authoritative only after the live sentinel."""
        return True

    def _apply_capability_snapshot(self, snap: Mapping[str, Any]) -> None:
        """Restore capability fields from a persisted snapshot (offline mint)."""
        for key in _CAPABILITY_SNAPSHOT_KEYS:
            if key in snap:
                value = snap[key]
                if key == "capability_records" and isinstance(value, Mapping):
                    records: dict[int, OctoCapabilityRecord] = {}
                    for feature_id, raw in value.items():
                        if not isinstance(raw, Mapping):
                            continue
                        try:
                            records[int(feature_id)] = OctoCapabilityRecord(
                                feature_id=int(feature_id),
                                readonly=int(raw["readonly"]),
                                characteristic=bytes(raw["characteristic"]),
                                value_type=int(raw["value_type"]),
                                value=bytes(raw["value"]),
                            )
                        except KeyError, TypeError, ValueError:
                            continue
                    self._capability_records = records
                    self._pending_capability_records = dict(records)
                elif key == "device_info":
                    self._device_info = dict(value) if isinstance(value, Mapping) else None
                else:
                    setattr(self, f"_{key}", value)
        if self._capability_records:
            self._apply_capability_records(self._capability_records)

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OCTO_CHAR_UUID

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object] | None:
        """Redact PIN authentication packets from logs and support bundles."""
        if command[:3] in {
            bytes((OCTO_PACKET_CHAR, 0x20, OCTO_SYSTEM_PIN_STATE)),
        } or command[:4] == bytes((OCTO_PACKET_CHAR, 0x20, 0x3C, 0x04)):
            return {
                "hex": "**REDACTED**",
                "length": len(command),
                "ascii_preview": None,
            }
        return super()._format_command_trace_payload(command)

    def _handle_feature_response(self, data: list[int]) -> None:
        """Process feature data from a 0x21 0x71 response."""
        if self._capability_response_invalid or self.invalid_response_received:
            self._capability_response_invalid = True
            return
        record = self._extract_feature_value_pair(data)
        if record is None:
            self._capability_response_invalid = True
            _LOGGER.debug("Could not extract feature from data: %s", data)
            return

        if record.feature_id == OCTO_FEATURE_END:
            _LOGGER.debug("Feature discovery complete (received 0xFFFFFF sentinel)")
            self._capability_records = dict(self._pending_capability_records)
            self._apply_capability_records(self._capability_records)
            self._features_complete.set()
            self._capability_records_authoritative = True
            self._legacy_motor_layout_available = False
            self._feature_discovery_event.set()
            self._publish_capability_state()
            return

        self._pending_capability_records[record.feature_id] = record
        _LOGGER.debug(
            "Feature 0x%06x: characteristic=%s valueType=0x%02x value=%s",
            record.feature_id,
            record.characteristic.hex(),
            record.value_type,
            record.value.hex(),
        )
        self._features_loaded.set()

    def _apply_capability_records(
        self,
        records: Mapping[int, OctoCapabilityRecord],
        *,
        preserve_notification_pin_state: bool = False,
    ) -> None:
        """Derive supported controls only from the latest complete record set."""
        if not preserve_notification_pin_state:
            self._pin_feature_active = None
            self._has_pin = None
            self._pin_locked = None
        self._has_lights = False
        self._has_rgbwi = False
        self._rgbwi_value_type = None
        self._has_rgb = False
        self._rgb_value_type = None
        self._memory_count = 0
        self._memory_mem_count = 0
        self._memory_fix_count = 0
        self._memory_lock_count = 0
        self._memory_descriptions = ()
        self._discovered_motor_count = None
        self._motor_count_invalid = False
        self._has_synchro = False
        self._synchro_active = None
        self._remote_lock_active = False
        self._light_duration_minutes = None
        self._light_duration_invalid = False
        self._automatic_light_active = False
        self._light_sensitivity = None

        if not preserve_notification_pin_state:
            pin = records.get(OCTO_FEATURE_PIN)
            if pin is not None:
                self._pin_feature_active = bool(pin.characteristic and pin.characteristic[0] == 1)
                if self._pin_feature_active and len(pin.value) >= 2:
                    self._has_pin = pin.value[0] == 1
                    self._pin_locked = pin.value[1] != 1

        motor_count = records.get(OCTO_FEATURE_MOTORCOUNT)
        if motor_count is not None:
            if motor_count.characteristic and 1 <= motor_count.characteristic[0] <= 4:
                self._discovered_motor_count = motor_count.characteristic[0]
            else:
                self._motor_count_invalid = True

        memory_info = records.get(OCTO_FEATURE_MEMINFO)
        memory_info_count: int | None = None
        if memory_info is not None and len(memory_info.characteristic) == 3:
            memory_info_count = memory_info.characteristic[0]
            self._apply_meminfo(memory_info)

        memory_count = records.get(OCTO_FEATURE_MEMCOUNT)
        if memory_info_count is not None:
            self._memory_count = memory_info_count
        elif memory_count is not None and memory_count.characteristic:
            self._memory_count = memory_count.characteristic[0]

        synchro = records.get(OCTO_FEATURE_SYNCHRO)
        self._has_synchro = bool(
            synchro and synchro.characteristic[:1] == b"\x01" and len(synchro.value) == 1
        )
        if self._has_synchro and synchro is not None and synchro.value:
            self._synchro_active = synchro.value[0] == 1

        light = records.get(OCTO_FEATURE_LIGHT)
        rgbwi = records.get(OCTO_FEATURE_LIGHT_RGBWI)
        rgb = records.get(OCTO_FEATURE_LIGHT_RGB)
        self._has_rgbwi = bool(
            rgbwi and rgbwi.characteristic[:1] == b"\x01" and len(rgbwi.value) == 5
        )
        self._rgbwi_value_type = rgbwi.value_type if self._has_rgbwi and rgbwi else None
        self._has_rgb = bool(rgb and rgb.characteristic[:1] == b"\x01" and len(rgb.value) == 3)
        self._rgb_value_type = rgb.value_type if self._has_rgb and rgb else None
        self._has_lights = bool(
            (light and light.characteristic[:1] == b"\x01" and len(light.value) == 1)
            or self._has_rgbwi
            or self._has_rgb
        )
        self._legacy_assumed_lights = False

        remote_lock = records.get(OCTO_FEATURE_REMOTE_CONTROL_LOCK)
        self._remote_lock_active = bool(
            remote_lock
            and remote_lock.characteristic[:1] == b"\x01"
            and len(remote_lock.value) == 1
            and remote_lock.value[0] == 1
        )
        duration = records.get(OCTO_FEATURE_LIGHT_DURATION)
        if duration and duration.characteristic[:1] == b"\x01":
            if len(duration.value) != 2:
                self._light_duration_invalid = True
            else:
                value = int.from_bytes(duration.value, "big")
                if 0 <= value <= 60:
                    self._light_duration_minutes = value
                else:
                    self._light_duration_invalid = True
        automatic = records.get(OCTO_FEATURE_LIGHT_AUTO)
        self._automatic_light_active = bool(
            automatic
            and automatic.characteristic[:1] == b"\x01"
            and len(automatic.value) == 1
            and automatic.value[0] == 1
        )
        sensitivity = records.get(OCTO_FEATURE_LIGHT_SENSITIVITY)
        if (
            sensitivity
            and sensitivity.characteristic[:1] == b"\x01"
            and len(sensitivity.value) == 2
        ):
            value = int.from_bytes(sensitivity.value, "big")
            if value in (6, 35, 85):
                self._light_sensitivity = value

        if (
            self._discovered_motor_count is not None
            and self._discovered_motor_count != self._coordinator.motor_count
        ):
            _LOGGER.info(
                "OCTO advertises %d motors; effective runtime layout is %d",
                self._discovered_motor_count,
                self.effective_motor_count,
            )

    def _apply_meminfo(self, record: OctoCapabilityRecord) -> None:
        """Apply a valid MEMINFO class block and complete optional label vector."""
        if len(record.characteristic) != 3:
            return
        mem_count, fix_count, lock_count = record.characteristic
        # The app clamps both class counts into the slot range before use.
        fix_count = min(fix_count, mem_count)
        lock_count = min(lock_count, mem_count - fix_count)

        self._memory_mem_count = mem_count
        self._memory_fix_count = fix_count
        self._memory_lock_count = lock_count
        self._memory_descriptions = tuple(record.value) if len(record.value) == mem_count else ()

        _LOGGER.info(
            "Memory info feature detected: %d slots (%d fixed, %d locked), descriptions=%s",
            mem_count,
            fix_count,
            lock_count,
            list(self._memory_descriptions) or "not reported",
        )

    def _publish_capability_state(self) -> None:
        """Publish keys consumed by existing selects, switches and lights."""
        light = self._capability_records.get(OCTO_FEATURE_LIGHT)
        light_on = (
            light.value[0] == 1
            if light is not None and light.characteristic[:1] == b"\x01" and len(light.value) == 1
            else None
        )
        self.forward_controller_state_updates(
            {
                "automatic_light": self._automatic_light_active,
                "synchro_mode": self._synchro_active,
                "remote_control_lock": self._remote_lock_active,
                "octo_light_duration": self._light_duration_minutes,
                "octo_light_sensitivity": (
                    str(self._light_sensitivity) if self._light_sensitivity is not None else None
                ),
                "under_bed_lights_on": light_on,
                "under_bed_lights_rgb": self._rgb_value(),
                "under_bed_lights_rgbw": self._rgbw_value(),
                "light_intensity": self._rgbwi_intensity(),
            }
        )

    def _rgb_value(self) -> tuple[int, int, int] | None:
        record = self._capability_records.get(OCTO_FEATURE_LIGHT_RGB)
        if self._has_rgb and record is not None and len(record.value) == 3:
            return cast(tuple[int, int, int], tuple(record.value))
        return None

    def _rgbw_value(self) -> tuple[int, int, int, int] | None:
        record = self._capability_records.get(OCTO_FEATURE_LIGHT_RGBWI)
        if self._has_rgbwi and record is not None and len(record.value) == 5:
            return cast(tuple[int, int, int, int], tuple(record.value[:4]))
        return None

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int] | None:
        """Return the current independent RGB record value, if active."""
        return self._rgb_value()

    @property
    def current_light_rgbw_color(self) -> tuple[int, int, int, int] | None:
        """Return the current independent RGBW channels, if active."""
        return self._rgbw_value()

    def _rgbwi_intensity(self) -> int | None:
        record = self._capability_records.get(OCTO_FEATURE_LIGHT_RGBWI)
        if self._has_rgbwi and record is not None and len(record.value) == 5:
            return record.value[4]
        return None

    @property
    def light_intensity(self) -> int | None:
        """Return the intensity byte from the RGBWI record."""
        return self._rgbwi_intensity()

    def _memory_slot_class(self, memory_num: int) -> str:
        """Return "standard", "fix" or "lock" for a 1-based memory slot.

        Classes partition the slot range contiguously with standard slots at
        the low indices: standard, then fix, then lock.
        """
        # CAP_MEMINFO is optional. Without a valid record we know nothing about
        # slot protection, and must not infer any: treating unknown as locked
        # would hide every Save button on a bed that simply never reports it.
        if self._memory_mem_count == 0:
            return "standard"

        # Partition on the count this MEMINFO record carried, not on
        # CAP_MEMCOUNT: the two capabilities arrive in whatever order the bed
        # sends them, and using a count of 0 here would drive lock_start
        # negative and classify every slot as locked.
        mem_count = self._memory_mem_count
        lock_start = mem_count - self._memory_lock_count
        fix_start = lock_start - self._memory_fix_count
        index = memory_num - 1
        if index >= lock_start:
            return "lock"
        if index >= fix_start:
            return "fix"
        return "standard"

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        """Return per-slot names from the CAP_MEMINFO description IDs."""
        return tuple(
            OCTO_MEMORY_DESCRIPTIONS.get(description) for description in self._memory_descriptions
        )

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        """Return False for locked slots, which the bed will not let us save."""
        if not self.supports_memory_programming:
            return False
        return self._memory_slot_class(memory_num) != "lock"

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle BLE notifications from the bed."""
        _LOGGER.debug("Received notification: %s", data.hex())
        self.forward_raw_notification(OCTO_CHAR_UUID, bytes(data))

        packets = self._extract_response_packets(bytes(data))
        if self.invalid_response_received:
            self._capability_response_invalid = True

        for packet in packets:
            command = packet["command"]
            packet_data = packet["data"]

            # Packet parsing already checked the checksum, declared length and
            # optional six-byte address fields. A valid ping carries no payload.
            if command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_PING]:
                self._ping_event.set()
                if packet_data:
                    self._ping_invalid = True

            if command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_GET_DEVICEINFO]:
                self._device_info_event.set()
                if len(packet_data) != 10:
                    self._device_info_invalid = True
                else:
                    self._device_info = {
                        "cid": int.from_bytes(packet_data[0:4], "big"),
                        "firmware": int.from_bytes(packet_data[4:6], "big"),
                        "pid": int.from_bytes(packet_data[6:8], "big"),
                        "hardware": int.from_bytes(packet_data[8:10], "big"),
                    }

            # Handle capability response (0x21 0x71).
            if command == [OCTO_SYSTEM_FROM_DEVICE, OCTO_SYSTEM_GET_CAPS]:
                self._handle_feature_response(packet_data)

            # SYSTEM packets from the device (command[0] == 0x21): PIN state machine.
            if command[0] == OCTO_SYSTEM_FROM_DEVICE:
                self._handle_pin_notification(command[1], list(packet_data))

    def _handle_pin_notification(self, command_byte: int, data: list[int]) -> None:
        """Track the live PIN state and honor the app's delayed lock challenge."""
        if command_byte in {
            OCTO_SYSTEM_PIN_NEED,
            OCTO_SYSTEM_PIN_SET,
            OCTO_SYSTEM_PIN_CLEARED,
            OCTO_SYSTEM_PIN_STATE,
            OCTO_SYSTEM_PIN_LOCK,
        }:
            self._pin_feature_active = True
        if command_byte == OCTO_SYSTEM_PIN_NEED:
            self._has_pin = False
            self._pin_locked = False
        elif command_byte == OCTO_SYSTEM_PIN_SET:
            self._has_pin = True
            if self._pin_locked is None:
                self._pin_locked = False
        elif command_byte == OCTO_SYSTEM_PIN_CLEARED:
            self._has_pin = False
            self._pin_locked = False
        elif command_byte == OCTO_SYSTEM_PIN_STATE:
            # A state response supersedes an older pending lock retry.
            self._pin_lock_generation += 1
            retry_task = self._pin_resend_task
            retry_auth_in_flight = self._pin_retry_auth_sent
            self._pin_resend_task = None
            self._pin_retry_pending = False
            self._pin_retry_authorized = False
            self._pin_retry_auth_sent = False
            if (
                retry_task is not None
                and retry_task is not asyncio.current_task()
                and not retry_auth_in_flight
            ):
                retry_task.cancel()
            self._pin_state_accepted = bool(data) and data[0] == 1
            self._pin_state_event.set()
            self._pin_locked = not self._pin_state_accepted
            if self._pin_state_accepted:
                self._has_pin = True
        elif command_byte == OCTO_SYSTEM_PIN_LOCK:
            _LOGGER.debug("Octo bed requested PIN re-authentication (PIN_LOCK)")
            self._pin_locked = True
            self._pin_sent = False
            self._pin_state_accepted = None
            self._pin_state_event.clear()
            self._schedule_pin_resend()
        else:
            return
        self._publish_pin_state()

    def _publish_pin_state(self) -> None:
        self.forward_controller_state_updates(
            {
                "octo_pin_feature_active": self._pin_feature_active,
                "octo_pin_set": self._has_pin,
                "octo_pin_locked": self._pin_locked,
            }
        )

    async def _retry_pin_after_lock(self, generation: int) -> None:
        await asyncio.sleep(OCTO_PIN_LOCK_RETRY_DELAY_SECONDS)
        if generation != self._pin_lock_generation or not self._session_ready:
            return
        self._pin_locked = True
        self._publish_pin_state()
        # Stop an in-flight bounded hold before queuing authentication, so a
        # card's one-minute host safety window cannot reserve the command lane.
        try:
            await self._coordinator.async_stop_command()
        except (BleakError, ConnectionError, TimeoutError) as err:
            _LOGGER.debug("OCTO PIN recovery STOP failed: %s", err)
            return
        if generation != self._pin_lock_generation or not self._session_ready:
            return
        self._pin_retry_authorized = True

        async def authenticate(_controller: BedController) -> None:
            return

        try:
            await self._coordinator.async_execute_controller_command(
                authenticate,
                cancel_running=False,
                skip_disconnect=True,
            )
        except (ConnectionError, PermissionError, TimeoutError) as err:
            _LOGGER.debug("OCTO PIN retry did not regain access: %s", err)
        finally:
            if self._pin_resend_task is asyncio.current_task():
                self._pin_resend_task = None
            self._pin_retry_auth_sent = False

    def _schedule_pin_resend(self) -> None:
        """Retry once after the app's one-second local lock transition."""
        if self._pin_resend_task is not None and not self._pin_resend_task.done():
            return
        self._pin_lock_generation += 1
        self._pin_retry_pending = True
        self._pin_retry_authorized = False
        self._pin_retry_auth_sent = False
        self._pin_resend_task = asyncio.create_task(
            self._retry_pin_after_lock(self._pin_lock_generation)
        )

    def on_disconnect(self) -> None:
        """Invalidate session-owned PIN retry work when the BLE link ends."""
        self._session_ready = False
        self._session_generation += 1
        self._keepalive_generation += 1
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        self._pin_state_accepted = None
        self._pin_state_event.set()
        self._pin_retry_pending = False
        self._pin_retry_authorized = False
        self._pin_retry_auth_sent = False
        self._pin_lock_generation += 1
        if self._pin_resend_task is not None:
            self._pin_resend_task.cancel()
            self._pin_resend_task = None

    async def _write_octo_command(
        self,
        command: list[int],
        data: list[int] | None = None,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Build and write an Octo command packet."""
        command_key = tuple(command[:2])
        pre_session_commands = {
            (0x20, OCTO_SYSTEM_PING),
            (0x20, OCTO_SYSTEM_GET_DEVICEINFO),
            (0x20, OCTO_SYSTEM_GET_CAPS),
            (0x02, 0x73),  # Safety STOP remains available during teardown.
        }
        if not self._session_ready and command_key not in pre_session_commands:
            raise ConnectionError("OCTO session discovery is not complete")
        if (
            self._session_ready
            and not self.normal_controls_available
            and command_key
            not in {
                (0x20, OCTO_SYSTEM_PING),
                (0x20, OCTO_SYSTEM_PIN_AUTH),
                (0x20, OCTO_SYSTEM_PIN_STATE),
                (0x02, 0x73),
            }
        ):
            raise PermissionError("OCTO PIN must be unlocked before normal controls are used")
        packet = self._build_packet(command, data)
        await self.write_command(packet, repeat_count, repeat_delay_ms, cancel_event)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for notifications.

        Octo beds don't support position notifications, but we use notifications
        for feature discovery responses.
        """
        self._notify_callback = callback
        if self.client is not None and self.client.is_connected:
            self._response_buffer.clear()
            try:
                async with self._ble_lock:
                    await self.client.start_notify(OCTO_CHAR_UUID, self._on_notification)
                self._notifications_started = True
                _LOGGER.debug("Started Octo notifications for feature discovery")
            except BleakError as err:
                _LOGGER.debug("Could not start notifications: %s", err)

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        self._notifications_started = False
        self._response_buffer.clear()
        if self.client is not None and self.client.is_connected:
            with contextlib.suppress(BleakError):
                async with self._ble_lock:
                    await self.client.stop_notify(OCTO_CHAR_UUID)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        pass

    @property
    def requires_pin(self) -> bool:
        """Whether an active, set PIN currently locks normal controls."""
        if self._pin_feature_active is False or self._has_pin is False:
            return False
        return bool(self._pin_feature_active and self._has_pin and self._pin_locked)

    @property
    def normal_controls_available(self) -> bool:
        """Fail closed while an active PIN capability has unknown lock state."""
        if self._pin_feature_active is not True or self._has_pin is False:
            return True
        return self._has_pin is True and self._pin_locked is False

    @property
    def is_octo_smart_control(self) -> bool:
        """Mark this Standard OCTO controller for its dynamic entity contracts."""
        return True

    @property
    def pin_locked_without_pin(self) -> bool | None:
        """Return whether the bed is PIN locked with no PIN configured.

        Return None until an authoritative PIN record or PIN notification exists.
        """
        if self._pin:
            return False
        if self._pin_feature_active is None or self._has_pin is None or self._pin_locked is None:
            return None
        return self._pin_feature_active and self._has_pin and self._pin_locked

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        """Report what connect-time capability discovery resolved to.

        ``None`` means the capability was never reported. When
        ``feature_discovery_complete`` is False, discovery timed out and the
        non-None booleans are the fallback defaults from ``discover_features()``
        rather than device-reported state. The configured PIN is never included.
        """
        return {
            "feature_discovery_complete": self.controller_entity_discovery_complete,
            "capability_records_authoritative": self._capability_records_authoritative,
            "session_ready": self._session_ready,
            "device_info": self._device_info,
            "capability_records": {
                f"{feature_id:06x}": {
                    "readonly": record.readonly,
                    "characteristic": list(record.characteristic),
                    "value_type": record.value_type,
                    "value": list(record.value),
                }
                for feature_id, record in self._capability_records.items()
            },
            "pin_feature_active": self._pin_feature_active,
            "has_pin": self._has_pin,
            "pin_locked": self._pin_locked,
            "pin_configured": bool(self._pin),
            "pin_sent": self._pin_sent,
            "pin_locked_without_pin": self.pin_locked_without_pin,
            "has_lights": self._has_lights,
            "has_rgbwi": self._has_rgbwi,
            "has_rgb": self._has_rgb,
            "memory_count": self._memory_count,
            "memory_fix_count": self._memory_fix_count,
            "memory_lock_count": self._memory_lock_count,
            "memory_slot_names": list(self.memory_slot_names),
            "discovered_motor_count": self._discovered_motor_count,
            "motor_count_invalid": self._motor_count_invalid,
            "has_synchro": self._has_synchro,
            "synchro_active": self._synchro_active,
            "remote_lock_active": self._remote_lock_active,
            "light_duration_minutes": self._light_duration_minutes,
            "automatic_light_active": self._automatic_light_active,
            "light_sensitivity": self._light_sensitivity,
            "pin_retry_pending": (
                self._pin_resend_task is not None and not self._pin_resend_task.done()
            ),
        }

    @property
    def _is_one_motor_lift(self) -> bool:
        """Return whether this controller represents an OCTO one-motor lift."""
        return self.effective_motor_count == 1

    @property
    def effective_motor_count(self) -> int | None:
        """Return the explicit override or a valid discovered layout.

        ``None`` means a complete capability list contained a malformed motor
        count and Auto cannot safely choose an actuator layout.
        """
        override = self._coordinator.entry.data.get(CONF_OCTO_MOTOR_COUNT_OVERRIDE)
        if override == "auto":
            if self._motor_count_invalid:
                return None
            return self._discovered_motor_count or self._rtv_fallback_motor_count()
        if isinstance(override, str) and override.isascii() and override.isdecimal():
            override = int(override)
        if type(override) is int and 1 <= override <= 4:
            return override
        configured = self._coordinator.motor_count
        if self._motor_count_invalid:
            if override is None and configured != 2 and 1 <= configured <= 4:
                return configured
            return None
        # Existing non-default values were explicit user selections before the
        # OCTO-only Auto option existed. Preserve those choices across upgrades.
        if override is None and configured != 2 and 1 <= configured <= 4:
            return configured
        return self._discovered_motor_count or self._rtv_fallback_motor_count(configured)

    def _rtv_fallback_motor_count(self, default: int | None = None) -> int:
        """Use the historical RTV lift layout only when no motor count was advertised."""
        name = self._coordinator.ble_device_name
        if isinstance(name, str) and name.strip().lower().startswith("rtv"):
            return 1
        return self._coordinator.motor_count if default is None else default

    @property
    def supports_lights(self) -> bool:
        """Whether current records or the legacy missing-list fallback expose lights."""
        if self._has_lights is not None:
            return self._has_lights
        return not self.controller_entity_discovery_complete

    @property
    def supports_light_color_control(self) -> bool:
        """Return True if either currently active color record is advertised."""
        return bool(self.supported_color_modes & {"rgb", "rgbw"})

    @property
    def supported_color_mode(self) -> str | None:
        """Choose the current OCTO color mode, preserving RGBWI preference."""
        if self._has_rgbwi:
            return "rgbw"
        if self._has_rgb:
            return "rgb"
        return None

    @property
    def supported_color_modes(self) -> frozenset[str]:
        """Return exactly the active RGB/RGBW modes, or on/off by itself."""
        modes = set()
        rgb = self._capability_records.get(OCTO_FEATURE_LIGHT_RGB)
        rgbwi = self._capability_records.get(OCTO_FEATURE_LIGHT_RGBWI)
        if self._has_rgb and rgb is not None and rgb.readonly == 0:
            modes.add("rgb")
        if self._has_rgbwi and rgbwi is not None and rgbwi.readonly == 0:
            modes.add("rgbw")
        if modes:
            return frozenset(modes)
        if self.supports_discrete_light_control:
            return frozenset(("onoff",))
        return frozenset()

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int] | None:
        """Return the current RGB record without deriving it from RGBWI."""
        rgb = self._rgb_value()
        if rgb is not None:
            return rgb
        if self._has_rgb:
            return (255, 255, 255)
        return None

    @property
    def supports_explicit_light_on_control(self) -> bool:
        """Return True if bed has a dedicated light-on command."""
        return self.supports_discrete_light_control

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return whether the advertised record or legacy fallback supports on/off."""
        record = self._capability_records.get(OCTO_FEATURE_LIGHT)
        return bool(
            record is not None
            and record.characteristic[:1] == b"\x01"
            and record.readonly == 0
            and len(record.value) == 1
        ) or (self._legacy_assumed_lights and self.supports_lights)

    @property
    def supports_light_toggle_control(self) -> bool:
        """Return whether an active writable light state can be toggled."""
        return self.supports_discrete_light_control

    @property
    def supports_reset_defaults(self) -> bool:
        """Require the explicitly confirmed OCTO reset service."""
        return False

    @property
    def light_auto_off_seconds(self) -> int | None:
        """Use advertised minutes, or the historical five-minute default if absent."""
        minutes = self._light_duration_minutes
        if not self.supports_lights or self._light_duration_invalid:
            return None
        if minutes is None:
            return OCTO_LIGHT_AUTO_OFF_SECONDS
        return minutes * 60 if minutes > 0 else None

    @property
    def legacy_light_fallback(self) -> bool:
        """Whether absent capability discovery activated the field-compatible light path."""
        return (
            self._legacy_assumed_lights
            and self._session_ready
            and not self.controller_entity_discovery_complete
        )

    def on_light_auto_off(self) -> None:
        """Publish the expected light expiry without sending a bed command."""
        if self.legacy_light_fallback:
            self.forward_controller_state_updates({"under_bed_lights_on": False})
            return
        if not self.controller_entity_discovery_complete:
            return
        record = self._capability_records.get(OCTO_FEATURE_LIGHT)
        if (
            record is not None
            and record.characteristic[:1] == b"\x01"
            and len(record.value) == 1
            and record.value != b"\x00"
        ):
            self._capability_records[OCTO_FEATURE_LIGHT] = record.with_value(b"\x00")
        self._publish_capability_state()

    @property
    def supports_automatic_light(self) -> bool:
        record = self._capability_records.get(OCTO_FEATURE_LIGHT_AUTO)
        return bool(
            record
            and record.readonly == 0
            and record.characteristic[:1] == b"\x01"
            and len(record.value) == 1
        )

    @property
    def supports_remote_control_lock(self) -> bool:
        record = self._capability_records.get(OCTO_FEATURE_REMOTE_CONTROL_LOCK)
        return bool(
            record
            and record.readonly == 0
            and record.characteristic[:1] == b"\x01"
            and len(record.value) == 1
        )

    @property
    def supports_light_duration(self) -> bool:
        record = self._capability_records.get(OCTO_FEATURE_LIGHT_DURATION)
        return self._light_duration_minutes is not None and bool(record and record.readonly == 0)

    @property
    def supports_light_sensitivity(self) -> bool:
        record = self._capability_records.get(OCTO_FEATURE_LIGHT_SENSITIVITY)
        return self._light_sensitivity is not None and bool(record and record.readonly == 0)

    @property
    def supports_remote_teach(self) -> bool:
        record = self._capability_records.get(OCTO_FEATURE_REMOTE_TEACH)
        return bool(
            record
            and record.readonly == 1
            and record.characteristic[:1] == b"\x01"
            and record.value_type == 1
            and record.value == b"\x01"
        )

    def _capability_active(self, feature_id: int) -> bool:
        record = self._capability_records.get(feature_id)
        return bool(record and record.characteristic[:1] == b"\x01")

    async def _write_capability_value(self, feature_id: int, value: bytes) -> None:
        """Write only the mutable value, preserving the exact advertised record."""
        if not self._session_ready:
            raise ConnectionError("OCTO session discovery is not complete")
        if not self.normal_controls_available:
            raise PermissionError("OCTO PIN must be unlocked before changing this setting")
        record = self._capability_records.get(feature_id)
        if record is None or record.characteristic[:1] != b"\x01":
            raise ValueError(f"OCTO capability {feature_id:06x} is not active")
        if record.readonly != 0:
            raise PermissionError(f"OCTO capability {feature_id:06x} is read-only")
        if len(value) != len(record.value):
            raise ValueError(
                f"OCTO capability {feature_id:06x} requires {len(record.value)} value bytes"
            )
        updated = record.with_value(value)
        await self._write_octo_command(
            [0x20, OCTO_SYSTEM_SET_CAPS], _encode_capability_value(updated, value)
        )
        self._capability_records[feature_id] = updated
        self._apply_capability_records(
            self._capability_records, preserve_notification_pin_state=True
        )
        self._publish_capability_state()

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        """Expose app memory slots and the active remote-teach action."""
        specs: list[ControllerButtonSpec] = []
        if self.supports_memory_presets:
            for slot in range(1, self.memory_slot_count + 1):
                label = (
                    self.memory_slot_names[slot - 1]
                    if slot <= len(self.memory_slot_names)
                    else None
                )
                label = label or f"Memory {slot}"
                hold = ControllerHoldSpec(
                    control=f"memory_{slot}", start_delay_ms=100, release_delay_ms=200
                )
                specs.append(
                    ControllerButtonSpec(
                        key=f"preset_memory_{slot}",
                        name=label,
                        icon=f"mdi:numeric-{slot}-box" if slot <= 9 else "mdi:bookmark-outline",
                        press_fn=lambda ctrl, slot=slot: ctrl.preset_memory(slot),
                        translation_key=f"preset_memory_{slot}",
                        hold=hold,
                    )
                )
                if self.is_memory_slot_programmable(slot):
                    specs.append(
                        ControllerButtonSpec(
                            key=f"program_memory_{slot}",
                            name=f"Save {label}",
                            icon="mdi:content-save",
                            press_fn=lambda ctrl, slot=slot: ctrl.program_memory(slot),
                            translation_key=f"program_memory_{slot}",
                        )
                    )
        if self.supports_remote_teach:
            specs.append(
                ControllerButtonSpec(
                    key="octo_remote_teach",
                    name="Teach remote",
                    icon="mdi:remote",
                    press_fn=lambda ctrl: cast(OctoController, ctrl).teach_remote(),
                )
            )
        if self.effective_motor_count is not None and self.effective_motor_count >= 3:
            specs.append(
                ControllerButtonSpec(
                    key="octo_all_down",
                    name="All motors down",
                    icon="mdi:arrow-collapse-down",
                    translation_key="octo_all_down",
                    press_fn=lambda ctrl: cast(OctoController, ctrl).preset_flat(),
                    hold=ControllerHoldSpec(
                        control="all_down", start_delay_ms=100, release_delay_ms=100
                    ),
                )
            )
        return tuple(specs)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        """Return typed motor-direction and memory-slot hold controls."""
        count = self.effective_motor_count
        controls: list[str] = []
        if count == 1:
            controls.extend(("tv_lift_up", "tv_lift_down"))
        elif count == 2:
            controls.extend(
                ("back_up", "back_down", "legs_up", "legs_down", "back_legs_up", "back_legs_down")
            )
        elif count == 3:
            controls.extend(
                (
                    "back_up",
                    "back_down",
                    "legs_up",
                    "legs_down",
                    "motor_3_up",
                    "motor_3_down",
                    "back_legs_up",
                    "back_legs_down",
                    "all_down",
                )
            )
        elif count == 4:
            controls.extend(
                (
                    "back_up",
                    "back_down",
                    "legs_up",
                    "legs_down",
                    "motor_3_up",
                    "motor_3_down",
                    "motor_4_up",
                    "motor_4_down",
                    "motor_34_up",
                    "motor_34_down",
                    "back_legs_up",
                    "back_legs_down",
                    "all_down",
                )
            )
        if self.supports_memory_presets:
            controls.extend(f"memory_{slot}" for slot in range(1, self.memory_slot_count + 1))
        return tuple(controls)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported OCTO held control: {control}")
        if (
            isinstance(duration_ms, bool)
            or not 100 <= duration_ms <= OCTO_CARD_HOLD_MAX_SECONDS * 1000
        ):
            raise ValueError("OCTO hold duration must be 100..60000 milliseconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Stream a selected motor or memory command, then send a fresh STOP."""
        self.validate_hold_control(control, duration_ms)
        cancel_event = self._coordinator.cancel_command
        memory_slot = None
        if control.startswith("memory_"):
            memory_slot = int(control.removeprefix("memory_"))
            command = [0x02, 0x72]
            data = [memory_slot - 1]
        else:
            if control == "all_down":
                motor_bits, direction = self._all_motors_mask, "down"
            else:
                motor_bits, direction = self._held_motor_command(control)
            command = [0x02, 0x70 if direction == "up" else 0x71]
            data = [motor_bits]

        writes = max(1, -(-duration_ms // OCTO_PROTOCOL_HOLD_INTERVAL_MS))
        remaining_ms = duration_ms - (writes - 1) * OCTO_PROTOCOL_HOLD_INTERVAL_MS
        try:
            await self._write_octo_command(
                command,
                data,
                repeat_count=writes,
                repeat_delay_ms=OCTO_PROTOCOL_HOLD_INTERVAL_MS,
                cancel_event=cancel_event,
            )
            if not cancel_event.is_set() and remaining_ms > 0:
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=remaining_ms / 1000)
                except TimeoutError:
                    pass
        finally:
            await self._stop_motors()

    @staticmethod
    def _held_motor_command(control: str) -> tuple[int, str]:
        """Map a typed motor/direction key to its proven OCTO mask."""
        mappings = {
            "back": OCTO_MOTOR_HEAD,
            "legs": OCTO_MOTOR_LEGS,
            "tv_lift": OCTO_MOTOR_HEAD,
            "motor_3": OCTO_MOTOR_3,
            "motor_4": OCTO_MOTOR_4,
            "motor_34": OCTO_MOTOR_34,
            "back_legs": OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS,
        }
        try:
            motor, direction = control.rsplit("_", 1)
            return mappings[motor], direction
        except (KeyError, ValueError) as err:
            raise ValueError(f"Unsupported OCTO motor hold: {control}") from err

    def controller_button_available(self, key: str) -> bool:
        """Gate dynamic OCTO actions on the complete capability and PIN state."""
        if not self._features_complete.is_set() or not self.normal_controls_available:
            return False
        if key == "octo_remote_teach":
            return self.supports_remote_teach
        if key.startswith("preset_memory_") or key.startswith("program_memory_"):
            try:
                slot = int(key.rsplit("_", 1)[1])
            except ValueError:
                return False
            if not 1 <= slot <= self.memory_slot_count:
                return False
            return key.startswith("preset_memory_") or self.is_memory_slot_programmable(slot)
        return True

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        """Expose only the advertised, validated motion-light sensitivity choices."""
        if not self.supports_light_sensitivity:
            return ()
        return (
            ControllerSelectSpec(
                key="octo_light_sensitivity",
                translation_key="octo_light_sensitivity",
                state_key="octo_light_sensitivity",
                options=("6", "35", "85"),
                select_fn=lambda ctrl, value: cast(OctoController, ctrl).set_light_sensitivity(
                    int(value)
                ),
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        """Expose the receiver's 0–60 minute light duration setting."""
        if not self.supports_light_duration:
            return ()
        return (
            ControllerNumberSpec(
                key="octo_light_duration",
                translation_key="octo_light_duration",
                state_key="octo_light_duration",
                native_min_value=0,
                native_max_value=60,
                native_step=1,
                set_fn=lambda ctrl, value: cast(OctoController, ctrl).set_light_duration(
                    int(value)
                ),
                native_unit_of_measurement="min",
            ),
        )

    @property
    def supports_memory_presets(self) -> bool:
        """Return True if bed supports memory presets (CAP_MEMCOUNT > 0)."""
        if self._memory_count is not None:
            return self._memory_count > 0
        # Features not discovered - assume no memory presets for safety
        return False

    @property
    def memory_slot_count(self) -> int:
        """Return number of memory preset slots."""
        return self._memory_count if self._memory_count is not None else 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return True if the bed exposes saveable memory slots.

        Octo saves a position with CONFIG/SAVE_MOTORPOS. Slots the bed reports
        as locked via CAP_MEMINFO are excluded individually by
        is_memory_slot_programmable().
        """
        return self.supports_memory_presets

    @property
    def discovered_motor_count(self) -> int | None:
        """Return the motor count reported by the bed, or None if not yet discovered."""
        return self._discovered_motor_count

    @property
    def supports_synchro(self) -> bool:
        """Check if the bed supports synchro/linked mode.

        Returns True only if CAP_SYNCHRO (0x000101) was detected during discovery.
        """
        record = self._capability_records.get(OCTO_FEATURE_SYNCHRO)
        return bool(self._has_synchro and record is not None and record.readonly == 0)

    @property
    def is_synchro_active(self) -> bool | None:
        """Return current synchro/linked mode state, or None if unknown."""
        return self._synchro_active

    async def set_synchro(self, enabled: bool) -> None:
        """Set the CAP_SYNCHRO value while preserving advertised metadata."""
        if not self.supports_synchro:
            _LOGGER.warning("This Octo bed doesn't support synchro/linked mode")
            return
        await self._write_capability_value(OCTO_FEATURE_SYNCHRO, bytes((int(enabled),)))
        self._synchro_active = enabled

    async def set_remote_control_lock(self, enabled: bool) -> None:
        """Set the receiver remote-control lock capability."""
        if not self.supports_remote_control_lock:
            raise ValueError("OCTO remote-control lock is not available")
        await self._write_capability_value(OCTO_FEATURE_REMOTE_CONTROL_LOCK, bytes((int(enabled),)))
        self._remote_lock_active = enabled

    async def set_automatic_light(self, enabled: bool) -> None:
        """Enable or disable motion-triggered lighting through CAP_LIGHT_AUTO."""
        if not self.supports_automatic_light:
            raise ValueError("OCTO automatic lighting is not available")
        await self._write_capability_value(OCTO_FEATURE_LIGHT_AUTO, bytes((int(enabled),)))
        self._automatic_light_active = enabled

    async def set_light_duration(self, minutes: int) -> None:
        """Set the receiver's advertised light duration in minutes."""
        if type(minutes) is not int or not 0 <= minutes <= 60:
            raise ValueError("OCTO light duration must be between 0 and 60 minutes")
        if not self.supports_light_duration:
            raise ValueError("OCTO light duration is not available")
        await self._write_capability_value(OCTO_FEATURE_LIGHT_DURATION, minutes.to_bytes(2, "big"))
        self._light_duration_minutes = minutes

    async def set_light_sensitivity(self, value: int) -> None:
        """Set one of the app's supported sensitivity values."""
        if value not in (6, 35, 85):
            raise ValueError("OCTO sensitivity must be 6, 35, or 85")
        if not self.supports_light_sensitivity:
            raise ValueError("OCTO light sensitivity is not available")
        await self._write_capability_value(OCTO_FEATURE_LIGHT_SENSITIVITY, value.to_bytes(2, "big"))
        self._light_sensitivity = value

    async def teach_remote(self) -> None:
        """Run the app's direct BLE remote-teach action."""
        if not self.supports_remote_teach:
            raise ValueError("OCTO remote teach is not available")
        # RCTEACH is advertised read-only, but the accepted app sends this
        # one exact action payload. Keep the exception local to this action.
        await self._write_octo_command(
            [0x20, OCTO_SYSTEM_SET_CAPS], [0x00, 0x00, 0x10, 0x01, 0x01, 0x01, 0x01, 0x01]
        )

    async def enroll_pin(self, pin: str) -> None:
        """Set a four-digit PIN on an active receiver that does not have one."""
        if len(pin) != 4 or not pin.isascii() or not pin.isdecimal():
            raise ValueError("OCTO PIN must contain exactly four ASCII digits")
        if not self._session_ready or not self._pin_feature_active:
            raise ValueError("OCTO PIN control is not available")
        if self._has_pin is not False or self._pin_locked is not False:
            raise ValueError("OCTO PIN enrollment requires an unlocked receiver without a PIN")
        await self._write_octo_command(
            [0x20, OCTO_SYSTEM_PIN_SET],
            [int(digit) for digit in pin],
            cancel_event=asyncio.Event(),
        )
        self._pin = pin

    async def reset_defaults(self) -> None:
        """Restore receiver defaults after explicit service confirmation."""
        if not self._session_ready or not self.normal_controls_available:
            raise PermissionError("OCTO reset requires a complete, unlocked session")
        await self._write_octo_command(
            [0x20, OCTO_SYSTEM_SET_DEFAULT_CONFIG], cancel_event=asyncio.Event()
        )

        async def disconnect_after_reset() -> None:
            await asyncio.sleep(5)
            await self._coordinator.async_disconnect(serialize_with_commands=True)

        self._coordinator.entry.async_create_background_task(
            self._coordinator.hass,
            disconnect_after_reset(),
            name=f"adjustable_bed_octo_reset_disconnect_{self._coordinator.address}",
        )

    async def discover_features(self) -> bool:
        """Run OCTO's ordered session, with legacy fallback for absent replies.

        Well-formed replies follow the app's P1 ping, device-info and complete
        capability order. A timeout means the receiver omitted that response;
        malformed responses remain strict failures. Missing CAP_END uses the
        field-compatible legacy defaults without claiming authoritative records.
        """
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot discover features: not connected")
            return False

        # Ensure notifications are started - required for receiving feature responses
        # This is called explicitly here because coordinator.async_start_notify() may
        # skip notification setup when disable_angle_sensing is true, but Octo still
        # needs notifications for feature discovery (PIN/lights detection)
        if not self._notifications_started:
            self._response_buffer.clear()
            try:
                async with self._ble_lock:
                    await self.client.start_notify(OCTO_CHAR_UUID, self._on_notification)
                self._notifications_started = True
                _LOGGER.debug("Started Octo notifications for feature discovery")
            except BleakError as err:
                err_str = str(err).lower()
                # Treat "already notifying" as success - notifications are already active
                if "already notifying" in err_str or "already subscribed" in err_str:
                    self._notifications_started = True
                    _LOGGER.debug("Notifications already active, continuing with feature discovery")
                else:
                    _LOGGER.warning("Could not start notifications for feature discovery: %s", err)
                    return False

        # The previous complete record set remains authoritative until a new
        # complete CAP_END arrives. The current session writes into staging.
        self._session_ready = False
        self._session_generation += 1
        self._pin_state_accepted = None
        self._pin_state_event.clear()
        self._pin_retry_auth_sent = False
        self.invalid_response_received = False
        self._response_buffer.clear()
        self._ping_event.clear()
        self._ping_invalid = False
        self._device_info_event.clear()
        self._device_info_invalid = False
        self._capability_response_invalid = False
        self._legacy_assumed_lights = False
        self._features_loaded.clear()
        self._feature_discovery_event.clear()
        self._pin_sent = False
        self._pending_capability_records = {}

        try:
            await self._write_octo_command([0x20, OCTO_SYSTEM_PING], cancel_event=asyncio.Event())
            try:
                await asyncio.wait_for(
                    self._ping_event.wait(), timeout=OCTO_SESSION_RESPONSE_TIMEOUT
                )
            except TimeoutError:
                if self.invalid_response_received:
                    _LOGGER.debug("Rejecting malformed OCTO ping response")
                    return False
                _LOGGER.debug("OCTO ping reply absent; continuing with legacy-compatible session")
            if self._ping_invalid or self.invalid_response_received:
                _LOGGER.debug("Rejecting malformed OCTO ping response")
                return False

            self._device_info_event.clear()
            await self._write_octo_command(
                [0x20, OCTO_SYSTEM_GET_DEVICEINFO], cancel_event=asyncio.Event()
            )
            try:
                await asyncio.wait_for(
                    self._device_info_event.wait(), timeout=OCTO_SESSION_RESPONSE_TIMEOUT
                )
            except TimeoutError:
                if self.invalid_response_received:
                    _LOGGER.debug("Rejecting malformed OCTO device-info response")
                    return False
                _LOGGER.debug(
                    "OCTO device-info reply absent; continuing with legacy-compatible session"
                )
            if self._device_info_event.is_set() and (
                self._device_info_invalid or self.invalid_response_received
            ):
                _LOGGER.debug("Rejecting OCTO device-info response without exactly ten bytes")
                return False

            self._pending_capability_records = {}
            self._feature_discovery_event.clear()
            await self._write_octo_command(
                [0x20, OCTO_SYSTEM_GET_CAPS], cancel_event=asyncio.Event()
            )
            try:
                await asyncio.wait_for(
                    self._feature_discovery_event.wait(), timeout=OCTO_FEATURE_TIMEOUT
                )
            except TimeoutError:
                if self._capability_response_invalid or self.invalid_response_received:
                    _LOGGER.debug("Rejecting malformed or incomplete OCTO capability response")
                    return False
                if not self.controller_entity_discovery_complete:
                    # Preserve the historical default without fabricating typed
                    # records or persisting an incomplete capability list.
                    self._legacy_assumed_lights = True
                    self._has_lights = True
                    self._memory_count = 0
                    self._has_synchro = False
                _LOGGER.debug(
                    "OCTO capability list absent or incomplete; keeping known surfaces and "
                    "using legacy light fallback where no complete snapshot exists"
                )
            self._session_ready = True
            if self._legacy_assumed_lights:
                self._legacy_motor_layout_available = True
                self._publish_capability_state()
            _LOGGER.info(
                "OCTO capability discovery complete: motors=%s memory=%d lights=%s",
                self.effective_motor_count,
                self.memory_slot_count,
                self.supports_lights,
            )
            return True
        except TimeoutError:
            _LOGGER.debug("OCTO session handshake or capability discovery timed out")
            return False
        except BleakError as err:
            _LOGGER.warning("OCTO session discovery failed: %s", err)
            return False

    async def _move_motor(
        self, motor_bits: int, direction: str, cancel_event: asyncio.Event | None = None
    ) -> None:
        """Move a motor in the specified direction.

        Args:
            motor_bits: Bit mask for which motors to move (0x02=head, 0x04=legs)
            direction: "up" or "down"
            cancel_event: Optional event to cancel the command
        """
        # 0x70 = open (up), 0x71 = close (down)
        direction_byte = 0x70 if direction == "up" else 0x71
        # Use coordinator's configurable pulse settings
        # Defaults from BED_MOTOR_PULSE_DEFAULTS: Octo = (3, 350)
        # Clamp to minimum of 1 to prevent invalid values
        pulse_count = max(1, self._coordinator.motor_pulse_count)
        pulse_delay = max(1, self._coordinator.motor_pulse_delay_ms)
        await self._write_octo_command(
            command=[0x02, direction_byte],
            data=[motor_bits],
            repeat_count=pulse_count,
            repeat_delay_ms=pulse_delay,
            cancel_event=cancel_event,
        )

    async def _stop_motors(self) -> None:
        """Send stop command to all motors."""
        await self._write_octo_command(
            command=[0x02, 0x73],
            cancel_event=asyncio.Event(),  # Don't cancel stop commands
        )

    async def _octo_move_with_stop(self, motor_bits: int, direction: str) -> None:
        """Execute a movement command and always send STOP at the end."""
        try:
            await self._move_motor(motor_bits, direction)
        finally:
            await self._stop_motors()

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head motor up (motor 1)."""
        await self._octo_move_with_stop(OCTO_MOTOR_HEAD, "up")

    async def move_head_down(self) -> None:
        """Move head motor down (motor 1)."""
        await self._octo_move_with_stop(OCTO_MOTOR_HEAD, "down")

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self._stop_motors()

    async def move_back_up(self) -> None:
        """Move back up (same as head for Octo)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Octo)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up (motor 2)."""
        await self._octo_move_with_stop(OCTO_MOTOR_LEGS, "up")

    async def move_legs_down(self) -> None:
        """Move legs motor down (motor 2)."""
        await self._octo_move_with_stop(OCTO_MOTOR_LEGS, "down")

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._stop_motors()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Octo)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Octo)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    # Motor 3 and 4 control methods (for beds with CAP_MOTORCOUNT > 2)
    async def _move_motor3_up(self) -> None:
        """Move third motor up."""
        await self._octo_move_with_stop(OCTO_MOTOR_3, "up")

    async def _move_motor3_down(self) -> None:
        """Move third motor down."""
        await self._octo_move_with_stop(OCTO_MOTOR_3, "down")

    async def _move_motor3_stop(self) -> None:
        """Stop third motor."""
        await self._stop_motors()

    async def _move_motor4_up(self) -> None:
        """Move fourth motor up."""
        await self._octo_move_with_stop(OCTO_MOTOR_4, "up")

    async def _move_motor4_down(self) -> None:
        """Move fourth motor down."""
        await self._octo_move_with_stop(OCTO_MOTOR_4, "down")

    async def _move_motor4_stop(self) -> None:
        """Stop fourth motor."""
        await self._stop_motors()

    async def _move_motor34_up(self) -> None:
        """Move motors 3 and 4 up together (CD_MOTOR34)."""
        await self._octo_move_with_stop(OCTO_MOTOR_34, "up")

    async def _move_motor34_down(self) -> None:
        """Move motors 3 and 4 down together (CD_MOTOR34)."""
        await self._octo_move_with_stop(OCTO_MOTOR_34, "down")

    async def _move_motor34_stop(self) -> None:
        """Stop motors 3 and 4."""
        await self._stop_motors()

    async def _move_tv_lift_up(self) -> None:
        """Raise an OCTO one-motor TV lift."""
        await self._octo_move_with_stop(OCTO_MOTOR_HEAD, "up")

    async def _move_tv_lift_down(self) -> None:
        """Lower an OCTO one-motor TV lift."""
        await self._octo_move_with_stop(OCTO_MOTOR_HEAD, "down")

    async def _move_tv_lift_stop(self) -> None:
        """Stop an OCTO one-motor TV lift."""
        await self._stop_motors()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self._stop_motors()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return motor controls for Octo beds.

        Octo motors use bitmask addressing:
        - Motor 1 (0x02): Head/Back
        - Motor 2 (0x04): Legs
        - Motor 3 (0x08): Third motor (for beds with CAP_MOTORCOUNT > 2)
        - Motor 4 (0x10): Fourth motor (for beds with CAP_MOTORCOUNT > 3)

        Motor 3/4 are mapped to "head" and "feet" entity keys to match the
        standard cover entity naming convention.
        """
        if not self._motor_control_surface_ready:
            return ()
        motor_count = self.effective_motor_count
        if motor_count is None:
            return ()

        def held(key: str) -> ControllerMotorHoldSpec:
            return ControllerMotorHoldSpec(
                up_control=f"{key}_up",
                down_control=f"{key}_down",
                start_delay_ms=100,
                release_delay_ms=100,
            )

        if motor_count == 1:
            return (
                MotorControlSpec(
                    key="tv_lift",
                    translation_key="tv_lift",
                    open_fn=lambda ctrl: cast(OctoController, ctrl)._move_tv_lift_up(),
                    close_fn=lambda ctrl: cast(OctoController, ctrl)._move_tv_lift_down(),
                    stop_fn=lambda ctrl: cast(OctoController, ctrl)._move_tv_lift_stop(),
                    hold=held("tv_lift"),
                ),
            )

        specs: list[MotorControlSpec] = [
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
                hold=held("back"),
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda ctrl: ctrl.move_legs_up(),
                close_fn=lambda ctrl: ctrl.move_legs_down(),
                stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                max_angle=45,
                hold=held("legs"),
            ),
        ]

        if motor_count >= 2:
            specs.append(
                MotorControlSpec(
                    key="back_legs",
                    translation_key=("back_legs" if motor_count == 2 else "octo_motors_1_2"),
                    open_fn=lambda ctrl: cast(OctoController, ctrl)._octo_move_with_stop(
                        OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS, "up"
                    ),
                    close_fn=lambda ctrl: cast(OctoController, ctrl)._octo_move_with_stop(
                        OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS, "down"
                    ),
                    stop_fn=lambda ctrl: ctrl.stop_all(),
                    hold=held("back_legs"),
                )
            )

        if motor_count >= 3:
            specs.append(
                MotorControlSpec(
                    key="head",
                    translation_key="head",
                    open_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor3_up(),
                    close_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor3_down(),
                    stop_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor3_stop(),
                    hold=held("motor_3"),
                )
            )

        if motor_count >= 4:
            specs.append(
                MotorControlSpec(
                    key="feet",
                    translation_key="feet",
                    open_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor4_up(),
                    close_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor4_down(),
                    stop_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor4_stop(),
                    max_angle=45,
                    hold=held("motor_4"),
                )
            )
            # The official 4-motor layout offers motors 3+4 as one hardware
            # synchronised step (CD_MOTOR34), which is not the same as driving
            # the two covers one after the other. The app labels this step with
            # a pictogram rather than text, so the name here is ours.
            specs.append(
                MotorControlSpec(
                    key="head_feet",
                    translation_key="head_feet",
                    open_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor34_up(),
                    close_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor34_down(),
                    stop_fn=lambda ctrl: cast(OctoController, ctrl)._move_motor34_stop(),
                    hold=held("motor_34"),
                )
            )

        return tuple(specs)

    @property
    def supports_preset_both_up(self) -> bool:
        """Return whether Both Up remains a separate preset control."""
        count = self.effective_motor_count
        return count is not None and count >= 3

    @property
    def supports_preset_flat(self) -> bool:
        """Return whether Flat remains a separate preset control."""
        count = self.effective_motor_count
        return count is not None and count >= 3

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Return entity keys belonging to the other OCTO actuator layout."""
        if self.effective_motor_count is None:
            return frozenset({"tv_lift", "back", "legs", "back_legs", "head", "feet", "head_feet"})
        if self._is_one_motor_lift:
            return frozenset({"back", "legs", "back_legs", "head", "feet", "head_feet"})
        stale = {"tv_lift"}
        if self.effective_motor_count != 2:
            stale.add("back_legs")
        if self.effective_motor_count < 4:
            # Reconfiguring 4 motors down to 2 or 3 drops the combined step, and
            # without this it lingers in the registry as an unavailable ghost.
            stale.add("head_feet")
        return frozenset(stale)

    # Preset methods
    async def preset_both_up(self) -> None:
        """Move both head and legs up simultaneously."""
        await self._octo_move_with_stop(OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS, "up")

    @property
    def _all_motors_mask(self) -> int:
        """Return the bitmask covering every motor this receiver has.

        Accepted analysis of OCTO Smart Control 1.03.02 shows the official app
        drives an all-motors step as M12 0x06 (2 motors), M123 0x0E (3) or
        M1234 0x1E (4), and exposes it as a down-only control.
        """
        mask = OCTO_MOTOR_HEAD | OCTO_MOTOR_LEGS
        motor_count = self.effective_motor_count
        if motor_count is None:
            raise ValueError("OCTO motor count is invalid; select an explicit layout to move")
        if motor_count >= 3:
            mask |= OCTO_MOTOR_3
        if motor_count >= 4:
            mask |= OCTO_MOTOR_4
        return mask

    async def preset_flat(self) -> None:
        """Go to flat position.

        Octo has no flat preset, so every motor is driven down at once. This
        must cover motors 3 and 4 as well: sending only M12 on a 3M/4M receiver
        (RC3, BM3, and 4-motor bases) leaves the extra actuators where they
        were, so the bed never actually reaches flat.
        """
        await self._octo_move_with_stop(self._all_motors_mask, "down")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset position.

        Args:
            memory_num: Memory slot number (1-based, will be converted to 0-based for protocol)
        """
        if not self.supports_memory_presets:
            _LOGGER.warning("This Octo bed doesn't support memory presets")
            return

        if memory_num < 1 or memory_num > self.memory_slot_count:
            _LOGGER.warning(
                "Invalid memory slot %d (bed has %d slots)",
                memory_num,
                self.memory_slot_count,
            )
            return

        # The headless service keeps a finite host safety bound; the card uses
        # hold_control directly and sends side STOP on release.
        await self.hold_control(f"memory_{memory_num}", OCTO_DEFAULT_PRESET_HOLD_MS)

    @property
    def supports_held_memory_recall(self) -> bool:
        return self.supports_memory_presets

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        """Recall a slot for an explicit, bounded service duration."""
        self.validate_memory_recall(slot)
        await self.hold_control(f"memory_{slot}", hold_ms)

    async def program_memory(self, memory_num: int) -> None:
        """Save current position to memory slot.

        Args:
            memory_num: Memory slot number (1-based, will be converted to 0-based for protocol)
        """
        if not self.supports_memory_presets:
            _LOGGER.warning("This Octo bed doesn't support memory presets")
            return

        if memory_num < 1 or memory_num > self.memory_slot_count:
            _LOGGER.warning(
                "Invalid memory slot %d (bed has %d slots)",
                memory_num,
                self.memory_slot_count,
            )
            return

        if not self.is_memory_slot_programmable(memory_num):
            # The Save button is hidden for locked slots, but adjustable_bed.
            # save_preset and automations reach this directly.
            _LOGGER.warning(
                "Memory slot %d is locked on this Octo bed and cannot be overwritten",
                memory_num,
            )
            return

        # Protocol uses 0-based slot index, CONFIG packet type (0x10)
        slot = memory_num - 1
        await self._write_octo_command(
            command=[0x10, 0x70],  # CONFIG packet, SAVE_MOTORPOS command
            data=[slot],
        )

    # Light control
    # Data format: [cap_id (3 bytes), readonly (1 byte), char_len (1 byte), char (n bytes), value_type (1 byte), value (n bytes)]
    # Cap ID 0x000102 = LIGHT feature, ReadOnly=0x00 for write operations, value 0x01=on, 0x00=off
    async def lights_on(self) -> None:
        """Turn on under-bed lights using advertised or legacy field behavior."""
        if self._legacy_assumed_lights:
            await self._write_octo_command(
                [0x20, OCTO_SYSTEM_SET_CAPS],
                [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x01],
            )
            return
        await self._write_capability_value(OCTO_FEATURE_LIGHT, b"\x01")

    async def lights_off(self) -> None:
        """Turn off under-bed lights using advertised or legacy field behavior."""
        if self._legacy_assumed_lights:
            await self._write_octo_command(
                [0x20, OCTO_SYSTEM_SET_CAPS],
                [0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x00],
            )
            return
        await self._write_capability_value(OCTO_FEATURE_LIGHT, b"\x00")

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights.

        Toggle only from a known active CAP_LIGHT state; never guess.
        """
        record = self._capability_records.get(OCTO_FEATURE_LIGHT)
        if record is None or len(record.value) != 1:
            raise ValueError("OCTO light state is unknown")
        await (self.lights_off() if record.value[0] == 1 else self.lights_on())

    async def _turn_light_on_before_color_write(self) -> None:
        """Apply the app's light-on-before-color ordering when CAP_LIGHT exists."""
        record = self._capability_records.get(OCTO_FEATURE_LIGHT)
        if (
            record is not None
            and record.characteristic[:1] == b"\x01"
            and len(record.value) == 1
            and record.value[0] == 0
        ):
            await self.lights_on()

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        """Write the independent three-byte CAP_LIGHT_RGB color record."""
        if len(rgb_color) != 3 or any(
            type(channel) is not int or not 0 <= channel <= 255 for channel in rgb_color
        ):
            raise ValueError(f"RGB values must be three integers from 0 to 255, got {rgb_color}")
        if not self._has_rgb:
            raise ValueError("OCTO RGB color control is not active")
        await self._turn_light_on_before_color_write()
        await self._write_capability_value(OCTO_FEATURE_LIGHT_RGB, bytes(rgb_color))

    async def set_light_color_rgbw(
        self,
        rgbw_color: tuple[int, int, int, int],
        intensity: int | None = None,
    ) -> None:
        """Set RGBWI light color.

        The five-byte advertised value is preserved independently; omitted
        intensity retains the bed's current byte.

        Args:
            rgbw_color: RGBW tuple with values from 0-255.
        """
        r, g, b, w = rgbw_color
        if not all(type(v) is int and 0 <= v <= 255 for v in (r, g, b, w)):
            raise ValueError(f"RGBW values must be 0-255, got {rgbw_color}")
        if not self._has_rgbwi:
            raise ValueError("OCTO RGBW color control is not active")
        record = self._capability_records[OCTO_FEATURE_LIGHT_RGBWI]
        if intensity is None:
            intensity = record.value[4]
        if type(intensity) is not int or not 0 <= intensity <= 255:
            raise ValueError("OCTO light intensity must be an integer from 0 to 255")
        await self._turn_light_on_before_color_write()
        await self._write_capability_value(OCTO_FEATURE_LIGHT_RGBWI, bytes((r, g, b, w, intensity)))

    # PIN authentication and challenge retry methods

    async def send_pin(self) -> None:
        """Send a validated four-digit PIN after the ordered session handshake."""
        if not self._pin:
            _LOGGER.debug("No PIN configured, skipping PIN authentication")
            return

        if not self._session_ready:
            _LOGGER.debug("OCTO session is not ready; skipping PIN authentication")
            return

        if not self.requires_pin:
            _LOGGER.debug("Bed does not require PIN authentication")
            return

        if self.client is None or not self.client.is_connected:
            _LOGGER.debug("Cannot send PIN: not connected")
            return

        try:
            # Convert PIN string to list of integer digits
            # Validation should happen in config flow, but add defensive check
            if len(self._pin) != 4 or not self._pin.isascii() or not self._pin.isdecimal():
                _LOGGER.error("Invalid PIN: must contain exactly four ASCII digits")
                return
            pin_data = [int(c) for c in self._pin]
            _LOGGER.debug("Sending PIN authentication (%d digits)", len(pin_data))
            self._pin_state_accepted = None
            self._pin_state_event.clear()
            if self._pin_retry_pending:
                self._pin_retry_authorized = False
                self._pin_retry_auth_sent = True
            await self._write_octo_command(
                command=[0x20, 0x43],
                data=pin_data,
                # Authentication is not a cancellable movement. A pending STOP
                # must not suppress the PIN write on reconnect.
                cancel_event=asyncio.Event(),
            )
            self._pin_sent = True
            _LOGGER.debug("PIN authentication sent successfully")
        except (ValueError, BleakError) as err:
            self._pin_retry_auth_sent = False
            _LOGGER.warning("Failed to send PIN: %s", err)

    async def start_keepalive(self) -> None:
        """Start periodic PIN refresh for a configured, held OCTO link."""
        if not self._pin:
            return
        client = self.client
        if not self._session_ready or client is None or not client.is_connected:
            return
        if (
            self._keepalive_task is not None
            and not self._keepalive_task.done()
            and self._keepalive_session_generation == self._session_generation
        ):
            return
        await self.stop_periodic_keepalive()
        self._keepalive_generation += 1
        generation = self._keepalive_generation
        session_generation = self._session_generation
        self._keepalive_session_generation = session_generation
        self._keepalive_task = asyncio.create_task(
            self._keepalive_loop(generation, session_generation)
        )

    async def stop_periodic_keepalive(self) -> None:
        """Cancel only the periodic PIN refresh task."""
        self._keepalive_generation += 1
        task = self._keepalive_task
        self._keepalive_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _keepalive_loop(self, generation: int, session_generation: int) -> None:
        """Periodically re-authenticate through the coordinator command lane."""
        try:
            while (
                generation == self._keepalive_generation
                and session_generation == self._session_generation
                and self._session_ready
                and self._pin
            ):
                await asyncio.sleep(OCTO_PIN_KEEPALIVE_INTERVAL)
                client = self.client
                if (
                    generation != self._keepalive_generation
                    or session_generation != self._session_generation
                    or not self._session_ready
                    or not self._pin
                    or client is None
                    or not client.is_connected
                ):
                    return

                async def authenticate(controller: BedController) -> None:
                    if controller is self:
                        await self._send_keepalive_pin()

                try:
                    await self._coordinator.async_execute_controller_command(
                        authenticate,
                        cancel_running=False,
                        skip_disconnect=True,
                        read_positions_after_operation=False,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    _LOGGER.warning("OCTO periodic PIN keepalive failed: %s", err)
        except asyncio.CancelledError:
            raise
        finally:
            if self._keepalive_task is asyncio.current_task():
                self._keepalive_task = None

    async def _send_keepalive_pin(self) -> None:
        """Refresh configured PIN authentication without changing live lock state."""
        if not self._pin or not self._session_ready:
            return
        client = self.client
        if client is None or not client.is_connected:
            return
        if len(self._pin) != 4 or not self._pin.isascii() or not self._pin.isdecimal():
            _LOGGER.error("Invalid PIN: must contain exactly four ASCII digits")
            return
        await self._write_octo_command(
            [0x20, OCTO_SYSTEM_PIN_AUTH],
            [int(character) for character in self._pin],
            cancel_event=asyncio.Event(),
        )

    async def async_wait_for_pin_acceptance(self, cancel_event: asyncio.Event) -> None:
        """Wait for this session to confirm PIN access before a normal command."""
        generation = self._session_generation
        if not self._session_ready:
            raise ConnectionError("OCTO session discovery is not complete")
        if self.normal_controls_available:
            return
        if not self._pin:
            raise PermissionError("OCTO PIN is required but no PIN is configured")
        if not self._pin_sent:
            if not self._pin_retry_pending or self._pin_retry_authorized:
                await self.send_pin()
            if not self._pin_sent:
                if generation != self._session_generation or not self._session_ready:
                    raise ConnectionError("OCTO session changed while sending the PIN")
                raise ConnectionError("OCTO PIN authentication could not be sent")
            if self.normal_controls_available:
                return

        state_wait = asyncio.create_task(self._pin_state_event.wait())
        cancel_wait = asyncio.create_task(cancel_event.wait())
        try:
            done, pending = await asyncio.wait(
                (state_wait, cancel_wait),
                timeout=OCTO_PIN_ACCEPTANCE_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in pending:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if cancel_wait in done:
                raise asyncio.CancelledError
            if self._session_generation != generation or not self._session_ready:
                raise ConnectionError("OCTO session changed while waiting for PIN access")
            if state_wait not in done:
                raise TimeoutError("Timed out waiting for OCTO PIN acceptance")
            if self._pin_state_accepted is not True or not self.normal_controls_available:
                raise PermissionError("OCTO bed rejected the configured PIN")
        finally:
            for task in (state_wait, cancel_wait):
                if not task.done():
                    task.cancel()
            for task in (state_wait, cancel_wait):
                if task.cancelled():
                    continue
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def stop_keepalive(self) -> None:
        """Cancel periodic PIN refresh and one-shot delayed challenge retry."""
        await self.stop_periodic_keepalive()
        self._pin_lock_generation += 1
        if self._pin_resend_task is not None:
            self._pin_resend_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pin_resend_task
            self._pin_resend_task = None


class OctoStar2Controller(BedController):
    """Controller for Octo Remote Star2 beds.

    Star2 uses a different protocol with fixed command bytes:
    - Service UUID: aa5c
    - Characteristic UUID: 5a55
    - Packet format: starts with 0x68, ends with 0x16
    """

    _write_with_response = True

    # Star2 fixed command bytes
    # Protocol reverse-engineered by goedh452
    # (https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10)
    # Format: starts with 0x68, ends with 0x16
    CMD_HEAD_UP = bytes(
        [0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x36, 0x31, 0x38, 0x16]
    )
    CMD_HEAD_DOWN = bytes(
        [0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x39, 0x31, 0x3B, 0x16]
    )
    CMD_FEET_UP = bytes(
        [0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x34, 0x31, 0x36, 0x16]
    )
    CMD_FEET_DOWN = bytes(
        [0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x30, 0x37, 0x31, 0x39, 0x16]
    )
    CMD_BOTH_UP = bytes(
        [0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x32, 0x37, 0x31, 0x3B, 0x16]
    )
    CMD_BOTH_DOWN = bytes(
        [0x68, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x31, 0x32, 0x38, 0x31, 0x3C, 0x16]
    )

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Octo Star2 controller."""
        super().__init__(coordinator)
        self._notify_callback: Callable[[str, float], None] | None = None
        _LOGGER.debug("OctoStar2Controller initialized")

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Return stale OCTO motor entities to remove for Star2."""
        return frozenset({"tv_lift", "head", "feet", "head_feet"})

    @property
    def auto_stops_on_idle(self) -> bool:
        """Star2 motors stop when the held-command refresh ends."""
        return True

    @property
    def supports_lights(self) -> bool:
        """Star2 protocol doesn't support light control."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return False - Octo Star2 beds don't support memory presets."""
        return False

    @property
    def supports_synchro(self) -> bool:
        """Star2 protocol doesn't support synchro/linked mode."""
        return False

    async def set_synchro(self, enabled: bool) -> None:
        """No-op: Star2 protocol doesn't support synchro/linked mode."""
        _LOGGER.warning("Octo Star2 beds don't support synchro/linked mode")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OCTO_STAR2_CHAR_UUID

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Start listening for notifications.

        Star2 doesn't support position notifications, so this only stores the callback.
        """
        _LOGGER.debug("start_notify called for OctoStar2Controller - notifications not supported")
        self._notify_callback = callback

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        _LOGGER.debug("stop_notify called for OctoStar2Controller - notifications not supported")
        self._notify_callback = None

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data.

        Star2 doesn't support position feedback.

        Args:
            motor_count: Number of motors to read positions for (unused).
        """
        _LOGGER.debug(
            "read_positions called for OctoStar2Controller with motor_count=%d "
            "- position feedback not supported",
            motor_count,
        )

    async def _send_stop(self) -> None:
        """Send stop command.

        Star2 protocol doesn't have an explicit stop command.
        Motors stop when commands stop being sent.
        """
        _LOGGER.debug(
            "Stop requested for OctoStar2Controller - Star2 has no explicit stop command, "
            "motors stop when commands cease"
        )

    def _get_pulse_settings(self) -> tuple[int, int]:
        """Get clamped pulse settings from coordinator.

        Returns:
            Tuple of (pulse_count, pulse_delay_ms), both clamped to minimum of 1.
        """
        return (
            max(1, self._coordinator.motor_pulse_count),
            max(1, self._coordinator.motor_pulse_delay_ms),
        )

    # Motor control methods using fixed Star2 commands
    # Uses coordinator's configurable pulse settings for timing
    async def move_head_up(self) -> None:
        """Move head motor up."""
        pulse_count, pulse_delay = self._get_pulse_settings()
        try:
            await self.write_command(
                self.CMD_HEAD_UP,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            await self._send_stop()

    async def move_head_down(self) -> None:
        """Move head motor down."""
        pulse_count, pulse_delay = self._get_pulse_settings()
        try:
            await self.write_command(
                self.CMD_HEAD_DOWN,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            await self._send_stop()

    async def move_head_stop(self) -> None:
        """Stop head motor.

        Star2 doesn't have explicit stop - motors stop when commands cease.
        """
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back up (same as head for Star2)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head for Star2)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up."""
        pulse_count, pulse_delay = self._get_pulse_settings()
        try:
            await self.write_command(
                self.CMD_FEET_UP,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            await self._send_stop()

    async def move_legs_down(self) -> None:
        """Move legs motor down."""
        pulse_count, pulse_delay = self._get_pulse_settings()
        try:
            await self.write_command(
                self.CMD_FEET_DOWN,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            await self._send_stop()

    async def move_legs_stop(self) -> None:
        """Stop legs motor.

        Star2 doesn't have explicit stop - motors stop when commands cease.
        """
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Star2)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Star2)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        """Stop all motors.

        Star2 doesn't have explicit stop command - motors stop when commands cease.
        """
        await self._send_stop()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose Star2's combined command as a hold-capable motor control."""
        return (
            *super().motor_control_specs,
            MotorControlSpec(
                key="back_legs",
                translation_key="back_legs",
                open_fn=lambda ctrl: cast(OctoStar2Controller, ctrl).preset_both_up(),
                close_fn=lambda ctrl: cast(OctoStar2Controller, ctrl).preset_flat(),
                stop_fn=lambda ctrl: ctrl.stop_all(),
            ),
        )

    @property
    def supports_preset_both_up(self) -> bool:
        """Return False because Both Up is exposed as a motor control."""
        return False

    @property
    def supports_preset_flat(self) -> bool:
        """Return False because Flat is exposed as a motor control."""
        return False

    async def preset_both_up(self) -> None:
        """Move both head and legs up simultaneously."""
        pulse_count, pulse_delay = self._get_pulse_settings()
        try:
            await self.write_command(
                self.CMD_BOTH_UP,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            await self._send_stop()

    async def preset_flat(self) -> None:
        """Go to flat position by moving both motors down."""
        pulse_count, pulse_delay = self._get_pulse_settings()
        try:
            await self.write_command(
                self.CMD_BOTH_DOWN,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
            )
        finally:
            await self._send_stop()

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset.

        Star2 doesn't support memory presets.

        Args:
            memory_num: Memory slot number (unused - feature not supported).
        """
        _LOGGER.warning(
            "Octo Star2 beds don't support memory presets (requested memory_num=%d)",
            memory_num,
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory.

        Star2 doesn't support memory presets.

        Args:
            memory_num: Memory slot number (unused - feature not supported).
        """
        _LOGGER.warning(
            "Octo Star2 beds don't support programming memory presets (requested memory_num=%d)",
            memory_num,
        )
