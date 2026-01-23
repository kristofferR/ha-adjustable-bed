"""Bed type detection logic for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import SelectOptionDict

from .const import (
    # Legacy/brand-specific bed types
    # NOTE: BED_TYPE_BEDTECH and BED_TYPE_OKIN_64BIT are imported for BED_TYPE_DISPLAY_NAMES
    # but are NOT auto-detected in detect_bed_type() because:
    # - BedTech shares the FEE9 service UUID with Richmat WiLinke
    # - OKIN 64-bit uses UUIDs common to other OKIN protocols (Nordic UART or 62741523)
    # Both require manual selection as they can't be reliably distinguished at the UUID level.
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_FFE,
    # Protocol-based bed types (new)
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    # Detection constants
    COMFORT_MOTION_SERVICE_UUID,
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
    OCTO_NAME_PATTERNS,
    OCTO_STAR2_SERVICE_UUID,
    OKIN_FFE_NAME_PATTERNS,
    OKIMAT_NAME_PATTERNS,
    OKIMAT_SERVICE_UUID,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NAME_PATTERNS,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SERTA_NAME_PATTERNS,
    SOLACE_NAME_PATTERNS,
    SOLACE_SERVICE_UUID,
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
    BED_TYPE_SOLACE: "Solace",
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
    """Detect bed type from service info."""
    # Handle devices that report None for service_uuids
    raw_uuids = service_info.service_uuids
    service_uuids = [str(uuid).lower() for uuid in raw_uuids] if raw_uuids else []
    device_name = (service_info.name or "").lower()

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
            return None

    # Check for Malouf NEW_OKIN - unique advertised service UUID (most specific first)
    if MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Malouf NEW_OKIN bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_MALOUF_NEW_OKIN

    # Check for Linak - most specific first
    # Some Linak beds may advertise position service but not control service
    if (
        LINAK_CONTROL_SERVICE_UUID.lower() in service_uuids
        or LINAK_POSITION_SERVICE_UUID.lower() in service_uuids
    ):
        _LOGGER.info(
            "Detected Linak bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_LINAK

    # Check for Linak by name pattern (e.g., "Bed 1696")
    # Some Linak beds don't advertise service UUIDs in their BLE beacon
    for pattern in LINAK_NAME_PATTERNS:
        if device_name.startswith(pattern) and device_name[len(pattern) :].isdigit():
            _LOGGER.info(
                "Detected Linak bed at %s (name: %s) by name pattern",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_LINAK

    # Check for Leggett & Platt Gen2 (must check before generic UUIDs)
    if LEGGETT_GEN2_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Leggett & Platt Gen2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_LEGGETT_PLATT

    # Check for Reverie Nightstand (Protocol 110) - more specific UUID
    if REVERIE_NIGHTSTAND_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Reverie Nightstand bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_REVERIE_NIGHTSTAND

    # Check for Reverie (Protocol 108)
    if REVERIE_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Reverie bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_REVERIE

    # Check for Nectar - name-based detection (before Okimat since same UUID)
    # Nectar beds use OKIN service UUID but different command protocol
    if "nectar" in device_name and OKIMAT_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Nectar bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_NECTAR

    # Check for beds using OKIN service UUID (Okimat, Leggett Okin, Nectar)
    # Nectar is already handled above by name check
    # Use name patterns to disambiguate between Okimat and Leggett Okin
    if OKIMAT_SERVICE_UUID.lower() in service_uuids:
        # Check for Leggett & Platt Okin by name patterns
        if any(pattern in device_name for pattern in LEGGETT_OKIN_NAME_PATTERNS):
            _LOGGER.info(
                "Detected Leggett & Platt Okin bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_LEGGETT_OKIN

        # Check for Okimat-specific name patterns
        if any(pattern in device_name for pattern in OKIMAT_NAME_PATTERNS):
            _LOGGER.info(
                "Detected Okimat bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_OKIMAT

        # Fallback: default to Okimat with warning about ambiguity
        _LOGGER.warning(
            "Okin UUID detected but device name '%s' at %s doesn't match known patterns. "
            "Defaulting to Okimat. Change to Leggett & Platt in settings if needed.",
            service_info.name,
            service_info.address,
        )
        return BED_TYPE_OKIMAT

    # Check for Leggett & Platt MlRM variant (MlRM prefix with WiLinke UUID)
    # Must be before generic Richmat WiLinke check
    # Variant detection (mlrm) happens at controller instantiation
    if any(device_name.startswith(pattern) for pattern in LEGGETT_RICHMAT_NAME_PATTERNS):
        for wilinke_uuid in RICHMAT_WILINKE_SERVICE_UUIDS:
            if wilinke_uuid.lower() in service_uuids:
                _LOGGER.info(
                    "Detected Leggett & Platt MlRM bed at %s (name: %s)",
                    service_info.address,
                    service_info.name,
                )
                return BED_TYPE_LEGGETT_PLATT

    # Check for Richmat WiLinke variants
    for wilinke_uuid in RICHMAT_WILINKE_SERVICE_UUIDS:
        if wilinke_uuid.lower() in service_uuids:
            _LOGGER.info(
                "Detected Richmat WiLinke bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_RICHMAT

    # Check for MotoSleep - name-based detection (HHC prefix)
    if device_name.startswith("hhc"):
        _LOGGER.info(
            "Detected MotoSleep bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_MOTOSLEEP

    # Check for Ergomotion - name-based detection (before Keeson since same UUID)
    # Includes "serta-i" prefix for Serta-branded ErgoMotion beds (e.g., Serta-i490350)
    if any(pattern in device_name for pattern in ERGOMOTION_NAME_PATTERNS):
        _LOGGER.info(
            "Detected Ergomotion bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_ERGOMOTION

    # Check for Malouf LEGACY_OKIN - name pattern + FFE5 service (before Keeson)
    # Malouf LEGACY_OKIN uses FFE5 service UUID but different 9-byte command format
    if (
        any(pattern in device_name for pattern in MALOUF_NAME_PATTERNS)
        and MALOUF_LEGACY_OKIN_SERVICE_UUID.lower() in service_uuids
    ):
        _LOGGER.info(
            "Detected Malouf LEGACY_OKIN bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_MALOUF_LEGACY_OKIN

    # Check for Keeson by name patterns (e.g., base-i4.XXXX, base-i5.XXXX, KSBTXXXX)
    # This catches devices that may not advertise the specific service UUID
    if any(device_name.startswith(pattern) for pattern in KEESON_NAME_PATTERNS):
        _LOGGER.info(
            "Detected Keeson bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_KEESON

    # Check for Richmat by name pattern (e.g., QRRM157052)
    if any(device_name.startswith(pattern) for pattern in RICHMAT_NAME_PATTERNS):
        _LOGGER.info(
            "Detected Richmat bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_RICHMAT

    # Check for Comfort Motion / Lierda - service UUID detection
    # Uses FF12 service UUID (more specific than generic Jiecang detection)
    if COMFORT_MOTION_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Comfort Motion bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_COMFORT_MOTION

    # Check for Jiecang - name-based detection (Glide beds, Dream Motion app)
    if any(x in device_name for x in ["jiecang", "jc-", "dream motion", "glide", "comfort motion", "lierda"]):
        _LOGGER.info(
            "Detected Jiecang bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_JIECANG

    # Check for DewertOkin - name-based detection (A H Beard, HankookGallery)
    if any(x in device_name for x in ["dewertokin", "dewert", "a h beard", "hankook"]):
        _LOGGER.info(
            "Detected DewertOkin bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_DEWERTOKIN

    # Check for Serta Motion Perfect - name-based detection (uses Keeson protocol)
    if any(x in device_name for x in ["serta", "motion perfect"]):
        _LOGGER.info(
            "Detected Serta bed at %s (name: %s) - uses Keeson protocol with serta variant",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_SERTA

    # Check for Octo by name pattern (e.g., DA1458x BLE chip used in some receivers)
    if any(device_name.startswith(pattern) for pattern in OCTO_NAME_PATTERNS):
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_OCTO

    # Check for Octo Star2 variant - service UUID detection
    if OCTO_STAR2_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Octo Star2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_OCTO

    # Check for beds using FFE5 service UUID (Keeson, OKIN FFE)
    # Priority: Serta/Keeson name patterns > OKIN FFE > Keeson (default)
    if KEESON_BASE_SERVICE_UUID.lower() in service_uuids:
        # Check for Serta name patterns (uses Keeson protocol with serta variant)
        if any(pattern in device_name for pattern in SERTA_NAME_PATTERNS):
            _LOGGER.info(
                "Detected Serta bed at %s (name: %s) - uses Keeson protocol with serta variant",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_SERTA
        # Check for OKIN FFE name patterns (0xE6 prefix variant)
        if any(pattern in device_name for pattern in OKIN_FFE_NAME_PATTERNS):
            _LOGGER.info(
                "Detected OKIN FFE bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_OKIN_FFE
        # Default to Keeson Base for other FFE5 devices
        _LOGGER.info(
            "Detected Keeson Base bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_KEESON

    # Check for Solace/Octo (same UUID, different protocols)
    # Octo is more common, so default to Octo unless name indicates Solace
    if SOLACE_SERVICE_UUID.lower() in service_uuids:
        # Check for Solace name patterns from Motion Bed app reverse engineering:
        # - QMS-*, QMS2, QMS3, QMS4 (QMS series)
        # - S3-*, S4-*, S5-*, S6-* (S-series)
        # - SealyMF (Sealy Motion Flex)
        # - Contains "solace"
        # - Matches legacy Solace naming convention like "S4-Y-192-461000AD"
        if any(device_name.startswith(p) for p in SOLACE_NAME_PATTERNS):
            _LOGGER.info(
                "Detected Solace bed at %s (name: %s) by name pattern",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_SOLACE
        if "solace" in device_name or SOLACE_NAME_PATTERN.match(device_name):
            _LOGGER.info(
                "Detected Solace bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return BED_TYPE_SOLACE
        # Default to Octo (more common)
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s) - defaulting to Octo for shared UUID",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_OCTO

    # Check for Mattress Firm 900 (iFlex) - name-based detection
    # Must check before Richmat Nordic since they share the same UUID
    if "iflex" in device_name:
        _LOGGER.info(
            "Detected Mattress Firm 900 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_MATTRESSFIRM

    # Check for Richmat Nordic / Keeson KSBT (same UUID)
    # These share the Nordic UART service UUID
    if RICHMAT_NORDIC_SERVICE_UUID.lower() in service_uuids:
        # Default to Richmat, user can change in config
        _LOGGER.info(
            "Detected Richmat/Keeson bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_RICHMAT

    _LOGGER.debug("Device %s does not match any known bed types", service_info.address)
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
