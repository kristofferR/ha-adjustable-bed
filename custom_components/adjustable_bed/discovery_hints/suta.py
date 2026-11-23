"""SUTA uses its case-sensitive advertised name, never a shared service alone."""

from ..const import BED_TYPE_SUTA
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names("SUTA", bed_types={BED_TYPE_SUTA}),
)
