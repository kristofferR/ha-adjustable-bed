"""N32 platform-name prefixes offer an app choice, never a UART assertion."""

from ..const import BED_TYPE_N32_MOTION_BED
from ._hints import SMARTBED, Case, names

HINTS = (
    names(*SMARTBED, bed_types={BED_TYPE_N32_MOTION_BED}, connectable=True),
    names("N32 MotionBed", bed_types={BED_TYPE_N32_MOTION_BED}, case=Case.FOLD),
)
