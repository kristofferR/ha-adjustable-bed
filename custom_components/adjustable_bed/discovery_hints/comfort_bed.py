"""Comfort Bed scan candidates require explicit app selection."""

from ..profiles.comfort_bed import SCAN_KEYWORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(*SCAN_KEYWORDS, bed_types={"comfort_bed"}, anywhere=True),)
