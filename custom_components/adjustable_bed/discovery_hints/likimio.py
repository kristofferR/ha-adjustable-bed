"""Shared Likimio scan words offer the app as a candidate."""

from ..const import BED_TYPE_LIKIMIO
from ..profiles.likimio import SCAN_WORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(*SCAN_WORDS, bed_types={BED_TYPE_LIKIMIO}, anywhere=True),)
