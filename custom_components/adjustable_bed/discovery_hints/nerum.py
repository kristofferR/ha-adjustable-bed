"""Nerum shared-name candidates require explicit app and transport selection."""

from ._hints import SMARTBED, Case, names

HINTS = (names("OKIN", bed_types={"nerum"}, case=Case.FOLD),
         names(*SMARTBED, bed_types={"nerum"}, connectable=True))
