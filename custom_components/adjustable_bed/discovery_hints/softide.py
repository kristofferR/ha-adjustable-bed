"""Softide's shared A00A service and case-sensitive KSWF16S substring."""

from ..profiles.softide import NAME, SERVICE
from ._hints import Hint, ServiceHint, names

HINTS: tuple[Hint, ...] = (
    names(NAME, bed_types={"softide"}, anywhere=True, connectable=True),
    ServiceHint(uuid=SERVICE, bed_types=frozenset({"softide"}), connectable=True),
)
