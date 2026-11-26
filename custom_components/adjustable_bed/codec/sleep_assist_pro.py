"""Sleep Assist Pro 1.1.3 carriers and remote feedback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, Literal

from . import keeson, sleep_assistant

Route = Literal["p1", "p2", "p3", "p4", "p5"]

# The app's key switches differ even when their outer carriers match another app.
_ONE_BITS: Final = frozenset(1 << bit for bit in range(32))
_P2_KEYS: Final = {0, 80, 160, 192, 240, 69632, 134221824, 1207959552, 1610612736} | (
    _ONE_BITS - {1 << bit for bit in (18, 19, 20, 21, 22, 28, 29)}
)
_P3_KEYS: Final = {0, 9, 1610612736} | (
    _ONE_BITS - {1 << bit for bit in (18, 19, 20, 21, 22, 26, 28, 30)}
)
_P5_KEYS: Final = {0, 134348800} | (_ONE_BITS - {1 << bit for bit in (28, 29)})
_JSON_MOVEMENT: Final = {1, 2, 4, 8, 16, 32, 64, 80, 128, 160}

WRITE_CHUNK_SIZE: Final = 20


def key(route: Route, word: int, device_id: str = "", *, epoch_seconds: int = 0) -> bytes:
    """Encode the selected route's key, including its own switch fallback."""
    word &= 0xFFFFFFFF
    match route:
        case "p1":
            return keeson.frame(word, header=0xE6, side=0)
        case "p2":
            return keeson.p2(word if word in _P2_KEYS else 0)
        case "p3":
            if word in (9, 1610612736):
                # These composite switch cases are specific to Pro.
                body = b"\xaa\x03\x00\x0a\x00\x04\x01" + word.to_bytes(4, "little")
                return body + bytes((keeson.checksum(body[5:]), 0xF3, 0x55))
            return sleep_assistant.instruction(word if word in _P3_KEYS else 0)
        case "p4":
            cmd: dict[str, int | str] = {"key": f"{word:08x}", "km": 1}
            if word in _JSON_MOVEMENT:
                cmd.update(keykt=1, km=5)
            elif word:
                cmd["ctrm"] = 1
                if word in (0x40000000, 0x80000000):
                    cmd["km"] = 6
            return keeson.json_packet(2, cmd, device_id)
        case "p5":
            mask = word if word in _P5_KEYS else 0
            body = b"\xaa\x01\x08\x05\x01" + mask.to_bytes(4, "little") + b"\0"
            checked = body + bytes((keeson.checksum(body[3:]),))
            envelope = {
                "cmd": keeson.checked(checked).hex().upper(),
                "id": device_id,
                "ts": epoch_seconds,
                "type": 12,
            }
            return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode()


def release(route: Route, device_id: str = "") -> bytes | None:
    """The held-motion follow-up, which is a status request on P2."""
    if route == "p5":
        return None
    if route == "p2":
        return keeson.STATUS_QUERY
    return key(route, 0, device_id)


@dataclass(frozen=True, slots=True)
class Feedback:
    lamp: bool | None = None
    timer_minutes: int | None = None
    brightness: int | None = None


_TIMER_BANDS: Final = {0: 10, 1: 20, 2: 30, 0xFF: 0}


def _duration_band(seconds: int) -> int | None:
    band = (seconds + 599) // 600 if 0 < seconds <= 1800 else 0xFF
    return _TIMER_BANDS.get(band)


def _base_long(data: bytes) -> Feedback | None:
    if data[0] + 2 != len(data):
        return None
    status = None
    offset = 7
    while offset < len(data):
        tag = data[offset]
        if tag in (0xA9, 0xEE):
            size = 8
        elif tag == 0xA4:
            size = 6
        elif tag == 0xA8:
            size = 11
        elif 0x10 <= tag <= 0x1F:
            size = 19 + 4 * (tag - 0x10)
            if offset + size <= len(data) and status is None:
                ticks = int.from_bytes(data[offset + 4 : offset + 8], "little")
                lamp = bool(data[offset + size - 2] >> 6)
                status = Feedback(lamp, _duration_band(ticks // 100))
        elif 0x20 <= tag <= 0x2F:
            size = 1 + 15 * (tag - 0x20)
        else:
            return None
        if offset + size > len(data):
            return None
        offset += size
    return status


def base_feedback(data: bytes) -> Feedback | None:
    """Decode the P1/P2 remote's lamp state and massage timer band."""
    length = len(data)
    if (
        length == 18
        and data.startswith(b"\xa5\x0b\x0f")
        or length == 16
        and data.startswith(b"\xa5\x0b\x0d")
        or length == 19
    ):
        return Feedback(bool(data[12]), _duration_band(int.from_bytes(data[3:5], "big")))
    if length == 31:
        if data.startswith(b"\x1c\x0b"):
            return Feedback(bool(data[10]), _duration_band(int.from_bytes(data[3:5], "big")))
        return Feedback(timer_minutes=_duration_band(int.from_bytes(data[2:4], "big")))
    if length > 80:
        return _base_long(data)
    if length == 16 and not data[13] & 0x20 or length in (20, 23):
        return Feedback(timer_minutes=_TIMER_BANDS.get(data[15 if length == 23 else 14]))
    return None


def smart_feedback(data: bytes, *, hardware_218: bool) -> Feedback:
    """Use only the common remote parser fields verified for Pro."""
    fields = sleep_assistant.remote_fields(data.hex(), hardware_218)
    lamp = fields.get("light")
    timer = fields.get("timer")
    brightness = fields.get("brightness_logged")
    return Feedback(
        lamp if type(lamp) is bool else None,
        (timer + 1) * 10 if type(timer) is int else None,
        brightness if type(brightness) is int else None,
    )


def smart_massage_timer(data: bytes, *, hardware_218: bool) -> int | None:
    """The 218 remote countdown, including its signed Java parser fallback."""
    if not hardware_218 or len(data) != 22 or data[:2] != b"\xdd\xee" or data[3] != 1:
        return None
    ticks = int.from_bytes(data[11:15], "little")
    if ticks > 0x7FFFFFFF:
        ticks = 0
    return ticks // 100 + bool(data[8] or data[9])
