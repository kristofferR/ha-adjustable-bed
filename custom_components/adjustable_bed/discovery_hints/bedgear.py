"""Shared HHC app hints; exact length and selector validation is separate."""

from ..const import BED_TYPE_ERGOBED, BED_TYPE_MOODBASE
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names('HHC', bed_types={'bedgear', 'l2motion', BED_TYPE_ERGOBED, BED_TYPE_MOODBASE}, anywhere=True),)
