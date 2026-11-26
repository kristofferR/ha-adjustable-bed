"""Frozen P1 and P2 literals from ROOMI bed 1.0.3 (com.richmat.roomi)."""

# The control key suffixes identify the shared profile entries.
CONTROLS = {
    "HeadUp": ("24", "6e 01 00 24 93"),
    "HeadDown": ("25", "6e 01 00 25 94"),
    "FootUp": ("26", "6e 01 00 26 95"),
    "FootDown": ("27", "6e 01 00 27 96"),
    "LumberUp": ("3f", "6e 01 00 3f ae"),
    "LumberDown": ("40", "6e 01 00 40 af"),
    "PillowUp": ("41", "6e 01 00 41 b0"),
    "PillowDown": ("42", "6e 01 00 42 b1"),
    "MotorReset": ("31", "6e 01 00 31 a0"),
    "BedLight": ("3c", "6e 01 00 3c ab"),
    "MassageHeadInstensityStrengthen": ("4c", "6e 01 00 4c bb"),
    "MassageFootInstensityStrengthen": ("4e", "6e 01 00 4e bd"),
    "MassageModeChange": ("48", "6e 01 00 48 b7"),
    "MassageSwitch": ("5e", "6e 01 00 5e cd"),
    "Massage10MinuteTimer": ("5f", "6e 01 00 5f ce"),
    "Massage20MinuteTimer": ("63", "6e 01 00 63 d2"),
    "Massage30MinuteTimer": ("61", "6e 01 00 61 d0"),
    "ZeroGravity": ("45", "6e 01 00 45 b4"),
    "ReadingPosition": ("58", "6e 01 00 58 c7"),
    "RelaxPosition": ("59", "6e 01 00 59 c8"),
    "AntiSnoring": ("46", "6e 01 00 46 b5"),
    "MemoryPosition1": ("2e", "6e 01 00 2e 9d"),
    "MemoryPosition2": ("2f", "6e 01 00 2f 9e"),
}

SAVES = {
    "ZeroGravity": ("66", "6e 01 00 66 d5"),
    "ReadingPosition": ("64", "6e 01 00 64 d3"),
    "RelaxPosition": ("65", "6e 01 00 65 d4"),
    "AntiSnoring": ("69", "6e 01 00 69 d8"),
    "MemoryPosition1": ("2b", "6e 01 00 2b 9a"),
    "MemoryPosition2": ("2c", "6e 01 00 2c 9b"),
}

STOP = ("6e", "6e 01 00 6e dd")
STARTUP = (
    ("ExitLimit", "00", "6e 02 01 00 71"),
    ("CheckClock", "01", "6e 08 01 01 78"),
    ("CheckLight", "01", "6e 0a 00 01 79"),
)

# The excluded local microphone path uses the same opcode as manual recall.
AUTO_SNORE_RECALL = ("46", "6e 01 00 46 b5")
