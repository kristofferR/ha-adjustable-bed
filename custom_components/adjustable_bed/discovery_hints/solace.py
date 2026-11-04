"""Solace discovery hints."""

from ..const import BED_TYPE_SOLACE, SOLACE_SERVICE_UUID
from ._hints import Case, Hint, names, services

HINTS: tuple[Hint, ...] = (
    *services(SOLACE_SERVICE_UUID, bed_types={BED_TYPE_SOLACE}),
    names(
        "QMS-IQ",
        "QMS-I06",
        "QMS-LQ",
        "QMS-L04",
        "QMS-JQ-D",
        "QMS4",
        "QMS-NQ",
        "QMS3",
        "QMS-MQ",
        "QMS2",
        "My QMS2",
        "SealyMF",
        "S4-Y-",
        bed_types={BED_TYPE_SOLACE},
        case=Case.FOLD,
    ),
)
