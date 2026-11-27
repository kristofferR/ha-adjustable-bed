"""AW MOTION 1.0.1: the three products offered by its brand picker."""

from typing import Final

from .dreamsense import Action, DreamSenseProfile


class AwMotionProfile(DreamSenseProfile):
    @property
    def key(self) -> str:
        return "awmotion_" + self.product


SCAN_WORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
PROFILES: Final = {
    "HC800": AwMotionProfile(
        product="HC800",
        remote="LTRM",
        normal=True,
        controls=(
            Action("HeadUp", 0x24, None, True, True, 0),
            Action("HeadDown", 0x25, None, True, True, 0),
            Action("FootUp", 0x26, None, True, True, 0),
            Action("FootDown", 0x27, None, True, True, 0),
            Action("LumberUp", 0x3F, None, True, True, 0),
            Action("LumberDown", 0x40, None, True, True, 0),
            Action("LightBoard", 0x50, None, False, True, 0),
            Action("BedLight", 0x3C, None, False, True, 0),
            Action("MotorReset", 0x31, None, False, True, 0),
            Action("MassageHeadInstensityStrengthen", 0x4C, None, False, True, 0),
            Action("MassageFootInstensityStrengthen", 0x4E, None, False, True, 0),
            Action("MassageModeChange", 0x48, None, False, True, 0),
            Action("MassageModeAllOff", 0x5E, None, False, True, 0),
            Action("Massage10MinuteTimer", 0x5F, None, False, True, 0),
            Action("Massage20MinuteTimer", 0x63, None, False, True, 0),
            Action("Massage30MinuteTimer", 0x61, None, False, True, 0),
            Action("AntiSnoring", 0x46, 0x69, False, False, 3000),
            Action("ZeroGravity", 0x45, 0x66, False, False, 3000),
            Action("MemoryPosition1", 0x2E, 0x2B, False, False, 3000),
        ),
        alarm={"AntiSnoring": 70, "ZeroGravity": 69, "MemoryPosition1": 46},
        clock=True,
        repeat=False,
        light=True,
        vibration=False,
        side=False,
        split=False,
    ),
    "SN500": AwMotionProfile(
        product="SN500",
        remote="LTRM",
        normal=True,
        controls=(
            Action("HeadUp", 0x24, None, True, True, 0),
            Action("HeadDown", 0x25, None, True, True, 0),
            Action("FootUp", 0x26, None, True, True, 0),
            Action("FootDown", 0x27, None, True, True, 0),
            Action("LumberUp", 0x3F, None, True, True, 0),
            Action("LumberDown", 0x40, None, True, True, 0),
            Action("PillowUp", 0x41, None, True, True, 0),
            Action("PillowDown", 0x42, None, True, True, 0),
            Action("LightBoard", 0x50, None, False, True, 0),
            Action("BedLight", 0x3C, None, False, True, 0),
            Action("MotorReset", 0x31, None, False, True, 0),
            Action("MassageHeadInstensityStrengthen", 0x4C, None, False, True, 0),
            Action("MassageFootInstensityStrengthen", 0x4E, None, False, True, 0),
            Action("MassageModeChange", 0x48, None, False, True, 0),
            Action("MassageModeAllOff", 0x5E, None, False, True, 0),
            Action("Massage10MinuteTimer", 0x5F, None, False, True, 0),
            Action("Massage20MinuteTimer", 0x63, None, False, True, 0),
            Action("Massage30MinuteTimer", 0x61, None, False, True, 0),
            Action("AntiSnoring", 0x46, 0x69, False, False, 3000),
            Action("ZeroGravity", 0x45, 0x66, False, False, 3000),
        ),
        alarm={"AntiSnoring": 70, "ZeroGravity": 69},
        clock=True,
        repeat=False,
        light=True,
        vibration=False,
        side=False,
        split=False,
    ),
    "SN300": AwMotionProfile(
        product="SN300",
        remote="B3RN",
        normal=True,
        controls=(
            Action("HeadUp", 0x24, None, True, True, 0),
            Action("HeadDown", 0x25, None, True, True, 0),
            Action("FootUp", 0x26, None, True, True, 0),
            Action("FootDown", 0x27, None, True, True, 0),
            Action("HeadAndFootUp", 0x29, None, True, True, 0),
            Action("HeadAndFootDown", 0x2A, None, True, True, 0),
            Action("LightBoard", 0x50, None, False, True, 0),
            Action("BedLight", 0x3C, None, False, True, 0),
            Action("MotorReset", 0x31, None, False, True, 0),
            Action("MassageHeadInstensityStrengthen", 0x4C, None, False, True, 0),
            Action("MassageFootInstensityStrengthen", 0x4E, None, False, True, 0),
            Action("MassageModeChange", 0x48, None, False, True, 0),
            Action("MassageModeAllOff", 0x5E, None, False, True, 0),
            Action("Massage10MinuteTimer", 0x5F, None, False, True, 0),
            Action("Massage20MinuteTimer", 0x63, None, False, True, 0),
            Action("Massage30MinuteTimer", 0x61, None, False, True, 0),
            Action("ZeroGravity", 0x45, 0x66, False, False, 3000),
            Action("AntiSnoring", 0x46, 0x69, False, False, 3000),
            Action("TVPosition", 0x58, 0x64, False, False, 3000),
            Action("MemoryPosition1", 0x2E, 0x2B, False, False, 3000),
        ),
        alarm={"ZeroGravity": 69, "AntiSnoring": 70, "TVPosition": 88, "MemoryPosition1": 46},
        clock=True,
        repeat=False,
        light=True,
        vibration=False,
        side=False,
        split=False,
    ),
}
CHOICES: Final = {
    "SN300": "SilentNight SN300",
    "SN500": "SilentNight SN500",
    "HC800": "HighClare HC800",
}
