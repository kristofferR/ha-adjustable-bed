"""The Casper Base 1.0.8 app's products as profiles over ``codec/richmat.py``.

The app (``com.richmat.casperbase``, row101) offers two products of its own,
PRO and MAX. It also restores products a phone saved under its shared catalog;
those are explicit choices, never inferred from an advertisement. Each row of
``beds/casper_base/catalog.py``, generated from the accepted catalog, names the
product, its control groups as indices into the action list and its page flags.

The app's Richmat library, which Hush Base 1.0.5 (row126) also ships, sets the
transports, connect queries and fixed opcodes below. This module stays free of
codec imports, so setup and pairing can read its products without the codec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from ..beds.casper_base.catalog import ACTIONS as _ACTIONS
from ..beds.casper_base.catalog import PRODUCTS as _PRODUCTS
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

if TYPE_CHECKING:
    from ..codec.richmat import TransportKey

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

# The library's services, in its lookup order; the first one present wins.
TRANSPORTS: Final[tuple[TransportKey, ...]] = ("n1", "w1", "w2", "w3", "w4", "w5")
# Sent after subscribing, as (function selector, code).
QUERIES: Final = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
    ("deviceFunctionItemCheckMusic", 1),
)
LIGHT_OFF: Final = 0x75
# Sent on the default side when an external detector reports snoring.
ANTI_SNORE: Final = 0x46
MUSIC_BLUETOOTH: Final = 0xD8


def light_duration(seconds: int) -> tuple[int, int]:
    """The light timer's high and low bytes; zero is the always-on ``FF FF``.

    The app slices them from a zero-padded hexadecimal string.
    """
    text = format(seconds, "x").rjust(4, "0")
    high, low = int(text[:2], 16), int(text[2:4], 16)
    return (255, 255) if high == low == 0 else (high, low)


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
# Setup choices, and the products with the side flag.
CASPER_BASE_VARIANTS: Final = {
    key: profile.label + ("" if profile.current else " (stored profile)")
    for key, profile in PROFILES.items()
}
CASPER_BASE_SIDE_VARIANTS: Final = frozenset(
    key for key, profile in PROFILES.items() if profile.row[11]
)
