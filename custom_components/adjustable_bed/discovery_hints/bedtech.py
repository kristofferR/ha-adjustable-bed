"""BedTech discovery hints."""

from ..const import BED_TYPE_BEDTECH, BEDTECH_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(BEDTECH_SERVICE_UUID, bed_types={BED_TYPE_BEDTECH})
