"""M Line name candidates. Shared names require choosing the app in setup."""

from ._hints import SMARTBED, Case, names

HINTS = (names("OKIN", bed_types={"mline"}, case=Case.FOLD, anywhere=True),
         names(*SMARTBED, bed_types={"mline"}, anywhere=True, connectable=True))
