"""Bed type detection logic for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

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
    BED_TYPE_COOLBASE,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JENSEN,
    BED_TYPE_JIECANG,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_MATTRESSFIRM,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_NECTAR,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    # Protocol-based bed types (new)
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REMACRO,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_RONDURE,
    BED_TYPE_SBI,
    BED_TYPE_SCOTT_LIVING,
    BED_TYPE_SERTA,
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPYS_BOX15,
    BED_TYPE_SLEEPYS_BOX24,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    BED_TYPE_SUTA,
    BED_TYPE_SVANE,
    BED_TYPE_TIMOTION_AHF,
    BED_TYPE_VIBRADORM,
    # Detection constants
    BEDTECH_MANUFACTURER_ID,
    BEDTECH_NAME_PATTERNS,
    BEDTECH_SERVICE_UUID,
    BEDTECH_WRITE_CHAR_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_SERVICE_UUID,
    COOLBASE_NAME_PATTERNS,
    DEVICE_INFO_SERVICE_UUID,
    DEWERTOKIN_NAME_PATTERNS,
    DEWERTOKIN_RF_GATEWAY_DEVICE_NAME_CHAR_UUID,
    DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
    DEWERTOKIN_SERVICE_UUID,
    ERGOMOTION_NAME_PATTERNS,
    JENSEN_NAME_PATTERNS,
    JENSEN_SERVICE_UUID,
    KAIDI_DISCOVERY_SERVICE_UUID,
    KAIDI_MAC_PREFIXES,
    KAIDI_MESH_SERVICE_UUID,
    KAIDI_NAME_PATTERNS,
    KEESON_BASE_SERVICE_UUID,
    KEESON_EXTENDED_NORDIC_SERVICE_UUID,
    KEESON_FALLBACK_GATT_PAIRS,
    KEESON_JSON_SERVICE_UUID,
    KEESON_NAME_PATTERNS,
    KEESON_SINO_NAME_PATTERNS,
    LEGGETT_GEN2_MANUFACTURER_PREFIXES,
    LEGGETT_GEN2_SERVICE_UUID,
    LEGGETT_OKIN_NAME_PATTERNS,
    LEGGETT_RICHMAT_NAME_PATTERNS,
    LEGGETT_VARIANT_OKIN,
    LIMOSS_NAME_PATTERNS,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_NAME_PATTERNS,
    LINAK_POSITION_SERVICE_UUID,
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
    OCTO_NAME_PATTERNS,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_NAME_ONLY_PATTERNS,
    OKIMAT_NAME_PATTERNS,
    OKIMAT_NOTIFY_CHAR_UUID,
    OKIMAT_SERVICE_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_FFE_NAME_PATTERNS,
    OKIN_GENERIC_NAME_PATTERNS,
    OKIN_ORE_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_SERVICE_UUID,
    OKIN_SMART_REMOTE_CSS_WRITE_CHAR_UUID,
    REMACRO_SERVICE_UUID,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
    RICHMAT_NAME_PATTERNS,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    RICHMAT_WILINKE_W5_SERVICE_UUID,
    SERTA_NAME_PATTERNS,
    SLEEP_NUMBER_MCR_SERVICE_UUID,
    SLEEP_NUMBER_SERVICE_UUID,
    SLEEPYS_BOX25_NAME_PATTERNS,
    SLEEPYS_NAME_PATTERNS,
    SOLACE_NAME_PATTERNS,
    SOLACE_SERVICE_UUID,
    SUTA_NAME_PATTERNS,
    SUTA_SERVICE_UUID,
    SUTA_UNSUPPORTED_NAME_PREFIXES,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_NAME_PATTERNS,
    TIMOTION_AHF_NAME_PATTERNS,
    TIMOTION_AHF_SERVICE_UUID,
    VIBRADORM_NAME_PATTERNS,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
    # Detection result type
    DetectionResult,
)
from .kaidi_protocol import extract_kaidi_advertisement

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

# Richmat remote code pattern (e.g., QRRM, V1RM, BURM, ZR10, ZR60)
# Matches: 2 alphanumeric + "R" + "M" or "N" (like QRRM, V1RM, BURM, A0RN)
# Or: "ZR" + 2 alphanumeric chars (like ZR10, ZR60, ZRA2, ZRS3)
# Case-insensitive via re.IGNORECASE
RICHMAT_CODE_PATTERN = re.compile(r"^([a-z0-9]{2}r[mn]|zr[a-z0-9]{2})", re.IGNORECASE)

KEESON_FALLBACK_SERVICE_UUIDS: frozenset[str] = frozenset(
    service_uuid.lower() for service_uuid, _ in KEESON_FALLBACK_GATT_PAIRS
)

OKIN_SHARED_UUID_GATT_REFINABLE_TYPES: frozenset[str] = frozenset(
    {
        BED_TYPE_LEGGETT_OKIN,
        BED_TYPE_NECTAR,
        BED_TYPE_OKIMAT,
        BED_TYPE_OKIN_7BYTE,
        BED_TYPE_OKIN_64BIT,
        BED_TYPE_OKIN_CST,
        BED_TYPE_OKIN_RF_ECO_BT,
        BED_TYPE_OKIN_UUID,
    }
)

# Shared-UUID profiles that already drive an OKIMAT bed acceptably, so a connected
# OKIMAT Device Info model must not rewrite them. BED_TYPE_OKIMAT and
# BED_TYPE_OKIN_UUID resolve to the same controller; BED_TYPE_OKIN_CST is its own
# deliberately preserved full-bed profile (see refine_okin_shared_uuid_protocol_from_gatt).
OKIMAT_COMPATIBLE_PROFILES: frozenset[str] = frozenset(
    {
        BED_TYPE_OKIMAT,
        BED_TYPE_OKIN_UUID,
        BED_TYPE_OKIN_CST,
    }
)

NORA_CONTROLLER_NORMALIZED_NAMES: frozenset[str] = frozenset({"noracon"})

# Manufacturer ID 89 is Nordic Semiconductor's company ID (0x0059), shared by many
# non-bed devices. The bare-manufacturer-data CB24 fallback only applies when the
# device also advertises a recognizable OKIN/SmartBed name, so a random Nordic
# gadget (e.g. "ABXM2", #366) is not misidentified as a bed.
OKIN_CB24_MANUFACTURER_NAME_HINTS: frozenset[str] = frozenset({"okin", "smartbed"})

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
        return BED_TYPE_DEWERTOKIN, 0.95, MANUFACTURER_ID_DEWERTOKIN

    # Vibradorm: Company ID 944 (0x03B0)
    # Source: de.vibradorm.vra app disassembly
    if MANUFACTURER_ID_VIBRADORM in manufacturer_data:
        return BED_TYPE_VIBRADORM, 0.95, MANUFACTURER_ID_VIBRADORM

    # Logicdata: Company ID 1351 (0x0547)
    # Source: at.silvermotion app disassembly
    if MANUFACTURER_ID_LOGICDATA in manufacturer_data:
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
SOLACE_NAME_PATTERN = re.compile(r"^s\d+-[a-z]-\d+-[a-z0-9]+$", re.IGNORECASE)

# Generic/shared BLE service UUIDs used by multiple bed types AND non-bed devices.
# Name-based exclusions are only applied when a device advertises these UUIDs,
# preserving UUID-based detection for beds with unique service UUIDs.
# See: https://github.com/kristofferR/ha-adjustable-bed/issues/187
GENERIC_SHARED_SERVICE_UUIDS: frozenset[str] = frozenset(
    uuid.lower()
    for uuid in (
        SOLACE_SERVICE_UUID,  # FFE0 - Solace, Octo, MotoSleep, scales, scooters
        KEESON_BASE_SERVICE_UUID,  # FFE5 - Keeson, Malouf, Serta, fitness trackers
        RICHMAT_NORDIC_SERVICE_UUID,  # Nordic UART - Richmat, many IoT devices
        OKIMAT_SERVICE_UUID,  # 62741523 - Okimat, Leggett Okin, Nectar
        *RICHMAT_WILINKE_SERVICE_UUIDS,  # FEE9 variants - Richmat WiLinke, BedTech
    )
)

# Device name patterns that should NOT be detected as beds
# These use generic BLE UUIDs that beds also use, but are clearly not beds
# Only applied when device has generic UUIDs (see GENERIC_SHARED_SERVICE_UUIDS)
# See: https://github.com/kristofferR/ha-adjustable-bed/issues/187
EXCLUDED_DEVICE_PATTERNS: tuple[str, ...] = (
    # Mobility devices
    "scooter",
    "ninebot",
    "segway",
    "ebike",
    "e-bike",
    "escooter",
    "e-scooter",
    "skateboard",
    "hoverboard",
    # Scales and health monitors
    "scale",
    "weight",
    "wyze",
    "withings",
    "renpho",
    "eufy",
    "fitindex",
    "greater goods",
    "etekcity",
    "arboleaf",
    # Wearables and fitness trackers
    "watch",
    "band",
    "tracker",
    "fitbit",
    "garmin",
    "amazfit",
    "xiaomi",
    "mi band",
    "miband",
    "huawei",
    "polar",
    "suunto",
    "coros",
    "whoop",
    # Health monitors
    "thermometer",
    "blood pressure",
    "pulse ox",
    "heart rate",
    "glucose",
    "oximeter",
    # Other common BLE devices
    "headphone",
    "earbud",
    "airpod",
    "speaker",
    "keyboard",
    "mouse",
    "controller",
    "gamepad",
    "tile",
    "airtag",
    "smarttag",
    "beacon",
)


def _has_only_generic_uuids(service_uuids: list[str]) -> bool:
    """Check if device has only generic/shared UUIDs (or no UUIDs).

    Returns True if the device should be subject to name-based exclusion checks.
    Returns False if the device has a unique bed-specific UUID that should
    take priority over name patterns.
    """
    if not service_uuids:
        return True
    return all(uuid in GENERIC_SHARED_SERVICE_UUIDS for uuid in service_uuids)


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
    BED_TYPE_OKIN_CB24: "Okin CB24 (SmartBed by Okin, Amada)",
    BED_TYPE_OKIN_DOT: "Okin DOT (FurniMove RF1058/RF34/RF6707 remotes)",
    BED_TYPE_OKIN_FFE: "Okin FFE (13/15 series)",
    BED_TYPE_OKIN_ORE: "Okin ORE (Dynasty, INNOVA)",
    BED_TYPE_OKIN_64BIT: "Okin 64-Bit (10-byte commands)",
    BED_TYPE_OKIN_CB35: "Okin CB35 (Sealy Posturematic, DewertOkin Star)",
    BED_TYPE_OKIN_CST: "Okin CST (Rize MF900, 14-byte dual-field)",
    BED_TYPE_OKIN_RF_ECO_BT: "OKIN Smart Remote / RF ECO BT single actuator",
    # Protocol-based types (Leggett & Platt family)
    BED_TYPE_LEGGETT_GEN2: "Leggett & Platt Gen2",
    BED_TYPE_LEGGETT_OKIN: "Leggett & Platt Okin (requires pairing)",
    BED_TYPE_LEGGETT_WILINKE: "Leggett & Platt WiLinke (MlRM)",
    # Brand-specific types
    BED_TYPE_BEDTECH: "BedTech",
    BED_TYPE_COOLBASE: "Cool Base (BaseI5 with fan)",
    BED_TYPE_ERGOMOTION: "Ergomotion",
    BED_TYPE_JIECANG: "Jiecang (Glide, Dream Motion)",
    BED_TYPE_JENSEN: "Jensen (JMC400, LinON Entry)",
    BED_TYPE_KEESON: "Keeson (Member's Mark, Purple, some Ergomotion Sync beds)",
    BED_TYPE_KAIDI: "Kaidi (Rize, Floyd, ISleep)",
    BED_TYPE_LINAK: "Linak",
    BED_TYPE_MALOUF_LEGACY_OKIN: "Malouf (FFE5 protocol)",
    BED_TYPE_MALOUF_NEW_OKIN: "Malouf (Nordic UART protocol)",
    BED_TYPE_MOTOSLEEP: "MotoSleep",
    BED_TYPE_OCTO: "Octo",
    BED_TYPE_REVERIE: "Reverie (Protocol 108)",
    BED_TYPE_REVERIE_NIGHTSTAND: "Reverie Nightstand (Protocol 110)",
    BED_TYPE_RICHMAT: "Richmat",
    BED_TYPE_RONDURE: "1500 Tilt Base (Rondure)",
    BED_TYPE_REMACRO: "Remacro (CheersSleep, Jeromes, Slumberland, The Brick)",
    BED_TYPE_COMFORT_MOTION: "Comfort Motion (Lierda)",
    BED_TYPE_LIMOSS: "Limoss / Stawett (TEA encrypted)",
    BED_TYPE_LOGICDATA: "Logicdata SimplicityFrame (SILVERmotion)",
    BED_TYPE_SBI: "SBI/Q-Plus (Costco)",
    BED_TYPE_SCOTT_LIVING: "Scott Living",
    BED_TYPE_SERTA: "Serta Motion Perfect",
    BED_TYPE_SLEEP_NUMBER: "Sleep Number Climate 360 / FlexFit",
    BED_TYPE_SLEEP_NUMBER_MCR: "Sleep Number 360 / i8 FlexFit (BAM/MCR)",
    BED_TYPE_SLEEPYS_BOX15: "Sleepy's Elite (BOX15, with lumbar)",
    BED_TYPE_SLEEPYS_BOX24: "Sleepy's Elite (BOX24)",
    BED_TYPE_SLEEPYS_BOX25: "Sleepy's Elite (BOX25 Star)",
    BED_TYPE_SOLACE: "Solace",
    BED_TYPE_SUTA: "SUTA Smart Home (AT protocol)",
    BED_TYPE_SVANE: "Svane",
    BED_TYPE_TIMOTION_AHF: "TiMOTION AHF",
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


def detect_bed_type_from_gatt_services(gatt_services: Any) -> DetectionResult:
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
            bed_type=BED_TYPE_DEWERTOKIN,
            confidence=0.9,
            signals=[
                "gatt_service:dewertokin_rf_gateway",
                "gatt_char:dewertokin_rf_gateway_name",
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
                ambiguous_types=[BED_TYPE_NECTAR, BED_TYPE_OKIN_RF_ECO_BT],
            )

        return DetectionResult(
            bed_type=BED_TYPE_OKIN_RF_ECO_BT,
            confidence=0.9,
            signals=signals,
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


def _is_okimat_bed_model(ble_model: str | None) -> bool:
    """Return True when Device Info identifies a multi-motor OKIMAT bed actuator.

    OKIMAT bed actuators (e.g. ``OKIMAT 4 IPS/M`` from issue #406) expose the same
    OKIN write + Smart-Remote-CSS GATT signature as the ELDA single-actuator stair
    (issue #344, ``MEGAMAT MBZ``). The connected Device Information model is the
    only reliable way to tell a full bed apart from the niche stair profile.
    """
    return "okimat" in (ble_model or "").strip().lower()


def refine_okin_shared_uuid_protocol_from_gatt(
    bed_type: str,
    gatt_services: Any,
    protocol_variant: str | None = None,
    ble_model: str | None = None,
) -> str:
    """Correct shared OKIN UUID profiles once connected GATT services are known."""
    is_leggett_okin_variant = (
        bed_type == BED_TYPE_LEGGETT_PLATT and protocol_variant == LEGGETT_VARIANT_OKIN
    )
    if bed_type not in OKIN_SHARED_UUID_GATT_REFINABLE_TYPES and not is_leggett_okin_variant:
        return bed_type

    gatt_detection = detect_bed_type_from_gatt_services(gatt_services)
    if gatt_detection.bed_type in {BED_TYPE_OKIN_CST, BED_TYPE_OKIN_RF_ECO_BT}:
        if gatt_detection.bed_type == BED_TYPE_OKIN_RF_ECO_BT and _is_okimat_bed_model(ble_model):
            # Full OKIMAT beds share the RF ECO BT stair's CSS GATT signature, so
            # the bare signature is not enough to pick the single-actuator stair
            # profile. The Device Info model proves this is a multi-motor OKIMAT
            # bed (issue #406).
            if bed_type in OKIMAT_COMPATIBLE_PROFILES:
                # Already on an OKIMAT-compatible controller; keep the saved label
                # (BED_TYPE_OKIMAT/OKIN_UUID resolve to the same controller, and
                # OKIN CST is its own deliberately preserved full-bed profile).
                _LOGGER.debug(
                    "Keeping %s profile for OKIMAT bed model %r despite RF ECO BT GATT signature",
                    bed_type,
                    ble_model,
                )
                return bed_type
            # Any other shared-UUID guess — a persisted RF ECO BT stair entry, or
            # an incompatible profile such as Nectar / OKIN 7-byte / Leggett OKIN —
            # is the wrong controller for an OKIMAT bed. Promote it to the
            # multi-motor OKIN UUID profile so the bed recovers (issue #406).
            _LOGGER.info(
                "Promoted %s to %s for OKIMAT bed model %r despite RF ECO BT GATT signature",
                bed_type,
                BED_TYPE_OKIN_UUID,
                ble_model,
            )
            return BED_TYPE_OKIN_UUID
        if bed_type == BED_TYPE_OKIN_CST and gatt_detection.bed_type == BED_TYPE_OKIN_RF_ECO_BT:
            return bed_type
        if gatt_detection.bed_type != bed_type:
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
    if bed_type not in (BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID) or not gatt_services:
        return bed_type

    from .const import (
        BED_TYPE_OKIN_DOT,
        NORDIC_UART_SERVICE_UUID,
        NORDIC_UART_WRITE_CHAR_UUID,
    )

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
        BED_TYPE_MATTRESSFIRM,
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
    detected_remote = detect_richmat_remote_from_name(service_info.name)
    is_leggett_mlrm_name = any(
        device_name.startswith(pattern) for pattern in LEGGETT_RICHMAT_NAME_PATTERNS
    )
    is_richmat_named = (
        bool(detected_remote)
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
    if kaidi_adv and not (has_kaidi_uuid or has_kaidi_name or has_kaidi_mac):
        _LOGGER.debug(
            "Ignoring PairLink-format manufacturer data for %s (name: %s): "
            "no Kaidi name, UUID, or MAC OUI to corroborate",
            service_info.address,
            service_info.name,
        )
    elif kaidi_adv:
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
        )

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

    if DEWERTOKIN_RF_GATEWAY_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:dewertokin_rf_gateway")
        _LOGGER.info(
            "Detected DewertOkin RF-Gateway bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_DEWERTOKIN,
            confidence=0.9,
            signals=signals,
        )

    # Check for OKIN ORE - unique service UUID (00001000)
    if OKIN_ORE_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:okin_ore")
        _LOGGER.info(
            "Detected OKIN ORE bed at %s (name: %s) by service UUID",
            service_info.address,
            service_info.name,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_ORE,
            confidence=1.0,
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

    # Check for SUTA Smart Home (AT command protocol over FFF0).
    # Excludes known accessory-only subtypes that use a separate binary protocol.
    if any(device_name.startswith(pattern) for pattern in SUTA_NAME_PATTERNS):
        if any(device_name.startswith(prefix) for prefix in SUTA_UNSUPPORTED_NAME_PREFIXES):
            signals.append("name:suta_accessory")
            _LOGGER.debug(
                "Skipping SUTA accessory subtype at %s (name: %s)",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(bed_type=None, confidence=0.0, signals=signals)
        else:
            signals.append("name:suta")
            if SUTA_SERVICE_UUID.lower() in service_uuids:
                signals.append("uuid:suta_fff0")
                _LOGGER.info(
                    "Detected SUTA bed at %s (name: %s) by FFF0 UUID + name pattern",
                    service_info.address,
                    service_info.name,
                )
                return DetectionResult(
                    bed_type=BED_TYPE_SUTA,
                    confidence=0.9,
                    signals=signals,
                )
            if not service_uuids:
                _LOGGER.info(
                    "Detected SUTA bed at %s (name: %s) by name pattern",
                    service_info.address,
                    service_info.name,
                )
                return DetectionResult(
                    bed_type=BED_TYPE_SUTA,
                    confidence=0.3,
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
        from .const import NORDIC_UART_SERVICE_UUID

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
            ],
            requires_characteristic_check=True,
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

        # Receiver names are still ambiguous even after the shared OKIN service
        # appears, because Okimat, CST, 64-bit, and Leggett Okin can share it.
        if any(pattern in device_name for pattern in OKIMAT_NAME_ONLY_PATTERNS):
            signals.append("name:okin_receiver")
            _LOGGER.warning(
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
            return DetectionResult(bed_type=BED_TYPE_OKIMAT, confidence=0.9, signals=signals)

        # Generic OKIN-XXXXXX names are not enough to pick a protocol. They can
        # be classic Okimat 6-byte devices or Nectar-style 7-byte bases.
        if any(device_name.startswith(pattern) for pattern in OKIN_GENERIC_NAME_PATTERNS):
            signals.append("name:okin_generic")
            _LOGGER.warning(
                "Generic OKIN device name '%s' at %s uses shared Okin UUID. "
                "Prompting for protocol because this can be Okimat, Nectar, or another Okin variant.",
                service_info.name,
                service_info.address,
            )
            return DetectionResult(
                bed_type=BED_TYPE_OKIMAT,
                confidence=0.6,
                signals=signals,
                ambiguous_types=[
                    BED_TYPE_NECTAR,
                    BED_TYPE_LEGGETT_OKIN,
                    BED_TYPE_OKIN_64BIT,
                    BED_TYPE_OKIN_CST,
                    BED_TYPE_OKIN_RF_ECO_BT,
                ],
                requires_characteristic_check=True,
            )

        # Fallback: default to Okimat with warning about ambiguity
        # This UUID is shared by Okimat, Leggett Okin, OKIN 64-bit, and OKIN CST
        _LOGGER.warning(
            "Okin UUID detected but device name '%s' at %s doesn't match known patterns. "
            "Defaulting to Okimat. Change to Nectar, Leggett & Platt, OKIN 64-bit, or OKIN CST in settings if needed.",
            service_info.name,
            service_info.address,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIMAT,
            confidence=0.5,
            signals=signals,
            ambiguous_types=[
                BED_TYPE_NECTAR,
                BED_TYPE_LEGGETT_OKIN,
                BED_TYPE_OKIN_64BIT,
                BED_TYPE_OKIN_CST,
                BED_TYPE_OKIN_RF_ECO_BT,
            ],
            requires_characteristic_check=True,
        )

    # Check for BedTech before Richmat WiLinke since they share FEE9 and QRRM
    # names. Confirmed BedTech QRRM controllers advertise their MAC suffix under
    # manufacturer ID 0x4C57; confirmed Casper/Richmat QRRM RGB controllers do not.
    has_bedtech_manufacturer = (
        BEDTECH_MANUFACTURER_ID in (service_info.manufacturer_data or {})
        and (
            device_name.startswith("qrrm")
            or any(pattern in device_name for pattern in BEDTECH_NAME_PATTERNS)
        )
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
            return DetectionResult(bed_type=BED_TYPE_LIMOSS, confidence=0.9, signals=signals)

        # Check for Solace name patterns from Motion Bed app reverse engineering:
        # - QMS-*, QMS2, QMS3, QMS4 (QMS series)
        # - S3-*, S4-*, S5-*, S6-* (S-series)
        # - SealyMF (Sealy Motion Flex)
        # - Contains "solace"
        # - Matches legacy Solace naming convention like "S2-Y-192-461000AD"
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
        # Check for MotoSleep name pattern (HHC prefix)
        if device_name.startswith("hhc"):
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
            ambiguous_types=[BED_TYPE_SOLACE, BED_TYPE_MOTOSLEEP],
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
            # W5 (E0FF) uses a Telink-style custom base that non-bed devices also
            # advertise (e.g. a "Nokia-*" headset, issue #382). It is not
            # bed-unique, so only trust it when a Richmat name corroborates the
            # match; otherwise keep scanning and let detection fall through.
            if (
                wilinke_uuid.lower() == RICHMAT_WILINKE_W5_SERVICE_UUID.lower()
                and not is_richmat_named
            ):
                _LOGGER.debug(
                    "Ignoring W5 WiLinke UUID for %s (name: %s): shared Telink "
                    "base with no Richmat name to corroborate",
                    service_info.address,
                    service_info.name,
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

    # Check for MotoSleep - name-based detection (HHC prefix)
    if device_name.startswith("hhc"):
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
        return DetectionResult(bed_type=BED_TYPE_LIMOSS, confidence=confidence, signals=signals)

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
    # Device names start with "base-i5" (from BleConnect.java: limitedDevice = "base-i5")
    if any(device_name.startswith(pattern) for pattern in COOLBASE_NAME_PATTERNS):
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
            ambiguous_types=[BED_TYPE_MATTRESSFIRM, BED_TYPE_RICHMAT],
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

    # Check for Richmat Nordic / Keeson KSBT / OKIN 64-bit (same UUID)
    # These share the Nordic UART service UUID
    if RICHMAT_NORDIC_SERVICE_UUID.lower() in service_uuids:
        signals.append("uuid:nordic_uart")

        # If OKIN manufacturer ID is also present, this is likely a CB24 device
        # (e.g., SmartBed by Okin / Lucid L600) that also advertises Nordic UART.
        # Nordic-only Malouf Smartbed428 variants are handled before this branch.
        if (
            service_info.manufacturer_data
            and MANUFACTURER_ID_OKIN in service_info.manufacturer_data
        ):
            signals.append(f"manufacturer_id:{MANUFACTURER_ID_OKIN}")
            _LOGGER.info(
                "Detected Okin CB24 bed at %s (name: %s) - Nordic UART + OKIN manufacturer ID",
                service_info.address,
                service_info.name,
            )
            return DetectionResult(
                bed_type=BED_TYPE_OKIN_CB24,
                confidence=0.7,
                signals=signals,
                ambiguous_types=[
                    BED_TYPE_RICHMAT,
                    BED_TYPE_KEESON,
                    BED_TYPE_MATTRESSFIRM,
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
            ambiguous_types=[BED_TYPE_KEESON, BED_TYPE_MATTRESSFIRM, BED_TYPE_OKIN_64BIT],
            requires_characteristic_check=True,
        )

    # Fallback: Check for manufacturer ID 89 (CB24 protocol)
    # This catches OKIN SmartBed devices that advertise only manufacturer data
    # (no service UUIDs); devices with Nordic UART + mfr ID 89 are handled above.
    #
    # Manufacturer ID 89 is Nordic Semiconductor's Bluetooth SIG company ID
    # (0x0059), used by countless unrelated devices built on Nordic SoCs, so it is
    # far too weak on its own to claim a CB24 bed. Require the device to also
    # advertise an OKIN/SmartBed name; otherwise a bare mfr-89 advertisement from a
    # random Nordic gadget gets misidentified as a bed (e.g. "ABXM2" in #366).
    if (
        service_info.manufacturer_data
        and MANUFACTURER_ID_OKIN in service_info.manufacturer_data
        and any(hint in device_name for hint in OKIN_CB24_MANUFACTURER_NAME_HINTS)
    ):
        signals.append(f"manufacturer_id:{MANUFACTURER_ID_OKIN}")
        _LOGGER.info(
            "Detected Okin CB24 bed at %s (name: %s) by manufacturer ID %s (fallback)",
            service_info.address,
            service_info.name,
            MANUFACTURER_ID_OKIN,
        )
        return DetectionResult(
            bed_type=BED_TYPE_OKIN_CB24,
            confidence=0.7,  # Lower confidence as fallback
            signals=signals,
            manufacturer_id=MANUFACTURER_ID_OKIN,
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
        gatt_detection = detect_bed_type_from_gatt_services(client.services)
        if gatt_detection.bed_type == BED_TYPE_OKIN_RF_ECO_BT:
            _LOGGER.info("Refined detection: OKIN Smart Remote CSS signature found")
            return BED_TYPE_OKIN_RF_ECO_BT
        if gatt_detection.bed_type == BED_TYPE_OKIN_CST:
            _LOGGER.info("Refined detection: OKIN CST dual-stack GATT signature found")
            return BED_TYPE_OKIN_CST

        # Build a set of all characteristic UUIDs for easy lookup
        all_chars: set[str] = set()
        for service in client.services:
            for char in service.characteristics:
                all_chars.add(char.uuid.lower())

        # For FEE9 service (Richmat WiLinke): Check if BedTech characteristic exists
        if initial_detection == BED_TYPE_RICHMAT:
            # BedTech has a specific write characteristic
            if BEDTECH_WRITE_CHAR_UUID.lower() in all_chars:
                _LOGGER.info("Refined detection: BedTech characteristic found (was Richmat)")
                return BED_TYPE_BEDTECH

        # For OKIN service (62741523): Check for 64-bit read characteristic
        if initial_detection == BED_TYPE_OKIMAT:
            # OKIN 64-bit has the response/notify characteristic (62741625)
            if OKIMAT_NOTIFY_CHAR_UUID.lower() in all_chars:
                # The presence of 62741625 doesn't definitively mean 64-bit
                # (Okimat also has this), but we can note it for logging
                _LOGGER.debug("OKIN notify characteristic found - could be Okimat or OKIN 64-bit")
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
