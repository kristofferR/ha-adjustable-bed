"""Constants for the Adjustable Bed integration."""

from dataclasses import dataclass, field
from enum import IntFlag
from typing import Final

DOMAIN: Final = "adjustable_bed"


@dataclass
class DetectionResult:
    """Result of bed type detection with confidence scoring.

    Attributes:
        bed_type: The detected bed type constant, or None if not detected
        confidence: Confidence score from 0.0 to 1.0:
            - 1.0: Unique UUID (Linak, Malouf NEW_OKIN, Reverie, Leggett Gen2)
            - 0.95: Manufacturer data match (e.g., DewertOkin Company ID)
            - 0.9: UUID + name pattern match or unique characteristic
            - 0.7: UUID + manufacturer data
            - 0.5: UUID only (ambiguous, shared by multiple bed types)
            - 0.3: Name pattern only (no UUID match)
        signals: List of detection signals that matched (e.g., ["uuid:linak", "name:bed"])
        ambiguous_types: List of other bed types that could match (for low confidence)
        detected_remote: Auto-detected remote code for Richmat beds
        manufacturer_id: BLE manufacturer Company ID if found
        requires_characteristic_check: True if post-connection check recommended
    """

    bed_type: str | None
    confidence: float
    signals: list[str] = field(default_factory=list)
    ambiguous_types: list[str] | None = None
    detected_remote: str | None = None
    manufacturer_id: int | None = None
    requires_characteristic_check: bool = False


@dataclass(frozen=True)
class ConnectionProfileSettings:
    """Connection timing profile settings for BLE connections."""

    max_retries: int
    retry_base_delay: float
    retry_jitter: float
    connection_timeout: float
    post_connect_delay: float

# Configuration keys
CONF_BED_TYPE: Final = "bed_type"
CONF_PROTOCOL_VARIANT: Final = "protocol_variant"
CONF_MOTOR_COUNT: Final = "motor_count"
CONF_HAS_MASSAGE: Final = "has_massage"
CONF_DISABLE_ANGLE_SENSING: Final = "disable_angle_sensing"
CONF_PREFERRED_ADAPTER: Final = "preferred_adapter"
CONF_CONNECTION_PROFILE: Final = "connection_profile"
CONF_MOTOR_PULSE_COUNT: Final = "motor_pulse_count"
CONF_MOTOR_PULSE_DELAY_MS: Final = "motor_pulse_delay_ms"
CONF_DISCONNECT_AFTER_COMMAND: Final = "disconnect_after_command"
CONF_IDLE_DISCONNECT_SECONDS: Final = "idle_disconnect_seconds"
CONF_POSITION_MODE: Final = "position_mode"
CONF_PASSIVE_POSITION_RECONCILIATION: Final = "passive_position_reconciliation"
# Global (not per-entry) toggle to suppress automatic Bluetooth discovery cards.
# Stored separately via discovery_settings, surfaced as a checkbox in the options
# flow. Manual "Add Integration" is unaffected.
CONF_DISABLE_DISCOVERY: Final = "disable_discovery"
CONF_OCTO_PIN: Final = "octo_pin"
CONF_RICHMAT_REMOTE: Final = "richmat_remote"
CONF_JENSEN_PIN: Final = "jensen_pin"
CONF_CB24_BED_SELECTION: Final = "cb24_bed_selection"
CONF_BLE_BOND_ESTABLISHED: Final = "ble_bond_established"
CONF_BACK_MAX_ANGLE: Final = "back_max_angle"
CONF_LEGS_MAX_ANGLE: Final = "legs_max_angle"
CONF_KAIDI_ROOM_ID: Final = "kaidi_room_id"
CONF_KAIDI_TARGET_VADDR: Final = "kaidi_target_vaddr"
CONF_KAIDI_PRODUCT_ID: Final = "kaidi_product_id"
CONF_KAIDI_SOFA_ACU_NO: Final = "kaidi_sofa_acu_no"
CONF_KAIDI_ADV_TYPE: Final = "kaidi_adv_type"
CONF_KAIDI_RESOLVED_VARIANT: Final = "kaidi_resolved_variant"
CONF_KAIDI_VARIANT_SOURCE: Final = "kaidi_variant_source"

# Default angle limits (from Linak beds)
DEFAULT_BACK_MAX_ANGLE: Final = 68.0
DEFAULT_LEGS_MAX_ANGLE: Final = 45.0
REVERIE_BACK_MAX_ANGLE: Final = 60.0

# Position mode values
POSITION_MODE_SPEED: Final = "speed"
POSITION_MODE_ACCURACY: Final = "accuracy"

# Connection profile values
CONNECTION_PROFILE_BALANCED: Final = "balanced"
CONNECTION_PROFILE_RELIABLE: Final = "reliable"

# Special value for auto adapter selection
ADAPTER_AUTO: Final = "auto"

# Bed types - Protocol-based naming (new)
# These are the canonical names organized by protocol characteristics
BED_TYPE_OKIN_HANDLE: Final = "okin_handle"  # Okin 6-byte via BLE handle
BED_TYPE_OKIN_UUID: Final = "okin_uuid"  # Okin 6-byte via UUID (requires pairing)
BED_TYPE_OKIN_7BYTE: Final = "okin_7byte"  # 7-byte via Okin service UUID
BED_TYPE_OKIN_NORDIC: Final = "okin_nordic"  # 7-byte via Nordic UART
BED_TYPE_OKIN_CB24: Final = "okin_cb24"  # CB24 protocol via Nordic UART (SmartBed by Okin)
BED_TYPE_OKIN_DOT: Final = "okin_dot"  # DOT PROTOCOL: CB24-style frames, FurniMove remote keycodes
BED_TYPE_OKIN_ORE: Final = "okin_ore"  # OREBedBleProtocol (A5 5A format, 00001000 service)
BED_TYPE_OKIN_CST: Final = "okin_cst"  # OKIN CSTProtocol (14-byte dual-field commands)
BED_TYPE_OKIN_RF_ECO_BT: Final = "okin_rf_eco_bt"  # OKIN Smart Remote single-actuator
BED_TYPE_LEGGETT_GEN2: Final = "leggett_gen2"  # Leggett Gen2 ASCII protocol
BED_TYPE_LEGGETT_OKIN: Final = "leggett_okin"  # Leggett Okin binary protocol
BED_TYPE_LEGGETT_WILINKE: Final = "leggett_wilinke"  # Leggett WiLinke 5-byte

OKIN_CST_POSITION_AXES: Final = frozenset({"back", "legs"})

# Bed types - Legacy naming (backwards compatibility)
# These map to the protocol-based types above
BED_TYPE_LINAK: Final = "linak"
BED_TYPE_RICHMAT: Final = "richmat"
BED_TYPE_SOLACE: Final = "solace"
BED_TYPE_MOTOSLEEP: Final = "motosleep"

BEDS_WITH_PASSIVE_POSITION_RECONCILIATION: Final = frozenset({BED_TYPE_LINAK})


def supports_passive_position_reconciliation(bed_type: str | None) -> bool:
    """Return True if the bed type supports passive position reconciliation."""
    return bed_type in BEDS_WITH_PASSIVE_POSITION_RECONCILIATION


def passive_position_reconciliation_default_enabled(bed_type: str | None) -> bool:
    """Return whether passive position reconciliation should default to enabled."""
    return supports_passive_position_reconciliation(bed_type)
BED_TYPE_REVERIE: Final = "reverie"
BED_TYPE_LEGGETT_PLATT: Final = "leggett_platt"  # -> leggett_gen2 or leggett_okin
BED_TYPE_OKIMAT: Final = "okimat"  # -> okin_uuid
BED_TYPE_KEESON: Final = "keeson"
BED_TYPE_ERGOMOTION: Final = "ergomotion"
BED_TYPE_JIECANG: Final = "jiecang"
BED_TYPE_DEWERTOKIN: Final = "dewertokin"  # -> okin_handle
BED_TYPE_OCTO: Final = "octo"
BED_TYPE_MATTRESSFIRM: Final = "mattressfirm"  # -> okin_nordic
BED_TYPE_NECTAR: Final = "nectar"  # -> okin_7byte
BED_TYPE_MALOUF_NEW_OKIN: Final = "malouf_new_okin"
BED_TYPE_MALOUF_LEGACY_OKIN: Final = "malouf_legacy_okin"
BED_TYPE_OKIN_FFE: Final = "okin_ffe"  # OKIN 13/15 series via FFE5 service (0xE6 prefix)
BED_TYPE_REVERIE_NIGHTSTAND: Final = "reverie_nightstand"  # Reverie Protocol 110
BED_TYPE_COMFORT_MOTION: Final = "comfort_motion"  # Comfort Motion / Lierda protocol
BED_TYPE_LIMOSS: Final = "limoss"  # Limoss / Stawett TEA-encrypted protocol
BED_TYPE_SERTA: Final = "serta"  # Serta Motion Perfect (uses Keeson protocol with serta variant)
BED_TYPE_BEDTECH: Final = "bedtech"  # BedTech 5-byte ASCII protocol
BED_TYPE_JENSEN: Final = "jensen"  # Jensen JMC400/LinON Entry (6-byte commands)
BED_TYPE_SLEEP_NUMBER: Final = "sleep_number"  # Sleep Number Climate 360 / Fuzion bamkey BLE
BED_TYPE_SLEEP_NUMBER_MCR: Final = "sleep_number_mcr"  # Sleep Number BAM/MCR BLE
BED_TYPE_OKIN_CB35: Final = "okin_cb35"  # DewertOkin CB35 Star (Sealy Posturematic, NUS 7-byte)
BED_TYPE_OKIN_64BIT: Final = "okin_64bit"  # OKIN 64-bit protocol (10-byte commands)
BED_TYPE_SLEEPYS_BOX15: Final = "sleepys_box15"  # Sleepy's Elite BOX15 protocol (9-byte with checksum)
BED_TYPE_SLEEPYS_BOX24: Final = "sleepys_box24"  # Sleepy's Elite BOX24 protocol (7-byte)
BED_TYPE_SLEEPYS_BOX25: Final = "sleepys_box25"  # Sleepy's Elite BOX25 Star (NUS multi-subsystem)
BED_TYPE_SVANE: Final = "svane"  # Svane LinonPI multi-service protocol
BED_TYPE_VIBRADORM: Final = "vibradorm"  # Vibradorm VMAT protocol
BED_TYPE_RONDURE: Final = "rondure"  # 1500 Tilt Base / Rondure Hump (8/9-byte FurniBus protocol)
BED_TYPE_REMACRO: Final = "remacro"  # Remacro protocol (CheersSleep/Jeromes/Slumberland/The Brick, 8-byte SynData)
BED_TYPE_COOLBASE: Final = "coolbase"  # Cool Base (Keeson BaseI5 with fan control)
BED_TYPE_SCOTT_LIVING: Final = "scott_living"  # Scott Living 9-byte protocol
BED_TYPE_SBI: Final = "sbi"  # SBI/Q-Plus (Costco) with position feedback
BED_TYPE_SUTA: Final = "suta"  # SUTA Smart Home AT protocol (ASCII + CRLF)
BED_TYPE_TIMOTION_AHF: Final = "timotion_ahf"  # TiMOTION AHF 11-byte bitmask protocol
BED_TYPE_KAIDI: Final = "kaidi"  # Kaidi custom mesh-over-GATT protocol (Rize/Floyd/ISleep)
BED_TYPE_LOGICDATA: Final = "logicdata"  # Logicdata SimplicityFrame (XXTEA+CRC16+SLIP)
BED_TYPE_DIAGNOSTIC: Final = "diagnostic"

# All supported bed types (includes both protocol-based and legacy names)
SUPPORTED_BED_TYPES: Final = [
    # Protocol-based types (new naming)
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_WILINKE,
    # Brand-specific types
    BED_TYPE_LINAK,
    BED_TYPE_RICHMAT,
    BED_TYPE_SOLACE,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_REVERIE,
    BED_TYPE_KEESON,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_OCTO,
    # Legacy aliases (for backwards compatibility with existing configs)
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OKIMAT,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_NECTAR,
    # Malouf protocols
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    # OKIN FFE series
    BED_TYPE_OKIN_FFE,
    # Reverie Nightstand (Protocol 110)
    BED_TYPE_REVERIE_NIGHTSTAND,
    # Comfort Motion / Lierda protocol
    BED_TYPE_COMFORT_MOTION,
    # Limoss / Stawett
    BED_TYPE_LIMOSS,
    # Serta Motion Perfect
    BED_TYPE_SERTA,
    # BedTech
    BED_TYPE_BEDTECH,
    # Jensen
    BED_TYPE_JENSEN,
    # Sleep Number Climate 360 / Fuzion
    BED_TYPE_SLEEP_NUMBER,
    # Sleep Number BAM / MCR
    BED_TYPE_SLEEP_NUMBER_MCR,
    # OKIN CB35 Star (Sealy Posturematic)
    BED_TYPE_OKIN_CB35,
    # OKIN 64-bit
    BED_TYPE_OKIN_64BIT,
    # Sleepy's Elite
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    # Sleepy's Elite BOX25 Star
    BED_TYPE_SLEEPYS_BOX25,
    # Svane
    BED_TYPE_SVANE,
    # Vibradorm
    BED_TYPE_VIBRADORM,
    # Rondure / 1500 Tilt Base
    BED_TYPE_RONDURE,
    # Remacro (CheersSleep / Jeromes / Slumberland / The Brick)
    BED_TYPE_REMACRO,
    # Cool Base (fan control)
    BED_TYPE_COOLBASE,
    # Scott Living (9-byte Keeson variant)
    BED_TYPE_SCOTT_LIVING,
    # SBI/Q-Plus (Costco, with position feedback)
    BED_TYPE_SBI,
    # SUTA Smart Home AT protocol
    BED_TYPE_SUTA,
    # TiMOTION AHF protocol
    BED_TYPE_TIMOTION_AHF,
    # Kaidi (Rize/Floyd/ISleep)
    BED_TYPE_KAIDI,
    # Logicdata SimplicityFrame (SILVERmotion)
    BED_TYPE_LOGICDATA,
]

# Mapping from legacy bed types to their protocol-based equivalents
# Used by controller_factory to resolve the correct controller
LEGACY_BED_TYPE_MAPPING: Final = {
    BED_TYPE_DEWERTOKIN: BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIMAT: BED_TYPE_OKIN_UUID,
    BED_TYPE_NECTAR: BED_TYPE_OKIN_7BYTE,
    BED_TYPE_MATTRESSFIRM: BED_TYPE_OKIN_NORDIC,
    # Note: leggett_platt not mapped here - requires variant detection in
    # controller_factory.py to determine gen2 (default), okin, or wilinke (mlrm)
}

# Standard BLE Device Information Service UUIDs
DEVICE_INFO_SERVICE_UUID: Final = "0000180a-0000-1000-8000-00805f9b34fb"
DEVICE_INFO_CHARS: Final = {
    "manufacturer_name": "00002a29-0000-1000-8000-00805f9b34fb",
    "model_number": "00002a24-0000-1000-8000-00805f9b34fb",
    "serial_number": "00002a25-0000-1000-8000-00805f9b34fb",
    "hardware_revision": "00002a27-0000-1000-8000-00805f9b34fb",
    "firmware_revision": "00002a26-0000-1000-8000-00805f9b34fb",
    "software_revision": "00002a28-0000-1000-8000-00805f9b34fb",
    "system_id": "00002a23-0000-1000-8000-00805f9b34fb",
}

# Linak specific UUIDs
LINAK_CONTROL_SERVICE_UUID: Final = "99fa0001-338a-1024-8a49-009c0215f78a"
LINAK_CONTROL_CHAR_UUID: Final = "99fa0002-338a-1024-8a49-009c0215f78a"

LINAK_POSITION_SERVICE_UUID: Final = "99fa0020-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_BACK_UUID: Final = "99fa0028-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_LEG_UUID: Final = "99fa0027-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_HEAD_UUID: Final = "99fa0026-338a-1024-8a49-009c0215f78a"
LINAK_POSITION_FEET_UUID: Final = "99fa0025-338a-1024-8a49-009c0215f78a"

# Linak position calibration
LINAK_BACK_MAX_POSITION: Final = 820
LINAK_BACK_MAX_ANGLE: Final = 68
LINAK_LEG_MAX_POSITION: Final = 548
LINAK_LEG_MAX_ANGLE: Final = 45
LINAK_HEAD_MAX_POSITION: Final = 820
LINAK_HEAD_MAX_ANGLE: Final = 68
LINAK_FEET_MAX_POSITION: Final = 548
LINAK_FEET_MAX_ANGLE: Final = 45

# Nordic UART Service UUIDs (used by multiple protocols)
NORDIC_UART_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NORDIC_UART_WRITE_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NORDIC_UART_READ_CHAR_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Richmat specific UUIDs
# Nordic variant (simple single-byte commands)
RICHMAT_NORDIC_SERVICE_UUID: Final = NORDIC_UART_SERVICE_UUID
RICHMAT_NORDIC_CHAR_UUID: Final = NORDIC_UART_WRITE_CHAR_UUID

# BedTech specific UUIDs (FEE9 service with d44bc439 characteristic)
# Note: Shares FEE9 service with Richmat WiLinke but uses different packet format.
# Confirmed BedTech QRRM advertisements expose the controller MAC as manufacturer
# data under company ID 0x4C57 (the little-endian form of the 57:4C MAC prefix).
# Richmat/Casper QRRM captures using the RGB-strip protocol omit this field.
BEDTECH_SERVICE_UUID: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
BEDTECH_WRITE_CHAR_UUID: Final = "d44bc439-abfd-45a2-b575-925416129600"
BEDTECH_MANUFACTURER_ID: Final = 0x4C57

# WiLinke variants (5-byte commands with checksum)
# Source: com.desarketing.gmmotor (Germany Motions) APK blutter decompilation
# The app supports 6 BLE variants (Nordic + W1-W5), we track the WiLinke ones here
# W1 is the default fallback when no specific service is found
RICHMAT_WILINKE_W1_SERVICE_UUID: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
# W4 uses the generic FFF0 short UUID, which countless non-bed BLE devices also
# advertise (a "NO_DVR-*" camera system in issue #418, plus LED strips, scales,
# etc.), so it is NOT bed-unique. All known W4 beds are Germany Motions units
# named "DHN-*" (issue #163; confirmed against the GM Bed Control 4.6.0 APK,
# whose scan is unfiltered and which identifies beds by name/remote code), so
# detection must require a corroborating Richmat name signal before treating a
# W4 advertisement as a bed. FFF0 stays in manifest.json because SUTA and the
# Keeson Sino fallback also discover via it (both name-guarded too).
RICHMAT_WILINKE_W4_SERVICE_UUID: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
# W5 uses a Telink-style custom 128-bit base (the "0xe0ff" is the little-endian
# encoding of the generic 0xFFE0 short UUID). That base is shared by many non-bed
# Telink-chip devices (e.g. a "Nokia-*" headset reported in issue #382), so this
# UUID is NOT bed-unique: detection must require a corroborating Richmat name
# signal before treating a W5 advertisement as a bed, and it is intentionally
# left out of manifest.json's passive bluetooth discovery matchers.
RICHMAT_WILINKE_W5_SERVICE_UUID: Final = "0000e0ff-3c17-d293-8e48-14fe2e4da212"
RICHMAT_WILINKE_SERVICE_UUIDS: Final = [
    "8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7",  # Custom (legacy, index 0)
    "0000fee9-0000-1000-8000-00805f9b34fb",  # W1 (index 1) - default fallback
    "0000fee9-0000-1000-8000-00805f9b34bb",  # W2 (index 2) - note different base UUID suffix
    "0000ffe0-0000-1000-8000-00805f9b34fb",  # W3 (index 3)
    RICHMAT_WILINKE_W4_SERVICE_UUID,  # W4 (index 4) - Germany Motions DHN-*, name-guarded
    RICHMAT_WILINKE_W5_SERVICE_UUID,  # W5 (index 5) - shared Telink base, name-guarded
]
RICHMAT_WILINKE_CHAR_UUIDS: Final = [
    # (write_char, notify_char) pairs matching service UUIDs above
    ("d44bc439-abfd-45a2-b575-925416129600", "d44bc439-abfd-45a2-b575-925416129601"),  # Custom
    ("d44bc439-abfd-45a2-b575-925416129600", "d44bc439-abfd-45a2-b575-925416129601"),  # W1
    ("d44bc439-abfd-45a2-b575-925416129622", "d44bc439-abfd-45a2-b575-925416129611"),  # W2
    ("0000ffe2-0000-1000-8000-00805f9b34fb", "0000ffe1-0000-1000-8000-00805f9b34fb"),  # W3
    ("0000fff2-0000-1000-8000-00805f9b34fb", "0000fff1-0000-1000-8000-00805f9b34fb"),  # W4
    ("00000002-3c17-d293-8e48-14fe2e4da212", "00000003-3c17-d293-8e48-14fe2e4da212"),  # W5
]

# Keeson specific UUIDs
# JSON/A00A variant (Juna Sleep, Linx, Ergo Health / ConnectedBed family)
KEESON_JSON_SERVICE_UUID: Final = "0000a00a-0000-1000-8000-00805f9b34fb"
KEESON_JSON_WRITE_CHAR_UUID: Final = "0000b002-0000-1000-8000-00805f9b34fb"
KEESON_JSON_NOTIFY_CHAR_UUID: Final = "0000b004-0000-1000-8000-00805f9b34fb"

# KSBT variant - primary UUIDs (Nordic UART Service)
KEESON_KSBT_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
KEESON_KSBT_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Extended Nordic UART variant (Ergomotion/SFD beds)
KEESON_EXTENDED_NORDIC_SERVICE_UUID: Final = "6e400020-b5a3-f393-e0a9-e50e24dcca9e"
KEESON_EXTENDED_NORDIC_CHAR_UUID: Final = "6e400021-b5a3-f393-e0a9-e50e24dcca9e"

# KSBT fallback service/characteristic UUIDs
# Some KSBT devices advertise with different service UUIDs but still use KSBT protocol
KEESON_KSBT_FALLBACK_GATT_PAIRS: Final = [
    # Fallback 1: Extended Nordic UART (Ergomotion 4.0, SFD beds)
    ("6e400020-b5a3-f393-e0a9-e50e24dcca9e", "6e400021-b5a3-f393-e0a9-e50e24dcca9e"),
    # Fallback 2: FFE5/FFE9 (same as Base service)
    ("0000ffe5-0000-1000-8000-00805f9b34fb", "0000ffe9-0000-1000-8000-00805f9b34fb"),
    # Fallback 3: FFE0/FFE1
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe1-0000-1000-8000-00805f9b34fb"),
]

# BaseI4/BaseI5 variant - primary UUIDs
KEESON_BASE_SERVICE_UUID: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
KEESON_BASE_WRITE_CHAR_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
KEESON_BASE_NOTIFY_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
KEESON_BASE_NOTIFY_CHAR_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Keeson fallback service/characteristic UUIDs for improved compatibility
# Some Keeson beds use different UUIDs - try these if primary fails
KEESON_FALLBACK_GATT_PAIRS: Final = [
    # Primary: 0000ffe5/0000ffe9 (already defined above)
    # Fallback 1: 0000fff0/0000fff2
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb"),
    # Fallback 2: 0000ffb0/0000ffb2
    ("0000ffb0-0000-1000-8000-00805f9b34fb", "0000ffb2-0000-1000-8000-00805f9b34fb"),
]

# BetterLiving-style OKIN-BLE beds advertise both fallback service UUIDs
KEESON_BETTERLIVING_SERVICE_UUIDS: Final = frozenset({
    "0000fff0-0000-1000-8000-00805f9b34fb",
    "0000ffb0-0000-1000-8000-00805f9b34fb",
})

# CB1322 sub-variant manufacturer name markers (lowercase for comparison)
CB1322_MANUFACTURER_MARKERS: Final = ("ble-4.0 module", "dewertokin")

# Ergomotion specific UUIDs (same protocol as Keeson Base, but with position feedback)
ERGOMOTION_SERVICE_UUID: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
ERGOMOTION_WRITE_CHAR_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
ERGOMOTION_NOTIFY_CHAR_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Ergomotion position calibration (based on AlexxIT/Ergomotion implementation)
# Position values are 16-bit little-endian, 0xFFFF means inactive
ERGOMOTION_MAX_POSITION: Final = 100  # Position values normalized to 0-100
ERGOMOTION_MAX_MASSAGE: Final = 6  # Massage levels 0-6

# Solace specific UUIDs
SOLACE_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
SOLACE_CHAR_UUID: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"

# MotoSleep specific UUIDs (same as Solace but different protocol)
MOTOSLEEP_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
MOTOSLEEP_CHAR_UUID: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"

# SUTA Smart Home specific UUIDs (AT command protocol)
# The app discovers writable/notifiable characteristics dynamically by properties.
# FFF1 is used as a fallback write characteristic when dynamic discovery is unavailable.
SUTA_SERVICE_UUID: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
SUTA_DEFAULT_WRITE_CHAR_UUID: Final = "0000fff1-0000-1000-8000-00805f9b34fb"

# TiMOTION AHF protocol UUIDs (Nordic UART Service)
TIMOTION_AHF_SERVICE_UUID: Final = NORDIC_UART_SERVICE_UUID
TIMOTION_AHF_WRITE_CHAR_UUID: Final = NORDIC_UART_WRITE_CHAR_UUID
TIMOTION_AHF_NOTIFY_CHAR_UUID: Final = NORDIC_UART_READ_CHAR_UUID

# Kaidi custom mesh-over-GATT protocol (Rize/Floyd/ISleep)
# Discovery is driven primarily by manufacturer data with BLE Company ID 0xFFFF
# and marker 0xC0FF. Some devices also surface the "Mouselet" name and/or the
# FFC0 discovery UUID, but those are supporting signals rather than the source
# of truth. The actual command transport is on the 9e5d1e47-... service.
KAIDI_MANUFACTURER_COMPANY_ID: Final = 0xFFFF
KAIDI_DISCOVERY_SERVICE_UUID: Final = "0000ffc0-0000-1000-8000-00805f9b34fb"
KAIDI_MESH_SERVICE_UUID: Final = "9e5d1e47-5c13-43a0-8635-82adffc0386f"
KAIDI_WRITE_CHAR_UUID: Final = "9e5d1e47-5c13-43a0-8635-82adffc1386f"
KAIDI_NOTIFY_CHAR_UUID: Final = "9e5d1e47-5c13-43a0-8635-82adffc2386f"
KAIDI_NAME_PATTERNS: Final = ("mouselet",)
# Known Kaidi OUI prefixes from decompiled app (getBtAddr MAC checks)
KAIDI_MAC_PREFIXES: Final = ("00:95:69", "F0:AC:D7")
KAIDI_JOIN_PASSWORD: Final = b"1122"
KAIDI_BROADCAST_VADDR: Final = 0xFFFFFFFF

# Logicdata SimplicityFrame (SILVERmotion) - LogicLink BLE protocol
# XXTEA encrypted, CRC16, SLIP framed
LOGICDATA_SERVICE_UUID: Final = "b9934c43-5c91-462b-80a1-30fccc29d758"
LOGICDATA_CHAR_UUID: Final = "b9934c44-5c91-462b-80a1-30fccc29d758"
MANUFACTURER_ID_LOGICDATA: Final = 1351  # 0x0547

# Leggett & Platt specific UUIDs
# Gen2 variant (a.k.a. LP Comfort Connect, control box 209-M001, ESP32-based;
# Richmat-derived ASCII commands)
LEGGETT_GEN2_SERVICE_UUID: Final = "45e25100-3171-4cfc-ae89-1d83cf8d8071"
LEGGETT_GEN2_WRITE_CHAR_UUID: Final = "45e25101-3171-4cfc-ae89-1d83cf8d8071"
LEGGETT_GEN2_READ_CHAR_UUID: Final = "45e25103-3171-4cfc-ae89-1d83cf8d8071"
# LP Comfort Connect beds advertise NO service UUID — only manufacturer data
# under company ID 0x092D whose payload begins with ASCII "XP" or "CP". The LP
# Control app (com.leggett.android.universal) recognizes these beds purely by
# this prefix (isGen2Box()); the company ID is an additional filter.
MANUFACTURER_ID_LEGGETT_GEN2: Final = 0x092D  # 2349
LEGGETT_GEN2_MANUFACTURER_PREFIXES: Final = (b"XP", b"CP")

# Okin variant (requires pairing)
LEGGETT_OKIN_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
LEGGETT_OKIN_CHAR_UUID: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"

# Leggett & Platt Richmat variant (WiLinke protocol, discrete massage commands)
# Uses same service/char as Richmat WiLinke but with L&P-specific features
LEGGETT_RICHMAT_SERVICE_UUID: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
LEGGETT_RICHMAT_CHAR_UUID: Final = "d44bc439-abfd-45a2-b575-925416129600"

# Reverie specific UUIDs (Protocol 108 - XOR checksum)
REVERIE_SERVICE_UUID: Final = "1b1d9641-b942-4da8-89cc-98e6a58fbd93"
REVERIE_CHAR_UUID: Final = "6af87926-dc79-412e-a3e0-5f85c2d55de2"

# Reverie Nightstand specific UUIDs (Protocol 110 - direct writes)
# Verified from ReverieBLEProtocolV1.java and PositionController.java
REVERIE_NIGHTSTAND_SERVICE_UUID: Final = "db801000-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_HEAD_POSITION_UUID: Final = "db801041-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_FOOT_POSITION_UUID: Final = "db801042-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_LUMBAR_UUID: Final = "db801040-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID: Final = "db801021-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID: Final = "db801022-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID: Final = "db801020-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_HEAD_WAVE_UUID: Final = "db801061-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_FOOT_WAVE_UUID: Final = "db801060-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID: Final = "db801080-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_LED_UUID: Final = "db8010a0-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_RGB_UUID: Final = "db8010a7-f324-29c3-38d1-85c0c2e86885"
REVERIE_NIGHTSTAND_PRESETS_UUID: Final = "db8010d0-f324-29c3-38d1-85c0c2e86885"

# Okimat specific UUIDs (same as Leggett Okin - requires pairing)
OKIMAT_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
OKIMAT_WRITE_CHAR_UUID: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
OKIMAT_NOTIFY_CHAR_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"

# OKIN Smart Remote CSS service observed on RF ECO BT / MEGAMAT single-actuator devices
OKIN_SMART_REMOTE_CSS_SERVICE_UUID: Final = "90311623-25fa-3346-12ef-3cfb7a2556ac"
OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID: Final = "90311625-25fa-3346-12ef-3cfb7a2556ac"
OKIN_SMART_REMOTE_CSS_NOTIFY_CHAR_UUID: Final = "90311725-25fa-3346-12ef-3cfb7a2556ac"

# Nordic DFU service observed on some newer OKIN dual-stack controllers. It is
# not a control surface, but helps distinguish full bed controllers from the
# RF ECO BT single-actuator profile when both expose OKIN Smart Remote CSS.
NORDIC_DFU_SERVICE_UUID: Final = "00001530-1212-efde-1523-785feabcd123"

# OKIN position feedback UUIDs (used by Lucid, some Okimat beds)
# Reference: https://github.com/richardhopton/smartbed-mqtt/issues/53
OKIN_POSITION_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
OKIN_POSITION_NOTIFY_CHAR_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

# OKIN position calibration
# Position data is in bytes 3-6 of notification (2 bytes each, little-endian)
# Head: raw 0-16000 maps to 0-60 degrees
# Foot: raw 0-12000 maps to 0-45 degrees
OKIN_HEAD_MAX_RAW: Final = 16000
OKIN_HEAD_MAX_ANGLE: Final = 60.0
OKIN_FOOT_MAX_RAW: Final = 12000
OKIN_FOOT_MAX_ANGLE: Final = 45.0

# Jiecang specific UUIDs (Glide beds, Dream Motion app)
JIECANG_CHAR_UUID: Final = "0000ff01-0000-1000-8000-00805f9b34fb"

# Comfort Motion / Lierda specific UUIDs (Full Jiecang protocol)
# Verified from BluetoothLeService.java and MainActivity.java
COMFORT_MOTION_SERVICE_UUID: Final = "0000ff12-0000-1000-8000-00805f9b34fb"
COMFORT_MOTION_WRITE_CHAR_UUID: Final = "0000ff01-0000-1000-8000-00805f9b34fb"
COMFORT_MOTION_READ_CHAR_UUID: Final = "0000ff02-0000-1000-8000-00805f9b34fb"
COMFORT_MOTION_BTNAME_CHAR_UUID: Final = "0000ff06-0000-1000-8000-00805f9b34fb"
# Lierda3 variant (LOGICDATA MOTIONrelax)
COMFORT_MOTION_LIERDA3_SERVICE_UUID: Final = "0000fe60-0000-1000-8000-00805f9b34fb"
COMFORT_MOTION_LIERDA3_WRITE_CHAR_UUID: Final = "0000fe61-0000-1000-8000-00805f9b34fb"
COMFORT_MOTION_LIERDA3_READ_CHAR_UUID: Final = "0000fe62-0000-1000-8000-00805f9b34fb"
COMFORT_MOTION_LIERDA3_BTNAME_CHAR_UUID: Final = "0000fe63-0000-1000-8000-00805f9b34fb"
# Peilin variant (secondary protocol)
COMFORT_MOTION_PEILIN_SERVICE_UUID: Final = "88121427-11e2-52a2-4615-ff00dec16800"
COMFORT_MOTION_PEILIN_CHAR_UUID: Final = "88121427-11e2-52a2-4615-ff00dec16801"

# Limoss / Stawett specific UUIDs (TEA-encrypted 10-byte packets)
# Service/characteristic are shared with other protocols, so detection primarily
# relies on device name patterns ("limoss", "stawett").
LIMOSS_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
LIMOSS_CHAR_UUID: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"

# DewertOkin specific (A H Beard, HankookGallery beds)
# Legacy handle from older traces. Handles are device/firmware-specific; the
# controller writes to the stable shared Okin characteristic UUID instead.
DEWERTOKIN_WRITE_HANDLE: Final = 0x0013

# DewertOkin manufacturer data (BLE Company ID)
# Source: com.dewertokin.okinsmartcomfort app disassembly
MANUFACTURER_ID_DEWERTOKIN: Final = 1643  # 0x066B

# OKIN Automotive manufacturer data (BLE Company ID)
# Source: Bluetooth SIG assigned numbers, SmartBed by Okin app
# Used by SmartBed devices that advertise manufacturer data instead of service UUIDs
MANUFACTURER_ID_OKIN: Final = 89  # 0x0059

# DewertOkin service UUID (unique to FurniMove/DewertOkin devices)
# This UUID can uniquely identify DewertOkin beds regardless of device name
DEWERTOKIN_SERVICE_UUID: Final = "00001523-0000-1000-8000-00805f9b34fb"

# DewertOkin RF Gateway settings service. Devices with BLE Device Information
# model "Bluetooth RF-Gateway" expose this name characteristic as the app's
# signal to wrap normal Okin commands in 8-byte RF frames.
DEWERTOKIN_RF_GATEWAY_MODEL: Final = "Bluetooth RF-Gateway"
DEWERTOKIN_RF_GATEWAY_SERVICE_UUID: Final = "92111420-72ab-4564-62ef-2a881286a6b0"
DEWERTOKIN_RF_GATEWAY_DEVICE_NAME_CHAR_UUID: Final = (
    "92111422-72ab-4564-62ef-2a881286a6b0"
)

# Serta Motion Perfect III specific
# Uses handle-based writes rather than UUID
SERTA_WRITE_HANDLE: Final = 0x0020

# Octo specific UUIDs
# Standard Octo variant
OCTO_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
OCTO_CHAR_UUID: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Octo Remote Star2 variant
OCTO_STAR2_SERVICE_UUID: Final = "0000aa5c-0000-1000-8000-00805f9b34fb"
OCTO_STAR2_CHAR_UUID: Final = "00005a55-0000-1000-8000-00805f9b34fb"

# Octo PIN keep-alive interval (seconds)
# Octo beds drop BLE connection after ~30s without PIN re-authentication
OCTO_PIN_KEEPALIVE_INTERVAL: Final = 25

# Octo light auto-off timeout (seconds)
# Octo under-bed lights automatically turn off after 5 minutes (hardware behavior)
OCTO_LIGHT_AUTO_OFF_SECONDS: Final = 300

# Octo variant identifiers (dict defined later after VARIANT_AUTO)
OCTO_VARIANT_STANDARD: Final = "standard"
OCTO_VARIANT_STAR2: Final = "star2"

# Mattress Firm 900 / Okin Nordic specific UUIDs
# Protocol reverse-engineered by David Delahoz (https://github.com/daviddelahoz/BLEAdjustableBase)
# Uses Nordic UART Service with custom 7-byte command format
MATTRESSFIRM_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
MATTRESSFIRM_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
MATTRESSFIRM_WRITE_CHAR_UUID: Final = MATTRESSFIRM_CHAR_UUID  # Alias for protocol clarity

# Okin CB24 bed selection values
# Used by SmartBed by Okin for split-king/dual bed configurations
# Source: com.okin.bedding.smartbedwifi ANALYSIS.md
CB24_BED_SELECTION_DEFAULT: Final = 0x00  # Default/single bed
CB24_BED_SELECTION_A: Final = 0xAA  # Bed A (left side)
CB24_BED_SELECTION_B: Final = 0xBB  # Bed B (right side)

# Nectar specific UUIDs
# Protocol reverse-engineered by MaximumWorf (https://github.com/MaximumWorf/homeassistant-nectar)
# Uses OKIN service UUID but with 7-byte direct command format (similar to Mattress Firm 900)
# Note: Shares service UUID with Okimat but uses different command protocol
NECTAR_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
NECTAR_WRITE_CHAR_UUID: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
NECTAR_NOTIFY_CHAR_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"

# OKIN ORE (OREBedBleProtocol) specific UUIDs
# Protocol reverse-engineered from com.ore.bedding.glideawaymontion APK
# Uses A5 5A packet format with checksum, unique 00001000 service UUID
# Detection: Service UUID or scan record bytes 9-10 = 0x4F 0x4B ("OK")
OKIN_ORE_SERVICE_UUID: Final = "00001000-0000-1000-8000-00805f9b34fb"
OKIN_ORE_WRITE_CHAR_UUID: Final = "00001001-0000-1000-8000-00805f9b34fb"
OKIN_ORE_READ_CHAR_UUID: Final = "00001002-0000-1000-8000-00805f9b34fb"

# Malouf NEW_OKIN specific UUIDs
# Protocol reverse-engineered from Malouf Base app
# Uses a unique advertised service UUID for detection plus Nordic UART for commands
MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID: Final = "01000001-0000-1000-8000-00805f9b34fb"
MALOUF_NEW_OKIN_WRITE_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
MALOUF_NEW_OKIN_NOTIFY_CHAR_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Malouf LEGACY_OKIN specific UUIDs
# Uses FFE5 service (similar to Keeson) but with different 9-byte command format
MALOUF_LEGACY_OKIN_SERVICE_UUID: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
MALOUF_LEGACY_OKIN_NOTIFY_CHAR_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Detection name patterns for beds sharing the OKIN service UUID
# Multiple bed types share the same UUID (62741523-...), so name patterns help disambiguate:
# - Nectar (7-byte protocol)
# - Okimat (6-byte protocol)
# - Leggett & Platt Okin variant (6-byte protocol, same as Okimat)
# - OKIN 64-bit (10-byte protocol with 64-bit bitmasks)
# Detection priority: name patterns first, then UUID fallback to Okimat
LEGGETT_OKIN_NAME_PATTERNS: Final = ("leggett", "l&p")
LEGGETT_RICHMAT_NAME_PATTERNS: Final = ("mlrm",)  # MlRM prefix beds
# Okimat devices: "Okimat", "OKIN RF", "OKIN BLE", "OKIN luis", or
# "Smartbed" (Malouf/Lucid/CVB beds using OKIN protocol).
# "OKIN-Receiver" / "OKIN - Receiver" stays in OKIMAT_NAME_ONLY_PATTERNS
# because the shared OKIN service UUID does not disambiguate the protocol.
# Generic "OKIN-XXXXXX" names are ambiguous: confirmed Nectar 7-byte bases can
# advertise this way too, so detection handles that prefix as low-confidence.
OKIMAT_NAME_PATTERNS: Final = (
    "okimat",
    "okin rf",
    "okin ble",
    "okin luis",
    "smartbed",
)
# Name-only matches must stay narrower than OKIMAT_NAME_PATTERNS because some
# OKIN families only become distinguishable once service UUIDs/manufacturer data
# are present.
OKIMAT_NAME_ONLY_PATTERNS: Final = ("okin-receiver", "okin - receiver", "okin receiver")
OKIN_GENERIC_NAME_PATTERNS: Final = ("okin-",)

# OKIN 64-bit name patterns (from com.okin.bedding.adjustbed app disassembly)
# Note: Most OKIN 64-bit devices don't have distinctive names - they require
# post-connection characteristic detection (presence of 62741625 read char)
OKIN_64BIT_NAME_PATTERNS: Final[tuple[str, ...]] = ()  # No reliable name patterns found

# BedTech name patterns (shares FEE9 service UUID with Richmat WiLinke)
# Keep this narrow: model-number aliases like BT6500 are also seen on beds
# that behave as Richmat WiLinke and should not be hard-forced to BedTech.
BEDTECH_NAME_PATTERNS: Final = ("bedtech",)

# DewertOkin name patterns (A H Beard, Hankook Gallery devices)
# Source: com.dewertokin.okinsmartcomfort app disassembly
# Note: "furnimove" is the app name but not a reliable device pattern
DEWERTOKIN_NAME_PATTERNS: Final = (
    "dewertokin",
    "dewert",
    "a h beard",
    "hankook",
)

# OKIN FFE name patterns (OKIN 13/15 series using FFE5 service with 0xE6 prefix)
# These use the same FFE5 service UUID as Keeson but with different command prefix
# Note: Generic "okin" pattern should match OKIN devices that don't match OKIMAT patterns
OKIN_FFE_NAME_PATTERNS: Final = ("okin", "cb-", "cb.")

# Serta/Ergomotion name patterns (big-endian variant of Keeson protocol)
# Uses same FFE5 service UUID as Keeson but with big-endian byte order
# Covers: Serta MP Remote, Ergomotion 4.0, and related OEM beds
SERTA_NAME_PATTERNS: Final = ("serta", "motion perfect", "ergomotion", "hump")

# Linak name patterns for devices that don't advertise service UUIDs
# Some Linak beds only advertise "Bed XXXX" (4 digits) without service UUIDs
LINAK_NAME_PATTERNS: Final = ("bed ",)

# Keeson name patterns for devices that may not advertise the specific service UUID
# - base-i4.XXXXXXXX (e.g., base-i4.00002574)
# - base-i5.XXXXXXXX (e.g., base-i5.00000682) - Note: base-i5 can also be Cool Base
# - KSBTXXXXCXXXXXX (e.g., KSBT03C000015046)
# - ORE-XXXXXXXXXXX (e.g., ORE-ac2170000d) - Dynasty, INNOVA beds (use ORE variant)
# - smart_dfu - Beautyrest Baselogic Platinum (Keeson MC232FD, KSBT04C protocol)
KEESON_NAME_PATTERNS: Final = ("base-i4.", "base-i5.", "ksbt", "ore-", "smart_dfu")

# BetterLiving / related OKIN app naming that uses Keeson-Sino packet format (E5 FE 16, big-endian)
# Source: com.ore.betterliving2 app disassembly
KEESON_SINO_NAME_PATTERNS: Final = ("okin-ble",)

# Cool Base name patterns (Keeson BaseI5 with fan control)
# From BleConnect.java: limitedDevice = "base-i5"
COOLBASE_NAME_PATTERNS: Final = ("base-i5",)

# Richmat Nordic name patterns (e.g., QRRM157052, Sleep Function 2.0, X1RM beds)
# Also includes DHN- prefix (Germany Motions beds using FFF0 service)
RICHMAT_NAME_PATTERNS: Final = ("qrrm", "sleep function", "x1rm", "dhn-")

# Ergomotion name patterns
# - "ergomotion", "ergo" (generic)
# - "serta-i" prefix for Serta-branded ErgoMotion beds (e.g., Serta-i490350)
ERGOMOTION_NAME_PATTERNS: Final = ("ergomotion", "ergo", "serta-i")

# Octo name patterns
# Source: blenames.json from de.octoactuators.octosmartcontrolapp APK
# These are the official BLE device name prefixes for Octo controllers:
# - RTV: Lift 1M
# - RC2: Receiver II
# - MC2: Micro 2
# - OCTOBrick: Brick 1
# - MC1: Micro 1
# - L2M: Lift 2M
# - CLI: Cosy Lift
# - OCTOIQ: IQ Redesign
# - OCTOBrick2: Brick 2
# - RC3: Receiver II 3M
# - BMB: BrickMini Basic
# - BMS: BrickMini Memo
# - BM3: BrickMini Basic 3M
# - da1458x: Dialog Semiconductor BLE SoC used in some receivers
OCTO_NAME_PATTERNS: Final = (
    "rtv",
    "rc2",
    "mc2",
    "octobrick",
    "mc1",
    "l2m",
    "cli",
    "octoiq",
    "rc3",
    "bmb",
    "bms",
    "bm3",
    "da1458x",
)

# Solace/Motion Bed name patterns (from Motion Bed app reverse engineering)
# These help distinguish Solace beds from Octo beds which share the same UUID
# - QMS-* (QMS-IQ, QMS-I06, QMS-I16, QMS-L04, QMS-NQ, QMS-MQ, QMS-KQ-H, QMS-DFQ, QMS-DQ, etc.)
# - QMS2, QMS3, QMS4 (no hyphen variants)
# - S3-*, S4-*, S5-*, S6-* (model series)
# - SealyMF (Sealy Motion Flex)
SOLACE_NAME_PATTERNS: Final = (
    "qms-",
    "qms2",
    "qms3",
    "qms4",
    "s3-",
    "s4-",
    "s5-",
    "s6-",
    "sealymf",
)

# Malouf name patterns
# Malouf beds typically have "malouf" in the device name
MALOUF_NAME_PATTERNS: Final = ("malouf",)

# Sleepy's Elite name patterns (MFRM = Mattress Firm)
# These beds use the Sleepy's Elite app (com.okin.bedding.sleepy)
SLEEPYS_NAME_PATTERNS: Final = ("sleepy", "mfrm")

# DewertOkin Star controller name patterns (BOX25 Star / CB35 Star)
# Devices advertise as "Star" + suffix (e.g., "Star352201011800")
# Source: com.okin.bedding.sleepy (Sleepy's Elite) BOX25 Star analysis
# Also used by Sealy Posturematic CB35 (com.okin.sealy)
SLEEPYS_BOX25_NAME_PATTERNS: Final = ("star",)

# Jensen name patterns (JMC400 / LinON Entry)
# Source: com.hilding.jbg_ble APK analysis
JENSEN_NAME_PATTERNS: Final = ("jmc",)  # JMC400, JMC300, etc.

# SUTA Smart Home name patterns.
# Note: The integration currently targets the bed-frame AT protocol (FFF0 service).
# Accessory/mattress subtypes use a different binary protocol and are excluded.
SUTA_NAME_PATTERNS: Final = ("suta-",)
SUTA_UNSUPPORTED_NAME_PREFIXES: Final = (
    "suta-moon",
    "suta-temp",
    "suta-rbhc",
    "suta-drawer",
    "suta-storage",
    "suta-sofa",
    "suta-yogabed",
    "suta-rollsofa",
)

# TiMOTION AHF name patterns
TIMOTION_AHF_NAME_PATTERNS: Final = ("ahf",)

# Limoss / Stawett name patterns
# Source: com.limoss.limossremote and com.stawett APK analysis
LIMOSS_NAME_PATTERNS: Final = ("limoss", "stawett")
# Sleepy's Elite BOX24 protocol UUIDs (OKIN 64-bit service)
SLEEPYS_BOX24_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
SLEEPYS_BOX24_WRITE_CHAR_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"

# Jensen specific UUIDs (JMC400 / LinON Entry)
# Protocol reverse-engineered from com.hilding.jbg_ble APK
# Uses simple 6-byte command format with no checksum
JENSEN_SERVICE_UUID: Final = "00001234-0000-1000-8000-00805f9b34fb"
JENSEN_CHAR_UUID: Final = "00001111-0000-1000-8000-00805f9b34fb"

# Sleep Number Climate 360 / FlexFit specific UUIDs (Fuzion bamkey protocol)
# Protocol reverse-engineered from com.selectcomfort.SleepIQ APK
# Commands are UTF-8 text written to the BamKey characteristic and responses
# arrive as notifications in PASS:/FAIL: form on the same characteristic.
SLEEP_NUMBER_SERVICE_UUID: Final = "09d23fae-90e6-44c2-95b6-0b3d0f1abf25"
SLEEP_NUMBER_BAMKEY_CHAR_UUID: Final = "421e00f3-ae76-4c49-ab6e-39e4df4a5333"
SLEEP_NUMBER_AUTH_CHAR_UUID: Final = "8d4675a5-b5fa-42b2-b587-0ee71c46b709"
SLEEP_NUMBER_TRANSFER_INFO_CHAR_UUID: Final = "e8d06e2a-c987-48f8-93a8-4d18d56b4337"
SLEEP_NUMBER_BULK_TRANSFER_CHAR_UUID: Final = "0ec9a5a3-8ac3-4582-92f3-1666421f323d"

# Sleep Number BAM / MCR specific UUIDs (older 360 / i8 FlexFit bases)
# Protocol reverse-engineered from com.selectcomfort.SleepIQ APK and live testing
SLEEP_NUMBER_MCR_SERVICE_UUID: Final = "ffffd1fd-388d-938b-344a-939d1f6efee0"
SLEEP_NUMBER_MCR_TX_CHAR_UUID: Final = "ffffd1fd-388d-938b-344a-939d1f6efee1"
SLEEP_NUMBER_MCR_RX_CHAR_UUID: Final = "ffffd1fd-388d-938b-344a-939d1f6efee2"

# Svane LinonPI specific UUIDs (multi-service architecture)
# Protocol reverse-engineered from com.produktide.svane.svaneremote APK
# Each motor has its own service with direction-specific characteristics
SVANE_HEAD_SERVICE_UUID: Final = "0000abcb-0000-1000-8000-00805f9b34fb"
SVANE_FEET_SERVICE_UUID: Final = "0000c258-0000-1000-8000-00805f9b34fb"
SVANE_LIGHT_SERVICE_UUID: Final = "0000d07b-0000-1000-8000-00805f9b34fb"
# Characteristic UUIDs (same UUID exists in each motor service)
SVANE_CHAR_UP_UUID: Final = "000001ac-0000-1000-8000-00805f9b34fb"
SVANE_CHAR_DOWN_UUID: Final = "0000bae9-0000-1000-8000-00805f9b34fb"
SVANE_CHAR_POSITION_UUID: Final = "0000143d-0000-1000-8000-00805f9b34fb"
SVANE_CHAR_MEMORY_UUID: Final = "0000fb6e-0000-1000-8000-00805f9b34fb"
SVANE_LIGHT_ON_OFF_UUID: Final = "0000a8e0-0000-1000-8000-00805f9b34fb"

# Svane name patterns
SVANE_NAME_PATTERNS: Final = ("svane bed",)

# Vibradorm specific UUIDs (VMAT Basic protocol)
# Protocol reverse-engineered from de.vibradorm.vra and com.vibradorm.vmatbasic APKs
VIBRADORM_SERVICE_UUID: Final = "00001525-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_SECONDARY_SERVICE_UUID: Final = "00001527-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_COMMAND_CHAR_UUID: Final = "00001526-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_SECONDARY_COMMAND_CHAR_UUID: Final = "00001528-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_SECONDARY_ALT_COMMAND_CHAR_UUID: Final = "00001534-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_LIGHT_CHAR_UUID: Final = "00001529-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_CBI_CHAR_UUID: Final = "00001550-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_NOTIFY_CHAR_UUID: Final = "00001551-9f03-0de5-96c5-b8f4f3081186"

# Vibradorm manufacturer ID
MANUFACTURER_ID_VIBRADORM: Final = 944  # 0x03B0

# Vibradorm name patterns (VMAT = Vibradorm Motor Actuator)
VIBRADORM_NAME_PATTERNS: Final = ("vmat",)

# Rondure / 1500 Tilt Base specific UUIDs (FurniBus protocol)
# Protocol reverse-engineered from com.sfd.rondure_hump APK
# Uses 8-byte (both sides) or 9-byte (single side) packets with ~sum checksum
RONDURE_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
RONDURE_WRITE_CHAR_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
RONDURE_READ_CHAR_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
# Also supports Nordic UART as an alternative (same UUIDs as NORDIC_UART_*)

# Rondure side selection variants
RONDURE_VARIANT_BOTH: Final = "both"  # Control both sides (default)
RONDURE_VARIANT_SIDE_A: Final = "side_a"  # Control side A only
RONDURE_VARIANT_SIDE_B: Final = "side_b"  # Control side B only
RONDURE_VARIANTS: Final = {
    RONDURE_VARIANT_BOTH: "Both sides",
    RONDURE_VARIANT_SIDE_A: "Side A only",
    RONDURE_VARIANT_SIDE_B: "Side B only",
}

# SBI/Q-Plus side selection variants
SBI_VARIANT_BOTH: Final = "both"  # Control both sides (8-byte, 0xE5 header)
SBI_VARIANT_SIDE_A: Final = "side_a"  # Control side A only (9-byte, 0xE6 header)
SBI_VARIANT_SIDE_B: Final = "side_b"  # Control side B only (9-byte, 0xE6 header)
SBI_VARIANTS: Final = {
    SBI_VARIANT_BOTH: "Both sides (dual bed)",
    SBI_VARIANT_SIDE_A: "Side A only",
    SBI_VARIANT_SIDE_B: "Side B only",
}

# Remacro specific UUIDs (SynData protocol)
# Protocol reverse-engineered from com.cheers.jewmes APK (Jeromes app)
# Used by: CheersSleep, Jeromes, Slumberland, The Brick furniture store beds
# Uses 8-byte packets: [serial, PID, cmd_lo, cmd_hi, param0-3]
# Note: The service UUID is similar to Nordic UART but with different prefix (6e4035xx vs 6e4000xx)
REMACRO_SERVICE_UUID: Final = "6e403587-b5a3-f393-e0a9-e50e24dcca9e"
REMACRO_WRITE_CHAR_UUID: Final = "6e403588-b5a3-f393-e0a9-e50e24dcca9e"
REMACRO_READ_CHAR_UUID: Final = "6e403589-b5a3-f393-e0a9-e50e24dcca9e"

# Protocol variants
VARIANT_AUTO: Final = "auto"

# Sleep Number side selection variants
SLEEP_NUMBER_VARIANT_LEFT: Final = "left"
SLEEP_NUMBER_VARIANT_RIGHT: Final = "right"
SLEEP_NUMBER_VARIANTS: Final = {
    VARIANT_AUTO: "Auto (left side by default)",
    SLEEP_NUMBER_VARIANT_LEFT: "Left side",
    SLEEP_NUMBER_VARIANT_RIGHT: "Right side",
}

# Kaidi variants — all OEM apps use SEAT_* commands exclusively.
# BED_* constants from PLDataTrans.java are legacy/enterprise firmware and are
# NOT used by any consumer mobile app (Rize, Floyd, ISleep).
KAIDI_VARIANT_SEAT_1: Final = "seat_1"
KAIDI_VARIANT_SEAT_2: Final = "seat_2"
KAIDI_VARIANT_SEAT_3: Final = "seat_3"
KAIDI_VARIANT_SEAT_1_2: Final = "seat_1_2"
KAIDI_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (recommended)",
    KAIDI_VARIANT_SEAT_1: "Seat 1 (single base)",
    KAIDI_VARIANT_SEAT_2: "Seat 2",
    KAIDI_VARIANT_SEAT_3: "Seat 3",
    KAIDI_VARIANT_SEAT_1_2: "Seat 1+2 (split/dual base)",
}

# OKIN CB24 profile variants (SmartBed app device profiles)
# Source: com.okin.bedding.smartbedwifi model/device/*
OKIN_CB24_VARIANT_OLD: Final = "cb_old"
OKIN_CB24_VARIANT_NEW: Final = "cb_new"
OKIN_CB24_VARIANT_CB24: Final = "cb24"
OKIN_CB24_VARIANT_CB27: Final = "cb27"
OKIN_CB24_VARIANT_CB24_AB: Final = "cb24_ab"
OKIN_CB24_VARIANT_CB1221: Final = "cb1221"
OKIN_CB24_VARIANT_DACHENG: Final = "dacheng"
OKIN_CB24_VARIANT_CB27NEW: Final = "cb27new"
OKIN_CB24_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (recommended)",
    OKIN_CB24_VARIANT_OLD: "OLD protocol compatibility (continuous presets)",
    OKIN_CB24_VARIANT_NEW: "NEW protocol (CB27New)",
    OKIN_CB24_VARIANT_CB24: "CB24 profile (legacy packets, one-shot presets)",
    OKIN_CB24_VARIANT_CB27: "CB27 profile (legacy packets, one-shot presets)",
    OKIN_CB24_VARIANT_CB24_AB: "CB24AB profile (legacy packets, one-shot presets)",
    OKIN_CB24_VARIANT_CB1221: "CB1221 profile (legacy packets, one-shot presets)",
    OKIN_CB24_VARIANT_DACHENG: "Dacheng profile (legacy packets, one-shot presets)",
    OKIN_CB24_VARIANT_CB27NEW: "CB27New profile (NEW protocol)",
}

# Keeson variants
KEESON_VARIANT_BASE: Final = "base"
KEESON_VARIANT_JSON: Final = "json"
KEESON_VARIANT_KSBT: Final = "ksbt"
KEESON_VARIANT_KSBT_CR: Final = "ksbt_cr"
KEESON_VARIANT_ERGOMOTION: Final = "ergomotion"
KEESON_VARIANT_OKIN: Final = "okin"
KEESON_VARIANT_SERTA: Final = "serta"
KEESON_VARIANT_SINO: Final = "sino"
KEESON_VARIANT_PURPLE: Final = "purple"
KEESON_VARIANT_KSBT04C: Final = "ksbt04c"
# Deprecated alias kept for compatibility with older references.
KEESON_VARIANT_ORE: Final = KEESON_VARIANT_SINO
KEESON_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect",
    KEESON_VARIANT_BASE: "BaseI4/BaseI5 (Member's Mark)",
    KEESON_VARIANT_JSON: "JSON/A00A (Juna, Linx, Ergo Health)",
    KEESON_VARIANT_KSBT: "KSBT (Nordic UART, some Ergomotion Sync beds)",
    KEESON_VARIANT_KSBT_CR: "KSBT03CR (7-byte, 0x05 prefix)",
    KEESON_VARIANT_KSBT04C: "KSBT04C (7-byte with checksum, Beautyrest Baselogic)",
    KEESON_VARIANT_ERGOMOTION: "Ergomotion (with position feedback)",
    KEESON_VARIANT_OKIN: "OKIN FFE (OKIN 13/15 series, 0xE6 prefix)",
    KEESON_VARIANT_SERTA: "Serta (Serta MP Remote)",
    KEESON_VARIANT_SINO: "Sino (Dynasty, INNOVA, BetterLiving - big-endian)",
    "ore": "ORE (deprecated alias for Sino)",
    KEESON_VARIANT_PURPLE: "Purple Premium Smart Base"
}

# Leggett & Platt variants
LEGGETT_VARIANT_GEN2: Final = "gen2"
LEGGETT_VARIANT_OKIN: Final = "okin"
LEGGETT_VARIANT_MLRM: Final = "mlrm"
LEGGETT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect",
    LEGGETT_VARIANT_GEN2: "Gen2 (Richmat-based, most common)",
    LEGGETT_VARIANT_OKIN: "Okin (requires BLE pairing)",
    LEGGETT_VARIANT_MLRM: "MlRM (WiLinke protocol, discrete massage control)",
}

# Richmat protocol variants (auto-detected, but can be overridden)
RICHMAT_VARIANT_NORDIC: Final = "nordic"
RICHMAT_VARIANT_WILINKE: Final = "wilinke"
RICHMAT_VARIANT_PREFIX55: Final = "prefix55"
RICHMAT_VARIANT_PREFIXAA: Final = "prefixaa"
RICHMAT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (recommended)",
    RICHMAT_VARIANT_NORDIC: "Nordic (single-byte commands)",
    RICHMAT_VARIANT_WILINKE: "WiLinke (5-byte commands with 0x6E prefix)",
    RICHMAT_VARIANT_PREFIX55: "Prefix55 (5-byte commands with 0x55 prefix)",
    RICHMAT_VARIANT_PREFIXAA: "PrefixAA (5-byte commands with 0xAA prefix)",
}


# Richmat feature flags for remote-based feature detection
# Reference: https://github.com/richardhopton/smartbed-mqtt/blob/main/src/Richmat/Features.ts
class RichmatFeatures(IntFlag):
    """Feature flags for Richmat beds based on remote code."""

    NONE = 0

    # Presets
    PRESET_FLAT = 1 << 0
    PRESET_ANTI_SNORE = 1 << 1
    PRESET_LOUNGE = 1 << 2
    PRESET_MEMORY_1 = 1 << 3
    PRESET_MEMORY_2 = 1 << 4
    PRESET_TV = 1 << 5
    PRESET_ZERO_G = 1 << 6

    # Program (save to memory)
    PROGRAM_ANTI_SNORE = 1 << 7
    PROGRAM_LOUNGE = 1 << 8
    PROGRAM_MEMORY_1 = 1 << 9
    PROGRAM_MEMORY_2 = 1 << 10
    PROGRAM_TV = 1 << 11
    PROGRAM_ZERO_G = 1 << 12

    # Lights
    UNDER_BED_LIGHTS = 1 << 13

    # Massage
    MASSAGE_HEAD_STEP = 1 << 14
    MASSAGE_FOOT_STEP = 1 << 15
    MASSAGE_MODE = 1 << 16
    MASSAGE_TOGGLE = 1 << 17

    # Motors
    MOTOR_HEAD = 1 << 18
    MOTOR_FEET = 1 << 19
    MOTOR_PILLOW = 1 << 20
    MOTOR_LUMBAR = 1 << 21

    # Memory 3 (extended)
    PRESET_MEMORY_3 = 1 << 22
    PROGRAM_MEMORY_3 = 1 << 23


# Richmat remote codes and their supported features
# Reference: https://github.com/richardhopton/smartbed-mqtt/blob/main/src/Richmat/remoteFeatures.ts
RICHMAT_REMOTE_AUTO: Final = "auto"
RICHMAT_REMOTE_AZRN: Final = "AZRN"
RICHMAT_REMOTE_BURM: Final = "BURM"
RICHMAT_REMOTE_BVRM: Final = "BVRM"
RICHMAT_REMOTE_VIRM: Final = "VIRM"
RICHMAT_REMOTE_V1RM: Final = "V1RM"
RICHMAT_REMOTE_W6RM: Final = "W6RM"
RICHMAT_REMOTE_X1RM: Final = "X1RM"
RICHMAT_REMOTE_ZR10: Final = "ZR10"
RICHMAT_REMOTE_ZR60: Final = "ZR60"
RICHMAT_REMOTE_I7RM: Final = "I7RM"
RICHMAT_REMOTE_190_0055: Final = "190-0055"
RICHMAT_REMOTE_BT6500: Final = "BT6500"

# Richmat WiLinke stop-byte compatibility.
# Most Richmat remotes use END=0x6E, but some devices require 0x5E to stop
# movement: QRRM remotes and BedTech BT6500 beds (issue #194).
RICHMAT_WILINKE_STOP_COMPAT_REMOTE_CODES: Final[frozenset[str]] = frozenset(
    {"qrrm", "bt6500"}
)

# Display names for remote selection
RICHMAT_REMOTES: Final = {
    RICHMAT_REMOTE_AUTO: "Auto (all features enabled)",
    RICHMAT_REMOTE_AZRN: "AZRN (Head, Pillow, Feet)",
    RICHMAT_REMOTE_BT6500: "BT6500 (Head, Feet, Pillow, Lumbar, M1/M2, ZG, Anti-snore, TV, Lights)",
    RICHMAT_REMOTE_BURM: "BURM (Head, Feet, Massage, Lights)",
    RICHMAT_REMOTE_BVRM: "BVRM (Head, Feet, Massage)",
    RICHMAT_REMOTE_VIRM: "VIRM (Head, Feet, Pillow, Lumbar, Massage, Lights)",
    RICHMAT_REMOTE_V1RM: "V1RM (Head, Feet)",
    RICHMAT_REMOTE_W6RM: "W6RM (Head, Feet, Massage, Lights)",
    RICHMAT_REMOTE_X1RM: "X1RM (Head, Feet)",
    RICHMAT_REMOTE_ZR10: "ZR10 (Head, Feet, Lights)",
    RICHMAT_REMOTE_ZR60: "ZR60 (Head, Feet, Lights)",
    RICHMAT_REMOTE_I7RM: "I7RM / HJH85 / Sleep Function 2.0 (Head, Feet, Pillow, Lumbar, Massage, Lights)",
    RICHMAT_REMOTE_190_0055: "190-0055 (Head, Pillow, Feet, Massage, Lights)",
}

# Feature sets for each remote code
_F = RichmatFeatures  # Shorthand for readability
RICHMAT_REMOTE_FEATURES: Final = {
    RICHMAT_REMOTE_AUTO: (
        # All features enabled for auto mode
        _F.PRESET_FLAT
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_LOUNGE
        | _F.PRESET_MEMORY_1
        | _F.PRESET_MEMORY_2
        | _F.PRESET_TV
        | _F.PRESET_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_LOUNGE
        | _F.PROGRAM_MEMORY_1
        | _F.PROGRAM_MEMORY_2
        | _F.PROGRAM_TV
        | _F.PROGRAM_ZERO_G
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
        | _F.MOTOR_PILLOW
        | _F.MOTOR_LUMBAR
    ),
    RICHMAT_REMOTE_AZRN: (
        _F.PRESET_FLAT
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PRESET_MEMORY_2
        | _F.PRESET_TV
        | _F.PRESET_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_LOUNGE
        | _F.PROGRAM_MEMORY_1
        | _F.PROGRAM_TV
        | _F.PROGRAM_ZERO_G
        | _F.MOTOR_HEAD
        | _F.MOTOR_PILLOW
        | _F.MOTOR_FEET
    ),
    # BedTech BT6500 support bundle (#194) shows a QRRM-family bed with
    # head/feet/pillow/lumbar controls plus M1/M2, TV, zero gravity,
    # anti-snore, under-bed lights, and massage.
    RICHMAT_REMOTE_BT6500: (
        _F.PRESET_FLAT
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PRESET_MEMORY_2
        | _F.PRESET_TV
        | _F.PRESET_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.PROGRAM_MEMORY_2
        | _F.PROGRAM_TV
        | _F.PROGRAM_ZERO_G
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
        | _F.MOTOR_PILLOW
        | _F.MOTOR_LUMBAR
    ),
    RICHMAT_REMOTE_BURM: (
        _F.PRESET_FLAT
        | _F.PRESET_MEMORY_1
        | _F.PRESET_MEMORY_2
        | _F.PRESET_TV
        | _F.PRESET_ZERO_G
        | _F.PROGRAM_LOUNGE
        | _F.PROGRAM_MEMORY_1
        | _F.PROGRAM_MEMORY_2
        | _F.PROGRAM_TV
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    RICHMAT_REMOTE_BVRM: (
        _F.PRESET_FLAT
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PRESET_MEMORY_2
        | _F.PRESET_TV
        | _F.PRESET_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.PROGRAM_MEMORY_2
        | _F.PROGRAM_TV
        | _F.PROGRAM_ZERO_G
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    RICHMAT_REMOTE_VIRM: (
        _F.PRESET_FLAT
        | _F.PRESET_ZERO_G
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
        | _F.MOTOR_PILLOW
        | _F.MOTOR_LUMBAR
    ),
    RICHMAT_REMOTE_V1RM: (
        _F.PRESET_FLAT
        | _F.PRESET_ZERO_G
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    RICHMAT_REMOTE_W6RM: (
        _F.PRESET_FLAT
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_LOUNGE
        | _F.PRESET_MEMORY_1
        | _F.PRESET_MEMORY_2
        | _F.PRESET_TV
        | _F.PRESET_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_LOUNGE
        | _F.PROGRAM_MEMORY_1
        | _F.PROGRAM_MEMORY_2
        | _F.PROGRAM_TV
        | _F.PROGRAM_ZERO_G
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    RICHMAT_REMOTE_X1RM: (
        _F.PRESET_FLAT
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_ZERO_G
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    RICHMAT_REMOTE_ZR10: (
        _F.PRESET_FLAT
        | _F.PRESET_ZERO_G
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.UNDER_BED_LIGHTS
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    RICHMAT_REMOTE_ZR60: (
        _F.PRESET_FLAT
        | _F.PRESET_ZERO_G
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.UNDER_BED_LIGHTS
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
    ),
    # I7RM - same features as VIRM (full-featured remote)
    RICHMAT_REMOTE_I7RM: (
        _F.PRESET_FLAT
        | _F.PRESET_ZERO_G
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_FEET
        | _F.MOTOR_PILLOW
        | _F.MOTOR_LUMBAR
    ),
    # 190-0055 - Has Pillow but NOT Lumbar
    RICHMAT_REMOTE_190_0055: (
        _F.PRESET_FLAT
        | _F.PRESET_ZERO_G
        | _F.PRESET_ANTI_SNORE
        | _F.PRESET_MEMORY_1
        | _F.PROGRAM_ZERO_G
        | _F.PROGRAM_ANTI_SNORE
        | _F.PROGRAM_MEMORY_1
        | _F.UNDER_BED_LIGHTS
        | _F.MASSAGE_HEAD_STEP
        | _F.MASSAGE_FOOT_STEP
        | _F.MASSAGE_MODE
        | _F.MASSAGE_TOGGLE
        | _F.MOTOR_HEAD
        | _F.MOTOR_PILLOW
        | _F.MOTOR_FEET
    ),
}

# Some Richmat OEM apps expose a generic QRRM family in BLE, then ask the user
# to pick the actual retail model. Use entry/device names to recover those
# model-specific surfaces when we have enough context.
RICHMAT_MODEL_REMOTE_ALIASES: Final[dict[str, str]] = {
    "bt2000": "a7rm",
    "bt2500": "t3rm",
    "bt3000fh": "ufrm",
    "bt3000": "ufrm",
    "bt4000": "vcrm",
    "bt6500": RICHMAT_REMOTE_BT6500.lower(),
    "bt7000": "u5rm",
}


def resolve_richmat_remote_code(
    remote_code: str | None,
    *,
    entry_title: str | None = None,
    configured_name: str | None = None,
    device_name: str | None = None,
) -> str:
    """Resolve a Richmat remote code using config and model-specific aliases.

    QRRM is a selector family in OEM apps rather than a concrete remote surface.
    If the config or device title includes a known retail model (for example
    "BedTech BT6500"), prefer that model-specific surface over the generic QRRM
    feature map.
    """
    normalized = (remote_code or RICHMAT_REMOTE_AUTO).lower()
    if normalized not in {"", RICHMAT_REMOTE_AUTO, "qrrm"}:
        return normalized

    haystack = " ".join(
        part.lower()
        for part in (entry_title, configured_name, device_name)
        if part
    )
    if not haystack:
        return normalized or RICHMAT_REMOTE_AUTO

    for model, resolved_remote in sorted(
        RICHMAT_MODEL_REMOTE_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if model in haystack:
            return resolved_remote

    return normalized or RICHMAT_REMOTE_AUTO


def get_richmat_features(remote_code: str) -> RichmatFeatures:
    """Get features for a Richmat remote code.

    Looks up features from both manually-defined overrides and the
    comprehensive auto-generated mapping (492 product codes extracted
    from Richmat apps).

    Args:
        remote_code: The remote code (e.g., "VIRM", "qrrm", "i7rm")
                    Case-insensitive, will be normalized to lowercase.

    Returns:
        RichmatFeatures flags for the remote code, or all features
        enabled if the code is not found (safe fallback).
    """
    # Import here to avoid circular dependency
    from .richmat_features import RICHMAT_REMOTE_FEATURES_GENERATED

    # Normalize to lowercase for lookup
    code_lower = remote_code.lower() if remote_code else ""

    # Special case: "auto" returns all features
    if code_lower == "auto" or not code_lower:
        return RICHMAT_REMOTE_FEATURES[RICHMAT_REMOTE_AUTO]

    # First check manually-defined features (uppercase keys)
    code_upper = remote_code.upper()
    if code_upper in RICHMAT_REMOTE_FEATURES:
        return RICHMAT_REMOTE_FEATURES[code_upper]

    # Then check generated features (lowercase keys)
    if code_lower in RICHMAT_REMOTE_FEATURES_GENERATED:
        return RICHMAT_REMOTE_FEATURES_GENERATED[code_lower]

    # Fallback: return all features enabled
    return RICHMAT_REMOTE_FEATURES[RICHMAT_REMOTE_AUTO]


def get_richmat_motor_count(features: RichmatFeatures) -> int:
    """Get motor count from Richmat feature flags.

    Richmat beds use `motor_count` for the primary head/feet axes only.
    Accessory actuators such as pillow and lumbar are exposed as dedicated
    entities, not as extra back/head or legs/feet slots.

    Returns:
        Motor count (0-2), minimum 2 for practical use.
    """
    count = 0
    if features & RichmatFeatures.MOTOR_HEAD:
        count += 1
    if features & RichmatFeatures.MOTOR_FEET:
        count += 1
    # Minimum 2 motors for practical use (head + feet is the baseline)
    return max(count, 2)


# Octo variants
OCTO_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (recommended)",
    OCTO_VARIANT_STANDARD: "Standard Octo (most common)",
    OCTO_VARIANT_STAR2: "Octo Remote Star2",
}

# Richmat command protocols (how command bytes are encoded - used internally)
RICHMAT_PROTOCOL_WILINKE: Final = "wilinke"  # [110, 1, 0, cmd, cmd+111]
RICHMAT_PROTOCOL_SINGLE: Final = "single"  # [cmd]
RICHMAT_PROTOCOL_PREFIX55: Final = "prefix55"  # [0x55, 1, 0, cmd, (cmd+0x56)&0xFF]
RICHMAT_PROTOCOL_PREFIXAA: Final = "prefixaa"  # [0xAA, 1, 0, cmd, (cmd+0xAB)&0xFF]

# Okimat remote code variants (generated; keyed by the printed remote code).
# Source of truth: DewertOkin FurniMove handset backend + bundled
# handsetlist.csv capability flags. Drives OKIN_UUID_REMOTES in
# beds/okin_uuid.py; regenerate via tools/okin_remotes/.
OKIMAT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (try 82417 first)",
    "62211": "62211 - RF (Head/Back/Legs, 4 Mem)",
    "62612": "62612 - RF (Head/Back/Legs/Feet, 4 Mem)",
    "63293": "63293 - RF (Back/Legs)",
    "63338": "63338 - RF (Back/Legs)",
    "63365": "63365 - RF (Head/Back/Legs, 4 Mem)",
    "65418": "65418 - RF (Head/Back/Legs, 4 Mem)",
    "65433": "65433 - RF (Back/Legs, 4 Mem)",
    "65567": "65567 - RF (Head/Back/Legs/Feet, 4 Mem, Massage)",
    "68036": "68036 - RF-SYSTEM/SW/6/1476/2400MHZ (Back/Legs)",
    "71852": "71852 - SET (Back/Legs)",
    "71853": "71853 - REMOTE (Back/Legs)",
    "73591": "73591 - REMOTE (Back/Legs)",
    "73593": "73593 - SET (Back/Legs)",
    "74130": "74130 - REMOTE (Head)",
    "74131": "74131 - SET (Head)",
    "75225": "75225 - RF-SYSTEM/SW/ST/6/1476/2400MHZ (Back/Legs)",
    "75267": "75267 - REMOTE (Back/Legs)",
    "75268": "75268 - SET (Back/Legs)",
    "76208": "76208 - RF (Back/Legs, 4 Mem, Massage)",
    "76688": "76688 - RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02 (Back/Legs)",
    "76691": "76691 - RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "77008": "77008 - RF (Back/Legs)",
    "77010": "77010 - RF (Back/Legs)",
    "77011": "77011 - RF (Back/Legs)",
    "77560": "77560 - REMOTE (Back/Legs)",
    "77561": "77561 - SET (Back/Legs)",
    "77839": "77839 - RF-TOUCH/BRW/BK/16/1867/L (Back/Legs, 4 Mem)",
    "77991": "77991 - RF-TOUCH/BRW/BK/16/1867/L (Back/Legs, 4 Mem)",
    "77994": "77994 - RF-TOUCH/BRW/BK/20/1868/L (Head/Back/Legs/Feet, 4 Mem)",
    "77995": "77995 - RF-TOUCH/BRW/BK/18/1869/L (Back/Legs/Feet, 4 Mem)",
    "77996": "77996 - RF-TOUCH/BK/BRW/18/1870/03 (Head/Back/Legs, 4 Mem)",
    "78031": "78031 - REMOTE (Back/Legs)",
    "78033": "78033 - SET (Back/Legs)",
    "78080": "78080 - RF-TOUCH/BRW/BK/16/1889/L (Back/Legs, 4 Mem)",
    "78081": "78081 - RF-TOUCH/BRW/BK/16/1889/L (Back/Legs, 4 Mem)",
    "78102": "78102 - RF-TOUCH/BRW/BK/18/1892/L (Head/Back/Legs, 4 Mem)",
    "78103": "78103 - RF-TOUCH/BRW/BK/20/1890/L (Head/Back/Legs/Feet, 4 Mem)",
    "78105": "78105 - RF-TOUCH/BRW/BK/16/1893/L (Back/Legs, 4 Mem)",
    "78109": "78109 - RF-TOUCH/BRW/BK/18/1891/L (Back/Legs/Feet, 4 Mem)",
    "78110": "78110 - RF-TOUCH/BRW/BK/18/1894/L (Head/Back/Legs, 4 Mem)",
    "78111": "78111 - RF-TOUCH/BRW/BK/20/1895/L (Head/Back/Legs/Feet, 4 Mem)",
    "78237": "78237 - REMOTE (Back/Legs)",
    "78238": "78238 - SET (Back/Legs)",
    "78281": "78281 - REMOTE (Back/Legs)",
    "78283": "78283 - SET (Back/Legs)",
    "78375": "78375 - RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02 (Back/Legs)",
    "78378": "78378 - RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02 (Back/Legs)",
    "78379": "78379 - RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "78381": "78381 - RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "78386": "78386 - RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02 (Back/Legs)",
    "78737": "78737 - RF-TOUCH/BRW/BK/21/1899/L (Head/Back/Legs, 4 Mem)",
    "78773": "78773 - RF-TOUCH/BRW/BK/19/1896 (Head/Back/Legs/Feet, 3 Mem)",
    "78785": "78785 - RF-TOUCH/BRW/BK/19/1897 (Head/Back/Legs/Feet, 3 Mem)",
    "78791": "78791 - RF-TOUCH/BRW/BK/19/1898/L (Head/Back/Legs/Feet, 3 Mem)",
    "78847": "78847 - RF-TOUCH/BRW/BK/14/1923 (Back/Legs, 2 Mem)",
    "78854": "78854 - RF-TOUCH/BRW/BK/14/1924/L (Back/Legs, 2 Mem)",
    "78860": "78860 - RF-TOUCH/BRW/BK/14/1925/L (Back/Legs, 2 Mem)",
    "80027": "80027 - RF-TOUCH/BK/BK/14/1923 (Back/Legs, 2 Mem)",
    "80035": "80035 - RF-TOUCH/BK/BK/19/1896 (Head/Back/Legs/Feet, 3 Mem)",
    "80036": "80036 - RF-TOUCH/BK/BK/17/1965 (Back/Legs/Feet, 3 Mem)",
    "80354": "80354 - REMOTE (Back/Legs)",
    "80355": "80355 - SET (Back/Legs)",
    "80358": "80358 - REMOTE (Head)",
    "80360": "80360 - SET (Head)",
    "80593": "80593 - RF-TOUCH/BRW/BK/8/1952/L (Back/Legs)",
    "80595": "80595 - RF-TOUCH/BRW/BK/8/1954/L (Back/Legs)",
    "80597": "80597 - RF-TOUCH/BRW/BK/8/1953/L (Back/Legs)",
    "80599": "80599 - RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02 (Back/Legs)",
    "80601": "80601 - RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "80602": "80602 - RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02 (Back/Legs)",
    "80603": "80603 - RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "80604": "80604 - RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02 (Back/Legs, 1 Mem)",
    "80608": "80608 - RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02 (Back/Legs)",
    "80616": "80616 - RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02 (Back/Legs)",
    "80673": "80673 - REMOTE (Back/Legs)",
    "80674": "80674 - REMOTE (Back/Legs)",
    "80675": "80675 - REMOTE (Back/Legs)",
    "80676": "80676 - SET (Back/Legs)",
    "80683": "80683 - SET (Back/Legs)",
    "80685": "80685 - SET (Back/Legs)",
    "80714": "80714 - SET (Back/Legs)",
    "80716": "80716 - REMOTE (Back/Legs)",
    "80903": "80903 - RF-TOUCH/BK/BK/14/2009 (Back/Legs, 2 Mem)",
    "81183": "81183 - RF-TOUCH/BRW/BK/8/1952/L (Back/Legs)",
    "81185": "81185 - RF-TOUCH/BRW/BK/16/1867/L (Back/Legs, 4 Mem)",
    "81186": "81186 - RF-TOUCH/BRW/BK/8/1954/L (Back/Legs)",
    "81187": "81187 - RF-TOUCH/BRW/BK/18/1870/L (Head/Back/Legs, 4 Mem)",
    "81191": "81191 - RF-TOUCH/BRW/BK/20/1868/L (Head/Back/Legs/Feet, 4 Mem)",
    "81192": "81192 - RF-TOUCH/BRW/BK/18/1894/L (Head/Back/Legs, 4 Mem)",
    "81193": "81193 - RF-TOUCH/BRW/BK/18/1869/L (Back/Legs/Feet, 4 Mem)",
    "81194": "81194 - RF-TOUCH/BRW/BK/8/1953/L (Back/Legs)",
    "81196": "81196 - RF-TOUCH/BRW/BK/16/1889/L (Back/Legs, 4 Mem)",
    "81197": "81197 - RF-TOUCH/BRW/BK/20/1890/L (Head/Back/Legs/Feet, 4 Mem)",
    "81202": "81202 - RF-TOUCH/BRW/BK/18/1892/L (Head/Back/Legs, 4 Mem)",
    "81204": "81204 - RF-TOUCH/BRW/BK/18/1891/L (Back/Legs/Feet, 4 Mem)",
    "81205": "81205 - RF-TOUCH/BRW/BK/20/1895/L (Head/Back/Legs/Feet, 4 Mem)",
    "81611": "81611 - REMOTE (Back/Legs)",
    "81613": "81613 - SET (Back/Legs)",
    "81619": "81619 - REMOTE (Back)",
    "81620": "81620 - SET (Head)",
    "82292": "82292 - RF-TOUCH/BRW/BK/14/2006 (Back/Legs, 2 Mem)",
    "82295": "82295 - RF-TOUCH/BRW/BK/19/2004 (Head/Back/Legs/Feet, 3 Mem)",
    "82417": "82417 - RF-TOPLINE (Back/Legs)",
    "82418": "82418 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "82620": "82620 - RF-TOPLINE (Back/Legs)",
    "82634": "82634 - RF-TOPLINE (Head/Back/Legs)",
    "82635": "82635 - RF-TOPLINE (Head/Back/Legs)",
    "82755": "82755 - RF-TOPLINE (Head)",
    "82757": "82757 - RF-TOPLINE (Back/Legs)",
    "82760": "82760 - RF-TOPLINE (Back/Legs)",
    "82764": "82764 - RF-TOPLINE (Back/Legs)",
    "82767": "82767 - RF-TOPLINE (Back/Legs)",
    "82770": "82770 - RF-TOPLINE (Back/Legs)",
    "82785": "82785 - RF-TOPLINE (Head/Back/Legs)",
    "82786": "82786 - RF-TOPLINE (Head/Back/Legs)",
    "82790": "82790 - RF-TOPLINE (Head/Back/Legs)",
    "82794": "82794 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82795": "82795 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82796": "82796 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82797": "82797 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "82799": "82799 - RF-TOPLINE (Head/Back/Legs/Feet)",
    "83060": "83060 - RF-TOUCH/BRW/BK/14/2182/L (Back/Legs, 2 Mem)",
    "83126": "83126 - RF-TOUCH/BRW/BK/19/2114 (Back/Legs, 3 Mem, Massage)",
    "83219": "83219 - RF-TOUCH/BRW/BK/24/2068/- (Head/Back/Legs/Feet, 3 Mem, Massage)",
    "83358": "83358 - RF-TOPLINE (Back/Legs)",
    "83462": "83462 - SET (Back/Legs)",
    "83489": "83489 - RF-TOPLINE (Back/Legs)",
    "83603": "83603 - SET (Back/Legs)",
    "84148": "84148 - REMOTE (Back/Legs)",
    "84149": "84149 - SET (Back/Legs)",
    "84150": "84150 - REMOTE (Back/Legs)",
    "84151": "84151 - SET (Back/Legs)",
    "84173": "84173 - RF-TOUCH/BRW/BK/23/2126 (Head/Back/Legs/Feet, 3 Mem, Massage)",
    "84562": "84562 - RF-ECO (Back/Legs)",
    "84563": "84563 - RF-ECO (Back/Legs)",
    "84564": "84564 - RF-ECO (Head/Back/Legs)",
    "84582": "84582 - RF-ECO (Head)",
    "84762": "84762 - HS-IPROXX (Back/Legs)",
    "84931": "84931 - RF-TOPLINE/07/AL/BK/L (Back/Legs)",
    "84963": "84963 - RF-TOPLINE/07/BK/BK/L (Back/Legs)",
    "85057": "85057 - RF-TOPLINE/11/AL/BK/L (Head/Back/Legs/Feet, 4 Mem)",
    "85058": "85058 - RF-TOPLINE/11/AL/BK/L (Back/Legs, 2 Mem)",
    "85124": "85124 - RF-LITE/06/BK/BK (Back/Legs)",
    "85126": "85126 - SET (Back/Legs)",
    "85281": "85281 - RF-FREE-ELEC (Head/Back/Legs/Feet, 4 Mem)",
    "86432": "86432 - RF-STYLE (Back/Legs, 2 Mem)",
    "88875": "88875 - RF-LITELINE/07/ (Back/Legs)",
    "88877": "88877 - RF-LITELINE/07/ (Back/Legs)",
    "89137": "89137 - RF-LITELINE/07/ (Back/Legs)",
    "89138": "89138 - RF-LITELINE/07/ (Back/Legs)",
    "89139": "89139 - RF-LITELINE/07/ (Back/Legs)",
    "89424": "89424 - RF (Back/Legs)",
    "89441": "89441 - RF-FREE-ELEC (Back/Legs, 4 Mem)",
    "89448": "89448 - RF-FREE-ELEC (Back/Legs/Feet, 4 Mem)",
    "89476": "89476 - RF-TOPLINE/11/AL/BK (Head/Back/Legs/Feet, 4 Mem)",
    "89545": "89545 - RF-TOPLINE/11/AL/BK (Back/Legs, 2 Mem)",
    "89746": "89746 - TOPLINE-11-SL-2M (Back/Legs, 2 Mem)",
    "89803": "89803 - LITELINE-7-SL-2M (Back/Legs)",
    "89837": "89837 - RF-TOUCH/18/WH/BK/KL/L (Back/Legs, 3 Mem, Massage)",
    "90199": "90199 - TOPLINE-11-SL-3M/4M (Back/Legs, 2 Mem)",
    "90269": "90269 - RF-STYLE/07/WH/WH (Back/Legs, 4 Mem)",
    "90354": "90354 - RF-STYLE/07/WH/WH (Head/Back/Legs, 2 Mem)",
    "90392": "90392 - HS-IPROXX (Back/Legs)",
    "90658": "90658 - RF-TOUCHLINE/15/BK/BK/KL (Head/Back, 4 Mem)",
    "90675": "90675 - RF-TOUCHLINE/15/AL/BK/KL (Head/Back, 4 Mem)",
    "90678": "90678 - RF-TOUCHLINE/19/AL/BK/KL (Head/Back/Legs/Feet, 4 Mem)",
    "90679": "90679 - RF-TOUCHLINE/19/BK/BK/KL (Head/Back/Legs/Feet, 4 Mem)",
    "90882": "90882 - TOPLINE-11-BK-2M (Back/Legs, 2 Mem)",
    "90916": "90916 - RF-TOUCHLINE/21/AL/BK/KL (Head/Back/Legs/Feet, 2 Mem, Massage)",
    "90918": "90918 - RF-TOUCHLINE/21/AL/BK/KL (Back/Legs, 3 Mem, Massage)",
    "90926": "90926 - RF-ECO (Back/Feet)",
    "90928": "90928 - TOPLINE-11-SL-3M/4M (Back/Legs, 2 Mem, Massage)",
    "91050": "91050 - RF-TOUCHLINE/21/AL/BK/KL (Back/Legs, 3 Mem, Massage)",
    "91244": "91244 - RF-FLASHLINE/07/WH/GY (Back/Legs)",
    "91246": "91246 - RF-FLASHLINE/09/WH/GY (Back/Legs, 2 Mem)",
    "91334": "91334 - TOPLINE-11-BK-2M (Back/Legs, 2 Mem)",
    "91616": "91616 - HS-IPROXX (Back/Legs)",
    "91751": "91751 - LITELINE-7-BK-2M (Back/Legs)",
    "91914": "91914 - RF-TOUCH/23/WH/BK/KL (Head/Back/Legs/Feet, 3 Mem, Massage)",
    "92063": "92063 - LITELINE-7-GR-2M (Back/Legs)",
    "92113": "92113 - RF-STYLE/BK/BK/14/2009 (Back/Legs, 4 Mem)",
    "92129": "92129 - TOPLINE-11-SL-2M (Back/Legs, 2 Mem, Massage)",
    "92428": "92428 - RF (Back/Legs, 2 Mem)",
    "92461": "92461 - \n  RF-TOPLINE\n  SI (Back/Legs)",
    "92471": "92471 - RF (Back/Legs, 2 Mem)",
    "92535": "92535 - RF-LITELINE/07/ (Back/Legs)",
    "92591": "92591 - RF-FLASHLINE/09/WH/GY (Back/Legs, 2 Mem)",
    "93025": "93025 - RF-STYLE/07/WH/WH (Back/Legs)",
    "93055": "93055 - RF-TOPLINE/15/WH/BK (Back/Legs, 2 Mem)",
    "93300": "93300 - RF-STYLE/07/WH/WH (Back/Legs, 4 Mem)",
    "93305": "93305 - RF-TOPLINE (Back/Legs)",
    "93306": "93306 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "93329": "93329 - RF-TOPLINE/15/AL/BK/M3/S/ST/IP20/BLI/FL/LED/M (Head/Back/Legs, 4 Mem)",
    "93332": "93332 - RF-TOPLINE/15/AL/BK/M4/S/ST/IP20/BLI/FL/LED/M (Head/Back/Legs/Feet, 2 Mem)",
    "93339": "93339 - RF-TOPLINE/15/AL/BK (Back/Legs, 2 Mem, Massage)",
    "94186": "94186 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "94238": "94238 - RF (Back/Legs, 2 Mem)",
    "94239": "94239 - RF (Back/Legs)",
    "94369": "94369 - RF-TOPLINE (Head/Back/Legs/Feet, 4 Mem)",
    "94428": "94428 - RF-TOPLINE (Head/Back/Legs/Feet, 4 Mem)",
    "94429": "94429 - RF-TOPLINE (Head/Back/Legs, 4 Mem)",
    "94430": "94430 - RF-TOPLINE (Back/Legs, 2 Mem)",
    "94495": "94495 - RF-FLASHLINE/TEMPUR/07/BLACK (Back/Legs)",
    "94500": "94500 - RF-FLASHLINE/TEMPUR/09/BLACK (Back/Legs, 2 Mem)",
    "96312": "96312 - RF34/07/BK/BK (Back/Legs)",
    "96313": "96313 - RF34/07/WH/GY (Back/Legs)",
    "96314": "96314 - RF28/07/BK/BK (Back/Legs)",
    "96315": "96315 - RF28/07/WH/GY (Back/Legs)",
    "97134": "97134 - RF-TOPLINE/11/AL/BK/L (Back/Legs, 2 Mem)",
    "97135": "97135 - RF-TOPLINE/15/AL/BK/L (Head/Back/Legs/Feet, 2 Mem)",
}

# DewertOkin "DOT PROTOCOL" remote codes (generated together with
# OKIMAT_VARIANTS; regenerate via tools/okin_remotes/). These handsets
# (RF1058/RF34/RF6707) resolve through the same FurniMove backend but their
# boxes expose Nordic UART and take CB24-style 7-byte frames — see
# beds/okin_dot.py. Motor keycodes are renumbered per handset (whichever
# channels exist start at 0x1/0x2) but keep their section meaning; the table
# maps them to the standard section fields, so labels match the exposed axes.
OKIN_DOT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto (RF34 layout, try 97450 first)",
    "90167": "90167 - RF1058 (Head/Feet, 4 Mem, Massage)",
    "91983": "91983 - RF1058 (Head/Feet, 3 Mem, Massage)",
    "93558": "93558 - RF1058 (Head/Feet, 3 Mem, Massage)",
    "97450": "97450 - RF34/09/WH/GY/ (Back/Legs, 2 Mem)",
    "97544": "97544 - RF34/09/BK/BK/ (Back/Legs, 2 Mem)",
    "98035": "98035 - RF6707 (Head/Back)",
}

# OKIN 64-bit protocol variants (10-byte commands with 64-bit bitmasks)
OKIN_64BIT_VARIANT_NORDIC: Final = "nordic"
OKIN_64BIT_VARIANT_CUSTOM: Final = "custom"
OKIN_64BIT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto (Nordic UART)",
    OKIN_64BIT_VARIANT_NORDIC: "Nordic UART (fire-and-forget)",
    OKIN_64BIT_VARIANT_CUSTOM: "Custom OKIN (wait-for-response)",
}

# All protocol variants (for validation)
ALL_PROTOCOL_VARIANTS: Final = [
    VARIANT_AUTO,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_2,
    KAIDI_VARIANT_SEAT_3,
    KAIDI_VARIANT_SEAT_1_2,
    OKIN_CB24_VARIANT_OLD,
    OKIN_CB24_VARIANT_NEW,
    OKIN_CB24_VARIANT_CB24,
    OKIN_CB24_VARIANT_CB27,
    OKIN_CB24_VARIANT_CB24_AB,
    OKIN_CB24_VARIANT_CB1221,
    OKIN_CB24_VARIANT_DACHENG,
    OKIN_CB24_VARIANT_CB27NEW,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_JSON,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_KSBT04C,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_OKIN,
    KEESON_VARIANT_SERTA,
    KEESON_VARIANT_SINO,
    KEESON_VARIANT_PURPLE,
    "ore",  # Deprecated alias for Sino retained for existing config entries
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    LEGGETT_VARIANT_MLRM,
    SLEEP_NUMBER_VARIANT_LEFT,
    SLEEP_NUMBER_VARIANT_RIGHT,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    RICHMAT_VARIANT_PREFIX55,
    RICHMAT_VARIANT_PREFIXAA,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    *(_variant for _variant in OKIMAT_VARIANTS if _variant != VARIANT_AUTO),
    *(_variant for _variant in OKIN_DOT_VARIANTS if _variant != VARIANT_AUTO),
    OKIN_64BIT_VARIANT_NORDIC,
    OKIN_64BIT_VARIANT_CUSTOM,
    # SBI/Q-Plus variants
    SBI_VARIANT_BOTH,
    SBI_VARIANT_SIDE_A,
    SBI_VARIANT_SIDE_B,
    # Rondure variants (already in RONDURE_VARIANTS)
    RONDURE_VARIANT_BOTH,
    RONDURE_VARIANT_SIDE_A,
    RONDURE_VARIANT_SIDE_B,
]

# Bed types that require BLE pairing before they can be controlled
# These beds use encrypted connections and must be paired at the OS level.
#
# NOTE: Sleep Number Climate 360 / FlexFit (Fuzion "bamkey") is deliberately
# NOT listed here. The official SleepIQ app never creates an OS-level BLE bond
# (there is no createBond/ensureBond call in the decompiled Fuzion BLE manager,
# and the Auth characteristic is read-only). The bed "authenticates" purely at
# the application layer by reading the Auth + TransferInfo characteristics after
# every connect — handled by SleepNumberController._ensure_bed_presence_channel_primed().
# Forcing OS-level pair=True made ESP-IDF/ESPHome Bluetooth proxies return
# "auth fail reason=82" and leave the link wedged in the ESTABLISHED state, which
# broke every subsequent reconnect until the proxy was factory reset (issue #318).
BEDS_REQUIRING_PAIRING: Final[set[str]] = {
    BED_TYPE_OKIN_UUID,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_OKIMAT,
    BED_TYPE_VIBRADORM,
    BED_TYPE_LOGICDATA,
}

# Bed type + variant combinations that require BLE pairing
# Maps bed type to set of variants that require pairing for that specific bed type
# Note: Keeson's "okin" variant (OKIN FFE) does NOT require pairing - it's a different protocol
BED_TYPE_VARIANTS_REQUIRING_PAIRING: Final[dict[str, set[str]]] = {
    BED_TYPE_LEGGETT_PLATT: {LEGGETT_VARIANT_OKIN},
}


def requires_pairing(bed_type: str, protocol_variant: str | None = None) -> bool:
    """Check if a bed configuration requires BLE pairing.

    Args:
        bed_type: The bed type constant (e.g., BED_TYPE_LEGGETT_PLATT)
        protocol_variant: Optional protocol variant (e.g., "okin", "gen2")

    Returns:
        True if this bed/variant combination requires OS-level BLE pairing
    """
    # Direct bed type match
    if bed_type in BEDS_REQUIRING_PAIRING:
        return True
    # Check if this specific bed type + variant combination requires pairing
    if protocol_variant and bed_type in BED_TYPE_VARIANTS_REQUIRING_PAIRING:
        if protocol_variant in BED_TYPE_VARIANTS_REQUIRING_PAIRING[bed_type]:
            return True
    return False

# Bed types that support angle sensing (position feedback)
BEDS_WITH_ANGLE_SENSING: Final = frozenset(
    {
        BED_TYPE_LINAK,
        BED_TYPE_OKIMAT,
        BED_TYPE_OKIN_CST,
        BED_TYPE_OKIN_UUID,  # Same protocol as Okimat
        BED_TYPE_REVERIE,
        BED_TYPE_REVERIE_NIGHTSTAND,
    }
)

# Bed types that support position feedback (for Number entities with position seeking)
# Includes all angle sensing beds plus beds that report percentage positions
# Note: BED_TYPE_KEESON is NOT included here because only the ergomotion variant supports
# position feedback - this is handled specially in number.py with variant checking
# Note: BED_TYPE_SLEEP_NUMBER_MCR (BAM beds) is NOT included - the MCR controller only
# reports sleep-number values and bed presence over BLE, never motor angle/position
# feedback, so it must not get angle sensors or position-seeking number entities (#322).
BEDS_WITH_POSITION_FEEDBACK: Final = frozenset(
    {
        BED_TYPE_LINAK,
        BED_TYPE_OKIMAT,
        BED_TYPE_OKIN_CST,
        BED_TYPE_OKIN_UUID,  # Same protocol as Okimat
        BED_TYPE_REVERIE,
        BED_TYPE_REVERIE_NIGHTSTAND,
        BED_TYPE_ERGOMOTION,
        BED_TYPE_JENSEN,
        BED_TYPE_LIMOSS,
        BED_TYPE_SLEEP_NUMBER,
        BED_TYPE_VIBRADORM,
        BED_TYPE_SLEEPYS_BOX25,
    }
)

# Bed types that may have angle sensing enabled but report NO degree-angle data.
# Sleep Number MCR/BAM beds only report sleep-number values and bed presence over BLE
# (no motor angle feedback at all), so degree angle sensors would sit at "unknown"
# forever. These are skipped during angle-sensor creation regardless of the
# disable_angle_sensing option, which also fixes existing installs whose stored config
# still has angle sensing enabled (#322).
BEDS_WITHOUT_ANGLE_FEEDBACK: Final = frozenset({BED_TYPE_SLEEP_NUMBER_MCR})

# Bed types that report positions as 0-100 percentages (not angle degrees)
# These bed types return percentage values directly, so no angle-to-percent conversion is needed
BEDS_WITH_PERCENTAGE_POSITIONS: Final = frozenset(
    {
        BED_TYPE_KEESON,
        BED_TYPE_ERGOMOTION,
        BED_TYPE_SERTA,
        BED_TYPE_JENSEN,
        BED_TYPE_SLEEP_NUMBER,
        BED_TYPE_SLEEPYS_BOX25,
    }
)

# Position seeking constants
POSITION_TOLERANCE: Final = 3.0  # Angle tolerance in degrees for target reached
POSITION_OVERSHOOT_TOLERANCE: Final = (
    6.0  # Larger tolerance for overshoot detection (prevents oscillation)
)
POSITION_SEEK_TIMEOUT: Final = 60.0  # Maximum time in seconds for position seeking
POSITION_CHECK_INTERVAL: Final = 0.3  # Interval between position checks in seconds
POSITION_STALL_THRESHOLD: Final = 0.5  # Minimum movement in degrees to not be considered stalled
POSITION_STALL_COUNT: Final = 3  # Number of consecutive stall detections before stopping

# Default values
DEFAULT_MOTOR_COUNT: Final = 2
DEFAULT_HAS_MASSAGE: Final = False
DEFAULT_DISABLE_ANGLE_SENSING: Final = True  # For beds without angle sensing
DEFAULT_POSITION_MODE: Final = POSITION_MODE_SPEED
DEFAULT_PROTOCOL_VARIANT: Final = VARIANT_AUTO
DEFAULT_DISCONNECT_AFTER_COMMAND: Final = False
DEFAULT_IDLE_DISCONNECT_SECONDS: Final = 40
DEFAULT_OCTO_PIN: Final = ""
DEFAULT_CONNECTION_PROFILE: Final = CONNECTION_PROFILE_BALANCED

# Connection profiles
CONNECTION_PROFILES: Final = {
    CONNECTION_PROFILE_BALANCED: ConnectionProfileSettings(
        max_retries=3,
        retry_base_delay=2.0,  # 2s then 4s (with jitter)
        retry_jitter=0.2,
        connection_timeout=20.0,
        post_connect_delay=0.5,
    ),
    CONNECTION_PROFILE_RELIABLE: ConnectionProfileSettings(
        max_retries=3,
        retry_base_delay=3.0,  # 3s then 6s (with jitter)
        retry_jitter=0.2,
        connection_timeout=25.0,
        post_connect_delay=1.0,
    ),
}

# Default motor pulse values (can be overridden per device)
# These control how many command pulses are sent and the delay between them
# Different bed types have different optimal defaults
DEFAULT_MOTOR_PULSE_COUNT: Final = 10  # Default for most beds
DEFAULT_MOTOR_PULSE_DELAY_MS: Final = 100  # Default for most beds

# Per-bed-type motor pulse defaults based on app disassembly analysis
# Target: ~1.0 second total motor movement duration (repeat_count = 1000ms / delay_ms)
BED_MOTOR_PULSE_DEFAULTS: Final = {
    # Richmat: 150ms delay → 7 repeats = 1.05s total
    # Source: com.richmat.sleepfunction ANALYSIS.md
    BED_TYPE_RICHMAT: (7, 150),
    # Keeson: 100ms delay → 10 repeats = 1.0s total
    # Source: com.sfd.ergomotion ANALYSIS.md
    BED_TYPE_KEESON: (10, 100),
    # Ergomotion: 100ms delay → 10 repeats = 1.0s total
    # Source: com.sfd.ergomotion ANALYSIS.md
    BED_TYPE_ERGOMOTION: (10, 100),
    # Serta: 100ms delay → 10 repeats = 1.0s total
    # Source: com.ore.serta330 ANALYSIS.md
    BED_TYPE_SERTA: (10, 100),
    # Malouf Legacy OKIN: 150ms delay → 7 repeats = 1.05s total
    # Source: com.malouf.bedbase / com.lucid.bedbase ANALYSIS.md
    BED_TYPE_MALOUF_LEGACY_OKIN: (7, 150),
    # Malouf New OKIN (Nordic): 100ms delay → 10 repeats = 1.0s total
    # Source: com.malouf.bedbase / com.lucid.bedbase ANALYSIS.md
    BED_TYPE_MALOUF_NEW_OKIN: (10, 100),
    # OKIN FFE: 150ms delay → 7 repeats = 1.05s total
    # Source: com.lucid.bedbase ANALYSIS.md
    BED_TYPE_OKIN_FFE: (7, 150),
    # OKIN Nordic: 100ms delay → 10 repeats = 1.0s total
    # Source: com.lucid.bedbase ANALYSIS.md
    BED_TYPE_OKIN_NORDIC: (10, 100),
    # OKIN CB24: 300ms delay → 3 repeats = 0.9s total
    # Source: com.okin.bedding.smartbedwifi ANALYSIS.md
    BED_TYPE_OKIN_CB24: (3, 300),
    # OKIN DOT: FurniMove resends the held keycode ~every 100ms
    # (BluetoothLeService.onCharacteristicWrite Thread.sleep(100) loop)
    BED_TYPE_OKIN_DOT: (10, 100),
    # OKIN CB35: 300ms delay → 3 repeats = 0.9s total
    # Source: com.okin.sealy ANALYSIS.md (Timer.periodic 300ms, exTimes: 2 → 3 sends)
    BED_TYPE_OKIN_CB35: (3, 300),
    # OKIN ORE: 300ms delay → 1 repeat = 0.3s per command (preset-based)
    # Source: com.ore.bedding.glideawaymontion ANALYSIS.md
    BED_TYPE_OKIN_ORE: (1, 300),
    # Leggett WiLinke: 110ms delay → 10 repeats = 1.1s total
    # Source: RICHMAT_MASTER_ANALYSIS.md - MLRM devices use 110ms timing
    BED_TYPE_LEGGETT_WILINKE: (10, 110),
    # OCTO: 350ms delay → 3 repeats = 1.05s total
    # Source: de.octoactuators.octosmartcontrolapp ANALYSIS.md
    BED_TYPE_OCTO: (3, 350),
    # Jiecang: 100ms delay → 10 repeats = 1.0s total
    # Source: com.jiecang.app.android.jiecangbed ANALYSIS.md
    BED_TYPE_JIECANG: (10, 100),
    # Comfort Motion: 100ms delay → 10 repeats = 1.0s total
    # Source: com.jiecang.app.android.jiecangbed ANALYSIS.md
    BED_TYPE_COMFORT_MOTION: (10, 100),
    # Limoss: 80ms delay → 12 repeats = 0.96s total
    # Source: com.limoss.limossremote ANALYSIS.md (LIMOSS_SENDING_INTERVAL = 80ms)
    BED_TYPE_LIMOSS: (12, 80),
    # Linak: 100ms delay → 10 repeats = 1.0s total
    # Source: com.linak.linakbed.ble.memory ANALYSIS.md
    BED_TYPE_LINAK: (10, 100),
    # Sleepy's BOX15: 100ms delay → 10 repeats = 1.0s total
    # Source: com.okin.bedding.sleepy ANALYSIS.md
    BED_TYPE_SLEEPYS_BOX15: (10, 100),
    # Sleepy's BOX24: 100ms delay → 10 repeats = 1.0s total
    # Source: com.okin.bedding.sleepy ANALYSIS.md
    BED_TYPE_SLEEPYS_BOX24: (10, 100),
    # Jensen: 400ms delay → 3 repeats = 1.2s total
    # Source: air.no.jensen.adjustablesleep APK analysis (RaiseAndLower.as:79 uses 400ms)
    BED_TYPE_JENSEN: (3, 400),
    # Svane: 100ms delay → 10 repeats = 1.0s total
    # Source: com.produktide.svane.svaneremote ANALYSIS.md (motorRunnable posts every 100ms)
    BED_TYPE_SVANE: (10, 100),
    # Vibradorm: 100ms delay → 10 repeats = 1.0s total
    # Source: de.vibradorm.vra APK analysis (CmdMotorVMAT uses 100ms intervals)
    BED_TYPE_VIBRADORM: (10, 100),
    # Rondure: 50ms delay → 25 repeats = 1.25s total
    # Source: com.sfd.rondure_hump ANALYSIS.md
    BED_TYPE_RONDURE: (25, 50),
    # Remacro: 100ms delay → 10 repeats = 1.0s total (matches DEFAULT)
    # Source: com.cheers.jewmes ANALYSIS.md
    BED_TYPE_REMACRO: (10, 100),
    # Cool Base: 100ms delay → 10 repeats = 1.0s total (same as BaseI5)
    # Source: com.keeson.coolbase ANALYSIS.md
    BED_TYPE_COOLBASE: (10, 100),
    # Scott Living: 100ms delay → 10 repeats = 1.0s total
    # Source: com.keeson.scottlivingrelease ANALYSIS.md
    BED_TYPE_SCOTT_LIVING: (10, 100),
    # SBI/Q-Plus: 100ms delay → 10 repeats = 1.0s total
    # Source: com.sbi.costco ANALYSIS.md
    BED_TYPE_SBI: (10, 100),
    # SUTA: 150ms delay → 7 repeats = 1.05s total
    # Source: com.shuta.smart_home ANALYSIS.md
    BED_TYPE_SUTA: (7, 150),
    # TiMOTION AHF: 100ms delay → 10 repeats = 1.0s total
    # Source: com.timotion.ahf ANALYSIS.md
    BED_TYPE_TIMOTION_AHF: (10, 100),
    # Logicdata: 30ms delay → 10 repeats = 0.3s total
    # Source: at.silvermotion APK analysis (SF_GetPipelineTx sendCount=10, delay=30ms)
    BED_TYPE_LOGICDATA: (10, 30),
}
