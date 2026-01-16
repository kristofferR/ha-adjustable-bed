"""Constants for the Adjustable Bed integration."""

from typing import Final

DOMAIN: Final = "adjustable_bed"

# Configuration keys
CONF_BED_TYPE: Final = "bed_type"
CONF_PROTOCOL_VARIANT: Final = "protocol_variant"
CONF_MOTOR_COUNT: Final = "motor_count"
CONF_HAS_MASSAGE: Final = "has_massage"
CONF_DISABLE_ANGLE_SENSING: Final = "disable_angle_sensing"
CONF_PREFERRED_ADAPTER: Final = "preferred_adapter"
CONF_MOTOR_PULSE_COUNT: Final = "motor_pulse_count"
CONF_MOTOR_PULSE_DELAY_MS: Final = "motor_pulse_delay_ms"
CONF_DISCONNECT_AFTER_COMMAND: Final = "disconnect_after_command"
CONF_IDLE_DISCONNECT_SECONDS: Final = "idle_disconnect_seconds"
CONF_POSITION_MODE: Final = "position_mode"
CONF_OCTO_PIN: Final = "octo_pin"

# Position mode values
POSITION_MODE_SPEED: Final = "speed"
POSITION_MODE_ACCURACY: Final = "accuracy"

# Special value for auto adapter selection
ADAPTER_AUTO: Final = "auto"

# Bed types
BED_TYPE_LINAK: Final = "linak"
BED_TYPE_RICHMAT: Final = "richmat"
BED_TYPE_SOLACE: Final = "solace"
BED_TYPE_MOTOSLEEP: Final = "motosleep"
BED_TYPE_REVERIE: Final = "reverie"
BED_TYPE_LEGGETT_PLATT: Final = "leggett_platt"
BED_TYPE_OKIMAT: Final = "okimat"
BED_TYPE_KEESON: Final = "keeson"
BED_TYPE_ERGOMOTION: Final = "ergomotion"
BED_TYPE_JIECANG: Final = "jiecang"
BED_TYPE_DEWERTOKIN: Final = "dewertokin"
BED_TYPE_SERTA: Final = "serta"
BED_TYPE_OCTO: Final = "octo"
BED_TYPE_MATTRESSFIRM: Final = "mattressfirm"
BED_TYPE_NECTAR: Final = "nectar"

SUPPORTED_BED_TYPES: Final = [
    BED_TYPE_LINAK,
    BED_TYPE_RICHMAT,
    BED_TYPE_SOLACE,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_REVERIE,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OKIMAT,
    BED_TYPE_KEESON,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_SERTA,
    BED_TYPE_OCTO,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_NECTAR,
]

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

# Richmat specific UUIDs
# Nordic variant (simple single-byte commands)
RICHMAT_NORDIC_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RICHMAT_NORDIC_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# WiLinke variants (5-byte commands with checksum)
RICHMAT_WILINKE_SERVICE_UUIDS: Final = [
    "8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7",
    "0000fee9-0000-1000-8000-00805f9b34fb",
    "0000fee9-0000-1000-8000-00805f9b34bb",
    "0000fff0-0000-1000-8000-00805f9b34fb",
]
RICHMAT_WILINKE_CHAR_UUIDS: Final = [
    ("d44bc439-abfd-45a2-b575-925416129600", "d44bc439-abfd-45a2-b575-925416129601"),
    ("d44bc439-abfd-45a2-b575-925416129600", "d44bc439-abfd-45a2-b575-925416129601"),
    ("d44bc439-abfd-45a2-b575-925416129622", "d44bc439-abfd-45a2-b575-925416129611"),
    ("0000fff2-0000-1000-8000-00805f9b34fb", "0000fff1-0000-1000-8000-00805f9b34fb"),
]

# Keeson specific UUIDs
# KSBT variant
KEESON_KSBT_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
KEESON_KSBT_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

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

# Reverie specific UUIDs
REVERIE_SERVICE_UUID: Final = "1b1d9641-b942-4da8-89cc-98e6a58fbd93"
REVERIE_CHAR_UUID: Final = "6af87926-dc79-412e-a3e0-5f85c2d55de2"

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

# DewertOkin specific (A H Beard, HankookGallery beds)
# Uses handle-based writes rather than UUID
DEWERTOKIN_WRITE_HANDLE: Final = 0x0013

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

# Octo variant identifiers (dict defined later after VARIANT_AUTO)
OCTO_VARIANT_STANDARD: Final = "standard"
OCTO_VARIANT_STAR2: Final = "star2"

# Mattress Firm 900 specific UUIDs
# Protocol reverse-engineered by David Delahoz (https://github.com/daviddelahoz/BLEAdjustableBase)
# Uses Nordic UART Service with custom 7-byte command format
MATTRESSFIRM_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
MATTRESSFIRM_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Nectar specific UUIDs
# Protocol reverse-engineered by MaximumWorf (https://github.com/MaximumWorf/homeassistant-nectar)
# Uses OKIN service UUID but with 7-byte direct command format (similar to Mattress Firm 900)
# Note: Shares service UUID with Okimat but uses different command protocol
NECTAR_SERVICE_UUID: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
NECTAR_WRITE_CHAR_UUID: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
NECTAR_NOTIFY_CHAR_UUID: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"

# Detection name patterns for beds sharing the OKIN service UUID
# Multiple bed types share the same UUID (62741523-...), so name patterns help disambiguate:
# - Nectar (7-byte protocol)
# - Okimat (6-byte protocol)
# - Leggett & Platt Okin variant (6-byte protocol, same as Okimat)
# Detection priority: name patterns first, then UUID fallback to Okimat
LEGGETT_OKIN_NAME_PATTERNS: Final = ("leggett", "l&p")
# Okimat devices: "Okimat", "OKIN RF", "OKIN BLE", or "OKIN-XXXXXX" (e.g., OKIN-346311)
OKIMAT_NAME_PATTERNS: Final = ("okimat", "okin rf", "okin ble", "okin-")

# Keeson name patterns for devices that may not advertise the specific service UUID
# - base-i4.XXXXXXXX (e.g., base-i4.00002574)
# - base-i5.XXXXXXXX (e.g., base-i5.00000682)
# - KSBTXXXXCXXXXXX (e.g., KSBT03C000015046)
KEESON_NAME_PATTERNS: Final = ("base-i4.", "base-i5.", "ksbt")

# Richmat Nordic name patterns (e.g., QRRM157052)
RICHMAT_NAME_PATTERNS: Final = ("qrrm",)

# Ergomotion name patterns
# - "ergomotion", "ergo" (generic)
# - "serta-i" prefix for Serta-branded ErgoMotion beds (e.g., Serta-i490350)
ERGOMOTION_NAME_PATTERNS: Final = ("ergomotion", "ergo", "serta-i")

# Protocol variants
VARIANT_AUTO: Final = "auto"

# Keeson variants
KEESON_VARIANT_BASE: Final = "base"
KEESON_VARIANT_KSBT: Final = "ksbt"
KEESON_VARIANT_ERGOMOTION: Final = "ergomotion"
KEESON_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect",
    KEESON_VARIANT_BASE: "BaseI4/BaseI5 (Member's Mark, Purple)",
    KEESON_VARIANT_KSBT: "KSBT (older Keeson remotes)",
    KEESON_VARIANT_ERGOMOTION: "Ergomotion (with position feedback)",
}

# Leggett & Platt variants
LEGGETT_VARIANT_GEN2: Final = "gen2"
LEGGETT_VARIANT_OKIN: Final = "okin"
LEGGETT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect",
    LEGGETT_VARIANT_GEN2: "Gen2 (Richmat-based, most common)",
    LEGGETT_VARIANT_OKIN: "Okin (requires BLE pairing)",
}

# Richmat variants (auto-detected, but can be overridden)
RICHMAT_VARIANT_NORDIC: Final = "nordic"
RICHMAT_VARIANT_WILINKE: Final = "wilinke"
# Richmat remote codes (for documentation - all use same command values)
# Reference: https://github.com/richardhopton/smartbed-mqtt/blob/main/src/Richmat/remoteFeatures.ts
RICHMAT_VARIANT_190_0055: Final = "190-0055"
RICHMAT_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (recommended)",
    RICHMAT_VARIANT_NORDIC: "Nordic (single-byte commands)",
    RICHMAT_VARIANT_WILINKE: "WiLinke (5-byte commands with checksum)",
    RICHMAT_VARIANT_190_0055: "190-0055 (Head, Pillow, Feet, Massage, Lights)",
}

# Octo variants
OCTO_VARIANTS: Final = {
    VARIANT_AUTO: "Auto-detect (recommended)",
    OCTO_VARIANT_STANDARD: "Standard Octo (most common)",
    OCTO_VARIANT_STAR2: "Octo Remote Star2",
}

# Richmat command protocols (how command bytes are encoded - used internally)
RICHMAT_PROTOCOL_WILINKE: Final = "wilinke"  # [110, 1, 0, cmd, cmd+111]
RICHMAT_PROTOCOL_SINGLE: Final = "single"  # [cmd]

# Okimat remote code variants
# Different remotes have different command values and motor configurations
# Reference: https://github.com/richardhopton/smartbed-mqtt
OKIMAT_VARIANT_80608: Final = "80608"
OKIMAT_VARIANT_82417: Final = "82417"
OKIMAT_VARIANT_82418: Final = "82418"
OKIMAT_VARIANT_88875: Final = "88875"
OKIMAT_VARIANT_91244: Final = "91244"
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
    OKIMAT_VARIANT_93329: "93329 - RF TOPLINE (Head, Back, Legs, 4 Memory)",
    OKIMAT_VARIANT_93332: "93332 - RF TOPLINE (Head, Back, Legs, Feet, 2 Memory)",
    OKIMAT_VARIANT_94238: "94238 - RF FLASHLINE (Back, Legs, 2 Memory)",
}

# All protocol variants (for validation)
ALL_PROTOCOL_VARIANTS: Final = [
    VARIANT_AUTO,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_ERGOMOTION,
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_OKIN,
    RICHMAT_VARIANT_NORDIC,
    RICHMAT_VARIANT_WILINKE,
    RICHMAT_VARIANT_190_0055,
    OCTO_VARIANT_STANDARD,
    OCTO_VARIANT_STAR2,
    OKIMAT_VARIANT_80608,
    OKIMAT_VARIANT_82417,
    OKIMAT_VARIANT_82418,
    OKIMAT_VARIANT_88875,
    OKIMAT_VARIANT_91244,
    OKIMAT_VARIANT_93329,
    OKIMAT_VARIANT_93332,
    OKIMAT_VARIANT_94238,
]

# Bed types that support angle sensing (position feedback)
BEDS_WITH_ANGLE_SENSING: Final = frozenset({
    BED_TYPE_LINAK,
    BED_TYPE_OKIMAT,
})

# Default values
DEFAULT_MOTOR_COUNT: Final = 2
DEFAULT_HAS_MASSAGE: Final = False
DEFAULT_DISABLE_ANGLE_SENSING: Final = True  # For beds without angle sensing
DEFAULT_POSITION_MODE: Final = POSITION_MODE_SPEED
DEFAULT_PROTOCOL_VARIANT: Final = VARIANT_AUTO
DEFAULT_DISCONNECT_AFTER_COMMAND: Final = False
DEFAULT_IDLE_DISCONNECT_SECONDS: Final = 40
DEFAULT_OCTO_PIN: Final = ""

# Default motor pulse values (can be overridden per device)
# These control how many command pulses are sent and the delay between them
# Different bed types have different optimal defaults
DEFAULT_MOTOR_PULSE_COUNT: Final = 25  # Default for most beds
DEFAULT_MOTOR_PULSE_DELAY_MS: Final = 50  # Default for most beds

# Per-bed-type motor pulse defaults (to preserve original behavior)
BED_MOTOR_PULSE_DEFAULTS: Final = {
    # Richmat: 30 repeats, 50ms delay (original hardcoded values)
    BED_TYPE_RICHMAT: (30, 50),
    # Keeson: 25 repeats, 200ms delay (original hardcoded values)
    BED_TYPE_KEESON: (25, 200),
}

