"""Session-owned, bounds-checked Nerum replies; source defects are not wire rules."""

from dataclasses import dataclass
from typing import Final

from ...controller_state import StateKey
from ...profiles.nerum import WAKE, Alarm, Protocol

HEAD: Final = StateKey[int]("nerum_head_massage")
FOOT: Final = StateKey[int]("nerum_foot_massage")
MINUTES: Final = StateKey[int]("nerum_minutes")
WAVE: Final = StateKey[int]("nerum_wave")
MASSAGE: Final = StateKey[bool]("nerum_massage")
# Each alarm sensor shows its HH:MM time; the rest of the record is attributes.
ALARM_KEYS: Final = tuple(StateKey[str](f"nerum_alarm_{slot}") for slot in (1, 2, 3))
ALARM_DETAIL_KEYS: Final = tuple(
    StateKey[dict[str, object]](f"nerum_alarm_{slot}_detail") for slot in (1, 2, 3)
)
_DAYS: Final = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
_ACTIONS: Final = {code: action for action, code in WAKE.items()}


def alarm_detail(alarm: Alarm) -> dict[str, object]:
    """Describe a received alarm record in user terms."""
    return {
        "enabled": alarm.on,
        "days": [day for bit, day in enumerate(_DAYS) if alarm.repeat & (1 << bit)],
        "recurring": bool(alarm.repeat & 0x80),
        "action": _ACTIONS.get(alarm.kind),
    }


def signed(value: int) -> int:
    return value if value < 128 else value - 256


@dataclass(frozen=True, slots=True)
class Status:
    head: int | None = None
    foot: int | None = None
    minutes: int | None = None
    wave: int | None = None
    light: bool | None = None
    massage: bool | None = None


@dataclass(frozen=True, slots=True)
class Operation:
    value: int


class Replies:
    """R1 prefixes publish nothing; consume bounded partials once per connection.

    Android retains relaData globally, including across devices, and can index
    admitted short alarm buffers out of bounds. HA rejects those inputs. It
    also refuses unsupported assembled lengths instead of publishing zeros.
    """

    def __init__(self) -> None:
        self.pending: bytes | None = None

    def feed(
        self, protocol: Protocol, data: bytes
    ) -> Status | Operation | tuple[tuple[int, Alarm], ...] | None:
        if protocol == "p1":
            if len(data) < 7 or data[0] != 0xA5 and data[1] != 0x5A:
                return None
            opcode = (signed(data[5]) << 8) + signed(data[6])
            if opcode == 0x2050 and len(data) >= 14:
                return Status(
                    signed(data[8]),
                    signed(data[9]),
                    {1: 10, 2: 20, 3: 30}.get(signed(data[10]), 0),
                    signed(data[11]),
                    signed(data[12]) > 0,
                    signed(data[13]) > 0,
                )
            value = {0x2060: 5, 0x2061: 3, 0x2062: 6, 0x2063: 2, 0x2064: 4}.get(opcode)
            # Canonical 20 80..95 do not reach the source's single-update switch.
            if len(data) >= 9:
                field = signed(data[8])
                if opcode == 0x2080:
                    return Status(light=field > 0)
                if opcode == 0x2081:
                    return Status(massage=field > 0)
                if opcode == 0x2082:
                    return Status(minutes=field)
                if opcode in (0x2083, 0x2090, 0x2091):
                    return Status(wave=field)
                if opcode in (0x2084, 0x2092, 0x2093):
                    return Status(head=field)
                if opcode in (0x2085, 0x2094, 0x2095):
                    return Status(foot=field)
            return Operation(value) if value is not None else None
        if protocol == "p3":
            if len(data) < 10 or data[1] not in (12, 13, 14):
                return None
            hour, minute = signed(data[6]), signed(data[7])
            if not 0 <= hour <= 23 or not 0 <= minute <= 59:
                return None
            return (
                (
                    data[1] - 11,
                    Alarm(
                        hour,
                        minute,
                        data[4],
                        {5: 17, 6: 19, 7: 18, 8: 9}.get(data[5], 0),
                        data[9] == 1,
                    ),
                ),
            )
        if not data or len(data) > 512:
            self.pending = None
            return None
        if len(data) <= 20:
            if len(data) > 3 and data[:3] == b"\xf4\xfe\x16":
                self.pending = data
                return None
            if len(data) not in (10, 16):
                previous, self.pending = self.pending, None
                if previous is None:
                    return None
                data = previous + data
            else:
                self.pending = None
        else:
            self.pending = None
        if data[:2] == b"\xed\x80":
            if len(data) < 15:
                return None
            bank = tuple(
                (
                    i + 1,
                    Alarm(
                        data[3 + i * 4],
                        data[4 + i * 4],
                        data[5 + i * 4],
                        data[6 + i * 4],
                        data[5 + i * 4] != 0,
                    ),
                )
                for i in range(3)
            )
            return bank if all(a.hour <= 23 and a.minute <= 59 for _, a in bank) else None
        if len(data) == 23:
            timer, head, foot, wave = data[19], data[11] & 15, signed(data[12]), data[21]
        elif len(data) == 16:
            timer, head, foot, wave = data[14] & 15, data[7] & 15, data[8] & 15, data[14] >> 4
        elif len(data) == 10:
            timer, head, foot, wave = data[8], 0, 0, 0
        else:
            return None
        minutes = {1: 10, 2: 20, 3: 30}.get(timer, 0)
        strength = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
        return Status(
            strength.get(head, 0),
            strength.get(foot, 0),
            minutes,
            {1: 0, 2: 1, 3: 2, 4: 3}.get(wave, 0),
            None,
            bool(minutes),
        )
