"""Saatva's shared UUID candidates require an explicit app/model choice."""

from ..profiles.saatva import SCAN_UUIDS
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(*SCAN_UUIDS, bed_types={"saatva"})
