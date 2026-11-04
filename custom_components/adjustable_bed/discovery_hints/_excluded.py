"""Name fragments of non-bed devices that share generic bed service UUIDs.

Detection rejects a name containing a fragment only when the device advertises
nothing but these generic UUIDs, so a bed-unique UUID still wins.
See https://github.com/kristofferR/ha-adjustable-bed/issues/187.
"""

from __future__ import annotations

from ..const import (
    KEESON_BASE_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_SERVICE_UUIDS,
    SOLACE_SERVICE_UUID,
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
