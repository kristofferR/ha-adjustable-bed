"""Bed type detection logic for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import SelectOptionDict

if TYPE_CHECKING:
    from bleak import BleakClient

from bleak.exc import BleakError

from .const import (
    # Legacy/brand-specific bed types
    # NOTE: BED_TYPE_BEDTECH and BED_TYPE_OKIN_64BIT can now be partially auto-detected:
    # - BedTech: By name pattern ("bedtech") or post-connection characteristic check
    # - OKIN 64-bit: By post-connection characteristic check (62741625 read char)
    # Full auto-detection requires connecting to examine GATT characteristics.
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_JENSEN,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_FFE,
    # Protocol-based bed types (new)
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SOLACE,
    BED_TYPE_SVANE,
    BED_TYPE_VIBRADORM,
    # Detection constants
    BEDTECH_NAME_PATTERNS,
    BEDTECH_SERVICE_UUID,
    BEDTECH_WRITE_CHAR_UUID,
    COMFORT_MOTION_SERVICE_UUID,
    JENSEN_NAME_PATTERNS,
    JENSEN_SERVICE_UUID,
    DEWERTOKIN_NAME_PATTERNS,
    DEWERTOKIN_SERVICE_UUID,
    ERGOMOTION_NAME_PATTERNS,
    KEESON_BASE_SERVICE_UUID,
    KEESON_NAME_PATTERNS,
    LEGGETT_GEN2_SERVICE_UUID,
    LEGGETT_OKIN_NAME_PATTERNS,
    LEGGETT_RICHMAT_NAME_PATTERNS,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_NAME_PATTERNS,
    LINAK_POSITION_SERVICE_UUID,
    MALOUF_LEGACY_OKIN_SERVICE_UUID,
    MALOUF_NAME_PATTERNS,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
    MANUFACTURER_ID_DEWERTOKIN,
    MANUFACTURER_ID_VIBRADORM,
    OCTO_NAME_PATTERNS,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_NAME_PATTERNS,
    OKIMAT_NOTIFY_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIN_FFE_NAME_PATTERNS,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NAME_PATTERNS,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SERTA_NAME_PATTERNS,
    SLEEPYS_NAME_PATTERNS,
    SOLACE_NAME_PATTERNS,
    SOLACE_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_NAME_PATTERNS,
    VIBRADORM_NAME_PATTERNS,
    VIBRADORM_SERVICE_UUID,
    # Detection result type
    DetectionResult,
)

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

# Richmat remote code pattern (e.g., QRRM, V1RM, BURM, ZR10, ZR60)
# Matches: 2 alphanumeric + "R" + "M" or "N" (like QRRM, V1RM, BURM, A0RN)
# Or: "ZR" + 2 digits (like ZR10, ZR60)
# Case-insensitive via re.IGNORECASE
RICHMAT_CODE_PATTERN = re.compile(r"^([a-z0-9]{2}r[mn]|zr[0-9]{2})", re.IGNORECASE)


def detect_richmat_remote_from_name(device_name: str | None) -> str | None:
    """Extract Richmat remote code from device name.

    Richmat devices typically have names like:
    - "QRRM157052" -> extracts "qrrm"
    - "V1RM123456" -> extracts "v1rm"
    - "Sleep Function 2.0" -> returns "i7rm" (known alias)
    - "X1RM...." -> extracts "x1rm"

    Args:
        device_name: The BLE device name

    Returns:
        The detected remote code (lowercase) or None if not detected.
    """
    if not device_name:
        return None

    name_lower = device_name.lower()

    # Special aliases that map to known remote codes
    if "sleep function" in name_lower:
        return "i7rm"

    # Try to extract the 4-character code prefix
    match = RICHMAT_CODE_PATTERN.match(name_lower)
    if match:
        code = match.group(1)
        _LOGGER.debug("Detected Richmat remote code '%s' from name '%s'", code, device_name)
        return code

    return None


def is_mac_like_name(name: str | None) -> bool:
    """Check if name is None, empty, or looks like a MAC address."""
    if not name:
        return True
    return bool(MAC_ADDRESS_PATTERN.match(name))


def _check_manufacturer_data(
    manufacturer_data: dict[int, bytes] | None,
) -> tuple[str | None, float, int | None]:
    """Check manufacturer data for bed identification.

    Args:
        manufacturer_data: Dictionary mapping Company ID to data bytes

    Returns:
        Tuple of (bed_type, confidence, manufacturer_id) or (None, 0.0, None)
    """
    if not manufacturer_data:
        return None, 0.0, None

    # DewertOkin: Company ID 1643 (0x066B)
    # Source: com.dewertokin.okinsmartcomfort app disassembly
    if MANUFACTURER_ID_DEWERTOKIN in manufacturer_data:
        return BED_TYPE_DEWERTOKIN, 0.95, MANUFACTURER_ID_DEWERTOKIN

    # Vibradorm: Company ID 944 (0x03B0)
    # Source: de.vibradorm.vra app disassembly
    if MANUFACTURER_ID_VIBRADORM in manufacturer_data:
        return BED_TYPE_VIBRADORM, 0.95, MANUFACTURER_ID_VIBRADORM

    return None, 0.0, None


# Solace naming convention pattern (e.g., S4-Y-192-461000AD)
SOLACE_NAME_PATTERN = re.compile(r"^s\d+-[a-z]-\d+-[a-z0-9]+$", re.IGNORECASE)

# Device name patterns that should NOT be detected as beds
# These use generic BUIDs that beds also use, but are clearly not beds
EXCLUDED_DEVICE_PATTERNS: tuple[str, ...] = (
    "scooter",
    "ninebot",
    "segway",
    "ebike",
    "e-bike",
    "escooter",
    "e-scooter",
    "skateboard",
    "hoverboard",
)

# Display names for bed types shown in the UI selector
# Note: Legacy types (dewertokin, okimat, nectar, mattressfirm, leggett_platt)
# are NOT included here - they're only kept for backward compatibility with
# existing config entries. New users should select the protocol-based equivalents.
BED_TYPE_DISPLAY_NAMES: dict[str, str] = {
    # Protocol-based types (Okin family)
    BED_TYPE_OKIN_HANDLE: "Okin Handle (DewertOkin, A H Beard)",
    BED_TYPE_OKIN_UUID: "Okin UUID (Okimat, Lucid, requires pairing)",
    BED_TYPE_OKIN_7BYTE: "Okin 7-Byte (Nectar)",
    BED_TYPE_OKIN_NORDIC: "Okin Nordic (Mattress Firm 900, iFlex)",
    BED_TYPE_OKIN_FFE: "Okin FFE (13/15 series)",
    BED_TYPE_OKIN_64BIT: "Okin 64-Bit (10-byte commands)",
    # Protocol-based types (Leggett & Platt family)
    BED_TYPE_LEGGETT_GEN2: "Leggett & Platt Gen2",
    BED_TYPE_LEGGETT_OKIN: "Leggett & Platt Okin (requires pairing)",
    BED_TYPE_LEGGETT_WILINKE: "Leggett & Platt WiLinke (MlRM)",
    # Brand-specific types
    BED_TYPE_BEDTECH: "BedTech",
    BED_TYPE_ERGOMOTION: "Ergomotion",
    BED_TYPE_JIECANG: "Jiecang (Glide, Dream Motion)",
    BED_TYPE_JENSEN: "Jensen (JMC400, LinON Entry)",
    BED_TYPE_KEESON: "Keeson (Member's Mark, Purple, Serta)",
    BED_TYPE_LINAK: "Linak",
    BED_TYPE_MALOUF_LEGACY_OKIN: "Malouf (FFE5 protocol)",
    BED_TYPE_MALOUF_NEW_OKIN: "Malouf (Nordic UART protocol)",
    BED_TYPE_MOTOSLEEP: "MotoSleep",
    BED_TYPE_OCTO: "Octo",
    BED_TYPE_REVERIE: "Reverie (Protocol 108)",
    BED_TYPE_REVERIE_NIGHTSTAND: "Reverie Nightstand (Protocol 110)",
    BED_TYPE_RICHMAT: "Richmat",
    BED_TYPE_COMFORT_MOTION: "Comfort Motion (Lierda)",
    BED_TYPE_SERTA: "Serta Motion Perfect",
    BED_TYPE_SLEEPYS_BOX15: "Sleepy's Elite (BOX15, with lumbar)",
    BED_TYPE_SLEEPYS_BOX24: "Sleepy's Elite (BOX24)",
    BED_TYPE_SOLACE: "Solace",
    BED_TYPE_SVANE: "Svane",
    BED_TYPE_VIBRADORM: "Vibradorm (VMAT)",
    # Diagnostic
    BED_TYPE_DIAGNOSTIC: "Diagnostic (unknown bed)",
}


def get_bed_type_options() -> list[SelectOptionDict]:
    """Get bed type options sorted alphabetically by display name."""
    return [
        SelectOptionDict(value=bed_type, label=display_name)
        for bed_type, display_name in sorted(
            BED_TYPE_DISPLAY_NAMES.items(), key=lambda x: x[1].lower()
        )
    ]


def detect_bed_type(service_info: BluetoothServiceInfoBleak) -> str | None:
    """Detect bed type from service info.

    Returns:
        The detected bed type constant, or None if not detected.
        For detailed detection with confidence scores, use detect_bed_type_detailed().
    """
    result = detect_bed_type_detailed(service_info)
    return result.bed_type


def detect_bed_type_detailed(service_info: BluetoothServiceInfoBleak) -> DetectionResult:
    """Detect bed type from service info with detailed confidence scoring.

    Returns:
        DetectionResult with bed_type, confidence score, and detection signals.
        Use requires_characteristic_check to determine if post-connection
        detection can improve confidence (for ambiguous UUID cases).
    """
    # Handle devices that report None for service_uuids
    raw_uuids = service_info.service_uuids
    service_uuids = [str(uuid).lower() for uuid in raw_uuids] if raw_uuids else []
    device_name = (service_info.name or "").lower()
    signals: list[str] = []

    _LOGGER.debug(
        "Detecting bed type for device %s (name: %s)",
        service_info.address,
        service_info.name,
    )
    _LOGGER.debug("  Service UUIDs: %s", service_uuids)
    _LOGGER.debug("  Manufacturer data: %s", service_info.manufacturer_data)

    # Exclude devices that are clearly not beds based on name
    # These often use the same generic BLE UUIDs as beds
    for pattern in EXCLUDED_DEVICE_PATTERNS:
        if pattern in device_name:
            _LOGGER.debug(
                "Device %s excluded: name '%s' matches excluded pattern '%s'",
                service_info.address,
                service_info.name,
                pattern,
            )
            return DetectionResult(bed_type=None, confidence=0.0, signals=["excluded:" + pattern])

    # Priority 1: Check manufacturer data (highest confidence, unique signal)
    mfr_bed_type, mfr_confidence, mfr_id = _check_manufacturer_data(service_info.manufacturer_data)
    if mfr_bed_type:
        signals.append(f"manufacturer_id:{mfr_id}")
        _LOGGER.info(
            "Detected %s bed at %s (name: %s) by manufacturer ID %s",
            mfr_bed_type,
            service_info.address,
            service_info.name,
            mfr_id,
        )
        return DetectionResult(
            bed_type=mfr_bed_type,
            confidence=mfr_confidence,
            signals=signals,
            manufacturer_id=mfr_id,
        )

    # Priority 2: Check for DewertOkin unique service UUID
    if DEWERTOKIN_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:dewertokin")
        _LOGGER.info(
            "Detected DewertOkin bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_DEWERTOKIN,
            confidence=0.9,
            signals=signals,
        )

    # Check for Jensen - unique service UUID (00001234)
    if JENSEN_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:jensen")
        _LOGGER.info(
            "Detected Jensen bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_JENSEN,
            confidence=1.0,
            signals=signals,
        )

    # Check for Jensen by name pattern (JMC400)
    if any(device_name.startswith(pattern) for pattern in JENSEN_NAME_PATTERNS):
        signals.append("name:jensen")
        _LOGGER.info(
            "Detected Jensen bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_JENSEN,
            confidence=0.9,
            signals=signals,
        )

    # Check for Vibradorm - unique service UUID (1525)
    if VIBRADORM_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:vibradorm")
        _LOGGER.info(
            "Detected Vibradorm bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_VIBRADORM,
            confidence=1.0,
            signals=signals,
        )

    # Check for Vibradorm by name pattern (VMAT*)
    if any(device_name.startswith(pattern) for pattern in VIBRADORM_NAME_PATTERNS):
        signals.append("name:vibradorm")
        _LOGGER.info(
            "Detected Vibradorm bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_VIBRADORM,
            confidence=0.9,
            signals=signals,
        )

    # Check for Svane - unique service UUID (abcb)
    if SVANE_HEAD_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:svane")
        _LOGGER.info(
            "Detected Svane bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SVANE,
            confidence=1.0,
            signals=signals,
        )

    # Check for Svane by name pattern
    if any(pattern in device_name for pattern in SVANE_NAME_PATTERNS):
        signals.append("name:svane")
        _LOGGER.info(
            "Detected Svane bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SVANE,
            confidence=0.9,
            signals=signals,
        )

    # Check for Malouf NEW_OKIN - unique advertised service UUID (most specific first)
    if MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:malouf_new_okin")
        _LOGGER.info(
            "Detected Malouf NEW_OKIN bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_MALOUF_NEW_OKIN, confidence=1.0, signals=signals)

    # Check for Linak - most specific first
    # Some Linak beds may advertise position service but not control service
    if (
        LINAK_CONTROL_SERVICE_UUID.lower() in service_uuids
        or LINAK_POSITION_SERVICE_UUID.lower() in service_uuids
    ):
        signals.append("uuid:linak")
        _LOGGER.info(
            "Detected Linak bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_LINAK, confidence=1.0, signals=signals)

    # Check for Linak by name pattern (e.g., "Bed 1696")
    # Some Linak beds don't advertise service UUIDs in their BLE beacon
    for pattern in LINAK_NAME_PATTERNS:
        if device_name.startswith(pattern) and device_name[len(pattern) :].isdigit():
            signals.append("name:linak")
            _LOGGER.info(
                "Detected Linak bed at %s (name: %s) by name pattern",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_LINAK, confidence=0.9, signals=signals)

    # Check for Leggett & Platt Gen2 (must check before generic UUIDs)
    if LEGGETT_GEN2_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:leggett_gen2")
        _LOGGER.info(
            "Detected Leggett & Platt Gen2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_LEGGETT_GEN2, confidence=1.0, signals=signals)

    # Check for Reverie Nightstand (Protocol 110) - more specific UUID
    if REVERIE_NIGHTSTAND_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:reverie_nightstand")
        _LOGGER.info(
            "Detected Reverie Nightstand bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_REVERIE_NIGHTSTAND, confidence=1.0, signals=signals)

    # Check for Reverie (Protocol 108)
    if REVERIE_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:reverie")
        _LOGGER.info(
            "Detected Reverie bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_REVERIE, confidence=1.0, signals=signals)

    # Check for Sleepy's Elite BOX24 - name-based detection (before Okimat since same UUID)
    # Sleepy's BOX24 beds use OKIN 64-bit service UUID
    if (
        any(pattern in device_name for pattern in SLEEPYS_NAME_PATTERNS)
        and OKIMAT_SERVICE_UUID.lower() in service_uuids
    ):
        signals.append("uuid:okin")
        signals.append("name:sleepys")
        _LOGGER.info(
            "Detected Sleepy's Elite BOX24 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SLEEPYS_BOX24, confidence=0.9, signals=signals
        )

    # Check for Nectar - name-based detection (before Okimat since same UUID)
    # Nectar beds use OKIN service UUID but different command protocol
    if "nectar" in device_name and OKIMAT_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:okin")
        signals.append("name:nectar")
        _LOGGER.info(
            "Detected Nectar bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_NECTAR, confidence=0.9, signals=signals)

    # Check for beds using OKIN service UUID (Okimat, Leggett Okin, Nectar, OKIN 64-bit)
    # Nectar is already handled above by name check
    # Use name patterns to disambiguate between Okimat and Leggett Okin
    # Note: OKIN 64-bit cannot be reliably detected without connecting
    if OKIMAT_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:okin")
        # Check for Leggett & Platt Okin by name patterns
        if any(pattern in device_name for pattern in LEGGETT_OKIN_NAME_PATTERNS):
            signals.append("name:leggett")
            _LOGGER.info(
                "Detected Leggett & Platt Okin bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_LEGGETT_OKIN, confidence=0.9, signals=signals)

        # Check for Okimat-specific name patterns
        if any(pattern in device_name for pattern in OKIMAT_NAME_PATTERNS):
            signals.append("name:okimat")
            _LOGGER.info(
                "Detected Okimat bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_OKIMAT, confidence=0.9, signals=signals)

        # Fallback: default to Okimat with warning about ambiguity
        # This UUID is shared by Okimat, Leggett Okin, and OKIN 64-bit
        _LOGGER.warning(
            "Okin UUID detected but device name '%s' at %s doesn't match known patterns. "
            "Defaulting to Okimat. Change to Leggett & Platt or OKIN 64-bit in settings if needed.",
            service_info.name,
            service_info.address,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIMAT,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[BED_TYPE_LEGGETT_OKIN, BED_TYPE_OKIN_64BIT],
            requires_characteristic_check=True,
        )

    # Check for BedTech - name-based detection (before Richmat WiLinke since same UUID)
    # BedTech shares FEE9 service UUID with Richmat WiLinke
    if any(pattern in device_name for pattern in BEDTECH_NAME_PATTERNS):
        if BEDTECH_SERVICE_UUID.lower() in service_uuids:
            signals.append(f"uuid:{BEDTECH_SERVICE_UUID.lower()}")
            signals.append("name:bedtech")
            _LOGGER.info(
                "Detected BedTech bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_BEDTECH, confidence=0.9, signals=signals)

    # Check for Leggett & Platt MlRM variant (MlRM prefix with WiLinke UUID)
    # Must be before generic Richmat WiLinke check
    # Variant detection (mlrm) happens at controller instantiation
    if any(device_name.startswith(pattern) for pattern in LEGGETT_RICHMAT_NAME_PATTERNS):
        for wilinke_uuid in RICHMAT_WILINKE_SERVICE_UUIDS:
            if wilinke_uuid.lower() in service_uuids:
                signals.append("uuid:wilinke")
                signals.append("name:mlrm")
                _LOGGER.info(
                    "Detected Leggett & Platt MlRM bed at %s (name: %s)",
                    service_info.address,
                    service_info.name,
                )
                return DetectionResult(
                    bed_type=BED_TYPE_LEGGETT_WILINKE, confidence=0.9, signals=signals
                )

    # Check for Richmat WiLinke variants (includes FEE9 which is also used by BedTech)
    for wilinke_uuid in RICHMAT_WILINKE_SERVICE_UUIDS:
        if wilinke_uuid.lower() in service_uuids:
            signals.append("uuid:wilinke")
            # FEE9 is ambiguous - could be Richmat or BedTech
            if wilinke_uuid.lower() == BEDTECH_SERVICE_UUID.lower():
                _LOGGER.info(
                    "Detected Richmat WiLinke bed at %s (name: %s) - FEE9 UUID (also used by BedTech)",
                    service_info.address,
                    service_info.name,
                )
                return DetectionResult(
                    bed_type=BED_TYPE_RICHMAT,
                    confidence=0.5,
                    signals=signals,
                    ambiguous_types=[BED_TYPE_BEDTECH],
                    requires_characteristic_check=True,
                )
            _LOGGER.info(
                "Detected Richmat WiLinke bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_RICHMAT, confidence=0.8, signals=signals)

    # Check for MotoSleep - name-based detection (HHC prefix)
    if device_name.startswith("hhc"):
        signals.append("name:motosleep")
        _LOGGER.info(
            "Detected MotoSleep bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_MOTOSLEEP, confidence=0.9, signals=signals)

    # Check for Ergomotion - name-based detection (before Keeson since same UUID)
    # Includes "serta-i" prefix for Serta-branded ErgoMotion beds (e.g., Serta-i490350)
    if any(pattern in device_name for pattern in ERGOMOTION_NAME_PATTERNS):
        signals.append("name:ergomotion")
        _LOGGER.info(
            "Detected Ergomotion bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_ERGOMOTION, confidence=0.9, signals=signals)

    # Check for Sleepy's Elite BOX15 - name pattern + FFE5 service (before Keeson)
    # Sleepy's BOX15 uses FFE5 service UUID with 9-byte checksum protocol
    if (
        any(pattern in device_name for pattern in SLEEPYS_NAME_PATTERNS)
        and KEESON_BASE_SERVICE_UUID.lower() in service_uuids
    ):
        signals.append("uuid:ffe5")
        signals.append("name:sleepys")
        _LOGGER.info(
            "Detected Sleepy's Elite BOX15 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SLEEPYS_BOX15, confidence=0.9, signals=signals
        )

    # Check for Malouf LEGACY_OKIN - name pattern + FFE5 service (before Keeson)
    # Malouf LEGACY_OKIN uses FFE5 service UUID but different 9-byte command format
    if (
        any(pattern in device_name for pattern in MALOUF_NAME_PATTERNS)
        and MALOUF_LEGACY_OKIN_SERVICE_UUID.lower() in service_uuids
    ):
        signals.append("uuid:ffe5")
        signals.append("name:malouf")
        _LOGGER.info(
            "Detected Malouf LEGACY_OKIN bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_MALOUF_LEGACY_OKIN, confidence=0.9, signals=signals
        )

    # Check for Keeson by name patterns (e.g., base-i4.XXXX, base-i5.XXXX, KSBTXXXX)
    # This catches devices that may not advertise the specific service UUID
    if any(device_name.startswith(pattern) for pattern in KEESON_NAME_PATTERNS):
        signals.append("name:keeson")
        _LOGGER.info(
            "Detected Keeson bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_KEESON, confidence=0.9, signals=signals)

    # Check for Richmat by name pattern (e.g., QRRM157052)
    # Also extract remote code for feature detection
    if any(device_name.startswith(pattern) for pattern in RICHMAT_NAME_PATTERNS):
        signals.append("name:richmat")
        detected_remote = detect_richmat_remote_from_name(service_info.name)
        _LOGGER.info(
            "Detected Richmat bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_RICHMAT,
            confidence=0.9,
            signals=signals,
            detected_remote=detected_remote,
        )

    # Check for Comfort Motion / Lierda - service UUID detection
    # Uses FF12 service UUID (more specific than generic Jiecang detection)
    if COMFORT_MOTION_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:comfort_motion")
        _LOGGER.info(
            "Detected Comfort Motion bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_COMFORT_MOTION, confidence=1.0, signals=signals)

    # Check for Jiecang - name-based detection (Glide beds, Dream Motion app)
    if any(
        x in device_name for x in ["jiecang", "jc-", "dream motion", "glide", "comfort motion", "lierda"]
    ):
        signals.append("name:jiecang")
        _LOGGER.info(
            "Detected Jiecang bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_JIECANG, confidence=0.9, signals=signals)

    # Check for DewertOkin - name-based detection (A H Beard, HankookGallery)
    # Note: Also detected by manufacturer data and service UUID above (higher priority)
    if any(x in device_name for x in DEWERTOKIN_NAME_PATTERNS):
        signals.append("name:dewertokin")
        _LOGGER.info(
            "Detected DewertOkin bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_DEWERTOKIN, confidence=0.3, signals=signals)

    # Check for Serta Motion Perfect - name-based detection (uses Keeson protocol)
    if any(x in device_name for x in ["serta", "motion perfect"]):
        signals.append("name:serta")
        _LOGGER.info(
            "Detected Serta bed at %s (name: %s) - uses Keeson protocol with serta variant",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_SERTA, confidence=0.9, signals=signals)

    # Check for Octo by name pattern (e.g., DA1458x BLE chip used in some receivers)
    if any(device_name.startswith(pattern) for pattern in OCTO_NAME_PATTERNS):
        signals.append("name:octo")
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_OCTO, confidence=0.9, signals=signals)

    # Check for Octo Star2 variant - service UUID detection
    if OCTO_STAR2_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:octo_star2")
        _LOGGER.info(
            "Detected Octo Star2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_OCTO, confidence=1.0, signals=signals)

    # Check for beds using FFE5 service UUID (Keeson, OKIN FFE, Malouf LEGACY, Serta)
    # Priority: Serta/Keeson name patterns > OKIN FFE > Keeson (default)
    if KEESON_BASE_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:ffe5")
        # Check for Serta name patterns (uses Keeson protocol with serta variant)
        if any(pattern in device_name for pattern in SERTA_NAME_PATTERNS):
            signals.append("name:serta")
            _LOGGER.info(
                "Detected Serta bed at %s (name: %s) - uses Keeson protocol with serta variant",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_SERTA, confidence=0.9, signals=signals)
        # Check for OKIN FFE name patterns (0xE6 prefix variant)
        if any(pattern in device_name for pattern in OKIN_FFE_NAME_PATTERNS):
            signals.append("name:okin_ffe")
            _LOGGER.info(
                "Detected OKIN FFE bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_OKIN_FFE, confidence=0.9, signals=signals)
        # Default to Keeson Base for other FFE5 devices
        # This UUID is shared by Keeson, Malouf LEGACY, OKIN FFE, Serta
        _LOGGER.info(
            "Detected Keeson Base bed at %s (name: %s) - FFE5 UUID is ambiguous",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_KEESON,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[BED_TYPE_MALOUF_LEGACY_OKIN, BED_TYPE_OKIN_FFE, BED_TYPE_SERTA],
        )

    # Check for Solace/Octo/MotoSleep (same UUID, different protocols)
    # Octo is more common, so default to Octo unless name indicates Solace
    if SOLACE_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:ffe0")
        # Check for Solace name patterns from Motion Bed app reverse engineering:
        # - QMS-*, QMS2, QMS3, QMS4 (QMS series)
        # - S3-*, S4-*, S5-*, S6-* (S-series)
        # - SealyMF (Sealy Motion Flex)
        # - Contains "solace"
        # - Matches legacy Solace naming convention like "S4-Y-192-461000AD"
        if any(device_name.startswith(p) for p in SOLACE_NAME_PATTERNS):
            signals.append("name:solace")
            _LOGGER.info(
                "Detected Solace bed at %s (name: %s) by name pattern",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_SOLACE, confidence=0.9, signals=signals)
        if "solace" in device_name or SOLACE_NAME_PATTERN.match(device_name):
            signals.append("name:solace")
            _LOGGER.info(
                "Detected Solace bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_SOLACE, confidence=0.9, signals=signals)
        # Default to Octo (more common)
        # This UUID is shared by Octo, Solace, and MotoSleep
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s) - defaulting to Octo for shared FFE0 UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OCTO,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[BED_TYPE_SOLACE, BED_TYPE_MOTOSLEEP],
        )

    # Check for Mattress Firm 900 (iFlex) - name-based detection
    # Must check before Richmat Nordic since they share the same UUID
    if "iflex" in device_name:
        signals.append("name:iflex")
        _LOGGER.info(
            "Detected Mattress Firm 900 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_MATTRESSFIRM, confidence=0.9, signals=signals)

    # Check for Richmat Nordic / Keeson KSBT / OKIN 64-bit (same UUID)
    # These share the Nordic UART service UUID
    if RICHMAT_NORDIC_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:nordic_uart")
        # This UUID is shared by Richmat, Keeson KSBT, Mattress Firm, and OKIN 64-bit
        _LOGGER.info(
            "Detected Richmat/Keeson bed at %s (name: %s) - Nordic UART UUID is ambiguous",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_RICHMAT,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[BED_TYPE_KEESON, BED_TYPE_MATTRESSFIRM, BED_TYPE_OKIN_64BIT],
            requires_characteristic_check=True,
        )

    _LOGGER.debug("Device %s does not match any known bed types", service_info.address)
    return DetectionResult(bed_type=None, confidence=0.0, signals=signals)


async def detect_bed_type_by_characteristics(
    client: BleakClient,
    initial_detection: str,
) -> str | None:
    """Refine bed type detection by examining characteristics after connection.

    This function should be called when initial detection was ambiguous
    (e.g., FEE9 could be Richmat or BedTech, 62741523 could be Okimat or OKIN 64-bit).

    Args:
        client: Connected BleakClient instance with services already discovered
        initial_detection: The bed type from initial detection (e.g., BED_TYPE_RICHMAT)

    Returns:
        Refined bed type if characteristics indicate a different type,
        or None if the initial detection should be kept.
    """
    try:
        # Build a set of all characteristic UUIDs for easy lookup
        all_chars: set[str] = set()
        for service in client.services:
            for char in service.characteristics:
                all_chars.add(char.uuid.lower())

        # For FEE9 service (Richmat WiLinke): Check if BedTech characteristic exists
        if initial_detection == BED_TYPE_RICHMAT:
            # BedTech has a specific write characteristic
            if BEDTECH_WRITE_CHAR_UUID.lower() in all_chars:
                _LOGGER.info(
                    "Refined detection: BedTech characteristic found (was Richmat)"
                )
                return BED_TYPE_BEDTECH

        # For OKIN service (62741523): Check for 64-bit read characteristic
        if initial_detection == BED_TYPE_OKIMAT:
            # OKIN 64-bit has the response/notify characteristic (62741625)
            if OKIMAT_NOTIFY_CHAR_UUID.lower() in all_chars:
                # The presence of 62741625 doesn't definitively mean 64-bit
                # (Okimat also has this), but we can note it for logging
                _LOGGER.debug(
                    "OKIN notify characteristic found - could be Okimat or OKIN 64-bit"
                )
                # To truly distinguish, we'd need to try sending a command
                # and check the response format (6-byte vs 10-byte)
                # For now, keep as Okimat since it's more common

        # For Nordic UART service: Check for specific protocol indicators
        if initial_detection == BED_TYPE_RICHMAT:
            # Nordic UART is used by Richmat, Keeson KSBT, Mattress Firm, OKIN 64-bit
            # Without actually sending commands, we can't reliably distinguish
            pass

    except BleakError as err:
        _LOGGER.debug("Characteristic detection failed (BLE error): %s", err)
    except AttributeError as err:
        _LOGGER.debug("Characteristic detection failed (malformed service): %s", err)

    return None


def determine_unsupported_reason(service_info: BluetoothServiceInfoBleak) -> str:
    """Determine why a device was not detected as a supported bed."""
    device_name = (service_info.name or "").lower()

    # Check if it was excluded
    for pattern in EXCLUDED_DEVICE_PATTERNS:
        if pattern in device_name:
            return f"Device name contains excluded pattern '{pattern}' (non-bed device)"

    # Check if it has any service UUIDs at all
    if not service_info.service_uuids:
        return "No BLE service UUIDs advertised"

    # Check if it has manufacturer data but unknown protocol
    if service_info.manufacturer_data:
        return "Has manufacturer data but no recognized service UUIDs"

    # Generic reason
    return "No matching service UUIDs or name patterns found"
