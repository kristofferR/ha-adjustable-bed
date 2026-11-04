"""Reverie discovery hints: classic, Nightstand and PairLink."""

from ..const import (
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_REVERIE_PAIRLINK,
    REVERIE_NIGHTSTAND_SERVICE_UUID,
    REVERIE_PAIRLINK_SERVICE_UUID,
    REVERIE_SERVICE_UUID,
)
from ._hints import Hint, manufacturer, services

# PairLink advertisement records: either company key, payload starting 0xC0.
PAIRLINK_MANUFACTURER_IDS = frozenset({0xFFFF, 0x05B9})
PAIRLINK_MANUFACTURER_PREFIX = b"\xc0"

HINTS: tuple[Hint, ...] = (
    *services(REVERIE_SERVICE_UUID, bed_types={BED_TYPE_REVERIE}),
    *services(REVERIE_NIGHTSTAND_SERVICE_UUID, bed_types={BED_TYPE_REVERIE_NIGHTSTAND}),
    *services(REVERIE_PAIRLINK_SERVICE_UUID, bed_types={BED_TYPE_REVERIE_PAIRLINK}),
    *(
        manufacturer(
            company_id,
            data_start=PAIRLINK_MANUFACTURER_PREFIX,
            bed_types={BED_TYPE_REVERIE_PAIRLINK},
        )
        for company_id in sorted(PAIRLINK_MANUFACTURER_IDS)
    ),
)
