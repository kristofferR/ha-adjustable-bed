"""N32 platform-name prefixes offer an app choice, never a UART assertion."""

from ..const import BED_TYPE_N32_MOTION_BED
from ._hints import Case, names

HINTS = (
    names("smartbed", bed_types={BED_TYPE_N32_MOTION_BED}, case=Case.ANY, connectable=True),
    names("n32 motionbed", bed_types={BED_TYPE_N32_MOTION_BED}, case=Case.ANY),
)
