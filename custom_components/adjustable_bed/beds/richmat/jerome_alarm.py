"""Jerome repeat alarm records over the shared Richmat codec."""

from dataclasses import dataclass, replace
from typing import Self

from ...alarm import WEEKDAYS
from ...codec import richmat as codec
from ..richmat_app.protocol import repeat_alarm, repeat_mask


@dataclass(frozen=True, slots=True)
class RepeatAlarm:
    slot: int
    raw_7: int
    hour: int
    minute: int
    action: int
    repeat: int

    @classmethod
    def decode(cls, frame: bytes) -> tuple[int, Self] | None:
        if (
            len(frame) != 13
            or frame[:5] != b"\x6e\x20\x0d\x05\x01"
            or frame[5] not in (2, 3)
            or not codec.is_valid(frame)
        ):
            return None
        return frame[5], cls(*frame[6:12])

    @classmethod
    def edited(cls, slot: int, hour: int, minute: int, action: int, days: tuple[int, ...]) -> Self:
        return cls(slot, 0, hour, minute, action, repeat_mask(days))

    def with_enabled(self, enabled: bool) -> Self:
        return replace(self, repeat=(self.repeat & 0xFE) | int(enabled))

    def encode(self) -> bytes:
        return repeat_alarm(self.slot, self.raw_7, self.hour, self.minute, self.action, self.repeat)

    def attributes(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "hour": self.hour,
            "minute": self.minute,
            "action_code": self.action,
            "enabled": bool(self.repeat & 1),
            "weekdays": [day for i, day in enumerate(WEEKDAYS) if self.repeat & (0x80 >> i)],
        }
