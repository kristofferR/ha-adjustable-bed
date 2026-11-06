"""The Casper Base 1.0.8 app's products as profiles over ``codec/casper.py``.

The app (``com.richmat.casperbase``, row101) offers two products of its own,
PRO and MAX. It also restores products a phone saved under its shared catalog;
those are explicit choices, never inferred from an advertisement. Each row of
``casper_base_catalog.py``, generated from the accepted catalog, names the
product, its control groups as indices into the action list and its page flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..casper_base_catalog import ACTIONS as _ACTIONS
from ..casper_base_catalog import PRODUCTS as _PRODUCTS
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

# A catalog row: label; motor, massage, preset, alarm and fan action indices;
# then the light, RGB, music, sleep, repeating-alarm and side flags. Hush Base
# products have the same layout.
type ProductRow = tuple[
    str, tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...],
    bool, bool, bool, bool, bool, bool,
]  # fmt: skip
# One control: name, short opcode and optional program opcode.
type Action = tuple[str, int, int | None]

ACTIONS: Final[tuple[Action, ...]] = _ACTIONS
# The app's own picker; the others are restored profiles.
CURRENT: Final = frozenset({"casperpro", "caspermax"})


@dataclass(frozen=True)
class CasperProfile:
    """One product: its catalog row, as the app selects it."""

    key: str
    row: ProductRow
    # No hold yet: see docs/design/execution-capabilities.md.
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES

    @property
    def label(self) -> str:
        return self.row[0]

    @property
    def current(self) -> bool:
        return self.key in CURRENT


PROFILES: Final[dict[str, CasperProfile]] = {
    key: CasperProfile(key, row) for key, row in _PRODUCTS.items()
}
