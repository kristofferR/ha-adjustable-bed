"""Typed internal envelopes for named Motion Bed configuration services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .motion_bed_state import MotionBedContext

RequestName = Literal[
    "alarm", "clock", "sleep_angles", "calibration", "sleep_timer", "sleep_report",
    "module", "air_setting", "pressure", "thermal_schedule", "audio",
]

@dataclass(frozen=True, slots=True)
class MotionBedWrite:
    name: RequestName
    frames: tuple[bytes, ...]
    context: MotionBedContext
    confirmed: bool = False
    persistent: bool = False
    initial_delay_ms: int = 0
    report_offset: int = 0
    historical_day: bool = False
    alarm_audio: bool | None = None
    alarm_switch: int | None = None
