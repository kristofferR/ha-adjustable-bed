"""FurniMove discovery hints."""

from ..const import BED_TYPE_FURNIMOVE
from ._hints import Hint, services

# The advertised gateway service FurniMove accepts as an RF receiver.
FURNIMOVE_GATEWAY_SERVICE_UUID = "00001420-0000-1000-8000-00805f9b34fb"

HINTS: tuple[Hint, ...] = services(FURNIMOVE_GATEWAY_SERVICE_UUID, bed_types={BED_TYPE_FURNIMOVE})
