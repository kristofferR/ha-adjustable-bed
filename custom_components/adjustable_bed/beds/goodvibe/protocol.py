"""Good Vibe Sleep 2.0.1/code20103 frames over the Richmat 6E codec (row116).

Commands and STOP are ``codec.function``, colour is ``codec.rgb``. Settings
records put ``len`` after ``20`` (``codec.record_20_len``). The sleep sensors'
JSON envelope is in ``sleep.py``.
"""

from __future__ import annotations

from datetime import datetime

from ...codec import richmat as codec
from .catalog import Action

LIGHT_OFF = 0x75
"""The dedicated close-bed-light command."""
MASSAGE_TIMER = {0: 0x5E, 10: 0x5F, 20: 0x63, 30: 0x61}
"""Bottom massage countdown command by minutes, sent once without a release."""


def action_frame(action: Action, side: int, legacy: bool, long: bool = False) -> bytes:
    """A catalog action's long, legacy-short or short operand as a command."""
    if side not in (0, 1, 2):
        raise ValueError("Invalid Good Vibe side")
    code = action.long if long else action.legacy_short if legacy else action.short
    return codec.function(code, side, single=legacy)


def clock(minutes: int, code: int) -> tuple[bytes, bytes]:
    """Single-alarm countdown. The high byte truncates toward zero, so a past alarm's
    negative countdown keeps the bytes the pre-v5 builder sent."""
    return codec.countdown(int(minutes / 256) << 8 | minutes & 0xFF, code)


def light_duration(seconds: int) -> bytes:
    """Seconds, big-endian; zero (always on) is ``FF FF``."""
    digits = f"{seconds:04x}"
    return codec.light_timer(*((0xFF, 0xFF) if seconds == 0 else
                              (int(digits[:2], 16), int(digits[2:4], 16))))


def snore_config(count: bool, value: int) -> bytes:
    return codec.record_20_len(6, 5, 1, (1 if count else 2, 0, value))


def snore_switch(enabled: bool) -> bytes:
    return codec.record_20_len(6, 1, 1, (0, int(enabled)))


def repeat_alarm(number: int, hour: int, minute: int, code: int, mask: int) -> bytes:
    return codec.record_20_len(5, 1, 1, (number, 0, hour, minute, code, mask))


def delete_alarm(number: int) -> bytes:
    return codec.record_20_len(5, 2, 1, (number,))


def sync_time(now: datetime, offset_now: datetime | None = None) -> tuple[bytes, bytes]:
    return codec.time_sync(now, offset_now, build=codec.record_20_len)


QUERIES = {
    "alarms": codec.record_20_len(5, 1, 0, (0,)),
    "sleep_name": codec.record_20_len(6, 3, 0, (0,)),
    "snore_switch": codec.record_20_len(6, 1, 0, (0,)),
    "snore_config": codec.record_20_len(6, 5, 0, (0, 0)),
}


def memory_eligible(model: str, action: str) -> bool:
    return (
        model in ("E3RM", "GXRM", "JDRM", "JFRM", "JGRM")
        and action
        in (
            "deviceFunctionItemMemoryPosition1",
            "deviceFunctionItemMemoryPosition2",
            "deviceFunctionItemMemoryPosition3",
            "deviceFunctionItemMemoryPosition4",
            "deviceFunctionItemAntiSnoring",
            "deviceFunctionItemZeroGravity",
            "deviceFunctionItemTVPosition",
        )
        and (model, action) != ("GXRM", "deviceFunctionItemTVPosition")
    )


EIGHT_COLORS = (
    (255, 255, 0),
    (0, 255, 0),
    (0, 127, 255),
    (0, 0, 255),
    (139, 0, 255),
    (255, 255, 255),
    (255, 0, 0),
    (255, 165, 0),
)


def light_durations(model: str, eight_color: bool) -> tuple[int, ...]:
    if eight_color:
        return (0, 1800, 3600, 14400, 28800) if model == "RNRN" else (0, 300, 600, 900)
    return tuple(range(0, 901, 60))


SNORE_MENU_EXCLUDED_MODELS = frozenset(("HNRN", "HQRN", "HSRN", "HURN", "M7RN", "MJRN"))
