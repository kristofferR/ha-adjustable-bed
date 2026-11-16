"""Nerum shared-name candidates require explicit app and transport selection."""

from ._hints import Case, names

HINTS = (names("OKIN", bed_types={"nerum"}, case=Case.ANY),
         names("SMARTBED", bed_types={"nerum"}, case=Case.ANY, connectable=True))
