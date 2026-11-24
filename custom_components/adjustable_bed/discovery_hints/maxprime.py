"""Maxprime name hints offer a classic Richmat app choice."""

from ..const import BED_TYPE_RICHMAT_CLASSIC_APPS
from ..profiles.maxprime import LAYOUTS, SCAN_PREFIXES
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(*LAYOUTS, *SCAN_PREFIXES, bed_types={BED_TYPE_RICHMAT_CLASSIC_APPS}),
)
