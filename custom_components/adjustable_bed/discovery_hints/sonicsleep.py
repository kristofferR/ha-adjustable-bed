"""SonicSleep's case-sensitive scan keyword substrings, never a model choice."""

from ..profiles.sonicsleep import SCAN_KEYWORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(*SCAN_KEYWORDS, bed_types={"sonicsleep"}, anywhere=True),)
