"""DewertOkin discovery hints."""

from ..const import BED_TYPE_DEWERTOKIN, DEWERTOKIN_RF_GATEWAY_SERVICE_UUID, DEWERTOKIN_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(
    DEWERTOKIN_SERVICE_UUID, DEWERTOKIN_RF_GATEWAY_SERVICE_UUID, bed_types={BED_TYPE_DEWERTOKIN}
)
