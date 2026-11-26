"""Sleep Assist Pro scan prefixes, refined by saved-ID rules during setup."""

from ..const import BED_TYPE_SLEEP_ASSIST_PRO
from ._hints import Case, names

HINTS = (
    names(
        "KSBT",
        "KSWF",
        "KSPSBED",
        "KSSLBED",
        bed_types={BED_TYPE_SLEEP_ASSIST_PRO},
        case=Case.IGNORE_CASE,
        connectable=True,
    ),
)
