"""Luuna + 2.0.1's three explicit products, accepted APK audit unit146."""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD, ExecutionCapabilities
from .casper import Action, ProductRow

ACTIONS: Final[tuple[Action, ...]] = (
    ("HeadUp", 0x24, None),
    ("HeadDown", 0x25, None),
    ("FootUp", 0x26, None),
    ("FootDown", 0x27, None),
    ("PillowUp", 0x41, None),
    ("PillowDown", 0x42, None),
    ("LumberUp", 0x3F, None),
    ("LumberDown", 0x40, None),
    ("MotorReset", 0x31, None),
    ("MassageHeadInstensityStrengthen", 0x4C, None),
    ("MassageFootInstensityStrengthen", 0x4E, None),
    ("MassageModeChange", 0x48, None),
    ("MassageModeAllOff", 0x5E, None),
    ("Massage10MinuteTimer", 0x5F, None),
    ("Massage20MinuteTimer", 0x63, None),
    ("Massage30MinuteTimer", 0x61, None),
    ("AntiSnoring", 0x46, 0x69),
    ("ZeroGravity", 0x45, 0x66),
    ("TVPosition", 0x58, 0x64),
    ("MemoryPosition1", 0x2E, 0x2B),
    ("MemoryPosition2", 0x2F, 0x2C),
)
TRANSPORTS: Final = ("n1", "w5", "w4", "w3", "w2", "w1")
SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
QUERIES: Final = (("deviceFunctionItemCheckClock", 1), ("deviceFunctionItemCheckLight", 1))
TICK_S: Final = 0.1
QUERY_INTERVAL_S: Final = 0.3
LIGHT_DURATIONS: Final = (0, 300, 600, 900)
LIGHT_COLORS: Final = {"warm": (255, 140, 20), "cold": (255, 255, 255)}


@dataclass(frozen=True)
class LuunaProfile:
    """Catalog groups and gates; names never infer a product."""

    key: str
    code: str
    row: ProductRow
    execution: ExecutionCapabilities = STREAM_HOLD


_TWO = (0, 1, 2, 3, 8)
_FOUR = tuple(range(9))
_MASSAGE = tuple(range(9, 16))
PROFILES: Final = {
    "rise": LuunaProfile(
        "rise",
        "V1RM",
        ("Rise", _TWO, (), (16, 17, 19), (16, 17, 19), (), False, False, False, True, False, False),
    ),
    "risepro": LuunaProfile(
        "risepro",
        "JVRM",
        (
            "Rise Pro",
            _FOUR,
            _MASSAGE,
            (16, 17, 18, 19, 20),
            (16, 17, 18, 19, 20),
            (),
            False,
            False,
            False,
            False,
            False,
            False,
        ),
    ),
    "riseprolight": LuunaProfile(
        "riseprolight",
        "FDRN",
        (
            "Rise Pro Light",
            _FOUR,
            _MASSAGE,
            (16, 17, 18, 19),
            (16, 17, 18, 19),
            (),
            True,
            False,
            False,
            True,
            False,
            False,
        ),
    ),
}
VARIANTS: Final = {key: p.row[0] for key, p in PROFILES.items()}
