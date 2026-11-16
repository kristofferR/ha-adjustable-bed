"""Linx current setup's case-sensitive KSWF07D substring, unit079 E14."""

from ..const import BED_TYPE_LINX
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names("KSWF07D", bed_types={BED_TYPE_LINX}, anywhere=True, connectable=True),
)
