"""Keeson discovery hints."""

from ..const import (
    BED_TYPE_BETTERLIVING2,
    BED_TYPE_COOLBASE,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_JALON,
    BED_TYPE_KEESON,
    BED_TYPE_SERTA_MP_REMOTE,
    KEESON_BASE_SERVICE_UUID,
    KEESON_EXTENDED_NORDIC_SERVICE_UUID,
    KEESON_JSON_SERVICE_UUID,
    KEESON_KSBT_SERVICE_UUID,
)
from ._hints import SMARTBED, Case, Hint, names, services

HINTS: tuple[Hint, ...] = (
    names("OKIN", bed_types={BED_TYPE_BETTERLIVING2}, case=Case.FOLD),
    names(*SMARTBED, bed_types={BED_TYPE_BETTERLIVING2}, connectable=True),
    names("OKIN-BLE", bed_types={BED_TYPE_JALON}, case=Case.FOLD, connectable=True),
    names(*SMARTBED, bed_types={BED_TYPE_JALON}, connectable=True),
    *services(
        KEESON_BASE_SERVICE_UUID,
        bed_types={BED_TYPE_KEESON, BED_TYPE_ERGOMOTION, BED_TYPE_SERTA_MP_REMOTE},
    ),
    *services(
        KEESON_JSON_SERVICE_UUID,
        KEESON_EXTENDED_NORDIC_SERVICE_UUID,
        KEESON_KSBT_SERVICE_UUID,
        bed_types={BED_TYPE_KEESON},
        connectable=True,
    ),
    # Restonic BT names are case-sensitive; Adjustable Lite scans names alone.
    names("base-i4", "KSBT01C", "KSBT03C", bed_types={BED_TYPE_KEESON}, connectable=True),
    names("base-i5", bed_types={BED_TYPE_KEESON, BED_TYPE_COOLBASE}, connectable=True),
)
