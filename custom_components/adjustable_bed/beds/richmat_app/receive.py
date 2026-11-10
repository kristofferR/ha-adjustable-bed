"""Richmat 4.2.0 receive framing and direct-bed fields, independent of Android bugs."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from ...codec import richmat as codec

type Value = str | int | float | bool | None | list[Value] | dict[str, Value]

EXACT = {
    "6e09010078": "clock_available",
    "6e0e00037f": "light_available",
    "6e1a000189": "aroma_available",
    "6e07010177": "alarm_saved",
    "6e07010278": "alarm_cancelled",
    "6e16010186": "music_available",
    "6e90c101c0": "detection_available",
    "6e2100008f": "snore_available",
    "6e23018416": "locked",
    "6e23008415": "unlocked",
    "6e23a06e9f": "stop_music",
}


def common(b: bytes) -> dict[str, Value]:
    if len(b) != 5 or b[:2] != b"\x6e\x90":
        return {}
    t, n = b[2] >> 4, b[2] & 15
    if t == 0 and n == 0:
        return {"version": b[3]}
    if t == 1:
        return {"bed_mode": n}
    if t == 3:
        return {"no": b[2] >> 2 & 3, "status": b[2] & 3, "angle": b[3]}
    if t == 10:
        x = (n << 8) | b[3]
        return {
            k: x >> shift & 7
            for k, shift in zip(
                ("mode", "massage3", "massage2", "massage1"), (9, 6, 3, 0), strict=True
            )
        }
    if t == 11:
        return {
            "usb": bool(b[2] & 1),
            "playing": bool(b[3] & 128),
            "shake": bool(b[3] & 64),
            "ble": bool(b[3] & 32),
        }
    if t == 12:
        if n == 2:
            return {
                "check_status": {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(b[3], "start")
            }
        if n in (3, 4, 5, 6):
            return {
                "type": {3: "motor", 4: "massage", 5: "ubl", 6: "usb"}[n],
                "number": b[3] >> 4,
                "status": {
                    0: "abnormal",
                    1: "normal",
                    2: "controlBoxMalfunction",
                    3: "notPluggedIn",
                }.get(b[3] & 15, "notPluggedIn"),
            }
    if t == 13 and n in (1, 2):
        return {"volume" if n == 1 else "shake_gear": b[3]}
    return {}


def extended(b: bytes) -> dict[str, Value]:
    """One verified leaf; malformed payloads fail before an incomplete model is published."""
    if len(b) < 7 or b[2] != len(b) or b[5] not in (2, 3):
        return {}
    g, o = b[3:5]
    n = len(b)
    if g == 1:
        if o == 2 and n > 9:
            return {
                "height": ((b[7] << 8) + b[8]) / 10,
                "type": b[9],
                "angle": b[10] if n > 11 else -1,
                "monitorHeight": ((b[11] << 8) + b[12]) / 10 if n > 13 else 0,
            }
        if o == 3 and n > 8:
            return {"position": b[6], "angle": b[8]}
    if g == 2:
        if o == 1 and (b[2] - 7) % 2 == 0:
            return {
                ("head" if b[i] == 1 else "foot"): b[i + 1]
                for i in range(6, b[2] - 1, 2)
                if b[i] in (1, 2)
            }
        if n > 7 and o in (2, 4, 5):
            return {{2: "mode", 4: "frequency", 5: "shake_strength"}[o]: b[7]}
        if n > 7 and o == 6:
            return {"power": b[7] == 1}
    if g == 3 and o == 1 and n > 7:
        return {"power": b[7] == 1}
    if g == 4:
        if o == 1 and n > 9:
            return {"rgb": [b[i] & 255 for i in (7, 8, 9)], "alpha": 1}
        if o == 2 and n > 8:
            return {"timer": b[7] * 60 + b[8]}
        if o in (3, 4) and n > 7:
            return {"motion" if o == 3 else "power": b[7] == 1}
    if g == 5 and o == 1:
        if n < 13:
            raise ValueError("Truncated repeat alarm")
        return {
            "fields": dict(zip(("7", "f", "17", "1f", "27", "2f"), b[6:12], strict=True)),
            "direction": b[5],
        }
    if g == 6:
        if o in (1, 2) and n > 7:
            return {"anti_snore" if o == 1 else "get_off": b[7] == 1}
        if o == 3:
            return {"name_bytes": list(b[7:-1])}
        if o == 4 and n > 8 and b[7] == b[8] == 1:
            return {"stop_music": True}
        if o == 5 and n > 8 and b[7] in (1, 2):
            return {"count" if b[7] == 1 else "time": b[8]}
    if g == 7 and o == 2 and n > 7:
        return {"locked": b[7] == 1}
    if g == 9 and n > 7:
        if o in (1, 3, 4):
            return {{1: "playing", 3: "ble", 4: "usb"}[o]: b[7] == 1}
        if o == 2 and b[6] in (2, 3):
            return {"volume" if b[6] == 2 else "silence_raw": b[7]}
    if g == 11 and n > 7:
        if o == 1:
            return {"press_mode": b[7]}
        if o == 2:
            return {"standard_split": b[7] == 2}
        if o == 4:
            return {"same_split_raw": b[7]}
    if g == 13:
        if o == 1 and n > 7:
            return {"7": b[7] == 1}
        if o == 2 and n > 9:
            return {"2f": b[7] == 1, "33": math.floor(((b[8] << 8) + b[9]) / 60 + 0.5)}
        if o == 5 and n > 9:
            return {"b": "cool" if b[7] == 1 else "warm", "f": b[8], "17": b[9]}
        if o == 6 and n > 7:
            return {"23": b[7] == 1}
        if o == 8 and n > 7:
            return {
                k: bool(b[7] >> i & 1) for i, k in enumerate(("3f", "3b", "4f", "43", "47", "4b"))
            }
        if o == 9 and n > 11:
            return {
                "f": b[7],
                "17": b[8],
                "4f": bool(b[9] & 1),
                "3b": bool(b[9] & 2),
                "5b": b[10],
                "63": b[11] & 1,
                "6b": b[11] >> 1 & 1,
            }
        if o == 7 and n > 20:
            zone = "a" if b[6] == 1 else "b"
            days = [
                name
                for bit, name in zip(
                    range(7, 0, -1),
                    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
                    strict=True,
                )
                if b[13] >> bit & 1
            ]
            kind = (
                "once"
                if not days
                else "everyDay"
                if len(days) == 7
                else "workDay"
                if days == ["monday", "tuesday", "wednesday", "thursday", "friday"]
                else "weekend"
                if days == ["saturday", "sunday"]
                else "custom"
            )
            s: dict[str, Value] = {
                "13": zone,
                "7": b[7] == 1,
                "b": "cool" if b[8] == 1 else "warm",
                "17": b[9],
                "1f": b[10],
                "27": b[11],
                "2f": b[12],
                "3b": list(days),
                "37": kind,
                "3f": list(days) if kind == "custom" else [],
                "43": "keep" if b[14] == 1 else "delay",
                "f": "manual" if b[20] == 0 else "auto",
            }
            s.update(zip(("47", "4f", "57", "5f", "67"), b[15:20], strict=True))
            return {"1f": zone, "53" if zone == "a" else "57": s}
    if g == 14 and o == 1 and n > 7:
        return {"gear": b[7]}
    if g == 16:
        if o == 1 and n > 7:
            return {"open_raw": b[7]}
        if o == 2 and n > 8:
            return {"time": b[8]}
    if g == 17:
        if o == 2 and n > 8:
            hi, lo = b[7:9]
            typ = 0 if hi == lo == 0 else 1 if hi == lo == 255 else 2
            return {"position": b[6], "type": typ, "timeSum": (hi << 8) | lo if typ == 2 else 0}
        if o == 3 and n > 8:
            return {"position": b[6], "temperature": b[8]}
        if o == 5 and n > 6:
            return {"mode": b[6]}
    return {}


@dataclass
class Receiver:
    emit: Callable[[str, dict[str, Value]], None]
    pending: bytearray = field(default_factory=bytearray)

    def feed(self, chunk: bytes) -> None:
        self.pending.extend(chunk)
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(110)
            except ValueError:
                self.pending.clear()
                return
            del self.pending[:start]
            if len(self.pending) < 3:
                return
            kind = self.pending[1]
            if kind == 64:
                if len(self.pending) < 4:
                    return
                size = int.from_bytes(self.pending[2:4], "big")
            elif kind in (32, 33):
                size = self.pending[2]
            else:
                size = self.pending.find(110, 1)
                if size < 0:
                    size = len(self.pending)
            if not size:
                self.pending.clear()
                raise ValueError("Nonprogressing Richmat frame")
            if len(self.pending) < size:
                return
            b = bytes(self.pending[:size])
            del self.pending[:size]
            if kind == 32 and codec.is_valid(b):
                self.emit(f"group_{b[3]}_{b[4]}", extended(b))
            elif kind not in (32, 33, 64):
                if event := EXACT.get(b.hex()):
                    self.emit(event, {})
                if value := common(b):
                    self.emit("common", value)
