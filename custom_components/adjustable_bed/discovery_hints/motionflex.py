"""MotionFlex scan substrings offer an app choice, never infer its model."""

from ..profiles.motionflex import SCAN_KEYWORDS
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names(*SCAN_KEYWORDS, bed_types={"motionflex"}, case=Case.EXACT, anywhere=True),
)
