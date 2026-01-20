"""Brand registry for adjustable bed controllers.

This module provides a centralized registry that maps user-facing brand names
to their underlying protocol implementations. This allows for:

1. Cleaner code organization by grouping beds by protocol rather than brand
2. Backwards compatibility with existing configurations
3. Easy addition of new brands that use existing protocols
4. Clear documentation of protocol relationships

Protocol file naming convention:
- okin_handle.py: Okin 6-byte protocol via BLE handle writes
- okin_uuid.py: Okin 6-byte protocol via UUID (requires pairing)
- okin_7byte.py: 7-byte protocol via Okin service UUID
- okin_nordic.py: 7-byte protocol via Nordic UART
- leggett_gen2.py: Leggett & Platt Gen2 ASCII commands
- leggett_okin.py: Leggett & Platt Okin protocol variant
- leggett_wilinke.py: Leggett & Platt WiLinke 5-byte protocol
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# Import bed type constants for mapping
from .const import (
    BED_TYPE_DEWERTOKIN,
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
    LEGGETT_VARIANT_GEN2,
    LEGGETT_VARIANT_MLRM,
    LEGGETT_VARIANT_OKIN,
    VARIANT_AUTO,
)


@dataclass(frozen=True)
class BrandInfo:
    """Information about a bed brand and its protocol.

    Attributes:
        protocol_file: The Python module name (without .py) containing the controller.
        controller_class: The class name of the controller in the protocol file.
        display_name: Human-readable brand name for UI display.
        manufacturer: The actual manufacturer (may differ from brand name).
        protocol_description: Brief description of the protocol used.
        service_uuids: List of BLE service UUIDs used for detection.
        name_patterns: List of device name patterns for detection.
        requires_pairing: Whether BLE pairing is required before use.
        has_variants: Whether this bed type has protocol variants.
        variant_mapping: Dict mapping variant names to (protocol_file, controller_class).
    """

    protocol_file: str
    controller_class: str
    display_name: str
    manufacturer: str = ""
    protocol_description: str = ""
    service_uuids: tuple[str, ...] = field(default_factory=tuple)
    name_patterns: tuple[str, ...] = field(default_factory=tuple)
    requires_pairing: bool = False
    has_variants: bool = False
    variant_mapping: dict[str, tuple[str, str]] = field(default_factory=dict)


# Protocol file constants
PROTOCOL_OKIN_HANDLE: Final = "okin_handle"
PROTOCOL_OKIN_UUID: Final = "okin_uuid"
PROTOCOL_OKIN_7BYTE: Final = "okin_7byte"
PROTOCOL_OKIN_NORDIC: Final = "okin_nordic"
PROTOCOL_LEGGETT_GEN2: Final = "leggett_gen2"
PROTOCOL_LEGGETT_OKIN: Final = "leggett_okin"
PROTOCOL_LEGGETT_WILINKE: Final = "leggett_wilinke"

# Unchanged protocol files (brand name matches protocol)
PROTOCOL_LINAK: Final = "linak"
PROTOCOL_RICHMAT: Final = "richmat"
PROTOCOL_KEESON: Final = "keeson"
PROTOCOL_SERTA: Final = "serta"
PROTOCOL_REVERIE: Final = "reverie"
PROTOCOL_JIECANG: Final = "jiecang"
PROTOCOL_SOLACE: Final = "solace"
PROTOCOL_MOTOSLEEP: Final = "motosleep"
PROTOCOL_OCTO: Final = "octo"


# Brand registry - maps bed_type constants to BrandInfo
BRANDS: dict[str, BrandInfo] = {
    # DewertOkin -> okin_handle protocol
    BED_TYPE_DEWERTOKIN: BrandInfo(
        protocol_file=PROTOCOL_OKIN_HANDLE,
        controller_class="OkinHandleController",
        display_name="DewertOkin",
        manufacturer="DewertOkin GmbH",
        protocol_description="Okin 6-byte protocol via BLE handle 0x0013",
        name_patterns=("dewertokin", "dewert", "a h beard", "hankook"),
        requires_pairing=False,
    ),
    # Okimat -> okin_uuid protocol (requires pairing)
    BED_TYPE_OKIMAT: BrandInfo(
        protocol_file=PROTOCOL_OKIN_UUID,
        controller_class="OkinUuidController",
        display_name="Okimat",
        manufacturer="Okin / Jiecang",
        protocol_description="Okin 6-byte protocol via UUID (requires pairing)",
        service_uuids=("62741523-52f9-8864-b1ab-3b3a8d65950b",),
        name_patterns=("okimat", "okin rf", "okin ble", "okin-"),
        requires_pairing=True,
    ),
    # Nectar -> okin_7byte protocol
    BED_TYPE_NECTAR: BrandInfo(
        protocol_file=PROTOCOL_OKIN_7BYTE,
        controller_class="Okin7ByteController",
        display_name="Nectar",
        manufacturer="Nectar Sleep",
        protocol_description="7-byte protocol via Okin service UUID",
        service_uuids=("62741523-52f9-8864-b1ab-3b3a8d65950b",),
        name_patterns=("nectar",),
        requires_pairing=False,
    ),
    # MattressFirm -> okin_nordic protocol
    BED_TYPE_MATTRESSFIRM: BrandInfo(
        protocol_file=PROTOCOL_OKIN_NORDIC,
        controller_class="OkinNordicController",
        display_name="MattressFirm 900",
        manufacturer="Mattress Firm / iFlex",
        protocol_description="7-byte protocol via Nordic UART",
        service_uuids=("6e400001-b5a3-f393-e0a9-e50e24dcca9e",),
        name_patterns=("iflex",),
        requires_pairing=False,
    ),
    # Leggett & Platt -> multiple protocols based on variant
    BED_TYPE_LEGGETT_PLATT: BrandInfo(
        protocol_file=PROTOCOL_LEGGETT_GEN2,  # Default for auto
        controller_class="LeggettGen2Controller",
        display_name="Leggett & Platt",
        manufacturer="Leggett & Platt",
        protocol_description="Multiple protocols (Gen2, Okin, WiLinke)",
        service_uuids=(
            "45e25100-3171-4cfc-ae89-1d83cf8d8071",  # Gen2
            "62741523-52f9-8864-b1ab-3b3a8d65950b",  # Okin variant
        ),
        name_patterns=("leggett", "l&p", "mlrm"),
        requires_pairing=False,  # Only Okin variant requires pairing
        has_variants=True,
        variant_mapping={
            VARIANT_AUTO: (PROTOCOL_LEGGETT_GEN2, "LeggettGen2Controller"),
            LEGGETT_VARIANT_GEN2: (PROTOCOL_LEGGETT_GEN2, "LeggettGen2Controller"),
            LEGGETT_VARIANT_OKIN: (PROTOCOL_LEGGETT_OKIN, "LeggettOkinController"),
            LEGGETT_VARIANT_MLRM: (PROTOCOL_LEGGETT_WILINKE, "LeggettWilinkeController"),
        },
    ),
    # Unchanged bed types - protocol file matches brand
    BED_TYPE_LINAK: BrandInfo(
        protocol_file=PROTOCOL_LINAK,
        controller_class="LinakController",
        display_name="Linak",
        manufacturer="Linak",
        protocol_description="Linak proprietary protocol",
        service_uuids=(
            "99fa0001-338a-1024-8a49-009c0215f78a",
            "99fa0020-338a-1024-8a49-009c0215f78a",
        ),
        name_patterns=("bed ",),
        requires_pairing=False,
    ),
    BED_TYPE_RICHMAT: BrandInfo(
        protocol_file=PROTOCOL_RICHMAT,
        controller_class="RichmatController",
        display_name="Richmat",
        manufacturer="Richmat",
        protocol_description="Richmat protocol (Nordic or WiLinke variants)",
        service_uuids=(
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7",
            "0000fee9-0000-1000-8000-00805f9b34fb",
        ),
        name_patterns=("qrrm", "sleep function"),
        requires_pairing=False,
        has_variants=True,
    ),
    BED_TYPE_KEESON: BrandInfo(
        protocol_file=PROTOCOL_KEESON,
        controller_class="KeesonController",
        display_name="Keeson",
        manufacturer="Keeson Technology",
        protocol_description="Keeson Base/KSBT protocol",
        service_uuids=(
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "0000ffe5-0000-1000-8000-00805f9b34fb",
        ),
        name_patterns=("base-i4.", "base-i5.", "ksbt"),
        requires_pairing=False,
        has_variants=True,
    ),
    BED_TYPE_ERGOMOTION: BrandInfo(
        protocol_file=PROTOCOL_KEESON,  # Uses Keeson with ergomotion variant
        controller_class="KeesonController",
        display_name="Ergomotion",
        manufacturer="Ergomotion",
        protocol_description="Keeson protocol with position feedback",
        service_uuids=("0000ffe5-0000-1000-8000-00805f9b34fb",),
        name_patterns=("ergomotion", "ergo", "serta-i"),
        requires_pairing=False,
    ),
    BED_TYPE_SERTA: BrandInfo(
        protocol_file=PROTOCOL_SERTA,
        controller_class="SertaController",
        display_name="Serta Motion Perfect",
        manufacturer="Serta",
        protocol_description="Serta handle-based protocol",
        name_patterns=("serta", "motion perfect"),
        requires_pairing=False,
    ),
    BED_TYPE_REVERIE: BrandInfo(
        protocol_file=PROTOCOL_REVERIE,
        controller_class="ReverieController",
        display_name="Reverie",
        manufacturer="Reverie",
        protocol_description="Reverie proprietary protocol",
        service_uuids=("1b1d9641-b942-4da8-89cc-98e6a58fbd93",),
        requires_pairing=False,
    ),
    BED_TYPE_JIECANG: BrandInfo(
        protocol_file=PROTOCOL_JIECANG,
        controller_class="JiecangController",
        display_name="Jiecang",
        manufacturer="Jiecang Linear Motion",
        protocol_description="Jiecang/Glide protocol",
        name_patterns=("jiecang", "jc-", "dream motion", "glide"),
        requires_pairing=False,
    ),
    BED_TYPE_SOLACE: BrandInfo(
        protocol_file=PROTOCOL_SOLACE,
        controller_class="SolaceController",
        display_name="Solace",
        manufacturer="Solace Sleep",
        protocol_description="Solace protocol",
        service_uuids=("0000ffe0-0000-1000-8000-00805f9b34fb",),
        name_patterns=("solace",),
        requires_pairing=False,
    ),
    BED_TYPE_MOTOSLEEP: BrandInfo(
        protocol_file=PROTOCOL_MOTOSLEEP,
        controller_class="MotoSleepController",
        display_name="MotoSleep",
        manufacturer="MotoSleep",
        protocol_description="MotoSleep protocol",
        service_uuids=("0000ffe0-0000-1000-8000-00805f9b34fb",),
        name_patterns=("hhc",),
        requires_pairing=False,
    ),
    BED_TYPE_OCTO: BrandInfo(
        protocol_file=PROTOCOL_OCTO,
        controller_class="OctoController",
        display_name="Octo",
        manufacturer="Octo",
        protocol_description="Octo protocol (with optional PIN)",
        service_uuids=(
            "0000ffe0-0000-1000-8000-00805f9b34fb",
            "0000aa5c-0000-1000-8000-00805f9b34fb",
        ),
        name_patterns=("da1458x",),
        requires_pairing=False,
        has_variants=True,
    ),
}


# Legacy aliases for backwards compatibility
# Maps old bed_type values to the current bed_type constant
LEGACY_ALIASES: dict[str, str] = {
    # These map old/alternative names to the canonical bed_type
    # No changes needed for now since we're keeping the same bed_type constants
    # This dict is here for future use if we ever rename bed_type values
}


# Module name mapping for the new protocol files
# Maps old module names to new protocol-based names
MODULE_ALIASES: dict[str, str] = {
    "dewertokin": PROTOCOL_OKIN_HANDLE,
    "okimat": PROTOCOL_OKIN_UUID,
    "nectar": PROTOCOL_OKIN_7BYTE,
    "mattressfirm": PROTOCOL_OKIN_NORDIC,
    "leggett_platt": PROTOCOL_LEGGETT_GEN2,
    "leggett_platt_mlrm": PROTOCOL_LEGGETT_WILINKE,
}


def resolve_protocol_file(bed_type: str, variant: str | None = None) -> str:
    """Resolve the protocol file name for a given bed type and variant.

    Args:
        bed_type: The bed type constant (e.g., BED_TYPE_DEWERTOKIN)
        variant: Optional protocol variant for beds with multiple protocols

    Returns:
        The protocol file name (without .py extension)

    Raises:
        ValueError: If bed_type is unknown
    """
    # Check legacy aliases first
    canonical_type = LEGACY_ALIASES.get(bed_type, bed_type)

    if canonical_type not in BRANDS:
        raise ValueError(f"Unknown bed type: {bed_type}")

    brand_info = BRANDS[canonical_type]

    # Handle variants for beds with multiple protocols
    if variant and brand_info.has_variants and brand_info.variant_mapping:
        if variant in brand_info.variant_mapping:
            return brand_info.variant_mapping[variant][0]
        # Fall back to default for unknown variants
        if VARIANT_AUTO in brand_info.variant_mapping:
            return brand_info.variant_mapping[VARIANT_AUTO][0]

    return brand_info.protocol_file


def resolve_controller_class(bed_type: str, variant: str | None = None) -> str:
    """Resolve the controller class name for a given bed type and variant.

    Args:
        bed_type: The bed type constant (e.g., BED_TYPE_DEWERTOKIN)
        variant: Optional protocol variant for beds with multiple protocols

    Returns:
        The controller class name

    Raises:
        ValueError: If bed_type is unknown
    """
    # Check legacy aliases first
    canonical_type = LEGACY_ALIASES.get(bed_type, bed_type)

    if canonical_type not in BRANDS:
        raise ValueError(f"Unknown bed type: {bed_type}")

    brand_info = BRANDS[canonical_type]

    # Handle variants for beds with multiple protocols
    if variant and brand_info.has_variants and brand_info.variant_mapping:
        if variant in brand_info.variant_mapping:
            return brand_info.variant_mapping[variant][1]
        # Fall back to default for unknown variants
        if VARIANT_AUTO in brand_info.variant_mapping:
            return brand_info.variant_mapping[VARIANT_AUTO][1]

    return brand_info.controller_class


def get_brand_info(bed_type: str) -> BrandInfo | None:
    """Get brand information for a bed type.

    Args:
        bed_type: The bed type constant

    Returns:
        BrandInfo object or None if unknown
    """
    canonical_type = LEGACY_ALIASES.get(bed_type, bed_type)
    return BRANDS.get(canonical_type)


def get_display_name(bed_type: str) -> str:
    """Get the display name for a bed type.

    Args:
        bed_type: The bed type constant

    Returns:
        Human-readable display name, or the bed_type if unknown
    """
    brand_info = get_brand_info(bed_type)
    return brand_info.display_name if brand_info else bed_type


def requires_pairing(bed_type: str) -> bool:
    """Check if a bed type requires BLE pairing.

    Args:
        bed_type: The bed type constant

    Returns:
        True if pairing is required, False otherwise
    """
    brand_info = get_brand_info(bed_type)
    return brand_info.requires_pairing if brand_info else False
