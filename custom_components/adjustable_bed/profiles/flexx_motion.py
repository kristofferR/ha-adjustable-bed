"""Flexx Motion 2.0.1 (20100), preset-only data over the Richmat codec.

These are partial preset menus, not runnable bed profiles. Discovery, session
admission and movement cleanup remain unverified. No controller or setup route
may be inferred from these records, including for the seven named products.
"""

from dataclasses import dataclass
from typing import Final, Literal

from ..codec.richmat import TransportKey

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

# Catalog roles only. They establish neither matching predicates nor admission.
CATALOG_TRANSPORTS: Final[tuple[TransportKey, ...]] = ("n1", "w1", "w2", "w3", "w4", "w5")
PRESET_WRITES: Final = 1
PRESET_RELEASE: Final = False
# The transport's scheduling cycle is not a minimum inter-write interval.
QUEUE_CYCLE_MS: Final = 100
RECEIVE_EXPIRY_S: Final = 0.5
