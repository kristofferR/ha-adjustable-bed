"""Profiles over the Malouf codec.

``NEW_OKIN`` serves the ``malouf_new_okin`` bed type; it has no accepted report,
so it holds the frames its pre-v5 controller sent. ``MALOUF`` and ``LUCID`` serve
the ``malouf_app`` bed type from the accepted row023 reports: Malouf Base 2.4.3
(``com.malouf.bedbase``) and Lucid Base 1.3.3 (``com.lucid.bedbase``), with the
accepted write-mode and routing amendments. Retail models, GATT transport and
the physical role are independent choices of an app profile.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from ..codec.malouf import Family, TransportKey
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class MaloufAppModel:
    """Explicit app model capabilities, including persisted-only profiles."""

    name: str
    memory_slots: int
    manual: tuple[str, ...]
    presets: tuple[str, ...]
    functions: tuple[str, ...]


_BASIC = ("back", "legs")
_PRESETS = ("zero_g", "anti_snore")
_FULL_PRESETS = ("zero_g", "tv", "anti_snore", "lounge")
_MASSAGE = ("massage", "massage_head", "massage_foot", "massage_wave")
_RICHMAT = (*_MASSAGE, "massage_off", "massage_timer_set", "light")
_OKIN = (*_MASSAGE, "massage_timer_step", "alarm", "light")

# The 16 model constructors both apps ship.
MALOUF_APP_MODELS: Final[dict[str, MaloufAppModel]] = {
    "Altitude": MaloufAppModel(
        "Altitude",
        0,
        (*_BASIC, "dual", "tilt_head", "full_tilt"),
        _PRESETS,
        (*_MASSAGE, "massage_off", "light"),
    ),
    "E450": MaloufAppModel("E450", 0, _BASIC, _PRESETS, ()),
    "E455": MaloufAppModel("E455", 0, _BASIC, _PRESETS, ()),
    "Forte": MaloufAppModel(
        "Forte", 0, _BASIC, ("zero_g",), ("massage", "massage_head", "massage_wave", "massage_off")
    ),
    "GoodLifeBase": MaloufAppModel("Good Life Base", 0, (*_BASIC, "dual"), _FULL_PRESETS, ()),
    "GoodLifePremierBase": MaloufAppModel(
        "Good Life Premier Base", 0, (*_BASIC, "dual", "tilt", "lumbar"), _FULL_PRESETS, _RICHMAT
    ),
    "GoodLifeProBase": MaloufAppModel(
        "Good Life Pro Base", 0, (*_BASIC, "dual"), _FULL_PRESETS, _RICHMAT
    ),
    "L300": MaloufAppModel("L300", 0, _BASIC, _PRESETS, ()),
    "L600": MaloufAppModel("L600", 1, _BASIC, ("zero_g", "anti_snore", "lounge", "tv"), _OKIN),
    "M455": MaloufAppModel(
        "M455",
        0,
        _BASIC,
        _PRESETS,
        ("massage", "massage_head", "massage_wave", "massage_off", "massage_timer_set"),
    ),
    "M550": MaloufAppModel("M550", 1, _BASIC, ("zero_g", "anti_snore", "lounge", "tv"), _OKIN),
    "M555": MaloufAppModel("M555", 1, (*_BASIC, "dual"), _FULL_PRESETS, _RICHMAT),
    # Malouf's uppercase READ has no writable endpoint. Lucid lowercases it
    # to an Okin-only endpoint, exposed separately as an app-labelled action.
    "Premium": MaloufAppModel(
        "Premium", 2, (*_BASIC, "dual"), ("zero_g", "anti_snore", "tv"), _OKIN
    ),
    "S655": MaloufAppModel("S655", 2, (*_BASIC, "dual", "tilt"), _FULL_PRESETS, _RICHMAT),
    "S750": MaloufAppModel("S750", 2, (*_BASIC, "tilt", "lumbar"), _FULL_PRESETS, _OKIN),
    "S755": MaloufAppModel("S755", 2, (*_BASIC, "dual", "tilt", "lumbar"), _FULL_PRESETS, _RICHMAT),
}


@dataclass(frozen=True, kw_only=True)
class Recall:
    """Presets and memory recall: the frame ``repeats`` times back to back, then STOP or not."""

    repeats: int = 1
    stop: bool


@dataclass(frozen=True, kw_only=True)
class Save:
    """Hold-to-save: wait one interval, then ``repeats`` writes ``interval_ms`` apart, no STOP."""

    repeats: int
    interval_ms: int


@dataclass(frozen=True, kw_only=True)
class SaveWords:
    """Okin save words per slot; device names containing ``smartbed238`` save slot 1 differently."""

    slots: Mapping[int, int]
    smartbed238_slot_1: int

    def word(self, slot: int, device_name: str | None) -> int:
        if slot == 1 and device_name and "smartbed238" in device_name.lower():
            return self.smartbed238_slot_1
        return self.slots[slot]


_SAVE_WORDS: Final = SaveWords(slots={1: 0x10000, 2: 0x80040000}, smartbed238_slot_1=0x80010000)


@dataclass(frozen=True, kw_only=True)
class Route:
    """What one transport does in an app: recall, Okin save and settings repeats, status query."""

    recall: Recall
    save: Save | None = None
    settings_repeats: int = 1
    """Clock and alarm writes, sent back to back."""
    status_query: bool = False
    """Send ``00 B0`` after light and massage actions."""


@dataclass(frozen=True, kw_only=True)
class MaloufAppProfile:
    """One app: its model picker, command tables, routes and app-specific gates."""

    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    models: tuple[str, ...]
    """The app's fresh-setup picker; every constructor stays valid for stored entries."""
    name_rule: tuple[tuple[tuple[str, ...], Family], ...]
    """Device-name fragments that pick the transport family; no name means Okin."""
    routes: Mapping[TransportKey, Route]
    richmat: Mapping[str, int]
    okin: Mapping[str, int]
    selector_actions: frozenset[str]
    """Actions whose framed Richmat selector follows the configured physical role."""
    status_actions: frozenset[str]
    save_words: SaveWords
    hold_ms: int
    """Movement refresh while held."""
    release_ms: int
    """STOP follows the end of a held movement after this delay."""
    read_models: frozenset[str] = frozenset()
    """Models whose READ preset reaches the Okin lounge endpoint."""
    oz_editor_models: frozenset[str] = frozenset()
    """Models whose Oz preset editor saves memory slot 2."""
    literal_oz_presets: bool = False
    """Good Life Oz preset labels pass through literally, which Okin does not accept."""
    timer_panel_by_model: bool = False
    """The direct massage timer follows the model's function, not the controller's."""

    def family(self, device_name: str | None) -> Family | None:
        """Transport family named by the device name, or None when the name is unknown."""
        if device_name is None:
            return "okin"
        return next(
            (family for parts, family in self.name_rule if any(p in device_name for p in parts)),
            None,
        )


_NAME_RULE: Final[tuple[tuple[tuple[str, ...], Family], ...]] = (
    (("X1RM", "QRRM"), "richmat"),
    (("OKIN", "Smartbed"), "okin"),
)
_RICHMAT_OPCODES: Final[dict[str, int]] = {
    "head_up": 0x24,
    "head_down": 0x25,
    "foot_up": 0x26,
    "foot_down": 0x27,
    "dual_up": 0x29,
    "dual_down": 0x2A,
    "save_1": 0x2B,
    "save_2": 0x2C,
    "memory_1": 0x2E,
    "memory_2": 0x2F,
    "flat": 0x31,
    "light": 0x3C,
    "tilt_up": 0x3F,
    "tilt_down": 0x40,
    "full_tilt_up": 0x3F,
    "full_tilt_down": 0x40,
    "tilt_head_up": 0x41,
    "tilt_head_down": 0x42,
    "lumbar_up": 0x41,
    "lumbar_down": 0x42,
    "zero_g": 0x45,
    "anti_snore": 0x46,
    "massage_off": 0x47,
    "massage_wave": 0x48,
    "massage_head": 0x4C,
    "massage_foot": 0x4E,
    "tv": 0x58,
    "lounge": 0x59,
    "massage_10": 0x5F,
    "massage_30": 0x61,
    "massage_20": 0x63,
    "stop": 0x6E,
}
_OKIN_WORDS: Final[dict[str, int]] = {
    "stop": 0,
    "head_up": 1,
    "head_down": 2,
    "foot_up": 4,
    "foot_down": 8,
    "dual_up": 5,
    "dual_down": 10,
    "tilt_up": 0x10,
    "tilt_down": 0x20,
    "lumbar_up": 0x40,
    "lumbar_down": 0x80,
    "massage_timer_step": 0x200,
    "massage_foot": 0x400,
    "massage_head": 0x800,
    "zero_g": 0x1000,
    "lounge": 0x2000,
    "tv": 0x4000,
    "anti_snore": 0x8000,
    "memory_1": 0x10000,
    "light": 0x20000,
    "memory_2": 0x40000,
    "flat": 0x08000000,
    "massage_wave": 0x10000000,
}
_SELECTOR_ACTIONS: Final = frozenset(
    {"head_up", "head_down", "massage_head", "flat", "zero_g", "anti_snore"}
)
_STATUS_ACTIONS: Final = frozenset(
    {"light", "massage_head", "massage_foot", "massage_wave", "massage_timer_step"}
)

MALOUF: Final = MaloufAppProfile(
    key="malouf",
    models=(
        "E450",
        "E455",
        "M455",
        "M555",
        "S655",
        "S755",
        "Forte",
        "Altitude",
        "GoodLifeBase",
        "GoodLifePremierBase",
        "GoodLifeProBase",
        "L600",
        "M550",
        "S750",
    ),
    name_rule=_NAME_RULE,
    routes={
        "richmat_single": Route(recall=Recall(stop=True)),
        "richmat_framed": Route(recall=Recall(stop=False)),
        "okin_legacy": Route(
            recall=Recall(repeats=3, stop=False),
            save=Save(repeats=85, interval_ms=150),
            settings_repeats=3,
        ),
        "okin_custom": Route(
            recall=Recall(repeats=3, stop=True),
            save=Save(repeats=85, interval_ms=150),
            settings_repeats=3,
        ),
        "okin_new": Route(
            recall=Recall(stop=True), save=Save(repeats=55, interval_ms=100), status_query=True
        ),
    },
    richmat=_RICHMAT_OPCODES,
    okin=_OKIN_WORDS,
    selector_actions=_SELECTOR_ACTIONS,
    status_actions=_STATUS_ACTIONS,
    save_words=_SAVE_WORDS,
    hold_ms=150,
    release_ms=150,
)
# Both apps embed the same com.malouf.adjustablebasebluetooth SDK. Each report
# independently proves its transports, tables and timing, and the accepted
# cluster007 reconciliation finds them equal; Lucid differs only in its app gates.
LUCID: Final = replace(
    MALOUF,
    key="lucid",
    models=("L300", "L600", "Premium"),
    read_models=frozenset({"Premium"}),
    oz_editor_models=frozenset({"GoodLifeBase", "GoodLifePremierBase", "GoodLifeProBase"}),
    literal_oz_presets=True,
    timer_panel_by_model=True,
)
APP_PROFILES: Final[dict[str, MaloufAppProfile]] = {
    profile.key: profile for profile in (MALOUF, LUCID)
}


@dataclass(frozen=True, kw_only=True)
class MaloufRouteProfile:
    """A fixed-transport route: its key words, recall and save; movement uses the pulse settings."""

    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    transport: TransportKey
    words: Mapping[str, int]
    recall: Recall
    save: Save
    save_words: SaveWords


NEW_OKIN: Final = MaloufRouteProfile(
    key="malouf_new_okin",
    transport="okin_new",
    # The app's word table without its combined and wave keys, plus the Hi-Lo
    # columns together and three words the shared SDK defines but no app screen sends.
    words={
        **{
            k: w
            for k, w in _OKIN_WORDS.items()
            if k not in ("dual_up", "dual_down", "massage_wave")
        },
        "bed_height_up": 0x50,
        "bed_height_down": 0xA0,
        "massage_head_minus": 0x800000,
        "massage_foot_minus": 0x1000000,
        "massage_off": 0x2000000,
    },
    recall=Recall(stop=True),
    save=Save(repeats=55, interval_ms=100),
    save_words=_SAVE_WORDS,
)
