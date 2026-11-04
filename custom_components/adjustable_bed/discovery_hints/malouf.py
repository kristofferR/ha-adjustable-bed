"""Malouf discovery hints."""

from ..const import (
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    MALOUF_LEGACY_OKIN_SERVICE_UUID,
    MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID,
)
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = (
    *services(MALOUF_LEGACY_OKIN_SERVICE_UUID, bed_types={BED_TYPE_MALOUF_LEGACY_OKIN}),
    *services(MALOUF_NEW_OKIN_ADVERTISED_SERVICE_UUID, bed_types={BED_TYPE_MALOUF_NEW_OKIN}),
)
