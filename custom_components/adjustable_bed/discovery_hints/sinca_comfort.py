"""Shared write carriers are hints only. Discovery also needs an admitted name."""

from ..codec import mline as wire
from ._hints import services

HINTS = (
    *services(wire.NORDIC_SERVICE, bed_types={"sinca_comfort"}, connectable=True),
    *services(wire.FFE_SERVICE, bed_types={"sinca_comfort"}),
)
