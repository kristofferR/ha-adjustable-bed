"""App-specific data for the shared Linak control codec."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class CarpeDiemProfile:
    key: str = "carpe_diem"
    hold_interval_ms: int = 300
    favorite_initial_delay_ms: int = 25
    favorite_interval_ms: int = 200
    massage_zone_gap_s: float = 0.1
    memory_opcodes: tuple[int, ...] = (0x0E, 0x0F, 0x0C, 0x44)
    save_opcodes: tuple[int, ...] = (0x38, 0x39, 0x3A, 0x45)


CARPE_DIEM: Final = CarpeDiemProfile()
