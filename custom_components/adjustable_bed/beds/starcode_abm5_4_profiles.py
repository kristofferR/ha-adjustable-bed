"""Exact AdjustableM5X4 app selectors, frames and state formulas.

The ten command enums are independent from device transport and UI selectors.
Artifact-derived integer fields have no inferred hardware units.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


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

FRAMES: Final[dict[str, dict[str, str]]] = {
    "none": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "underbedLighting": "08020002000000000000",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX15": {
        "headUp": "e6fe16010000000004",
        "headDown": "e6fe16020000000003",
        "footUp": "e6fe16040000000001",
        "footDown": "e6fe160800000000fd",
        "unionUp": "e6fe16050000000000",
        "unionDown": "e6fe160a00000000fb",
        "stop": "e6fe16000000000005",
        "flatPosition": "e6fe160000000800fd",
        "tv": "e6fe160040000000c5",
        "lounge": "e6fe160020000000e5",
        "zeroGravity": "e6fe160010000000f5",
        "anti": "e6fe16008000000085",
        "m1": "e6fe16000001000004",
        "saveM1": "e6fe16000001000004",
        "saveTv": "e6fe160040000000c5",
        "saveLounge": "e6fe160020000000e5",
        "saveZeroGravity": "e6fe160010000000f5",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "underbedLighting": "e6fe16000002000003",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX24": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "underbedLighting": "08020002000000000000",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX1220": {
        "headUp": "a55ade00002001",
        "headDown": "a55add00002002",
        "footUp": "a55adc00002003",
        "footDown": "a55adb00002004",
        "unionUp": "a55adb00002004",
        "unionDown": "a55adb00002004",
        "stop": "a55adf00002000",
        "flatPosition": "a55a7900002066",
        "tv": "a55a7d00002062",
        "lounge": "a55a7e00002061",
        "zeroGravity": "a55a7f00002060",
        "anti": "a55a7c00002063",
        "m1": "a55a7b00002064",
        "saveM1": "a55a7b00002064",
        "saveTv": "a55a7d00002062",
        "saveLounge": "a55a7e00002061",
        "saveZeroGravity": "a55a7f00002060",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "headStrengthAdd": "05020000080000",
        "headStrengthReduce": "05020080000000",
        "footStrengthAdd": "05020000040000",
        "footStrengthReduce": "05020100000000",
        "waveAdd": "05021000000000",
        "waveReduce": "05020400000000",
        "underbedLighting": "a55a5f00002080",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX1221": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "underbedLighting": "08020002000000000000",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX2422": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "underbedLighting": "08020002000000000000",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX2442": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "underbedLighting": "08020002000000000000",
        "turnonUnderbedLighting": "05020002000000",
        "turnoffUnderbedLighting": "05020002000000",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX3633": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "headStrengthAdd": "05020000080000",
        "headStrengthReduce": "05020080000000",
        "footStrengthAdd": "05020000040000",
        "footStrengthReduce": "05020100000000",
        "waveAdd": "05021000000000",
        "waveReduce": "05020400000000",
        "underbedLighting": "05020002000000",
        "turnonUnderbedLighting": "08020000000000000040",
        "turnoffUnderbedLighting": "08020000000000000080",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX25": {
        "headUp": "05020000000100",
        "headDown": "05020000000200",
        "footUp": "05020000000400",
        "footDown": "05020000000800",
        "unionUp": "05020000000500",
        "unionDown": "05020000000a00",
        "stop": "05020000000000",
        "flatPosition": "05020800000000",
        "tv": "05020000400000",
        "lounge": "05020000200000",
        "zeroGravity": "05020000100000",
        "anti": "05020000800000",
        "m1": "05020001000000",
        "saveM1": "05020001000000",
        "saveTv": "05028000400000",
        "saveLounge": "05028000200000",
        "saveZeroGravity": "05028000100000",
        "resetMemory": "05028800000000",
        "massageOnOff": "05020008000000",
        "headStrengthAdd": "05020000080000",
        "headStrengthReduce": "05020080000000",
        "footStrengthAdd": "05020000040000",
        "footStrengthReduce": "05020100000000",
        "waveAdd": "05021000000000",
        "waveReduce": "05020400000000",
        "underbedLighting": "08020002000000000000",
        "turnonUnderbedLighting": "04e001010000",
        "turnoffUnderbedLighting": "04e001000000",
        "change2White": "05020002000400",
        "keepConnect": "5a0b00a5",
        "queryMassage": "00b0",
    },
    "BOX25_STAR": {
        "headUp": "5a0103103000a5",
        "headDown": "5a0103103001a5",
        "footUp": "5a0103103002a5",
        "footDown": "5a0103103003a5",
        "unionUp": "5a010310300ca5",
        "unionDown": "5a010310300da5",
        "stop": "5a010310300fa5",
        "flatPosition": "5a0103103010a5",
        "tv": "5a0103103011a5",
        "lounge": "5a0103103017a5",
        "zeroGravity": "5a0103103013a5",
        "anti": "5a0103103016a5",
        "m1": "5a010310301aa5",
        "saveM1": "5a0103103094a5",
        "saveTv": "5a0103103021a5",
        "saveLounge": "5a0103103027a5",
        "saveZeroGravity": "5a0103103023a5",
        "resetMemory": "5a0103103037a5",
        "massageOnOff": "5a010310305aa5",
        "headStrengthAdd": "5a0103103060a5",
        "headStrengthReduce": "5a0103103061a5",
        "footStrengthAdd": "5a0103103062a5",
        "footStrengthReduce": "5a0103103063a5",
        "waveAdd": "5a0103103058a5",
        "waveReduce": "5a0103103059a5",
        "underbedLighting": "5a0103103071a5",
        "turnonUnderbedLighting": "5a0103103073a5",
        "turnoffUnderbedLighting": "5a0103103074a5",
        "change2White": "5a0103103079a5",
        "keepConnect": "5a0b00a5",
        "queryMassage": "5ab000a5",
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
    return bool(name) and name.lower().startswith("star")


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
    if action in ("changeMassageTime", "changeLightBrightness"):
        maximum = 255
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError("Input is outside the private one-byte builder domain")
        parameter = 7 if action == "changeMassageTime" else 0
        if selector == "BOX25_STAR":
            return bytes((0x5A, 0xE0, 4, parameter, value, 0, 0, 0xA5))
        return bytes((4, 0xE0, parameter, value, 0, 0))
    try:
        return bytes.fromhex(FRAMES[selector][action])
    except KeyError as err:
        raise ValueError("Action is unreachable for this command selector") from err


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
