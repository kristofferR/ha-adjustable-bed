"""Flexispot's cached-name substring does not identify its product."""

from ..const import BED_TYPE_FLEXISPOT
from ..profiles.flexispot import NAME
from ._hints import names

HINTS = (names(NAME, bed_types={BED_TYPE_FLEXISPOT}, anywhere=True, connectable=True),)
