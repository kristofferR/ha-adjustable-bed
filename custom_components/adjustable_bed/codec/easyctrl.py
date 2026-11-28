"""EasyCtrl counter policy and bounded whole-buffer status dispatch over P1."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from .cheerssleep import p1 as p1


@dataclass(slots=True)
class Counters:
    sequence: int = 1
    cache: int = 0

    def control(self, code: int, parameter: int = 0, *, cached: bool = False) -> bytes:
        if not cached or self.cache != code:
            self.sequence += 1
        if cached:
            self.cache = code
        return p1(self.sequence, 1, code, parameter)

    def query(self, code: int) -> bytes:
        return p1(0, 2, code)

    def setting(self, code: int, value: int) -> bytes:
        return p1(0, 3, code, value)


STATUS: Final = {
    0x337: "child_lock_status_1",
    0x338: "child_lock_status_2",
    0x301: "heat_status_1",
    0x321: "heat_status_2",
    0x309: "airbag_massage_status_1",
    0x329: "airbag_massage_status_2",
    0x34A: "duolian_status_1",
    0x305: "led_status_1",
    0x325: "led_status_2",
    0x306: "led_status_RGBA_1",
    0x30E: "music_massage_status_1",
    0x32E: "music_massage_status_2",
    0x30F: "music_massage_strength_1",
    0x316: "Fushou_status",
    0x336: "Fushou_status",
    0x307: "cup_cold_status_1",
    0x327: "cup_cold_status_2",
    0x1002: "audio_scene_status_1",
    0x304: "knead_speed_mode_1",
    0x339: "knead_location_mode_1",
    0x314: "rhythm_state_1",
    1: "SCD_BACK_MASSAGE_STATE_1",
    0x315: "Swing_timing_1",
    0x31A: "waist_status_1",
    0x33A: "waist_status_2",
    0x30D: "ventilate_status_1",
    0x32D: "ventilate_status_2",
    0x302: "zz_massage_mode_1",
}
LUMBAR: Final = {
    1: "MASSAGE_status",
    2: "MASSAGE_time",
    3: "HEAT_status",
    4: "HEAT_time",
    8: "CHILD_LOCK",
    9: "BATTERY_LEVEL",
}


def parse(data: bytes) -> tuple[str, int | str] | None:
    """Preserve the app's first substring search, including unaligned matches.

    Unknown special tags and truncated values are ignored instead of allowing
    the app's unchecked exception to escape a Home Assistant BLE callback.
    """
    if len(data) < 4 or data[1] != 0x82:
        return None
    code = int.from_bytes(data[2:4], "little")
    if code == 0x82:
        return (LUMBAR[data[5]], data[4]) if len(data) >= 6 and data[5] in LUMBAR else None
    event = STATUS.get(code)
    if event is None:
        return None
    raw = data.hex()
    start = raw.find(data[2:4].hex()) + 4
    length = 8 if code == 0x306 else 4
    if start + length > len(raw):
        return None
    value = raw[start : start + length]
    return event, value if code == 0x306 else int.from_bytes(bytes.fromhex(value), "little")


def alarm_values(hour: int, minute: int, days: tuple[int, ...], now: datetime) -> tuple[int, int]:
    """Java truncation and the artifact's asymmetric +13 past-time day mask."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
    if now.utcoffset() is not None:
        later = target.replace(fold=1)
        # Calendar chooses the later overlap, but normalizes spring gaps forward.
        roundtrip = later.astimezone(UTC).astimezone(now.tzinfo)
        if roundtrip.replace(tzinfo=None) == target.replace(tzinfo=None):
            target = later
    elapsed = (
        target.astimezone(UTC) - now.astimezone(UTC)
        if now.utcoffset() is not None
        else target - now
    )
    seconds = int(elapsed.total_seconds())
    mask = sum(1 << ((day - now.weekday() + (7 if seconds >= 0 else 13)) % 7) for day in set(days))
    return ((seconds + 86400) % 86400 if seconds < 0 else seconds), mask
