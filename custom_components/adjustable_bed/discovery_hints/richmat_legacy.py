"""Shared Nordic service; it cannot choose between the two legacy apps."""

from ..const import NORDIC_UART_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(
    NORDIC_UART_SERVICE_UUID, bed_types={"sleep_evolution", "wsilver_legacy"}, connectable=True
)
