"""Shared scan-name candidates; none identifies a Symphony product."""

from ..const import BED_TYPE_SYMPHONY
from ._hints import Case, names

HINTS = (
    names(
        "SMARTBED", case=Case.ANY, anywhere=True, connectable=True, bed_types={BED_TYPE_SYMPHONY}
    ),
    names("OKIN", "SLEEP", case=Case.ANY, anywhere=True, bed_types={BED_TYPE_SYMPHONY}),
)
