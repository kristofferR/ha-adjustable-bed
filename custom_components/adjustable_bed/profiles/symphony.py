"""Symphony Sleep Sense 2.8.0 (194): independent product and driver choices.

Source: accepted row133, E-MODEL/E-CLOSURE/E-CALENDAR/E-ALARM. This is the
app's dispatch domain. It does not assert hardware compatibility for every cell.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from ..codec import keeson, okin_nframe, okin_soundwave
from ..execution import ExecutionCapabilities
from .keeson import KeesonProfile

type Wire = Literal["P1", "P2", "P3"]

SELECTORS: Final = {
    "0": "Unknown selector (app fallback)",
    "2": "Sleep Smart",
    "3": "CB.24.42.X",
    "4": "CB.23.43.12A / CB.13.X",
    "5": "CB.24.54.04",
    "6": "CB.24.42.17",
    "7": "CB.27.42.04",
    "8": "CB.27.42.10 / 11, CB.37.42.01, D6",
    "9": "New Sleep Smart",
}


@dataclass(frozen=True, slots=True)
class Product:
    """Only the axes and pages actually constructed by this app model."""

    name: str
    value: int
    axes: tuple[str, ...]
    page: str = "normal"
    massage: str | None = "normal"
    light: bool = True
    combined: bool = False


PRODUCTS: Final = {
    "0": Product("Unknown product (app fallback)", 0, ("head", "feet", "lumbar"), combined=True),
    "1": Product("ST800 (Storage Series)", 1, ("head", "feet"), "st800", None),
    "2": Product(
        "400E (Premier Series 400)", 2, ("head", "elevation", "feet"), "premier", None, False
    ),
    "3": Product(
        "500E (Premier Series 500)",
        3,
        ("head", "feet", "elevation"),
        "premier",
        "premier",
        combined=True,
    ),
    "4": Product(
        "600E (Premier Series 600)", 4, ("head", "feet", "neck", "elevation"), "premier", "premier"
    ),
    "5": Product("ES500 (Esquire)", 5, ("head", "feet", "elevation"), combined=True),
    "6": Product("ES600 (Elegance)", 6, ("head", "feet", "lumbar", "elevation")),
    "8": Product(
        "SS300 (Superior Sleep 300)",
        8,
        ("head", "feet", "elevation"),
        "premier",
        "premier",
        combined=True,
    ),
    "9": Product(
        "SS600 (Superior Sleep 600)",
        9,
        ("head", "feet", "lumbar", "elevation"),
        "premier",
        "premier",
    ),
    "10": Product(
        "ES500 Split-Head (Esquire)",
        10,
        ("head", "feet", "elevation"),
        "split_p3",
        "split_p3",
        combined=True,
    ),
    "11": Product(
        "SS400 (Superior Sleep 400)",
        11,
        ("head", "feet", "elevation"),
        massage="ss400",
        combined=True,
    ),
    "12": Product("ES700", 12, ("head", "feet", "elevation", "lumbar"), "soundwave", None),
    "13": Product(
        "SS800 (Superior Sleep 800)",
        13,
        ("head", "feet", "neck", "lumbar", "elevation"),
        "soundwave",
        None,
    ),
    "14": Product("ES500KGD", 14, ("head", "feet"), "normal", "kgd", combined=True),
    "15": Product(
        "ES500KGD-SHQ/SHK", 15, ("head", "feet", "elevation"), "split_p1", "split_p1", combined=True
    ),
    "20": Product(
        "ST800HILO (Storage Series)",
        20,
        ("head", "feet", "elevation", "head_foot_lift"),
        "hilo",
        None,
        False,
        True,
    ),
}

WORDS: Final = {
    "flat": 0x08000000,
    "zero_g": 0x1000,
    "anti_snore": 0x8000,
    "reading": 0x2000,
    "tv": 0x4000,
    "memory_1": 0x10000,
    "memory_2": 0x40000,
    "light": 0x20000,
    "massage_on": 0x100,
    "massage_off": 0x02000000,
    "intensity_up": 0xC00,
    "intensity_down": 0x01800000,
    "timer": 0x200,
    "wave_next": 0x10000000,
    "wave_previous": 0x04000000,
    "head_strength": 0x800,
    "foot_strength": 0x400,
}
P2_PRESETS: Final = {
    "zero_g": 1,
    "reading": 2,
    "tv": 3,
    "anti_snore": 4,
    "memory_1": 5,
    "memory_2": 6,
    "flat": 9,
}
P1_MODES: Final = {
    "memory_1": 17,
    "memory_2": 19,
    "zero_g": 13,
    "flat": 28,
    "anti_snore": 16,
    "massage": 9,
}
P3_MODES: Final = {
    "zero_g": 1,
    "reading": 2,
    "tv": 3,
    "anti_snore": 4,
    "memory_1": 5,
    "memory_2": 6,
    "light": 7,
    "massage": 8,
    "flat": 9,
}
ALARM_CHOICES: Final = {
    "normal": ("zero_g", "flat", "memory_1", "memory_2", "massage"),
    "premier": ("memory_1", "memory_2"),
    "st800": ("zero_g", "flat"),
    "hilo": ("zero_g", "flat", "memory_1", "tv", "reading", "anti_snore"),
    "split_p1": ("zero_g", "flat", "memory_1", "memory_2", "anti_snore", "massage"),
    "split_p3": ("zero_g", "flat", "memory_1", "memory_2", "anti_snore", "massage"),
    "soundwave": tuple(P3_MODES),
}
EXECUTION: Final = ExecutionCapabilities(hold="latched")


def scan_matches(name: str, manufacturer: Mapping[int, bytes]) -> bool:
    upper = name.upper()
    return bool(upper) and (
        "SMARTBED" in upper or "OKIN" in upper or ("SLEEP" in upper and bool(manufacturer))
    )


def selector_from_scan(name: str, manufacturer: Mapping[int, bytes], cached: int = 0) -> int:
    """Source overwrite order, with 0x59 (not tagged Smi 178)."""
    if cached:
        return cached
    upper, data, result = name.upper(), manufacturer.get(89, b""), 0
    if not upper:
        return 2
    if "SLEEP" in upper:
        result = 9 if len(data) >= 7 and data[6] & 128 else 2
    if "SMART" in upper:
        result = 5 if len(data) == 5 and data[-1] == 5 else 3
    if "SMARTBED417" in upper:
        result = 6
    if "SMARTBED7404" in upper:
        result = 7
    if any(key in upper for key in ("SMARTBED7410", "SMARTBED7411", "SMARTBED8401", "SMARTBEDD6")):
        result = 8
    if "OKIN" in upper:
        result = 4
    return result


def logical_name(manufacturer: Mapping[int, bytes]) -> str | None:
    data = manufacturer.get(89, b"")
    return data[1:7].hex() if len(data) >= 7 else None


@dataclass(frozen=True, slots=True)
class SymphonyProfile:
    product: Product
    selector: int
    side: int = 1

    @property
    def key(self) -> str:
        return f"symphony_{self.product.value}_{self.selector}"

    @property
    def execution(self) -> ExecutionCapabilities:
        return EXECUTION

    @property
    def wire(self) -> Wire:
        return "P1" if self.selector == 4 else "P2" if self.selector in (8, 9) else "P3"

    @property
    def position_wire(self) -> Wire:
        return (
            "P1"
            if self.product.page == "split_p1"
            else "P3"
            if self.product.page == "split_p3"
            else self.wire
        )

    @property
    def sonic(self) -> bool:
        return self.selector in (8, 9)

    @property
    def presets(self) -> tuple[str, ...]:
        if self.product.page == "st800":
            return ("zero_g", "flat")
        if self.product.page == "hilo":
            return ("memory_1", "flat", "reading", "tv", "zero_g", "anti_snore")
        return ("memory_1", "memory_2", "flat", "zero_g", "anti_snore")

    @property
    def saves(self) -> tuple[str, ...]:
        if self.product.page in ("soundwave", "hilo"):
            return tuple(key for key in self.presets if key != "flat")
        return ()

    @property
    def alarm_modes(self) -> tuple[str, ...]:
        return ALARM_CHOICES[self.product.page]


def encode_word(wire: Wire, word: int, side: int = 0) -> bytes:
    if wire == "P1":
        return keeson.frame(word, header=0xE6, order="little", side=side)
    if wire == "P3":
        return okin_nframe.frame40(word, side)
    if word < 256:
        return okin_soundwave.movement(word)
    if word in (WORDS["massage_on"], WORDS["massage_off"]):
        return okin_soundwave.record(2, 1, (0x40 if word == WORDS["massage_on"] else 0x41,))
    key = next((key for key, value in WORDS.items() if value == word), None)
    if key in P2_PRESETS:
        return okin_soundwave.preset(P2_PRESETS[key])
    raise ValueError("This word has no source-proven SoundWave encoding")


def movement(profile: SymphonyProfile, axis: str, up: bool, side: int) -> bytes:
    if axis not in (*profile.product.axes, *(("head_foot",) if profile.product.combined else ())):
        raise ValueError(f"The selected product has no {axis} control")
    wire = profile.position_wire
    masks = {
        "head": 1,
        "feet": 4,
        "head_foot": 5,
        "neck": 16,
        "lumbar": 16,
        "elevation": 64,
        "head_foot_lift": 80,
    }
    if profile.product.value == 13:
        masks["lumbar"] = 64
        if axis == "elevation":
            return okin_soundwave.movement(0, 1 if up else 2)
    if profile.product.page == "hilo":
        masks["elevation"] = 64 if profile.selector == 2 else 16
    if profile.product.page == "split_p1":
        masks.update(head=16 if side == 1 else 64, head_foot=20 if side == 1 else 68, elevation=1)
    if profile.product.page == "split_p3":
        masks["elevation"] = 64
    mask = masks[axis] * (1 if up else 2)
    if axis == "head_foot_lift":
        wire = "P2" if profile.sonic else "P3"
    return encode_word(wire, mask, side if profile.product.page in ("split_p1", "split_p3") else 0)


def stops(
    profile: SymphonyProfile, side: int, *, wire: Wire | None = None
) -> tuple[int, tuple[bytes, ...]]:
    selected = wire or profile.position_wire
    if selected == "P2":
        return 0, (okin_soundwave.movement(0), okin_soundwave.record(1, 2, ()))
    split = profile.product.page in ("split_p1", "split_p3")
    return (100 if selected == "P3" or split else 300), (
        encode_word(selected, 0, side if split else 0),
    )


def preset(profile: SymphonyProfile, name: str, side: int, *, save: bool = False) -> bytes:
    if name not in (profile.saves if save else profile.presets):
        raise ValueError("This product has no requested recall/save action")
    if profile.product.page == "soundwave":
        return okin_soundwave.preset(P2_PRESETS[name] + (32 if save else 0), save=save)
    if save:  # HILO's Save modifier invokes fixed P3 builders.
        return encode_word("P3", WORDS[name] | 0x40000)
    if profile.product.page == "hilo" and name in ("reading", "tv"):
        return encode_word("P3", WORDS[name])
    return encode_word(
        profile.position_wire,
        WORDS[name],
        side if profile.product.page in ("split_p1", "split_p3") else 0,
    )


def clock(selector: int, now: datetime) -> bytes:
    fields = (
        now.year - 2000,
        now.month - 1,
        now.day,
        now.isoweekday(),
        now.hour,
        now.minute,
        now.second,
    )
    if selector == 4:
        return keeson.clock(now)
    if selector == 5:

        def bcd(value: int) -> int:
            return (value // 10) * 16 + value % 10

        return okin_nframe.clock(
            (
                bcd(now.year - 2000),
                bcd(now.month),
                bcd(now.day),
                now.isoweekday() % 7,
                bcd(now.hour),
                bcd(now.minute),
                bcd(now.second),
            )
        )
    if selector == 2:
        fields = (
            now.year - 1900,
            now.month - 1,
            now.day,
            now.isoweekday() - 1,
            now.hour,
            now.minute,
            now.second,
        )
    if selector in (8, 9):
        return okin_soundwave.record(
            3,
            1,
            (
                now.year - 2000,
                now.month,
                now.day,
                now.isoweekday(),
                now.hour,
                now.minute,
                now.second,
            ),
        )
    return okin_nframe.clock(fields)


def alarm_week(mask: int, requested: datetime, now: datetime) -> int:
    """Keep the artifact's raw weekday/equal-time behavior, including Sunday 128."""
    if mask > 0 and mask != 128:
        return mask
    raw_weekday = now.isoweekday()
    exponent = (
        (raw_weekday + 1) % 7
        if int(requested.timestamp() * 1000) <= int(now.timestamp() * 1000)
        else raw_weekday
    )
    return 1 << exponent


def alarm_mode(selector: int, mode: str, *, split: bool = False) -> int:
    if split:
        return {key: P3_MODES[key] for key in ALARM_CHOICES["split_p3"]}.get(mode, 0)
    if selector == 4:
        return P1_MODES.get(mode, 0)
    if selector == 5:
        return {"memory_1": 2, "memory_2": 3}.get(mode, 0)
    if selector == 7 and mode == "memory_2":
        return 0
    return P3_MODES.get(mode, 0)


def alarm(
    profile: SymphonyProfile,
    *,
    enabled: bool,
    hour: int,
    minute: int,
    week: int,
    mode: str,
    side: int,
    cache: bytes | None = None,
) -> bytes:
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= week <= 255:
        raise ValueError("Invalid alarm time or week mask")
    if mode not in profile.alarm_modes:
        raise ValueError("This product's alarm page does not offer that mode")
    if profile.product.page == "split_p1":
        i = 3 + 4 * side
        if cache is None or cache[:3] != b"\xed\x80\x03" or len(cache) < 16:
            raise ValueError("Refresh a complete current-session split alarm response first")
        data = bytearray(cache[:-1])
        data[i : i + 4] = (
            bytes((hour, minute, week, P1_MODES.get(mode, 0))) if enabled else bytes(4)
        )
        return keeson.checked(bytes(data))
    if profile.product.page == "soundwave":
        return (
            soundwave_alarm(hour, minute, week, P3_MODES[mode])
            if enabled
            else okin_soundwave.record(3, 2, (1, 0, 0, 0, 0, 0, 0))
        )
    split = profile.product.page == "split_p3"
    if not split and profile.selector == 4:
        return keeson.alarm_table(
            3, bytes((hour, minute, week, alarm_mode(4, mode))) if enabled else bytes(4)
        )
    if not enabled:
        return okin_nframe.alarm((0, 0, 0, 0, 0, 0, side if split else 0))
    if profile.selector == 5:
        hour, minute = (hour // 10) * 16 + hour % 10, (minute // 10) * 16 + minute % 10
    return okin_nframe.alarm(
        (
            week,
            alarm_mode(profile.selector, mode, split=split),
            hour,
            minute,
            0,
            1,
            side if split else 1,
        )
    )


def light(color: int, brightness: int) -> bytes:
    return okin_soundwave.record(
        4, 1, (2, max(1, min(7, color)), 0, 0, 0, max(20, min(80, brightness))), size=5
    )


def soundwave_alarm(hour: int, minute: int, week: int, mode_index: int) -> bytes:
    return okin_soundwave.record(3, 2, (1, week, max(1, min(9, mode_index)), 1, hour, minute, 0))


def sonic_timer(current: int) -> bytes:
    next_index = current + 1
    if next_index > 3:
        next_index = 1
    seconds = next_index * 600
    return okin_soundwave.record(6, 11, (0, 1, seconds & 255, seconds >> 8))


def sonic_strength(current: int, zone: int) -> bytes:
    raw = 2 * current + 2
    value = 4 if raw >= 8 or raw < 4 else 6 if raw < 6 else 8 if raw < 8 else 0
    return okin_soundwave.record(6, 2, (0, zone, value))


def anti_snore(
    profile: SymphonyProfile, *, enabled: bool, axis: str, strength: int, demo: bool = False
) -> bytes:
    if axis not in ("head", "elevation"):
        raise ValueError("Choose Head or Elevation")
    p2 = profile.sonic
    if demo:
        selector = 1 if axis == "head" else 2
        return (
            okin_soundwave.record(7, 1, (2, 2, 1, selector, 0, 0, 0, 0))
            if p2
            else okin_nframe.parameter_record(11, (2, 1, selector), size=4)
        )
    if enabled and strength not in ((1, 2, 3) if p2 else (1, 3, 6)):
        raise ValueError("Invalid strength for the selected anti-snore page")
    selector = (
        (4 if profile.product.value == 10 else 1)
        if axis == "head"
        else (1 if profile.product.value == 10 else 6 if p2 and profile.product.value == 13 else 2)
    )
    if p2:
        return okin_soundwave.record(
            7,
            1,
            (int(enabled), 2, strength if enabled else 0, selector if enabled else 0, 0, 0, 0, 0),
        )
    return okin_nframe.parameter_record(11, (int(enabled), strength, selector), size=4)


@dataclass(frozen=True, kw_only=True)
class SymphonyWordProfile(KeesonProfile):
    """The shared Keeson controller's word contract plus this app's routing."""

    app: SymphonyProfile


def word_profile(app: SymphonyProfile) -> SymphonyWordProfile:
    return SymphonyWordProfile(
        key="symphony",
        app=app,
        execution=EXECUTION,
        hold=None,
        header=0xE6,
        side=0,
        order="little",
        keeson_motor_names=False,
        lights=None,
        massage="none",
        tilt=False,
        lumbar=False,
    )
