"""MotoMotion 3.1.9 numeric rules, from the accepted row113 artifact.

The frames these values go into are built by ``codec/motomotion.py``.
"""

from __future__ import annotations

from math import ceil, floor, isnan

from ...codec.motomotion import Position, u16


def decimal(token: str) -> int:
    """Notification decimal domain; leading zeroes have no lexical length cap."""
    if not isinstance(token, str):
        raise TypeError("MotoMotion decimal must be a string")
    if not token or not token.isascii() or not token.isdecimal():
        raise ValueError("Invalid MotoMotion decimal token")
    value = 0
    for c in token:
        digit = ord(c) - 48
        if value > 922337203685477580 or (value == 922337203685477580 and digit > 7):
            raise ValueError("MotoMotion decimal exceeds signed int64")
        value = value * 10 + digit
    return value


def add64(left: int, right: int) -> int:
    bits = (left + right) & 0xFFFFFFFFFFFFFFFF
    return bits - 0x10000000000000000 if bits & 0x8000000000000000 else bits


def rgb_total(rgb: tuple[str, str, str]) -> int:
    r, g = decimal(rgb[0]), decimal(rgb[1])
    rg = add64(r, g)
    return add64(rg, decimal(rgb[2]))


def light_cycle(value: str, known: bool) -> int:
    if not known:
        return 32788
    # Python's positive modulo equals SDIV/MSUB followed by the source's negative correction.
    result = add64(decimal(value), 1) % 9
    return 32787 + (result or 1)


def color_parameters(rgb: tuple[int, int, int]) -> tuple[int, ...]:
    values = tuple(floor(c / 255 * 120) for c in rgb)
    return tuple(0 if c < 10 else c for c in values)


def round_away(value: float) -> int:
    return floor(value + 0.5) if value >= 0 else ceil(value - 0.5)


def interpolate(value: float, points: tuple[int, ...]) -> int:
    if value <= 500:
        return points[0]
    if value >= 640:
        return points[-1]
    index = int((value - 500) // 20)
    fraction = (value - (500 + index * 20)) / 20
    return round_away(points[index] + fraction * (points[index + 1] - points[index]))


def posture(name: str, height: float, buttocks: float, knee: float) -> Position:
    back, tilt, head, base, lumbar = {
        "upright": (1451, 0, 199, 0, 16),
        "recline": (873, 0, 143, 416, 166),
        "tv": (1368, 623, 167, 416, 16),
        "lay": (0, 0, 0, 0, 0),
    }[name]
    if name == "upright":
        base = interpolate(knee * 10, (926, 1065, 1308, 1441, 1536, 1710, 1981, 2144))
    base, back = u16(base), u16(back)
    if name == "upright":
        tilt = interpolate(knee * 10, (0, 117, 195, 77, 246, 437, 461, 629))
    tilt = u16(tilt)
    difference = (height - buttocks) * 10
    if name != "tv":
        low, span = {"upright": (425, 300), "recline": (625, 240), "lay": (225, 240)}[name]
        value = (difference - low) / span
        # ARM FMIN/FMAX propagates NaN; the separate lumbar clamp orders it above 1.
        clamped = value if isnan(value) else max(0.0, min(value, 1.0))
        head = round_away((1 - clamped) * 867)
    head = u16(head)
    if name == "lay":
        lumbar = 0
    elif name != "recline":
        value = ((buttocks - knee) * 10 - 400) / 200
        clamped = 1.0 if isnan(value) else max(0.0, min(value, 1.0))
        lumbar = round_away(clamped * 702 + 166)
    return Position(head, base, back, u16(lumbar), tilt)
