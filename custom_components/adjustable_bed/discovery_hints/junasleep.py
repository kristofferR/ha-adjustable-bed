"""JunaSleep candidates; shared names never select a remote layout."""

from ..const import BED_TYPE_JUNASLEEP
from ._hints import Case, Hint, names

HINTS: tuple[Hint, ...] = (
    names("KSBT02C", bed_types={BED_TYPE_JUNASLEEP}, anywhere=True, connectable=True),
    names("base", bed_types={BED_TYPE_JUNASLEEP}, case=Case.IGNORE_CASE, anywhere=True, connectable=True),
)
