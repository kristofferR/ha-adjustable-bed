"""Bed type detection logic for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re
from typing import Any, Final

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.helpers.selector import SelectOptionDict

from .app_families import FAMILY_STEP_ROUTES, family_member_rows, family_row_label
from .beds.cheerssleep.catalog import advertisement as cheerssleep_advertisement
from .beds.doublesleep.protocol import discover as discover_doublesleep
from .beds.fsm_relax.discovery import matches_fsm_relax_candidate
from .beds.galaxy.catalog import PROFILE_CHOICES as GALAXY_PROFILES
from .beds.galaxy.discovery import scan_matches as galaxy_scan_matches
from .beds.goodvibe.catalog import PROFILE_CHOICES as GOODVIBE_PROFILES
from .beds.goodvibe.discovery import scan_matches as goodvibe_scan_matches
from .beds.goodvibe.discovery import suggested_profile as goodvibe_suggested_profile
from .beds.hjbed.catalog import PROFILE_CHOICES as HJBED_PROFILES
from .beds.kaidi.protocol import extract_kaidi_advertisement, is_floyd_advertisement
from .beds.mlily import scan_matches as mlily_scan_matches
from .beds.mlily import suggested_profile as mlily_suggested_profile
from .beds.motion_bed.models import accepts_motion_bed_name
from .beds.richmat_app.catalog import ALL_CHOICES as RICHMAT_APP_PRODUCTS
from .beds.richmat_app.sleep_profiles import CHOICES as RICHMAT_SLEEP_CHOICES
from .beds.richmat_classic.discovery import matching_apps as richmat_classic_matching_apps
from .beds.richmat_classic.profiles import APP_NAMES as RICHMAT_CLASSIC_APPS
from .beds.silvermotion.discovery import scan_matches as silvermotion_scan_matches
from .beds.starcode.abm5_4_profiles import TRANSPORTS as STARCODE_ABM5_4_TRANSPORTS
from .beds.svane.state import is_svane_discovery_name
from .bluetooth_transport import advertised_local_name
from .codec.ergobq import IDENTITY_SERVICE as ERGOBQ_IDENTITY_SERVICE
from .const import (
    BED_TYPE_ADJUSTABLE_BED,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_ADJUSTAMATTRESS,
    BED_TYPE_ALYA,
    BED_TYPE_AMBIENT,
    BED_TYPE_ATLAS_LIFT,
    BED_TYPE_BEDJET_POWERLAYER,
    BED_TYPE_BEDSENSE,
    # Legacy/brand-specific bed types
    # NOTE: BED_TYPE_BEDTECH and BED_TYPE_OKIN_64BIT can now be partially auto-detected:
    # - BedTech: By name pattern ("bedtech") or post-connection characteristic check
    # - OKIN 64-bit: By post-connection characteristic check (62741625 read char)
    # Full auto-detection requires connecting to examine GATT characteristics.
    BED_TYPE_BEDTECH,
    BED_TYPE_BETTERLIVING2,
    BED_TYPE_BF,
    BED_TYPE_CASPER_BASE,
    BED_TYPE_CASPER_SLEEP_MM,
    BED_TYPE_CASPER_SLEEP_SXB,
    BED_TYPE_CHERISH,
    BED_TYPE_COMFORT_ENHANCEMENT3,
    BED_TYPE_COMFORT_ENHANCEMENTS,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_COMFORTBASE,
    BED_TYPE_COMFYDS,
    BED_TYPE_COOLBASE,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_DEMO,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_DORSAL,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ENSO2,
    BED_TYPE_ERGOBED,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_ERGOMOTION_4,
    BED_TYPE_ESHINE,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_FLEXISPOT,
    BED_TYPE_FSM_RELAX,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GALAXY,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GMMOTOR_SLEEP_MM,
    BED_TYPE_GOODVIBE,
    BED_TYPE_HJBED,
    BED_TYPE_ISLEEP,
    BED_TYPE_JALON,
    BED_TYPE_JALON_BED,
    BED_TYPE_JENSEN,
    BED_TYPE_JEROME_ADJUSTABLE_BASE,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_JOBS,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_KOMFYD,
    BED_TYPE_LANGJUE,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LEVA,
    BED_TYPE_LIKIMIO,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_LINX,
    BED_TYPE_LOGICDATA,
    BED_TYPE_LOGICDATA_AIR_PUMP,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MLILY,
    BED_TYPE_MLILY0,
    BED_TYPE_MLILY_REMOTE,
    BED_TYPE_MLINE,
    BED_TYPE_MOODBASE,
    BED_TYPE_MOTION_BED,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_MYSIDE,
    BED_TYPE_N32_MOTION_BED,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMATTMOTION,
    BED_TYPE_OKIMIKI,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    # Protocol-based bed types (new)
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_MOTIONBED,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_ORMATEK,
    BED_TYPE_REMACRO,
    BED_TYPE_RESIDENT,
    BED_TYPE_RESTFUL,
    BED_TYPE_RESTONIC,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_APP,
    BED_TYPE_RICHMAT_APP_SLEEP,
    BED_TYPE_RICHMAT_BEST_MATTRESS,
    BED_TYPE_RICHMAT_BLVD_HOME,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    BED_TYPE_RICHMAT_HARMONY,
    BED_TYPE_RICHMAT_IDEALBED,
    BED_TYPE_RICHMAT_REVIVE,
    BED_TYPE_RIZE,
    BED_TYPE_RIZE_HOME,
    BED_TYPE_RIZE_REMEDY_II,
    BED_TYPE_RONCO_MOTION,
    BED_TYPE_RONDURE,
    BED_TYPE_SCOTT_LIVING,
    BED_TYPE_SERENITY,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SHUDA,
    BED_TYPE_SILVERMOTION,
    BED_TYPE_SIMMONS,
    BED_TYPE_SIMMONS_BLUE,
    BED_TYPE_SLEEP_ASSIST_PRO,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPSTAR,
    BED_TYPE_SLEEPTIME,
    BED_TYPE_SLEEPTRACKER,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_SOMOS,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SUPERIOR_SLEEP,
    BED_TYPE_SUTA,
    BED_TYPE_SUTA_KING_KOIL,
    BED_TYPE_SVANE,
    BED_TYPE_SYMPHONY,
    BED_TYPE_SYMPHONY_SLEEP,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_TRANQUIL,
    BED_TYPE_TRUEMOTION,
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VINDO,
    BED_TYPE_VMATBASIC,
    BED_TYPE_YAMADA,
    BED_TYPE_ZSERIES,
    # Detection constants
    BEDJET_ADVERTISED_SERVICE_UUID,
    BEDJET_POWERLAYER_NAME_PATTERNS,
    BEDTECH_MANUFACTURER_ID,
    BEDTECH_NAME_PATTERNS,
    BEDTECH_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_SERVICE_UUID,
    COOLBASE_NAME_PATTERNS,
    DEVICE_INFO_SERVICE_UUID,
    DEWERTOKIN_EXCLUDED_DEVICE_NAMES,
    DEWERTOKIN_NAME_PATTERNS,
    DEWERTOKIN_RF_GATEWAY_DEVICE_NAME_CHAR_UUID,
    DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
    DEWERTOKIN_SERVICE_UUID,
    DORSAL_ROOMI_S655_PLUS,
    DORSAL_ROUTES,
    ERGOMOTION_NAME_PATTERNS,
    ESHINE_OKIN_PROFILES,
    GLIDEAWAY_MOTION_MODELS,
    JENSEN_LINON_NAME_PATTERNS,
    JENSEN_NAME_FRAGMENT,
    JENSEN_NAME_PATTERNS,
    JENSEN_SERVICE_UUID,
    KAIDI_DISCOVERY_SERVICE_UUID,
    KAIDI_MAC_PREFIXES,
    KAIDI_MESH_SERVICE_UUID,
    KAIDI_NAME_PATTERNS,
    KAIDI_VARIANT_FLOYD,
    KEESON_BASE_SERVICE_UUID,
    KEESON_EXTENDED_NORDIC_SERVICE_UUID,
    KEESON_FALLBACK_GATT_PAIRS,
    KEESON_JSON_SERVICE_UUID,
    KEESON_NAME_PATTERNS,
    KEESON_SINO_NAME_PATTERNS,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_COMFORTFURNITURE,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_KSBT04C,
    KEESON_VARIANT_KSBT_CR,
    KEESON_VARIANT_LEVA_SLEEP,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_COMFORT_BED,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_ORE_ULTRAMATIC,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
    KEESON_VARIANT_SIMON_LI,
    LEGGETT_GEN2_MANUFACTURER_PREFIXES,
    LEGGETT_GEN2_SERVICE_UUID,
    LEGGETT_OKIN_NAME_PATTERNS,
    LEGGETT_RICHMAT_NAME_PATTERNS,
    LIMOSS_NAME_PATTERNS,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_NAME_PATTERNS,
    LINAK_POSITION_SERVICE_UUID,
    LINAK_VARIANT_AA_CONTROL_MY_BED,
    LINAK_VARIANT_CARPE_DIEM,
    LOGICDATA_SERVICE_UUID,
    MALOUF_LEGACY_OKIN_SERVICE_UUID,
    MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
    MALOUF_NAME_PATTERNS,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
    MALOUF_NEW_OKIN_WRITE_CHAR_UUID,
    MANUFACTURER_ID_DEWERTOKIN,
    MANUFACTURER_ID_LEGGETT_GEN2,
    MANUFACTURER_ID_LOGICDATA,
    MANUFACTURER_ID_OKIN,
    MANUFACTURER_ID_VIBRADORM,
    NORDIC_DFU_SERVICE_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
    OCTO_NAME_PATTERNS,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_NAME_ONLY_PATTERNS,
    OKIMAT_NAME_PATTERNS,
    OKIMAT_SERVICE_UUID,
    OKIMAT_VARIANTS,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_CST_VARIANTS,
    OKIN_FFE_NAME_PATTERNS,
    OKIN_GENERIC_NAME_PATTERNS,
    OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
    REMACRO_SERVICE_UUID,
    REMACRO_VARIANT_JEROMES,
    REMACRO_VARIANT_THE_BRICK,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_PAIRLINK_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NAME_PATTERNS,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RICHMAT_WILINKE_W4_SERVICE_UUID,
    RICHMAT_WILINKE_W5_SERVICE_UUID,
    SLEEP_NUMBER_MCR_SERVICE_UUID,
    SLEEP_NUMBER_SERVICE_UUID,
    SLEEPSTAR_DUAL_SUBTYPE,
    SLEEPSTAR_MANUFACTURER_ID,
    SLEEPSTAR_NAME_PATTERNS,
    SLEEPSTAR_SINGLE_SUBTYPE,
    SLEEPTRACKER_SERVICE_UUID,
    SLEEPYS_BOX25_NAME_PATTERNS,
    SLEEPYS_NAME_PATTERNS,
    SOLACE_NAME_PATTERNS,
    SOLACE_SERVICE_UUID,
    SOLACE_VARIANT_FLEXIREST,
    SOLACE_VARIANT_SOPHIE,
    SOLACE_VARIANT_WOOSA,
    STAR_ELEVATE_NAME_PATTERNS,
    STAR_ELEVATE_VARIANT_M1X12,
    SUTA_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_NAME_PATTERNS,
    SVANE_VARIANT_JENSEN_LINON,
    SVANE_VARIANT_JMC,
    TIMOTION_AHF_NAME_PATTERNS,
    TIMOTION_AHF_SERVICE_UUID,
    VARIANT_AUTO,
    VARIANT_REQUIRED_BED_TYPES,
    VIBRADORM_NAME_PATTERNS,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
    ZSERIES_VARIANT_Z230,
    ZSERIES_VARIANT_Z280,
    # Detection result type
    DetectionResult,
)
from .discovery_hints import (
    EXCLUDED_DEVICE_PATTERNS,
    GENERIC_SHARED_SERVICE_UUIDS,
    FirstPass,
    first_pass,
)
from .discovery_hints._hints import ManufacturerHint, NameHint
from .discovery_hints.linak import matches_vindo_advertisement
from .discovery_hints.richmat import ATLAS_LIFT_NAME_HINT
from .profiles.bedgear import eligible as bedgear_eligible
from .profiles.bedgear import ergobed_eligible
from .profiles.bobpowerbase import PROFILE_CHOICES as BOB_PROFILES
from .profiles.bobpowerbase import SCAN_KEYWORDS as BOB_SCAN_KEYWORDS
from .profiles.customatic_demo import NAME_PREFIX as CUSTOMATIC_DEMO_NAME_PREFIX
from .profiles.ergobq import product as ergobq_product
from .profiles.flexirest import accepts_name as accepts_flexirest_name
from .profiles.majestichome import PROFILE_CHOICES as MAJESTICHOME_PROFILES
from .profiles.mlily0 import VARIANTS as MLILY0_PROFILES
from .profiles.mlily_choices import PROFILE_CHOICES as MLILY_PROFILES
from .profiles.mlily_remote import VARIANTS as MLILY_REMOTE_PROFILES
from .profiles.moodbase import receiver_hint as moodbase_receiver_hint
from .profiles.motomotion import eligible as motomotion_eligible
from .profiles.myside import CHOICES as MYSIDE_PRODUCTS
from .profiles.okimiki import PROFILE_CHOICES as OKIMIKI_PROFILES
from .profiles.okimiki import scan_matches as okimiki_scan_matches
from .profiles.onlysnore import advertisement as onlysnore_advertisement
from .profiles.relax_motion import discovery_matches as relax_motion_matches
from .profiles.saatva import SCAN_UUIDS as SAATVA_SCAN_UUIDS
from .profiles.sealy import matches_name as sealy_name
from .profiles.simmons_blue import NAME_PREFIX as SIMMONS_BLUE_PREFIX
from .profiles.sinca_comfort import scan_name as sinca_scan_name
from .profiles.smart_sleep import advertisement as smart_sleep_advertisement
from .profiles.sophie import accepts_name as accepts_sophie_name
from .profiles.vmatbasic import manufacturer_payload_matches

_LOGGER = logging.getLogger(__name__)


def _is_motosleep_local_name(device_name: str) -> bool:
    """Return whether the normalized name is an HHC or exact MOTO bed name."""
    return (
        device_name.startswith("hhc")
        or (len(device_name) >= 14 and "hhc" in device_name)
        or (
            len(device_name) == 28
            and re.match(r"^moto[bs]\d{2}\w[0-9][bcd][a-z]\w\w\w", device_name) is not None
        )
    )


# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

# Richmat remote code pattern (e.g., QRRM, V1RM, BURM, ZR10, ZR60)
# Matches: 2 alphanumeric + "R" + "M" or "N" (like QRRM, V1RM, BURM, A0RN)
# Or: "ZR" + 2 alphanumeric chars (like ZR10, ZR60, ZRA2, ZRS3)
# Case-insensitive via re.IGNORECASE
RICHMAT_CODE_PATTERN = re.compile(r"^([a-z0-9]{2}r[mn]|zr[a-z0-9]{2})", re.IGNORECASE)
# Beds advertise the code in upper case (UaRM is the one catalog code with a
# lower-case letter), followed by a serial number or a separator, never a
# letter. Otherwise words such as "Firmware", "WARMUP" or "TERMINAL" would
# look like codes.
_RICHMAT_ADVERTISED_CODE = re.compile(r"^(?:[A-Z0-9]{2}R[MN]|ZR[A-Z0-9]{2}|UaRM)(?![A-Za-z])")

KEESON_FALLBACK_SERVICE_UUIDS: frozenset[str] = frozenset(
    service_uuid.lower() for service_uuid, _ in KEESON_FALLBACK_GATT_PAIRS
)

# WiLinke service UUIDs that non-bed devices also advertise, mapped to the
# reason they are not bed-unique. These only detect as Richmat when a Richmat
# name corroborates the match (see const.py for the full rationale).
NAME_GUARDED_WILINKE_UUIDS: dict[str, str] = {
    # W4: fully generic FFF0 short UUID - a "NO_DVR-*" camera system (#418)
    # and a FIXD OBD scanner (#415); all known W4 beds are "DHN-*" units.
    RICHMAT_WILINKE_W4_SERVICE_UUID.lower(): "generic FFF0 service",
    # W5: Telink-style custom base - a "Nokia-*" headset (#382).
    RICHMAT_WILINKE_W5_SERVICE_UUID.lower(): "shared Telink base",
}

OKIN_SHARED_UUID_GATT_REFINABLE_TYPES: frozenset[str] = frozenset(
    {
        BED_TYPE_LEGGETT_OKIN,
        BED_TYPE_OKIN_7BYTE,
        BED_TYPE_OKIN_UUID,
        BED_TYPE_OKIN_64BIT,
        BED_TYPE_OKIN_CST,
        BED_TYPE_OKIN_RF_ECO_BT,
    }
)

# Shared-UUID profiles a connected OKIMAT Device Info model must not rewrite.
# BED_TYPE_OKIN_UUID and
# BED_TYPE_OKIN_UUID resolve to the same controller. BED_TYPE_OKIN_CST is never
# rewritten here; the okimat_cst_route repair lets the user move it (#555).
OKIMAT_COMPATIBLE_PROFILES: frozenset[str] = frozenset(
    {
        BED_TYPE_OKIN_UUID,
        BED_TYPE_OKIN_CST,
    }
)

NORA_CONTROLLER_NORMALIZED_NAMES: frozenset[str] = frozenset({"noracon"})

# Manufacturer ID 89 is Nordic Semiconductor's company ID (0x0059), shared by many
# non-bed devices. The bare-manufacturer-data SmartBed fallback only applies when the
# device also advertises a recognizable OKIN/SmartBed name, so a random Nordic
# gadget (e.g. "ABXM2", #366) is not misidentified as a bed.
SMARTBED_MANUFACTURER_NAME_HINTS: frozenset[str] = frozenset({"okin", "smartbed"})

# Malouf S755 / DewertOkin CB.24.42.28 bases have been observed advertising only
# Nordic UART plus OKIN's company ID, without the usual Malouf 01000001 family
# UUID. The name prefix appears to encode the CB.24.42.28 control-box family.
MALOUF_NEW_OKIN_SMARTBED_NAME_PREFIXES: frozenset[str] = frozenset({"smartbed428"})
MALOUF_NEW_OKIN_OKIN_PAYLOAD_PREFIXES: tuple[bytes, ...] = (b"AB\x01\x02",)


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
        return BED_TYPE_OKIN_HANDLE, 0.95, MANUFACTURER_ID_DEWERTOKIN

    # Vibradorm: Company ID 944 (0x03B0)
    # Source: de.vibradorm.vra app disassembly
    if MANUFACTURER_ID_VIBRADORM in manufacturer_data:
        return BED_TYPE_VIBRADORM, 0.95, MANUFACTURER_ID_VIBRADORM

    # Logicdata: Company ID 1351 (0x0547)
    # Source: SILVERmotion app disassembly
    if MANUFACTURER_ID_LOGICDATA in manufacturer_data:
        if silvermotion_scan_matches(manufacturer_data):
            return BED_TYPE_SILVERMOTION, 0.95, MANUFACTURER_ID_LOGICDATA
        return BED_TYPE_LOGICDATA, 0.95, MANUFACTURER_ID_LOGICDATA

    # Leggett & Platt Gen2 / LP Comfort Connect (control box 209-M001): advertises
    # only manufacturer data under company 0x092D with an "XP"/"CP" payload prefix
    # and NO service UUID. Matches the LP Control app's isGen2Box() check.
    # Source: com.leggett.android.universal disassembly.
    lp_payload = manufacturer_data.get(MANUFACTURER_ID_LEGGETT_GEN2)
    if lp_payload is not None and lp_payload[:2] in LEGGETT_GEN2_MANUFACTURER_PREFIXES:
        return BED_TYPE_LEGGETT_GEN2, 0.95, MANUFACTURER_ID_LEGGETT_GEN2

    # Note: OKIN Automotive (ID 89) is NOT checked here because it should be
    # a fallback after UUID-based detection. See detect_bed_type_detailed().

    return None, 0.0, None


def _manufacturer_data_contains_ascii(
    manufacturer_data: dict[int, bytes] | None,
    marker: str,
) -> bool:
    """Return True if any manufacturer payload contains an ASCII marker."""
    if not manufacturer_data:
        return False

    marker_lower = marker.lower()
    return any(
        marker_lower in payload.decode("ascii", errors="ignore").lower()
        for payload in manufacturer_data.values()
    )


def _normalize_compact_identifier(value: str | None) -> str:
    """Normalize BLE names/model IDs for exact identifier comparisons."""
    return re.sub(r"[\s_-]+", "", (value or "").strip().lower())


def _is_nora_controller_identifier(value: str | None) -> bool:
    """Return True for NORA_CON / NORACON controller identifiers."""
    return _normalize_compact_identifier(value) in NORA_CONTROLLER_NORMALIZED_NAMES


def _is_malouf_new_okin_smartbed_signature(
    device_name: str,
    service_uuids: list[str],
    manufacturer_data: dict[int, bytes] | None,
) -> bool:
    """Return True for Nordic-only Malouf New Okin Smartbed advertisements."""
    if RICHMAT_NORDIC_SERVICE_UUID.lower() not in service_uuids:
        return False
    normalized_name = device_name.lower()
    if not any(
        normalized_name.startswith(prefix)
        for prefix in MALOUF_NEW_OKIN_SMARTBED_NAME_PREFIXES
    ):
        return False
    if not manufacturer_data:
        return False

    okin_payload = manufacturer_data.get(MANUFACTURER_ID_OKIN)
    return bool(
        okin_payload
        and okin_payload.startswith(MALOUF_NEW_OKIN_OKIN_PAYLOAD_PREFIXES)
    )


# Solace naming convention pattern (e.g., S4-Y-192-461000AD)
SOLACE_NAME_PATTERN = re.compile(r"^s4-y-\d+-[a-z0-9]+$", re.IGNORECASE)


def _is_standard_service(uuid: str) -> bool:
    """Return whether a UUID is an assigned 0x18xx service, such as Battery or HID.

    Watches, trackers, scales and mice advertise these beside a shared service.
    """
    return uuid.startswith("000018") and uuid.endswith("-0000-1000-8000-00805f9b34fb")


def _has_only_generic_uuids(service_uuids: list[str]) -> bool:
    """Check if device has only generic/shared UUIDs (or no UUIDs).

    Standard Bluetooth services are neutral. Returns True if the device should
    be subject to name-based exclusion checks, False if it has a unique
    bed-specific UUID that should take priority over name patterns.
    """
    return all(
        uuid in GENERIC_SHARED_SERVICE_UUIDS
        for uuid in service_uuids
        if not _is_standard_service(uuid)
    )


def _rests_on_shared_service(
    service_uuids: list[str], first: FirstPass, result: DetectionResult
) -> bool:
    """Return whether only shared services led to a bed type.

    A declared name or maker hint confirms the match, as does a name a
    detection rule recorded (``name:...``, other than an app candidate's).
    """
    return (
        any(not _is_standard_service(uuid) for uuid in service_uuids)
        and _has_only_generic_uuids(service_uuids)
        and not any(isinstance(hint, NameHint | ManufacturerHint) for hint in first.hints)
        and not any(
            signal.startswith("name:") and not signal.endswith("candidate")
            for signal in result.signals
        )
    )


# Display names for bed types shown in the UI selector. The automatic
# Leggett & Platt setup is not offered to a new bed, so it is not listed here.
BED_TYPE_DISPLAY_NAMES: dict[str, str] = {
    "dorsal": "Dorsal app / Roomi",
    "berun": "BERUN app",
    "nerum": "Nerum app",
    "relax_motion": "Relax Motion app",
    "cheerssleep": "CheersSleep app",
    "agingplace": "Aging in Place / Dawn House app",
    "smart_sleep": "OKIN Smart Sleep app",
    "sleep_assistant": "Sleep Assist",
    BED_TYPE_SLEEP_ASSIST_PRO: "Sleep Assist Pro",
    "onlysnore": "Snore Monitor app",
    "smart_comfort_synargy": "Smart Comfort by SYNARGY app",
    "smart_comfort_synergy": "Smart Comfort app",
    # v5 names the RUF and Richmat apps like the other Richmat MH apps.
    **{
        bed_type: f"{name} app"
        + {
            "AMERICANSTAR": " (Richmat)",
            "W.Silver Products": " (newer version)",
            # Not the newer BedTech app, whose name has no space.
            "Bed Tech": " (older app)",
        }.get(name, "")
        for bed_type, name in (
            ("ruf_betten", "RUF | Betten (Motor 2)"),
            ("wsilver_products", "W.Silver Products"),
            ("richmat_americanstar", "AMERICANSTAR"),
            ("bailey_bed_control", "Bailey's Bed Control"),
            ("richmat_tx", "TX"),
            ("richmat_nisco", "Nisco"),
            ("richmat_mlily_supreme", "MLILY Supreme"),
            ("bedtech_classic", "Bed Tech"),
        )
    },
    "richmat_sleep_receiver": "W.Silver / AMERICANSTAR / Bailey / TX sleep receiver",
    "gmmotor": "GM Control app",
    "gmmotor_sleep_mm": "GM Control sleep module (name starts with RM-)",
    "gmmotor_sleep_sxb": "GM Control sleep module (name starts with HJ-)",
    'tempur_curve': 'Tempur Curve app',
    'qplus_app': 'Q-Plus Adjustable Remote app (SBI and Costco beds)',
    'serta_mp_remote': 'Serta MP Remote app (Serta Motion Perfect)',
    'omazz_adjusto_iii': 'Omazz Adjusto III app',
    'ergomotion_app': 'Ergomotion app',
    'row_control': 'ROW Control app',
    'ergo_slim': 'Ergo Slim app',
    'tempur_au': 'TEMPUR AU app',
    BED_TYPE_BEDSENSE: "BedSense app",
    BED_TYPE_BF: "BF app",
    BED_TYPE_CHERISH: "Cherish app",
    "casper_remote": "Casper Base remote finder",
    "casper_base": "Casper Base app",
    "hush_base": "Hush Base app",
    "silksnow": "Silk & Snow (S&S Base app)",
    "majestichome": "Majestic Home app",
    "luuna": "Luuna + app (Rise, Rise Pro, Rise Pro Light)",
    "personal_comfort": "Personal Comfort app",
    "instant_comfort": "Instant Comfort app",
    "mline": "M Line app",
    "sinca_comfort": "Sinca Comfort Bed app",
    "luniosmart": "Lunio Smart+ app",
    "sleep_evolution": "SleepEvolution app",
    "wsilver_legacy": "W.Silver Products app (older version)",
    "super_colchones": "Super Colchones app (AFEG302, AFEG350)",
    "sonicsleep": "SonicSleep / 소닉슬립 app",
    "ergobq": "ErgoBQ BED app",
    "hush_remote": "Hush Base remote finder",
    "hush_sleep_mm": "Hush Base sleep sensor (name starts with RM-)",
    "hush_sleep_sxb": "Hush Base sleep sensor (name starts with HJ-)",
    "casper_sleep_mm": "Casper Base sleep sensor (name starts with RM-)",
    "casper_sleep_sxb": "Casper Base sleep sensor (name starts with HJ-)",

    BED_TYPE_FSM_RELAX: "FSM Relax app",

    BED_TYPE_STARCODE_M5X5: "AdjustableM5X5 app",
    BED_TYPE_STARCODE_M1X12: "Adjustable Comfort M1X12 app",
    BED_TYPE_FURNIMOVE: "FurniMove / OKIN Smart Remote app",
    BED_TYPE_SERENITY: "Jordan's Serenity app",
    BED_TYPE_TRANQUIL: "Jordan's Tranquil app",
    BED_TYPE_JOBS: "JobsAI智能助眠床 / Jobs AI app",
    BED_TYPE_RESTFUL: "Jordan's Restful app",
    BED_TYPE_RIZE_REMEDY_II: "Rize Remedy II app",
    BED_TYPE_ZSERIES: "Customatic Z-Series app",
    BED_TYPE_SIMMONS: "SIMMONS app",
    BED_TYPE_ADJUSTAMATTRESS: "AdjustaMattress app",
    BED_TYPE_ADJUSTABLE_BED: "Adjustable bed app",
    BED_TYPE_ADJUSTABLE_LUMBAR: "Adjustable bed (Lumbar) app",
    BED_TYPE_SUPERIOR_SLEEP: "Superior sleep app (SS350 / SS650)",
    BED_TYPE_RIZE_HOME: "Rize Home app",
    BED_TYPE_OKIN_MOTIONBED: "OKIN Motion Bed app",
    BED_TYPE_OKIMATTMOTION: "OkimattMotion app",
    BED_TYPE_COMFORT_ENHANCEMENT3: "Comfort Enhancement 3 / Comfort Plus3 app",
    BED_TYPE_N32_MOTION_BED: "N32 Motion Bed app",
    BED_TYPE_SHUDA: "Shuda app",
    BED_TYPE_SIMMONS_BLUE: "Simmons Blue app",
    BED_TYPE_RESIDENT: "Resident Adjustable Base app",
    BED_TYPE_SLEEPTIME: "Sleeptime Australia app (SmartBed205, 402, 404, 405)",
    "enso": "Enso Remote",
    BED_TYPE_ENSO2: "ENSO Sleep Control (Enso 2)",
    "sealy_posturematic": "Sealy Posturematic",
    BED_TYPE_YAMADA: "アシステック / ASSISTEC / Yamada app",
    BED_TYPE_BETTERLIVING2: "BetterLiving / BetterLiving2 app",
    BED_TYPE_LEVA: "Leva Bed Remote (Leva Smart App)",
    BED_TYPE_LANGJUE: "Comfort Smart Bed app (Langjue)",
    BED_TYPE_LINX: "Linx app",
    BED_TYPE_RESTONIC: "Restonic app (Prime / Lombar / Infinity)",
    BED_TYPE_FLEXISPOT: "Flexispot app",
    "kingkoil": "King Koil Bed app",
    BED_TYPE_SOMOS: "Somos / SomosBeds app",
    BED_TYPE_COMFORTBASE: "ComfortBaseForBluetooth app",
    BED_TYPE_COMFORT_ENHANCEMENTS: "Comfort Enhancements app",
    BED_TYPE_ALYA: "Alya Smart Furnishing app (choose BLE type and motor layout)",
    BED_TYPE_ESHINE_OKIN: "eShine app (E2000 to E5000)",
    BED_TYPE_ESHINE: "eShine app (E6000)",
    BED_TYPE_RICHMAT_REVIVE: "Revive Control app",
    BED_TYPE_RICHMAT_BEST_MATTRESS: "Best Mattress app",
    BED_TYPE_RICHMAT_BLVD_HOME: "Blvd Home app",
    BED_TYPE_RICHMAT_HARMONY: "HARMONY app",
    BED_TYPE_RICHMAT_IDEALBED: "Idealbed app",
    "ultramatic_smart_bed": "Ultramatic Smart Bed app",
    BED_TYPE_CUSTOMATIC_DEMO: "Independence app (Customatic Demo)",
    BED_TYPE_CUSTOMATIC_CLARITY: "Customatic Clarity app (Rize Clarity)",
    BED_TYPE_CUSTOMATIC_JEROMES: "Customatic Jerome's C app",
    BED_TYPE_CUSTOMATIC_REMEDY: "Customatic Remedy app (Rize Remedy)",
    # Protocol-based types (Okin family)
    BED_TYPE_OKIN_HANDLE: "Okin receiver (DewertOkin and A H Beard beds)",
    BED_TYPE_OKIN_UUID: "Okin receiver (Okimat and Lucid remotes)",
    BED_TYPE_OKIN_7BYTE: "Okin receiver (Nectar beds)",
    BED_TYPE_OKIN_NORDIC: "Okin receiver (Mattress Firm 900 and iFlex beds)",
    "smartbed": "SmartBed app (Okin receivers, Amada beds)",
    BED_TYPE_OKIN_DOT: "Okin DOT remotes (RF1058, RF34 and RF6707)",
    BED_TYPE_OKIN_FFE: "Okin receiver (13 and 15 series)",
    "hestia_motion": "Hestia Motion app",
    BED_TYPE_OKIN_ORE: "Okin receiver (older ORE remotes)",
    BED_TYPE_GALAXY: "Galaxy Bed Control app",
    BED_TYPE_GOODVIBE: "Good Vibe Sleep app",
    BED_TYPE_MLILY: "MLILY Control app",
    BED_TYPE_OKIMIKI: "Okimiki app",
    "dreamsense": "Dream Sense Bed",
    BED_TYPE_LIKIMIO: "Likimio (ABM10)",
    "saatva": "Saatva app",
    "bobpowerbase": "Power Bob Base app",
    BED_TYPE_MLILY0: "MLILY 3.1.1 app",
    BED_TYPE_MLILY_REMOTE: "MLILY Remote app",
    BED_TYPE_RICHMAT_CLASSIC_APPS: "Avocado Eco Base / CoasterSleep / Forty Winks / Milemont / Superior",
    BED_TYPE_MOTOMOTION: "MotoMotion app",
    BED_TYPE_HJBED: "HJBed app",
    BED_TYPE_JALON: "OkinComfortBed II N app",
    BED_TYPE_SYMPHONY_SLEEP: "Symphony Sleep app",
    BED_TYPE_JALON_BED: "OkinComfortBed II app",
    BED_TYPE_SYMPHONY: "Symphony Sleep Sense app",
    BED_TYPE_ORMATEK: "OrmatekTechnoSmart app",
    BED_TYPE_JEROME_ADJUSTABLE_BASE: "Jerome's Adjustable Base app",
    BED_TYPE_MYSIDE: "My Side app",
    BED_TYPE_RICHMAT_APP: "Richmat app",
    BED_TYPE_RICHMAT_APP_SLEEP: "Richmat app sleep sensor",
    BED_TYPE_GLIDEAWAY_MOTION: "Glideaway Motion app",
    BED_TYPE_OKIN_64BIT: "Okin receiver (NORA_CON or NORACON)",
    BED_TYPE_OKIN_CB35: "Okin receiver (Sealy Posturematic and DewertOkin Star beds)",
    # Each app is its own row; this row asks which one.
    BED_TYPE_OKIN_CST: "Rize and Jordan's apps (and other Okin apps)",
    BED_TYPE_OKIN_RF_ECO_BT: "OKIN RF ECO BT stair lift",
    # Protocol-based types (Leggett & Platt family)
    BED_TYPE_LEGGETT_GEN2: "LP Control and LP Comfort Connect (Leggett & Platt Gen2)",
    BED_TYPE_LEGGETT_LP_LEGACY: "L&P Adjustable Base app (older version)",
    BED_TYPE_LEGGETT_OKIN: (
        "Leggett & Platt Okin (Prodigy CE, Prodigy 2, Prodigy 2L, U Series and LP Control apps, "
        "requires pairing)"
    ),
    BED_TYPE_LEGGETT_WILINKE: "Leggett & Platt MlRM remote",
    # Brand-specific types
    BED_TYPE_BEDTECH: "BedTech app (newer app)",
    BED_TYPE_COOLBASE: "Cool Base app",
    BED_TYPE_ERGOMOTION: "Ergomotion remote",
    BED_TYPE_ERGOMOTION_4: "Ergomotion 4.0 app",
    BED_TYPE_JIECANG: "Glide and Comfort Motion remotes (Jiecang)",
    BED_TYPE_JIECANG_APP: (
        "Jiecang: ERGOBALANCE, Dream Motion, Dream Motion HD and Comfort Motion apps, "
        "Glide and Lierda remotes"
    ),
    BED_TYPE_JENSEN: "Jensen Adjustable Sleep app, JMC400 bed",
    BED_TYPE_KEESON: (
        "Keeson (Member's Mark, Purple, Sleep Harmony and Linx / Juna Sleep apps, "
        "some Ergomotion Sync beds)"
    ),
    BED_TYPE_RIZE: "Rize Beds app",
    BED_TYPE_ISLEEP: "ISleep app",
    BED_TYPE_KOMFYD: "KomfyD app",
    BED_TYPE_COMFYDS: "ComfyDS app",
    BED_TYPE_KAIDI: "Rize app (older version)",
    BED_TYPE_LINAK: "Linak (Bed Control, Bed Connect and Performance Series apps)",
    BED_TYPE_AMBIENT: "M3 Ambient app",
    BED_TYPE_VINDO: "Vindö (Carpe Diem Beds)",
    BED_TYPE_MALOUF_LEGACY_OKIN: "Malouf remote, older receiver",
    BED_TYPE_MALOUF_NEW_OKIN: "Malouf remote, newer receiver",
    "bedgear": "Bedgear app",
    "l2motion": "L2 Motion app",
    BED_TYPE_ERGOBED: "ErgoBed Control app",
    BED_TYPE_MOODBASE: "MoodBase app",
    BED_TYPE_MOTOSLEEP: "MotoSleep / Power Bob app",
    BED_TYPE_RONCO_MOTION: "Ronco Motion app (ECONOMY / PREMIUM)",
    BED_TYPE_OCTO: "OCTO Smart Control",
    BED_TYPE_REVERIE: "Reverie app",
    BED_TYPE_REVERIE_NIGHTSTAND: "Reverie Nightstand app",
    BED_TYPE_REVERIE_PAIRLINK: "Reverie Pairlink (R510L / Harmoniq)",
    BED_TYPE_ATLAS_LIFT: "Atlas Lift app (Cama Lift)",
    BED_TYPE_RICHMAT: "Richmat / RMControl app",
    BED_TYPE_RONDURE: "1500 Tilt Base (Rondure)",
    BED_TYPE_REMACRO: "Slumberland app (Remacro)",
    BED_TYPE_COMFORT_MOTION: "Comfort Motion and Lierda remotes",
    BED_TYPE_LIMOSS: "Limoss and Stawett remotes",
    BED_TYPE_LIMOSS_REMOTE: "Limoss Remote app",
    BED_TYPE_SILVERMOTION: "SILVERmotion Android (LOGICDATA)",
    BED_TYPE_LOGICDATA: "Logicdata SimplicityFrame (SILVERmotion)",
    BED_TYPE_LOGICDATA_APP: "MOTIONrelax and Sleep Smart apps (LOGICDATA)",
    BED_TYPE_LOGICDATA_AIR_PUMP: "Logicdata Sleep Smart air mattress pump",
    BED_TYPE_MALOUF_APP: "Malouf Base / Lucid Base apps",
    BED_TYPE_SCOTT_LIVING: "Scott Living",
    BED_TYPE_SLEEP_NUMBER: "Sleep Number Fuzion (Climate 360, FlexFit)",
    BED_TYPE_SLEEP_NUMBER_MCR: "Sleep Number older base (i8, 360 FlexFit 2)",
    BED_TYPE_SLEEPSTAR: "SleepSpa S9000AI (SLEEPSTAR)",
    BED_TYPE_SLEEPYS_BOX15: "Sleepy's Elite BOX15 receiver",
    BED_TYPE_SLEEPYS_BOX24: "Sleepy's Elite BOX24 receiver",
    BED_TYPE_SLEEPYS_BOX25: "Sleepy's Elite BOX25 receiver",
    BED_TYPE_SLEEPYS_ELITE_APP: "MFRM Sleepy's Elite app",
    BED_TYPE_STAR_ELEVATE: "DewertOkin Elevate lift (two motors)",
    BED_TYPE_SOLACE: "Solace (HomeKobo, Sealy MotionFlex and Sweet Night apps)",
    BED_TYPE_SUTA: "SUTA Smart Home app",
    BED_TYPE_TRUEMOTION: "trueMotion app",
    BED_TYPE_SUTA_KING_KOIL: "King Koil (SUTA) app",
    "paramount": "Paramount Bed Operation (ベッド操作)",
    BED_TYPE_BEDJET_POWERLAYER: "BedJet PowerLayer adjustable frame",
    BED_TYPE_SVANE: "Svane Remote app",
    BED_TYPE_TIMOTION_AHF: "TiMOTION AHF",
    BED_TYPE_VIBRADORM: "Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic",
    BED_TYPE_VIBRADORM_APP: "Vibradorm apps: VMAT, Caresse Diamant or Werkmeister",
    BED_TYPE_VMATBASIC: "V-MAT Basic app",
    BED_TYPE_STARCODE_ABM5_4: "AdjustableM5X4 app",
    BED_TYPE_MOTION_BED: "Motion Bed app",
    BED_TYPE_DOUBLESLEEP: "OKIN SleepEase (DoubleSleep / XiaoBao)",
    BED_TYPE_SLEEPTRACKER: "Tempur Sleeptracker-AI (ProSmart, ActiveBreeze)",
    # Diagnostic
    # Kept in the list: a discovered bed nothing supports can still be added to
    # capture a support bundle (#385).
    BED_TYPE_DIAGNOSTIC: "Unsupported bed (diagnostics only)",
}


def is_jensen_linon_name(name: str | None) -> bool:
    """Return True for names the Jensen app drives with its LinOn profile."""
    lowered = (name or "").lower()
    return any(pattern in lowered for pattern in JENSEN_LINON_NAME_PATTERNS)


# Apps chosen by a protocol variant, listed as their own bed-type choices so
# users find them by app name. A bed type's own entry names the app its auto
# variant selects; see AGENTS.md "Adding a New Bed Type".
APP_VARIANT_CHOICES: dict[tuple[str, str], str] = {
    (BED_TYPE_LINAK, LINAK_VARIANT_AA_CONTROL_MY_BED): "AA Control My Bed app",
    (BED_TYPE_LINAK, LINAK_VARIANT_CARPE_DIEM): "Carpe Diem Beds app",
    (BED_TYPE_DORSAL, DORSAL_ROOMI_S655_PLUS): DORSAL_ROUTES[DORSAL_ROOMI_S655_PLUS],
    **{("majestichome", profile): f"Majestic Home ({label})" for profile, label in MAJESTICHOME_PROFILES.items()},
    **{("richmat_sleep_receiver", app): f"{label} separate sleep receiver"
       for app, label in (("wsilver2", "W.Silver Products"), ("americanstar", "AMERICANSTAR"),
                          ("bailey2", "Bailey's Bed Control"), ("tx", "TX"))},
    **{(BED_TYPE_MLILY0, profile): f"MLILY 3.1.1 ({label})" for profile, label in MLILY0_PROFILES.items()},
    **{(BED_TYPE_MLILY_REMOTE, profile): f"MLILY Remote ({label})" for profile, label in MLILY_REMOTE_PROFILES.items()},
    **{(BED_TYPE_MLILY, profile): f"MLILY Control ({label})" for profile, label in MLILY_PROFILES.items()},
    **{(BED_TYPE_OKIMIKI, profile): f"Okimiki ({label})" for profile, label in OKIMIKI_PROFILES.items()},
    **{("bobpowerbase", profile): label for profile, label in BOB_PROFILES.items()},
    **{(BED_TYPE_GALAXY, profile): f"Galaxy Bed Control ({label})" for profile, label in GALAXY_PROFILES.items()},
    **{(BED_TYPE_GOODVIBE, profile): f"Good Vibe Sleep ({label})" for profile, label in GOODVIBE_PROFILES.items()},
    **{(BED_TYPE_ESHINE_OKIN, profile): f"eShine app ({label})" for profile, label in ESHINE_OKIN_PROFILES.items()},
    **{(BED_TYPE_RICHMAT_CLASSIC_APPS, app): f"{label} app" for app, label in RICHMAT_CLASSIC_APPS.items()},
    # The current L&P Adjustable Base app, told apart from its older version's row.
    (BED_TYPE_RICHMAT_CLASSIC_APPS, "homezone"): "Home Zone Adjustable app",
    (BED_TYPE_RICHMAT_CLASSIC_APPS, "lp2"): "L&P Adjustable Base app (newer version)",
    **{(BED_TYPE_RICHMAT_APP_SLEEP, profile): f"Richmat app sleep sensor ({label})" for profile, label in RICHMAT_SLEEP_CHOICES.items()},
    **{(BED_TYPE_MYSIDE, product): f"My Side ({label})" for product, label in MYSIDE_PRODUCTS.items()},
    **{(BED_TYPE_RICHMAT_APP, profile): f"Richmat app ({label})" for profile, label in RICHMAT_APP_PRODUCTS.items()},
    **{(BED_TYPE_HJBED, profile): f"HJBed app ({label})" for profile, label in HJBED_PROFILES.items()},
    **{(BED_TYPE_GLIDEAWAY_MOTION, model): f"Glideaway Motion app ({label.replace(' (', ', ').rstrip(')')})"
       for model, label in GLIDEAWAY_MOTION_MODELS.items()},
    (BED_TYPE_KAIDI, KAIDI_VARIANT_FLOYD): "Floyd Home app",
    (BED_TYPE_KEESON, KEESON_VARIANT_ADJUSTABLE_LITE): "Adjustable Lite app",
    (BED_TYPE_KEESON, KEESON_VARIANT_SIMON_LI): "Simon Li app",
    (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT): "Heal Every Night app",
    (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_SEATING): "OKIN-Seating app",
    (BED_TYPE_KEESON, KEESON_VARIANT_AVANTI_BASES): "Avanti Bases app",
    (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_COMFORT_BED): "OKIN Comfort Bed app",
    (BED_TYPE_KEESON, KEESON_VARIANT_COMFORTFURNITURE): "ComfortFurniture app",
    (BED_TYPE_KEESON, KEESON_VARIANT_ORE_ULTRAMATIC): "Ultramatic app",
    (BED_TYPE_KEESON, KEESON_VARIANT_LEVA_SLEEP): "Leva Sleep app",
    (BED_TYPE_KEESON, KEESON_VARIANT_AMERICANSTAR): "AMERICANSTAR app (Keeson)",
    (BED_TYPE_KEESON, KEESON_VARIANT_BEDSENSE_BASES): "Bedsense Bases app",
    (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA): "INNOVA app",
    (BED_TYPE_KEESON, KEESON_VARIANT_MAXCOIL_UNA): "MaxCoil Una app",
    (BED_TYPE_KEESON, KEESON_VARIANT_DYNASTY_BASES): "Dynasty Bases app",
    (BED_TYPE_KEESON, KEESON_VARIANT_RESTONIC_A): "Restonic BT app, remote A",
    (BED_TYPE_KEESON, KEESON_VARIANT_RESTONIC_B): "Restonic BT app, remote B",
    (BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA): "Woosa Sleep app",
    (BED_TYPE_SOLACE, SOLACE_VARIANT_SOPHIE): "Sophie app",
    (BED_TYPE_SOLACE, SOLACE_VARIANT_FLEXIREST): "Sealy FlexiRest app",
    # Each Okin CST app is its own row.
    **{
        (BED_TYPE_OKIN_CST, variant): label
        for variant, label in OKIN_CST_VARIANTS.items()
        if variant != VARIANT_AUTO
    },
    (BED_TYPE_SVANE, SVANE_VARIANT_JMC): "Svane Remote app (JMC400)",
    (BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON): "Jensen Adjustable Sleep app (LinOn)",
    (BED_TYPE_STAR_ELEVATE, STAR_ELEVATE_VARIANT_M1X12): "Adjustable Comfort M1X12 app, Elevate lift",
    (BED_TYPE_REMACRO, REMACRO_VARIANT_THE_BRICK): "The Brick app (Remacro)",
    (BED_TYPE_REMACRO, REMACRO_VARIANT_JEROMES): "Jerome's app (Remacro)",
    (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z230): "Customatic Z-Series app (Z-230)",
    (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280): "Customatic Z-Series app (Z-280)",
}
_CHOICE_SEPARATOR = ":"


def keeson_variant_from_device_name(device_name: str | None) -> str | None:
    """Return the existing generic KSBT transport selected by auto configuration."""
    name = (device_name or "").lower()
    if name.startswith("ksbt03cr"):
        return KEESON_VARIANT_KSBT_CR
    if name.startswith("ksbt04c") or name == "smart_dfu":
        return KEESON_VARIANT_KSBT04C
    if name.startswith("ksbt"):
        return KEESON_VARIANT_KSBT
    return None


def bed_type_choice(bed_type: str, variant: str | None) -> str:
    """Return the selector value for a bed type and variant: its app entry if any."""
    if variant is not None and (bed_type, variant) in APP_VARIANT_CHOICES:
        return f"{bed_type}{_CHOICE_SEPARATOR}{variant}"
    return bed_type


def resolve_bed_type_choice(choice: str) -> tuple[str, str | None]:
    """Return the bed type and, for an app entry, the variant it selects."""
    bed_type, separator, variant = choice.partition(_CHOICE_SEPARATOR)
    if separator and (bed_type, variant) in APP_VARIANT_CHOICES:
        return bed_type, variant
    return choice, None


def bed_type_label(bed_type: str | None) -> str:
    """Return the friendly label of a bed type, including one no list offers."""
    if bed_type is None:
        return ""
    if (label := BED_TYPE_DISPLAY_NAMES.get(bed_type)) is not None:
        return label
    return _UNLISTED_LABELS.get(bed_type, bed_type)


# A bed type the lists do not offer is still named where a bed's setup is shown.
_UNLISTED_LABELS: Final[dict[str, str]] = {
    BED_TYPE_LEGGETT_PLATT: "Gen2 or MlRM, found automatically (Leggett & Platt)",
}


# One Restonic BT row: its follow-up asks the remote style the app's settings chose.
_APP_ROW_LABELS: Final[dict[tuple[str, str], str]] = {
    (BED_TYPE_KEESON, KEESON_VARIANT_RESTONIC_A): "Restonic BT app",
}
# The Z-Series models are answers of the Customatic question.
_HIDDEN_APP_ROWS: Final = frozenset(
    {
        (BED_TYPE_KEESON, KEESON_VARIANT_RESTONIC_B),
        (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z230),
        (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280),
        # The Svane Remote JMC400 profile and the Jensen app's LinOn profile
        # are answers of the Jensen / Svane question.
        (BED_TYPE_SVANE, SVANE_VARIANT_JMC),
        (BED_TYPE_SVANE, SVANE_VARIANT_JENSEN_LINON),
        # The Remacro apps are answers of the Remacro question.
        (BED_TYPE_REMACRO, REMACRO_VARIANT_THE_BRICK),
        (BED_TYPE_REMACRO, REMACRO_VARIANT_JEROMES),
        # The classic Richmat apps are answers of the Richmat question.
        *((BED_TYPE_RICHMAT_CLASSIC_APPS, app) for app in RICHMAT_CLASSIC_APPS),
        # The Good Vibe Sleep products and HJBed products are answers of
        # their app's own question, behind one row each.
        *((BED_TYPE_GALAXY, product) for product in GALAXY_PROFILES),
        *((BED_TYPE_GOODVIBE, product) for product in GOODVIBE_PROFILES),
        *((BED_TYPE_MLILY, product) for product in MLILY_PROFILES),
        *(("majestichome", product) for product in MAJESTICHOME_PROFILES),
        *((BED_TYPE_OKIMIKI, product) for product in OKIMIKI_PROFILES),
        *(("bobpowerbase", product) for product in BOB_PROFILES),
        *((BED_TYPE_MLILY0, product) for product in MLILY0_PROFILES),
        *((BED_TYPE_MLILY_REMOTE, product) for product in MLILY_REMOTE_PROFILES),
        *((BED_TYPE_HJBED, product) for product in HJBED_PROFILES),
        *((BED_TYPE_MYSIDE, product) for product in MYSIDE_PRODUCTS),
        *((BED_TYPE_RICHMAT_APP, product) for product in RICHMAT_APP_PRODUCTS),
        *((BED_TYPE_RICHMAT_APP_SLEEP, product) for product in RICHMAT_SLEEP_CHOICES),
    }
)
# Configure still accepts a hidden app row by its value, as a repair submits it.
HIDDEN_APP_CHOICES: Final = frozenset(bed_type_choice(*row) for row in _HIDDEN_APP_ROWS)
# Bed types whose one row asks for the product, although each product is an app entry.
PRODUCT_QUESTION_BED_TYPES: Final = frozenset(
    {
        BED_TYPE_ALYA, BED_TYPE_RONCO_MOTION, BED_TYPE_AMBIENT, BED_TYPE_RESTONIC, BED_TYPE_FLEXISPOT, "kingkoil", BED_TYPE_ENSO2, BED_TYPE_LIKIMIO, "dreamsense", "saatva", "majestichome", BED_TYPE_LEVA, BED_TYPE_LINX, BED_TYPE_SOMOS, "bobpowerbase", BED_TYPE_COMFORT_ENHANCEMENT3, BED_TYPE_SYMPHONY_SLEEP, BED_TYPE_YAMADA, BED_TYPE_MYSIDE, BED_TYPE_RICHMAT_APP, BED_TYPE_RICHMAT_APP_SLEEP, BED_TYPE_GALAXY, BED_TYPE_MLILY, BED_TYPE_MLILY0, BED_TYPE_MLILY_REMOTE, BED_TYPE_OKIMIKI, "luuna", BED_TYPE_GOODVIBE, BED_TYPE_HJBED, BED_TYPE_CASPER_BASE, BED_TYPE_COMFORT_ENHANCEMENTS, BED_TYPE_COMFORTBASE, "sleep_evolution", "wsilver_legacy", "personal_comfort", "instant_comfort"}
).union({BED_TYPE_BETTERLIVING2, BED_TYPE_JEROME_ADJUSTABLE_BASE, BED_TYPE_SLEEPTIME, "sealy_posturematic"})
# Routes named after their protocol, not an app or brand. They stay off the
# bed-type list and are reached through detection, the brand list and Configure.
PROTOCOL_ROUTES: Final = frozenset(
    {
        BED_TYPE_OKIN_64BIT,
        BED_TYPE_OKIN_7BYTE,
        BED_TYPE_OKIN_CB35,
        BED_TYPE_OKIN_FFE,
        BED_TYPE_OKIN_HANDLE,
        BED_TYPE_OKIN_NORDIC,
        BED_TYPE_OKIN_ORE,
    }
)


def get_bed_type_options() -> list[SelectOptionDict]:
    """Get bed type and app choices sorted alphabetically by label.

    A bed type whose variant has no automatic choice is offered only through
    its app entries, unless its row asks for the product. Each family has one
    row that opens its family step; the routes behind it stay selectable there.
    Protocol-named routes are not listed.
    """
    choices = {
        bed_type: family_row_label(bed_type) or label
        for bed_type, label in BED_TYPE_DISPLAY_NAMES.items()
        if (bed_type not in VARIANT_REQUIRED_BED_TYPES or bed_type in PRODUCT_QUESTION_BED_TYPES)
        and bed_type not in FAMILY_STEP_ROUTES
        and bed_type not in PROTOCOL_ROUTES
    }
    choices.update(
        {
            bed_type_choice(*key): _APP_ROW_LABELS.get(key, label)
            for key, label in APP_VARIANT_CHOICES.items()
            if key not in _HIDDEN_APP_ROWS
        }
    )
    # A family with many apps also lists each app by its own name, so a search
    # finds it; the row still opens the family question with that app chosen.
    for bed_type, variant in family_member_rows():
        choice = bed_type_choice(bed_type, variant)
        if choice not in choices:
            label = (
                APP_VARIANT_CHOICES.get((bed_type, variant)) if variant is not None else None
            ) or BED_TYPE_DISPLAY_NAMES[bed_type]
            choices[choice] = label
    return [
        SelectOptionDict(value=value, label=label)
        for value, label in sorted(choices.items(), key=lambda item: item[1].lower())
    ]


def _uuid_from_gatt_object(item: Any) -> str | None:
    """Return a normalized UUID from a Bleak object, dataclass, or dict."""
    uuid = item.get("uuid") if isinstance(item, dict) else getattr(item, "uuid", None)
    return str(uuid).lower() if uuid is not None else None


def _characteristics_from_gatt_service(service: Any) -> list[Any]:
    """Return characteristic-like objects from a Bleak service, dataclass, or dict."""
    characteristics = (
        service.get("characteristics")
        if isinstance(service, dict)
        else getattr(service, "characteristics", None)
    )
    return list(characteristics or [])


def _is_leggett_okin_name(device_name: str | None) -> bool:
    """Return whether a BLE name identifies LP Control's Okin protocol."""
    normalized_name = (device_name or "").strip().lower()
    return _is_lp_control_okin_name(device_name) or any(
        pattern in normalized_name for pattern in LEGGETT_OKIN_NAME_PATTERNS if pattern != "lp bed"
    )


def _is_lp_control_okin_name(device_name: str | None) -> bool:
    """Return whether a BLE name matches LP Control's proven Okin prefix."""
    return (device_name or "").strip().lower().startswith("lp bed")


def detect_bed_type_from_gatt_services(
    gatt_services: Any,
    device_name: str | None = None,
) -> DetectionResult:
    """Detect a bed/profile from connected GATT services.

    This is intentionally limited to signatures that are not safe to infer from
    advertisements alone. Generic OKIN names remain ambiguous until a connected
    service/characteristic signature is available.
    """
    service_uuids: set[str] = set()
    characteristic_uuids: set[str] = set()

    for service in gatt_services or []:
        if service_uuid := _uuid_from_gatt_object(service):
            service_uuids.add(service_uuid)
        for char in _characteristics_from_gatt_service(service):
            if char_uuid := _uuid_from_gatt_object(char):
                characteristic_uuids.add(char_uuid)

    has_okin_uuid_write = (
        OKIMAT_SERVICE_UUID.lower() in service_uuids
        and OKIMAT_WRITE_CHAR_UUID.lower() in characteristic_uuids
    )
    has_smart_remote_css = (
        OKIN_SMART_REMOTE_CSS_SERVICE_UUID.lower() in service_uuids
        and OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID.lower() in characteristic_uuids
    )
    has_dewertokin_rf_gateway = (
        DEWERTOKIN_RF_GATEWAY_SERVICE_UUID.lower() in service_uuids
        and DEWERTOKIN_RF_GATEWAY_DEVICE_NAME_CHAR_UUID.lower() in characteristic_uuids
    )
    has_nordic_dfu = NORDIC_DFU_SERVICE_UUID.lower() in service_uuids

    if has_dewertokin_rf_gateway:
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_HANDLE,
            confidence=0.9,
            signals=[
                "gatt_service:dewertokin_rf_gateway",
                "gatt_char:dewertokin_rf_gateway_name",
            ],
        )

    if has_okin_uuid_write and _is_lp_control_okin_name(device_name):
        # LP Control classifies these receivers as Okin from 62741523 alone
        # and sends 6-byte 04 02 frames to 62741525. Some LP BED CONTROL
        # receivers also expose the CSS and Nordic DFU services, but the app
        # ignores those services; their presence is not proof of CST (#368).
        return DetectionResult(
            bed_type=BED_TYPE_LEGGETT_OKIN,
            confidence=0.95,
            signals=[
                "gatt_service:okin_uuid",
                "gatt_char:okin_write",
                "name:leggett_okin",
            ],
        )

    if has_okin_uuid_write and has_smart_remote_css:
        signals = [
            "gatt_service:okin_uuid",
            "gatt_char:okin_write",
            "gatt_service:okin_smart_remote_css",
            "gatt_char:okin_smart_remote_css_write",
        ]
        if has_nordic_dfu:
            return DetectionResult(
                bed_type=BED_TYPE_OKIN_CST,
                confidence=0.8,
                signals=[*signals, "gatt_service:nordic_dfu"],
                ambiguous_types=[BED_TYPE_OKIN_7BYTE, BED_TYPE_OKIN_RF_ECO_BT, BED_TYPE_FURNIMOVE],
            )

        return DetectionResult(
            bed_type=BED_TYPE_OKIN_RF_ECO_BT,
            confidence=0.6,
            signals=signals,
            ambiguous_types=[BED_TYPE_FURNIMOVE],
        )

    return DetectionResult(bed_type=None, confidence=0.0, signals=[])


def refine_malouf_protocol_from_gatt(bed_type: str, gatt_services: Any) -> str:
    """Correct Malouf/Lucid family protocol once connected GATT services are known."""
    if bed_type not in {BED_TYPE_MALOUF_NEW_OKIN, BED_TYPE_MALOUF_LEGACY_OKIN}:
        return bed_type

    characteristic_uuids: set[str] = set()
    for service in gatt_services or []:
        for char in _characteristics_from_gatt_service(service):
            if char_uuid := _uuid_from_gatt_object(char):
                characteristic_uuids.add(char_uuid)

    has_new_okin_write = MALOUF_NEW_OKIN_WRITE_CHAR_UUID.lower() in characteristic_uuids
    has_legacy_okin_write = MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID.lower() in characteristic_uuids

    if bed_type == BED_TYPE_MALOUF_NEW_OKIN and has_legacy_okin_write and not has_new_okin_write:
        return BED_TYPE_MALOUF_LEGACY_OKIN
    if bed_type == BED_TYPE_MALOUF_LEGACY_OKIN and has_new_okin_write and not has_legacy_okin_write:
        return BED_TYPE_MALOUF_NEW_OKIN

    return bed_type


def is_okimat_bed_model(ble_model: str | None) -> bool:
    """Return True when Device Info identifies a multi-motor OKIMAT bed actuator.

    OKIMAT bed actuators (e.g. ``OKIMAT 4 IPS/M`` from issue #406) expose the same
    OKIN write + Smart-Remote-CSS GATT signature as the ELDA single-actuator stair
    (issue #344, ``MEGAMAT MBZ``). The connected Device Information model is the
    only reliable way to tell a full bed apart from the niche stair profile.
    """
    return "okimat" in (ble_model or "").strip().lower()


def _is_rf_eco_bt_stair_model(ble_model: str | None) -> bool:
    """Return True when Device Info identifies the known RF ECO BT stair."""
    return (ble_model or "").strip().lower() == "megamat mbz"


def refine_okin_shared_uuid_protocol_from_gatt(
    bed_type: str,
    gatt_services: Any,
    protocol_variant: str | None = None,
    ble_model: str | None = None,
    device_name: str | None = None,
    *,
    _log_correction: bool = True,
) -> str:
    """Correct shared OKIN UUID profiles once connected GATT services are known."""
    if bed_type not in OKIN_SHARED_UUID_GATT_REFINABLE_TYPES:
        return bed_type

    gatt_detection = detect_bed_type_from_gatt_services(gatt_services, device_name)
    if gatt_detection.bed_type in {
        BED_TYPE_LEGGETT_OKIN,
        BED_TYPE_OKIN_CST,
        BED_TYPE_OKIN_RF_ECO_BT,
    }:
        if gatt_detection.bed_type == BED_TYPE_LEGGETT_OKIN:
            if bed_type != BED_TYPE_LEGGETT_OKIN and _log_correction:
                _LOGGER.info(
                    "Refined shared OKIN protocol from %s to %s using LP Control "
                    "device identity and GATT signals: %s",
                    bed_type,
                    BED_TYPE_LEGGETT_OKIN,
                    ", ".join(gatt_detection.signals),
                )
            return BED_TYPE_LEGGETT_OKIN
        if _is_rf_eco_bt_stair_model(ble_model):
            if bed_type != BED_TYPE_OKIN_RF_ECO_BT and _log_correction:
                _LOGGER.info(
                    "Refined shared OKIN protocol from %s to %s using stair model %r",
                    bed_type,
                    BED_TYPE_OKIN_RF_ECO_BT,
                    ble_model,
                )
            return BED_TYPE_OKIN_RF_ECO_BT
        if (
            gatt_detection.bed_type
            in {
                BED_TYPE_OKIN_CST,
                BED_TYPE_OKIN_RF_ECO_BT,
            }
            and bed_type in {BED_TYPE_OKIN_UUID}
            and protocol_variant in OKIMAT_VARIANTS
            and protocol_variant != VARIANT_AUTO
        ):
            # RF ECO BT is a receiver family, not a topology: the two-motor
            # installation in #344 reports that generic model while using the
            # standard Okin UUID transport selected by its 82620 handset code.
            # A validated explicit remote is stronger evidence than shared GATT.
            if _log_correction:
                _LOGGER.info(
                    "Keeping %s profile for explicitly configured Okin remote %s "
                    "despite shared OKIN GATT detection %s and model %r",
                    bed_type,
                    protocol_variant,
                    gatt_detection.bed_type,
                    ble_model,
                )
            return bed_type
        if gatt_detection.bed_type in {
            BED_TYPE_OKIN_CST,
            BED_TYPE_OKIN_RF_ECO_BT,
        } and is_okimat_bed_model(ble_model):
            # Full OKIMAT beds share the CSS GATT inventory used to infer both
            # profiles, so the Device Info model is the stronger signal (#406).
            if bed_type in OKIMAT_COMPATIBLE_PROFILES:
                # Already on an OKIMAT-compatible controller; keep the saved label
                # (BED_TYPE_OKIN_UUID/OKIN_UUID resolve to the same controller, and
                # OKIN CST is its own deliberately preserved full-bed profile).
                if _log_correction:
                    _LOGGER.debug(
                        "Keeping %s profile for OKIMAT bed model %r despite shared OKIN GATT signals",
                        bed_type,
                        ble_model,
                    )
                return bed_type
            # Any other shared-UUID guess — a persisted RF ECO BT stair entry, or
            # an incompatible profile such as Nectar / OKIN 7-byte / Leggett OKIN —
            # is the wrong controller for an OKIMAT bed. Promote it to the
            # multi-motor OKIN UUID profile so the bed recovers (issue #406).
            if _log_correction:
                _LOGGER.info(
                    "Promoted %s to %s for OKIMAT bed model %r despite shared OKIN GATT signals",
                    bed_type,
                    BED_TYPE_OKIN_UUID,
                    ble_model,
                )
            return BED_TYPE_OKIN_UUID
        if {bed_type, gatt_detection.bed_type} == {
            BED_TYPE_OKIN_CST,
            BED_TYPE_OKIN_RF_ECO_BT,
        }:
            # CSS and Nordic DFU overlap across these profiles. GATT can narrow
            # the family but cannot safely override the configured choice.
            return bed_type
        if gatt_detection.bed_type == BED_TYPE_OKIN_CST:
            # CSS plus Nordic DFU is only a hint. No CST app identifies its
            # product from GATT, names or Device Information in the Rize apps, and
            # OKIMAT beds expose the same services (#555). CST stays opt-in.
            return bed_type
        if gatt_detection.bed_type != bed_type and _log_correction:
            _LOGGER.info(
                "Refined shared OKIN protocol from %s to %s using GATT signals: %s",
                bed_type,
                gatt_detection.bed_type,
                ", ".join(gatt_detection.signals),
            )
        return gatt_detection.bed_type

    return bed_type


def refine_okin_dot_protocol_from_gatt(bed_type: str, gatt_services: Any) -> str:
    """Promote Okimat entries connected to DOT PROTOCOL boxes to okin_dot.

    DOT boxes (RF1058/RF34/RF6707 handsets) are CB24-family receivers: they
    expose the Nordic UART write characteristic and no Okin 62741523 service.
    An Okimat/Okin UUID entry pointed at such a box can never work over the
    Okimat transport, so persist the corrected bed type — this also drops the
    pairing requirement, which DOT boxes don't have (FurniMove flags DOT the
    same way, by the presence of its CB24_WRITE_CHARACTERISTIC).
    """
    if bed_type not in (BED_TYPE_OKIN_UUID,) or not gatt_services:
        return bed_type

    service_uuids: set[str] = set()
    characteristic_uuids: set[str] = set()
    for service in gatt_services:
        if service_uuid := _uuid_from_gatt_object(service):
            service_uuids.add(service_uuid)
        for char in _characteristics_from_gatt_service(service):
            if char_uuid := _uuid_from_gatt_object(char):
                characteristic_uuids.add(char_uuid)

    has_okimat_write = (
        OKIMAT_SERVICE_UUID.lower() in service_uuids
        and OKIMAT_WRITE_CHAR_UUID.lower() in characteristic_uuids
    )
    has_nordic_uart_write = (
        NORDIC_UART_SERVICE_UUID.lower() in service_uuids
        and NORDIC_UART_WRITE_CHAR_UUID.lower() in characteristic_uuids
    )
    if has_nordic_uart_write and not has_okimat_write:
        _LOGGER.info(
            "Promoted %s to %s: connected box exposes Nordic UART and no Okin "
            "62741523 service (DOT PROTOCOL receiver)",
            bed_type,
            BED_TYPE_OKIN_DOT,
        )
        return BED_TYPE_OKIN_DOT

    return bed_type


def refine_dewertokin_star_protocol_from_name(
    bed_type: str,
    device_name: str | None,
) -> str:
    """Correct CB35/BOX25 entries from the protocol digits in a Star name.

    ``Star35...`` identifies CB35 while ``Star25...`` identifies BOX25.  Both
    families can report ``STAR`` in Device Information characteristic 0x2A29;
    the M1X12 app uses that value to select StarCode framing, not to distinguish
    CB35 from BOX25.  Treating it as a CB35 discriminator caused a correctly
    discovered Star25 entry to be overwritten on every connection (issue #413).
    """
    if bed_type not in {BED_TYPE_OKIN_CB35, BED_TYPE_SLEEPYS_BOX25}:
        return bed_type

    normalized_name = (device_name or "").strip().lower()
    if normalized_name.startswith("star25"):
        return BED_TYPE_SLEEPYS_BOX25
    if normalized_name.startswith("star35"):
        return BED_TYPE_OKIN_CB35
    return bed_type


def refine_nordic_uart_protocol_from_device_info(
    bed_type: str,
    device_name: str | None,
    ble_manufacturer: str | None,
    ble_model: str | None,
) -> str:
    """Correct Nordic UART profiles when Device Info identifies a NORA controller."""
    if bed_type not in {
        BED_TYPE_RICHMAT,
        BED_TYPE_OKIN_NORDIC,
        BED_TYPE_OKIN_64BIT,
    }:
        return bed_type

    has_nora_name = _is_nora_controller_identifier(device_name)
    has_nora_model = _is_nora_controller_identifier(ble_model)
    has_idt_manufacturer = (ble_manufacturer or "").strip().lower() == "idt"
    if not (has_nora_model or (has_nora_name and has_idt_manufacturer)):
        return bed_type

    if bed_type != BED_TYPE_OKIN_64BIT:
        _LOGGER.info(
            "Refined Nordic UART protocol from %s to %s using Device Info "
            "(name=%s, manufacturer=%s, model=%s)",
            bed_type,
            BED_TYPE_OKIN_64BIT,
            device_name,
            ble_manufacturer,
            ble_model,
        )
    return BED_TYPE_OKIN_64BIT


def refine_qrrm_protocol_from_device_info(
    bed_type: str,
    device_name: str | None,
    ble_model: str | None,
) -> str:
    """Disambiguate QRRM BedTech and Richmat controllers by exact WLT model.

    The confirmed BedTech BT3000 from issue #410 and Casper/Richmat HJC27 from
    issue #300 share the QRRM name family, FEE9 GATT layout, and WLT
    manufacturer. Their vendor models differ by the Richmat controller's ``_S``
    suffix, so only these observed exact models are safe correction signals.
    """
    if bed_type not in {BED_TYPE_BEDTECH, BED_TYPE_RICHMAT}:
        return bed_type
    if not (device_name or "").strip().casefold().startswith("qrrm"):
        return bed_type

    normalized_model = (ble_model or "").strip().casefold()
    corrected_bed_type = {
        "wlt825x_h35": BED_TYPE_BEDTECH,
        "wlt825x_h35_s": BED_TYPE_RICHMAT,
    }.get(normalized_model)
    if corrected_bed_type is None:
        return bed_type

    if corrected_bed_type != bed_type:
        _LOGGER.info(
            "Refined QRRM protocol from %s to %s using Device Info model %s",
            bed_type,
            corrected_bed_type,
            ble_model,
        )
    return corrected_bed_type


def detect_bed_type(service_info: BluetoothServiceInfoBleak) -> str | None:
    """Detect the bed type a nearby device would be offered as.

    Returns:
        The detected bed type constant, or None if not detected.
        For detailed detection with confidence scores, use detect_new_bed().
    """
    result = detect_new_bed(service_info)
    if result.bed_type in (BED_TYPE_RONCO_MOTION, BED_TYPE_AMBIENT, BED_TYPE_ATLAS_LIFT, BED_TYPE_LIKIMIO, "dorsal", BED_TYPE_SIMMONS_BLUE, "sleep_assistant", BED_TYPE_SLEEP_ASSIST_PRO, "super_colchones", "bobpowerbase", BED_TYPE_GALAXY, BED_TYPE_GOODVIBE, BED_TYPE_MLILY, BED_TYPE_MLILY0, BED_TYPE_MLILY_REMOTE, BED_TYPE_MOTOMOTION, BED_TYPE_N32_MOTION_BED, BED_TYPE_SYMPHONY, BED_TYPE_MLINE, BED_TYPE_OKIMIKI) and result.confidence < 0.7:
        return None  # An app name hint requires an explicit product choice.
    return result.bed_type


def detect_new_bed(service_info: BluetoothServiceInfoBleak) -> DetectionResult:
    """Detect a device not yet set up, which may not be a bed at all.

    A shared service alone never identifies a bed: a device with nothing else
    needs a name, which the non-bed exclusions have checked, and is uncertain.
    A configured bed's route is reviewed with detect_bed_type_detailed().
    """
    # The SmartBed app's headboards. Only a new setup is offered them, so a bed
    # already set up on another route is not asked to change.
    if (service_info.name or "").startswith(("Headboard126", "Headboard265")):
        return DetectionResult("smartbed", 0.9, ["name:smartbed_headboard"])
    first = first_pass(service_info)
    result = _detect_with_first_pass(service_info, first)
    service_uuids = [str(uuid).lower() for uuid in service_info.service_uuids or ()]
    if result.bed_type is not None and _rests_on_shared_service(service_uuids, first, result):
        if is_mac_like_name(service_info.name):
            if "app_hint:ergobed" in result.signals:
                return DetectionResult(BED_TYPE_ERGOBED, 0.3, ["app_hint:ergobed"])
            return DetectionResult(None, 0.0, ["shared_service:no_name"])
        result.confidence = min(result.confidence, 0.5)
        result.signals.append("shared_service:no_name_match")
    if result.bed_type == "smartbed" and "name:shuda_app_candidate" in result.signals:
        # Nordic's shared company ID and service cannot tell these apps apart.
        result.confidence = min(result.confidence, 0.6)
    local_name = getattr(getattr(service_info, "advertisement", None), "local_name", None)
    if relax_motion_matches(local_name, service_info.service_uuids or ()):
        # Apps with different model gates share this service, so a new setup
        # asks which app runs the bed. A configured bed is reviewed as before.
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "relax_motion"]))
        result.signals.append("service:relax_motion_app_candidate")
        result.confidence = min(result.confidence, 0.5)
    platform_name = getattr(getattr(service_info, "device", None), "name", None)
    if (
        isinstance(platform_name, str)
        and platform_name.lower().startswith(CUSTOMATIC_DEMO_NAME_PREFIX)
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # Independence has the shared Okin prefix, never a unique receiver identity.
        result.ambiguous_types = list(dict.fromkeys([
            *(result.ambiguous_types or ()), BED_TYPE_CUSTOMATIC_DEMO,
        ]))
        result.signals.append("name:customatic_demo_app_candidate")
    return result


def detect_bed_type_detailed(service_info: BluetoothServiceInfoBleak) -> DetectionResult:
    """Detect a bed type with its confidence, signals and alternative app candidates."""
    # The first pass matches the declared discovery hints, as the manifest does.
    return _detect_with_first_pass(service_info, first_pass(service_info))


def _detect_with_first_pass(
    service_info: BluetoothServiceInfoBleak, first: FirstPass
) -> DetectionResult:
    """Offer Good Vibe Sleep without changing an existing receiver/app choice."""
    identity = (getattr(service_info, "service_data", None) or {}).get(
        ERGOBQ_IDENTITY_SERVICE, b""
    )
    if ergobq_product(identity, service_info.name) is not None:
        return DetectionResult("ergobq", 0.99, ["service_data:ergobq_bed"])
    result = _detect_bed_type_with_app_candidates(service_info, first)
    from .profiles.ronco_motion import accepts_name as ronco_name

    if ronco_name(service_info.name or "") and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_RONCO_MOTION, 0.3, result.signals)
        elif result.bed_type != BED_TYPE_RONCO_MOTION:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_RONCO_MOTION]))
        result.signals.append("name:ronco_motion_app_candidate")
    # CONTROL_BOX is the app's scan filter. It cannot identify the receiver or layout.
    if first.name(BED_TYPE_AMBIENT) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        signal = "app_hint:ambient"
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_AMBIENT, 0.3, [*result.signals, signal])
        else:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_AMBIENT]))
            result.signals.append(signal)
    # King Koil uses this scan prefix without a name-selected product layout.
    if first.name(BED_TYPE_SUTA_KING_KOIL) and not any(
        signal.startswith("excluded:") or signal == "name:suta_accessory"
        for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SUTA_KING_KOIL, 0.3, result.signals)
        elif result.bed_type != BED_TYPE_SUTA_KING_KOIL:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_SUTA_KING_KOIL]))
        result.signals.append("app_hint:suta_king_koil")
    # The scan name chooses a trueMotion layout after explicit app selection.
    # It is shared with the SUTA receiver route and supplies no receiver evidence.
    if first.name(BED_TYPE_TRUEMOTION) and not any(
        signal.startswith("excluded:") or signal == "name:suta_accessory"
        for signal in result.signals
    ):
        signal = "app_hint:truemotion"
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_TRUEMOTION, 0.3, [*result.signals, signal])
        else:
            result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_TRUEMOTION]
            result.signals.append(signal)
    from .profiles.sleep_assistant import discovered as sleep_assistant_discovered
    if sleep_assistant_discovered(service_info.name or ""):
        if result.bed_type is None:
            result = DetectionResult("sleep_assistant", 0.3, ["name:sleep_assistant_candidate"])
        elif result.bed_type != "sleep_assistant":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "sleep_assistant"]))
            result.signals.append("name:sleep_assistant_candidate")
    from .profiles.sleep_assist_pro import route_for_id

    if route_for_id(service_info.name) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        signal = "app_hint:sleep_assist_pro"
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SLEEP_ASSIST_PRO, 0.3, [*result.signals, signal])
        elif result.bed_type != BED_TYPE_SLEEP_ASSIST_PRO:
            result.ambiguous_types = [
                *(result.ambiguous_types or ()), BED_TYPE_SLEEP_ASSIST_PRO
            ]
            result.signals.append(signal)
    if first.name(BED_TYPE_FLEXISPOT):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_FLEXISPOT, 0.3, ["name:flexispot_app_candidate"])
        elif result.bed_type != BED_TYPE_FLEXISPOT:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_FLEXISPOT]))
            result.signals.append("name:flexispot_app_candidate")
    # The current Linx scan filter is a case-sensitive substring, not a model
    # or service selector. Preserve existing receiver detection as an alternative.
    if isinstance(service_info.name, str) and "KSWF07D" in service_info.name:
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_LINX, 0.3, ["name:linx_app_candidate"])
        elif result.bed_type != BED_TYPE_LINX:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_LINX]))
            result.signals.append("name:linx_app_candidate")
    if REMACRO_SERVICE_UUID in {
        uuid.lower() for uuid in service_info.service_uuids or ()
    } and cheerssleep_advertisement(service_info.manufacturer_data or {}):
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "cheerssleep"]))
        result.signals.append("manufacturer:cheerssleep_model_candidate")
    # Dawn House scans case-sensitive substrings, without a service filter.
    if any(name in (service_info.name or "") for name in ("KSWF07S", "KSWF19S")):
        if result.bed_type is None:
            result = DetectionResult("agingplace", 0.3, ["name:agingplace", *result.signals])
        elif result.bed_type != "agingplace":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "agingplace"]))
            result.signals.append("name:agingplace")
    # The app's scan filter is wider than the manifest gate, so it refines
    # advertisements another matcher admitted; it declares no hint of its own.
    if galaxy_scan_matches(service_info.name) and result.bed_type != BED_TYPE_GALAXY and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_GALAXY, 0.3, ["name:galaxy_app_candidate", *result.signals])
        else:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_GALAXY]))
            result.signals.insert(0, "name:galaxy_app_candidate")
    if goodvibe_scan_matches(service_info.name) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        hints = ["name:goodvibe_app_candidate"]
        if suggested := goodvibe_suggested_profile(service_info.name):
            hints.append("goodvibe_profile:" + suggested)
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_GOODVIBE, 0.3, [*hints, *result.signals])
        elif result.bed_type is not None and result.bed_type != BED_TYPE_GOODVIBE:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_GOODVIBE]))
            result.signals[0:0] = hints
    # The app's shared base services offer a candidate, never a route or
    # capabilities for an existing Malouf/Reverie entry.
    from .codec.personal_comfort import V1_SERVICE, bluetooth_uuid, reverie_uuid
    from .profiles.personal_comfort import air_route

    pc_services = {uuid.lower() for uuid in (service_info.service_uuids or ())}
    pc_candidate = air_route(service_info.name or "", pc_services) is not None or bool(
        pc_services & {bluetooth_uuid("fee9"), "fee9", V1_SERVICE, reverie_uuid("db801000")}
    )
    if not pc_candidate:
        if result.bed_type == "personal_comfort":
            result = DetectionResult(None, 0, ["personal_comfort:no_matching_air_service"])
        elif result.ambiguous_types:
            result.ambiguous_types = [key for key in result.ambiguous_types if key != "personal_comfort"]
    # Shared services do not weaken an existing receiver/app identity or an
    # explicit accessory exclusion. Personal Comfort remains selectable in setup.
    if pc_candidate and result.bed_type is None and not any(
        signal.startswith("excluded:") or signal == "name:suta_accessory"
        for signal in result.signals
    ):
        result = DetectionResult("personal_comfort", 0.3, ["personal_comfort:app_candidate", *result.signals])
    # Instant Comfort runs the same air units and bases, so it is offered beside them.
    if pc_candidate and not any(
        signal.startswith("excluded:") or signal == "name:suta_accessory"
        for signal in result.signals
    ):
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "instant_comfort"]))
    # Resident's platform-name filter admits these shared receiver names. Keep
    # existing protocol detection and ask the user to identify the app.
    device_name = getattr(getattr(service_info, "device", None), "name", None)
    platform_name = device_name if isinstance(device_name, str) and device_name else service_info.name
    # This app checks the first manufacturer VALUE, without a company-id gate.
    # Its shared name/UART route offers an explicit app choice, never an ORE alias.
    manufacturer_value = next(iter((service_info.manufacturer_data or {}).values()), b"")
    if (
        isinstance(platform_name, str) and platform_name.lower().startswith("smartbed")
        and manufacturer_value.startswith(bytes.fromhex("44 4f 54 01 05"))
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        if result.bed_type is None:
            result = DetectionResult("ultramatic_smart_bed", 0.3, ["name:ultramatic_app_candidate"])
        elif result.bed_type != "ultramatic_smart_bed":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "ultramatic_smart_bed"]))
            result.signals.append("name:ultramatic_app_candidate")
    if (
        isinstance(platform_name, str)
        and platform_name.lower().startswith(("okin", "smartbed"))
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_RESIDENT, 0.3, [*result.signals, "name:resident_app_candidate"])
        elif result.bed_type != BED_TYPE_RESIDENT:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_RESIDENT]))
            result.signals.append("name:resident_app_candidate")
    if (
        isinstance(platform_name, str) and platform_name.lower().startswith("okin")
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # Jobs' shared platform-name rule offers an app, never identifies it.
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_JOBS]))
        result.signals.append("name:jobs_app_candidate")
    if (
        isinstance(service_info.name, str)
        and service_info.name.lower().startswith("smartbed")
        and result.confidence < 0.8
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # Offer the shared name only when there is no confident receiver match.
        # It cannot select Rize Home or a product, or question a proven receiver.
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_RIZE_HOME, 0.3, ["name:rize_home_app_candidate"])
        elif result.bed_type != BED_TYPE_RIZE_HOME:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_RIZE_HOME]))
            result.signals.append("name:rize_home_app_candidate")
    if (
        isinstance(platform_name, str) and platform_name.lower().startswith("okin")
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # Name-only acceptance in the app proves a candidate, never hardware identity.
        result.ambiguous_types = list(dict.fromkeys([
            *(result.ambiguous_types or ()), BED_TYPE_RIZE_REMEDY_II,
        ]))
        result.signals.append("name:rize_remedy_ii_app_candidate")
    if (
        isinstance(platform_name, str) and platform_name.startswith(("Smartbed", "BLE"))
        and (
            "00001000-0000-1000-8000-00805f9b34fb" if platform_name.startswith("BLE")
            else "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
        ) in {u.lower() for u in (service_info.service_uuids or ())}
        and result.confidence < 0.8
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # The app's broad name scan chooses transport, not hardware identity.
        # Require the selected route as corroboration; names alone stay manual.
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SUPERIOR_SLEEP, 0.3, ["name:superior_sleep_app_candidate"])
        elif result.bed_type != BED_TYPE_SUPERIOR_SLEEP:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_SUPERIOR_SLEEP]))
            result.signals.append("name:superior_sleep_app_candidate")
    # The Shuda app uses a shared name and UART route. Neither identifies it.
    if (
        isinstance(device_name, str)
        and device_name.lower().startswith("smartbed")
        and first.service(BED_TYPE_SHUDA)
        and result.confidence < 0.8
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        result.ambiguous_types = list(dict.fromkeys([
            *(result.ambiguous_types or ()), BED_TYPE_SHUDA,
        ]))
        result.signals.append("name:shuda_app_candidate")
    # A shared service makes this app a choice, never overrides a stronger
    # receiver signature and never infers a remote from the Bluetooth name.
    if OKIMAT_SERVICE_UUID.lower() in {u.lower() for u in (service_info.service_uuids or ())} and not any(
        signal.startswith("excluded:") for signal in result.signals
    ) and result.bed_type != BED_TYPE_COMFORT_ENHANCEMENT3:
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_COMFORT_ENHANCEMENT3]))
        result.signals.append("service:comfort_enhancement3_candidate")
    if isinstance(platform_name, str) and platform_name.lower().startswith(SIMMONS_BLUE_PREFIX) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        # SmartBed is shared across several apps, so the name can only offer a choice.
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SIMMONS_BLUE, 0.3, ["name:simmons_blue_app_candidate"])
        elif result.bed_type != BED_TYPE_SIMMONS_BLUE:
            result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_SIMMONS_BLUE]
            result.signals.append("name:simmons_blue_app_candidate")
    from .profiles.sleeptime import select as sleeptime_selector

    # The stock picker names a layout but the shared UART does not identify the app.
    if (
        isinstance(platform_name, str)
        and sleeptime_selector(platform_name) is not None
        and result.confidence < 0.8
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SLEEPTIME, 0.3, ["name:sleeptime_app_candidate"])
        elif result.bed_type != BED_TYPE_SLEEPTIME:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_SLEEPTIME]))
            result.signals.append("name:sleeptime_app_candidate")
    # These shared app names are candidates only. Never replace a confident
    # receiver signature or infer N32 from the Nordic service alone.
    if (isinstance(platform_name, str)
        and platform_name.lower().startswith(("smartbed", "n32 motionbed"))
        and result.confidence < 0.7
        and not any(signal.startswith("excluded:") for signal in result.signals)):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_N32_MOTION_BED, 0.3, ["name:n32_app_candidate"])
        elif result.bed_type != BED_TYPE_N32_MOTION_BED:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_N32_MOTION_BED]))
            result.signals.append("name:n32_app_candidate")
    # This app's scan substrings offer a choice, never a receiver or product identity.
    if first.name("silksnow") and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult("silksnow", 0.3, [*result.signals, "name:silksnow_app_candidate"])
        elif result.bed_type != "silksnow":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "silksnow"]))
            result.signals.append("name:silksnow_app_candidate")
    if first.name(BED_TYPE_MLILY0) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_MLILY0, 0.3, [*result.signals, "name:mlily0_app_candidate"])
        elif result.bed_type != BED_TYPE_MLILY0:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_MLILY0]))
            result.signals.append("name:mlily0_app_candidate")
    if mlily_scan_matches(service_info.name) and mlily_suggested_profile(service_info.name) and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_MLILY, 0.3, ["name:mlily_app_candidate", *result.signals])
        elif result.bed_type != BED_TYPE_MLILY:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_MLILY]))

    if okimiki_scan_matches(service_info.name) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_OKIMIKI, 0.3, ["name:okimiki_app_candidate"])
        elif result.bed_type != BED_TYPE_OKIMIKI:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_OKIMIKI]))
            # Keep established receiver/name evidence in its existing priority.
            result.signals.insert(0, "name:okimiki_app_candidate")

    from .profiles.symphony import scan_matches as symphony_scan_matches

    # Shared app keywords must not question an established receiver signature.
    if result.confidence < 0.8 and symphony_scan_matches(platform_name or "", service_info.manufacturer_data or {}) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SYMPHONY, 0.3, [*result.signals, "name:symphony_app_candidate"])
        elif result.bed_type != BED_TYPE_SYMPHONY:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_SYMPHONY]))
            result.signals.append("name:symphony_app_candidate")
    # A shared name must not question a corroborated receiver signature.
    if (result.confidence < 0.85 and isinstance(platform_name, str)
        and platform_name.lower().startswith(("okin-ble", "smartbed"))
        and not any(signal.startswith("excluded:") for signal in result.signals)):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_YAMADA, 0.3, ["name:yamada_app_candidate"])
        elif result.bed_type != BED_TYPE_YAMADA:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_YAMADA]))
            result.signals.append("name:yamada_app_candidate")
    # A shared phone-app scan prefix never becomes a competing recommended
    # receiver. It offers the explicit app only when no receiver is identified.
    if (result.bed_type is None and isinstance(platform_name, str)
        and platform_name.lower().startswith(("okin", "smartbed"))
        and not any(signal.startswith("excluded:") for signal in result.signals)):
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_BETTERLIVING2]))
        result.signals.append("name:betterliving2_app_candidate")
    # BERUN shares receiver names with other apps, so offer an app candidate.
    if (isinstance(platform_name, str) and platform_name.lower().startswith(("okin", "smartbed"))
        and not any(signal.startswith("excluded:") for signal in result.signals)
        and result.bed_type != "berun"):
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "berun"]))
        result.signals.append("name:berun_app_candidate")
    # Nerum's names overlap existing receivers. Offer explicit app selection.
    if (result.confidence < 0.85 and isinstance(platform_name, str)
        and platform_name.lower().startswith(("okin", "smartbed"))
        and not any(signal.startswith("excluded:") for signal in result.signals)):
        if result.bed_type is None:
            result = DetectionResult("nerum", 0.3, ["name:nerum_app_candidate"])
        elif result.bed_type != "nerum":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "nerum"]))
    if first.name("kingkoil") and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult("kingkoil", 0.3, [*result.signals, "name:kingkoil_app_candidate"])
        elif result.bed_type != "kingkoil":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "kingkoil"]))
    if first.name(BED_TYPE_SOMOS) and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_SOMOS, 0.3, [*result.signals, "name:somos_app_candidate"])
        elif result.bed_type != BED_TYPE_SOMOS:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_SOMOS]))
    # Shared names and a write-carrier advertisement offer a choice only.
    if (result.confidence < 0.8 and first.service("sinca_comfort") and sinca_scan_name(platform_name or "")
        and not any(signal.startswith("excluded:") for signal in result.signals)):
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "sinca_comfort"]))
        result.signals.append("name_service:sinca_comfort_app_candidate")
    # Dorsal's scan words are shared and do not identify the selected project.
    if first.name("dorsal") and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult(
                "dorsal", 0.3, [*result.signals, "name:dorsal_app_candidate"],
                ambiguous_types=result.ambiguous_types,
            )
        else:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "dorsal"]))
            result.signals.append("name:dorsal_app_candidate")
    # Shared names offer the app; they never replace a stronger receiver match.
    if first.name(BED_TYPE_MLINE) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_MLINE, 0.3, [*result.signals, "name:mline_app_candidate"])
        elif result.bed_type != BED_TYPE_MLINE:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_MLINE]))
            result.signals.append("name:mline_app_candidate")
    if set(SAATVA_SCAN_UUIDS).intersection(uuid.lower() for uuid in service_info.service_uuids or ()) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult("saatva", 0.3, [*result.signals, "service:saatva_app_candidate"])
        elif result.bed_type != "saatva":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "saatva"]))
            result.signals.append("service:saatva_app_candidate")
    if first.name("dreamsense") and not any(signal.startswith("excluded:") for signal in result.signals):
        if result.bed_type is None:
            result = DetectionResult("dreamsense", 0.3, ["name:dreamsense_app_candidate"])
        elif result.bed_type != "dreamsense":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "dreamsense"]))
    if first.name(BED_TYPE_LIKIMIO) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_LIKIMIO, 0.3, ["name:likimio_app_candidate"])
        elif result.bed_type != BED_TYPE_LIKIMIO:
            result.ambiguous_types = list(
                dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_LIKIMIO])
            )
    # Bob's shared scan words are an opt-in app choice, after established
    # receiver and app-name priorities, with the same exclusion boundary.
    if service_info.name and any(word in service_info.name for word in BOB_SCAN_KEYWORDS) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult("bobpowerbase", 0.3, ["name:bobpowerbase_app_candidate"])
        elif result.bed_type != "bobpowerbase":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "bobpowerbase"]))
    local_name = advertised_local_name(service_info)
    if (
        isinstance(local_name, str)
        and ATLAS_LIFT_NAME_HINT.matches_name(local_name)
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # QRRM is shared. Keep Atlas Lift available as an explicit app choice.
        if result.bed_type is None:
            result.bed_type, result.confidence = BED_TYPE_ATLAS_LIFT, 0.3
        else:
            result.ambiguous_types = list(
                dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_ATLAS_LIFT])
            )
        result.signals.append("name:atlas_lift_app_candidate")
    if (
        getattr(service_info, "advertisement", None) is not None
        and ergobed_eligible(local_name)
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # Keep a raw-name-only match visible in setup at app-choice confidence.
        if result.bed_type is None:
            result.bed_type = BED_TYPE_ERGOBED
            result.confidence = 0.3
        else:
            result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_ERGOBED]
        result.signals.append("app_hint:ergobed")
    return result


def _detect_bed_type_with_app_candidates(
    service_info: BluetoothServiceInfoBleak, first: FirstPass
) -> DetectionResult:
    """Keep existing receiver detection while offering an explicit app candidate."""
    result = _detect_bed_type_detailed(service_info, first=first)
    # The Casper Base sensor classifier uses case-sensitive startsWith. Its
    # names never outrank a bed's own service or the non-bed exclusions, and
    # where another sleep module shares the name the user chooses.
    casper = next(
        (key for key in (BED_TYPE_CASPER_SLEEP_MM, BED_TYPE_CASPER_SLEEP_SXB) if first.name(key)),
        None,
    )
    if casper is not None and result.confidence < 0.7 and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        shared = any(
            isinstance(hint, NameHint) and hint.bed_types - {casper} for hint in first.hints
        )
        if result.bed_type is None:
            result.bed_type, result.confidence = casper, 0.3 if shared else 0.9
        elif result.bed_type != casper:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), casper]))
        result.signals.append("name:casper_base_sleep_sensor")
    if first.name("super_colchones") and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result.bed_type, result.confidence = "super_colchones", 0.3
        elif result.bed_type != "super_colchones":
            result.ambiguous_types = list(dict.fromkeys([
                *(result.ambiguous_types or ()), "super_colchones",
            ]))
        result.signals.append("name:super_colchones_app_candidate")
    if sealy_name(service_info.name or "") and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result.bed_type, result.confidence = "sealy_posturematic", 0.3
        elif result.bed_type != "sealy_posturematic":
            result.ambiguous_types = list(dict.fromkeys([
                *(result.ambiguous_types or ()), "sealy_posturematic",
            ]))
        result.signals.append("name:sealy_posturematic_app_candidate")
    # A name-only app hint must not contest an existing Richmat receiver signature.
    if first.name(BED_TYPE_RICHMAT) and not first.service(BED_TYPE_RICHMAT) and not any(
        (service_info.name or "").lower().startswith(pattern)
        for pattern in LEGGETT_RICHMAT_NAME_PATTERNS
    ) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        # Luuna's scan keywords identify a family candidate, never its product.
        if result.bed_type is None:
            result.bed_type, result.confidence = BED_TYPE_RICHMAT, 0.3
        elif (
            result.confidence < 0.9
            and result.bed_type != BED_TYPE_RICHMAT
            and BED_TYPE_RICHMAT not in (result.ambiguous_types or ())
        ):
            result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_RICHMAT]
        result.signals.append("name:richmat_app_candidate")
    if first.name(BED_TYPE_GMMOTOR) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None and not any(
            (service_info.name or "").lower().startswith(pattern)
            for pattern in LEGGETT_RICHMAT_NAME_PATTERNS
        ):
            result.bed_type = "gmmotor"
            result.confidence = 0.6
        elif result.bed_type != "gmmotor":
            result.ambiguous_types = [
                *(result.ambiguous_types or ()),
                *([] if "gmmotor" in (result.ambiguous_types or ()) else ["gmmotor"]),
            ]
        result.signals.append("name:gmmotor_app_candidate")
    if first.name(BED_TYPE_GMMOTOR_SLEEP_MM):
        # GM's input-name classifier owns the session mode. The shared scan
        # keywords identify candidates; they cannot identify this companion app.
        hints = ["gmmotor_sleep_mm", "gmmotor_sleep_sxb"]
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), *hints]))
        result.signals.append("name:gmmotor_sleep_app_candidate")
    # FurniMove accepts this gateway service last, after its manufacturer and
    # 1523 service predicates, and without a payload mask. It names an app
    # candidate, never a handset or layout, so any other match keeps priority.
    if first.service(BED_TYPE_FURNIMOVE):
        if result.bed_type is None:
            if not any(signal.startswith("excluded:") for signal in result.signals):
                return DetectionResult(
                    bed_type=BED_TYPE_FURNIMOVE,
                    confidence=0.6,
                    signals=["uuid:furnimove_gateway"],
                    ambiguous_types=[BED_TYPE_OKIN_HANDLE],
                )
        elif result.bed_type != BED_TYPE_FURNIMOVE:
            if BED_TYPE_FURNIMOVE not in (result.ambiguous_types or ()):
                result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_FURNIMOVE]
            result.signals.append("uuid:furnimove_gateway")
    if result.bed_type is not None and first.name(BED_TYPE_STARCODE_ABM5_4):
        candidates = list(result.ambiguous_types or ())
        if BED_TYPE_STARCODE_ABM5_4 not in candidates:
            candidates.append(BED_TYPE_STARCODE_ABM5_4)
        result.ambiguous_types = candidates
        # Shared app transports require a choice; unrelated private UUIDs retain
        # their receiver confidence even when the advertisement name starts Star.
        advertised_services = {uuid.lower() for uuid in (service_info.service_uuids or [])}
        if any(role.service.lower() in advertised_services for role in STARCODE_ABM5_4_TRANSPORTS.values()):
            result.confidence = min(result.confidence, 0.65)
        result.signals.append("name:starcode_abm5_4_app_candidate")
    if "Smartbed" in (service_info.name or ""):
        # App candidate only. Shared names cannot identify the product selector.
        if result.bed_type is None:
            if not any(signal.startswith("excluded:") for signal in result.signals):
                return DetectionResult(
                    bed_type=BED_TYPE_ESHINE_OKIN, confidence=0.3,
                    signals=[*result.signals, "name:eshine_okin_app_candidate"],
                )
        elif result.bed_type != BED_TYPE_ESHINE_OKIN:
            result.ambiguous_types = list(dict.fromkeys([
                *(result.ambiguous_types or ()), BED_TYPE_ESHINE_OKIN,
            ]))
            result.signals.append("name:eshine_okin_app_candidate")
    # The five classic apps' scan names are package-local layout codes, wider
    # than any manifest matcher, so they only add an app candidate.
    name = service_info.name
    if name and richmat_classic_matching_apps(
        name, tuple(uuid.lower() for uuid in service_info.service_uuids or ())
    ) and name.upper()[:4] not in ("TEST", "RMCS"):
        from .profiles import maxprime

        if (
            result.bed_type is None
            and not any(signal.startswith("excluded:") for signal in result.signals)
            and maxprime.scan_matches(name)
            and any(uuid.lower() in maxprime.RECEIVER_SERVICES for uuid in service_info.service_uuids)
        ):
            result = DetectionResult(
                BED_TYPE_RICHMAT_CLASSIC_APPS, 0.3, result.signals,
                ambiguous_types=result.ambiguous_types,
            )
        if result.bed_type is not None and result.bed_type != BED_TYPE_RICHMAT_CLASSIC_APPS:
            if BED_TYPE_RICHMAT_CLASSIC_APPS not in (result.ambiguous_types or ()):
                result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_RICHMAT_CLASSIC_APPS]
        result.signals.append("name:richmat_classic_app_candidate")
    # App name rules add candidates without replacing an existing route.
    # Each app reads the exact name, not a normalized shared prefix.
    if (accepts_sophie_name(service_info.name) or accepts_flexirest_name(service_info.name)) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(bed_type=BED_TYPE_SOLACE, confidence=0.3,
                signals=list(result.signals))
        elif result.bed_type != BED_TYPE_SOLACE:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_SOLACE]))
        if accepts_sophie_name(service_info.name):
            result.signals.append("name:sophie_app_candidate")
        if accepts_flexirest_name(service_info.name):
            result.signals.append("name:flexirest_app_candidate")
    if bedgear_eligible(service_info.name) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(
                bed_type="bedgear", confidence=0.3,
                signals=[*result.signals, "name:bedgear_app_candidate"],
                ambiguous_types=result.ambiguous_types,
            )
        elif result.bed_type != "bedgear":
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "bedgear"]))
            result.signals.append("name:bedgear_app_candidate")
    if bedgear_eligible(service_info.name) and not any(signal.startswith("excluded:") for signal in result.signals):
        # Identical scan grammar is only an app candidate, never permission to
        # run L2 Motion's independently declared controls on another route.
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), "l2motion"]))
        result.signals.append("name:l2motion_app_candidate")
        if result.bed_type == BED_TYPE_MOTOSLEEP and "name:motosleep" in result.signals:
            # The exact name grammar also belongs to L2 Motion. A name alone
            # cannot select which app's independently proven controls to run.
            result.confidence = min(result.confidence, 0.6)
    if (
        first.name(BED_TYPE_MOODBASE)
        and bedgear_eligible(service_info.name)
        and not any(signal.startswith("excluded:") for signal in result.signals)
    ):
        # The app lists a name-only match, while FFE0 corroborates only its shared carrier.
        result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_MOODBASE]))
        result.signals.append("name:moodbase_app_candidate")
        if moodbase_receiver_hint(service_info.name, service_info.service_uuids):
            result.signals.append("service:moodbase_app_candidate")
    if motomotion_eligible(service_info.name):
        if result.bed_type is None and not any(signal.startswith("excluded:") for signal in result.signals):
            return DetectionResult(bed_type=BED_TYPE_MOTOMOTION, confidence=0.3, signals=[*result.signals, "name:motomotion_app_candidate"])
        if result.bed_type is not None and result.bed_type != BED_TYPE_MOTOMOTION:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_MOTOMOTION]))
            result.signals.append("name:motomotion_app_candidate")
    from .beds.richmat_app.catalog import scan_matches as richmat_app_scan_matches

    if first.name(BED_TYPE_RICHMAT_APP_SLEEP) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_RICHMAT_APP_SLEEP, 0.3, ["name:richmat_sleep_candidate"])
        elif result.bed_type != BED_TYPE_RICHMAT_APP_SLEEP:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_RICHMAT_APP_SLEEP]))

    if first.name(BED_TYPE_MYSIDE) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_MYSIDE, 0.3, ["name:myside_candidate"])
        elif result.bed_type != BED_TYPE_MYSIDE:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_MYSIDE]))
            result.signals.append("name:myside_candidate")
    if richmat_app_scan_matches(service_info.name) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        if result.bed_type is None:
            result = DetectionResult(BED_TYPE_RICHMAT_APP, 0.3, ["name:richmat_app_candidate"])
        elif result.bed_type != BED_TYPE_RICHMAT_APP:
            result.ambiguous_types = list(dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_RICHMAT_APP]))
            result.signals.append("name:richmat_app_candidate")

    if first.name(BED_TYPE_JEROME_ADJUSTABLE_BASE) and result.bed_type == BED_TYPE_RICHMAT:
        # The scan substrings are shared. Offer the app without selecting it or a product.
        result.ambiguous_types = list(
            dict.fromkeys([*(result.ambiguous_types or ()), BED_TYPE_JEROME_ADJUSTABLE_BASE])
        )

    from .profiles.enso2 import admitted_name as enso2_name

    if first.name(BED_TYPE_ENSO2) and enso2_name(service_info.name) and not any(
        signal.startswith("excluded:") for signal in result.signals
    ):
        signal = "name:enso2_app_candidate"
        if result.bed_type is None:
            result = DetectionResult(
                BED_TYPE_ENSO2, 0.3, [*result.signals, signal],
                ambiguous_types=result.ambiguous_types,
            )
        elif result.bed_type != BED_TYPE_ENSO2:
            result.ambiguous_types = list(dict.fromkeys(
                [*(result.ambiguous_types or ()), BED_TYPE_ENSO2]
            ))
            result.signals.append(signal)
    if first.name(BED_TYPE_HJBED):
        if result.bed_type is None:
            if not any(signal.startswith("excluded:") for signal in result.signals):
                return DetectionResult(
                    bed_type=BED_TYPE_HJBED, confidence=0.3,
                    signals=[*result.signals, "name:hjbed_app_candidate"],
                )
        elif result.bed_type != BED_TYPE_HJBED:
            if BED_TYPE_HJBED not in (result.ambiguous_types or ()):
                result.ambiguous_types = [*(result.ambiguous_types or ()), BED_TYPE_HJBED]
            result.signals.append("name:hjbed_app_candidate")
    return result


def _detect_bed_type_detailed(
    service_info: BluetoothServiceInfoBleak,
    *,
    first: FirstPass | None = None,
    _vmatbasic_checked: bool = False,
) -> DetectionResult:
    """Detect bed type from service info with detailed confidence scoring.

    Returns:
        DetectionResult with bed_type, confidence score, and detection signals.
        Use requires_characteristic_check to determine if post-connection
        detection can improve confidence (for ambiguous UUID cases).
    """
    # Handle devices that report None for service_uuids
    raw_uuids = service_info.service_uuids
    service_uuids = [str(uuid).lower() for uuid in raw_uuids] if raw_uuids else []
    if first is None:
        first = first_pass(service_info)
    if first.service("paramount"):
        return DetectionResult("paramount", 1.0, ["service:paramount_session"])
    device_name = (service_info.name or "").lower()
    signals: list[str] = []
    detected_remote = detect_richmat_remote_from_name(service_info.name)
    is_leggett_mlrm_name = any(
        device_name.startswith(pattern) for pattern in LEGGETT_RICHMAT_NAME_PATTERNS
    )
    is_richmat_named = (
        _RICHMAT_ADVERTISED_CODE.match(service_info.name or "") is not None
        or any(device_name.startswith(pattern) for pattern in RICHMAT_NAME_PATTERNS)
    ) and not is_leggett_mlrm_name

    _LOGGER.debug(
        "Detecting bed type for device %s (name: %s)",
        service_info.address,
        service_info.name,
    )
    _LOGGER.debug("  Service UUIDs: %s", service_uuids)
    _LOGGER.debug("  Manufacturer data: %s", service_info.manufacturer_data)

    # Parse Kaidi metadata up front so validated Kaidi advertisements are not
    # discarded by the generic "mouse" exclusion before protocol detection.
    kaidi_adv = extract_kaidi_advertisement(service_info.manufacturer_data)

    # The Jura TT214H BlueFrog coffee-machine dongle advertises the same 1523
    # service UUID as DewertOkin beds. Its exact model/name is authoritative
    # enough to reject before the otherwise high-confidence UUID check (#450).
    if (
        device_name in DEWERTOKIN_EXCLUDED_DEVICE_NAMES
        and DEWERTOKIN_SERVICE_UUID.lower() in service_uuids
    ):
        _LOGGER.debug(
            "Device %s excluded: known Jura BlueFrog dongle '%s' advertises "
            "the shared DewertOkin service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=None,
            confidence=0.0,
            signals=["excluded:jura_bluefrog"],
        )

    # Exclude devices that are clearly not beds based on name, but only when
    # they have generic/shared UUIDs. This preserves UUID-based detection for
    # beds with unique service UUIDs (e.g., a hypothetical "Linak Band" bed
    # with Linak's unique UUID would not be excluded by the "band" pattern).
    if _has_only_generic_uuids(service_uuids) and kaidi_adv is None:
        for pattern in EXCLUDED_DEVICE_PATTERNS:
            if pattern in device_name:
                _LOGGER.debug(
                    "Device %s excluded: name '%s' matches excluded pattern '%s' "
                    "(device has only generic UUIDs)",
                    service_info.address,
                    service_info.name,
                    pattern,
                )
                return DetectionResult(
                    bed_type=None, confidence=0.0, signals=["excluded:" + pattern]
                )

    # Priority 1: Check manufacturer data (highest confidence, unique signal)
    mfr_bed_type, mfr_confidence, mfr_id = _check_manufacturer_data(service_info.manufacturer_data)
    # A host-map record is a candidate hint, not proof of the source's first
    # raw manufacturer AD field or an exact one of its three product profiles.
    # The complete payload predicate ignores company ID, even a known family ID.
    if not _vmatbasic_checked and len(service_info.manufacturer_data or {}) == 1:
        company, payload = next(iter(service_info.manufacturer_data.items()))
        if manufacturer_payload_matches(payload):
            # The payload outranks a bare company-family hint, but not a bed
            # identified by its own service UUID or name: the same BABE record
            # is also VMAT revision-3 hardware, which stays on its controller.
            other = _detect_bed_type_detailed(
                service_info, first=first, _vmatbasic_checked=True
            )
            if other.bed_type is not None:
                other.ambiguous_types = [*(other.ambiguous_types or ()), BED_TYPE_VMATBASIC]
                other.signals.append("manufacturer:vmatbasic_conditional_record")
                return other
            return DetectionResult(
                bed_type=BED_TYPE_VMATBASIC,
                confidence=0.6,
                signals=["manufacturer:vmatbasic_conditional_record", "raw_first_ad_order:unknown"],
                manufacturer_id=company,
                requires_characteristic_check=True,
            )

    if mfr_bed_type and not _vmatbasic_checked:
        signals.append(f"manufacturer_id:{mfr_id}")
        _LOGGER.info(
            "Detected %s bed at %s (name: %s) by manufacturer ID %s",
            mfr_bed_type,
            service_info.address,
            service_info.name,
            mfr_id,
        )
        # FurniMove also accepts DewertOkin receivers, but handsets on the
        # released routes stay there; it remains an explicit app candidate.
        return DetectionResult(
            bed_type=mfr_bed_type,
            confidence=mfr_confidence,
            signals=signals,
            manufacturer_id=mfr_id,
            ambiguous_types=[BED_TYPE_FURNIMOVE] if mfr_bed_type == BED_TYPE_OKIN_HANDLE else [],
        )

    # Priority 2: Kaidi detection - manufacturer data is the primary signal.
    # The bed advertises FFC0 UUID, name "Mouselet", AND manufacturer data with
    # Company ID 0xFFFF / marker 0xC0FF.
    #
    # The 0xFFFF/0xC0FF blob is the PairLink mesh SDK transport
    # (com.pairlink.mesh_lib in the OEM APKs), which non-bed products - notably
    # BLE mesh LED controllers - also emit. An ESPHome ESP32-C6 LED controller
    # advertising a structurally valid PairLink payload was misdetected as a
    # Kaidi bed at 90% confidence (issue #417); even the OEM app's own scan
    # validation accepts that exact payload (length, sofaType 0x82 = product ID
    # 130, sane seat counts) and relies on mesh room-ID membership to filter,
    # which we cannot replicate. So the payload alone is not sufficient: require
    # a Kaidi-specific signal (Mouselet name, FFC0/mesh UUID, or Kaidi MAC OUI)
    # to corroborate before detecting.
    has_kaidi_uuid = (
        KAIDI_DISCOVERY_SERVICE_UUID.lower() in service_uuids
        or KAIDI_MESH_SERVICE_UUID.lower() in service_uuids
    )
    has_kaidi_name = any(device_name.startswith(pattern) for pattern in KAIDI_NAME_PATTERNS)
    has_kaidi_mac = any(
        service_info.address.upper().startswith(prefix) for prefix in KAIDI_MAC_PREFIXES
    )
    floyd_payload = (service_info.manufacturer_data or {}).get(0xFFFF)
    floyd_adv = extract_kaidi_advertisement({0xFFFF: floyd_payload}) if floyd_payload else None
    has_floyd_product = is_floyd_advertisement(floyd_adv) and service_info.rssi >= -92
    if kaidi_adv and not (has_kaidi_uuid or has_kaidi_name or has_kaidi_mac or has_floyd_product):
        _LOGGER.debug(
            "Ignoring PairLink-format manufacturer data for %s (name: %s): "
            "no Kaidi name, UUID, or MAC OUI to corroborate",
            service_info.address,
            service_info.name,
        )
    elif kaidi_adv:
        if has_floyd_product:
            signals.append("product:floyd_139")
        signals.append(f"manufacturer_payload:kaidi_type_{kaidi_adv.adv_type}")
        if has_kaidi_uuid:
            signals.append("uuid:kaidi")
        if has_kaidi_name:
            signals.append("name:kaidi")
        if has_kaidi_mac:
            signals.append("mac:kaidi_oui")
        confidence = 0.95 if has_kaidi_uuid else 0.9
        _LOGGER.info(
            "Detected Kaidi bed at %s (name: %s) by manufacturer data (type=%s)",
            service_info.address,
            service_info.name,
            kaidi_adv.adv_type,
        )
        return DetectionResult(
            bed_type=BED_TYPE_KAIDI,
            confidence=confidence,
            signals=signals,
            ambiguous_types=[BED_TYPE_ISLEEP, BED_TYPE_RIZE, BED_TYPE_KOMFYD, BED_TYPE_COMFYDS],
        )

    if DEWERTOKIN_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:dewertokin")
        _LOGGER.info(
            "Detected DewertOkin bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_HANDLE,
            confidence=0.9,
            signals=signals,
            ambiguous_types=[BED_TYPE_FURNIMOVE],
        )

    if DEWERTOKIN_RF_GATEWAY_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:dewertokin_rf_gateway")
        _LOGGER.info(
            "Detected DewertOkin RF-Gateway bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_HANDLE,
            confidence=0.9,
            signals=signals,
            ambiguous_types=[BED_TYPE_FURNIMOVE],
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

    # Check for Sleep Number Climate 360 / FlexFit - unique Fuzion service UUID
    if SLEEP_NUMBER_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:sleep_number")
        _LOGGER.info(
            "Detected Sleep Number bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SLEEP_NUMBER,
            confidence=1.0,
            signals=signals,
        )

    # Check for older Sleep Number BAM/MCR beds - unique MCR UART service UUID
    if SLEEP_NUMBER_MCR_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:sleep_number_mcr")
        _LOGGER.info(
            "Detected Sleep Number BAM/MCR bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SLEEP_NUMBER_MCR,
            confidence=1.0,
            signals=signals,
        )

    # Check for Jensen by name pattern (JMC400)
    if (
        any(device_name.startswith(pattern) for pattern in JENSEN_NAME_PATTERNS)
        or JENSEN_NAME_FRAGMENT in device_name
    ):
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

    if discover_doublesleep(
        getattr(getattr(service_info, "device", None), "name", None) or "",
        service_info.manufacturer_data or {},
        service_info.name,
    ):
        return DetectionResult(
            bed_type=BED_TYPE_DOUBLESLEEP,
            confidence=1.0,
            signals=["name:sleepease", "manufacturer:89"],
        )

    # Unique app processor service. Do not identify UART bases by KSSF names.
    if SLEEPTRACKER_SERVICE_UUID in service_uuids:
        return DetectionResult(
            bed_type=BED_TYPE_SLEEPTRACKER,
            confidence=1.0,
            signals=[f"uuid:{SLEEPTRACKER_SERVICE_UUID}"],
        )

    # Check for Keeson JSON/A00A protocol family (Juna Sleep, Linx, Ergo Health)
    if KEESON_JSON_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:keeson_json")
        _LOGGER.info(
            "Detected Keeson JSON/A00A bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_KEESON,
            confidence=1.0,
            signals=signals,
        )

    # Check for Vibradorm - VMAT service UUIDs (1525/1527)
    if (
        VIBRADORM_SERVICE_UUID.lower() in service_uuids
        or VIBRADORM_SECONDARY_SERVICE_UUID.lower() in service_uuids
    ):
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

    # Check for Svane / Jensen LinOn - unique service UUID (abcb)
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

    # Check for Svane / Jensen LinOn by name pattern
    # The app's exact scan names are a subset; keep the established substring
    # match so renamed beds (e.g. "Svane Bed 2") still detect as before.
    if is_svane_discovery_name(service_info.name) or any(
        pattern in device_name for pattern in SVANE_NAME_PATTERNS
    ):
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

    # Check for Remacro (Jeromes / Slumberland / The Brick) - unique service UUID (6e403587)
    # Note: Similar to Nordic UART (6e400001) but with different prefix, so unique
    if REMACRO_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:remacro")
        _LOGGER.info(
            "Detected Remacro bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_REMACRO,
            confidence=1.0,
            signals=signals,
        )

    # SUTA's scan gate is case-sensitive and independent of advertised UUIDs.
    # The nine-character UI route and full-name GATT route are resolved later.
    if (service_info.name or "").startswith("SUTA-"):
        if len(service_info.name) < 9 or service_info.name[:9] == "SUTA-DRAW":
            return DetectionResult(bed_type=None, confidence=0.0, signals=[*signals, "name:suta_accessory"])
        signals.append("name:suta")
        if SUTA_SERVICE_UUID.lower() in service_uuids:
            signals.append("uuid:suta_fff0")
        return DetectionResult(bed_type=BED_TYPE_SUTA, confidence=0.9, signals=signals)

    # Check for the BedJet PowerLayer frame. The frame and the BedJet climate
    # blower both advertise the 1000 service and only the frame exposes 1001
    # once connected, so the advertised name is the only discovery-time signal
    # that separates them. Claiming the shared UUID would offer bed setup for
    # climate units this integration cannot drive.
    if any(device_name.startswith(pattern) for pattern in BEDJET_POWERLAYER_NAME_PATTERNS):
        signals.append("name:bedjet_powerlayer")
        confidence = 0.6
        if BEDJET_ADVERTISED_SERVICE_UUID.lower() in service_uuids:
            signals.append("uuid:bedjet_1000")
            confidence = 0.9
        _LOGGER.info(
            "Detected BedJet PowerLayer at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_BEDJET_POWERLAYER,
            confidence=confidence,
            signals=signals,
        )

    # Check for Octo Star2 variant before generic Star* matching.
    if OCTO_STAR2_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:octo_star2")
        _LOGGER.info(
            "Detected Octo Star2 bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_OCTO, confidence=1.0, signals=signals)

    # SleepSpa bundles library implementations for SLEEPBT, but its application
    # model filter rejects both SLEEPBT subtypes. Do not let the shared Nordic
    # UART fallback misclassify these monitors as a generic Richmat/Keeson bed.
    if device_name.startswith("sleepbt"):
        return DetectionResult(
            bed_type=None,
            confidence=0.0,
            signals=["name:sleepbt_rejected"],
        )

    # SleepSpa S9000AI is a CB37 monitor that tunnels StarCode over Nordic UART.
    # It is distinct from direct BOX25/CB35 StarCode and from the app's rejected
    # SLEEPBT classes. The app selects single only for payload byte 6 == 0x88;
    # byte 0x86, missing data, and unknown values all select its dual fallback.
    if any(device_name.startswith(pattern) for pattern in SLEEPSTAR_NAME_PATTERNS):
        signals.append("name:sleepstar")
        has_nordic_uart = NORDIC_UART_SERVICE_UUID.lower() in service_uuids
        payload = (service_info.manufacturer_data or {}).get(SLEEPSTAR_MANUFACTURER_ID, b"")
        subtype = (
            "single"
            if len(payload) >= 7 and payload[6] == SLEEPSTAR_SINGLE_SUBTYPE
            else "dual"
            if len(payload) >= 7 and payload[6] == SLEEPSTAR_DUAL_SUBTYPE
            else "dual_fallback"
        )
        signals.append(f"sleepstar_subtype:{subtype}")
        if has_nordic_uart:
            signals.append("uuid:nordic_uart")
        if SLEEPSTAR_MANUFACTURER_ID in (service_info.manufacturer_data or {}):
            signals.append(f"manufacturer_id:{SLEEPSTAR_MANUFACTURER_ID}")

        confidence = 0.3
        if has_nordic_uart and payload:
            confidence = 0.98
        elif has_nordic_uart:
            confidence = 0.95
        elif payload:
            confidence = 0.9
        return DetectionResult(
            bed_type=BED_TYPE_SLEEPSTAR,
            confidence=confidence,
            signals=signals,
            manufacturer_id=(
                SLEEPSTAR_MANUFACTURER_ID
                if SLEEPSTAR_MANUFACTURER_ID in (service_info.manufacturer_data or {})
                else None
            ),
        )

    if (service_info.name or "").startswith("STAR25"):
        return DetectionResult(
            bed_type=BED_TYPE_SLEEPYS_BOX25,
            confidence=0.65,
            signals=[*signals, "name:starcode_bedding_app_choices"],
            ambiguous_types=[BED_TYPE_STARCODE_M5X5, BED_TYPE_STARCODE_M1X12],
        )

    # ELEVATE is a separate StarCode controller with a dedicated 0x40-0x4F
    # command range. Check it before the generic Star controller family. It is
    # the one route for both apps' ELEVATE lifts, including AdjustableM5X5
    # groups, so the app does not make this name ambiguous.
    if any(device_name.startswith(pattern) for pattern in STAR_ELEVATE_NAME_PATTERNS):
        signals.append("name:star_elevate")
        if NORDIC_UART_SERVICE_UUID.lower() in service_uuids:
            signals.append("uuid:nordic_uart")
            return DetectionResult(
                bed_type=BED_TYPE_STAR_ELEVATE,
                confidence=0.95,
                signals=signals,
            )
        return DetectionResult(
            bed_type=BED_TYPE_STAR_ELEVATE,
            confidence=0.3,
            signals=signals,
        )

    # Check for DewertOkin Star controllers - name pattern + Nordic UART service.
    # Both CB35 (Sealy Posturematic) and BOX25 Star (Sleepy's Elite) use Star* names
    # with Nordic UART. The protocol version is encoded in positions 4-5 of the name:
    #   Star35... = CB35 (protocol 35_22_01, 7-byte sequential commands)
    #   Star25... = BOX25 (protocol 25_42_02, 10-byte bitmask commands)
    # Source: com.okin.bedding.adjustbed blutter analysis; confirmed by real-world
    # device names from Discord (Star352201011800=CB35, Star254202079996=BOX25).
    # Post-connection, the adjustbed app also reads BLE characteristic 2A29
    # (Manufacturer Name): exactly "STAR" confirms CB35.
    if any(device_name.startswith(pattern) for pattern in SLEEPYS_BOX25_NAME_PATTERNS):
        signals.append("name:dewertokin_star")

        # Parse protocol version from name digits (positions 4-5 of original name)
        original_name = service_info.name or ""
        star_digits = original_name[4:6] if len(original_name) >= 6 else ""
        if star_digits:
            signals.append(f"star_digits:{star_digits}")

        has_nordic_uart = NORDIC_UART_SERVICE_UUID.lower() in service_uuids
        if has_nordic_uart:
            signals.append("uuid:nordic_uart")

        # High-confidence detection when protocol digits match a known version
        if star_digits == "35" and has_nordic_uart:
            _LOGGER.info(
                "Detected DewertOkin CB35 Star bed at %s (name: %s, digits=%s) "
                "with Nordic UART service",
                service_info.address,
                service_info.name,
                star_digits,
            )
            return DetectionResult(
                bed_type=BED_TYPE_OKIN_CB35,
                confidence=0.95,
                signals=signals,
            )

        if star_digits == "25" and has_nordic_uart:
            _LOGGER.info(
                "Detected DewertOkin BOX25 Star bed at %s (name: %s, digits=%s) "
                "with Nordic UART service",
                service_info.address,
                service_info.name,
                star_digits,
            )
            return DetectionResult(
                bed_type=BED_TYPE_SLEEPYS_BOX25,
                confidence=0.95,
                signals=signals,
            )

        # Unknown digits or no Nordic UART -- fall back to ambiguous detection
        if has_nordic_uart:
            _LOGGER.info(
                "Detected DewertOkin Star bed at %s (name: %s, digits=%s) "
                "with Nordic UART service - unknown protocol version, presenting both options",
                service_info.address,
                service_info.name,
                star_digits or "none",
            )
            return DetectionResult(
                bed_type=BED_TYPE_OKIN_CB35,
                confidence=0.65,
                signals=signals,
                ambiguous_types=[BED_TYPE_SLEEPYS_BOX25],
            )

        _LOGGER.info(
            "Detected possible DewertOkin Star bed at %s (name: %s) by name pattern only",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_CB35,
            confidence=0.3,
            signals=signals,
            ambiguous_types=[BED_TYPE_SLEEPYS_BOX25, BED_TYPE_OCTO],
        )

    # Check for TiMOTION AHF protocol by device name.
    # The protocol uses Nordic UART UUIDs, which are shared by many devices.
    if any(device_name.startswith(pattern) for pattern in TIMOTION_AHF_NAME_PATTERNS):
        signals.append("name:timotion_ahf")
        confidence = 0.3
        if TIMOTION_AHF_SERVICE_UUID.lower() in service_uuids:
            signals.append("uuid:nordic_uart")
            confidence = 0.9

        _LOGGER.info(
            "Detected TiMOTION AHF bed at %s (name: %s)%s",
            service_info.address,
            service_info.name,
            " with Nordic UART service" if confidence >= 0.9 else " by name pattern",
        )
        return DetectionResult(
            bed_type=BED_TYPE_TIMOTION_AHF,
            confidence=confidence,
            signals=signals,
        )

    # Check for Malouf/Lucid app family. Most devices advertising this UUID use
    # NEW_OKIN over Nordic UART, but Lucid L600 / OKIN-BLE BTCB controllers have
    # been observed advertising the same UUID while exposing the FFE5/FFE9 command
    # path after connection.
    if MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID.lower() in service_uuids:
        if device_name.startswith("okin-ble") and _manufacturer_data_contains_ascii(
            service_info.manufacturer_data,
            "btcb",
        ):
            signals.append("uuid:malouf_family")
            signals.append("name:okin_ble")
            signals.append("manufacturer_payload:btcb")
            _LOGGER.info(
                "Detected Malouf/Lucid FFE5 bed at %s (name: %s, BTCB payload)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(
                bed_type=BED_TYPE_MALOUF_LEGACY_OKIN,
                confidence=0.9,
                signals=signals,
                ambiguous_types=[BED_TYPE_MALOUF_NEW_OKIN],
            )

        signals.append("uuid:malouf_new_okin")
        _LOGGER.info(
            "Detected Malouf NEW_OKIN bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_MALOUF_NEW_OKIN, confidence=1.0, signals=signals)

    if _is_malouf_new_okin_smartbed_signature(
        device_name,
        service_uuids,
        service_info.manufacturer_data,
    ):
        signals.append("uuid:nordic_uart")
        signals.append("name:smartbed428")
        signals.append(f"manufacturer_id:{MANUFACTURER_ID_OKIN}")
        signals.append("manufacturer_payload:ab0102")
        _LOGGER.info(
            "Detected Malouf NEW_OKIN Smartbed at %s (name: %s) by Nordic UART "
            "Smartbed428 advertisement",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_MALOUF_NEW_OKIN,
            confidence=0.85,
            signals=signals,
            manufacturer_id=MANUFACTURER_ID_OKIN,
        )

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
        vindo = matches_vindo_advertisement(device_name, service_uuids)
        if vindo:
            signals.append("app_hint:vindo")
        return DetectionResult(
            bed_type=BED_TYPE_LINAK,
            confidence=1.0,
            signals=signals,
            ambiguous_types=[BED_TYPE_VINDO] if vindo else None,
        )

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

    # Some Okin receiver modules only advertise a local name, and sometimes
    # the generic Device Information service, until paired. They expose the
    # 62741523 service after OS-level bonding.
    if (
        any(pattern in device_name for pattern in OKIMAT_NAME_ONLY_PATTERNS)
        and set(service_uuids).issubset({DEVICE_INFO_SERVICE_UUID.lower()})
        and (
            not service_info.manufacturer_data
            or MANUFACTURER_ID_OKIN not in service_info.manufacturer_data
        )
    ):
        if service_uuids:
            signals.append("uuid:device_info")
        signals.append("name:okin_receiver")
        _LOGGER.info(
            "Detected Okin UUID bed at %s (name: %s) by receiver name",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_UUID,
            confidence=0.6,
            signals=signals,
            ambiguous_types=[
                BED_TYPE_LEGGETT_OKIN,
                BED_TYPE_OKIN_64BIT,
                BED_TYPE_OKIN_CST,
                BED_TYPE_OKIN_RF_ECO_BT,
                BED_TYPE_FURNIMOVE,
            ],
            requires_characteristic_check=True,
        )

    # Pairlink has its own private service UUID. Manufacturer prefixes are only
    # used to refine its model after the protocol has been identified.
    if REVERIE_PAIRLINK_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:reverie_pairlink")
        _LOGGER.info(
            "Detected Reverie Pairlink bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_REVERIE_PAIRLINK, confidence=1.0, signals=signals
        )

    # Check for Reverie Nightstand (Protocol 110) - more specific UUID
    if REVERIE_NIGHTSTAND_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:reverie_nightstand")
        _LOGGER.info(
            "Detected Reverie Nightstand bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_REVERIE_NIGHTSTAND, confidence=1.0, signals=signals
        )

    # Check for Logicdata SimplicityFrame (unique LogicLink UUID)
    if LOGICDATA_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:logicdata")
        _LOGGER.info(
            "Detected Logicdata bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_LOGICDATA, confidence=1.0, signals=signals)

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
        return DetectionResult(bed_type=BED_TYPE_SLEEPYS_BOX24, confidence=0.9, signals=signals)

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
        return DetectionResult(bed_type=BED_TYPE_OKIN_7BYTE, confidence=0.9, signals=signals)

    # Check for beds using OKIN service UUID (Okimat, Leggett Okin, Nectar, OKIN 64-bit)
    # Nectar is already handled above by name check
    # Use name patterns to disambiguate between Okimat and Leggett Okin
    # Note: OKIN 64-bit cannot be reliably detected without connecting
    if OKIMAT_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:okin")
        # Check for Leggett & Platt Okin by name patterns
        if _is_leggett_okin_name(device_name):
            signals.append("name:leggett")
            _LOGGER.info(
                "Detected Leggett & Platt Okin bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_LEGGETT_OKIN, confidence=0.9, signals=signals)

        # Receiver names are still ambiguous even after the shared OKIN service
        # appears, because Okimat, CST, 64-bit, and Leggett Okin can share it.
        if any(pattern in device_name for pattern in OKIMAT_NAME_ONLY_PATTERNS):
            signals.append("name:okin_receiver")
            _LOGGER.debug(
                "OKIN receiver name '%s' at %s uses shared Okin UUID. "
                "Prompting for protocol because this can be Okimat, CST, or another Okin variant.",
                service_info.name,
                service_info.address,
            )
            return DetectionResult(
                bed_type=BED_TYPE_OKIN_UUID,
                confidence=0.6,
                signals=signals,
                ambiguous_types=[
                    BED_TYPE_LEGGETT_OKIN,
                    BED_TYPE_OKIN_64BIT,
                    BED_TYPE_OKIN_CST,
                    BED_TYPE_OKIN_RF_ECO_BT,
                    BED_TYPE_FURNIMOVE,
                ],
                requires_characteristic_check=True,
            )

        # Check for Okimat-specific name patterns
        if any(pattern in device_name for pattern in OKIMAT_NAME_PATTERNS):
            signals.append("name:okimat")
            _LOGGER.info(
                "Detected Okimat bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_OKIN_UUID, confidence=0.9, signals=signals)

        # Generic OKIN-XXXXXX names are not enough to pick a protocol. They can
        # be classic Okimat 6-byte devices or Nectar-style 7-byte bases.
        if any(device_name.startswith(pattern) for pattern in OKIN_GENERIC_NAME_PATTERNS):
            signals.append("name:okin_generic")
            _LOGGER.debug(
                "Generic OKIN device name '%s' at %s uses shared Okin UUID. "
                "Prompting for protocol because this can be Okimat, Nectar, or another Okin variant.",
                service_info.name,
                service_info.address,
            )
            return DetectionResult(
                bed_type=BED_TYPE_OKIN_UUID,
                confidence=0.6,
                signals=signals,
                ambiguous_types=[
                    BED_TYPE_OKIN_7BYTE,
                    BED_TYPE_LEGGETT_OKIN,
                    BED_TYPE_OKIN_64BIT,
                    BED_TYPE_OKIN_CST,
                    BED_TYPE_OKIN_RF_ECO_BT,
                    BED_TYPE_FURNIMOVE,
                ],
                requires_characteristic_check=True,
            )

        # Fallback: default to Okimat with warning about ambiguity
        # This UUID is shared by Okimat, Leggett Okin, OKIN 64-bit, and OKIN CST
        _LOGGER.debug(
            "Okin UUID detected but device name '%s' at %s doesn't match known patterns. "
            "Defaulting to Okimat. Change to Nectar, Leggett & Platt, OKIN 64-bit, or OKIN CST in settings if needed.",
            service_info.name,
            service_info.address,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_UUID,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[
                BED_TYPE_OKIN_7BYTE,
                BED_TYPE_LEGGETT_OKIN,
                BED_TYPE_OKIN_64BIT,
                BED_TYPE_OKIN_CST,
                BED_TYPE_OKIN_RF_ECO_BT,
                BED_TYPE_FURNIMOVE,
            ],
            requires_characteristic_check=True,
        )

    # Check for BedTech before Richmat WiLinke since they share FEE9 and QRRM
    # names. Confirmed BedTech QRRM controllers advertise their MAC suffix under
    # manufacturer ID 0x4C57; confirmed Casper/Richmat QRRM RGB controllers do not.
    has_bedtech_manufacturer = BEDTECH_MANUFACTURER_ID in (
        service_info.manufacturer_data or {}
    ) and (
        device_name.startswith("qrrm")
        or any(pattern in device_name for pattern in BEDTECH_NAME_PATTERNS)
    )
    if has_bedtech_manufacturer and BEDTECH_SERVICE_UUID.lower() in service_uuids:
        signals.extend(
            [
                f"uuid:{BEDTECH_SERVICE_UUID.lower()}",
                f"manufacturer_id:{BEDTECH_MANUFACTURER_ID}",
            ]
        )
        _LOGGER.info(
            "Detected BedTech bed at %s (name: %s) by FEE9 UUID + manufacturer ID 0x%04X",
            service_info.address,
            service_info.name,
            BEDTECH_MANUFACTURER_ID,
        )
        return DetectionResult(
            bed_type=BED_TYPE_BEDTECH,
            confidence=0.95,
            signals=signals,
            manufacturer_id=BEDTECH_MANUFACTURER_ID,
        )

    # BedTech-branded names remain a strong signal even without manufacturer data.
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

    # Check for Octo by name pattern (e.g., RC2, DA1458x, etc.)
    # MUST be before Richmat WiLinke since FFE0 (W3 variant) is in both lists
    if any(device_name.startswith(pattern) for pattern in OCTO_NAME_PATTERNS):
        signals.append("name:octo")
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_OCTO, confidence=0.9, signals=signals)

    motion_name = accepts_motion_bed_name(service_info.name or "")

    # Home Assistant's Bluetooth index requires three literal leading characters,
    # so automatic discovery is limited to the accepted prefixes represented in
    # the manifest. Shared accepted app names require an explicit profile choice.
    if (
        any(device_name.startswith(pattern) for pattern in SOLACE_NAME_PATTERNS)
        or (device_name.startswith("my qms2"))
        or (SOLACE_NAME_PATTERN.fullmatch(device_name))
    ):
        motion_overlap = motion_name
        signals.append("name:solace")
        if motion_overlap:
            signals.append("name:motion_bed")
        _LOGGER.info(
            "Detected Solace bed at %s (name: %s) by accepted name route",
            service_info.address,
            service_info.name,
        )
        # Hardware-confirmed Solace names keep their confidence; Motion Bed is
        # offered as an alternative rather than forcing a chooser.
        return DetectionResult(
            bed_type=BED_TYPE_SOLACE,
            confidence=0.9,
            signals=signals,
            ambiguous_types=[BED_TYPE_MOTION_BED] if motion_overlap else None,
        )

    # Check for Solace/Octo/MotoSleep disambiguation (FFE0 UUID)
    # MUST be before Richmat WiLinke since FFE0 is in RICHMAT_WILINKE_SERVICE_UUIDS as W3
    if SOLACE_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:ffe0")
        # Limoss / Stawett use the same FFE0 UUID but are identified by name.
        if any(pattern in device_name for pattern in LIMOSS_NAME_PATTERNS):
            signals.append("name:limoss")
            _LOGGER.info(
                "Detected Limoss bed at %s (name: %s) by FFE0 UUID + name pattern",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(
                bed_type=BED_TYPE_LIMOSS,
                confidence=0.6 if matches_fsm_relax_candidate(service_info.name) else 0.9,
                signals=signals,
                ambiguous_types=[BED_TYPE_FSM_RELAX]
                if matches_fsm_relax_candidate(service_info.name)
                else [],
            )

        # MotoSleep and Power Bob use HHC names; the current MotoSleep app also
        # routes exact 28-character MOTO model names to its binary bed protocol.
        # AUDIO and MotoAMP are intentionally not bed controllers.
        if _is_motosleep_local_name(device_name):
            signals.append("name:motosleep")
            _LOGGER.info(
                "Detected MotoSleep bed at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=BED_TYPE_MOTOSLEEP, confidence=0.9, signals=signals)
        # Default to Octo for unknown FFE0 names
        _LOGGER.info(
            "Detected Octo bed at %s (name: %s) - defaulting to Octo for shared FFE0 UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OCTO,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[
                BED_TYPE_SOLACE,
                BED_TYPE_MOTOSLEEP,
                *([BED_TYPE_MOTION_BED] if motion_name else []),
            ],
        )

    # BetterLiving / related OKIN-BLE names use Keeson-Sino packet format on
    # fallback UUIDs that are otherwise shared with Richmat WiLinke (FFF0).
    # Keep this before generic Richmat WiLinke checks.
    if any(device_name.startswith(pattern) for pattern in KEESON_SINO_NAME_PATTERNS):
        matched_fallback_uuids = sorted(
            uuid for uuid in KEESON_FALLBACK_SERVICE_UUIDS if uuid in service_uuids
        )
        if matched_fallback_uuids:
            signals.append("name:keeson_sino")
            for uuid in matched_fallback_uuids:
                signals.append(f"uuid:{uuid}")
            _LOGGER.info(
                "Detected Keeson Sino bed at %s (name: %s) by name pattern + fallback UUIDs: %s",
                service_info.address,
                service_info.name,
                ", ".join(matched_fallback_uuids),
            )
            return DetectionResult(
                bed_type=BED_TYPE_KEESON,
                confidence=0.9,
                signals=signals,
            )

    # Check for Leggett & Platt MlRM variant (MlRM prefix with WiLinke UUID)
    # Must be before generic Richmat WiLinke check
    # Variant detection (mlrm) happens at controller instantiation
    if is_leggett_mlrm_name:
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
            # Some WiLinke UUIDs are shared with non-bed devices, so they are
            # only trusted when a Richmat name corroborates the match;
            # otherwise keep scanning and let detection fall through.
            guard_reason = NAME_GUARDED_WILINKE_UUIDS.get(wilinke_uuid.lower())
            if guard_reason and not is_richmat_named:
                _LOGGER.debug(
                    "Ignoring WiLinke UUID %s for %s (name: %s): %s with no "
                    "Richmat name to corroborate",
                    wilinke_uuid,
                    service_info.address,
                    service_info.name,
                    guard_reason,
                )
                continue
            signals.append("uuid:wilinke")
            # FEE9 is ambiguous - could be Richmat or BedTech
            if wilinke_uuid.lower() == BEDTECH_SERVICE_UUID.lower():
                if is_richmat_named:
                    signals.append("name:richmat")
                    _LOGGER.info(
                        "Detected Richmat WiLinke bed at %s (name: %s) by Richmat name + FEE9 UUID",
                        service_info.address,
                        service_info.name,
                    )
                    return DetectionResult(
                        bed_type=BED_TYPE_RICHMAT,
                        confidence=0.9,
                        signals=signals,
                        detected_remote=detected_remote,
                    )
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

    # Check for MotoSleep - name-based HHC and MOTO bed-controller detection.
    if _is_motosleep_local_name(device_name):
        signals.append("name:motosleep")
        _LOGGER.info(
            "Detected MotoSleep bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_MOTOSLEEP, confidence=0.9, signals=signals)

    # Check for Limoss / Stawett (TEA-encrypted protocol over shared FFE0/FFE1 UUIDs)
    # Detection relies primarily on device name because FFE0 is shared by many protocols.
    if any(pattern in device_name for pattern in LIMOSS_NAME_PATTERNS):
        signals.append("name:limoss")
        confidence = 0.3
        _LOGGER.info(
            "Detected Limoss bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_LIMOSS,
            confidence=confidence,
            signals=signals,
            ambiguous_types=[BED_TYPE_FSM_RELAX]
            if matches_fsm_relax_candidate(service_info.name)
            else [],
        )

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
        return DetectionResult(bed_type=BED_TYPE_SLEEPYS_BOX15, confidence=0.9, signals=signals)

    # Check for Cool Base - name pattern detection (before Keeson since same UUID)
    # Cool Base is a Keeson BaseI5 variant with additional fan control
    # The Cool Base app accepts any scan name containing "base-i5"
    if any(pattern in device_name for pattern in COOLBASE_NAME_PATTERNS):
        signals.append("name:coolbase")
        _LOGGER.info(
            "Detected Cool Base bed at %s (name: %s) by name pattern",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_COOLBASE, confidence=0.9, signals=signals)

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

    # Check for Richmat by name pattern (e.g., QRRM157052, B6RM123456, ZR10...)
    # Uses RICHMAT_CODE_PATTERN regex to match all valid remote codes (492 codes supported)
    # Also extract remote code for feature detection
    # Exclude MlRM patterns which are Leggett & Platt (need WiLinke UUID to detect)
    if is_richmat_named:
        signals.append("name:richmat")
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
    # Supports both legacy FF12 service and Lierda3 FE60 service.
    if (
        COMFORT_MOTION_SERVICE_UUID.lower() in service_uuids
        or COMFORT_MOTION_LIERDA3_SERVICE_UUID.lower() in service_uuids
    ):
        if COMFORT_MOTION_LIERDA3_SERVICE_UUID.lower() in service_uuids:
            signals.append("uuid:comfort_motion_lierda3")
        else:
            signals.append("uuid:comfort_motion")
        _LOGGER.info(
            "Detected Comfort Motion bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_COMFORT_MOTION, confidence=1.0, signals=signals)

    # Check for Jiecang - name-based detection (Glide beds, Dream Motion app)
    if any(
        x in device_name
        for x in ["jiecang", "jc-", "dream motion", "glide", "comfort motion", "lierda"]
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
        return DetectionResult(bed_type=BED_TYPE_OKIN_HANDLE, confidence=0.3, signals=signals)

    # Check for Serta Motion Perfect - name-based detection (Serta MP Remote app)
    if any(x in device_name for x in ["serta", "motion perfect"]):
        signals.append("name:serta")
        _LOGGER.info(
            "Detected Serta bed at %s (name: %s) - Serta MP Remote app",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_SERTA_MP_REMOTE, confidence=0.9, signals=signals
        )

    # Check for beds using FFE5 service UUID (Keeson, OKIN FFE, Malouf LEGACY, Serta)
    # Priority: OKIN FFE name patterns > Keeson (default); a Serta name matched above
    if KEESON_BASE_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:ffe5")
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
        # This UUID is shared by Keeson, Malouf LEGACY, OKIN FFE and Serta MP Remote
        _LOGGER.info(
            "Detected Keeson Base bed at %s (name: %s) - FFE5 UUID is ambiguous",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_KEESON,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[
                BED_TYPE_MALOUF_LEGACY_OKIN,
                BED_TYPE_OKIN_FFE,
                BED_TYPE_SERTA_MP_REMOTE,
            ],
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
        return DetectionResult(bed_type=BED_TYPE_OKIN_NORDIC, confidence=0.9, signals=signals)

    # NORA_CON / NORACON Mattress Firm controllers use OKIN's 64-bit Nordic UART
    # profile. Without this name-specific check, the shared Nordic UART service
    # falls through to Richmat's incompatible single-byte Nordic profile.
    if (
        _is_nora_controller_identifier(service_info.name)
        and RICHMAT_NORDIC_SERVICE_UUID.lower() in service_uuids
    ):
        signals.append("name:nora_con")
        signals.append("uuid:nordic_uart")
        _LOGGER.info(
            "Detected NORA_CON OKIN 64-bit bed at %s (name: %s)",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_64BIT,
            confidence=0.85,
            signals=signals,
            ambiguous_types=[BED_TYPE_OKIN_NORDIC, BED_TYPE_RICHMAT],
        )

    # Check for Extended Nordic UART (Ergomotion/SFD beds) - maps to Keeson
    if KEESON_EXTENDED_NORDIC_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:extended_nordic_uart")
        _LOGGER.info(
            "Detected Keeson/Ergomotion bed at %s (name: %s) - Extended Nordic UART UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(bed_type=BED_TYPE_KEESON, confidence=0.8, signals=signals)

    if onlysnore_advertisement(
        service_info.name or "", service_info.manufacturer_data or {}, service_info.address
    ):
        return DetectionResult(
            "onlysnore", 0.9, ["name:SLEEP_V", "manufacturer_id:89", "manufacturer_identity"]
        )
    if smart_sleep_advertisement(service_info.name or "", service_info.manufacturer_data or {}, service_info.address):
        return DetectionResult("smart_sleep", 0.9, ["name:smart_sleep", "manufacturer_id:89"])

    # Check for Richmat Nordic / Keeson KSBT / OKIN 64-bit (same UUID)
    # These share the Nordic UART service UUID
    if RICHMAT_NORDIC_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:nordic_uart")

        # If OKIN manufacturer ID is also present, this is likely a SmartBed app
        # receiver (for example a Lucid L600) that also advertises Nordic UART.
        # Nordic-only Malouf Smartbed428 variants are handled before this branch.
        if (
            service_info.manufacturer_data
            and MANUFACTURER_ID_OKIN in service_info.manufacturer_data
        ):
            signals.append(f"manufacturer_id:{MANUFACTURER_ID_OKIN}")
            _LOGGER.info(
                "Detected SmartBed bed at %s (name: %s) - Nordic UART + OKIN manufacturer ID",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(
                bed_type="smartbed",
                confidence=0.7,
                signals=signals,
                ambiguous_types=[
                    BED_TYPE_RICHMAT,
                    BED_TYPE_KEESON,
                    BED_TYPE_OKIN_NORDIC,
                    BED_TYPE_OKIN_64BIT,
                ],
                manufacturer_id=MANUFACTURER_ID_OKIN,
            )

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
            ambiguous_types=[BED_TYPE_KEESON, BED_TYPE_OKIN_NORDIC, BED_TYPE_OKIN_64BIT],
            requires_characteristic_check=True,
        )

    # Fallback: Check for manufacturer ID 89 (SmartBed app receivers)
    # This catches OKIN SmartBed devices that advertise only manufacturer data
    # (no service UUIDs); devices with Nordic UART + mfr ID 89 are handled above.
    #
    # Manufacturer ID 89 is Nordic Semiconductor's Bluetooth SIG company ID
    # (0x0059), used by countless unrelated devices built on Nordic SoCs, so it is
    # far too weak on its own to claim a SmartBed bed. Require the device to also
    # advertise an OKIN/SmartBed name; otherwise a bare mfr-89 advertisement from a
    # random Nordic gadget gets misidentified as a bed (e.g. "ABXM2" in #366).
    if (
        service_info.manufacturer_data
        and MANUFACTURER_ID_OKIN in service_info.manufacturer_data
        and any(hint in device_name for hint in SMARTBED_MANUFACTURER_NAME_HINTS)
    ):
        signals.append(f"manufacturer_id:{MANUFACTURER_ID_OKIN}")
        _LOGGER.info(
            "Detected SmartBed bed at %s (name: %s) by manufacturer ID %s (fallback)",
            service_info.address,
            service_info.name,
            MANUFACTURER_ID_OKIN,
        )
        return DetectionResult(
            bed_type="smartbed",
            confidence=0.7,  # Lower confidence as fallback
            signals=signals,
            manufacturer_id=MANUFACTURER_ID_OKIN,
        )

    if motion_name and SOLACE_SERVICE_UUID.lower() not in service_uuids:
        # The app's case-sensitive contains match also hits short interior
        # markers (TL-A, S3-2), so it only applies when no other route claimed
        # the device. The setup chooser still requires an explicit selection.
        return DetectionResult(
            bed_type=BED_TYPE_MOTION_BED,
            confidence=0.6,
            signals=[*signals, "name:motion_bed"],
        )

    # These app prefixes are shared with other bed apps. Keep stronger service
    # and model matches above; ask for the app rather than infer its identity.
    if device_name.startswith(("okin-ble", "smartbed")):
        return DetectionResult(
            bed_type=BED_TYPE_JALON, confidence=0.3,
            signals=[*signals, "name:jalon_app_candidate"],
            ambiguous_types=[BED_TYPE_KEESON, "smartbed"],
        )

    _LOGGER.debug("Device %s does not match any known bed types", service_info.address)
    return DetectionResult(bed_type=None, confidence=0.0, signals=signals)
