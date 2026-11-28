"""Only the accepted Smart Base name route is offered for explicit setup."""

from ..profiles.smart_base import NAME
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(NAME, bed_types={"smart_base"}, packet_name_only=True),)
