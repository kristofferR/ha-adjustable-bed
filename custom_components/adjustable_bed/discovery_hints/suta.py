"""SUTA discovery hints."""

from ..const import BED_TYPE_SUTA, SUTA_SERVICE_UUID
from ._hints import Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(SUTA_SERVICE_UUID, bed_types={BED_TYPE_SUTA}),
    names("SUTA", bed_types={BED_TYPE_SUTA}),
)
