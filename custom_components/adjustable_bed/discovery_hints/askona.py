"""Askona's name candidates, exact admission is checked by detection."""

from ._hints import names

HINTS = (names("base-i4", "base-i5", bed_types={"askona"}, connectable=True),)
