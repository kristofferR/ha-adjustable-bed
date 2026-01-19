"""Bed type detection logic for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import SelectOptionDict

from .const import (
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_REVERIE,
    BED_TYPE_RICHMAT,
    BED_TYPE_SERTA,
    BED_TYPE_SOLACE,
    ERGOMOTION_NAME_PATTERNS,
    KEESON_BASE_SERVICE_UUID,
    KEESON_NAME_PATTERNS,
    LEGGETT_GEN2_SERVICE_UUID,
    LEGGETT_OKIN_NAME_PATTERNS,
    LEGGETT_RICHMAT_NAME_PATTERNS,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_NAME_PATTERNS,
    LINAK_POSITION_SERVICE_UUID,
    OCTO_NAME_PATTERNS,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_NAME_PATTERNS,
    OKIMAT_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NAME_PATTERNS,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SOLACE_SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


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

# Display names for bed types (sorted alphabetically by display name)
BED_TYPE_DISPLAY_NAMES: dict[str, str] = {
    BED_TYPE_DEWERTOKIN: "DewertOkin",
    BED_TYPE_DIAGNOSTIC: "Diagnostic (unknown bed)",
    BED_TYPE_ERGOMOTION: "Ergomotion",
    BED_TYPE_JIECANG: "Jiecang",
    BED_TYPE_KEESON: "Keeson",
    BED_TYPE_LEGGETT_PLATT: "Leggett & Platt",
    BED_TYPE_LINAK: "Linak",
    BED_TYPE_MATTRESSFIRM: "MattressFirm",
    BED_TYPE_MOTOSLEEP: "MotoSleep",
    BED_TYPE_NECTAR: "Nectar",
    BED_TYPE_OCTO: "Octo",
    BED_TYPE_OKIMAT: "Okimat",
    BED_TYPE_REVERIE: "Reverie",
    BED_TYPE_RICHMAT: "Richmat",
    BED_TYPE_SERTA: "Serta",
    BED_TYPE_SOLACE: "Solace",
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

    # Check for Linak - most specific first
    # Some Linak beds may advertise position service but not control service
    if LINAK_CONTROL_SERVICE_UUID.lower() in service_uuids or LINAK_POSITION_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Linak bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_LINAK

    # Check for Linak by name pattern (e.g., "Bed 1696")
    # Some Linak beds don't advertise service UUIDs in their BLE beacon
    for pattern in LINAK_NAME_PATTERNS:
        if device_name.startswith(pattern) and device_name[len(pattern):].isdigit():
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

    # Check for Reverie
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
            return BED_TYPE_LEGGETT_PLATT

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

    # Check for Jiecang - name-based detection (Glide beds, Dream Motion app)
    if any(x in device_name for x in ["jiecang", "jc-", "dream motion", "glide"]):
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

    # Check for Serta Motion Perfect - name-based detection
    if any(x in device_name for x in ["serta", "motion perfect"]):
        _LOGGER.info(
            "Detected Serta bed at %s (name: %s)",
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

    # Check for Keeson BaseI4/I5 (must check before generic UUIDs)
    if KEESON_BASE_SERVICE_UUID.lower() in service_uuids:
        _LOGGER.info(
            "Detected Keeson Base bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return BED_TYPE_KEESON

    # Check for Solace/Octo (same UUID, different protocols)
    # Octo is more common, so default to Octo unless name indicates Solace
    if SOLACE_SERVICE_UUID.lower() in service_uuids:
        # Check for explicit Solace name patterns:
        # - Contains "solace"
        # - Matches Solace naming convention like "S4-Y-192-461000AD"
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
