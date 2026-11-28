"""Shipped fallback data from Active Sleep 1.3.5, never a live product catalog."""

from dataclasses import dataclass
from typing import Final

from ..codec.active_sleep import Posture
from ..execution import ExecutionCapabilities

AUTH_ID: Final = "active_sleep_auth_id"
BED_TEMPLATES: Final[tuple[Posture, ...]] = (
    (70, 5, 30, 255),
    (6, 6, 30, 255),
    (8, 8, 30, 255),
    (10, 10, 30, 255),
    (12, 12, 30, 255),
    (14, 14, 30, 255),
    (21, 9, 30, 255),
    (22, 12, 30, 255),
    (20, 5, 30, 255),
    (0, 0, 255, 3),
)
MATTRESS_TEMPLATES: Final = (
    ((5, 5, 5, 1, 1, 1), 3),
    ((2, 4, 3, 2, 1, 6), 5),
    ((3, 3, 4, 1, 3, 1), 1),
    ((4, 2, 1, 2, 1, 1), 11),
    ((5, 1, 5, 1, 1, 4), 12),
)


@dataclass(frozen=True, slots=True)
class ActiveSleepProfile:
    key: str = "active_sleep"
    interval_ms: int = 200
    manual_delay_ms: int = 50
    preset_delay_ms: int = 250
    response_timeout_ms: int = 50
    no_change_ms: int = 2000
    reached_stop_ms: int = 1000
    realtime_ms: int = 100
    # HA transport bounds, not bed timing or replay instructions.
    query_timeout_s: float = 5
    execution: ExecutionCapabilities = ExecutionCapabilities(hold="stream")


ACTIVE_SLEEP: Final = ActiveSleepProfile()
