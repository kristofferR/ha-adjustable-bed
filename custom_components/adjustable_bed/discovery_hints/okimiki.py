"""Okimiki's case-sensitive name candidates, without shared-service promotion."""

from ..profiles.okimiki import SCAN_KEYWORDS
from ._hints import Case, names

HINTS = (names(*SCAN_KEYWORDS, bed_types={"okimiki"}, case=Case.EXACT, anywhere=True),)
