"""Power Bob Base's case-sensitive scan words, without product inference."""

from ..profiles.bobpowerbase import SCAN_KEYWORDS
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names(*SCAN_KEYWORDS, bed_types={"bobpowerbase"}, case=Case.EXACT, anywhere=True),
)
