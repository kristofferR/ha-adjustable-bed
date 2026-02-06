"""Actuator group definitions for two-tier bed selection.

This module organizes bed types into user-friendly groups based on actuator brand,
making it easier for users to select the correct bed type during setup.
"""

from __future__ import annotations

from typing import Final, TypedDict

from .const import (
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LINAK,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SOLACE,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_SERTA,
)


class ActuatorVariant(TypedDict):
    """Type definition for an actuator variant."""

    type: str  # The bed_type constant
    label: str  # Short label for the variant
    description: str  # Bed brands that use this variant
    hint: str  # How to identify this variant (e.g., device name patterns)


class ActuatorVariantWithProtocol(ActuatorVariant, total=False):
    """Type definition for an actuator variant with optional protocol variant."""

    variant: str  # Optional protocol variant (e.g., 'base', 'ksbt')


class ActuatorGroup(TypedDict):
    """Type definition for an actuator group."""

    display: str  # Display name for the actuator brand
    description: str  # Bed brands that commonly use this actuator
    variants: list[ActuatorVariantWithProtocol] | None  # None = single protocol


# Groups are in alphabetical order by key
ACTUATOR_GROUPS: Final[dict[str, ActuatorGroup]] = {
    "bedtech": {
        "display": "BedTech",
        "description": "BedTech adjustable bases",
        "variants": None,  # Single protocol
    },
    "comfort_motion": {
        "display": "Comfort Motion",
        "description": "Comfort Motion, Lierda beds",
        "variants": None,  # Single protocol
    },
    "ergomotion": {
        "display": "Ergomotion",
        "description": "Ergomotion, Serta Motion (not Motion Perfect), some Tempur-Pedic",
        "variants": None,  # Single protocol
    },
    "jensen": {
        "display": "Jensen",
        "description": "Jensen JMC400, LinON Entry beds",
        "variants": None,  # Single protocol
    },
    "jiecang": {
        "display": "Jiecang",
        "description": "Glideaway, Dream Motion beds",
        "variants": None,  # Single protocol
    },
    "keeson": {
        "display": "Keeson",
        "description": "Purple, Member's Mark, GhostBed, Serta Motion Perfect, ErgoSportive",
        "variants": [
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_BASE,
                "label": "BaseI4 / BaseI5 (most common)",
                "description": "Purple Ascent, Member's Mark, GhostBed",
                "hint": "Device name starts with 'Base-I4' or 'Base-I5'",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_KSBT,
                "label": "KSBT (older remotes)",
                "description": "Older Keeson remotes with KSBT prefix",
                "hint": "Device name starts with 'KSBT'",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_SERTA,
                "label": "Serta Motion Perfect",
                "description": "Serta Motion Perfect III beds",
                "hint": "Device name contains 'Serta' or 'Motion Perfect'",
            },
        ],
    },
    "leggett": {
        "display": "Leggett & Platt",
        "description": "L&P branded bases, various furniture brands",
        "variants": [
            {
                "type": BED_TYPE_LEGGETT_GEN2,
                "label": "Gen2 (most common)",
                "description": "Most L&P bases - Richmat-based ASCII protocol",
                "hint": "Try this first if unsure",
            },
            {
                "type": BED_TYPE_LEGGETT_OKIN,
                "label": "Okin-based (requires pairing)",
                "description": "Older L&P bases using Okin protocol",
                "hint": "Device name contains 'Leggett' or 'L&P'",
            },
            {
                "type": BED_TYPE_LEGGETT_WILINKE,
                "label": "MlRM / WiLinke",
                "description": "Uses WiLinke 5-byte protocol",
                "hint": "Device name starts with 'MLRM'",
            },
        ],
    },
    "linak": {
        "display": "Linak",
        "description": "Tempur-Pedic, Carpe Diem, Wonderland, Svane, high-end European beds",
        "variants": None,  # Single protocol
    },
    "limoss": {
        "display": "Limoss / Stawett",
        "description": "Limoss and Stawett bases (TEA-encrypted protocol)",
        "variants": None,  # Single protocol
    },
    "malouf": {
        "display": "Malouf",
        "description": "Malouf adjustable bases",
        "variants": [
            {
                "type": BED_TYPE_MALOUF_NEW_OKIN,
                "label": "New (Nordic UART)",
                "description": "Newer Malouf bases",
                "hint": "Device name contains 'Malouf' - try this first",
            },
            {
                "type": BED_TYPE_MALOUF_LEGACY_OKIN,
                "label": "Legacy (FFE5)",
                "description": "Older Malouf bases",
                "hint": "Try 'New' first, use this if it doesn't work",
            },
        ],
    },
    "motosleep": {
        "display": "MotoSleep",
        "description": "HHC branded beds",
        "variants": None,  # Single protocol
    },
    "octo": {
        "display": "Octo",
        "description": "Octo beds (may require PIN)",
        "variants": None,  # Single protocol
    },
    "okin": {
        "display": "Okin / DewertOkin",
        "description": "Rize, Simmons, Nectar, Mattress Firm, Lucid beds",
        "variants": [
            {
                "type": BED_TYPE_OKIN_HANDLE,
                "label": "Standard (most common)",
                "description": "DewertOkin, A H Beard, Rize, Simmons, Resident, Symphony",
                "hint": "Device name often contains brand name or 'CB-'",
            },
            {
                "type": BED_TYPE_OKIN_UUID,
                "label": "Requires Bluetooth pairing",
                "description": "Okimat, Lucid, CVB, Smartbed - must pair in phone settings first",
                "hint": "Device name often starts with 'Okimat' or 'OKIN-'",
            },
            {
                "type": BED_TYPE_OKIN_7BYTE,
                "label": "Nectar beds",
                "description": "Nectar Move and similar models",
                "hint": "Device name contains 'Nectar'",
            },
            {
                "type": BED_TYPE_OKIN_NORDIC,
                "label": "Mattress Firm 900 / iFlex",
                "description": "Uses Nordic UART protocol",
                "hint": "Device name contains 'iFlex' or 'MF900'",
            },
            {
                "type": BED_TYPE_OKIN_FFE,
                "label": "OKIN 13/15 series",
                "description": "Newer OKIN actuators with FFE5 service",
                "hint": "Device name starts with 'OKIN', 'CB-', or 'CB.'",
            },
            {
                "type": BED_TYPE_OKIN_64BIT,
                "label": "64-bit protocol",
                "description": "OKIN actuators using 10-byte 64-bit commands",
                "hint": "Try other variants first, use this if they don't work",
            },
        ],
    },
    "reverie": {
        "display": "Reverie",
        "description": "Reverie adjustable bases",
        "variants": [
            {
                "type": BED_TYPE_REVERIE_NIGHTSTAND,
                "label": "Nightstand (Protocol 110)",
                "description": "Beds using the Reverie Nightstand app",
                "hint": "Device name contains 'RV' - try this first",
            },
            {
                "type": BED_TYPE_REVERIE,
                "label": "Legacy (Protocol 108)",
                "description": "Older Reverie beds",
                "hint": "Try 'Nightstand' first, use this if it doesn't work",
            },
        ],
    },
    "richmat": {
        "display": "Richmat",
        "description": "Casper, MLILY, Avocado, Jerome's, SVEN & SON, and 50+ brands",
        "variants": None,  # Single protocol, variant detected automatically
    },
    "sleepys": {
        "display": "Sleepy's",
        "description": "Sleepy's Elite adjustable bases",
        "variants": [
            {
                "type": BED_TYPE_SLEEPYS_BOX15,
                "label": "BOX15 (9-byte)",
                "description": "Sleepy's Elite with BOX15 protocol",
                "hint": "Try this first if unsure",
            },
            {
                "type": BED_TYPE_SLEEPYS_BOX24,
                "label": "BOX24 (7-byte)",
                "description": "Sleepy's Elite with BOX24 protocol",
                "hint": "Try BOX15 first, use this if it doesn't work",
            },
        ],
    },
    "solace": {
        "display": "Solace",
        "description": "Solace Sleep beds",
        "variants": None,  # Single protocol
    },
}

# Mapping from actuator group to single bed type (for groups without variants)
SINGLE_TYPE_GROUPS: Final[dict[str, str]] = {
    "bedtech": BED_TYPE_BEDTECH,
    "comfort_motion": BED_TYPE_COMFORT_MOTION,
    "ergomotion": BED_TYPE_ERGOMOTION,
    "jensen": BED_TYPE_JENSEN,
    "jiecang": BED_TYPE_JIECANG,
    "linak": BED_TYPE_LINAK,
    "limoss": BED_TYPE_LIMOSS,
    "motosleep": BED_TYPE_MOTOSLEEP,
    "octo": BED_TYPE_OCTO,
    "richmat": BED_TYPE_RICHMAT,
    "solace": BED_TYPE_SOLACE,
}


def get_bed_type_for_group(group_key: str) -> str | None:
    """Get the bed type for a single-type actuator group.

    Args:
        group_key: The actuator group key (e.g., 'richmat', 'linak')

    Returns:
        The bed type constant, or None if the group has variants
    """
    return SINGLE_TYPE_GROUPS.get(group_key)


def get_actuator_group_for_bed_type(bed_type: str) -> tuple[str, str | None] | None:
    """Find the actuator group and variant label for a bed type.

    Args:
        bed_type: The bed type constant (e.g., BED_TYPE_OKIN_HANDLE)

    Returns:
        Tuple of (group_key, variant_label) or None if not found.
        variant_label is None for single-type groups.
    """
    for group_key, group in ACTUATOR_GROUPS.items():
        variants = group["variants"]
        if variants is not None:
            for variant in variants:
                if variant["type"] == bed_type:
                    return (group_key, variant["label"])
        else:
            single_type = SINGLE_TYPE_GROUPS.get(group_key)
            if single_type == bed_type:
                return (group_key, None)
    return None


def get_friendly_display_name(bed_type: str) -> str:
    """Get a user-friendly display name for a bed type.

    Used for auto-detection messages like "Detected as: Okin (Standard)".

    Args:
        bed_type: The bed type constant

    Returns:
        A friendly display name like "Okin (Standard)" or "Richmat"
    """
    result = get_actuator_group_for_bed_type(bed_type)
    if not result:
        # Fallback: return bed_type as-is with underscores replaced
        return bed_type.replace("_", " ").title()

    group_key, variant_label = result
    group = ACTUATOR_GROUPS[group_key]
    group_display = group["display"]

    if variant_label:
        # Extract short label from variant_label.
        # Variant labels in ACTUATOR_GROUPS typically follow the pattern
        # "Short Name (extra info)" - e.g., "Standard (most common)".
        # We extract just the prefix before the parenthesis for display.
        # If no parenthesis exists, use the full label as-is.
        if " (" in variant_label:
            short_label = variant_label.split(" (")[0]
        else:
            short_label = variant_label.strip()
        return f"{group_display} ({short_label})"

    return group_display
