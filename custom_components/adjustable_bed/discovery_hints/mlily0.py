"""MLILY 3.1.1 scan keywords; a shared name never selects the product."""

from ..profiles.mlily0 import SCAN_KEYWORDS
from ._hints import names

HINTS = (names(*SCAN_KEYWORDS, bed_types={"mlily0"}, anywhere=True),)
