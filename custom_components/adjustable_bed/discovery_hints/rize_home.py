"""Rize Home's shared name is an app candidate, never product inference."""

from ..const import BED_TYPE_RIZE_HOME
from ._hints import SMARTBED, names

HINTS = (names(*SMARTBED, bed_types={BED_TYPE_RIZE_HOME}, connectable=True),)
