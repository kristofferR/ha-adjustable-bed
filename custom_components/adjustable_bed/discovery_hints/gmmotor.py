"""GM Control discovery hints, from the generated catalog's scan keywords."""

from ..const import BED_TYPE_GMMOTOR, BED_TYPE_GMMOTOR_SLEEP_MM, BED_TYPE_GMMOTOR_SLEEP_SXB
from ..gmmotor_catalog import SCAN_KEYWORDS
from ._hints import Hint, names

# The app scan accepts a keyword anywhere in the name, case-sensitively.
SCAN = names(*SCAN_KEYWORDS, bed_types={BED_TYPE_GMMOTOR}, anywhere=True)

HINTS: tuple[Hint, ...] = (
    SCAN,
    # The input-name classifier picks the sleep session mode from either key.
    names(
        "RM-",
        "HJ-",
        bed_types={BED_TYPE_GMMOTOR_SLEEP_MM, BED_TYPE_GMMOTOR_SLEEP_SXB},
        anywhere=True,
    ),
)
