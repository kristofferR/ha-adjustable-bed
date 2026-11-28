"""AR Connect's independent native service and headboard name admission."""

from ..profiles.ar_connect import AR_CONNECT
from ._hints import Case, NameHint, services

HINTS = (
    *services(AR_CONNECT.control_service, bed_types={"ar_connect"}),
    NameHint(
        patterns=("dosseret",),
        bed_types=frozenset({"ar_connect"}),
        case=Case.IGNORE_CASE,
        anywhere=True,
    ),
)
