"""Rize Home's shared name is an app candidate, never product inference."""

from ..const import BED_TYPE_RIZE_HOME
from ._hints import Case, names

HINTS = (names("smartbed", bed_types={BED_TYPE_RIZE_HOME}, case=Case.ANY, connectable=True),)
