"""Resident 1.0.0's case-insensitive admitted device-name prefixes.

Names offer an app candidate, never a protocol assertion for another Okin app.
Home Assistant gates on advertised local name; the app reads platform name.
"""

from ..const import BED_TYPE_RESIDENT
from ._hints import Case, names

HINTS = (
    names("okin", bed_types={BED_TYPE_RESIDENT}, case=Case.ANY),
    names("smartbed", bed_types={BED_TYPE_RESIDENT}, case=Case.ANY, connectable=True),
)
