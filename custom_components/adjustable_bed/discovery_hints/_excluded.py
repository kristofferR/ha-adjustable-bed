"""Shared service UUIDs, and name fragments of non-bed devices that advertise them.

Detection rejects a name containing a fragment only when the device advertises
nothing but these generic UUIDs and standard Bluetooth services, so a
bed-unique UUID still wins. A device with only these services and no name is
never offered. See https://github.com/kristofferR/ha-adjustable-bed/issues/187.
"""

from __future__ import annotations

from ..const import (
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_SERVICE_UUID,
    JENSEN_SERVICE_UUID,
    KEESON_BASE_SERVICE_UUID,
    KEESON_JSON_SERVICE_UUID,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
    OCTO_STAR2_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SOLACE_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
)

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
        # Short UUIDs outside the assigned Bluetooth range that any module can
        # advertise: another bed's DA1458X receiver advertised AA5C (#510).
        COMFORT_MOTION_SERVICE_UUID,  # FF12
        COMFORT_MOTION_LIERDA3_SERVICE_UUID,  # FE60 - Lierda modules
        JENSEN_SERVICE_UUID,  # 1234
        KEESON_JSON_SERVICE_UUID,  # A00A
        OCTO_STAR2_SERVICE_UUID,  # AA5C
        SVANE_HEAD_SERVICE_UUID,  # ABCB
        MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,  # 01000001
    )
)

# Device name patterns that should NOT be detected as beds
# These use generic BLE UUIDs that beds also use, but are clearly not beds
# Only applied when device has generic UUIDs (see GENERIC_SHARED_SERVICE_UUIDS)
# See: https://github.com/kristofferR/ha-adjustable-bed/issues/187
EXCLUDED_DEVICE_PATTERNS: tuple[str, ...] = (
    # Flexsteel seating controllers recovered from com.okin.flex_demo. These
    # advertise Nordic UART but are chairs, not adjustable-bed control boxes.
    "flx_audio",
    "flx_rush",
    # TiMOTION Smart Move+ height-adjustable desks (com.timotion.smartmove).
    # The app accepts only names starting "stand UP-" on Nordic UART.
    "stand up-",
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
