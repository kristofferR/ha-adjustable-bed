"""Shared receiver services are compatible hints, never a Leva match by themselves."""

from ..const import BED_TYPE_LEVA, KEESON_BASE_SERVICE_UUID, NORDIC_UART_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = (
    *services(KEESON_BASE_SERVICE_UUID, bed_types={BED_TYPE_LEVA}),
    *services(NORDIC_UART_SERVICE_UUID, bed_types={BED_TYPE_LEVA}, connectable=True),
)
