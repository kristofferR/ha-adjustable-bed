"""Cosyworld shares FFE0 with other apps; detection offers an explicit choice."""

from ..const import BED_TYPE_COSYWORLD
from ..profiles.cosyworld import SERVICE
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = services(SERVICE, bed_types={BED_TYPE_COSYWORLD})
