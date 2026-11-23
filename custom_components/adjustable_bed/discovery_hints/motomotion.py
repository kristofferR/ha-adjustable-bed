"""MotoMotion discovery hints."""

from ..const import BED_TYPE_MOTOMOTION
from ._hints import Hint, names

# The app's name rule accepts these fragments anywhere in the name; detection
# then requires the exact name lengths the app checks.
HINTS: tuple[Hint, ...] = (
    names("SOFA", "BT201", "MOTO", bed_types={BED_TYPE_MOTOMOTION}, anywhere=True, connectable=True),
)
