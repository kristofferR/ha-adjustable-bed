"""Jensen discovery hints."""

from ..const import BED_TYPE_JENSEN, JENSEN_SERVICE_UUID
from ._hints import Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(JENSEN_SERVICE_UUID, bed_types={BED_TYPE_JENSEN}),
    names("JMC", bed_types={BED_TYPE_JENSEN}),
)
