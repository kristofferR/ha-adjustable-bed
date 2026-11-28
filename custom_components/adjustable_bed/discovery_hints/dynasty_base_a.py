"""Dynasty Base A has no name filter; shared GATT roles offer an app choice."""

from ..const import BED_TYPE_DYNASTY_BASE_A
from ..profiles.dynasty_base_a import PROFILES, codec
from ._hints import services

HINTS = tuple(
    services(
        *(codec.TRANSPORTS[p.transport].service_uuid for p in PROFILES.values()),
        bed_types={BED_TYPE_DYNASTY_BASE_A},
    )
)
