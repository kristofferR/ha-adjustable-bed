"""Active Sleep registration list uses this exact case-sensitive prefix."""

from ._hints import NameHint

HINTS = (NameHint(patterns=("Active",), bed_types=frozenset({"active_sleep"})),)
