"""King Koil's case-sensitive app scan hint, shared with other SUTA apps."""

from ..const import BED_TYPE_SUTA_KING_KOIL
from ..profiles.suta_king_koil import PREFIX
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(PREFIX, bed_types={BED_TYPE_SUTA_KING_KOIL}),)
