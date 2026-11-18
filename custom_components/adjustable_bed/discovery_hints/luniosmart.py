"""Lunio Smart+ aliases suggest the app family, never a product layout."""

from ..beds.luniosmart.discovery import SCAN_CODES
from ..profiles.luniosmart import KEYWORDS
from ._hints import names

HINTS = (names(*KEYWORDS, *SCAN_CODES, bed_types={"luniosmart"}, anywhere=True),)
