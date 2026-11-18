"""Personal Comfort candidates, never inferred capabilities for shared bases."""

from ..codec.personal_comfort import RA_SERVICE
from ._hints import names, services

HINTS = (
    names("ANM-", bed_types={"personal_comfort"}),
    *services(RA_SERVICE, bed_types={"personal_comfort"}),
)
