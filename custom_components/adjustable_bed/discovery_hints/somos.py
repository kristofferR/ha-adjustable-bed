"""Somos candidates, case-sensitive and never a product selection."""

from ..const import BED_TYPE_SOMOS
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(
        "base-i5",
        "KSBT03C3",
        "KSBT03CR",
        bed_types={BED_TYPE_SOMOS},
        anywhere=True,
        connectable=True,
    ),
)
