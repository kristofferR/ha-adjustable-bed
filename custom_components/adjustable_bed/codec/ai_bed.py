"""AI Bed's AA/length/opcode/XOR format and bounded BB parsers.

Recovered from com.bedding.flutter_ai_bed 5.7.9(128). Raw fields have no
inferred physical units. Builders alone do not establish reachable workflows.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from functools import reduce
from operator import xor


def frame(opcode: int, parameters: Iterable[int] = ()) -> bytes:
    params = bytes(parameters)
    body = bytes((0xAA, len(params) + 4, opcode)) + params
    return body + bytes((reduce(xor, body, 0),))


def query(packages: Iterable[int]) -> bytes:
    values = tuple(packages)
    if not values or any(v not in (2, 4, 5, 7) for v in values):
        raise ValueError("Query packages must be nonempty and selected from 2,4,5,7")
    return frame(0x41, values)


def clock(now: datetime) -> bytes:
    return frame(
        4,
        (
            now.isoweekday(),
            now.year - 2000,
            now.month,
            now.day,
            now.hour,
            now.minute,
            now.second,
            0xF1,
            4,
            0x4F,
            0x70,
            0x1A,
            0xA0,
        ),
    )


def privacy(pin: str) -> bytes:
    if len(pin) != 3 or not pin.isascii() or not pin.isdecimal():
        raise ValueError("PIN must contain three decimal digits")
    return frame(0x9D, (int(c) for c in pin))


def vibration(part: int, mode: int, level: int) -> bytes:
    if part not in (0, 1) or not 0 <= mode <= 2 or not 1 <= level <= 15:
        raise ValueError("Invalid vibration part, mode or strength")
    return frame(0xA1, (part, mode, level, 1))


def vibration_both(mode: int, head: int, foot: int, preview: bool) -> bytes:
    if not 0 <= mode <= 2 or not 1 <= head <= 15 or not 1 <= foot <= 15:
        raise ValueError("Invalid vibration mode or strength")
    return frame(0xA1, (2, mode, head, foot, int(preview)))


def schedule(opcode: int, hour: int, minute: int, week: int) -> bytes:
    if (
        opcode not in (0x1E, 0x20, 0x2F)
        or not 0 <= hour <= 23
        or not 0 <= minute <= 59
        or not 0 <= week <= 255
    ):
        raise ValueError("Invalid schedule")
    tail = (0x14,) if opcode == 0x20 else (2,) if opcode == 0x2F else ()
    return frame(opcode, (hour, minute, week, *tail))


def waist(left: int, right: int) -> bytes:
    return frame(0x10, (left & 255, right & 255))


def heat(level: int) -> bytes:
    return frame(0x12, (level & 255,))


def sleep_aid(a_hex: str, b_hex: str, c_hex: str) -> bytes:
    """Reusable formula; the save UI's field mapping remains unresolved."""
    return frame(0x39, (15, 1, 1, int(a_hex, 16), int(b_hex, 16), int(c_hex, 16)))


def waist_state(
    last_left: int | None, last_right: int | None, left: int, right: int
) -> tuple[bytes, tuple[int, int], tuple[bool, bool]]:
    return (
        frame(0x10, (left if last_left != left else 0, right if last_right != right else 0)),
        (left, right),
        (left == 5, right == 5),
    )


def valid(data: bytes, opcode: int, minimum: int = 5) -> bool:
    return (
        len(data) >= minimum and data[0] == 0xBB and data[2] == opcode and reduce(xor, data, 0) == 0
    )


def qc_sample(d: bytes) -> dict[str, int | None] | None:
    if not valid(d, 0x46, 8):
        return None
    return {
        "status": d[3],
        "port0": d[4],
        "port1": d[5],
        "espDet": d[6],
        "headDuty": d[7] if d[1] >= 10 and len(d) >= 10 else None,
        "footDuty": d[8] if d[1] >= 10 and len(d) >= 10 else None,
    }


def qc_stm32(d: bytes) -> dict[str, int | None] | None:
    if not valid(d, 0x48, 17):
        return None

    def le(n: int) -> int:
        return int.from_bytes(d[n : n + 2], "little")

    return {
        "headHeight": le(3),
        "footHeight": le(7),
        "leftPressureAdc": le(9),
        "rightPressureAdc": le(11),
        "leftPressureStd": d[13],
        "rightPressureStd": d[14],
        "flags": d[15],
        "caps": d[16] if len(d) >= 18 else None,
        "headMax": le(17) if len(d) >= 22 else None,
        "footMax": le(19) if len(d) >= 22 else None,
    }


def qc_wave(d: bytes) -> dict[str, int | dict[str, int]] | None:
    if not valid(d, 0x49, 17):
        return None
    fields = ("min", "max", "mean", "jump", "rev", "periodMs")
    return {
        "status": d[3],
        "head": dict(zip(fields, d[4:10], strict=True)),
        "foot": dict(zip(fields, d[10:16], strict=True)),
    }


def parse_state(d: bytes) -> dict[str, int] | None:
    """Decode bed fields safely, retaining the app's 2305 checksum exception.

    Unlike the app's unchecked indexing, truncated packets are dropped. The
    2301/06 minimum permits the checksum to overlap the last indexed field.
    """
    if len(d) < 4 or d[0] != 0xBB or d[2] != 0x23:
        return None
    sub = d[3]
    if sub == 7:
        if len(d) < 15 or reduce(xor, d, 0):
            return None
        return {
            "headAngleRaw": d[7],
            "footAngleRaw": d[8],
            "motorGearTime": d[12],
            "smartSwitch": d[13],
        }
    definitions = {
        2: (
            11,
            4,
            (
                "inflationHour",
                "inflationMinute",
                "inflationWeek",
                "wakeHour",
                "wakeMinute",
                "wakeWeek",
            ),
        ),
        1: (
            17,
            5,
            (
                "height1",
                "height2",
                "height3",
                "height4",
                "heatLevel",
                "shockSwitch",
                "shockMode",
                "shockTime",
                "leftPressure",
                "rightPressure",
                "lampSwitch",
            ),
        ),
        5: (
            19,
            4,
            (
                "hour",
                "minute",
                "week",
                "headMassage",
                "footMassage",
                "mode",
                "headGear",
                "footGear",
                "selectedMode",
                "relaxationTime",
                "flatTime",
                "sleepHour",
                "sleepMinute",
                "sleepWeek",
                "sleepMode",
            ),
        ),
        6: (
            17,
            4,
            (
                "customSnoreEnabled",
                "customMode",
                "sensitivity",
                "headVib",
                "footVib",
                "headFootMode",
                "headLevel",
                "footLevel",
                "timeCycle",
                "interventionCount",
                "timeAfterVib",
                "timeBeforeSupine",
                "snoreEnabled",
            ),
        ),
        8: (14, 4, ("roomC", "humidity", "waistC", "footC", "waistLevel", "footLevel")),
    }
    if sub not in definitions:
        return None
    minimum, start, keys = definitions[sub]
    if len(d) < minimum or (sub != 5 and reduce(xor, d, 0)):
        return None
    result = dict(zip(keys, d[start : start + len(keys)], strict=True))
    if sub == 1 and len(d) >= 19:
        result["motorMode"] = d[17]
    if sub == 5:
        result["headGear"] //= 2
        result["footGear"] //= 2
    if sub == 8:
        result.update(minutes=int.from_bytes(d[10:12], "little"), seconds=d[12])
    return result
