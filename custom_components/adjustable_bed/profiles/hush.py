"""The Hush Base 1.0.5 app's products as profiles over ``codec/richmat.py``.

The app (``com.richmat.hushbase``, row126) lists twelve products of its own,
catalog indices 46 to 57. It also restores products a phone saved under its
shared catalog, the other indices from 1 to 71; those keep the Hush app's own
rows. Each row in ``hush_catalog.py`` names the product, its action groups,
alarm positions and page flags, from the accepted product joins. The app ships
the Casper Base library: its transports, queries and fixed opcodes are in
``profiles/casper.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ..hush_catalog import ACTIONS as _CATALOG_ACTIONS
from ..hush_catalog import INDICES, PRODUCTS
from .casper import Action, ProductRow

# The app's own products; the others are restored profiles.
CURRENT: Final = range(46, 58)
# The catalog's actions, then the music page's own controls, which no product
# list includes.
ACTIONS: Final[tuple[Action, ...]] = (
    *_CATALOG_ACTIONS,
    ("MusicSwitchSoundTrack", 0xC4, None),
    ("MusicShakeMode", 0xD6, None),
    ("MusicVolumuDown", 0xD5, None),
    ("MusicVolumuUp", 0xD4, None),
    ("MusicNextSong", 0xD3, None),
    ("MusicPausePlay", 0xD7, None),
    ("MusicPreviousSong", 0xD2, None),
)


@dataclass(frozen=True)
class HushProfile:
    """One product: its catalog row, as the app selects it."""

    key: str
    index: int
    row: ProductRow
    # No hold yet: see docs/design/execution-capabilities.md.
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES

    @property
    def label(self) -> str:
        return self.row[0]

    @property
    def current(self) -> bool:
        return self.index in CURRENT


PROFILES: Final[dict[str, HushProfile]] = {
    key: HushProfile(key, INDICES[key], row) for key, row in PRODUCTS.items()
}
# Setup choices, and the products with the side flag.
HUSH_BASE_VARIANTS: Final = {
    key: profile.label + ("" if profile.current else " (restored profile)")
    for key, profile in PROFILES.items()
}
HUSH_BASE_SIDE_VARIANTS: Final = frozenset(key for key, profile in PROFILES.items() if profile.row[11])
