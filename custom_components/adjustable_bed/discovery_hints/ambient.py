"""M3 Ambient's broad app scan hint."""

from ..const import BED_TYPE_AMBIENT
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names("CONTROL_BOX", bed_types={BED_TYPE_AMBIENT}, case=Case.IGNORE_CASE, anywhere=True),
)
