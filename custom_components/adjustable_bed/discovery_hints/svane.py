"""Svane discovery hints."""

from ..const import BED_TYPE_SVANE, SVANE_HEAD_SERVICE_UUID
from ._hints import Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(SVANE_HEAD_SERVICE_UUID, bed_types={BED_TYPE_SVANE}),
    # The Jensen app's LinOn beds; its generic "Adjustable Bed" is no hint.
    names("Svane", "Jensen Bed", bed_types={BED_TYPE_SVANE}),
)
