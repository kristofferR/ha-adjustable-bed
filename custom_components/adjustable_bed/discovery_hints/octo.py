"""Octo discovery hints."""

from ..const import BED_TYPE_OCTO, OCTO_SERVICE_UUID, OCTO_STAR2_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(
    OCTO_SERVICE_UUID, OCTO_STAR2_SERVICE_UUID, bed_types={BED_TYPE_OCTO}
)
