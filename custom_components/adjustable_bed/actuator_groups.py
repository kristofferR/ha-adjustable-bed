"""Actuator group definitions for two-tier bed selection.

This module organizes bed types into user-friendly groups based on actuator brand,
making it easier for users to select the correct bed type during setup.
"""

from __future__ import annotations

from typing import Final, TypedDict

from .const import (
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_BEST_MATTRESS,
    BED_TYPE_RICHMAT_BLVD_HOME,
    BED_TYPE_RICHMAT_HARMONY,
    BED_TYPE_RICHMAT_IDEALBED,
    BED_TYPE_RICHMAT_REVIVE,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_TRANQUIL,
    BED_TYPE_ZSERIES_Z230,
    BED_TYPE_ZSERIES_Z280,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_PURPLE,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
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
    "starcode_abm5_4": {
        "display": "AdjustableM5X4 app",
        "description": "Explicit app profile with independent command and Bluetooth selectors",
        "variants": [
            {
                "type": BED_TYPE_STARCODE_ABM5_4,
                "label": "AdjustableM5X4",
                "description": "Two control axes, one memory and app-specific massage/light controls",
                "hint": "Choose the app profile explicitly; shared Bluetooth names do not identify it.",
            }
        ],
    },
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
    "customatic": {
        "display": "Customatic apps",
        "description": "Clarity, Jerome's C and Remedy app profiles",
        "variants": [
            {
                "type": BED_TYPE_CUSTOMATIC_CLARITY,
                "label": "Clarity",
                "description": "Two motors, memory controls and light toggle",
                "hint": "Choose the Clarity app shown on your phone.",
            },
            {
                "type": BED_TYPE_CUSTOMATIC_JEROMES,
                "label": "Jerome's C",
                "description": "Two motors and the Jerome's flat action",
                "hint": "Choose the Jerome's C app shown on your phone.",
            },
            {
                "type": BED_TYPE_CUSTOMATIC_REMEDY,
                "label": "Remedy",
                "description": "Back, legs and lumbar, memory controls and light toggle",
                "hint": "Choose the Remedy app shown on your phone.",
            },
        ],
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
        "description": "Glideaway, ERGOBALANCE and Dream Motion beds",
        "variants": [
            {
                "type": BED_TYPE_JIECANG,
                "label": "Legacy Glide / Comfort Motion",
                "description": "Existing Jiecang controls",
                "hint": "Keep this choice for an existing working legacy bed.",
            },
            {
                "type": BED_TYPE_JIECANG_APP,
                "label": "ERGOBALANCE / Dream Motion apps",
                "description": "App-specific controls with an explicit physical layout",
                "hint": "Choose the app and its layout in the next step.",
            },
        ],
    },
    "kaidi": {
        "display": "Kaidi",
        "description": "Rize Remedy III, Floyd Home, ISleep (Mouselet devices)",
        "variants": None,  # Single protocol
    },
    "keeson": {
        "display": "Keeson",
        "description": "Purple, Member's Mark, GhostBed, Serta Motion Perfect, some Ergomotion Sync beds",
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
                "label": "KSBT (Nordic UART)",
                "description": "KSBT Nordic UART beds, including some Ergomotion Sync models",
                "hint": "Device name starts with 'KSBT03' or 'KSBT04'",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_ADJUSTABLE_LITE,
                "label": "Adjustable Lite app",
                "description": "KSBT01C and KSBT03C remotes from the Adjustable Lite app",
                "hint": "Choose this if you control the bed with the Adjustable Lite app",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_MAXCOIL_UNA,
                "label": "MaxCoil Una app",
                "description": "2-, 3- or 4-motor screens of the MaxCoil Una app; set the motor count",
                "hint": "Choose this if you control the bed with the MaxCoil Una app",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_DYNASTY_BASES,
                "label": "Dynasty Bases app",
                "description": "2-, 3- or 4-motor screens of the Dynasty Bases app; set the motor count",
                "hint": "Choose this if you control the bed with the Dynasty Bases app",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_RESTONIC_A,
                "label": "Restonic BT app, remote A",
                "description": "Head, foot, Flat and Zero G (6 buttons)",
                "hint": "Choose this if the Restonic BT Remote app is set to remote style A",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_RESTONIC_B,
                "label": "Restonic BT app, remote B",
                "description": "Adds Back + Legs, light and ZZZ buttons (10 buttons)",
                "hint": "Choose this if the Restonic BT Remote app is set to remote style B",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_SERTA,
                "label": "Serta Motion Perfect",
                "description": "Serta Motion Perfect III beds",
                "hint": "Device name contains 'Serta' or 'Motion Perfect'",
            },
            {
                "type": BED_TYPE_KEESON,
                "variant": KEESON_VARIANT_PURPLE,
                "label": "Purple Smart Base",
                "description": "Purple Premium Smart Base",
                "hint": "2023 and newer Purple beds with device name starting with 'Base-I5'",
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
        "variants": [
            {"type": BED_TYPE_LIMOSS, "label": "Legacy Limoss / Stawett", "description": "Existing generic controls", "hint": "Keep this choice for an existing working device."},
            {"type": BED_TYPE_LIMOSS_REMOTE, "label": "Limoss Remote app", "description": "App bed/chair layouts and eight local memories", "hint": "Select this explicitly for the Limoss Remote Android app."},
        ],
    },
    "malouf": {
        "display": "Malouf / Lucid",
        "description": "Malouf and Lucid adjustable bases",
        "variants": [
            {
                "type": BED_TYPE_MALOUF_APP,
                "label": "Malouf Base / Lucid Base apps",
                "description": "App model controls, status feedback and alarms",
                "hint": "Choose the app and model shown in your app in the next step.",
            },
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
    "logicdata": {
        "display": "Logicdata",
        "description": "SimplicityFrame, MotionRelax and Sleep Smart beds",
        "variants": [
            {
                "type": BED_TYPE_LOGICDATA,
                "label": "SimplicityFrame (SILVERmotion)",
                "description": "Existing encrypted SimplicityFrame protocol",
                "hint": "Keep this choice for an existing working SimplicityFrame bed.",
            },
            {
                "type": BED_TYPE_LOGICDATA_APP,
                "label": "MotionRelax / Sleep Smart bed apps",
                "description": "Explicit app, command family and physical layout",
                "hint": "Choose the app and its configuration in the next step.",
            },
            {
                "type": BED_TYPE_LOGICDATA_AIR_PUMP,
                "label": "Sleep Smart air mattress pump",
                "description": "Inflate, deflate, firmness 30, pressure memory and pressure",
                "hint": "Add the pump as its own device; its shared service cannot identify it.",
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
                "type": BED_TYPE_OKIN_CST,
                "label": "CST / Rize / Nectar Motion",
                "description": (
                    "Rize Sanctuary, Resident, Aviada, Bob, Contempo, II Carefree, "
                    "II Clarity, Rize MF900, Support, newer Nectar Motion, and some OKIN-* bases"
                ),
                "hint": "Try this for OKIN-* beds with 62741525 plus 90311625/00001530 GATT services",
            },
            {
                "type": BED_TYPE_OKIN_NORDIC,
                "label": "Mattress Firm 900 / iFlex",
                "description": "Uses Nordic UART protocol",
                "hint": "Device name contains 'iFlex' or 'MF900'",
            },
            {
                "type": BED_TYPE_FURNIMOVE,
                "label": "FurniMove / OKIN Smart Remote",
                "description": "Select the handset ID used in the app",
                "hint": "The receiver label and shared Bluetooth services do not choose the layout.",
            },
            {
                "type": BED_TYPE_SERENITY,
                "label": "Jordan's Serenity app",
                "description": "Serenity app controls, M1/M2 and separate massage zones",
                "hint": "Choose the app shown on your phone; a shared OKIN name is not enough.",
            },
            {
                "type": BED_TYPE_TRANQUIL,
                "label": "Jordan's Tranquil app",
                "description": "Tranquil app controls, Lounge, M1/M2 and separate massage zones",
                "hint": "Choose the app shown on your phone; a shared OKIN name is not enough.",
            },
            {
                "type": BED_TYPE_ZSERIES_Z230,
                "label": "Customatic Z-Series app (Z-230)",
                "description": "Z-230 page: combined head and foot, M1, ZG and TV saves",
                "hint": "Choose the model selected in the Z-Series app; a shared OKIN name is not enough.",
            },
            {
                "type": BED_TYPE_ZSERIES_Z280,
                "label": "Customatic Z-Series app (Z-280)",
                "description": "Z-280 page: extra selector, M1/M2 and separate massage zones",
                "hint": "Choose the model selected in the Z-Series app; a shared OKIN name is not enough.",
            },
            {
                "type": BED_TYPE_SIMMONS,
                "label": "SIMMONS app",
                "description": "SIMMONS app controls, Custom Mode memory and two alarms",
                "hint": "Choose the app shown on your phone; OKIN/SmartBed names are shared.",
            },
            {
                "type": BED_TYPE_ADJUSTABLE_LUMBAR,
                "label": "Adjustable bed (Lumbar) app",
                "description": "Head, foot and lumbar, four presets with saves, light and massage",
                "hint": "Choose the app shown on your phone; OKIN/Star names are shared.",
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
            {
                "type": BED_TYPE_OKIN_RF_ECO_BT,
                "label": "Smart Remote / RF ECO BT single actuator",
                "description": "Elda BTH, MEGAMAT MBZ, RF ECO BT staircase actuator",
                "hint": "Device may advertise as OKIN-* with 62741525/90311625 GATT characteristics",
            },
            {
                "type": BED_TYPE_STARCODE_M5X5,
                "label": "AdjustableM5X5 app",
                "description": "CB25, F23, kneading and Elevate with independently addressed lifts",
                "hint": "Select the app class and exact Bluetooth name in the next step",
            },
            {
                "type": BED_TYPE_STAR_ELEVATE,
                "label": "ELEVATE two-actuator lift",
                "description": "Separate ELEVATE accessory used with M1X12/M5X5 systems",
                "hint": "Device name starts with 'ELEVATE' and advertises Nordic UART",
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
    "richmat_apps": {
        "display": "Richmat app profiles",
        "description": "Revive Control, Best Mattress, Blvd Home, HARMONY and Idealbed apps",
        "variants": [
            {
                "type": BED_TYPE_RICHMAT_REVIVE,
                "label": "Revive Control app",
                "description": "The Revive Control model catalog and pages",
                "hint": "Choose the app shown on your phone; Richmat names are shared.",
            },
            {
                "type": BED_TYPE_RICHMAT_BEST_MATTRESS,
                "label": "Best Mattress app",
                "description": "The Best Mattress model catalog and pages",
                "hint": "Choose the app shown on your phone; Richmat names are shared.",
            },
            {
                "type": BED_TYPE_RICHMAT_BLVD_HOME,
                "label": "Blvd Home app",
                "description": "The Blvd Home model catalog and pages",
                "hint": "Choose the app shown on your phone; Richmat names are shared.",
            },
            {
                "type": BED_TYPE_RICHMAT_HARMONY,
                "label": "HARMONY app",
                "description": "The HARMONY model catalog and pages",
                "hint": "Choose the app shown on your phone; Richmat names are shared.",
            },
            {
                "type": BED_TYPE_RICHMAT_IDEALBED,
                "label": "Idealbed app",
                "description": "The Idealbed model catalog and pages",
                "hint": "Choose the app shown on your phone; Richmat names are shared.",
            },
        ],
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
            {
                "type": BED_TYPE_SLEEPYS_BOX25,
                "label": "BOX25 Star (full-featured)",
                "description": "Sleepy's Elite with BOX25 Star controller (lights, massage, positions)",
                "hint": "Device name starts with 'Star'",
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
    "kaidi": BED_TYPE_KAIDI,
    "linak": BED_TYPE_LINAK,
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
