"""Flexx Motion 2.0.1 (20100) product-owned direct BLE profiles.

The original preset subsets remain useful reference data. The complete profiles
below distinguish the current picker from other products restored by the app.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from ..codec.richmat import TransportKey
from ..execution import ExecutionCapabilities
from .dreamsense import Action, DreamSenseProfile

PresetKey = Literal[
    "memory_1", "memory_2", "zero_g", "anti_snore", "tv", "lounge", "soothing_sleep"
]


@dataclass(frozen=True)
class Preset:
    """One app preset descriptor; missing save means no save control exists."""

    key: PresetKey
    label: str
    recall: int
    save: int | None


@dataclass(frozen=True)
class PresetSubset:
    """Only the verified preset list of one product, with no capability defaults."""

    product: str
    presets: tuple[Preset, ...]


MEMORY_1: Final = Preset("memory_1", "Memory 1", 0x2E, 0x2B)
MEMORY_2: Final = Preset("memory_2", "Memory 2", 0x2F, 0x2C)
ZERO_G: Final = Preset("zero_g", "Zero gravity", 0x45, 0x66)
ANTI_SNORE: Final = Preset("anti_snore", "Anti-snore", 0x46, 0x69)
TV: Final = Preset("tv", "TV", 0x58, 0x64)
LOUNGE: Final = Preset("lounge", "Lounge", 0x59, 0x65)
SOOTHING_SLEEP: Final = Preset("soothing_sleep", "Soothing sleep", 0x86, None)
PRESETS: Final = (MEMORY_1, MEMORY_2, ZERO_G, ANTI_SNORE, TV, LOUNGE, SOOTHING_SLEEP)

SUBSETS: Final = (
    PresetSubset("productFlexxPB450SH", (MEMORY_1, ZERO_G, ANTI_SNORE)),
    PresetSubset("productFlexxAFEG300SH", (MEMORY_1, ZERO_G, TV, LOUNGE, SOOTHING_SLEEP)),
    PresetSubset("productFlexxAFEG300", (MEMORY_1, ZERO_G, TV, LOUNGE, SOOTHING_SLEEP)),
    PresetSubset("productFlexxPB450", (MEMORY_1, ZERO_G, ANTI_SNORE)),
    PresetSubset("productFlexxPB325", (MEMORY_1, ZERO_G, ANTI_SNORE, TV)),
    PresetSubset("productFlexxPB300", (MEMORY_1, MEMORY_2, ZERO_G, TV, LOUNGE)),
    PresetSubset("productFlexxPB250", (MEMORY_1,)),
)

# Endpoint values; live role and property admission belongs to transport.select.
CATALOG_TRANSPORTS: Final[tuple[TransportKey, ...]] = ("n1", "w1", "w2", "w3", "w4", "w5")
PRESET_WRITES: Final = 1
PRESET_RELEASE: Final = False
# The transport's scheduling cycle is not a minimum inter-write interval.
QUEUE_CYCLE_MS: Final = 100
RECEIVE_EXPIRY_S: Final = 0.5

SCAN_WORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
HOLD_MS: Final = 100
QUERY_MS: Final = 300
LIGHT_DELAY_MS: Final = 200
IO_TIMEOUT_S: Final = 15.0
LIGHT_CLOSE_OPCODE: Final = 0x75
BOX_SPLIT: Final = 0
BOX_STANDARD: Final = 2
PALETTE: Final = {
    "yellow": (255, 255, 0),
    "green": (0, 255, 0),
    "sky_blue": (0, 127, 255),
    "blue": (0, 0, 255),
    "violet": (139, 0, 255),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
}
LABELS: Final = {
    "HeadUp": "Head up",
    "HeadDown": "Head down",
    "FootUp": "Feet up",
    "FootDown": "Feet down",
    "HeadAndFootUp": "Head and feet up",
    "HeadAndFootDown": "Head and feet down",
    "LumberUp": "Lumbar up",
    "LumberDown": "Lumbar down",
    "PillowUp": "Pillow up",
    "PillowDown": "Pillow down",
    "FootBoxUp": "Storage lift up",
    "FootBoxDown": "Storage lift down",
    "MotorReset": "Flat",
    "BedLight": "Bed light",
    "BedLightClose": "Bed light off",
    "LightBoard": "Light panel",
    "MassageHeadInstensityStrengthen": "Increase head massage",
    "MassageFootInstensityStrengthen": "Increase foot massage",
    "MassageInstensityStrengthen": "Increase massage",
    "MassageModeChange": "Change massage mode",
    "MassageModeAllOff": "Massage off",
    "MassageSwitch": "Toggle massage",
    "Massage10MinuteTimer": "Massage 10 min",
    "Massage20MinuteTimer": "Massage 20 min",
    "Massage30MinuteTimer": "Massage 30 min",
    "AntiSnoring": "Anti-snore",
    "ZeroGravity": "Zero gravity",
    "TVPosition": "TV",
    "LoungePosition": "Lounge",
    "CoaxingSleepMode": "Soothing sleep",
    "SyncOn": "Synchronize",
    "SyncOff": "Stop synchronization",
    **{f"MemoryPosition{i}": f"Memory {i}" for i in range(1, 5)},
}


class FlexxAction(Action):
    @property
    def label(self) -> str:
        return LABELS[self.action]


@dataclass(frozen=True, slots=True, kw_only=True)
class FlexxProfile(DreamSenseProfile):
    label: str
    box_query: bool
    omitted: tuple[str, ...]

    @property
    def motor_count(self) -> int:
        """Count only the model's physically named motor controls."""
        return sum(
            any(a.action == name + "Up" for a in self.controls)
            for name in ("Head", "Foot", "Lumber", "Pillow", "FootBox")
        )

    @property
    def key(self) -> str:
        return "flexx_motion_" + self.product

    @property
    def light_seconds(self) -> tuple[int, ...]:
        return tuple(range(1800, 28801, 2700)) if self.label == "blue" else tuple(range(0, 901, 60))


def _profiles() -> dict[str, FlexxProfile]:
    profiles = {}
    for row in json.loads(Path(__file__).with_suffix(".json").read_text()):
        controls = tuple(FlexxAction(*action) for action in row.pop("controls"))
        row["omitted"] = tuple(row["omitted"])
        profiles[row["product"]] = FlexxProfile(
            **row,
            controls=controls,
            execution=ExecutionCapabilities(
                hold="stream", hold_controls=frozenset(a.action for a in controls if a.held)
            ),
        )
    return profiles


PROFILES: Final = _profiles()
CHOICES: Final = {
    key: p.label if p.normal else f"Restored product: {p.label}"
    for key, p in sorted(PROFILES.items(), key=lambda item: (not item[1].normal, item[0]))
}
