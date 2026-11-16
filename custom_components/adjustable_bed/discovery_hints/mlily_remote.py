"""MLILY Remote scan candidates, never a product-to-advertisement mapping."""

from ..profiles.mlily_remote import SCAN_KEYWORDS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(*SCAN_KEYWORDS, bed_types={"mlily_remote"}, anywhere=True),)
