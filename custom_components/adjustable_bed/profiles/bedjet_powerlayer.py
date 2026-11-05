"""The BedJet PowerLayer frame as a profile over ``codec/bedjet_powerlayer.py``.

The keys are ported from the MIT-licensed ``powerlayer`` branch of
https://github.com/natekspencer/ha-bedjet (``pybedjet/powerlayer.py`` and
``const.py``). The calibration tables come from a PowerLayer owner reading the
BedJet LCD remote's own degree display against the reported counts in
https://github.com/natekspencer/ha-bedjet/issues/49, so they carry roughly one
degree of unit-to-unit tolerance.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..codec import bedjet_powerlayer as codec
from ..const import BEDJET_POWERLAYER_FOOT_MAX_ANGLE, BEDJET_POWERLAYER_HEAD_MAX_ANGLE
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

# Raw actuator count -> degrees shown on the BedJet LCD remote. Interpolated
# between points and clamped outside them. The head table starts above zero
# because the captured frame rested at a nonzero count when flat.
# fmt: off
HEAD_ANGLE_TABLE: Final[tuple[tuple[int, float], ...]] = (
    (32, 0), (119, 1), (154, 2), (185, 3), (270, 4), (336, 5),
    (419, 6), (454, 7), (495, 8), (583, 9), (666, 10), (695, 11),
    (783, 12), (851, 13), (950, 14), (989, 15), (1087, 16), (1116, 17),
    (1150, 18), (1178, 19), (1204, 20), (1248, 21), (1274, 22), (1309, 23),
    (1335, 24), (1361, 25), (1410, 26), (1447, 27), (1480, 28), (1507, 29),
    (1542, 30), (1596, 31), (1633, 32), (1660, 33), (1697, 34), (1725, 35),
    (1762, 36), (1825, 37), (1869, 38), (1896, 39), (1923, 40), (1973, 41),
    (2040, 42), (2050, 43), (2117, 44), (2145, 45), (2207, 46), (2232, 47),
    (2307, 48), (2343, 49), (2370, 50), (2426, 51), (2463, 52), (2526, 53),
    (2563, 54), (2599, 55), (2635, 56), (2690, 57), (2728, 58), (2783, 59),
    (2820, 60), (2883, 61), (2919, 62), (2971, 63), (3026, 64), (3055, 65),
    (3115, 66), (3151, 67), (3196, 68), (3223, 69), (3259, 70), (3312, 71),
    (3347, 72), (3390, 73),
)

FOOT_ANGLE_TABLE: Final[tuple[tuple[int, float], ...]] = (
    (0, 0), (34, 1), (66, 2), (85, 3), (103, 4), (125, 5),
    (163, 6), (189, 7), (216, 8), (242, 9), (269, 10), (306, 11),
    (346, 12), (374, 13), (403, 14), (439, 15), (468, 16), (525, 17),
    (568, 18), (606, 19), (639, 20), (644, 21), (719, 22), (785, 23),
    (823, 24), (862, 25), (923, 26), (982, 27), (1028, 28), (1068, 29),
    (1097, 30), (1163, 31), (1201, 32), (1238, 33), (1276, 34), (1323, 35),
    (1364, 36), (1404, 37), (1461, 38), (1489, 39), (1549, 40), (1561, 41),
    (1600, 42), (1627, 43), (1664, 44), (1692, 45), (1708, 46), (1741, 47),
)
# fmt: on


def raw_count_to_angle(raw: int, table: tuple[tuple[int, float], ...]) -> float:
    """Convert a raw actuator count to degrees using a calibration table."""
    if raw <= table[0][0]:
        return table[0][1]
    if raw >= table[-1][0]:
        return table[-1][1]
    for (low_raw, low_deg), (high_raw, high_deg) in zip(table, table[1:], strict=False):
        if low_raw <= raw <= high_raw:
            span = high_raw - low_raw
            if span == 0:
                return high_deg
            return round(low_deg + (raw - low_raw) * (high_deg - low_deg) / span, 1)
    return table[-1][1]


@dataclass(frozen=True)
class PowerLayerProfile:
    """The remote keys, calibration and travel limits of one frame."""

    key: str
    # Movement keys run for about 1.3 s, then the frame halts by itself.
    movement: Mapping[str, int]
    # Presets and memory recalls drive to the stored position on one write.
    presets: Mapping[str, int]
    memory: Mapping[int, int]
    head_angles: tuple[tuple[int, float], ...]
    foot_angles: tuple[tuple[int, float], ...]
    head_max_angle: float
    foot_max_angle: float
    # No accepted app report proves a hold (docs/design/execution-capabilities.md).
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES

    @property
    def frames(self) -> dict[str, bytes]:
        """Every command frame the profile sends, by control."""
        return {
            **{name: codec.command(key) for name, key in self.movement.items()},
            **{name: codec.command(key) for name, key in self.presets.items()},
            **{f"memory_{slot}": codec.command(key) for slot, key in self.memory.items()},
        }


POWERLAYER: Final = PowerLayerProfile(
    key="powerlayer",
    movement={"head_up": 0x02, "head_down": 0x03, "foot_up": 0x04, "foot_down": 0x05},
    presets={"flat": 0x10, "anti_snore": 0x11, "zero_g": 0x12, "tv": 0x13},
    memory={1: 0x20, 2: 0x21, 3: 0x22},
    head_angles=HEAD_ANGLE_TABLE,
    foot_angles=FOOT_ANGLE_TABLE,
    head_max_angle=BEDJET_POWERLAYER_HEAD_MAX_ANGLE,
    foot_max_angle=BEDJET_POWERLAYER_FOOT_MAX_ANGLE,
)
PROFILES: Final[dict[str, PowerLayerProfile]] = {POWERLAYER.key: POWERLAYER}
