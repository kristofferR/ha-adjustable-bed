"""The app scans by service only, with no name or manufacturer filter."""

from ..const import BED_TYPE_COMFORT_ENHANCEMENT3, OKIMAT_SERVICE_UUID
from ._hints import services

HINTS = services(OKIMAT_SERVICE_UUID, bed_types={BED_TYPE_COMFORT_ENHANCEMENT3})
