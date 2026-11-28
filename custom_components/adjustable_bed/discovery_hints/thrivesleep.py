"""Shared current-app scan substrings, not evidence of a particular product."""

from ._hints import Hint, names

HINTS: tuple[Hint, ...] = tuple(
    names(word, bed_types={"thrivesleep"}, anywhere=True, packet_name_only=True)
    for word in ("QRRM", "COOL", "MPE_", "209A", "BED-")
)
