"""Linx 1.0.7 setup scans for the case-sensitive KSWF07D substring."""

from ..const import BED_TYPE_LINX
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names("KSWF07D", bed_types={BED_TYPE_LINX}, anywhere=True, connectable=True),
)
