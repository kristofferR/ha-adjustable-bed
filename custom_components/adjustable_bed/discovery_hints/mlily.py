"""MLILY Control row159, shared GATT never selects a product or app by itself."""

from ..const import BED_TYPE_MLILY
from ..profiles.mlily_choices import PROFILE_CHOICES
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    # Shared services cannot identify this app. Name hints preserve HA's
    # non-bed guards; the selected profile still supports all six GATT routes.
    names(
        "RM-", "HJ-", "B6RU", "MPE_", "200I", "200i", "400I", "400i", "800I", "800i",
        *(key.upper() for key in PROFILE_CHOICES if "/" not in key and not key.startswith("sleep_") and len(key) >= 3),
        bed_types={BED_TYPE_MLILY}, case=Case.EXACT,
    ),
)
