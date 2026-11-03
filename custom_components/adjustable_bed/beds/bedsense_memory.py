"""Ordered app memory-indicator rules from HHKuaiJieFragment:691-919.

These describe app indicators, not independently confirmed hardware state.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class MemoryRule:
    pattern: str
    exact: bool
    required_n: int | None
    excluded: tuple[str, ...]
    excluded_exact: bool
    slot: int
    saved: bool
    next_n: int | None


MEMORY_RULES: Final = (
    MemoryRule("00 A5", False, None, (), False, 3, True, None),
    MemoryRule("00 A9", False, None, (), False, 4, True, None),
    MemoryRule("00 AA", False, None, (), False, 1, True, None),
    MemoryRule("00 AB", False, None, (), False, 2, True, None),
    MemoryRule("00 AF", False, None, ("FF FF FF FF 05 00 00 AF 0A 2A F7 ",), True, 5, True, None),
    MemoryRule("FF FF FF FF 05 00 00 A0 0A 2F 07 ", True, None, (), False, 1, True, None),
    MemoryRule("FF FF FF FF 05 00 00 AF 0A 2A F7 ", True, None, (), False, 1, False, None),
    MemoryRule("FF FF FF FF 05 00 00 B0 0B E3 07 ", True, None, (), False, 2, True, None),
    MemoryRule("FF FF FF FF 05 00 00 BF 0B E6 F7 ", True, None, (), False, 2, False, None),
    MemoryRule("FF FF FF FF 05 00 00 50 05 2B 03 ", True, None, (), False, 3, True, None),
    MemoryRule("FF FF FF FF 05 00 00 5F 05 2E F3 ", True, None, (), False, 3, False, None),
    MemoryRule("FF FF FF FF 05 00 00 90 09 7B 06 ", True, None, (), False, 4, True, None),
    MemoryRule("FF FF FF FF 05 00 00 9F 09 7E F6 ", True, None, (), False, 4, False, None),
    MemoryRule("FF FF FF FF 05 00 00 F0 0F D3 04 ", False, None, (), False, 5, True, None),
    MemoryRule("FF FF FF FF 05 00 00 FF 0F D6 F4 ", True, None, (), False, 5, False, None),
    MemoryRule("FF FF FF FF 03 00 24 00 03 5F 0A ", False, None, (), False, 1, False, 1),
    MemoryRule("00 0A ", False, 1, (), False, 1, True, None),
    MemoryRule("FF FF FF FF 03 00 28 00 03 9F 09 ", False, None, (), False, 1, False, 2),
    MemoryRule("00 0A ", False, 2, (), False, 1, True, None),
    MemoryRule("FF FF FF FF 03 00 2C 00 03 DE C8 ", False, None, (), False, 2, False, 3),
    MemoryRule("00 0B ", False, 3, (), False, 2, True, None),
    MemoryRule("FF FF FF FF 03 00 31 00 09 CE C9 ", False, None, (), False, 2, False, 11),
    MemoryRule("00 0B ", False, 11, (), False, 2, True, None),
    MemoryRule("FF FF FF FF 03 00 30 00 03 1F 0E ", False, None, (), False, 2, False, 4),
    MemoryRule("00 0B ", False, 4, (), False, 2, True, None),
    MemoryRule("FF FF FF FF 03 00 14 00 03 5F 05 ", False, None, (), False, 3, False, 5),
    MemoryRule("00 05 ", False, 5, (), False, 3, True, None),
    MemoryRule("FF FF FF FF 03 00 16 00 09 7E C2 ", False, None, (), False, 3, False, 15),
    MemoryRule("00 05 ", False, 15, (), False, 3, True, None),
    MemoryRule("FF FF FF FF 03 00 18 00 03 9F 06 ", False, None, (), False, 3, False, 6),
    MemoryRule("00 05 ", False, 6, (), False, 3, True, None),
    MemoryRule("FF FF FF FF 03 00 1C 00 03 DE C7 ", False, None, (), False, 4, False, 7),
    MemoryRule("00 09 ", False, 7, (), False, 4, True, None),
    MemoryRule("FF FF FF FF 03 00 1F 00 09 AE C0 ", False, None, (), False, 4, False, 14),
    MemoryRule("00 09 ", False, 14, ("BF 0B ", "AE C0 ", "7E C2 "), False, 4, True, None),
    MemoryRule("FF FF FF FF 03 00 20 00 03 1E CB ", False, None, (), False, 4, False, 8),
    MemoryRule("00 09 ", False, 8, (), False, 4, True, None),
    MemoryRule("FF FF FF FF 03 00 3A 00 09 BF 0B ", False, None, (), False, 5, False, 13),
    MemoryRule("00 0F ", False, 13, (), False, 5, True, None),
    MemoryRule("FF FF FF FF 03 00 38 00 03 9E CC ", False, None, (), False, 5, False, 9),
    MemoryRule("00 0F ", False, 9, (), False, 5, True, None),
)
