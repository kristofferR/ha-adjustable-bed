"""The app's case-sensitive substring, independent of product metadata."""

from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names("QRRM", bed_types={"super_colchones"}, anywhere=True),)
