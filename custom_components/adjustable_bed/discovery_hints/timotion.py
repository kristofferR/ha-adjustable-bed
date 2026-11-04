"""TiMOTION discovery hints."""

from ..const import BED_TYPE_TIMOTION_AHF
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names("AHF", bed_types={BED_TYPE_TIMOTION_AHF}),)
