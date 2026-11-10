"""Richmat 4.2.0 case-sensitive scan keywords, plus separate sleep-link names."""

from ..beds.richmat_app.catalog import SCAN_KEYWORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(*SCAN_KEYWORDS, bed_types={"richmat_app"}, anywhere=True),
    names("RM-", "HJ-", bed_types={"richmat_app_sleep"}),
)
