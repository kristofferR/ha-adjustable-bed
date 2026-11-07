"""Profiles over the Richmat 6E codec.

``RICHMAT`` profiles serve the ``richmat`` bed type, one per framing (WiLinke,
Nordic, Prefix55, PrefixAA); its remote codes select features, not frames.
``BEDTECH`` and ``LEGGETT_WILINKE`` are their own bed types. These three take
their frames from the pre-v5 controllers. The catalog apps keep their per-model
tables as data and use this module for their transports: RMControl 21.3.7
(row018), the five Richmat MH apps (row055), HJBed 2.1.2 (row121), the five
classic apps (row066), Good Vibe Sleep 2.0.1 (row116) and the legacy L&P
Adjustable Base 2.2.1 (row019).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from ..codec import richmat as codec
from ..codec.richmat import COMPAT_STOP, STOP, Framing, Transport, TransportKey
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities

Button = Literal[
    "head_up",
    "head_down",
    "feet_up",
    "feet_down",
    "head_feet_up",
    "head_feet_down",
    "pillow_up",
    "pillow_down",
    "lumbar_up",
    "lumbar_down",
    "flat",
    "zero_g",
    "anti_snore",
    "tv",
    "lounge",
    "save_lounge",
    "save_zero_g",
    "save_anti_snore",
    "light_toggle",
    "light_off",
    "massage_toggle",
    "massage_off",
    "massage_head",
    "massage_foot",
    "massage_mode",
    "massage_head_up",
    "massage_head_down",
    "massage_foot_up",
    "massage_foot_down",
    "massage_intensity_up",
    "massage_intensity_down",
    "massage_wave",
    "massage_timer_10",
    "massage_timer_20",
    "massage_timer_30",
    "sync_on",
    "sync_off",
]


@dataclass(frozen=True, kw_only=True)
class Recall:
    """Presets and memory recall: repeats, then STOP when ``release`` is set."""

    repeats: int = 1
    repeat_ms: int = 100
    release: bool = False


@dataclass(frozen=True, kw_only=True)
class RichmatProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    transports: tuple[TransportKey, ...]
    """Transports this profile drives, in the app's selection order."""
    framing: Framing = "wilinke"
    codes: Mapping[Button, int] | None = None
    """Fixed button codes. ``None``: a per-model catalog supplies them."""
    memory: tuple[tuple[int, int], ...] = ()
    """(recall, save) code per memory slot, from slot 1."""
    stop: int = STOP
    recall: Recall = Recall()
    quiet_release: bool = True
    """Movement cleanup logs a failed STOP instead of raising it."""

    def frame(self, code: int) -> bytes:
        return codec.encode(self.framing, code)

    def button(self, name: Button) -> bytes | None:
        code = (self.codes or {}).get(name)
        return None if code is None else self.frame(code)

    def transport(self, index: int) -> Transport:
        return codec.TRANSPORTS[self.transports[index]]


# The pre-v5 controller tried every WiLinke service before Nordic UART.
_LEGACY_TRANSPORTS: Final[tuple[TransportKey, ...]] = ("w0", "w1", "w2", "w3", "w4", "w5", "n1")

RICHMAT_CODES: Final[Mapping[Button, int]] = {
    "head_up": 0x24,
    "head_down": 0x25,
    "feet_up": 0x26,
    "feet_down": 0x27,
    "head_feet_up": 0x29,
    "head_feet_down": 0x2A,
    "pillow_up": 0x3F,
    "pillow_down": 0x40,
    "lumbar_up": 0x41,
    "lumbar_down": 0x42,
    "flat": 0x31,
    "zero_g": 0x45,
    "anti_snore": 0x46,
    "tv": 0x58,
    "lounge": 0x59,
    "save_lounge": 0x65,
    "light_toggle": 0x3C,
    "massage_toggle": 0x5D,
    "massage_off": 0x5E,
    "massage_head": 0x4C,
    "massage_foot": 0x4E,
    "massage_mode": 0x48,
    "sync_on": 0xBC,
    "sync_off": 0xBD,
}
RICHMAT_MEMORY: Final = ((0x2E, 0x2B), (0x2F, 0x2C), (0x30, 0x2D), (0xB2, 0xB3), (0xF4, 0xF5))
# GGRM's catalog ONCE actions (row055 binding rows), each released after 120 ms.
GGRM_ACTIONS: Final = {
    0x66: ("Save Zero G", "richmat_mh_save"),
    0x69: ("Save Anti-snore", "richmat_mh_save"),
    0x5F: ("Massage 10 min", "richmat_mh_massage"),
    0x63: ("Massage 20 min", "richmat_mh_massage"),
    0x61: ("Massage 30 min", "richmat_mh_massage"),
}

RICHMAT: Final[dict[Framing, RichmatProfile]] = {
    framing: RichmatProfile(
        key=f"richmat_{framing}",
        execution=STREAM_HOLD,
        transports=_LEGACY_TRANSPORTS,
        framing=framing,
        codes=RICHMAT_CODES,
        memory=RICHMAT_MEMORY,
    )
    for framing in ("wilinke", "nordic", "prefix55", "prefixaa")
}
"""Remote codes in ``RICHMAT_WILINKE_STOP_COMPAT_REMOTE_CODES`` stop with ``5E``."""

BEDTECH: Final = RichmatProfile(
    key="bedtech",
    transports=("w1",),
    codes={
        "head_up": 0x24,
        "head_down": 0x25,
        "feet_up": 0x26,
        "feet_down": 0x27,
        "pillow_up": 0x29,
        "pillow_down": 0x2A,
        "flat": 0x31,
        "zero_g": 0x45,
        "anti_snore": 0x46,
        "tv": 0x58,
        "lounge": 0x65,
        "light_toggle": 0x3C,
        "light_off": 0x75,
        "massage_toggle": 0x5D,
        "massage_head": 0x4C,
        "massage_foot": 0x4E,
        "massage_mode": 0x48,
    },
    memory=((0x2E, 0x2B), (0x2F, 0x2C)),
    # Field reports: BT6500 variants stop only on ``^``.
    stop=COMPAT_STOP,
    quiet_release=False,
)
LEGGETT_WILINKE: Final = RichmatProfile(
    key="leggett_wilinke",
    execution=STREAM_HOLD,
    transports=("w1",),
    codes={
        "head_up": 0x24,
        "head_down": 0x25,
        "feet_up": 0x26,
        "feet_down": 0x27,
        "flat": 0x31,
        "zero_g": 0x45,
        "anti_snore": 0x46,
        "tv": 0x58,
        "lounge": 0x59,
        "light_toggle": 0x3C,
        "massage_off": 0x47,
        "massage_toggle": 0x32,
        "massage_head": 0x32,
        "massage_foot": 0x33,
        "massage_mode": 0x38,
        "massage_head_up": 0x4C,
        "massage_head_down": 0x4D,
        "massage_foot_up": 0x4E,
        "massage_foot_down": 0x4F,
        "massage_intensity_up": 0x34,
        "massage_intensity_down": 0x35,
        "massage_wave": 0x39,
        "massage_timer_10": 0x5F,
        "massage_timer_20": 0x63,
        "massage_timer_30": 0x61,
    },
    memory=((0x2E, 0x2B), (0x2F, 0x2C)),
    recall=Recall(repeats=100, repeat_ms=300, release=True),
)

# The five MH apps and the five RUF and Richmat app profiles (RUF, W.Silver,
# AMERICANSTAR, Bailey, TX) share one BLE library and its transport order.
RICHMAT_MH: Final[dict[str, RichmatProfile]] = {
    app: RichmatProfile(
        key=f"richmat_mh_{app}", execution=STREAM_HOLD, transports=("n1", "w1", "w2", "w3", "w4")
    )
    for app in (
        "revive",
        "best_mattress",
        "blvd_home",
        "harmony",
        "idealbed",
        "ruf",
        "wsilver2",
        "americanstar",
        "bailey2",
        "tx",
    )
}
HJBED: Final = RichmatProfile(
    key="hjbed", execution=STREAM_HOLD, transports=("w1", "n1", "w5", "w4", "w3", "w2")
)
# The services Good Vibe accepts; it takes them in the bed's enumeration order.
# Its controller declares holds per product, on the sustained-press controls.
GOODVIBE: Final = RichmatProfile(key="goodvibe", transports=("w1", "n1", "w5", "w4", "w3", "w2"))
# The five classic resource-driven apps (row066) share one builder and service
# order; each keeps its own catalog in ``beds/richmat_classic/data``. The first present
# service wins, and Nordic UART takes the bare resource bytes.
CLASSIC_TRANSPORTS: Final[tuple[TransportKey, ...]] = ("w1", "w2", "n1", "w4")
RICHMAT_CLASSIC: Final[dict[str, RichmatProfile]] = {
    app: RichmatProfile(key=f"richmat_classic_{app}", transports=CLASSIC_TRANSPORTS)
    for app in ("avocadoecobase", "coastersleep", "fortywinks", "milemont", "superior")
}

# Eshine 1.0.1 (row106): the E6000's one fixed table, over the app's transports.
ESHINE: Final = RichmatProfile(
    key="eshine",
    execution=STREAM_HOLD,
    transports=("n1", "w1", "w2", "w3", "w4", "w5"),
    codes={
        "head_up": 0x24,
        "head_down": 0x25,
        "feet_up": 0x26,
        "feet_down": 0x27,
        "lumbar_up": 0x3F,
        "lumbar_down": 0x40,
        "pillow_up": 0x41,
        "pillow_down": 0x42,
        "flat": 0x31,
        "zero_g": 0x45,
        "anti_snore": 0x46,
        "save_zero_g": 0x66,
        "save_anti_snore": 0x69,
        "light_toggle": 0x3C,
        "massage_head": 0x4C,
        "massage_foot": 0x4E,
        "massage_mode": 0x48,
        "massage_off": 0x5E,
        "massage_timer_10": 0x5F,
        "massage_timer_20": 0x63,
        "massage_timer_30": 0x61,
    },
)

# L&P Adjustable Base 2.2.1 (row019): its per-layout tokens are
# ``beds/leggett/lp_legacy_catalog.py``. It writes to the characteristics the user
# configures, so it drives none of the codec's transports.
LP_LEGACY: Final = RichmatProfile(key="leggett_lp_legacy", transports=())
