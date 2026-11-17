"""CheersSleep v2.7.0/code40: all 36 accepted catalog keys remain distinct."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..codec import cheerssleep as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class CheersSleepProfile:
    key: codec.Format
    execution: ExecutionCapabilities
    refresh_ms: int = 100
    release_ms: int = 0

    @property
    def frames(self) -> dict[str, bytes]:
        if self.key == "p1":
            return {"head_up": codec.p1(2, 1, 257), "stop": codec.p1(3, 1, 256)}
        return {"head_up": codec.normal(1), "stop": codec.normal(0), "query": codec.query()}


PROFILES: Final = {
    "p1": CheersSleepProfile("p1", ExecutionCapabilities(hold="latched"), release_ms=120),
    "p2": CheersSleepProfile("p2", STREAM_HOLD),
}


@dataclass(frozen=True, slots=True)
class Model:
    key: int
    label: str
    page: str
    format: codec.Format
    axes: tuple[str, ...]
    memory: int = 0
    presets: bool = False
    light: bool = False
    massage: bool = False
    split: bool = False
    sonic: bool = False
    as_layout: bool = False
    rgb: bool = False
    combined: bool = True

    @property
    def shared(self) -> bool:
        return self.sonic or self.as_layout


MODELS: Final[dict[int, Model]] = {
    14: Model(14, "BS200C/BS200P", "StorageActivity", "p1", ("all",)),
    16: Model(16, "BS200C/BS200P", "StorageActivity", "p1", ("all",)),
    45: Model(45, "CS-B200", "TwoActivity", "p1", ("back", "legs")),
    46: Model(
        46, "CS-B200A", "SixActivity", "p1", ("back", "legs"), memory=2, presets=True, light=True
    ),
    47: Model(
        47, "CS-B200M", "ThreeActivity", "p1", ("back", "legs"), memory=2, light=True, massage=True
    ),
    48: Model(48, "CS-B300", "OneActivity", "p1", ("back", "legs", "lumbar")),
    49: Model(
        49,
        "CS-B300A",
        "FiveActivity",
        "p1",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
    ),
    50: Model(
        50,
        "CS-B300M",
        "FourActivity",
        "p1",
        ("back", "legs", "lumbar"),
        memory=2,
        light=True,
        massage=True,
    ),
    51: Model(
        51,
        "CS-B500YA",
        "EightActivity",
        "p1",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
        split=True,
    ),
    52: Model(
        52,
        "CS-B500YM",
        "NineActivity",
        "p1",
        ("back", "legs", "lumbar"),
        memory=2,
        light=True,
        massage=True,
        split=True,
    ),
    53: Model(53, "BA210", "TwoActivity1", "p1", ("back", "legs")),
    54: Model(
        54,
        "CS-B300M",
        "FourActivity",
        "p1",
        ("back", "legs", "lumbar"),
        memory=2,
        light=True,
        massage=True,
    ),
    55: Model(
        55, "CS-B200M", "ThreeActivity", "p1", ("back", "legs"), memory=2, light=True, massage=True
    ),
    57: Model(
        57,
        "BS300YA",
        "Bs300yaActivity",
        "p1",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
    ),
    134: Model(134, "CS-B200", "NewTwoActivity", "p2", ("back", "legs")),
    135: Model(
        135,
        "CS-B200A",
        "NewSixActivity",
        "p2",
        ("back", "legs"),
        memory=2,
        presets=True,
        light=True,
    ),
    136: Model(
        136,
        "CS-B200M",
        "NewThreeActivity",
        "p2",
        ("back", "legs"),
        memory=2,
        light=True,
        massage=True,
    ),
    137: Model(137, "CS-B300", "NewOneActivity", "p2", ("back", "legs", "lumbar")),
    138: Model(
        138,
        "CS-B300A",
        "NewFiveActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
    ),
    139: Model(
        139,
        "CS-B300M",
        "NewFourActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        light=True,
        massage=True,
    ),
    140: Model(
        140,
        "CS-B500YA",
        "NewEightActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
        split=True,
    ),
    141: Model(
        141,
        "CS-B500YM",
        "NewNineActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        light=True,
        massage=True,
        split=True,
    ),
    142: Model(142, "BA210", "NewTwoActivity1", "p2", ("back", "legs")),
    145: Model(
        145,
        "CS-B200I",
        "NewMusicBed200IActivity",
        "p2",
        ("back", "legs"),
        memory=2,
        presets=True,
        light=True,
        sonic=True,
        rgb=True,
    ),
    153: Model(
        153,
        "CS-B200AS",
        "NewMusicBedActivity",
        "p2",
        ("back", "legs"),
        memory=2,
        presets=True,
        light=True,
        as_layout=True,
        rgb=True,
    ),
    154: Model(
        154,
        "CS-B300AS",
        "NewMusicBed300ASActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
        as_layout=True,
        rgb=True,
    ),
    169: Model(
        169,
        "CS-B200MS",
        "NewMusicBedActivity",
        "p2",
        ("back", "legs"),
        memory=2,
        presets=True,
        light=True,
        as_layout=True,
        rgb=True,
    ),
    170: Model(
        170,
        "CS-B300I",
        "NewMusicBed300IActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
        sonic=True,
        rgb=True,
    ),
    171: Model(
        171,
        "CS-B400I",
        "NewMusicBed400IActivity",
        "p2",
        ("back", "legs", "lumbar", "head"),
        memory=2,
        presets=True,
        light=True,
        sonic=True,
        rgb=True,
        combined=False,
    ),
    172: Model(
        172,
        "CS-B500YI",
        "NewMusicBed500IActivity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        presets=True,
        light=True,
        split=True,
        sonic=True,
        rgb=True,
    ),
    173: Model(
        173,
        "CS-B500XL",
        "NewMusicBed500xlActivity",
        "p2",
        ("back", "legs", "lumbar", "lift_head", "lift_foot", "lift"),
        memory=2,
        presets=True,
        light=True,
        sonic=True,
        rgb=True,
    ),
    174: Model(
        174,
        "CS-B600I",
        "NewMusicBed600IActivity",
        "p2",
        ("back", "legs", "lumbar", "head", "lift_head", "lift_foot", "lift"),
        memory=2,
        presets=True,
        light=True,
        sonic=True,
        rgb=True,
        combined=False,
    ),
    175: Model(175, "CS-BX200", "NewBx200Activity", "p2", ("back", "legs")),
    176: Model(
        176,
        "CB-B200M2",
        "B200m2Activity",
        "p2",
        ("back", "legs"),
        memory=2,
        light=True,
        massage=True,
    ),
    177: Model(
        177,
        "CB-B300M2",
        "B300m2Activity",
        "p2",
        ("back", "legs", "lumbar"),
        memory=2,
        light=True,
        massage=True,
    ),
    179: Model(
        179,
        "BS20HI",
        "BS20HIActivity",
        "p2",
        ("back", "legs"),
        memory=2,
        presets=True,
        light=True,
        sonic=True,
    ),
}


def advertisement(manufacturer: Mapping[int, bytes]) -> tuple[Model, bool] | None:
    if not manufacturer:
        return None
    first = min(manufacturer)  # Android SparseArray keyAt(0), not insertion order.
    new = first == 89
    if new:
        payload = manufacturer[first]
        if len(payload) < 3:
            return None
        key = 89 + codec.signed(payload[2])
    else:
        key = first
    return (MODELS[key], new) if key in MODELS else None


# (up, down, release). The split foot is intentionally shared.
P1_AXES: Final = {
    "all": (0x110, 0x111, 1),
    "back": (0x101, 0x102, 0x100),
    "legs": (0x105, 0x106, 0x104),
    "lumbar": (0x109, 0x10A, 0x108),
}
P1_SPLIT: Final = {
    1: {
        "all": (0x6444, 0x6445, 0x6443),
        "back": (0x6401, 0x6402, 0x6400),
        "lumbar": (0x6407, 0x6408, 0x6406),
        "legs": (0x640D, 0x640E, 0x640C),
    },
    2: {
        "all": (0x6456, 0x6457, 0x6455),
        "back": (0x6404, 0x6405, 0x6403),
        "lumbar": (0x640A, 0x640B, 0x6409),
        "legs": (0x640D, 0x640E, 0x640C),
    },
}
P2_AXES: Final = {
    "back": (1, 2),
    "legs": (4, 8),
    "lumbar": (16, 32),
    "lift_head": (64, 128),
    "lift_foot": (256, 512),
    "lift": (320, 640),
}
PRESETS: Final = {"anti_snore": (0x301, 0x8000), "tv": (0x302, 0x4000), "zero_g": (0x303, 0x1000)}
SONIC: Final = {
    "sonic_back": 0x303,
    "sonic_foot": 0xC03,
    "sonic_toggle": 0x3C,
    "sonic_mode_1": 0xCC,
    "sonic_mode_2": 0x30C,
    "sonic_switch": 0xC0C,
}
AXIS_LABELS: Final = {
    "back": "back",
    "legs": "legs",
    "lumbar": "lumbar",
    "head": "head",
    "all": "cheerssleep_all",
    "lift_head": "cheerssleep_lift_head",
    "lift_foot": "cheerssleep_lift_foot",
    "lift": "cheerssleep_lift",
}

# Level0 is off. Wave intensities have no zero member and retain the right-head typo.
P1_STEADY: Final = {
    0: {"head": (0x123, 0x201, 0x202, 0x203), "foot": (0x124, 0x204, 0x205, 0x206)},
    1: {"head": (0x123, 0x201, 0x202, 0x203), "foot": (0x124, 0x204, 0x205, 0x206)},
    2: {"head": (0x133, 0x207, 0x208, 0x209), "foot": (0x134, 0x20A, 0x20B, 0x20C)},
}
P1_WAVE: Final = {
    0: {"head": (0x220, 0x221, 0x222), "foot": (0x228, 0x229, 0x22A)},
    1: {"head": (0x220, 0x221, 0x222), "foot": (0x228, 0x229, 0x22A)},
    2: {"head": (0x240, 0x2401, 0x242), "foot": (0x248, 0x249, 0x24A)},
}
P1_WAVE_MODE: Final = {0: (0x200, 0x230, 0x231), 1: (0x233, 0x230, 0x231), 2: (0x253, 0x250, 0x251)}
P2_MASSAGE: Final = {"head": 0x200000, "foot": 0x400000, "mode": 0x10000000}
P1_SETTINGS: Final = {"delay": 0x1101, "out_of_bed_setting": 0x1102, "snore_setting": 0x1103}
RGB_PREVIEW_MS: Final = {"rgb_preview": 200, "rgb2_preview": 150}
RGB_SAVE_MS: Final = 500
MAC_QUERY_ATTEMPTS: Final = 20
MAC_QUERY_INTERVAL_MS: Final = 120
YB_SPEEDS: Final = (0x201, 0x202, 0x203)
YB_TIMERS: Final = (300, 900)
