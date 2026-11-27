"""MUUEGM shared scan words only offer an explicit app choice."""

from ..profiles.muuegm import SCAN_WORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(*SCAN_WORDS, bed_types={"muuegm"}, anywhere=True, packet_name_only=True),
)
