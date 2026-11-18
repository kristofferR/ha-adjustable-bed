"""Bounded notification decoders. Only source-reachable BED fields are exposed."""

from __future__ import annotations

import math
import struct
from decimal import ROUND_HALF_UP, Decimal


def signed(value: int) -> int:
    return value if value < 128 else value - 256


def version(data: bytes) -> dict[str, object]:
    return {"firmware_date": f"20{signed(data[6]):02}-{signed(data[7]):02}-{signed(data[8]):02}",
            "firmware_version": signed(data[9])}


def temp(data: bytes) -> dict[str, object]:
    """TEMP's A0/81 version gate deliberately differs from MOON's A0/01."""
    if len(data) < 7:
        return {}
    group, op = data[2:4]
    b = tuple(map(signed, data))
    if group == 0xA0 and op == 0x81 and len(data) >= 10:
        return version(data)
    if group == 0xA1:
        if op == 0x81:
            return {"power": b[6], **({"displayed_setpoint": 30} if b[6] == 1 else {})}
        if op == 0x82:
            return {"light": b[6]}
        if op in (0x83, 0x84) and len(data) >= 8:
            return {f"side_{b[6]}_" + ("setpoint" if op == 0x83 else "timer"): b[7]}
        if op == 0x85 and len(data) >= 15:
            return dict(zip(("left_current", "side_1_setpoint", "right_current", "side_2_setpoint",
                             "side_1_timer", "side_2_timer", "light", "power", "water"), b[6:15], strict=True))
    if group == 0xA2:
        if op in (0x81, 0x83) and len(data) >= 8:
            field = "temperature" if op == 0x81 else "circulation"
            return {f"left_{field}": b[6], f"right_{field}": b[7]}
        if op == 0x82:
            return {"water": b[6]}
    return {}


def moon(data: bytes) -> dict[str, object]:
    if len(data) < 7:
        return {}
    group, op = data[2:4]
    if group == 0xA0:
        return version(data) if op == 1 and len(data) >= 10 else {}
    side = signed(data[6])
    prefix = f"side_{side}_"
    if op in (0x88, 0x08):
        raw = data[7:-3]
        values = tuple(value for (value,) in struct.iter_unpack(">f", raw[:len(raw)//4*4]))
        return {prefix + "pressure": values} if all(math.isfinite(x) for x in values) else {}
    if op in (0x0A, 0x8A) and len(data) >= 11:
        value = struct.unpack(">f", data[7:11])[0]
        return {prefix + "temperature": float(Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))} if math.isfinite(value) else {}
    if op == 0x0D and len(data) >= 14:
        result: dict[str, object] = {}
        for side, offset in ((1, 6), (2, 10)):
            p = f"side_{side}_"
            result.update({p + "massage": signed(data[offset]), p + "strength": signed(data[offset+1]),
                           p + "timer": signed(data[offset+2]), p + "automatic_checked": data[offset+3] == 0})
            if data[offset] == 0:
                result.update({p + "adaptive": 4, p + "stiffness": 3})
        # HA observes programmatic checkbox updates without echoing control
        # frames. Only an explicitly admitted user action may change the bed.
        return result
    if op == 0x84:
        return {prefix + "massage": 0, prefix + "strength": 0, prefix + "timer": 0,
                prefix + "adaptive": 4, prefix + "stiffness": 3}
    if len(data) < 8:
        return {}
    value = signed(data[7])
    if op == 1:
        return {prefix + "massage": value, prefix + "strength": 2,
                prefix + "timer": 10, prefix + "adaptive": 0, prefix + "pressure": ()}
    if op in (2, 3, 0x8C):
        return {prefix + {2: "timer", 3: "strength", 0x8C: "leak_number"}[op]: value}
    if op in (4, 5, 6, 7, 14):
        if op == 5 and group == 0x96:
            return {prefix + "massage": 0}
        return {prefix + "stiffness": value, prefix + "adaptive": op, prefix + "massage": 0}
    return {}


class TextReceiver:
    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, data: bytes) -> dict[str, object]:
        text = data.decode("utf-8", errors="replace")
        if text.startswith("+ERR:"):
            return {}
        result: dict[str, object] = {}
        if text.endswith("\r\n"):
            if text.startswith(("+OK:GD=", "+OK:GA=")):
                result["date" if text.startswith("+OK:GD=") else "alarm_record"] = text[7:-2]
            elif text.startswith("+OK:ALR=GET"):
                result["alarm_record"] = text[12:-2]
            elif text.startswith("+OK:RTC="):
                result["date"] = text[8:-2]
        self.buffer = (self.buffer + text.replace("\r\n", ""))[-8192:]
        if self.buffer.startswith("+OK:Version=") and "Update=" in self.buffer:
            result["version"] = self.buffer[12:].replace(",", "\n").replace("Update=", "")
            self.buffer = ""
        record = result.get("alarm_record")
        if isinstance(record, str) and len(record) >= 8:
            status = record[-2:]
            if status == "02":
                result["alarm_list_complete"] = True
            elif record[1:2].isdigit():
                key = record[2:]
                result["alarm"] = {"weekday": int(record[1]), "key": key, "time": key[:4],
                                   "loop": key[-4:-2], "enabled": key[-2:]}
        return result
