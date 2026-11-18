"""StarCode discovery hints: Star bases, ELEVATE lifts and SleepStar."""

from ..const import (
    BED_TYPE_SLEEPSTAR,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
)
from ._hints import Case, Hint, names

# The apps match a "star" prefix in any case; bases advertise these spellings.
SCAN = names(
    "STAR", "Star", "star", bed_types={BED_TYPE_STARCODE_ABM5_4, BED_TYPE_SLEEPYS_BOX25}
)

HINTS: tuple[Hint, ...] = (
    SCAN,
    names(
        "STAR25",
        bed_types={BED_TYPE_SLEEPYS_BOX25, BED_TYPE_STARCODE_M5X5, BED_TYPE_STARCODE_M1X12},
        connectable=True,
    ),
    names("ELEVATE", bed_types={BED_TYPE_STAR_ELEVATE}, case=Case.FOLD),
    names("SLEEPSTAR", bed_types={BED_TYPE_SLEEPSTAR}, case=Case.FOLD),
)
