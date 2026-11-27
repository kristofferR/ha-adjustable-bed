"""MLILY 3.1.1 (com.richmat.mlily0): explicit bed products over Richmat 6E.

The accepted subset proves these controls; other library functions are not capabilities.
Membership is ordered unique, not a positional layout.
"""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD, ExecutionCapabilities
from .casper import Action, ProductRow

SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")

@dataclass(frozen=True)
class MlilyProfile:
    key: str
    row: ProductRow
    # Preserved offsets have no inferred UI meaning.
    raw_flags: tuple[bool, bool, bool]
    cooling: bool = False
    phone_snore: bool = False
    execution: ExecutionCapabilities = STREAM_HOLD

ACTIONS: Final[tuple[Action, ...]] = (
    ('ExitLimit', 0, None),
    ('MemoryPosition2', 47, None),
    ('MemoryPosition1', 46, None),
    ('SleepPosition', 197, None),
    ('HelpGetUp', 61, None),
    ('AntiSnoring', 70, None),
    ('MotorReset', 49, None),
    ('ReadingPosition', 242, None),
    ('TVPosition', 88, None),
    ('YogaPosition', 107, None),
    ('ZeroGravity', 69, None),
    ('MemoryPosition2', 47, 44),
    ('MemoryPosition1', 46, 43),
    ('BedLight', 60, None),
    ('Massage30MinuteTimer', 97, None),
    ('Massage20MinuteTimer', 99, None),
    ('Massage10MinuteTimer', 95, None),
    ('MassageModeAllOff', 94, None),
    ('MassageModeChange', 72, None),
    ('MassageFootInstensityStrengthen', 78, None),
    ('FootDown', 39, None),
    ('FootUp', 38, None),
    ('HeadDown', 37, None),
    ('HeadUp', 36, None),
    ('SleepPosition', 197, None),
    ('ReadingPosition', 242, 243),
    ('HelpGetUp', 61, None),
    ('AntiSnoring', 70, 105),
    ('MotorReset', 49, None),
    ('TVPosition', 88, 100),
    ('YogaPosition', 107, 106),
    ('ZeroGravity', 69, 102),
    ('Massage30MinuteTimer', 97, None),
    ('Massage20MinuteTimer', 99, None),
    ('Massage10MinuteTimer', 95, None),
    ('MassageFootInstensityStrengthen', 78, None),
    ('MassageHeadInstensityStrengthen', 76, None),
    ('Stop', 110, None),
    ('MassageFootInstensityStrengthen', 78, None),
    ('MassageHeadInstensityStrengthen', 76, None),
    ('LumberDown', 64, None),
    ('LumberUp', 63, None),
    ('LoungePosition', 89, None),
    ('PillowDown', 66, None),
    ('PillowUp', 65, None),
    ('LoungePosition', 89, 101),
    ('HelpGetUp', 61, 248),
    ('MemoryPosition2', 240, None),
    ('HelpGetUp', 89, None),
    ('ReadingPosition', 48, None),
    ('YogaPosition', 47, None),
    ('MemoryPosition2', 240, 241),
    ('ReadingPosition', 48, 45),
    ('HelpGetUp', 89, None),
    ('YogaPosition', 47, 44),
    ('PillowDown', 64, None),
    ('PillowUp', 63, None),
    ('ReadingPosition', 89, 101),
    ('HelpGetUp', 48, 45),
    ('LumberDown', 66, None),
    ('LumberUp', 65, None),
)

PROFILES: Final = {
    'bedc': MlilyProfile('bedc', ('C', (23, 22, 21, 20), (38, 18, 17, 16, 15, 14), (31, 30, 29, 28, 27, 26, 52), (10, 9, 8, 49, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, False)),
    'bedHP': MlilyProfile('bedHP', ('HP', (23, 22, 21, 20, 41, 40, 44, 43), (39, 38, 17, 13, 18, 16, 15, 14), (31, 30, 29, 28, 27, 46, 25, 45), (8, 5, 9, 7, 6, 4, 10, 42, 2), (12,), False, False, False, False, True, False), (False, False, True)),
    'bedm10': MlilyProfile('bedm10', ('M10', (23, 22, 21, 20), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 52), (8, 5, 9, 49, 4, 10, 6, 2, 1), (12, 11), False, False, False, False, True, False), (False, True, False)),
    'bedM11': MlilyProfile('bedM11', ('M11', (23, 22, 21, 20), (), (31, 30, 29, 28, 27, 26, 25), (8, 5, 9, 7, 6, 4, 10, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'bedM11P': MlilyProfile('bedM11P', ('M11P', (23, 22, 21, 20, 41, 40), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 25), (10, 9, 8, 7, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'bedM11W': MlilyProfile('bedM11W', ('M11W', (23, 22, 21, 20, 41, 40), (), (31, 30, 29, 28, 27, 26, 25), (10, 9, 8, 7, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'bedM12': MlilyProfile('bedM12', ('M12', (23, 22, 21, 20), (), (31, 30, 29, 28, 27, 26, 25), (8, 5, 9, 7, 6, 4, 10, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'bedM12P': MlilyProfile('bedM12P', ('M12P', (23, 22, 21, 20, 41, 40), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 25), (10, 9, 8, 7, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'bedM12W': MlilyProfile('bedM12W', ('M12W', (23, 22, 21, 20, 41, 40), (), (31, 30, 29, 28, 27, 26, 25), (10, 9, 8, 7, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'M2Pro': MlilyProfile('M2Pro', ('M2Pro', (23, 22, 21, 20), (19, 18, 17, 16, 15, 14, 13), (31, 30, 29, 28, 27, 26, 25, 24), (10, 9, 8, 7, 6, 5, 4, 3, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, False)),
    'bedm3': MlilyProfile('bedm3', ('M3', (23, 22, 21, 20), (), (31, 54, 29, 28, 27, 58, 57), (), (12,), False, False, False, False, False, False), (False, False, False)),
    'bedm3pro': MlilyProfile('bedm3pro', ('M3Pro', (23, 22, 21, 20), (39, 18, 17, 16, 15, 14), (31, 30, 29, 28, 27, 26, 52), (), (12, 11), False, False, False, False, False, False), (False, False, False)),
    'bedm3promusic': MlilyProfile('bedm3promusic', ('M3ProMusic', (23, 22, 21, 20), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 52), (8, 5, 9, 49, 4, 10, 6, 2, 1), (12, 11), False, False, False, False, True, False), (False, True, False)),
    'bedm4': MlilyProfile('bedm4', ('M4', (23, 22, 21, 20, 41, 40), (39, 18, 17, 16, 15, 14), (31, 30, 28, 27, 26), (), (12, 11), False, False, False, False, False, False), (False, False, False)),
    'bedm5': MlilyProfile('bedm5', ('M5', (23, 22, 21, 20), (39, 38, 18, 17, 13, 16, 15, 14), (27, 31, 30, 28, 26), (), (12, 11), False, False, False, False, False, False), (False, False, False)),
    'bedM6': MlilyProfile('bedM6', ('M6', (23, 22, 21, 20), (), (31, 54, 29, 28, 27, 53, 52), (8, 5, 50, 6, 49, 48, 10, 2, 47), (12, 51), False, False, False, False, True, False), (False, False, True)),
    'bednl400': MlilyProfile('bednl400', ('NL400', (23, 22, 21, 20, 56, 55), (39, 38, 13, 18, 17, 16, 15, 14), (27, 31, 28), (5, 10, 6, 2, 1), (12, 11), False, False, False, False, False, False), (False, False, False)),
    'bedp': MlilyProfile('bedp', ('P', (23, 22, 21, 20, 60, 59), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 52), (10, 9, 8, 49, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, False)),
    'bedpowercool': MlilyProfile('bedpowercool', ('PowerCool', (23, 22, 21, 20), (36, 35, 17, 13, 34, 33, 32), (31, 27, 28), (5, 6), (12, 11), False, False, False, False, False, False), (False, False, False)),
    'beds': MlilyProfile('beds', ('S', (23, 22, 21, 20), (), (31, 54, 29, 28, 27, 58, 52), (), (12,), False, False, False, False, False, False), (False, False, False)),
    'bedsa': MlilyProfile('bedsa', ('SA', (23, 22, 21, 20), (), (31, 54, 29, 28, 27, 53, 52), (8, 5, 50, 49, 6, 48, 10, 2, 47), (12, 51), False, False, False, False, True, False), (False, False, False)),
    'bedse': MlilyProfile('bedse', ('SE', (23, 22, 21, 20), (), (31, 30, 29, 28, 27, 26, 25), (), (12,), False, False, False, False, False, False), (False, False, False)),
    'bedsl': MlilyProfile('bedsl', ('SL', (23, 22, 21, 20, 41, 40), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 25), (10, 9, 8, 7, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, True)),
    'bedsmart': MlilyProfile('bedsmart', ('Smart', (23, 22, 21, 20), (), (31, 54, 29, 28, 27, 52), (), (12,), False, False, False, False, False, False), (False, False, False)),
    'bedthreepro': MlilyProfile('bedthreepro', ('ThreePro', (23, 22, 21, 20), (13,), (31, 27, 28), (), (12,), False, False, False, False, False, False), (True, False, False)),
    'bedx3': MlilyProfile('bedx3', ('X3', (23, 22, 21, 20, 60, 59), (39, 38, 17, 18, 16, 15, 14), (31, 30, 29, 28, 27, 26, 52), (10, 9, 8, 49, 6, 5, 4, 2, 1), (12, 11), False, False, False, False, True, False), (False, False, False)),
    'bedzero': MlilyProfile('bedzero', ('Zero', (23, 22, 21, 20), (), (31, 54, 29, 28, 27, 58, 57), (), (12,), False, False, False, False, False, False), (False, False, False)),
}

VARIANTS: Final = {key: profile.row[0] for key, profile in PROFILES.items()}
