"""Linak discovery hints."""

from ..const import BED_TYPE_LINAK, LINAK_CONTROL_SERVICE_UUID, LINAK_POSITION_SERVICE_UUID
from ._hints import Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(LINAK_CONTROL_SERVICE_UUID, LINAK_POSITION_SERVICE_UUID, bed_types={BED_TYPE_LINAK}),
    # Some Linak beds advertise only a name such as "Bed 1696".
    names("Bed", bed_types={BED_TYPE_LINAK}),
)
