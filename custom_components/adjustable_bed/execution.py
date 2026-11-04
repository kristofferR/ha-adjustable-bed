"""Execution capabilities a protocol is proven to support (#483, #516).

The scheduler, the cover platform and paired intersection read these facts. A
family profile declares them from its own app's accepted evidence; a
standalone controller overrides ``BedController.execution``. Every declaration
needs an evidence row in ``tests/test_execution_capabilities.py``, which maps
it to its key in ``docs/design/execution-capabilities.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

HoldMode = Literal["stream", "latched"]
HOLD_MODES: Final[frozenset[str]] = frozenset({"stream", "latched"})


@dataclass(frozen=True, kw_only=True)
class ExecutionCapabilities:
    """How a controller may execute held and concurrent motion.

    The empty default keeps today's behavior: finite pulses, one motor
    operation at a time. ``auto_stops_on_idle`` stays the separate cleanup
    question of whether a release frame may be skipped.
    """

    hold: HoldMode | None = None
    """Open-ended hold until release; None keeps finite pulses."""
    sustain_ms: int | None = None
    """Measured motion one frame buys. None when unproven."""
    concurrent: frozenset[str] = field(default_factory=frozenset)
    """Motor resources that may run in one window. Empty means serialized."""

    def __post_init__(self) -> None:
        if self.hold is not None and self.hold not in HOLD_MODES:
            raise ValueError(f"Unknown hold mode {self.hold!r}")
        if self.sustain_ms is not None:
            if self.hold is None:
                raise ValueError("sustain_ms describes a hold; declare hold first")
            if isinstance(self.sustain_ms, bool) or self.sustain_ms <= 0:
                raise ValueError("sustain_ms must be a positive number of milliseconds")
        if not isinstance(self.concurrent, frozenset):
            raise TypeError("concurrent must be a frozenset of motor resources")
        if any(not isinstance(item, str) or not item for item in self.concurrent):
            raise ValueError("concurrent motor resources must be non-empty strings")
        if len(self.concurrent) == 1:
            raise ValueError("concurrent motion needs at least two motor resources")

    @property
    def hold_ceiling_ms(self) -> int | None:
        """Longest one renewable hold may run; None when no hold is declared."""
        if self.hold is None:
            return None
        return LATCHED_HOLD_CEILING_MS if self.hold == "latched" else HOLD_CEILING_MS

    @property
    def declared(self) -> frozenset[str]:
        """Names of the capabilities this value declares, for evidence checks."""
        return frozenset(
            name
            for name, value in (
                ("hold", self.hold),
                ("sustain_ms", self.sustain_ms),
                ("concurrent", self.concurrent),
            )
            if value
        )


NO_EXECUTION_CAPABILITIES: Final = ExecutionCapabilities()
STREAM_HOLD: Final = ExecutionCapabilities(hold="stream")
"""The app refreshes a held frame until release, then sends its release frames."""

HOLD_CEILING_MS: Final = 30_000
"""The longest one renewable hold streams, however often its lease is renewed."""
LATCHED_HOLD_CEILING_MS: Final = 10_000
"""Ceiling of a latched hold, whose bed keeps moving until STOP arrives."""
