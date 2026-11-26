"""OkimattMotion 1.1.1 (3), APK Protocol Audit row 137."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from ..codec import keeson as codec
from ..const import KEESON_BASE_SERVICE_UUID, KEESON_BASE_WRITE_CHAR_UUID
from .keeson import OKIMATTMOTION, OKIMATTMOTION_REFRESH_MS, encode

if TYPE_CHECKING:
    from datetime import datetime, time

WRITE_SERVICE: Final = KEESON_BASE_SERVICE_UUID
WRITE_CHAR: Final = KEESON_BASE_WRITE_CHAR_UUID
NOTIFY_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"
NAME_PREFIXES: Final = ("okin", "comfort", "ble")
LAYOUTS: Final = {"20": "Back and legs", "30": "Back and legs with combined movement and Book"}
DEFAULT_LAYOUT: Final = "30"  # The app's unset value 40 takes the same branch as 30.
MOTORS: Final = {"back": (1, 2), "legs": (4, 8), "back_legs": (5, 10)}
MANUAL_STOP: Final = codec.RELEASE
PRESET_STOP: Final = 0x21000000
# Position-tab labels. Book is the Remote-tab alias for Quiet Sleep.
PRESETS: Final = {
    "zero_g": (0x21000001, 0x21000011),
    "flat": (0x21000002, 0x21000012),
    "anti_snore": (0x21000003, 0x21000013),
    "memory_1": (0x21000004, 0x21000014),
    "memory_2": (0x21000006, 0x21000016),
}
MASSAGE_LEVELS: Final = range(1, 4)
MASSAGE_INTENSITY: Final = 0x10000010
MASSAGE_WAVE: Final = 0x10000020
MASSAGE_TIMERS: Final = {10: 0x10000030, 20: 0x10000031, 30: 0x10000032}
MASSAGE_POWER_DELAY_S: Final = 0.1
LIGHT: Final = {False: 0x30000000, True: 0x30000001}
SLEEP_TIMERS: Final = {None: 0xFF, 10: 0x30, 20: 0x31, 30: 0x32}
WAKE_MODES: Final = {"none": 0xFF, "wake_mode_1": 0x04}
ALARM_OPTIONS_PREFIX: Final = (0x11, 0x22)
ALARM_WRITES: Final = 2
REFRESH_MS: Final = OKIMATTMOTION_REFRESH_MS
MANUAL_STOP_WRITES: Final = len(OKIMATTMOTION.release.steps)


def control_frame(word: int) -> bytes:
    """Encode one of this app's direct control words."""
    return encode(OKIMATTMOTION, word)


def alarm_frame(
    now: datetime, target: time | None, sleep_timer: int | None, wake_mode: str
) -> bytes:
    """Encode the app's clock set or cancel, with explicit sleep and wake choices."""
    sleep = SLEEP_TIMERS[sleep_timer] if target is not None else SLEEP_TIMERS[None]
    wake = WAKE_MODES[wake_mode] if target is not None else WAKE_MODES["none"]
    return codec.ea_clock(now, target, (*ALARM_OPTIONS_PREFIX, sleep, wake))
