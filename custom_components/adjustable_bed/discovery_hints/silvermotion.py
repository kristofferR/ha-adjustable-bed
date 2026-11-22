"""SILVERmotion Android scans manufacturer data without a name or service filter."""

from ..codec.silvermotion import MANUFACTURER
from ._hints import Hint, manufacturer

HINTS: tuple[Hint, ...] = (manufacturer(MANUFACTURER, bed_types={"silvermotion"}),)
