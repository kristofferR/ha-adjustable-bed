"""BedJet PowerLayer discovery hints."""

from ..const import BED_TYPE_BEDJET_POWERLAYER
from ._hints import Hint, names

# The frame shares its advertised service with the BedJet climate blower, so
# only the frame's factory names lead to it.
HINTS: tuple[Hint, ...] = (names("BEDJET_BF", "BEDFRM", bed_types={BED_TYPE_BEDJET_POWERLAYER}),)
