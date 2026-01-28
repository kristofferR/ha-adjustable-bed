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
CONF_OCTO_PIN: Final = "octo_pin"
CONF_RICHMAT_REMOTE: Final = "richmat_remote"
CONF_JENSEN_PIN: Final = "jensen_pin"

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
BED_TYPE_LEGGETT_GEN2: Final = "leggett_gen2"  # Leggett Gen2 ASCII protocol
BED_TYPE_LEGGETT_OKIN: Final = "leggett_okin"  # Leggett Okin binary protocol
BED_TYPE_LEGGETT_WILINKE: Final = "leggett_wilinke"  # Leggett WiLinke 5-byte

# Bed types - Legacy naming (backwards compatibility)
# These map to the protocol-based types above
BED_TYPE_LINAK: Final = "linak"
BED_TYPE_RICHMAT: Final = "richmat"
BED_TYPE_SOLACE: Final = "solace"
BED_TYPE_MOTOSLEEP: Final = "motosleep"
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
BED_TYPE_SERTA: Final = "serta"  # Serta Motion Perfect (uses Keeson protocol with serta variant)
BED_TYPE_BEDTECH: Final = "bedtech"  # BedTech 5-byte ASCII protocol
BED_TYPE_JENSEN: Final = "jensen"  # Jensen JMC400/LinON Entry (6-byte commands)
BED_TYPE_OKIN_64BIT: Final = "okin_64bit"  # OKIN 64-bit protocol (10-byte commands)
BED_TYPE_SLEEPYS_BOX15: Final = "sleepys_box15"  # Sleepy's Elite BOX15 protocol (9-byte with checksum)
BED_TYPE_SLEEPYS_BOX24: Final = "sleepys_box24"  # Sleepy's Elite BOX24 protocol (7-byte)
BED_TYPE_SVANE: Final = "svane"  # Svane LinonPI multi-service protocol
BED_TYPE_VIBRADORM: Final = "vibradorm"  # Vibradorm VMAT protocol
BED_TYPE_RONDURE: Final = "rondure"  # 1500 Tilt Base / Rondure Hump (8/9-byte FurniBus protocol)
BED_TYPE_REMACRO: Final = "remacro"  # Remacro protocol (CheersSleep/Jeromes/Slumberland/The Brick, 8-byte SynData)
BED_TYPE_DIAGNOSTIC: Final = "diagnostic"

# All supported bed types (includes both protocol-based and legacy names)
SUPPORTED_BED_TYPES: Final = [
    # Protocol-based types (new naming)
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_NORDIC,
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
    # Serta Motion Perfect
    BED_TYPE_SERTA,
    # BedTech
    BED_TYPE_BEDTECH,
    # Jensen
    BED_TYPE_JENSEN,
    # OKIN 64-bit
    BED_TYPE_OKIN_64BIT,
    # Sleepy's Elite
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    # Svane
    BED_TYPE_SVANE,
    # Vibradorm
    BED_TYPE_VIBRADORM,
    # Rondure / 1500 Tilt Base
    BED_TYPE_RONDURE,
    # Remacro (CheersSleep / Jeromes / Slumberland / The Brick)
    BED_TYPE_REMACRO,
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
# Note: Shares FEE9 service with Richmat WiLinke but uses different packet format
BEDTECH_SERVICE_UUID: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
BEDTECH_WRITE_CHAR_UUID: Final = "d44bc439-abfd-45a2-b575-925416129600"

# WiLinke variants (5-byte commands with checksum)
# Source: com.desarketing.gmmotor (Germany Motions) APK blutter decompilation
# The app supports 6 BLE variants (Nordic + W1-W5), we track the WiLinke ones here
# W1 is the default fallback when no specific service is found
RICHMAT_WILINKE_W1_SERVICE_UUID: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
RICHMAT_WILINKE_SERVICE_UUIDS: Final = [
    "8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7",  # Custom (legacy, index 0)
    "0000fee9-0000-1000-8000-00805f9b34fb",  # W1 (index 1) - default fallback
    "0000fee9-0000-1000-8000-00805f9b34bb",  # W2 (index 2) - note different base UUID suffix
    "0000ffe0-0000-1000-8000-00805f9b34fb",  # W3 (index 3)
    "0000fff0-0000-1000-8000-00805f9b34fb",  # W4 (index 4) - Germany Motions DHN-* beds
    "0000e0ff-3c17-d293-8e48-14fe2e4da212",  # W5 (index 5) - custom base UUID
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
# KSBT variant - primary UUIDs (Nordic UART Service)
KEESON_KSBT_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
KEESON_KSBT_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# KSBT fallback service/characteristic UUIDs
# Some KSBT devices advertise with different service UUIDs but still use KSBT protocol
KEESON_KSBT_FALLBACK_GATT_PAIRS: Final = [
    # Fallback 1: FFE5/FFE9 (same as Base service)
    ("0000ffe5-0000-1000-8000-00805f9b34fb", "0000ffe9-0000-1000-8000-00805f9b34fb"),
    # Fallback 2: FFE0/FFE1
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

# Leggett & Platt specific UUIDs
# Gen2 variant (Richmat-based, ASCII commands)
LEGGETT_GEN2_SERVICE_UUID: Final = "45e25100-3171-4cfc-ae89-1d83cf8d8071"
LEGGETT_GEN2_WRITE_CHAR_UUID: Final = "45e25101-3171-4cfc-ae89-1d83cf8d8071"
LEGGETT_GEN2_READ_CHAR_UUID: Final = "45e25103-3171-4cfc-ae89-1d83cf8d8071"

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
# Peilin variant (secondary protocol)
COMFORT_MOTION_PEILIN_SERVICE_UUID: Final = "88121427-11e2-52a2-4615-ff00dec16800"
COMFORT_MOTION_PEILIN_CHAR_UUID: Final = "88121427-11e2-52a2-4615-ff00dec16801"

# DewertOkin specific (A H Beard, HankookGallery beds)
# Uses handle-based writes rather than UUID
DEWERTOKIN_WRITE_HANDLE: Final = 0x0013

# DewertOkin manufacturer data (BLE Company ID)
# Source: com.dewertokin.okinsmartcomfort app disassembly
MANUFACTURER_ID_DEWERTOKIN: Final = 1643  # 0x066B

# DewertOkin service UUID (unique to FurniMove/DewertOkin devices)
# This UUID can uniquely identify DewertOkin beds regardless of device name
DEWERTOKIN_SERVICE_UUID: Final = "00001523-0000-1000-8000-00805f9b34fb"

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

# Nectar specific UUIDs
# Protocol reverse-engineered by MaximumWorf (https://github.com/MaximumWorf/homeassistant-nectar)
# Uses OKIN service UUID but with 7-byte direct command format (similar to Mattress Firm 900)
# Note: Shares service UUID with Okimat but uses different command protocol
NECTAR_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
NECTAR_WRITE_CHAR_UUID: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
NECTAR_NOTIFY_CHAR_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"

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
# Okimat devices: "Okimat", "OKIN RF", "OKIN BLE", "OKIN-XXXXXX" (e.g., OKIN-346311), "OKIN luis",
# or "Smartbed" (Malouf/Lucid/CVB beds using OKIN protocol)
OKIMAT_NAME_PATTERNS: Final = ("okimat", "okin rf", "okin ble", "okin-", "okin luis", "smartbed")

# OKIN 64-bit name patterns (from com.okin.bedding.adjustbed app disassembly)
# Note: Most OKIN 64-bit devices don't have distinctive names - they require
# post-connection characteristic detection (presence of 62741625 read char)
OKIN_64BIT_NAME_PATTERNS: Final[tuple[str, ...]] = ()  # No reliable name patterns found

# BedTech name patterns (shares FEE9 service UUID with Richmat WiLinke)
# Post-connection characteristic detection (d44bc439...) is more reliable
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
# - base-i5.XXXXXXXX (e.g., base-i5.00000682)
# - KSBTXXXXCXXXXXX (e.g., KSBT03C000015046)
KEESON_NAME_PATTERNS: Final = ("base-i4.", "base-i5.", "ksbt")

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

# Jensen name patterns (JMC400 / LinON Entry)
# Source: com.hilding.jbg_ble APK analysis
JENSEN_NAME_PATTERNS: Final = ("jmc",)  # JMC400, JMC300, etc.

# Sleepy's Elite BOX24 protocol UUIDs (OKIN 64-bit service)
SLEEPYS_BOX24_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
SLEEPYS_BOX24_WRITE_CHAR_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"

# Jensen specific UUIDs (JMC400 / LinON Entry)
# Protocol reverse-engineered from com.hilding.jbg_ble APK
# Uses simple 6-byte command format with no checksum
JENSEN_SERVICE_UUID: Final = "00001234-0000-1000-8000-00805f9b34fb"
JENSEN_CHAR_UUID: Final = "00001111-0000-1000-8000-00805f9b34fb"

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
VIBRADORM_COMMAND_CHAR_UUID: Final = "00001526-9f03-0de5-96c5-b8f4f3081186"
VIBRADORM_LIGHT_CHAR_UUID: Final = "00001529-9f03-0de5-96c5-b8f4f3081186"
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

# Keeson variants
KEESON_VARIANT_BASE: Final = "base"
KEESON_VARIANT_KSBT: Final = "ksbt"
KEESON_VARIANT_ERGOMOTION: Final = "ergomotion"
KEESON_VARIANT_OKIN: Final = "okin"
KEESON_VARIANT_SERTA: Final = "serta"
KEESON_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect",
    KEESON_VARIANT_BASE: "BaseI4/BaseI5 (Member's Mark, Purple)",
    KEESON_VARIANT_KSBT: "KSBT (older Keeson remotes)",
    KEESON_VARIANT_ERGOMOTION: "Ergomotion (with position feedback)",
    KEESON_VARIANT_OKIN: "OKIN FFE (OKIN 13/15 series, 0xE6 prefix)",
    KEESON_VARIANT_SERTA: "Serta (Serta MP Remote)",
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

# Display names for remote selection
RICHMAT_REMOTES: Final = {
    RICHMAT_REMOTE_AUTO: "Auto (all features enabled)",
    RICHMAT_REMOTE_AZRN: "AZRN (Head, Pillow, Feet)",
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

    Counts the number of motor types present in the features:
    - MOTOR_HEAD
    - MOTOR_FEET
    - MOTOR_PILLOW
    - MOTOR_LUMBAR

    Returns:
        Motor count (0-4), minimum 2 for practical use.
    """
    count = 0
    if features & RichmatFeatures.MOTOR_HEAD:
        count += 1
    if features & RichmatFeatures.MOTOR_FEET:
        count += 1
    if features & RichmatFeatures.MOTOR_PILLOW:
        count += 1
    if features & RichmatFeatures.MOTOR_LUMBAR:
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

# Okimat remote code variants
# Different remotes have different command values and motor configurations
# Reference: https://github.com/richardhopton/smartbed-mqtt
OKIMAT_VARIANT_80608: Final = "80608"
OKIMAT_VARIANT_82417: Final = "82417"
OKIMAT_VARIANT_82418: Final = "82418"
OKIMAT_VARIANT_88875: Final = "88875"
OKIMAT_VARIANT_91244: Final = "91244"
OKIMAT_VARIANT_92471: Final = "92471"
OKIMAT_VARIANT_93329: Final = "93329"
OKIMAT_VARIANT_93332: Final = "93332"
OKIMAT_VARIANT_94238: Final = "94238"
OKIMAT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (try 82417 first)",
    OKIMAT_VARIANT_80608: "80608 - RFS ELLIPSE (Back, Legs)",
    OKIMAT_VARIANT_82417: "82417 - RF TOPLINE (Back, Legs)",
    OKIMAT_VARIANT_82418: "82418 - RF TOPLINE (Back, Legs, 2 Memory)",
    OKIMAT_VARIANT_88875: "88875 - RF LITELINE (Back, Legs)",
    OKIMAT_VARIANT_91244: "91244 - RF-FLASHLINE (Back, Legs)",
    OKIMAT_VARIANT_92471: "92471 - RF TOPLINE (Back, Legs, 2 Memory)",
    OKIMAT_VARIANT_93329: "93329 - RF TOPLINE (Head, Back, Legs, 4 Memory)",
    OKIMAT_VARIANT_93332: "93332 - RF TOPLINE (Head, Back, Legs, Feet, 2 Memory)",
    OKIMAT_VARIANT_94238: "94238 - RF FLASHLINE (Back, Legs, 2 Memory)",
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
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_OKIN,
    KEESON_VARIANT_SERTA,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    LEGGETT_VARIANT_MLRM,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    RICHMAT_VARIANT_PREFIX55,
    RICHMAT_VARIANT_PREFIXAA,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    OKIMAT_VARIANT_80608,
    OKIMAT_VARIANT_82417,
    OKIMAT_VARIANT_82418,
    OKIMAT_VARIANT_88875,
    OKIMAT_VARIANT_91244,
    OKIMAT_VARIANT_92471,
    OKIMAT_VARIANT_93329,
    OKIMAT_VARIANT_93332,
    OKIMAT_VARIANT_94238,
    OKIN_64BIT_VARIANT_NORDIC,
    OKIN_64BIT_VARIANT_CUSTOM,
]

# Bed types that require BLE pairing before they can be controlled
# These beds use encrypted connections and must be paired at the OS level
BEDS_REQUIRING_PAIRING: Final[set[str]] = {BED_TYPE_OKIN_UUID, BED_TYPE_LEGGETT_OKIN, BED_TYPE_OKIMAT}

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
        BED_TYPE_OKIN_UUID,  # Same protocol as Okimat
        BED_TYPE_REVERIE,
        BED_TYPE_REVERIE_NIGHTSTAND,
    }
)

# Bed types that support position feedback (for Number entities with position seeking)
# Includes all angle sensing beds plus beds that report percentage positions
# Note: BED_TYPE_KEESON is NOT included here because only the ergomotion variant supports
# position feedback - this is handled specially in number.py with variant checking
BEDS_WITH_POSITION_FEEDBACK: Final = frozenset(
    {
        BED_TYPE_LINAK,
        BED_TYPE_OKIMAT,
        BED_TYPE_OKIN_UUID,  # Same protocol as Okimat
        BED_TYPE_REVERIE,
        BED_TYPE_REVERIE_NIGHTSTAND,
        BED_TYPE_ERGOMOTION,
        BED_TYPE_JENSEN,
        BED_TYPE_VIBRADORM,
    }
)

# Bed types that report positions as 0-100 percentages (not angle degrees)
# These bed types return percentage values directly, so no angle-to-percent conversion is needed
BEDS_WITH_PERCENTAGE_POSITIONS: Final = frozenset(
    {
        BED_TYPE_KEESON,
        BED_TYPE_ERGOMOTION,
        BED_TYPE_SERTA,
        BED_TYPE_JENSEN,
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
    # Leggett WiLinke: 150ms delay → 7 repeats = 1.05s total
    # Source: com.richmat.sleepfunction ANALYSIS.md - WiLinke protocol variant
    BED_TYPE_LEGGETT_WILINKE: (7, 150),
    # OCTO: 350ms delay → 3 repeats = 1.05s total
    # Source: de.octoactuators.octosmartcontrolapp ANALYSIS.md
    BED_TYPE_OCTO: (3, 350),
    # Jiecang: 100ms delay → 10 repeats = 1.0s total
    # Source: com.jiecang.app.android.jiecangbed ANALYSIS.md
    BED_TYPE_JIECANG: (10, 100),
    # Comfort Motion: 100ms delay → 10 repeats = 1.0s total
    # Source: com.jiecang.app.android.jiecangbed ANALYSIS.md
    BED_TYPE_COMFORT_MOTION: (10, 100),
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
}
