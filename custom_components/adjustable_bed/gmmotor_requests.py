"""Finite direct BLE GM Control operations exposed to Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

type Operation = Literal[
    "clock_sync",
    "alarm",
    "alarm_at",
    "alarm_cancel",
    "repeat_alarm",
    "repeat_delete",
    "repeat_query",
    "light_color",
    "light_timeout",
    "light_off",
    "snore_enabled",
    "snore_count",
    "snore_time",
    "snore_query",
    "sleep_name",
    "refresh",
    "massage_timer",
    "sensor_time",
    "sensor_part",
    "sensor_query_part",
    "sensor_live",
    "sensor_report",
    "sensor_sensitivity",
    "sensor_stop",
    "desk_height",
    "desk_unit",
    "desk_query",
]


@dataclass(frozen=True, slots=True)
class Request:
    """Validated scalar fields; model/capability admission belongs to controller."""

    operation: Operation
    value: int = 0
    mode: str = ""
    slot: int = 1
    repeat: int = 0
    hour: int = 0
    minute: int = 0
    status: int = 1
    enabled: bool = True
    rgb: tuple[int, int, int] = (0, 0, 0)
    part: int = 1
    report_type: int = 1
    report_date: date | None = None
    height: float = 60.0
    unit: Literal["cm", "inch"] = "cm"

    def __post_init__(self) -> None:
        for name, maximum in (
            ("value", 65535),
            ("slot", 255),
            ("repeat", 255),
            ("hour", 23),
            ("minute", 59),
            ("status", 255),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(f"Invalid GM Control {name}")
        if any(type(value) is not int or not 0 <= value <= 255 for value in self.rgb):
            raise ValueError("Invalid GM Control RGB component")
        if len(self.rgb) != 3 or type(self.enabled) is not bool:
            raise ValueError("Invalid GM Control color or enable flag")
        if self.operation in ("snore_count", "snore_time") and self.value > 255:
            raise ValueError("Anti-snore quantity exceeds one byte")
        if type(self.part) is not int or self.part not in (1, 2):
            raise ValueError("Select the left or right report part")
        if type(self.report_type) is not int or self.report_type not in (1, 2):
            raise ValueError("Select a day or month report")
        if type(self.height) not in (int, float) or not 0 <= self.height <= 2559.999:
            raise ValueError("Invalid desk height")
        if self.unit not in ("cm", "inch"):
            raise ValueError("Select centimetres or inches")
