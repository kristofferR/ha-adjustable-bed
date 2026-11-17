"""Somos 1.0.0/code1, accepted row099: five explicit UI profiles.

Hand-transcribed accepted report data. D/E axes identify UI groups only;
physical anatomy and side are unverified. No generated catalog or runtime fetch.
"""

from dataclasses import dataclass
from typing import Final

from ..codec import keeson as codec
from ..execution import STREAM_HOLD
from .keeson import KeesonProfile, Release

REFRESH_MS: Final = 300
QUERY_INITIAL_S: Final = 2.0
QUERY_PERIOD_S: Final = 1.0
LIGHT_BUTTON: Final = 0x20000


@dataclass(frozen=True, slots=True)
class Product:
    label: str
    profile: KeesonProfile
    axes: tuple[tuple[str, int, int], ...]
    name_contains: str
    initial_ms: int
    query: bytes | None = None
    massage: bool = False


_HEAD_FOOT = (("head", 1, 2), ("feet", 4, 8))
_NEUTRAL = (("axis_1", 1, 2), ("axis_2", 4, 8), ("axis_3", 16, 32))
PROFILES: Final = {
    key: KeesonProfile(
        key=f"somos_{key}",
        execution=STREAM_HOLD,
        carrier="k1" if key in ("a", "c") else "p2" if key == "b" else "p2_side",
        header=0xE6,
        order="little",
        side=0 if key in ("a", "c") else None,
        transport="base" if key in ("a", "c") else "ksbt",
        notify="base" if key in ("a", "c") else "ksbt",
        fixed_write=True,
        hold=(10, REFRESH_MS),
        refresh_ms=REFRESH_MS,
        release=Release(steps=(), on_stop=False),
        presets={
            "flat": 0x08000000,
            "zero_g": 0x1000,
            **({"anti_snore": 0x8000} if key in ("b", "c", "e") else {}),
        },
        memory=memory,
        memory_slots=len(memory),
        lights=None,
        massage="none",
        tilt=False,
        lumbar=False,
        keeson_motor_names=False,
    )
    for key, memory in (
        ("a", {}),
        ("b", {1: 0x10000, 2: 0x2000, 3: 0x4000}),
        ("c", {1: 0x10000, 2: 0x4000}),
        ("d", {1: 0x10000}),
        ("e", {}),
    )
}
PRODUCTS: Final = {
    "a": Product("Signature (A)", PROFILES["a"], _HEAD_FOOT, "base-i5", 30),
    "b": Product(
        "Elite (B)",
        PROFILES["b"],
        (*_HEAD_FOOT, ("lumbar_tilt", 64, 128)),
        "KSBT03C3",
        0,
        codec.STATUS_QUERY,
        True,
    ),
    "c": Product(
        "Ultra (C)",
        PROFILES["c"],
        _HEAD_FOOT,
        "base-i5",
        30,
        codec.frame(0, header=0xE6, side=0),
        True,
    ),
    "d": Product("Signature Split Head (D)", PROFILES["d"], _NEUTRAL, "KSBT03CR", 0),
    "e": Product(
        "Ultra Split Head (E)",
        PROFILES["e"],
        _NEUTRAL,
        "KSBT03CR",
        0,
        codec.SOMOS_SPLIT_STATUS_QUERY,
        True,
    ),
}
CHOICES: Final = {key: product.label for key, product in PRODUCTS.items()}
MASSAGE_ACTIONS: Final = {
    "head_massage": 0x800,
    "foot_massage": 0x400,
    "massage_timer_cycle": 0x200,
}
