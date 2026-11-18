"""Dawn House's case-sensitive name scan; GATT UUIDs need not be advertised."""

from ._hints import names

HINTS = (names("KSWF07S", "KSWF19S", bed_types={"agingplace"}, anywhere=True, connectable=True),)
