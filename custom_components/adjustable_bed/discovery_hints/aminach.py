"""The Platinum app accepts an exact, case-sensitive AMB2 name prefix."""

from ..profiles.aminach import NAME_PREFIX
from ._hints import NameHint

HINTS = (NameHint(patterns=(NAME_PREFIX,), bed_types=frozenset({"aminach"})),)
