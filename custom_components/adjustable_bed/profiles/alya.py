"""Alya Smart Furnishing 1.0.2's explicit layouts over ORE, Keeson and N-frame.

Evidence: accepted APK Protocol Audit row090, E-SELECT/E-BUILDERS/E-RELEASE.
The advertised DeviceType and app motor picker select these twelve layouts.
Shared UUIDs cannot select an app. No model-to-physical-bed mapping is known.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from ..codec import keeson, okin_nframe, okin_ore
from ..execution import STREAM_HOLD, ExecutionCapabilities

type Protocol = Literal["P1", "P2", "P3", "P4"]


@dataclass(frozen=True)
class Command:
    value: int
    payload: bytes = b""
    tail: int = 0
    setting: int = 0

    def encode(self, protocol: Protocol, side: int = 0) -> bytes:
        if protocol == "P1":
            return okin_ore.frame(self.value, self.payload)
        if protocol == "P2":
            return keeson.frame(self.value, header=0xE6, side=self.tail)
        if self.setting:
            return okin_nframe.massage_setting(self.setting, self.value, side)
        return okin_nframe.frame40(self.value, side)


@dataclass(frozen=True, kw_only=True)
class AlyaProfile:
    key: str
    name: str
    device_type: str
    motors: int
    protocol: Protocol
    commands: Mapping[str, Command]
    execution: ExecutionCapabilities = STREAM_HOLD
    refresh_ms: int = 300
    release_ms: int = 300

    @property
    def axes(self) -> tuple[str, ...]:
        return (
            "back",
            "legs",
            *(("head",) if self.motors >= 3 else ()),
            *(("lumbar",) if self.motors >= 4 else ()),
        )

    @property
    def side_controls(self) -> bool:
        return self.device_type == "DACHENG" and self.motors == 5


# Values from this APK, independently checked by all frozen command vectors.
_MOVES: Final = {
    "headup": 1,
    "headdown": 2,
    "footup": 4,
    "footdown": 8,
    "unionup": 5,
    "uniondown": 10,
    "headtiltup": 16,
    "headtiltdown": 32,
    "lumbarup": 64,
    "lumbardown": 128,
    "hpsup": 0x40000000,
    "hpsdown": 0x80000000,
}
_PRESETS: Final = {
    "stop": 0,
    "flat": 0x08000000,
    "anti": 0x8000,
    "lounge": 0x2000,
    "memory": 0x10000,
    "m1": 0x10000,
    "m2": 0x40000,
    "zg": 0x1000,
    "tv": 0x4000,
    "light": 0x20000,
}
_ORE: Final = {
    "headup": 0x2001,
    "headdown": 0x2002,
    "footup": 0x2003,
    "footdown": 0x2004,
    "unionup": 0x200B,
    "uniondown": 0x200C,
    "headtiltup": 0x2005,
    "headtiltdown": 0x2006,
    "lumbarup": 0x2007,
    "lumbardown": 0x2008,
    "stop": 0x2000,
    "flat": 0x2066,
    "anti": 0x2063,
    "lounge": 0x2061,
    "memory": 0x2064,
    "zg": 0x2060,
    "tv": 0x2062,
    "light": 0x2080,
}


def commands(protocol: Protocol) -> dict[str, Command]:
    """The app's constructors; layout reachability is applied separately."""
    result = {
        k: Command(v) for k, v in (_ORE if protocol == "P1" else {**_MOVES, **_PRESETS}).items()
    }
    if protocol == "P1":
        result.update(
            {
                "massage-on": Command(0x2081, b"\x01"),
                "massage-off": Command(0x2000, b"\x00"),
                "query-massage": Command(0x2050),
            }
        )
        for zone, plus, minus, absolute in (
            ("head", 0x2020, 0x2021, 0x2084),
            ("foot", 0x2030, 0x2031, 0x2085),
            ("", 0x2096, 0x2097, 0x2086),
        ):
            result[zone + "intensityincrease"] = Command(plus)
            result[zone + "intensitydecrease"] = Command(minus)
            for level in (1, 2, 3):
                result[f"{zone}intensity{level}"] = Command(absolute, bytes((level,)))
        result.update({"waveincrease": Command(0x2070), "wavedecrease": Command(0x2071)})
        for level in (1, 2, 3):
            result[f"wave{level}"] = Command(0x2083, bytes((level,)))
            result[f"time{level * 10}"] = Command(0x2082, bytes((level * 10,)))
    else:
        result.update({"massage-on": Command(0x100), "massage-off": Command(0x100)})
        for zone, plus, minus in (
            ("head", 0x800, 0x800000),
            ("foot", 0x400, 0x1000000),
            ("", 0xC00, 0x1800000),
        ):
            result[zone + "intensityincrease"] = Command(plus)
            result[zone + "intensitydecrease"] = Command(minus)
            for level in (1, 2, 3):
                result[f"{zone}intensity{level}"] = (
                    Command(1 << (level + 18))
                    if protocol == "P2" or not zone
                    else Command(level, setting=2 if zone == "head" else 3)
                )
        result.update(
            {
                "waveincrease": Command(0x10000000),
                "wavedecrease": Command(0x4000000),
                "timeincrease": Command(0x200),
                "timedecrease": Command(0x100000),
                "timer": Command(0x200),
            }
        )
        for level in (1, 2, 3):
            result[f"time{level * 10}"] = (
                Command(0x200, tail=level * 64) if protocol == "P2" else Command(level, setting=1)
            )
        for level in (1, 2, 3) if protocol == "P2" else (2, 3, 4):
            result[f"wave{level}"] = (
                Command(0x10000000, tail=level * 64)
                if protocol == "P2"
                else Command(level, setting=4)
            )
    return result


def _profile(device: str, count: int, protocol: Protocol) -> AlyaProfile:
    available = commands(protocol)
    available = {key: available[key] for key in _REACHABLE[f"{device.lower()}_{count}"]}
    return AlyaProfile(
        key=f"{device.lower()}_{count}",
        name=f"Alya {device}, {count} motors",
        device_type=device,
        motors=count,
        protocol=protocol,
        commands=MappingProxyType(available),
    )


# Per-layout UI controls from commands.json; no dormant builder branch is exposed.
_REACHABLE: Final = {
    "bluetooth_2": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headup",
        "intensity1",
        "intensity2",
        "intensity3",
        "intensitydecrease",
        "intensityincrease",
        "light",
        "lounge",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "tv",
        "uniondown",
        "unionup",
        "wave1",
        "wave2",
        "wave3",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "bluetooth_3": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headtiltdown",
        "headtiltup",
        "headup",
        "intensity1",
        "intensity2",
        "intensity3",
        "intensitydecrease",
        "intensityincrease",
        "light",
        "lounge",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "tv",
        "uniondown",
        "unionup",
        "wave1",
        "wave2",
        "wave3",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "bluetooth_4": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headtiltdown",
        "headtiltup",
        "headup",
        "intensity1",
        "intensity2",
        "intensity3",
        "intensitydecrease",
        "intensityincrease",
        "light",
        "lounge",
        "lumbardown",
        "lumbarup",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "tv",
        "uniondown",
        "unionup",
        "wave1",
        "wave2",
        "wave3",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb_2": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headup",
        "intensity1",
        "intensity2",
        "intensity3",
        "intensitydecrease",
        "intensityincrease",
        "light",
        "lounge",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "tv",
        "uniondown",
        "unionup",
        "wave1",
        "wave2",
        "wave3",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb_3": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headtiltdown",
        "headtiltup",
        "headup",
        "intensity1",
        "intensity2",
        "intensity3",
        "intensitydecrease",
        "intensityincrease",
        "light",
        "lounge",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "tv",
        "uniondown",
        "unionup",
        "wave1",
        "wave2",
        "wave3",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb_4": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headtiltdown",
        "headtiltup",
        "headup",
        "intensity1",
        "intensity2",
        "intensity3",
        "intensitydecrease",
        "intensityincrease",
        "light",
        "lounge",
        "lumbardown",
        "lumbarup",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "tv",
        "uniondown",
        "unionup",
        "wave1",
        "wave2",
        "wave3",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb1221_2": (
        "anti",
        "flat",
        "footdown",
        "footup",
        "headdown",
        "headintensity1",
        "headintensity2",
        "headintensity3",
        "headintensitydecrease",
        "headintensityincrease",
        "headup",
        "m1",
        "m2",
        "massage-off",
        "massage-on",
        "stop",
        "time10",
        "time20",
        "time30",
        "timedecrease",
        "timeincrease",
        "timer",
        "wave2",
        "wave3",
        "wave4",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb24_2": (
        "anti",
        "flat",
        "footdown",
        "footintensity1",
        "footintensity2",
        "footintensity3",
        "footintensitydecrease",
        "footintensityincrease",
        "footup",
        "headdown",
        "headintensity1",
        "headintensity2",
        "headintensity3",
        "headintensitydecrease",
        "headintensityincrease",
        "headup",
        "light",
        "m1",
        "m2",
        "massage-off",
        "massage-on",
        "stop",
        "time10",
        "time20",
        "time30",
        "timedecrease",
        "timeincrease",
        "timer",
        "wave2",
        "wave3",
        "wave4",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb24_4": (
        "anti",
        "flat",
        "footdown",
        "footintensity1",
        "footintensity2",
        "footintensity3",
        "footintensitydecrease",
        "footintensityincrease",
        "footup",
        "headdown",
        "headintensity1",
        "headintensity2",
        "headintensity3",
        "headintensitydecrease",
        "headintensityincrease",
        "headtiltdown",
        "headtiltup",
        "headup",
        "light",
        "lounge",
        "lumbardown",
        "lumbarup",
        "massage-off",
        "massage-on",
        "memory",
        "stop",
        "time10",
        "time20",
        "time30",
        "timedecrease",
        "timeincrease",
        "timer",
        "tv",
        "uniondown",
        "unionup",
        "wave2",
        "wave3",
        "wave4",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "cb24_5": (
        "anti",
        "flat",
        "footdown",
        "footintensity1",
        "footintensity2",
        "footintensity3",
        "footintensitydecrease",
        "footintensityincrease",
        "footup",
        "headdown",
        "headintensity1",
        "headintensity2",
        "headintensity3",
        "headintensitydecrease",
        "headintensityincrease",
        "headtiltdown",
        "headtiltup",
        "headup",
        "hpsdown",
        "hpsup",
        "light",
        "lumbardown",
        "lumbarup",
        "m1",
        "m2",
        "massage-off",
        "massage-on",
        "stop",
        "time10",
        "time20",
        "time30",
        "timedecrease",
        "timeincrease",
        "timer",
        "wave2",
        "wave3",
        "wave4",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "dacheng_2": (
        "anti",
        "flat",
        "footdown",
        "footintensity1",
        "footintensity2",
        "footintensity3",
        "footintensitydecrease",
        "footintensityincrease",
        "footup",
        "headdown",
        "headintensity1",
        "headintensity2",
        "headintensity3",
        "headintensitydecrease",
        "headintensityincrease",
        "headup",
        "light",
        "m1",
        "m2",
        "massage-off",
        "massage-on",
        "stop",
        "time10",
        "time20",
        "time30",
        "timedecrease",
        "timeincrease",
        "timer",
        "wave2",
        "wave3",
        "wave4",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
    "dacheng_5": (
        "anti",
        "flat",
        "footdown",
        "footintensity1",
        "footintensity2",
        "footintensity3",
        "footintensitydecrease",
        "footintensityincrease",
        "footup",
        "headdown",
        "headintensity1",
        "headintensity2",
        "headintensity3",
        "headintensitydecrease",
        "headintensityincrease",
        "headtiltdown",
        "headtiltup",
        "headup",
        "hpsdown",
        "hpsup",
        "light",
        "lumbardown",
        "lumbarup",
        "m1",
        "m2",
        "massage-off",
        "massage-on",
        "stop",
        "time10",
        "time20",
        "time30",
        "timedecrease",
        "timeincrease",
        "timer",
        "wave2",
        "wave3",
        "wave4",
        "wavedecrease",
        "waveincrease",
        "zg",
    ),
}

PROFILES: Final = {
    p.key: p
    for p in (
        *(_profile("BLUETOOTH", n, "P1") for n in (2, 3, 4)),
        *(_profile("CB", n, "P2") for n in (2, 3, 4)),
        _profile("CB1221", 2, "P3"),
        *(_profile("CB24", n, "P3" if n != 5 else "P4") for n in (2, 4, 5)),
        _profile("DACHENG", 2, "P3"),
        _profile("DACHENG", 5, "P4"),
    )
}
