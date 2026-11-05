"""The Hush Base 1.0.5 app's products as profiles over ``codec/casper.py``.

The app (``com.richmat.hushbase``, row126) lists twelve products of its own,
catalog indices 46 to 57. It also restores products a phone saved under its
shared catalog, the other indices from 1 to 71; those keep the Hush app's own
rows. Each row in ``hush_catalog.py`` names the product, its action groups,
alarm positions and page flags, from the accepted product joins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ..hush_catalog import INDICES, PRODUCTS

# The app's own products; the others are restored profiles.
CURRENT: Final = range(46, 58)


@dataclass(frozen=True)
class HushProfile:
    """One product: its catalog row, as the app selects it."""

    key: str
    index: int
    row: tuple[object, ...]
    # No hold yet: see docs/design/execution-capabilities.md.
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES

    @property
    def label(self) -> str:
        return str(self.row[0])

    @property
    def current(self) -> bool:
        return self.index in CURRENT


PROFILES: Final[dict[str, HushProfile]] = {
    key: HushProfile(key, INDICES[key], row) for key, row in PRODUCTS.items()
}
