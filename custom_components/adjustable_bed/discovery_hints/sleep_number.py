"""Sleep Number discovery hints."""

from ..const import (
    BED_TYPE_SLEEP_NUMBER,
    BED_TYPE_SLEEP_NUMBER_MCR,
    SLEEP_NUMBER_MCR_SERVICE_UUID,
    SLEEP_NUMBER_SERVICE_UUID,
)
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = (
    *services(SLEEP_NUMBER_SERVICE_UUID, bed_types={BED_TYPE_SLEEP_NUMBER}),
    *services(SLEEP_NUMBER_MCR_SERVICE_UUID, bed_types={BED_TYPE_SLEEP_NUMBER_MCR}),
)
