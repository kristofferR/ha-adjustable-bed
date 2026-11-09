"""Separate Smart Comfort app profiles over the cluster-024 seat codec.

Accepted static evidence: com.synargy.okin 1.1.0 (12), com.synergy.okin 2.2.0
(16). Shared wire actions do not establish full app/firmware equivalence.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import smart_comfort as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities

HELD: Final = (
    "head_up",
    "head_down",
    "reclining_up",
    "reclining_down",
    "lumbar_up",
    "lumbar_down",
    "home",
)


@dataclass(frozen=True)
class SmartComfortProfile:
    key: str
    package: str
    version: str
    notify_delay_ms: int | None
    refresh_ms: int = 100
    release_ms: int = 100
    system_timeout_ms: int = 2500
    execution: ExecutionCapabilities = STREAM_HOLD

    @property
    def frames(self) -> dict[str, bytes]:
        return {
            name: codec.command(name)
            for name in (
                *codec.MOTORS,
                *codec.ACCESSORIES,
                "base_brightness",
                "read_brightness",
                "color",
                "query_system",
                "query_device",
            )
        }


SYNARGY: Final = SmartComfortProfile("synargy", "com.synargy.okin", "1.1.0 (12)", 500)
SYNERGY: Final = SmartComfortProfile("synergy", "com.synergy.okin", "2.2.0 (16)", None)
PROFILES: Final = {p.key: p for p in (SYNARGY, SYNERGY)}
