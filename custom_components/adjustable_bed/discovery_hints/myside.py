"""My Side's scan substrings offer an app candidate, never choose its product."""

from ..const import BED_TYPE_MYSIDE
from ..profiles.myside import SCAN_WORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(*SCAN_WORDS, bed_types={BED_TYPE_MYSIDE}, anywhere=True, packet_name_only=True),
)
