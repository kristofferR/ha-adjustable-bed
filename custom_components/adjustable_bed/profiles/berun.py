"""BERUN 1.1.1 (7): four explicit versions over three existing wire codecs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from ..codec import keeson, okin_nframe, okin_ore
from ..execution import STREAM_HOLD
from .keeson import AppAction, AppProfile

# Only live controls. No combined, neck, waist or massage-minus helpers.
CONTROLS: Final = (
    AppAction("head_up", "Head up", 1, "held"),
    AppAction("head_down", "Head down", 2, "held"),
    AppAction("foot_up", "Foot up", 4, "held"),
    AppAction("foot_down", "Foot down", 8, "held"),
    AppAction("flat", "Flat", 0x08000000, "held"),
    AppAction("zero_g", "Zero gravity", 0x1000, "held"),
    AppAction("memory", "Memory", 0x10000, "held"),
    AppAction("tv", "TV", 0x4000, "held"),
    AppAction("read", "Read", 0x2000, "held"),
    AppAction("anti_snore", "Anti-snore", 0x8000, "held"),
    AppAction("light", "Toggle light", 0x20000, "single"),
    AppAction("massage_toggle", "Toggle massage", 0x100, "single"),
    AppAction("massage_timer", "Cycle massage timer", 0x200, "single"),
    AppAction("massage_head", "Cycle head massage", 0x800, "single"),
    AppAction("massage_foot", "Cycle foot massage", 0x400, "single"),
    AppAction("massage_mode", "Cycle massage mode", 0x10000000, "single"),
)
ORE: Final = {
    0: 0x2000,
    1: 0x2001,
    2: 0x2002,
    4: 0x2003,
    8: 0x2004,
    0x08000000: 0x2066,
    0x1000: 0x2060,
    0x10000: 0x2064,
    0x4000: 0x2062,
    0x2000: 0x2061,
    0x8000: 0x2063,
    0x20000: 0x2080,
    0x100: 0x2081,
    0x800: 0x2084,
    0x400: 0x2085,
    0x10000000: 0x2070,
}
# These are GATT roles, independent of the advertisement's motion version.
ROLES: Final = (
    (
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    (
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001001-0000-1000-8000-00805f9b34fb",
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001002-0000-1000-8000-00805f9b34fb",
    ),
    (
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
        "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    ),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BerunProfile(AppProfile):
    version: int
    refresh_ms: int = 200
    massage_query_ms: int = 100
    alarm_repeat_ms: int = 300

    def frame(self, word: int) -> bytes:
        allowed = {0, *(a.mask for a in self.actions)}
        if word not in allowed:
            raise ValueError("This BERUN version has no working control for that command")
        if self.version == 7:
            return okin_ore.frame(ORE[word])
        if self.version == 6:
            return keeson.frame(word, header=0xE6, side=0)
        return okin_nframe.frame40(word)

    def clock_frame(self, now: datetime) -> bytes:
        if self.version < 8:
            return keeson.clock(now)
        return okin_nframe.clock(
            (
                now.year - 2000,
                now.month,
                now.day,
                (now.weekday() + 1) % 7,
                now.hour,
                now.minute,
                now.second,
            )
        )

    def query(self, *, alarm: bool = False) -> bytes:
        if self.version >= 8:
            return okin_nframe.request(0xC0 if alarm else 0xB0)
        # Version 7 deliberately queries massage using the version 6 frame.
        return keeson.ALARM_QUERY if alarm else keeson.frame(3, header=0xE6, side=0)

    def alarm_frame(self, hour: int, minute: int, days: int, kind: int) -> bytes:
        if self.version < 8:
            return keeson.alarm_table(3, bytes((hour, minute, days, kind)))
        return okin_nframe.alarm((days, kind, hour, minute, 0, int(bool(kind)), 0))


PROFILES: Final = {
    f"v{version}": BerunProfile(
        key="berun",
        app="berun",
        layout=f"v{version}",
        version=version,
        actions=tuple(
            a
            for a in CONTROLS
            if not (version == 8 and a.key == "light" or version == 7 and a.key == "massage_timer")
        ),
        alarm=None,
        rename_units=0,
        execution=STREAM_HOLD,
    )
    for version in (6, 7, 8, 9)
}


def advertisement(name: str, manufacturer: dict[int, bytes]) -> str | None:
    """Reconstruct the active Android parser's company-id-inclusive data.

    Shared names only seed the version after the user explicitly chooses BERUN.
    Truncated data cannot grant a version; HA never reproduces the app's crash.
    """
    if not name.lower().startswith(("okin", "smartbed")):
        return None
    data = b"".join(
        company.to_bytes(2, "little") + payload for company, payload in sorted(manufacturer.items())
    )
    if data.startswith(b"OK"):
        return "v7"
    if data[2:7] == b"DOT\x00\x01":
        return "v8"
    if data[2:6] == b"DOT\x00":
        return "v9"
    return "v6"
