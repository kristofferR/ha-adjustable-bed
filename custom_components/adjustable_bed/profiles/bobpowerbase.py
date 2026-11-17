"""Power Bob Base 1.0.9's four explicit products over the proven Richmat codec."""

from typing import Final

from .richmat import RichmatProfile
from .richmat_app import Action, Product
from .richmat_catalog import BedRuntime, Catalog

PROFILE_CHOICES: Final = {
    "elite": "Power Bob Elite",
    "elite_sh": "Power Bob Elite SH",
    "ultra": "Power Bob Ultra",
    "ultra_sh": "Power Bob Ultra SH",
}
LAYOUTS: Final = {
    "standard": "Standard",
    "split_head": "Split head",
    "split": "Split",
}
SCAN_KEYWORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
WIRE: Final = RichmatProfile(
    key="bobpowerbase", transports=("n1", "w1", "w2", "w3", "w4", "w5")
)


def _action(name: str, code: int, gesture: str = "shortPress", save: int = 0) -> Action:
    return Action("deviceFunctionItem" + name, gesture, False, False, False, False, code, save, code)


ACTIONS: Final = {
    "head_up": _action("HeadUp", 0x24, "sustainPress"),
    "head_down": _action("HeadDown", 0x25, "sustainPress"),
    "foot_up": _action("FootUp", 0x26, "sustainPress"),
    "foot_down": _action("FootDown", 0x27, "sustainPress"),
    "head_foot_up": _action("HeadAndFootUp", 0x29, "sustainPress"),
    "head_foot_down": _action("HeadAndFootDown", 0x2A, "sustainPress"),
    "lumbar_up": _action("LumberUp", 0x3F, "sustainPress"),
    "lumbar_down": _action("LumberDown", 0x40, "sustainPress"),
    "pillow_up": _action("PillowUp", 0x41, "sustainPress"),
    "pillow_down": _action("PillowDown", 0x42, "sustainPress"),
    "reset": _action("MotorReset", 0x31),
    "light": _action("BedLight", 0x3C),
    "massage_head": _action("MassageHeadInstensityStrengthen", 0x4C),
    "massage_foot": _action("MassageFootInstensityStrengthen", 0x4E),
    "massage_mode": _action("MassageModeChange", 0x48),
    "massage_off": _action("MassageModeAllOff", 0x5E),
    "massage_10": _action("Massage10MinuteTimer", 0x5F),
    "massage_20": _action("Massage20MinuteTimer", 0x63),
    "massage_30": _action("Massage30MinuteTimer", 0x61),
    "anti_snore": _action("AntiSnoring", 0x46, "shortAndLongPress", 0x69),
    "zero_gravity": _action("ZeroGravity", 0x45, "shortAndLongPress", 0x66),
    "tv": _action("TVPosition", 0x58, "shortAndLongPress", 0x64),
    "memory_1": _action("MemoryPosition1", 0x2E, "shortAndLongPress", 0x2B),
    "memory_2": _action("MemoryPosition2", 0x2F, "shortAndLongPress", 0x2C),
}
PRESETS: Final = ("anti_snore", "zero_gravity", "tv", "memory_1", "memory_2")
_MOTORS: Final = ("head_up", "head_down", "foot_up", "foot_down")
_ULTRA: Final = (
    "head_foot_up", "head_foot_down", "lumbar_up", "lumbar_down", "pillow_up", "pillow_down",
)
_MASSAGE: Final = (
    "massage_head", "massage_foot", "massage_mode", "massage_off", "massage_10", "massage_20", "massage_30",
)
PRODUCTS: Final = {
    key: Product(
        label,
        (*_MOTORS, *_ULTRA, "reset", *_MASSAGE, *PRESETS)
        if key.startswith("ultra") else (*_MOTORS, "reset", "light", *PRESETS),
        PRESETS, (0, 1) if key.endswith("_sh") else (0,),
        True, "normal", True, "deviceSleepMonitoringNone", False,
    )
    for key, label in PROFILE_CHOICES.items()
}
CATALOG: Final = Catalog(
    "bobpowerbase", "Power Bob Base", WIRE, ACTIONS, PRODUCTS, {},
    bed=BedRuntime(100, 3000, 200, 0.5, tuple(range(16))),
)
