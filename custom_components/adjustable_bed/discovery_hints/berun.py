"""BERUN shared-name candidates require explicit app selection."""
from ._hints import SMARTBED, Case, names

HINTS = (names("okin", bed_types={"berun"}, case=Case.FOLD),
         names(*SMARTBED, bed_types={"berun"}, connectable=True))
