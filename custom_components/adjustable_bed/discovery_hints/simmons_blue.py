"""Discovery hint for the Simmons Blue app."""

from ..const import BED_TYPE_SIMMONS_BLUE
from ..profiles.simmons_blue import NAME_PREFIX
from ._hints import Case, names

HINTS = (
    names(NAME_PREFIX, bed_types={BED_TYPE_SIMMONS_BLUE}, case=Case.IGNORE_CASE, connectable=True),
)
