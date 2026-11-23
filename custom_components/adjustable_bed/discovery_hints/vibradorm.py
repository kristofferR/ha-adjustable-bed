"""Vibradorm discovery hints."""

from ..const import (
    BED_TYPE_VIBRADORM,
    MANUFACTURER_ID_VIBRADORM,
    VIBRADORM_SECONDARY_SERVICE_UUID,
    VIBRADORM_SERVICE_UUID,
)
from ._hints import Hint, manufacturer, names, services

HINTS: tuple[Hint, ...] = (
    *services(
        VIBRADORM_SERVICE_UUID, VIBRADORM_SECONDARY_SERVICE_UUID, bed_types={BED_TYPE_VIBRADORM}
    ),
    manufacturer(MANUFACTURER_ID_VIBRADORM, bed_types={BED_TYPE_VIBRADORM}),
    names("VMAT", bed_types={BED_TYPE_VIBRADORM}),
)
