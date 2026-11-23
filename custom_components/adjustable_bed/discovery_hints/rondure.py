"""Rondure discovery hints."""

from ..const import BED_TYPE_RONDURE, RONDURE_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(RONDURE_SERVICE_UUID, bed_types={BED_TYPE_RONDURE})
