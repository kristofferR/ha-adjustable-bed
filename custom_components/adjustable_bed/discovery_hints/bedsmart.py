"""BedSmart's shipped name prefixes offer the shared app choice, never a layout."""

from ..const import BED_TYPE_RICHMAT_CLASSIC_APPS
from ..profiles.bedsmart import EXCLUDED_LAYOUTS, LAYOUTS, SCAN_PREFIXES
from ._hints import Hint, names

# Beds advertise the codes in upper case, the only case detection reads.
HINTS: tuple[Hint, ...] = (
    names(
        *(code for code in LAYOUTS if code not in EXCLUDED_LAYOUTS),
        *SCAN_PREFIXES,
        'QRRM',
        bed_types={BED_TYPE_RICHMAT_CLASSIC_APPS},
    ),
)
