"""Static accepted CheersSleep models and manufacturer discovery facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ...codec import cheerssleep as codec


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
