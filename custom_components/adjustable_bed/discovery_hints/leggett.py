"""Leggett & Platt discovery hints."""

from ..const import (
    BED_TYPE_LEGGETT_GEN2,
    LEGGETT_GEN2_MANUFACTURER_PREFIXES,
    LEGGETT_GEN2_SERVICE_UUID,
    MANUFACTURER_ID_LEGGETT_GEN2,
)
from ._hints import Hint, manufacturer, services

HINTS: tuple[Hint, ...] = (
    *services(LEGGETT_GEN2_SERVICE_UUID, bed_types={BED_TYPE_LEGGETT_GEN2}),
    # LP Comfort Connect advertises no service UUID, only this record.
    *(
        manufacturer(
            MANUFACTURER_ID_LEGGETT_GEN2, data_start=prefix, bed_types={BED_TYPE_LEGGETT_GEN2}
        )
        for prefix in LEGGETT_GEN2_MANUFACTURER_PREFIXES
    ),
)
