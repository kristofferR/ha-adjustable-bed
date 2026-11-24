"""ENSO Sleep Control name candidates and shared receiver services."""

from ..const import BED_TYPE_ENSO2
from ..profiles.enso2 import SCAN_PREFIXES, TRANSPORTS
from ._hints import TOO_BROAD, names, services

HINTS = (
    names(
        *(prefix for prefix in SCAN_PREFIXES if prefix not in TOO_BROAD), bed_types={BED_TYPE_ENSO2}
    ),
    *services(
        *(route.service_uuid for route in TRANSPORTS if not route.single),
        bed_types={BED_TYPE_ENSO2},
    ),
    *services(
        *(route.service_uuid for route in TRANSPORTS if route.single),
        bed_types={BED_TYPE_ENSO2},
        connectable=True,
    ),
)
