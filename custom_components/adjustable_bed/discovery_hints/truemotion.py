"""The ASCII scan prefix is an app hint, shared with SUTA Smart Home."""

from ..const import BED_TYPE_TRUEMOTION
from ..profiles.truemotion import PREFIX
from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (names(PREFIX, bed_types={BED_TYPE_TRUEMOTION}),)
