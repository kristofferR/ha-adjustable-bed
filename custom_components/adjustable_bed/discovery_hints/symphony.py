"""Shared scan-name candidates; none identifies a Symphony product."""

from ..const import BED_TYPE_SYMPHONY
from ._hints import SMARTBED, Case, names

HINTS = (
    names(*SMARTBED, anywhere=True, connectable=True, bed_types={BED_TYPE_SYMPHONY}),
    names("OKIN", case=Case.FOLD, anywhere=True, bed_types={BED_TYPE_SYMPHONY}),
    names("SLEEP", anywhere=True, bed_types={BED_TYPE_SYMPHONY}),
)
