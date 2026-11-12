"""Yamada's platform-name candidates; the user still identifies app and route."""

from ..const import BED_TYPE_YAMADA
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names("okin-ble", "smartbed", bed_types={BED_TYPE_YAMADA}, case=Case.ANY, connectable=True),
)
