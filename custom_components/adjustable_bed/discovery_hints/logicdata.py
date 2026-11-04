"""Logicdata discovery hints."""

from ..const import BED_TYPE_LOGICDATA, LOGICDATA_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(LOGICDATA_SERVICE_UUID, bed_types={BED_TYPE_LOGICDATA})
