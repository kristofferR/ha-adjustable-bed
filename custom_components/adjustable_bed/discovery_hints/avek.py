"""AVEK's case-sensitive API21+ name prefixes, never generic Nordic UART."""

from ..profiles.avek import AVEK
from ._hints import NameHint

HINTS = (NameHint(patterns=AVEK.name_prefixes, bed_types=frozenset({AVEK.key})),)
