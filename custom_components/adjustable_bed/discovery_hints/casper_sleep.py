"""Casper Base sleep sensor discovery hints."""

from ..const import BED_TYPE_CASPER_SLEEP_MM, BED_TYPE_CASPER_SLEEP_SXB
from ._hints import Hint, names

# The sensor classifier is a case-sensitive startsWith.
HINTS: tuple[Hint, ...] = (
    names("RM-", bed_types={BED_TYPE_CASPER_SLEEP_MM}),
    names("HJ-", bed_types={BED_TYPE_CASPER_SLEEP_SXB}),
)
