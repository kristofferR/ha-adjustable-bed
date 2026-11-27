"""King Koil's case-sensitive contains scan, shared names require app selection."""

from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names("KSBT03CK", "KSBT03CL", bed_types={"kingkoil"}, anywhere=True, connectable=True),
)
