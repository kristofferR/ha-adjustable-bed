"""Yamada's platform-name candidates; the user still identifies app and route."""

from ..const import BED_TYPE_YAMADA
from ._hints import SMARTBED, Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names("OKIN-BLE", bed_types={BED_TYPE_YAMADA}, case=Case.FOLD, connectable=True),
    names(*SMARTBED, bed_types={BED_TYPE_YAMADA}, connectable=True),
)
