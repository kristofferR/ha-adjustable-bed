"""Ultramatic UART app's name gate, which ignores case; detection checks data."""

from ..const import BED_TYPE_ULTRAMATIC_SMART_BED
from ._hints import SMARTBED, names

HINTS = (
    names(*SMARTBED, bed_types={BED_TYPE_ULTRAMATIC_SMART_BED}, connectable=True),
)
