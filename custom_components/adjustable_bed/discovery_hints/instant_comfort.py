"""Instant Comfort candidates require an explicit app and controller choice."""

from ..codec.personal_comfort import RA_SERVICE
from ._hints import names, services

HINTS = (
    names("ANM-", bed_types={"instant_comfort"}),
    names("2618", bed_types={"instant_comfort"}),
    names("2816", bed_types={"instant_comfort"}),
    *services(RA_SERVICE, bed_types={"instant_comfort"}),
)
