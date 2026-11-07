"""Exact AdjustableM5X4 app selectors, frames and state formulas.

The ten command enums are independent from device transport and UI selectors.
Artifact-derived integer fields have no inferred hardware units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ...codec import keeson, okin_5a, okin_ore
from ...codec import okin_nframe as codec
from ...profiles.okin_nframe import STARCODE_ABM5_4_PROFILES


@dataclass(frozen=True, slots=True)
class RetainedAppState:
    """Process-local state observed on one physical address, not fresh feedback."""

    address: str
    observed: bool
    massage_on: bool
    light_on: bool
    level: int
    timer_index: int
    head_intensity: int | None
    wave: int | None
    low_4b: int | None
    automatic_white_flag: bool | None
    last_light_time_ms: int | None


SELECTORS: Final = (
    "none",
    "BOX15",
    "BOX24",
    "BOX1220",
    "BOX1221",
    "BOX2422",
    "BOX2442",
    "BOX3633",
    "BOX25",
    "BOX25_STAR",
)
FIELDS: Final = (
    "b",
    "13",
    "1b",
    "23",
    "2b",
    "33",
    "3b",
    "43",
    "47",
    "4b",
    "53",
    "5f",
    "67",
    "6f",
    "77",
    "7f",
)
STATE_KEYS: Final = tuple("raw_" + field for field in FIELDS) + (
    "command_selector",
    "transport_selector",
    "ui_selector",
    "manufacturer",
    "firmware",
    "massage_timer",
    "light_level",
    "massage_on",
    "light_on",
    "wave",
    "head_intensity",
    "low_4b",
    "automatic_white_flag",
)

# The 40-bit and 64-bit key frames are the ``STARCODE_ABM5_4_PROFILES`` data;
# these are the selectors' other frames, as the app's builders emit them.
_BOX25_LIGHT_SWITCHES: Final = {"turnonUnderbedLighting": 1, "turnoffUnderbedLighting": 0}
FRAMES: Final[dict[str, dict[str, bytes]]] = {
    "none": {},
    "BOX15": {
        "headUp": keeson.frame(0x00000001, header=0xE6, side=0),
        "headDown": keeson.frame(0x00000002, header=0xE6, side=0),
        "footUp": keeson.frame(0x00000004, header=0xE6, side=0),
        "footDown": keeson.frame(0x00000008, header=0xE6, side=0),
        "unionUp": keeson.frame(0x00000005, header=0xE6, side=0),
        "unionDown": keeson.frame(0x0000000A, header=0xE6, side=0),
        "stop": keeson.frame(0x00000000, header=0xE6, side=0),
        "flatPosition": keeson.frame(0x08000000, header=0xE6, side=0),
        "tv": keeson.frame(0x00004000, header=0xE6, side=0),
        "lounge": keeson.frame(0x00002000, header=0xE6, side=0),
        "zeroGravity": keeson.frame(0x00001000, header=0xE6, side=0),
        "anti": keeson.frame(0x00008000, header=0xE6, side=0),
        "m1": keeson.frame(0x00010000, header=0xE6, side=0),
        "saveM1": keeson.frame(0x00010000, header=0xE6, side=0),
        "saveTv": keeson.frame(0x00004000, header=0xE6, side=0),
        "saveLounge": keeson.frame(0x00002000, header=0xE6, side=0),
        "saveZeroGravity": keeson.frame(0x00001000, header=0xE6, side=0),
        "underbedLighting": keeson.frame(0x00020000, header=0xE6, side=0),
    },
    "BOX24": {},
    "BOX1220": {
        "headUp": okin_ore.frame(0x2001),
        "headDown": okin_ore.frame(0x2002),
        "footUp": okin_ore.frame(0x2003),
        "footDown": okin_ore.frame(0x2004),
        "unionUp": okin_ore.frame(0x2004),
        "unionDown": okin_ore.frame(0x2004),
        "stop": okin_ore.frame(0x2000),
        "flatPosition": okin_ore.frame(0x2066),
        "tv": okin_ore.frame(0x2062),
        "lounge": okin_ore.frame(0x2061),
        "zeroGravity": okin_ore.frame(0x2060),
        "anti": okin_ore.frame(0x2063),
        "m1": okin_ore.frame(0x2064),
        "saveM1": okin_ore.frame(0x2064),
        "saveTv": okin_ore.frame(0x2062),
        "saveLounge": okin_ore.frame(0x2061),
        "saveZeroGravity": okin_ore.frame(0x2060),
        "underbedLighting": okin_ore.frame(0x2080),
    },
    "BOX1221": {},
    "BOX2422": {},
    "BOX2442": {},
    "BOX3633": {},
    "BOX25": {},
    "BOX25_STAR": {
        "headUp": okin_5a.command(0x00),
        "headDown": okin_5a.command(0x01),
        "footUp": okin_5a.command(0x02),
        "footDown": okin_5a.command(0x03),
        "unionUp": okin_5a.command(0x0C),
        "unionDown": okin_5a.command(0x0D),
        "stop": okin_5a.command(0x0F),
        "flatPosition": okin_5a.command(0x10),
        "tv": okin_5a.command(0x11),
        "lounge": okin_5a.command(0x17),
        "zeroGravity": okin_5a.command(0x13),
        "anti": okin_5a.command(0x16),
        "m1": okin_5a.command(0x1A),
        "saveM1": okin_5a.command(0x94),
        "saveTv": okin_5a.command(0x21),
        "saveLounge": okin_5a.command(0x27),
        "saveZeroGravity": okin_5a.command(0x23),
        "resetMemory": okin_5a.command(0x37),
        "massageOnOff": okin_5a.command(0x5A),
        "headStrengthAdd": okin_5a.command(0x60),
        "headStrengthReduce": okin_5a.command(0x61),
        "footStrengthAdd": okin_5a.command(0x62),
        "footStrengthReduce": okin_5a.command(0x63),
        "waveAdd": okin_5a.command(0x58),
        "waveReduce": okin_5a.command(0x59),
        "underbedLighting": okin_5a.command(0x71),
        "turnonUnderbedLighting": okin_5a.command(0x73),
        "turnoffUnderbedLighting": okin_5a.command(0x74),
        "change2White": okin_5a.command(0x79),
        "keepConnect": okin_5a.WAKE,
        "queryMassage": okin_5a.request(0xB0),
    },
}


def validate_selector(value: str) -> str:
    if value not in SELECTORS:
        raise ValueError("Unsupported AdjustableM5X4 selector")
    return value


def constructor_selector(name: str) -> str:
    return (
        "BOX25" if name.startswith("Star") else "BOX1220" if name.startswith("BLE") else "BOX3633"
    )


def scan_matches(name: str | None) -> bool:
    from ...discovery_hints.starcode import SCAN

    return bool(name) and SCAN.matches_name(name)


def manufacturer_selector(text: str) -> str:
    return "BOX25_STAR" if text == "star" else "BOX25"


@dataclass(frozen=True, slots=True)
class Transport:
    service: str
    write: str
    notify: str
    response: bool
    subscribe: bool
    wake: bool = False


UART: Final = Transport(
    "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
    False,
    True,
    True,
)
TRANSPORTS: Final = {
    "BOX1220": Transport(
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001001-0000-1000-8000-00805f9b34fb",
        "00001002-0000-1000-8000-00805f9b34fb",
        False,
        True,
    ),
    "BOX3633": Transport(
        "62741523-52f9-8864-b1ab-3b3a8d65950b",
        "62741525-52f9-8864-b1ab-3b3a8d65950b",
        "62741625-52f9-8864-b1ab-3b3a8d65950b",
        True,
        False,
    ),
    "BOX25": UART,
    "BOX25_STAR": UART,
}
MANUFACTURER_UUID: Final = "00002a29-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID: Final = "00002a28-0000-1000-8000-00805f9b34fb"


def build_frame(selector: str, action: str, value: int = 0) -> bytes:
    validate_selector(selector)
    star = selector == "BOX25_STAR"
    if action in ("changeMassageTime", "changeLightBrightness"):
        maximum = 255
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError("Input is outside the private one-byte builder domain")
        parameter = 7 if action == "changeMassageTime" else 0
        if star:
            return okin_5a.extended(parameter, value)
        return codec.extended(parameter, value)
    if frame := FRAMES[selector].get(action):
        return frame
    if not star:
        if action == "keepConnect":
            return okin_5a.WAKE
        if action == "queryMassage":
            return codec.request(0xB0)
        if selector == "BOX25" and action in _BOX25_LIGHT_SWITCHES:
            return codec.extended(0x01, _BOX25_LIGHT_SWITCHES[action])
    profile = STARCODE_ABM5_4_PROFILES.get(selector)
    if profile is not None and action in profile.keys:
        return codec.frame40(profile.keys[action])
    if profile is not None and action in profile.long_keys:
        return codec.frame(profile.long_keys[action], 8)
    raise ValueError("Action is unreachable for this command selector")


def initial_fields() -> dict[str, int | bool]:
    fields: dict[str, int | bool] = dict.fromkeys(FIELDS, 0)
    fields.update({"43": False, "47": True, "5f": True})
    return fields


def parse_fields(selector: str, data: bytes) -> dict[str, int | bool]:
    """Return only assigned fields; short indexed access cannot mutate state."""
    validate_selector(selector)
    b = data
    if selector == "BOX15":
        if len(b) > 3 and b[:2] == b"\xed\x80":
            if len(b) < 7:
                return {}
            return {"67": b[3], "7f": b[5], "6f": b[4], "77": b[6]}
        if len(b) == 23:
            timer, head, foot, wave = b[19] & 15, b[11] & 7, b[12], b[21]
        elif len(b) == 16:
            timer, head, foot, wave = b[14] & 15, b[7], b[8], b[14] >> 4
        elif len(b) == 10:
            timer, head, foot, wave = b[8] & 15, 0, 0, 1
        else:
            timer, head, foot, wave = 0, 0, 0, 1
        remap = {3: 2, 6: 3}
        return {"b": timer, "13": remap.get(head, head), "1b": remap.get(foot, foot), "23": wave}
    if len(b) < 2 or b[0] != 0xA5:
        return {}
    if b[1] == 0x0C:
        if len(b) < 8:
            return {}
        return {"67": b[6], "7f": b[4], "6f": b[7], "77": {5: 17, 6: 19}.get(b[5], 9)}
    modern = selector in ("BOX25", "BOX25_STAR")
    if b[1] == 0x0B:
        if len(b) < (16 if modern else 9) or (not modern and b[2] != 14):
            return {}
        t = (b[4] << 8) | b[5]
        timer = 1 if 0 < t <= 600 else 2 if 600 < t <= 1200 else 3 if 1200 < t <= 1800 else 0
        if modern:
            return {
                "b": timer,
                "23": b[6] & 15,
                "13": b[7] & 15,
                "1b": b[7] & 15,
                "53": b[14] >> 4,
                "4b": b[14] & 15,
                "43": (b[14] & 15) > 0,
                "47": b[15] >> 4 == 1,
            }
        head, foot = b[7] & 15, b[8]
        return {
            "b": timer * 10,
            "23": b[6] - 1,
            "13": head // 3 + head % 3 + int(head > 1),
            "1b": foot // 3 + foot % 3 + int(foot > 1),
        }
    if modern and b[1] == 0x0D and len(b) >= 19:
        return {"2b": min(b[4], 100), "33": min(b[6], 100), "3b": min(b[8], 100), "5f": b[17] == 0}
    return {}
