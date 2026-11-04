"""Limoss discovery hints."""

from ..const import BED_TYPE_LIMOSS, LIMOSS_SERVICE_UUID
from ._hints import Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(LIMOSS_SERVICE_UUID, bed_types={BED_TYPE_LIMOSS}),
    names("LIMOSS", "STAWETT", bed_types={BED_TYPE_LIMOSS}),
)
