"""Ultramatic UART app's case-insensitive name gate; detection checks data."""

from ..const import BED_TYPE_ULTRAMATIC_SMART_BED
from ._hints import Case, names

HINTS = (
    names("smartbed", bed_types={BED_TYPE_ULTRAMATIC_SMART_BED}, case=Case.ANY, connectable=True),
)
