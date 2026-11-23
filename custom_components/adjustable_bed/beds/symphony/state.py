"""Source-qualified BED notifications, with atomic malformed-input rejection.

The app can throw after partially updating anti-snore state. HA rejects those
short packets before publishing anything. Fragmentation is only the original
20-byte FE16 branch, never an inferred SoundWave length assembler.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...profiles.symphony import SymphonyProfile


class Assembler:
    def __init__(self) -> None:
        self.pending = b""

    def feed(self, incoming: bytes) -> bytes | None:
        if len(incoming) < 3:
            return None
        effective = self.pending + incoming
        self.pending = b""
        if len(incoming) == 20 and incoming[1:3] == b"\xfe\x16":
            self.pending = incoming
            return None
        return effective


@dataclass(frozen=True, slots=True)
class Massage:
    running: bool
    timer_index: int
    wave: int | None
    head: int | None
    foot: int | None
    sonic: bool | None = None


def legacy_massage(
    profile: SymphonyProfile, data: bytes, side: int, old: bytes = b""
) -> Massage | None:
    p1 = data[:3] == b"\xf4\xfe\x16"
    if not p1 and data[:2] != b"\xa5\x0b":
        return None
    required = 22 if profile.selector == 4 else 15 if profile.selector == 6 else 9
    if len(data) < required or (
        old and (len(old) < 16 or len(data) < 16 or old[4:16] == data[4:16])
    ):
        return None
    if profile.selector == 4:
        timer, wave = data[19] & 15, data[21]
        timer, wave = timer if timer <= 4 else 0, wave if wave <= 4 else 0
        head, foot = ((data[11] & 15) + 1) // 2, (data[12] + 1) // 2
        # The logged combined maximum is computed before these overrides. It
        # never becomes one of the six pages' UI strength values.
        if profile.product.value == 15:
            head, foot = ((data[11 if side == 1 else 12] & 15) + 1) // 2, ((data[13] & 15) + 1) // 2
    else:

        def strength(raw: int) -> int:
            return raw % 3 + raw // 3 + int(raw > 1)

        if profile.selector == 6:
            low, high, kind, raw = (5, 4, 6, 7) if side == 1 else (12, 11, 13, 14)
            seconds, wave = data[low] | data[high] << 8, data[kind]
            head = foot = strength(data[raw])
        else:
            low, high = (4, 5) if profile.selector == 2 else (5, 4)
            seconds, wave = data[low] | data[high] << 8, data[6]
            head, foot = strength(data[7] & 15), strength(data[8])
        timer = seconds // 600 + 1 if seconds else 0
    page = profile.product.massage
    if page is None:
        return None
    if page == "premier":
        # F1: received TIME, not the transformed WAVE, supplies page field47.
        return Massage(head > 0, timer if head > 0 else 0, None, None, None)
    running = timer > 0 and (page != "split_p1" or head > 0 or foot > 0)
    return Massage(
        running,
        timer if running else 0,
        wave if running else 0,
        head,
        foot if page in ("kgd", "split_p1") else None,
    )


@dataclass(frozen=True, slots=True)
class Light:
    color: int
    brightness: int
    on: bool


@dataclass(frozen=True, slots=True)
class Snore:
    enabled: bool
    strength: int
    privacy: bool


@dataclass(frozen=True, slots=True)
class Alarm:
    enabled: bool
    week: int | None = None
    mode: int | None = None
    hour: int | None = None
    minute: int | None = None
    second: int | None = None


def soundwave(data: bytes) -> Light | Massage | Snore | Alarm | None:
    if len(data) <= 5 or data[:3] != b"\x2a\x00\x00":
        return None
    if len(data) == 12 and data[3:7] == b"\x04\x81\x06\x02":
        return Light(data[7], data[11], bool(data[7] and data[11]))
    if len(data) >= 13 and data[3:5] == b"\x03\x81" and data[6] == 1:
        if data[9] != 1:
            return Alarm(False)
        if data[10] > 23 or data[11] > 59 or data[12] > 59:
            return None
        return Alarm(True, data[7], data[8], data[10], data[11], data[12])
    if len(data) >= 17 and data[3:6] == b"\x06\x81\x0b":
        head, foot = max(0, ((data[7] & 15) - 2) // 2), max(0, ((data[8] & 15) - 2) // 2)
        sonic = (data[9] & 15) == 1
        timer = max(
            (int.from_bytes(data[13:15], "little") + 599) // 600,
            (int.from_bytes(data[15:17], "little") + 599) // 600,
        )
        timer, wave = (0, 0) if sonic else (timer, data[11])
        running = bool(head or foot)
        if not running:
            head = foot = timer = wave = 0
        elif not sonic and not timer:
            running = False
        return Massage(running, timer, wave, head, foot, sonic)
    if len(data) >= 12 and data[3:6] == b"\x07\x81\x09":
        return Snore(data[6] == 1, data[8], data[11] == 1)
    return None


def alarm(profile: SymphonyProfile, data: bytes, side: int) -> Alarm | None:
    page = profile.product.page
    if page == "soundwave":
        value = soundwave(data)
        return value if isinstance(value, Alarm) else None
    if data[:3] == b"\xed\x80\x03" and page in ("premier", "st800", "hilo", "split_p1"):
        i = 3 + 4 * side if page == "split_p1" else 3
        if len(data) < i + 4:
            return None
        hour, minute, week, mode = data[i : i + 4]
        enabled = week not in (0, 128)
    elif data[:2] == b"\xa5\x0c" if page == "split_p3" else data[:3] == b"\xa5\x0c\x0e":
        wi, mi, hi, ni, ei = (
            (11, 12, 13, 14, 16) if page == "split_p3" and side == 2 else (4, 5, 6, 7, 9)
        )
        if len(data) <= max(wi, mi, hi, ni, ei):
            return None
        week, mode, hour, minute, enable = (data[i] for i in (wi, mi, hi, ni, ei))
        if page == "premier" and profile.selector == 5:
            hour, minute = (hour >> 4) * 10 + (hour & 15), (minute >> 4) * 10 + (minute & 15)
        enabled = enable != 0 and not (enable == 1 and week == mode == hour == minute == 0)
    else:
        return None
    if hour > 23 or minute > 59:
        return None
    return Alarm(
        enabled,
        week if enabled else 0,
        mode if enabled else None,
        hour if enabled else None,
        minute if enabled else None,
    )


def opposite_alarm_conflict(data: bytes | None, side: int, hour: int, minute: int) -> bool:
    """No week-overlap rule: the opposite enabled, nonzero record owns the time."""
    wi, mi, hi, ni, ei = (11, 12, 13, 14, 16) if side == 1 else (4, 5, 6, 7, 9)
    if data is None or data[:2] != b"\xa5\x0c" or len(data) <= ei:
        raise ValueError("Refresh a complete current-session opposite-side alarm response first")
    week, mode, old_hour, old_minute, enabled = (data[i] for i in (wi, mi, hi, ni, ei))
    return (
        enabled == 1
        and any((week, mode, old_hour, old_minute))
        and (old_hour, old_minute) == (hour, minute)
    )


def offline_voice(protocol: str | None, firmware: str | None) -> bool:
    if protocol != "SENSOR_VOICE" or firmware is None:
        return False
    try:
        parts = tuple(int(value) for value in firmware.split("."))
    except ValueError:
        return False
    return bool(parts) and (parts[0] > 1 or parts[0] == 1 and len(parts) > 1 and parts[1] > 0)
