"""MotoSleep discovery hints."""

from ..const import BED_TYPE_MOTOSLEEP, MOTOSLEEP_SERVICE_UUID
from ._hints import Case, Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(MOTOSLEEP_SERVICE_UUID, bed_types={BED_TYPE_MOTOSLEEP}),
    names("HHC", "MOTOB", "MOTOS", bed_types={BED_TYPE_MOTOSLEEP}, case=Case.FOLD),
)
