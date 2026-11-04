"""Comfort Motion discovery hints."""

from ..const import (
    BED_TYPE_COMFORT_MOTION,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    COMFORT_MOTION_SERVICE_UUID,
)
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(
    COMFORT_MOTION_SERVICE_UUID,
    COMFORT_MOTION_LIERDA3_SERVICE_UUID,
    bed_types={BED_TYPE_COMFORT_MOTION},
)
