"""Sven app candidates share names with other Richmat apps."""

from ..profiles.sven import PREFIXES
from ._hints import NameHint

HINTS = (NameHint(patterns=PREFIXES, bed_types=frozenset({"sven"})),)
