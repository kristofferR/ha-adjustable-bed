"""Vibradorm VMAT protocol helpers.

This module holds the protocol-specific constants, advertisement parser, and
EEPROM reassembly for the Vibradorm VMAT BLE protocol (de.vibradorm.vra2 and
its variants — CARESSE, WERKMEISTER, de.vibradorm.vmat). The companion
controller lives in :mod:`custom_components.adjustable_bed.beds.vibradorm`.

All constants and offsets here are taken directly from the decompiled
``de.vibradorm.diamant`` APK
(``utilities/VibUUIDs.java``, ``utilities/VibCommandCodes.java``,
``utilities/XMCMotorData.java``, ``utilities/XMCeeprom.java``,
``VibBle/MC.java``, ``VibBle/ManufacturerDataParser.java``,
``CBICommands/Cmd*.java``) — see issue #403 for the full protocol map.

Two parallel command paths exist in the OEM apps:

* **VMAT-basic** — single byte on the COMMAND characteristic
  (``0x1526``) for motor moves. Some VMAT-basic beds (e.g. RF-CBI) ignore
  ``0x1528``/``0x1534`` and never drive the secondary motor characteristics.
* **CBI** — framed 16-bit big-endian command word (``toggle | cmd``)
  followed by an optional payload on the CBI characteristic (``0x1550``).
  The toggle bit alternates ``0x0000 ⇄ 0x8000`` so the controller can
  distinguish a fresh press from a repeat, and the CBI bus mask
  (``0x1000``) routes traffic to the secondary "XT box" accessory bus.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Command codes
# ---------------------------------------------------------------------------

# Single-byte motor codes (written to COMMAND 0x1526 for VMAT-basic beds).
CMD_STOP: int = 0xFF
CMD_AR: int = 0x00  # Alles Runter — all down / flat
CMD_AH: int = 0x10  # Alles Hoch  — all up
CMD_NR: int = 0x02  # Nacken Runter (neck down)
CMD_NH: int = 0x03  # Nacken Hoch   (neck up)
CMD_FR: int = 0x04  # Fuß Runter    (foot down)
CMD_FH: int = 0x05  # Fuß Hoch      (foot up)
CMD_OSR: int = 0x08  # Oberschenkel Runter (thigh down)
CMD_OSH: int = 0x09  # Oberschenkel Hoch   (thigh up)
CMD_KR: int = 0x0A  # Kopf Runter  (back down)
CMD_KH: int = 0x0B  # Kopf Hoch    (back up)
CMD_STORE: int = 0x0D
CMD_MEM1: int = 0x0E
CMD_MEM2: int = 0x0F
CMD_MEM3: int = 0x0C
CMD_MEM4: int = 0x1A
CMD_MEM5: int = 0x1B
CMD_MEM6: int = 0x1C
CMD_SYNC_OFF: int = 0x19
CMD_SYNC_ON: int = 0x18

# 16-bit CBI command codes. ``0x1000`` (CBI_BUS_MASK) is OR'd in for the
# secondary "XT box" accessory bus.
CBI_BUS_MASK: int = 0x1000
TOGGLE_BIT: int = 0x8000

CMD_DIM: int = 0x11  # VMAT/CBI light dim — written as 2-byte to CBI
CMD_VxEFF: int = 0x30  # VRT (vibration) effect / settings payload
CMD_VRT: int = 0x34  # VRT on/off toggle
CMD_GET_STATUS: int = 0x3D  # CmdGetStatusMotMon
CMD_INIT: int = 0x3E
CMD_COLOR: int = 0x77  # Mood-light base code (0x1077 for XT box)
CMD_GET_INFO: int = 0x1A0
CMD_REG_READ: int = 0x1B3
CMD_REG_CLEAR: int = 0x1B4
INFO_ID_VM: int = 0x30

# CmdLightCBI packet shape: ``[msb,lsb, level(0-8), timer(min)]``.
# MC.setFloorLightLevel clamps level to 0..8.

# Mood-light packet (CmdMoodColor): ``[msb,lsb, 0x01, 0x00, R, G, B]``.
MOOD_COLOR_SUBCMD: int = 0x01

# Mood-light effect selector (CmdMoodEffect): ``[msb,lsb, 0x08, effectId]``.
MOOD_EFFECT_SUBCMD: int = 0x08

# Mood-light effect speed (CmdEffectSpeed):
#   ``speed = 20 - (uiSpeed + 1) * 2``  →  ``[msb,lsb, 0x09, speed]``
MOOD_SPEED_SUBCMD: int = 0x09
MOOD_SPEED_BASE: int = 20
MOOD_SPEED_STEP: int = 2

# VRT settings packet (CmdVRT):
#   ``[msb,lsb, effect, speed, intensityZone1, intensityZone2, 0,0,0, timer]``
# `intensityZone1` = head, `intensityZone2` = foot, both 0..5 (0 = off).
# Speed is 1..5. Timer is in minutes.
VRT_EFFECT_DEFAULT: int = 0
VRT_TIMER_DEFAULT: int = 0  # minutes
VRT_INTENSITY_MAX: int = 5  # inclusive
VRT_SPEED_MAX: int = 5  # 1..5
VRT_TIMER_OPTIONS: tuple[int, ...] = (10, 20, 30)

# CmdGetStatusMotMon packet: ``[msb,lsb, 0x3F]``.
CMD_GET_STATUS_QUERY_BYTE: int = 0x3F

# Position notification flags byte (XMCMotorData.flags).
XMCMOTOR_INIT_ZWANG_MASK: int = 0x10  # teach/limit run needed
XMCMOTOR_SYNC_STATUS_MASK: int = 0x40  # head+foot sync active

# Position stream long-format prefix (VibCommandCodes + XMC).
POSITION_NOTIFY_PREFIX: int = 0x20
POSITION_NOTIFY_TYPE: int = 0x3F
POSITION_NOTIFY_SHORT_TYPE: int = 0x3F

# EEPROM image: 256 bytes delivered as 32 rows of 8 bytes.
EEPROM_SIZE: int = 256
EEPROM_ROW_SIZE: int = 8
EEPROM_ROW_COUNT: int = EEPROM_SIZE // EEPROM_ROW_SIZE
EEPROM_ALL_ROWS_BITMASK: int = (1 << EEPROM_ROW_COUNT) - 1  # 0xFFFFFFFF

# Layout offsets into the 256-byte EEPROM image (XMCeeprom.java).
EEPROM_OFFSET_LOCK: int = 0
EEPROM_OFFSET_SYNC_MODE: int = 1
EEPROM_OFFSET_INIT_ZWANG: int = 2
EEPROM_OFFSET_PULSE_MOT1: int = 10
EEPROM_OFFSET_PULSE_MOT2: int = 12
EEPROM_OFFSET_PULSE_MOT3: int = 14
EEPROM_OFFSET_PULSE_MOT4: int = 16
EEPROM_OFFSET_MEM_BASE: int = 20  # slot 0 motor 0 → +0; +2 per motor; +8 per slot
EEPROM_OFFSET_TEACH_INS: int = 72
EEPROM_OFFSET_FACTORY_RESET: int = 74
EEPROM_OFFSET_INIT_ZWANG_COUNT: int = 76
EEPROM_OFFSET_POWER_UPS: int = 78
EEPROM_OFFSET_WDT_RESETS: int = 80
EEPROM_OFFSET_SYSTEM_RESET: int = 81
EEPROM_OFFSET_OTHER_RESET: int = 82
EEPROM_OFFSET_TOTAL_PULSE_MOT1: int = 84
EEPROM_OFFSET_TOTAL_PULSE_MOT2: int = 88
EEPROM_OFFSET_TOTAL_PULSE_MOT3: int = 92
EEPROM_OFFSET_TOTAL_PULSE_MOT4: int = 96
EEPROM_OFFSET_TOTAL_ON_TIME: int = 100
EEPROM_OFFSET_FAHRT_UEBERWACHUNG1: int = 104
EEPROM_OFFSET_FAHRT_UEBERWACHUNG2: int = 106
EEPROM_OFFSET_FAHRT_UEBERWACHUNG3: int = 108
EEPROM_OFFSET_FAHRT_UEBERWACHUNG4: int = 110
EEPROM_OFFSET_H_BRIDGE_OVER_TEMP: int = 112

# ---------------------------------------------------------------------------
# Manufacturer data parser
# ---------------------------------------------------------------------------


def _concat_manufacturer_payloads(
    manufacturer_data: Mapping[int, bytes] | None,
) -> bytes | None:
    """Concatenate all 0xFF manufacturer-data blocks from an AD payload.

    Mirrors ``ManufacturerDataParser`` in the decompiled APK: it walks the
    AD structures, picks blocks with type ``0xFF`` and concatenates them
    into a single byte string. Returns ``None`` when no manufacturer data
    is available.
    """
    if not manufacturer_data:
        return None
    blocks = [bytes(payload) for payload in manufacturer_data.values() if payload]
    if not blocks:
        return None
    return b"".join(blocks)


def parse_manufacturer_id(payload: bytes | None) -> int:
    """Return the manufacturer ID (LE u16 at offset 0)."""
    if payload is None or len(payload) < 2:
        return 0
    return payload[0] | (payload[1] << 8)


def parse_vib_identifier(payload: bytes | None) -> int:
    """Return the VMAT ``vibIdentifier`` (BE u16 at offset 2)."""
    if payload is None or len(payload) < 4:
        return 0
    return (payload[2] << 8) | payload[3]


def parse_vib_flags(payload: bytes | None) -> int:
    """Return the VMAT ``vibFlags`` (4-bit packed across offsets 4..5)."""
    if payload is None or len(payload) < 6:
        return 0
    return (payload[4] & 0xF0) | ((payload[5] & 0xF0) >> 4)


def parse_kunden_id(payload: bytes | None) -> int:
    """Return the VMAT ``kundenID`` (4-bit packed across offsets 8..9).

    Returns ``0xFFFF`` (sentinel) when the payload is too short.
    """
    if payload is None or len(payload) <= 6:
        return 0xFFFF
    if len(payload) < 10:
        return 0xFFFF
    return (payload[8] & 0xF0) | ((payload[9] & 0xF0) >> 4)


def control_version_to_motor_count(control_version: int) -> int | None:
    """Map the OEM app's control-version int to a motor count.

    Source: ``MainScreen.getControlVersion()`` in the decompiled APK:
    ``0``/``5`` → 2-motor, ``4``/``6`` → 3-motor, ``1``/``-1`` → 4-motor.
    Returns ``None`` for unrecognised values so callers can fall back to
    the user-configured motor count.
    """
    if control_version in (0, 5):
        return 2
    if control_version in (4, 6):
        return 3
    if control_version in (1, -1):
        return 4
    return None


def detect_control_version(
    manufacturer_data: Mapping[int, bytes] | None,
) -> int | None:
    """Return the control-version byte for the given manufacturer data.

    The version lives in the lower byte of the ``vibIdentifier`` BE u16
    (the OEM apps use ``getControlType()`` to read the same value from
    SharedPreferences after onboarding, so the value is normally
    available locally — but the byte survives a fresh advertisement once
    the user has paired the bed). The byte is signed: ``-1`` (0xFF) is
    the 4-motor "Vibradorm 4" variant.
    """
    payload = _concat_manufacturer_payloads(manufacturer_data)
    if payload is None or len(payload) < 4:
        return None
    vib_identifier = parse_vib_identifier(payload)
    signed_version = _to_signed_byte(vib_identifier & 0xFF)
    if control_version_to_motor_count(signed_version) is None:
        return None
    return signed_version


def detect_motor_count_from_manufacturer_data(
    manufacturer_data: Mapping[int, bytes] | None,
) -> int | None:
    """Return the OEM app's motor count for the given manufacturer data, or ``None``."""
    control_version = detect_control_version(manufacturer_data)
    if control_version is None:
        return None
    return control_version_to_motor_count(control_version)


def _to_signed_byte(value: int) -> int:
    """Convert an unsigned byte to its signed 8-bit representation.

    The OEM app's ``getControlType()`` returns signed bytes (e.g. -1 for
    the 4-motor "Vibradorm 4" variant); the advertisement byte carries the
    same value as an unsigned u8 (0xFF), so we re-sign before comparing
    against the documented control-version constants.
    """
    value &= 0xFF
    if value >= 0x80:
        return value - 0x100
    return value


# ---------------------------------------------------------------------------
# EEPROM reassembly
# ---------------------------------------------------------------------------


@dataclass
class EepromSnapshot:
    """Decoded view of the 256-byte EEPROM image.

    Mirrors the field accessors on ``XMCeeprom.java``. ``total_*`` fields
    are 32-bit big-endian values; ``*_pulse``/``mem_pos`` are 16-bit
    big-endian. ``h_bridge_over_temp`` and ``fahrt_ueberwachung`` are
    raw diagnostic values the OEM apps surface as "ED active" / "link
    failure" / over-temperature flags.
    """

    lock_flag: int
    sync_mode: int
    init_zwang: int
    pulse_mot1: int
    pulse_mot2: int
    pulse_mot3: int
    pulse_mot4: int
    memory_positions: tuple[tuple[int, int, int, int], ...]  # 6 slots × 4 motors
    teach_in_count: int
    factory_reset_count: int
    init_zwang_count: int
    power_up_count: int
    wdt_resets: int
    system_resets: int
    other_resets: int
    total_pulse_mot1: int
    total_pulse_mot2: int
    total_pulse_mot3: int
    total_pulse_mot4: int
    total_on_time: int
    fahrt_ueberwachung: tuple[int, int, int, int]
    h_bridge_over_temp: int
    complete: bool  # True when all 32 rows have been received


def _word_be(data: bytes | bytearray, offset: int) -> int:
    """Read a signed 16-bit big-endian value at ``offset`` (M.word)."""
    if offset + 1 >= len(data):
        return 0
    value = (data[offset] << 8) | data[offset + 1]
    if value >= 0x8000:
        value -= 0x10000
    return value


def _long_be(data: bytes | bytearray, offset: int) -> int:
    """Read an unsigned 32-bit big-endian value at ``offset`` (M.longWord)."""
    if offset + 3 >= len(data):
        return 0
    return (
        (data[offset] << 24)
        | (data[offset + 1] << 16)
        | (data[offset + 2] << 8)
        | data[offset + 3]
    )


class VibradormEeprom:
    """Reassemble 32×8 EEPROM row notifications into a 256-byte image.

    Each CBI-response notification carrying an EEPROM row has the layout
    ``[echoCmdHi, echoCmdLo, offset, b0, b1, b2, b3, b4, b5, b6, b7]``
    (the OEM app's ``XMCeeprom.setRow``). The 8 data bytes are copied at
    ``offset``; the row index is ``offset // 8`` and a 32-bit mask tracks
    which rows have been received. ``all_received()`` returns True once
    the mask equals ``(1 << 32) - 1``.
    """

    __slots__ = ("_data", "_rows_received")

    def __init__(self) -> None:
        """Initialise an empty EEPROM image."""
        self._data: bytearray = bytearray(EEPROM_SIZE)
        self._rows_received: int = 0

    def reset(self) -> None:
        """Discard the cached image and row mask."""
        self._data = bytearray(EEPROM_SIZE)
        self._rows_received = 0

    @property
    def rows_received(self) -> int:
        """Return the bitmap of rows successfully received (LSB = row 0)."""
        return self._rows_received

    def set_row(self, payload: bytes | bytearray) -> bool:
        """Apply a single EEPROM-row notification.

        Returns True when this row completes the full 32-row image.
        Rejects packets that aren't a full 11 bytes, that target an
        offset outside the 256-byte image, or whose offset is not
        row-aligned (rows are exactly 8 bytes per the OEM app's
        ``XMCeeprom.setRow``).
        """
        if len(payload) < 3 + EEPROM_ROW_SIZE:
            return False
        offset = int(payload[2]) & 0xFF
        if offset % EEPROM_ROW_SIZE != 0:
            return False
        if offset + EEPROM_ROW_SIZE > EEPROM_SIZE:
            return False
        for index in range(EEPROM_ROW_SIZE):
            self._data[offset + index] = payload[3 + index]
        self._rows_received |= 1 << (offset // EEPROM_ROW_SIZE)
        return self.all_received()

    def all_received(self) -> bool:
        """Return True once all 32 rows have been received."""
        return self._rows_received == EEPROM_ALL_ROWS_BITMASK

    def snapshot(self) -> EepromSnapshot:
        """Return a decoded view of the current image.

        Safe to call before the full image is reassembled — any field
        whose offset has not been received will read 0. Callers can
        check ``snapshot.complete`` to filter on full-image availability.
        """
        memory_positions: list[tuple[int, int, int, int]] = []
        for slot in range(6):
            base = EEPROM_OFFSET_MEM_BASE + slot * 8
            memory_positions.append(
                (
                    _word_be(self._data, base),
                    _word_be(self._data, base + 2),
                    _word_be(self._data, base + 4),
                    _word_be(self._data, base + 6),
                )
            )
        return EepromSnapshot(
            lock_flag=self._data[EEPROM_OFFSET_LOCK] & 0xFF,
            sync_mode=self._data[EEPROM_OFFSET_SYNC_MODE] & 0xFF,
            init_zwang=self._data[EEPROM_OFFSET_INIT_ZWANG] & 0xFF,
            pulse_mot1=_word_be(self._data, EEPROM_OFFSET_PULSE_MOT1),
            pulse_mot2=_word_be(self._data, EEPROM_OFFSET_PULSE_MOT2),
            pulse_mot3=_word_be(self._data, EEPROM_OFFSET_PULSE_MOT3),
            pulse_mot4=_word_be(self._data, EEPROM_OFFSET_PULSE_MOT4),
            memory_positions=tuple(memory_positions),
            teach_in_count=_word_be(self._data, EEPROM_OFFSET_TEACH_INS),
            factory_reset_count=_word_be(self._data, EEPROM_OFFSET_FACTORY_RESET),
            init_zwang_count=_word_be(self._data, EEPROM_OFFSET_INIT_ZWANG_COUNT),
            power_up_count=_word_be(self._data, EEPROM_OFFSET_POWER_UPS),
            wdt_resets=self._data[EEPROM_OFFSET_WDT_RESETS] & 0xFF,
            system_resets=self._data[EEPROM_OFFSET_SYSTEM_RESET] & 0xFF,
            other_resets=self._data[EEPROM_OFFSET_OTHER_RESET] & 0xFF,
            total_pulse_mot1=_long_be(self._data, EEPROM_OFFSET_TOTAL_PULSE_MOT1),
            total_pulse_mot2=_long_be(self._data, EEPROM_OFFSET_TOTAL_PULSE_MOT2),
            total_pulse_mot3=_long_be(self._data, EEPROM_OFFSET_TOTAL_PULSE_MOT3),
            total_pulse_mot4=_long_be(self._data, EEPROM_OFFSET_TOTAL_PULSE_MOT4),
            total_on_time=_long_be(self._data, EEPROM_OFFSET_TOTAL_ON_TIME),
            fahrt_ueberwachung=(
                self._data[EEPROM_OFFSET_FAHRT_UEBERWACHUNG1] & 0xFF,
                self._data[EEPROM_OFFSET_FAHRT_UEBERWACHUNG2] & 0xFF,
                self._data[EEPROM_OFFSET_FAHRT_UEBERWACHUNG3] & 0xFF,
                self._data[EEPROM_OFFSET_FAHRT_UEBERWACHUNG4] & 0xFF,
            ),
            h_bridge_over_temp=self._data[EEPROM_OFFSET_H_BRIDGE_OVER_TEMP] & 0xFF,
            complete=self.all_received(),
        )


# ---------------------------------------------------------------------------
# Position notification helpers
# ---------------------------------------------------------------------------


@dataclass
class MotorPositionPacket:
    """Decoded view of an XMCMotorData position notification.

    The OEM app's ``XMCMotorData`` constructor reads four motor positions
    as BE 16-bit values from bytes [3..4], [5..6], [7..8], [9..10] (the
    decompiled source mistakenly reads motor 2 from [6..7] which would
    overlap motor 1's MSB with motor 2's LSB — verified on-device to be
    a typo; the correct layout puts motor 2 at [7..8] and motor 3 at
    [9..10]). The ``flags`` byte is parsed for the init/sync status
    reported via ``isInitRequested()`` and ``isSyncActive()``.
    """

    flags: int
    init_requested: bool
    sync_active: bool
    motor1: int  # back/Kopf
    motor2: int  # legs/Oberschenkel
    motor3: int  # head/Nacken (3-motor+)
    motor4: int  # feet/Fuß   (4-motor)


def parse_position_notification(payload: bytes | bytearray) -> MotorPositionPacket | None:
    """Parse a VMAT position notification, returning ``None`` on no-match.

    Accepts the long format (``0x20, 0x3F, flags, M1hi, M1lo, M2hi, M2lo,
    M3hi, M3lo, M4hi, M4lo``) and the short format (``0x3F, flags, …``)
    captured by some nRF Connect traces. Returns ``None`` for packets
    that don't start with the known position-prefix bytes.
    """
    if not payload or len(payload) < 2:
        return None
    if len(payload) >= 7 and payload[0] == POSITION_NOTIFY_PREFIX and payload[1] == POSITION_NOTIFY_TYPE:
        if len(payload) < 11:
            return None
        flags = payload[2]
        motor1 = (payload[3] << 8) | payload[4]
        motor2 = (payload[5] << 8) | payload[6]
        motor3 = (payload[7] << 8) | payload[8]
        motor4 = (payload[9] << 8) | payload[10]
    elif payload[0] == POSITION_NOTIFY_SHORT_TYPE:
        if len(payload) < 10:
            return None
        flags = payload[1]
        motor1 = (payload[2] << 8) | payload[3]
        motor2 = (payload[4] << 8) | payload[5]
        motor3 = (payload[6] << 8) | payload[7]
        motor4 = (payload[8] << 8) | payload[9]
    else:
        return None
    return MotorPositionPacket(
        flags=flags,
        init_requested=bool(flags & XMCMOTOR_INIT_ZWANG_MASK),
        sync_active=bool(flags & XMCMOTOR_SYNC_STATUS_MASK),
        motor1=motor1,
        motor2=motor2,
        motor3=motor3,
        motor4=motor4,
    )


# ---------------------------------------------------------------------------
# Capability container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VibradormCapabilities:
    """Detected/expected capabilities of a VMAT controller.

    ``is_vmat_basic`` controls whether motor moves use single-byte
    commands on ``COMMAND`` (``0x1526``) — true for VMAT-basic and the
    RF-CBI variant — or the 2-byte CBI path. The other flags are
    surfaced as Home Assistant entity capability properties.
    """

    is_vmat_basic: bool = True
    uses_cbi_motor_commands: bool = False
    has_cbi_characteristic: bool = True
    has_mood_light: bool = False
    has_massage: bool = False
    has_floor_light: bool = True
    control_version: int | None = None
    motor_count: int | None = None
    xt_box: bool = False
