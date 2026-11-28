"""Validation and configuration helpers for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re
from typing import Any, Final

from homeassistant.core import HomeAssistant

from .beds.galaxy.catalog import PROFILE_CHOICES as GALAXY_PROFILES
from .beds.goodvibe.catalog import PROFILE_CHOICES as GOODVIBE_PROFILES
from .beds.hjbed.catalog import PROFILE_CHOICES as HJBED_PROFILES
from .beds.reverie.profiles import REVERIE_MODEL_CHOICES
from .beds.richmat_app.catalog import ALL_CHOICES as RICHMAT_APP_PRODUCTS
from .beds.richmat_app.sleep_profiles import CHOICES as RICHMAT_SLEEP_CHOICES
from .beds.richmat_classic.profiles import APP_NAMES as RICHMAT_CLASSIC_APPS
from .beds.richmat_mh.models import RICHMAT_MH_VARIANTS_BY_APP
from .const import (
    ADAPTER_AUTO,
    ADJUSTABLE_BED_VARIANTS,
    ADJUSTABLE_LUMBAR_VARIANTS,
    ADJUSTAMATTRESS_VARIANTS,
    ALYA_LAYOUTS,
    AUTOMATIC_LABEL,
    BED_TYPE_ADJUSTABLE_BED,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_ADJUSTAMATTRESS,
    BED_TYPE_ALYA,
    BED_TYPE_AMBIENT,
    BED_TYPE_BEDSENSE,
    BED_TYPE_BETTERLIVING2,
    BED_TYPE_CASPER_BASE,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_COMFORTBASE,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_DUNLOPILLO,
    BED_TYPE_DYNASTY_BASE_A,
    BED_TYPE_ENSO2,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_GALAXY,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_JOBS,
    BED_TYPE_JUNASLEEP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LIKIMIO,
    BED_TYPE_LINAK,
    BED_TYPE_MLILY,
    BED_TYPE_MYSIDE,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMIKI,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_PURELY_SLEEP,
    BED_TYPE_QPLUS_APP,
    BED_TYPE_REMACRO,
    BED_TYPE_RESTONIC,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_APP,
    BED_TYPE_RICHMAT_APP_SLEEP,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_RONDURE,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEPTIME,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    BED_TYPE_SOMOS,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_SVANE,
    BED_TYPE_YAMADA,
    BED_TYPE_ZSERIES,
    BEDSENSE_VARIANTS,
    COMFORT_ENHANCEMENTS_VARIANTS,
    DORSAL_ROUTES,
    DOUBLESLEEP_VARIANTS,
    ESHINE_OKIN_PROFILES,
    GLIDEAWAY_MOTION_MODELS,
    JOBS_VARIANTS,
    KAIDI_VARIANTS,
    KEESON_VARIANTS,
    LINAK_VARIANTS,
    OCTO_VARIANTS,
    OKIMAT_VARIANTS,
    OKIN_64BIT_VARIANTS,
    OKIN_CST_VARIANTS,
    OKIN_DOT_VARIANTS,
    PAIRLINK_MODEL_CHOICES,
    QPLUS_VARIANTS,
    REMACRO_VARIANTS,
    RICHMAT_MH_APPS,
    RICHMAT_VARIANTS,
    RONDURE_VARIANTS,
    SIMMONS_VARIANTS,
    SLEEP_NUMBER_VARIANTS,
    SLEEPYS_BOX25_VARIANTS,
    SMARTBED_VARIANTS,
    SOLACE_VARIANTS,
    STAR_ELEVATE_VARIANTS,
    SVANE_VARIANTS,
    VARIANT_AUTO,
    VARIANT_REQUIRED_BED_TYPES,
    ZSERIES_VARIANTS,
)
from .profiles.ai_bed import ROUTE_CHOICES as AI_BED_VARIANTS
from .profiles.ambient import LAYOUTS as AMBIENT_LAYOUTS
from .profiles.askona import MODEL_CHOICES as ASKONA_MODELS
from .profiles.berun import PROFILES as BERUN_PROFILES
from .profiles.bobpowerbase import PROFILE_CHOICES as BOB_PROFILES
from .profiles.casper import CASPER_BASE_VARIANTS
from .profiles.comfort_enhancement3 import CHOICES as APEX_CHOICES
from .profiles.comfortbase import PRODUCTS as COMFORTBASE_PRODUCTS
from .profiles.dunlopillo import CHOICES as DUNLOPILLO_CHOICES
from .profiles.dynasty_base_a import CHOICES as DYNASTY_BASE_A_CHOICES
from .profiles.enso2 import LAYOUT_CHOICES as ENSO2_LAYOUT_CHOICES
from .profiles.ergosportive import VARIANTS as ERGOSPORTIVE_CHOICES
from .profiles.hush import HUSH_BASE_VARIANTS
from .profiles.instant_comfort import ROUTES as INSTANT_COMFORT_ROUTES
from .profiles.junasleep import CHOICES as JUNASLEEP_CHOICES
from .profiles.kingkoil import CHOICES as KINGKOIL_CHOICES
from .profiles.konfurt import CHOICES as KONFURT_CHOICES
from .profiles.leva import RECEIVERS as LEVA_RECEIVERS
from .profiles.likimio import CHOICES as LIKIMIO_CHOICES
from .profiles.linx import TRANSPORT_CHOICES as LINX_TRANSPORTS
from .profiles.luuna import VARIANTS as LUUNA_VARIANTS
from .profiles.majestichome import PROFILE_CHOICES as MAJESTICHOME_PROFILES
from .profiles.mlily0 import VARIANTS as MLILY0_PROFILES
from .profiles.mlily_choices import PROFILE_CHOICES as MLILY_PROFILES
from .profiles.mlily_remote import VARIANTS as MLILY_REMOTE_PROFILES
from .profiles.motionflex import CHOICES as MOTIONFLEX_CHOICES
from .profiles.myside import CHOICES as MYSIDE_PRODUCTS
from .profiles.okimiki import PROFILE_CHOICES as OKIMIKI_PROFILES
from .profiles.personal_comfort import ROUTES as PERSONAL_COMFORT_ROUTES
from .profiles.purely_sleep import PRODUCT_CHOICES as PURELY_SLEEP_PRODUCTS
from .profiles.relax_motion import ROUTES as RELAX_MOTION_ROUTES
from .profiles.restonic import BRANCH_CHOICES as RESTONIC_BRANCHES
from .profiles.richmat import BEDTECH_VARIANTS
from .profiles.richmat_legacy import APP_NAMES as LEGACY_APPS
from .profiles.richmat_legacy import choices as legacy_choices
from .profiles.ronco_motion import CHOICES as RONCO_MOTION_VARIANTS
from .profiles.saatva import CHOICES as SAATVA_CHOICES
from .profiles.silksnow import CHOICES as SILKSNOW_CHOICES
from .profiles.sinca_comfort import PROTOCOL_LABELS as SINCA_RECEIVERS
from .profiles.sleeptime import SELECTORS as SLEEPTIME_SELECTORS
from .profiles.somos import CHOICES as SOMOS_CHOICES
from .profiles.super_colchones import VARIANTS as SUPER_COLCHONES_VARIANTS
from .profiles.sven import CHOICES as SVEN_CHOICES
from .profiles.symphony import SELECTORS as SYMPHONY_SELECTORS
from .profiles.thrivesleep import VARIANTS as THRIVESLEEP_VARIANTS

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
# Enforces consistent separator (all colons or all dashes, not mixed)
MAC_ADDRESS_PATTERN = re.compile(
    r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$|^([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}$"
)


def is_valid_mac_address(address: str) -> bool:
    """Validate a MAC address format."""
    return bool(MAC_ADDRESS_PATTERN.match(address))


def normalize_octo_pin(pin: Any | None) -> str:
    """Normalize Octo PIN input to a clean string."""
    if pin is None:
        return ""
    return str(pin).strip()


def is_valid_octo_pin(pin: str) -> bool:
    """Return True if PIN is empty or exactly four keypad digits."""
    return pin == "" or (len(pin) == 4 and pin.isascii() and pin.isdigit())


# What a user can tell the Smart Sleep app's two control sets apart by.
SMART_SLEEP_CONTROLS: Final = {"p1": "Older bed controls", "p2": "Newer bed controls"}
# The M Line app picks its commands by the Bluetooth name, which users can read.
MLINE_PROTOCOL_LABELS: Final = {
    "sleep": "Bluetooth name contains SLEEP",
    "smart": "Bluetooth name contains SMART",
    "smartsainuo": "Bluetooth name contains SMART, other receiver",
    "okin": "Bluetooth name contains OKIN",
    "unknown": "Any other Bluetooth name",
}

# Single source of truth for bed types with variants
VARIANTS_BY_BED_TYPE: dict[str, dict[str, str]] = {
    "askona": ASKONA_MODELS,
    "intellibed": {"old": "Old / white remote", "hhc": "HHC / silver remote"},
    BED_TYPE_AMBIENT: AMBIENT_LAYOUTS,
    "berun": {key: f"Version {profile.version}" for key, profile in BERUN_PROFILES.items()},
    BED_TYPE_SLEEPTIME: dict(SLEEPTIME_SELECTORS),
    "mattresspoint": {"BOX2422": "BOX2422", "BOX2442": "BOX2442"},
    BED_TYPE_PURELY_SLEEP: dict(PURELY_SLEEP_PRODUCTS),
    "ormatek": {"okin15": "Bluetooth name starts with Okin", "okin24": "Bluetooth name starts with SmartBed"},
    "leva": dict(LEVA_RECEIVERS),
    BED_TYPE_LIKIMIO: LIKIMIO_CHOICES,
    "linx": LINX_TRANSPORTS,
    "nerum": {"p1": "Receiver type P1 (one memory)", "p2": "Receiver type P2 (two memories, alarms)", "p3": "Receiver type P3 (two memories, alarms)"},
    **{app: legacy_choices(app) for app in LEGACY_APPS},
    "smart_sleep": SMART_SLEEP_CONTROLS,
    "comfort_enhancement3": APEX_CHOICES,
    "symphony_sleep": {"box1": "Box 1 (P1)", "box2": "Box 2 (P2)", "fallback": "Box 1, without position readings"},
    "bedtech": BEDTECH_VARIANTS,
    BED_TYPE_GALAXY: GALAXY_PROFILES,
    BED_TYPE_GOODVIBE: GOODVIBE_PROFILES,
    BED_TYPE_MLILY: MLILY_PROFILES,
    "majestichome": MAJESTICHOME_PROFILES,
    BED_TYPE_OKIMIKI: OKIMIKI_PROFILES,
    "saatva": SAATVA_CHOICES,
    "bobpowerbase": BOB_PROFILES,
    BED_TYPE_RICHMAT_CLASSIC_APPS: RICHMAT_CLASSIC_APPS,
    BED_TYPE_HJBED: HJBED_PROFILES,
    BED_TYPE_ENSO2: ENSO2_LAYOUT_CHOICES,
    BED_TYPE_MYSIDE: MYSIDE_PRODUCTS,
    BED_TYPE_RICHMAT_APP: RICHMAT_APP_PRODUCTS,
    BED_TYPE_RICHMAT_APP_SLEEP: RICHMAT_SLEEP_CHOICES,
    BED_TYPE_ALYA: ALYA_LAYOUTS,
    BED_TYPE_ESHINE_OKIN: ESHINE_OKIN_PROFILES,
    "rize_home": {"remedy_iii": "Remedy III", "contempo_iv": "Contempo IV"},
    "superior_sleep": {"ss350": "SS350", "ss650": "SS650"},
    "meisemobell": {"15_22_15a": "15_22_15A", "24_xx_xx": "24_XX_XX"},
    BED_TYPE_DOUBLESLEEP: DOUBLESLEEP_VARIANTS,
    "symphony": {"auto": AUTOMATIC_LABEL, **SYMPHONY_SELECTORS},
    BED_TYPE_GLIDEAWAY_MOTION: GLIDEAWAY_MOTION_MODELS,
    BED_TYPE_BEDSENSE: BEDSENSE_VARIANTS,
    BED_TYPE_CASPER_BASE: CASPER_BASE_VARIANTS,
    "hush_base": HUSH_BASE_VARIANTS,
    "silksnow": SILKSNOW_CHOICES,
    "ai_bed": AI_BED_VARIANTS,
    "ronco_motion": RONCO_MOTION_VARIANTS,
    "luuna": LUUNA_VARIANTS,
    "thrivesleep": THRIVESLEEP_VARIANTS,
    "super_colchones": SUPER_COLCHONES_VARIANTS,
    "personal_comfort": PERSONAL_COMFORT_ROUTES,
    "instant_comfort": INSTANT_COMFORT_ROUTES,
    "mlily_remote": MLILY_REMOTE_PROFILES,
    "mlily0": MLILY0_PROFILES,
    "motionflex": MOTIONFLEX_CHOICES,
    "mline": {"auto": AUTOMATIC_LABEL, **MLINE_PROTOCOL_LABELS},
    "sinca_comfort": {"auto": AUTOMATIC_LABEL, **SINCA_RECEIVERS},
    BED_TYPE_KAIDI: KAIDI_VARIANTS,
    "smartbed": SMARTBED_VARIANTS,
    BED_TYPE_OKIN_CST: OKIN_CST_VARIANTS,
    BED_TYPE_KEESON: KEESON_VARIANTS,
    BED_TYPE_LINAK: LINAK_VARIANTS,
    BED_TYPE_REMACRO: REMACRO_VARIANTS,
    BED_TYPE_RICHMAT: RICHMAT_VARIANTS,
    BED_TYPE_RONDURE: RONDURE_VARIANTS,
    BED_TYPE_QPLUS_APP: QPLUS_VARIANTS,
    BED_TYPE_SLEEP_NUMBER: SLEEP_NUMBER_VARIANTS,
    BED_TYPE_SLEEPYS_BOX25: SLEEPYS_BOX25_VARIANTS,
    BED_TYPE_SIMMONS: SIMMONS_VARIANTS,
    BED_TYPE_ADJUSTAMATTRESS: ADJUSTAMATTRESS_VARIANTS,
    BED_TYPE_ADJUSTABLE_BED: ADJUSTABLE_BED_VARIANTS,
    BED_TYPE_ADJUSTABLE_LUMBAR: ADJUSTABLE_LUMBAR_VARIANTS,
    BED_TYPE_COMFORT_ENHANCEMENTS: COMFORT_ENHANCEMENTS_VARIANTS,
    BED_TYPE_RESTONIC: RESTONIC_BRANCHES,
    "sven": SVEN_CHOICES,
    "konfurt": KONFURT_CHOICES,
    "ergosportive": ERGOSPORTIVE_CHOICES,
    "kingkoil": KINGKOIL_CHOICES,
    BED_TYPE_DUNLOPILLO: DUNLOPILLO_CHOICES,
    BED_TYPE_JUNASLEEP: JUNASLEEP_CHOICES,
    BED_TYPE_DYNASTY_BASE_A: DYNASTY_BASE_A_CHOICES,
    BED_TYPE_SOMOS: SOMOS_CHOICES,
    BED_TYPE_COMFORTBASE: {key: p.name for key, p in COMFORTBASE_PRODUCTS.items()},
    "dorsal": DORSAL_ROUTES,
    "relax_motion": RELAX_MOTION_ROUTES,
    BED_TYPE_YAMADA: {"p1": "P1 control box", "p2": "P2 control box"},
    BED_TYPE_BETTERLIVING2: {"p1": "P1 control box", "p2": "P2 control box", "p3": "P3 control box"},
    **{bed_type: RICHMAT_MH_VARIANTS_BY_APP[app] for bed_type, app in RICHMAT_MH_APPS.items()},
    "richmat_sleep_receiver": {"wsilver2": "W.Silver Products", "americanstar": "AMERICANSTAR",
                               "bailey2": "Bailey's Bed Control", "tx": "TX"},
    BED_TYPE_SOLACE: SOLACE_VARIANTS,
    BED_TYPE_REVERIE_NIGHTSTAND: REVERIE_MODEL_CHOICES,
    BED_TYPE_REVERIE: REVERIE_MODEL_CHOICES,
    BED_TYPE_REVERIE_PAIRLINK: PAIRLINK_MODEL_CHOICES,
    BED_TYPE_STAR_ELEVATE: STAR_ELEVATE_VARIANTS,
    BED_TYPE_SVANE: SVANE_VARIANTS,
    BED_TYPE_JOBS: JOBS_VARIANTS,
    BED_TYPE_ZSERIES: ZSERIES_VARIANTS,
    BED_TYPE_OCTO: OCTO_VARIANTS,
    BED_TYPE_OKIN_UUID: OKIMAT_VARIANTS,
    BED_TYPE_OKIN_DOT: OKIN_DOT_VARIANTS,
    BED_TYPE_OKIN_64BIT: OKIN_64BIT_VARIANTS,
}


def get_variants_for_bed_type(bed_type: str | None) -> dict[str, str] | None:
    """Get available protocol variants for a bed type, or None if no variants."""
    if bed_type is None:
        return None
    return VARIANTS_BY_BED_TYPE.get(bed_type)


def is_valid_variant_for_bed_type(bed_type: str, variant: str) -> bool:
    """Check if a protocol variant is valid for a given bed type."""
    if variant == VARIANT_AUTO:
        return bed_type not in VARIANT_REQUIRED_BED_TYPES
    valid_variants = get_variants_for_bed_type(bed_type)
    return valid_variants is not None and variant in valid_variants


def get_available_adapters(hass: HomeAssistant) -> dict[str, str]:
    """Get available Bluetooth adapters/proxies."""
    adapters: dict[str, str] = {ADAPTER_AUTO: "Automatic (let Home Assistant choose)"}

    try:
        from homeassistant.components.bluetooth import async_current_scanners

        from .bluetooth_transport import TransportClass, classify_scanner

        for scanner in async_current_scanners(hass):
            source = getattr(scanner, "source", None)
            name = getattr(scanner, "name", None)
            if not source:
                continue
            if source not in adapters:
                if name and name != source:
                    # Avoid duplicating MAC if it's already in the name
                    if source in name:
                        adapters[source] = name
                    else:
                        adapters[source] = f"{name} ({source})"
                else:
                    # Classify from the scanner object. The old test here was
                    # `":" in source`, which reads a local adapter's own MAC
                    # address as evidence of a remote proxy.
                    transport = classify_scanner(scanner)
                    if transport is TransportClass.PROXY:
                        adapters[source] = f"Bluetooth Proxy ({source})"
                    elif transport is TransportClass.LOCAL:
                        adapters[source] = f"Local Adapter ({source})"
                    else:
                        adapters[source] = f"Bluetooth Adapter ({source})"
    except Exception as err:
        _LOGGER.debug("Could not get scanner names: %s", err)

    _LOGGER.debug("Available Bluetooth adapters: %s", adapters)
    return adapters
