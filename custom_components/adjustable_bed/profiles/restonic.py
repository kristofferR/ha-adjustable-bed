"""Restonic 1.0.1 (okin.bedding.restonic): independent layout and BLE branch.

Hand-transcribed from the accepted artifact report. No generated catalog.
Words are app controls, not inferred capabilities of a physical model.
"""

from dataclasses import dataclass
from typing import Final, Literal

from ..codec import keeson, okin_ore
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

Branch = Literal["box15", "box1220", "box24"]
REFRESH_MS: Final = 200
STOP_COUNT: Final = 2
BRANCH_CHOICES: Final = {
    "box15": "BOX15 (other nonempty Bluetooth names)",
    "box1220": "BOX1220 (BLE prefix, case sensitive)",
    "box24": "BOX24 (Smartbed prefix, case sensitive)",
}
LAYOUT_CHOICES: Final = {"prime": "Prime", "lombar": "Lombar", "infinity": "Infinity"}


@dataclass(frozen=True, slots=True)
class Transport:
    service: str
    write: str
    notify_service: str
    notify: str
    response: bool


_BASE = "-0000-1000-8000-00805f9b34fb"
_NUS = "-b5a3-f393-e0a9-e50e24dcca9e"
TRANSPORTS: Final = {
    "box15": Transport(
        "0000ffe5" + _BASE, "0000ffe9" + _BASE, "0000ffe0" + _BASE, "0000ffe4" + _BASE, True
    ),
    "box1220": Transport(
        "00001000" + _BASE, "00001001" + _BASE, "00001000" + _BASE, "00001002" + _BASE, False
    ),
    "box24": Transport(
        "6e400001" + _NUS, "6e400002" + _NUS, "6e400001" + _NUS, "6e400003" + _NUS, True
    ),
}
# fmt: off
WORDS: Final = {
    "anti": 0x8000, "underbedLighting": 0x20000, "lounge": 0x2000,
    "m1": 0x10000, "tv": 0x4000, "zeroGravity": 0x1000,
    "massageSwitch": 0x100, "waveAdd": 0x10000000, "massageTimer": 0x200,
    "footStrengthAdd": 0x400, "headStrengthAdd": 0x800,
    "neckTiltDown": 0x20, "neckTiltUp": 0x10,
    "lumbarDown": 0x80, "lumbarUp": 0x40,
    "footDown": 0x08, "footUp": 0x04, "headDown": 0x02, "headUp": 0x01,
    "flatPosition": 0x08000000, "stop": 0,
}
_OPCODES: Final = {
    "anti": 0x63, "underbedLighting": 0x80, "lounge": 0x61, "m1": 0x64,
    "tv": 0x62, "zeroGravity": 0x60, "footDown": 4, "footUp": 3,
    "headDown": 2, "headUp": 1, "flatPosition": 0x66, "stop": 0,
}
# fmt: on
_P3_WORDS: Final = {**WORDS, "lumbarUp": 0x10, "lumbarDown": 0x20, "massageSwitch": 0x200}
ACTION_BY_WORD: Final = {word: action for action, word in WORDS.items()}
_COMMON: Final = (
    "flatPosition",
    "headUp",
    "headDown",
    "footUp",
    "footDown",
    "zeroGravity",
    "underbedLighting",
)
MASSAGE: Final = ("headStrengthAdd", "footStrengthAdd", "massageTimer", "waveAdd", "massageSwitch")
AXES: Final = {
    "prime": ("head", "feet"),
    "lombar": ("head", "feet", "lumbar"),
    "infinity": ("head", "feet", "lumbar", "neck"),
}
ACTIONS: Final = {
    "prime": (*_COMMON, "m1", "anti"),
    "lombar": (*_COMMON, "lumbarUp", "lumbarDown", *MASSAGE, "m1", "lounge"),
    "infinity": (*_COMMON, "lumbarUp", "lumbarDown", "neckTiltUp", "neckTiltDown", *MASSAGE, "tv"),
}
PROFILES: Final = {
    layout: KeesonProfile(
        key=f"restonic_{layout}",
        execution=STREAM_HOLD,
        hold=(10, REFRESH_MS),
        refresh_ms=REFRESH_MS,
        release=Release(steps=((0, 0), (REFRESH_MS, 0)), after_tap=True),
        presets={
            "flat": WORDS["flatPosition"],
            "zero_g": WORDS["zeroGravity"],
            **({"anti_snore": WORDS["anti"]} if layout == "prime" else {}),
            **({"lounge": WORDS["lounge"]} if layout == "lombar" else {}),
            **({"tv": WORDS["tv"]} if layout == "infinity" else {}),
        },
        memory={1: WORDS["m1"]} if layout != "infinity" else {},
        memory_slots=1 if layout != "infinity" else 0,
        lights=None,
        massage="none",
        tilt=False,
        lumbar=layout != "prime",
        keeson_motor_names=False,
    )
    for layout in LAYOUT_CHOICES
}


def branch_for_name(name: str) -> Branch | None:
    """Exact artifact selector; broad fallback is never an app identity signal."""
    return (
        "box24"
        if name.startswith("Smartbed")
        else "box1220"
        if name.startswith("BLE")
        else "box15"
        if name
        else None
    )


def encode(branch: str, action: str) -> bytes:
    """Reuse only the carriers proven by all 63 independent final literals."""
    if branch == "box15":
        return keeson.frame(WORDS[action], header=0xE6, side=0)
    if branch == "box1220" and action in _OPCODES:
        return okin_ore.frame(0x2000 | _OPCODES[action])
    if branch in ("box24", "box1220"):
        return keeson.p2(_P3_WORDS[action], "p2_side")
    raise ValueError("Unknown Restonic BLE branch")
