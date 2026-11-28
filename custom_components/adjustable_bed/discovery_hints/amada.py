"""AMADA platform-name admission is an app candidate, not a UART signature."""
from ..const import BED_TYPE_AMADA
from ..profiles.amada import NAME_PREFIX
from ._hints import Case, names

HINTS = (names(NAME_PREFIX + "*", bed_types={BED_TYPE_AMADA}, case=Case.IGNORE_CASE),)
