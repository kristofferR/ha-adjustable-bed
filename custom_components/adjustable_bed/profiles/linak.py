"""App-specific data for the shared Linak control codec."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class LinakAppProfile:
    key: str = "carpe_diem"
    hold_interval_ms: int = 300
    favorite_initial_delay_ms: int = 25
    favorite_interval_ms: int = 200
    massage_zone_gap_s: float = 0.1
    memory_opcodes: tuple[int, ...] = (0x0E, 0x0F, 0x0C, 0x44)
    save_opcodes: tuple[int, ...] = (0x38, 0x39, 0x3A, 0x45)


CARPE_DIEM: Final = LinakAppProfile()


@dataclass(frozen=True, slots=True)
class TempurRelaxProfile(LinakAppProfile):
    name_code_units: int = 17
    alarm_recurrence_minutes: int = 1440
    alarm_recurrence_count: int = 31
    alarm_action_lifetime: int = 5
    alarm_action_pause: int = 0
    alarm_massage_opcode: int = 0x91


# Tempur Relax Control 6.1.3 (269), accepted full A79 static contracts.
TEMPUR_RELAX: Final = TempurRelaxProfile(
    key="tempur_relax", hold_interval_ms=100,
    favorite_initial_delay_ms=0, favorite_interval_ms=100, massage_zone_gap_s=0.1,
    memory_opcodes=(0x0E, 0x0F, 0x0C, 0x44), save_opcodes=(0x38, 0x39, 0x3A, 0x45),
)


def tempur_advertisement_allowed(manufacturer_data: dict[int, bytes] | None) -> bool:
    """The current app filters the first SparseArray manufacturer value."""
    from ..codec.linak import ArtifactParseError, manufacturer_product

    data = manufacturer_data or {}
    try:
        return bool(manufacturer_product(data[min(data)] if data else None)["accepted"])
    except ArtifactParseError:
        # HA rejects malformed metadata rather than exposing a failed scanner.
        return False


def tempur_release_frame(*, alarm: bool, td3: bool, favorite: bool, automatic: bool) -> bytes | None:
    """The admitted gesture's primary-selected cleanup, not a physical STOP claim."""
    from ..codec.linak import control_frame

    if favorite and (td3 or automatic):
        return None
    return control_frame(0xFE if alarm or td3 else 0xFF)
