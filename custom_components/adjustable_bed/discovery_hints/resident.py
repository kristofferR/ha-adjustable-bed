"""Resident 1.0.0's admitted device-name prefixes, which the app reads in any case.

Names offer an app candidate, never a protocol assertion for another Okin app.
Home Assistant gates on advertised local name; the app reads platform name.
"""

from ..const import BED_TYPE_RESIDENT
from ._hints import SMARTBED, Case, names

HINTS = (
    names("OKIN", bed_types={BED_TYPE_RESIDENT}, case=Case.FOLD),
    names(*SMARTBED, bed_types={BED_TYPE_RESIDENT}, connectable=True),
)
