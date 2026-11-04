"""HJBed discovery hints."""

from ..const import BED_TYPE_HJBED, HJBED_SCAN_KEYWORDS
from ._hints import Hint, names

# The app scan accepts a keyword anywhere in the name.
HINTS: tuple[Hint, ...] = (names(*HJBED_SCAN_KEYWORDS, bed_types={BED_TYPE_HJBED}, anywhere=True),)
