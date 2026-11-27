"""MySide caller projections and bounded complete-frame replies, using Richmat."""

from dataclasses import dataclass, replace
from typing import Literal

from ...codec import richmat as codec


@dataclass(frozen=True, slots=True)
class Alarm:
    number: int
    unknown: int
    hour: int
    minute: int
    opcode: int
    repeat: int

    def frame(self) -> bytes:
        return codec.record(
            5, 1, 1, (self.number, self.unknown, self.hour, self.minute, self.opcode, self.repeat)
        )

    def enabled(self, enabled: bool) -> Alarm:
        return replace(self, repeat=self.repeat & 0xFE | int(enabled))

    def attributes(self) -> dict[str, int | bool]:
        return {
            "number": self.number,
            "unknown": self.unknown,
            "hour": self.hour,
            "minute": self.minute,
            "opcode": self.opcode,
            "repeat": self.repeat,
            "enabled": bool(self.repeat & 1),
        }


@dataclass(frozen=True, slots=True)
class Reply:
    event: Literal["alarm_list", "alarm_update", "sleep_name"]
    alarm: Alarm | None = None
    name: str | None = None


def parse(data: bytes) -> Reply | None:
    """Only the accepted alarm/name subset; unrelated packets cannot add features."""
    if (
        len(data) < 8
        or data[:2] != b"\x6e\x20"
        or data[2] != len(data)
        or not codec.is_valid(data)
        or data[4] != 1
    ):
        return None
    if data[3] == 5 and data[5] in (2, 3) and len(data) == 13:
        return Reply("alarm_list" if data[5] == 2 else "alarm_update", Alarm(*data[6:12]))
    if data[3] == 6 and data[5] == 3:
        return Reply("sleep_name", name="".join(chr(x) for x in data[7:-1]))
    return None


def repeat_mask(days: tuple[int, ...], enabled: bool) -> int:
    """Weekdays use Monday=0 through Sunday=6; the empty set means once."""
    return int(enabled) | sum(1 << (7 - day) for day in set(days))


ALARM_QUERY = codec.record(5, 1, 0, (0,))
NAME_QUERY = codec.record(6, 3, 0, (0,))
