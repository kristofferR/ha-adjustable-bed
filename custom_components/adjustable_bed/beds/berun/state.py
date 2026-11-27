"""BERUN event-local status parsing. No checksum or fragment reassembly is implied."""

from dataclasses import dataclass, replace
from typing import Final

from ...controller_state import StateKey

HEAD: Final = StateKey[int | None]("berun_head_massage")
FOOT: Final = StateKey[int | None]("berun_foot_massage")
TIMER: Final = StateKey[int | None]("berun_massage_timer_index")
MODE: Final = StateKey[int | None]("berun_massage_mode")
MASSAGE: Final = StateKey[bool | None]("berun_massage_on")
ALARM: Final = StateKey[str | None]("berun_alarm")
ALARM_DETAIL: Final = StateKey[dict[str, object] | None]("berun_alarm_detail")
ALARM_ON: Final = StateKey[bool | None]("berun_alarm_on")


@dataclass(frozen=True, slots=True)
class Massage:
    time: int = 0
    head: int = 0
    foot: int = 0
    mode: int = 0
    isOn: bool = False


@dataclass(frozen=True, slots=True)
class Alarm:
    hour: int = 0
    minute: int = 0
    days: int = 0
    action: str | None = None
    on: bool = False

    def detail(self) -> dict[str, object]:
        return {
            "enabled": self.on,
            "wake_action": self.action,
            "day_mask": self.days,
            "recurring": bool(self.days & 128),
            "weekdays": [
                name
                for day, name in enumerate(
                    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
                    1,
                )
                if self.days & 128 and self.days & (1 << (day % 7))
            ],
        }


class Replies:
    def __init__(self) -> None:
        self.alarm = Alarm()

    def feed(self, version: int, data: bytes) -> Massage | Alarm | None:
        if len(data) < 3:
            return None
        text = data.hex()
        if data.startswith(b"\xed\xfe\x16"):
            # The app parses these four nibbles as decimal, not hexadecimal.
            # Missing/invalid nibbles would be NaN in JS; HA publishes no fake value.
            if len(text) < 30 or any(text[i] not in "0123456789" for i in (15, 17, 28)):
                return None
            time = int(text[29]) if text[29].isdigit() else 0
            time = time if time <= 3 else 0
            mode = int(text[28])
            mode = mode if mode < 4 else 0
            head, foot = int(text[15]), int(text[17])
            head, foot = (n // 3 + 1 if n >= 3 else n for n in (head, foot))
        elif data.startswith(b"\xf4\xfe\x16"):
            if len(data) < 22:
                return None
            time = data[19] & 15
            if text[29] == "f" or time > 3:
                time = 0
            mode = data[21] if data[21] < 4 else 0
            head, foot = (n // 3 + 1 if n >= 3 else n for n in (data[11] & 15, data[12]))
        elif data.startswith(b"\xa5\x0b\x0e"):
            if len(data) < 9:
                return None
            seconds = int.from_bytes(data[4:6], "big")
            time = 0 if not seconds else 1 if seconds <= 600 else 3 if seconds <= 1200 else 6
            mode = data[6] if data[6] < 4 else 0
            head, foot = data[7] & 15, data[8]
        elif data.startswith(b"\xed\x80\x03"):
            if len(data) < 7:
                return None
            if not data[6]:
                self.alarm = replace(self.alarm, on=False)
            else:
                self.alarm = Alarm(
                    data[3],
                    data[4],
                    data[5],
                    {9: "massage", 17: "memory", 13: "zero_g", 28: "read"}.get(data[6]),
                    True,
                )
            return self.alarm
        elif data.startswith(b"\xa5\x0c\x0e"):
            if len(data) < 10:
                return None
            if not data[9]:
                self.alarm = replace(self.alarm, on=False)
            else:
                self.alarm = Alarm(
                    data[6],
                    data[7],
                    data[4],
                    {8: "massage", 5: "memory", 1: "zero_g", 2: "read", 3: "tv"}.get(data[5]),
                    True,
                )
            return self.alarm
        else:
            # a55a is log-only, including its exact 14-byte reply.
            return None
        if version >= 8:
            on = bool(time or head or foot)
            time = 0 if time <= 2 else 1 if time <= 4 else 2
            head, foot = ((n + 1) // 2 for n in (head, foot))
        else:
            time = max(time - 1, 0)
            on = bool(time or head or foot)
        return Massage(time, head, foot, mode, on)
