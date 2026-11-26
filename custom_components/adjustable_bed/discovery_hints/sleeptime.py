"""Sleeptime app name prefixes on the shared Nordic UART transport."""

from ..const import BED_TYPE_SLEEPTIME
from ..profiles.sleeptime import PREFIXES
from ._hints import Case, names

HINTS = (names(*PREFIXES, bed_types={BED_TYPE_SLEEPTIME}, case=Case.IGNORE_CASE, connectable=True),)
