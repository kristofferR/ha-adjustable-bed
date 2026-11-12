"""M Line name candidates. Shared names require choosing the app in setup."""

from ._hints import Case, names

HINTS = (names("SLEEP", "OKIN", bed_types={"mline"}, case=Case.ANY, anywhere=True),
         names("SMARTBED", bed_types={"mline"}, case=Case.ANY, anywhere=True, connectable=True))
