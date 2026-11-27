"""JobsAI shares the existing OKIN receiver discovery gate.

The app reads the platform name in any case. Detection offers it as an
explicit candidate; the advertisement gate keeps known receiver spellings.
"""

from ..const import BED_TYPE_JOBS
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names("OKIN", case=Case.FOLD, bed_types={BED_TYPE_JOBS}),
)
