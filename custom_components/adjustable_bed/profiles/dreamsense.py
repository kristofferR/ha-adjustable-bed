"""Dream Sense Bed's saved product keys, distinct from its remote labels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..codec import richmat as codec
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

SCAN_WORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")
TICK_MS: Final = 100
PROBE_MS: Final = 300
EXPIRY_MS: Final = 500


@dataclass(frozen=True, slots=True)
class Action:
    action: str
    code: int
    save: int | None
    held: bool
    release: bool
    save_delay_ms: int

    @property
    def label(self) -> str:
        return LABELS[self.action]


@dataclass(frozen=True, slots=True)
class DreamSenseProfile:
    product: str
    remote: str
    normal: bool
    controls: tuple[Action, ...]
    alarm: dict[str, int]
    clock: bool
    repeat: bool
    light: bool
    vibration: bool
    side: bool
    split: bool
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES

    @property
    def key(self) -> str:
        return "dreamsense_" + self.product

    def frame(self, code: int, *, single: bool, side: int = 0, action: str = "") -> bytes:
        return codec.function(code, side, action=action, single=single)


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
    "TileUp": "Tilt up",
    "TileDown": "Tilt down",
    "FootBoxUp": "Storage lift up",
    "FootBoxDown": "Storage lift down",
    "MotorReset": "Flat",
    "BedLight": "Toggle underbed light",
    "LightBoard": "Toggle light board",
    "MassageHeadInstensityStrengthen": "Head massage intensity step",
    "MassageFootInstensityStrengthen": "Foot massage intensity step",
    "MassageInstensityStrengthen": "Massage intensity step",
    "MassageModeChange": "Massage mode step",
    "MassageModeAllOff": "Massage off",
    "MassageSwitch": "Toggle massage",
    "Massage10MinuteTimer": "Massage 10 min",
    "Massage20MinuteTimer": "Massage 20 min",
    "Massage30MinuteTimer": "Massage 30 min",
    "AntiSnoring": "Anti-snore",
    "ZeroGravity": "Zero gravity",
    "TVPosition": "TV",
    "LoungePosition": "Lounge",
    "CoaxingSleepMode": "Sleep aid",
    "SyncOn": "Synchronization on",
    "SyncOff": "Synchronization off",
    **{f"MemoryPosition{i}": f"Memory {i}" for i in range(1, 5)},
}
ALARM_NAMES: Final = {
    "MotorReset": "flat",
    "ZeroGravity": "zero_g",
    "AntiSnoring": "anti_snore",
    "TVPosition": "tv",
    "LoungePosition": "lounge",
    "CoaxingSleepMode": "sleep_aid",
    **{f"MemoryPosition{i}": f"memory_{i}" for i in range(1, 5)},
}


def _load() -> dict[str, DreamSenseProfile]:
    return {
        row["key"]: DreamSenseProfile(
            **{
                **{k: v for k, v in row.items() if k != "key"},
                "product": row["key"],
                "controls": tuple(Action(**a) for a in row["controls"]),
            }
        )
        for row in json.loads(Path(__file__).with_suffix(".json").read_text())
    }


PROFILES: Final = _load()
CHOICES: Final = {
    key: key.title()
    if p.normal
    else f"Saved product: {key}" + (f" ({p.remote})" if p.remote and p.remote != key else "")
    for key, p in sorted(PROFILES.items(), key=lambda item: (not item[1].normal, item[0]))
}
