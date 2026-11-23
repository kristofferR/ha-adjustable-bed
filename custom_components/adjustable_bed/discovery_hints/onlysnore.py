"""BED name and manufacturer must both pass the app predicate in detection."""

from ._hints import manufacturer

HINTS = (manufacturer(89, bed_types={"onlysnore"}),)
