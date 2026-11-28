"""MattressPoint candidate names; app and model still require a choice."""

from ._hints import Case, names

HINTS = (names("smartbed", bed_types={"mattresspoint"}, case=Case.IGNORE_CASE, connectable=True),)
