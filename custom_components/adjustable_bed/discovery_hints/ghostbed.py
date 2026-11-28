"""GhostBed's case-sensitive cached-name substrings suggest its app route."""

from ..const import BED_TYPE_GHOSTBED
from ..profiles.ghostbed import NAMES
from ._hints import names

HINTS = (names(*NAMES, bed_types={BED_TYPE_GHOSTBED}, anywhere=True, connectable=True),)
