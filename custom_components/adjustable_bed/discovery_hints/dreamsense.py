"""Dream Sense's shared scan words offer an app choice, never a product guess."""

from ..profiles.dreamsense import SCAN_WORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(*SCAN_WORDS, bed_types={"dreamsense"}, anywhere=True),)
