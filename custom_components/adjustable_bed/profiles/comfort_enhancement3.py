"""Comfort Enhancement 3 / Comfort Plus3 1.4.0 (5), accepted row083.

Hand-maintained from the accepted APK Protocol Audit variant inventory and
literal vectors. Group names describe app controls, not measured anatomy.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from ..const import BED_TYPE_COMFORT_ENHANCEMENT3, CONF_COMFORT_ENHANCEMENT3_REMOTE_CODE
from ..execution import STREAM_HOLD
from .okin_nframe import Hold, OkinNFrameProfile, Tap

REMOTE_CODE: Final = CONF_COMFORT_ENHANCEMENT3_REMOTE_CODE


@dataclass(frozen=True, slots=True)
class Remote:
    codes: tuple[str, ...]
    groups: tuple[tuple[str, str, int, int], ...]
    m2: bool
    zg: bool
    tv: bool
    qs: bool
    massage: bool
    wake_massage: bool
    flat: bool = True
    light: bool = True
    tilt: bool = False

    @property
    def wake_presets(self) -> tuple[str, ...]:
        return (
            "None",
            "M1",
            *(("M2",) if self.m2 else ()),
            *(("Zero Gravity",) if self.zg else ()),
            *(("TV",) if self.tv else ()),
            *(("QS",) if self.qs else ()),
        )


# fmt: off
_M34 = ("m3_m4", "M3 + M4", 0x50, 0xA0)
_MID34 = ("midbody", "MidBody (M3 + M4)", 0x50, 0xA0)
_MID3 = ("midbody", "MidBody (M3)", 0x10, 0x20)
_TFLAT = ("tflat", "TFlat (M4)", 0x40, 0x80)
REMOTES: Final = (
    Remote(("89746", "90882", "91334"), (), True, True, False, False, False, False),
    Remote(("92063", "91751"), (), True, True, False, False, False, False, light=False),
    Remote(("89925", "90568"), (_M34,), True, True, False, False, False, False),
    Remote(("90566", "89927", "92169"), (), True, True, True, False, True, True),
    Remote(("90188", "92177"), (("lumbar", "Lumbar (M3)", 0x10, 0x20),), False, True, False, True, True, True),
    Remote(("90192",), (_M34,), False, True, False, True, True, True),
    Remote(("91869", "91871", "92379"), (_M34,), False, True, False, False, True, True, tilt=True),
    Remote(("93567",), (("head_foot", "Head + Foot (M1 + M2)", 5, 10),), True, True, True, False, False, False),
    Remote(("93372",), (("head_foot", "Head + Foot (M1 + M2)", 5, 10),), True, True, True, False, True, True),
    Remote(("93375",), (_MID34,), True, True, True, False, True, True),
    Remote(("93379",), (_M34, _TFLAT), True, True, True, False, True, True),
    Remote(("PMT-5019",), (_MID34,), True, False, False, False, False, False, flat=False),
    Remote(("PMT-5020",), (("head_tilt", "HeadTilt (M3 + M4)", 0x50, 0xA0),), True, False, False, False, False, True, flat=False),
    Remote(("95563",), (_MID3, _TFLAT), True, True, True, False, True, True),
    Remote(("PMT-5024",), (_MID3, ("head_tilt", "HeadTilt (M4)", 0x40, 0x80)), True, True, True, False, True, True),
)
# fmt: on
CODE_INDEX: Final = {code: i for i, remote in enumerate(REMOTES) for code in remote.codes}
CHOICES: Final = {
    f"apex_{i}": f"{i}: {', '.join(remote.codes)}" for i, remote in enumerate(REMOTES)
}
CHOICES_WITH_CODE: Final = {**CHOICES, "15": "Enter the remote code"}
MASSAGE_KEYS: Final = {
    "massage_duration": 0x02000000,
    "massage_head": 0x800,
    "massage_foot": 0x400000,
    "massage_wave": 0x80000000,
    "massage_stop": 0x400,
}


def profile(index: int) -> OkinNFrameProfile:
    remote = REMOTES[index]
    keys = {
        "head_up": 1,
        "head_down": 2,
        "feet_up": 4,
        "feet_down": 8,
        "memory_1": 0x1000,
        "memory_store": 0x10000,
    }
    for key, _, up, down in remote.groups:
        keys |= {f"{key}_up": up, f"{key}_down": down}
    for enabled, name, word in (
        (remote.m2, "memory_2", 0x2000),
        (remote.zg, "zero_g", 0x4000),
        (remote.tv, "tv", 0x3000),
        (remote.tv or remote.qs, "qs", 0x8000),
        (remote.flat, "flat", 0x10000000),
        (remote.light, "light", 0x20000),
        (remote.tilt, "tilt", 0x90),
    ):
        if enabled:
            keys[name] = word
    if remote.massage:
        keys |= MASSAGE_KEYS
    return OkinNFrameProfile(
        key=f"apex_{index}",
        name=f"Comfort Enhancement 3 remote {index}",
        bed_types=(BED_TYPE_COMFORT_ENHANCEMENT3,),
        write="response",
        envelope="plain",
        axes=("head", "feet"),
        keys=MappingProxyType(keys),
        hold=Hold(repeat_ms=100, releases=2, release_after_ms=200, release_ms=100),
        execution=STREAM_HOLD,
        # Favorites ZG self-rejects after one write. One safe press preserves
        # that effect; no uniform held preset wire cadence is inferred.
        recall=Tap(repeats=1, releases=2),
        memory_slots=2 if remote.m2 else 1,
    )


PROFILES: Final = {f"apex_{i}": profile(i) for i in range(len(REMOTES))}


def resolve(variant: str | None, code: str = "") -> int:
    if variant == "15":
        if code not in CODE_INDEX:
            raise ValueError("Choose an exact supported remote code")
        return CODE_INDEX[code]
    if variant in PROFILES:
        return int(variant.removeprefix("apex_"))
    if variant in (None, "auto"):
        # The factory's unconfigured preview. Setup requires an explicit choice.
        return 0
    raise ValueError("Unknown Comfort Enhancement 3 remote profile")
