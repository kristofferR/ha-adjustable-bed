"""SleepFunction's local fan and aroma settings, with no app-screen drafts."""

from dataclasses import dataclass
from typing import Literal

from ...errors import invalid
from .protocol import aroma, direct


@dataclass(frozen=True, slots=True)
class Settings:
    operation: Literal["head_fan", "foot_fan", "aroma"]
    hours: int | None = None
    speed: int | None = None
    mode_2_minutes: int | None = None
    mode_3_minutes: int | None = None
    pause_hours: int | None = None

    def frames(self) -> tuple[bytes, ...]:
        if self.operation == "aroma":
            values = (self.mode_2_minutes, self.mode_3_minutes, self.pause_hours)
            if any(
                type(v) is not int or not 1 <= v <= limit
                for v, limit in zip(values, (60, 60, 12), strict=True)
            ):
                raise invalid("sleepfunction_control")
            assert all(v is not None for v in values)
            return tuple(
                aroma(op, v) for op, v in zip((27, 28, 29), values, strict=True) if v is not None
            )
        if (
            self.operation not in ("head_fan", "foot_fan")
            or type(self.hours) is not int
            or not 0 <= self.hours <= 6
            or self.speed not in (0, 20, 40, 60, 80, 100)
            or type(self.speed) is not int
        ):
            raise invalid("sleepfunction_control")
        volume = 215 + self.speed // 20
        # The foot route actually sends its volume twice, without its time.
        return (
            (direct(1, 208 + self.hours), direct(1, volume))
            if self.operation == "head_fan"
            else (direct(1, 1, volume),) * 2
        )
