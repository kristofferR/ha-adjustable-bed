"""SmartBed profile handlers followed by the manager's legacy fallback.

Signed byte arithmetic and profile-specific asymmetries are intentional. Short
replies are rejected atomically instead of reproducing Android indexing errors.
Caches belong to one connection and are discarded by the controller on disconnect.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from ...profiles.smartbed import signed


@dataclass(slots=True)
class State:
    alarm_hour: int = 0
    alarm_min: int = 0
    alarm_on: bool = False
    alarm_repeat: int = 0
    alarm_type: int = 0
    bed_selection: int = 1
    foot_intensity: int = 0
    has_sonic_massage: bool = False
    have_light: bool = True
    have_massage: bool = True
    head_intensity: int = 0
    is_rgb_light: bool = False
    light_on: bool = False
    massage_num: int = 2
    massage_on: bool = False
    massage_time: int = 0
    massage_wave: int = 0
    motor_number: int = 2
    sonic_massage_mode: int = 0
    sonic_volume: int = 0


def alarm_kind(value: int, dacheng: bool = False) -> int:
    return (
        {1: 9, 2: 13, 3: 20}
        if dacheng
        else {1: 13, 2: 14, 3: 15, 4: 16, 5: 20, 6: 19, 7: 18, 8: 9, 9: 21}
    ).get(value, 0)


def seconds_tier(value: int) -> int:
    return 0 if value <= 0 or value > 1800 else 1 if value <= 600 else 2 if value <= 1200 else 3


class Fragments:
    def __init__(self) -> None:
        self.first: bytes | None = None

    def feed(self, raw: bytes) -> bytes | None:
        if len(raw) <= 20:
            if len(raw) > 3:
                if raw[:3] == b"\xf4\xfe\x16":
                    self.first = raw
                elif len(raw) not in (10, 16) and self.first is not None:
                    raw = self.first + raw
            else:
                return self.first + raw if self.first is not None else None
        return raw


class Parser:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.state = State(have_light=False, massage_num=0) if profile == "cb24_ab" else State()
        self.fragments = Fragments()
        self.fallback_fragments = Fragments()
        self.pages: list[int] = []
        self.next_page = -1
        self.malformed = 0
        self.configuration_received = False
        self.sonic_received = False
        self.changed: frozenset[str] = frozenset()

    def profile_only(self, raw: bytes, side: int = 0) -> bool:
        old = replace(self.state)
        old_pages = self.pages[:]
        self.next_page = -1
        self.configuration_received = False
        self.sonic_received = False
        try:
            consumed = self._profile(raw, side)
        except IndexError, ValueError:
            self.state, self.pages = old, old_pages
            self.malformed += 1
            consumed = False
        self.changed = frozenset(k for k, v in asdict(self.state).items() if v != getattr(old, k))
        return consumed

    def feed(self, raw: bytes, side: int = 0) -> frozenset[str]:
        old = replace(self.state)
        malformed = self.malformed
        data = self.fragments.feed(raw) if self.profile == "cb" else raw
        consumed = self.profile_only(data, side) if data is not None else False
        if self.malformed != malformed:
            self.changed = frozenset()
            return self.changed
        if not consumed and self.profile != "standard":
            fallback = self.fallback_fragments.feed(raw)
            if fallback is not None:
                self._legacy(fallback)
        self.changed = frozenset(k for k, v in asdict(self.state).items() if v != getattr(old, k))
        if data and (
            (self.profile != "cb27new" and len(data) >= 10 and data[1] == 12 and consumed)
            or (len(data) >= 7 and data[:2] == b"\xed\x80")
        ):
            self.changed |= frozenset(
                ("alarm_hour", "alarm_min", "alarm_repeat", "alarm_type", "alarm_on")
            )
        # Replies can confirm a value equal to the initial cache. Publish the
        # relevant group as well as changed fields so zero/off becomes known.
        if data and len(data) > 1:
            if self.profile == "standard" and len(data) >= 14 and data[5:7] == b"\x20\x50":
                self.changed |= frozenset(
                    (
                        "head_intensity",
                        "foot_intensity",
                        "massage_time",
                        "massage_wave",
                        "massage_on",
                        "light_on",
                    )
                )
            elif data[1] == 11 or len(data) in (10, 16, 23) and not consumed:
                self.changed |= frozenset(
                    ("head_intensity", "foot_intensity", "massage_time", "massage_wave")
                )
            if (
                self.profile == "cb27new"
                and len(data) >= 10
                and data[:1] == b"*"
                and data[4] == 129
            ):
                groups = {
                    2: ("head_intensity", "foot_intensity", "massage_time", "massage_wave"),
                    3: ("alarm_hour", "alarm_min", "alarm_repeat", "alarm_type", "alarm_on"),
                    4: ("light_on",),
                    6: (
                        "sonic_massage_mode",
                        "sonic_volume",
                        "head_intensity",
                        "foot_intensity",
                        "massage_time",
                        "massage_wave",
                    ),
                }
                if data[3] != 3 or len(data) >= 13:
                    self.changed |= frozenset(groups.get(data[3], ()))
        return self.changed

    def _legacy(self, raw: bytes) -> bool:
        d = [signed(v) for v in raw]
        if len(d) >= 7 and d[:2] == [-19, -128]:
            (
                self.state.alarm_hour,
                self.state.alarm_min,
                self.state.alarm_repeat,
                self.state.alarm_type,
            ) = d[3:7]
            self.state.alarm_on = any(d[3:7])
            return False
        if len(d) == 23:
            timer, head, foot, wave = d[19], d[11] & 15, d[12], d[21]
        elif len(d) == 16:
            timer, head, foot, wave = d[14] & 15, d[7] & 15, d[8] & 15, (d[14] & 240) >> 4
        elif len(d) == 10:
            timer, head, foot, wave = d[8], 0, 0, 0
        else:
            return False

        def level(value: int) -> int:
            return 1 if value in (1, 2) else 2 if value in (3, 4) else 3 if value in (5, 6) else 0

        self.state.massage_time = {1: 10, 2: 20, 3: 30}.get(timer, 0)
        self.state.head_intensity, self.state.foot_intensity = level(head), level(foot)
        self.state.massage_wave = {1: 0, 2: 1, 3: 2, 4: 3}.get(wave, 0)
        return True

    def _profile(self, raw: bytes, side: int) -> bool:
        d, s, name = [signed(v) for v in raw], self.state, self.profile
        if name == "headboard126":
            return False
        if name == "standard":
            if d[0] != -91 and d[1] != 90:
                return False
            op = (d[5] << 8) + d[6]
            if op == 0x2050:
                if len(d) < 14:
                    return False
                s.head_intensity, s.foot_intensity = d[8:10]
                s.massage_time = {1: 10, 2: 20, 3: 30}.get(d[10], 0)
                s.massage_wave, s.light_on, s.massage_on = d[11], d[12] > 0, d[13] > 0
                return True
            # Unmasked signed low bytes make the app's 2080..2095 branches unreachable.
            return op in (0x2060, 0x2061, 0x2062, 0x2063, 0x2064)
        if name == "cb":
            return self._legacy(raw)
        if name == "cb27new":
            if len(d) < 10 or d[0] != 42:
                return False
            group = d[3]
            if d[4] != -127:
                return False
            if group == 5:
                if d[7] == 1:
                    self.pages = [i for i in range(8) if d[6] & (1 << i)][1:]
                    s.motor_number, s.massage_num = (d[8] & 255).bit_count(), d[11] & 15
                    s.have_light, s.is_rgb_light = d[12] > 0, d[12] > 1
                else:
                    for i in range(9, d[8] + 9):
                        if d[i] | (d[i + 1] << 8) == 7:
                            s.has_sonic_massage = True
                self.next_page = self.pages.pop() if self.pages else -1
                self.configuration_received = True
                return True
            if group == 4:
                s.light_on = d[7] > 0
            elif group == 2:

                def level(v: int) -> int:
                    return 3 if v >= 6 else 2 if v >= 3 else 1 if v >= 1 else 0

                s.head_intensity, s.foot_intensity = level(d[7] & 15), level(d[10] & 15)
                s.massage_wave = (d[7] & 240) >> 4
                s.massage_time = seconds_tier((d[8] & 255) | ((d[9] & 255) << 8))
            elif group == 3:
                if len(d) < 13:
                    return True
                s.alarm_repeat, s.alarm_type, s.alarm_on = d[7], alarm_kind(d[8]), d[9] == 1
                s.alarm_hour, s.alarm_min = d[10:12]
            elif group == 6:

                def sonic_level(v: int) -> int:
                    return 3 if v >= 8 else 2 if v >= 6 else 1 if v >= 2 else 0

                s.sonic_massage_mode = d[9] & 15
                s.head_intensity, s.foot_intensity = sonic_level(d[7] & 15), sonic_level(d[8] & 15)
                s.sonic_volume, s.massage_wave = (d[7] & 240) >> 4, d[11] & 255
                s.massage_time = seconds_tier((d[13] & 255) | ((d[14] & 255) << 8))
                self.sonic_received = True
            return False
        if len(d) < 5:
            return False
        dacheng, ab = name == "dacheng", name == "cb24_ab"
        marker = 1 if dacheng else -86
        if d[1] == 11:
            off = 0
            if ab or dacheng:
                if side == 1:
                    off = 0 if d[3] == marker else 7
                elif side == 2:
                    off = 0 if d[3] == (2 if dacheng else -69) else 7
            value = d[4 + off]
            s.massage_time = 30 if value > 4 else 20 if value > 2 else 10 if value > 0 else 0
            if ab and side == 0 and not (d[4] > 0 and d[11] > 0):
                s.massage_time = 30 if d[4] > 4 else 20 if d[4] > 2 else 0
            s.massage_on = d[4 + off] > 0 if not (ab and side == 0) else d[4] > 0 and d[11] > 0
            s.massage_wave = d[6 + off] - 1
            if dacheng and ((side == 1 and off == 7) or (side == 2 and off == 0)):
                s.massage_wave = d[6 + off]
            for key, index in (("head_intensity", 7 + off), ("foot_intensity", 8 + off)):
                value = d[index] if dacheng else {0: 0, 1: 1, 3: 2, 6: 3}.get(d[index])
                if value is not None:
                    setattr(s, key, value)
            return True
        if d[1] != 12 or name == "headboard265":
            return False

        def segment(off: int) -> tuple[int, int, int, int, bool]:
            hour, minute = d[6 + off], d[7 + off]
            if dacheng:
                hour, minute = int(f"{hour & 255:02x}", 10), int(f"{minute & 255:02x}", 10)
            return d[4 + off], alarm_kind(d[5 + off], dacheng), hour, minute, d[9 + off] == 1

        if ab or dacheng:
            a, b = (segment(0), segment(7)) if d[3] == marker else (segment(7), segment(0))
            if side == 0:
                repeat, kind, hour, minute, enabled = a
                enabled = enabled and a == b
            else:
                off = (
                    (0 if d[3] == marker else 7)
                    if side == 1
                    else (0 if d[3] == (2 if dacheng else -69) else 7)
                )
                repeat, kind, hour, minute, enabled = segment(off)
        else:
            repeat, kind, hour, minute, enabled = segment(0)
            kind = kind or s.alarm_type
        s.alarm_repeat, s.alarm_type, s.alarm_hour, s.alarm_min, s.alarm_on = (
            repeat,
            kind,
            hour,
            minute,
            enabled,
        )
        return True
