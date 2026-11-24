"""Dorsal's exact-case scan keywords and accepted Richmat services."""

from typing import Final

from ..codec.richmat import TRANSPORTS, TransportKey
from ._hints import names, services

DORSAL_TRANSPORTS: Final[tuple[TransportKey, ...]] = ("n1", "w1", "w2", "w3", "w4", "w5")
ROOMI_SCAN: Final = "QRRM"

HINTS = (
    names("ZRS6", ROOMI_SCAN, bed_types={"dorsal"}, anywhere=True),
    *services(TRANSPORTS["n1"].service_uuid, bed_types={"dorsal"}, connectable=True),
    # W5 is checked on the live link only; its UUID alone matches unrelated devices.
    *services(
        *(TRANSPORTS[key].service_uuid for key in DORSAL_TRANSPORTS if key not in ("n1", "w5")),
        bed_types={"dorsal"},
    ),
)
