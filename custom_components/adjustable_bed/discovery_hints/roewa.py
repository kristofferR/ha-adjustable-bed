"""RÖWA scan alternatives; generic Device Information alone cannot identify a bed."""

from ..profiles.roewa import NAME_SERVICE_UUID, SERVICE_UUID
from ._hints import ServiceHint

HINTS = tuple(
    ServiceHint(uuid=uuid, bed_types=frozenset({"roewa"}))
    for uuid in (SERVICE_UUID, NAME_SERVICE_UUID)
)
