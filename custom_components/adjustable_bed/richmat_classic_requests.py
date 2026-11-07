"""Typed public settings requests for cluster-018, never arbitrary bytes."""

from dataclasses import dataclass
from datetime import time
from typing import Literal

Operation = Literal[
    "query", "alarm", "cancel_alarm", "rgb", "lamp_slider", "lamp_save", "aroma",
    "massage_timer", "massage_popup", "desk_target", "desk_unit", "desk_recall", "desk_reset",
]


@dataclass(frozen=True, slots=True)
class Request:
    operation: Operation
    action: str | None = None
    when: time | None = None
    minutes: int | None = None
    color: tuple[int, int, int] | None = None
    aroma_values: tuple[int, int, int] | None = None
    progress: int | None = None
    height: float | None = None
    unit: Literal["cm", "inches"] | None = None
    slot: int | None = None
    duration_ms: int = 1000
    popup: str | None = None
