"""MLILY Remote 1.0.1 (10103), independent of MLILY Control.

Static product gates and literals from the accepted Dart 3.7.0 artifact.
No advertisement or shared response parser identifies a product.
"""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD, ExecutionCapabilities
from .casper import Action, ProductRow

TRANSPORTS: Final = ("n1", "w1", "w2", "w3", "w4", "w5")
SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
TICK_S: Final = 0.1
SAVE_MS: Final = 3000
STARTUP: Final = (("deviceFunctionItemExitLimit", 0), ("deviceFunctionItemCheckClock", 1))

ACTIONS: Final[tuple[Action, ...]] = (
    ("HeadUp", 0x24, None),
    ("HeadDown", 0x25, None),
    ("FootUp", 0x26, None),
    ("FootDown", 0x27, None),
    ("HeadAndFootUp", 0x29, None),
    ("HeadAndFootDown", 0x2A, None),
    ("LumberUp", 0x3F, None),
    ("LumberDown", 0x40, None),
    ("PillowUp", 0x41, None),
    ("PillowDown", 0x42, None),
    ("MemoryPosition1", 0x2E, 0x2B),
    ("MemoryPosition2", 0x2F, 0x2C),
    ("MemoryPosition3", 0x30, 0x2D),
    ("BedLight", 0x3C, None),
    ("MotorReset", 0x31, None),
    ("MassageHeadInstensityStrengthen", 0x4C, None),
    ("MassageFootInstensityStrengthen", 0x4E, None),
    ("MassageLumbarInstensityStrengthen", 0xE0, None),
    ("MassageModeChange", 0x48, None),
    ("MassageModeAllOff", 0x5E, None),
    ("Massage10MinuteTimer", 0x5F, None),
    ("Massage20MinuteTimer", 0x63, None),
    ("Massage30MinuteTimer", 0x61, None),
    ("ZeroGravity", 0x45, 0x66),
    ("AntiSnoring", 0x46, 0x69),
    ("TVPosition", 0x58, 0x64),
    ("LoungePosition", 0x59, 0x65),
)


@dataclass(frozen=True)
class MlilyRemoteProfile:
    key: str
    code: str
    row: ProductRow
    cooling: bool = False
    phone_snore: bool = False
    execution: ExecutionCapabilities = STREAM_HOLD


PROFILES: Final = {
    "ms200": MlilyRemoteProfile(
        "ms200",
        "EGRM",
        (
            "MS200",
            (0, 1, 2, 3, 14),
            (),
            (23, 26, 24, 10, 11),
            (),
            (),
            False,
            False,
            False,
            False,
            False,
            True,
        ),
        cooling=False,
        phone_snore=False,
    ),
    "ms300": MlilyRemoteProfile(
        "ms300",
        "JBRM",
        (
            "MS300",
            (0, 1, 2, 3, 4, 5, 13, 14),
            (15, 16, 18, 19, 20, 21, 22),
            (24, 23, 10, 11),
            (),
            (),
            False,
            False,
            False,
            False,
            False,
            True,
        ),
        cooling=False,
        phone_snore=False,
    ),
    "ms300_sh": MlilyRemoteProfile(
        "ms300_sh",
        "DYRN",
        (
            "MS300-SH",
            (0, 1, 2, 3, 4, 5, 13, 14),
            (15, 16, 18, 19, 20, 21, 22),
            (23, 24, 10, 11),
            (),
            (),
            False,
            False,
            False,
            False,
            False,
            True,
        ),
        cooling=False,
        phone_snore=True,
    ),
    "powercool": MlilyRemoteProfile(
        "powercool",
        "D9RM",
        (
            "PowerCool",
            (0, 1, 2, 3, 14, 13),
            (15, 16, 18, 19, 20, 21, 22),
            (23, 24, 10, 11),
            (),
            (),
            False,
            False,
            False,
            False,
            False,
            True,
        ),
        cooling=True,
        phone_snore=False,
    ),
    "ms600": MlilyRemoteProfile(
        "ms600",
        "ANRN",
        (
            "MS600",
            (0, 1, 2, 3, 6, 7, 8, 9, 14, 13),
            (15, 17, 16, 18, 19, 20, 21, 22),
            (23, 24, 25, 10, 11, 12),
            (23, 24, 25, 10, 11, 12),
            (),
            False,
            False,
            False,
            False,
            False,
            True,
        ),
        cooling=False,
        phone_snore=False,
    ),
}
VARIANTS: Final = {key: PROFILES[key].row[0] for key in ("ms200", "ms300", "ms600", "powercool", "ms300_sh")}
