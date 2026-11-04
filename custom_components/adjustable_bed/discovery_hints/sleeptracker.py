"""Sleeptracker discovery hints."""

from ..const import BED_TYPE_SLEEPTRACKER, SLEEPTRACKER_SERVICE_UUID
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(
    SLEEPTRACKER_SERVICE_UUID, bed_types={BED_TYPE_SLEEPTRACKER}, connectable=True
)
