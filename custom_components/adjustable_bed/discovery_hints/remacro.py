"""Remacro discovery hints."""

from ..const import BED_TYPE_REMACRO, REMACRO_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(REMACRO_SERVICE_UUID, bed_types={BED_TYPE_REMACRO})
