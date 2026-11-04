"""Profiles over the Keeson codec.

Each ``keeson`` protocol variant is a profile here, and so are the routes a
device name or service resolves inside a variant (KSBT03C, Purple Premium Plus,
Sleep Harmony base-i5, the Adjustable Lite KSBT03C remote, and the BetterLiving
and CB1322 auto-detected tables). The ``ergomotion``, ``serta`` and ``okin_ffe``
bed types are aliases of the variant profiles of the same name. The cluster033
app bed types (Tempur Curve, Q-Plus, Serta MP Remote and the other
``APP_LAYOUTS`` apps) are ``AppProfile`` layouts, driven by ``beds/cluster033.py``;
Ergomotion 4.0 is one too, with its product catalog in ``ergomotion4_profiles.py``.

App profiles take their words and timing from their accepted APK Protocol Audit
reports; the other routes keep the frames and timing of the pre-v5 controller.
Timing is per profile and never shared.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, Literal

from ..alarm_table import AlarmTableScheduleSpec
from ..codec import keeson as codec
from ..codec.keeson import ByteOrder, Carrier, Side, TransportKey

Preset = Literal["flat", "zero_g", "lounge", "tv", "anti_snore"]
Massage = Literal["step", "absolute", "zone_steps", "none"]
Lights = Literal["toggle", "discrete"]
Step = tuple[int, int | bytes]
"""Wait in ms after the previous write, then a word (in the profile's carrier) or literal frame."""


class KeesonCommands:
    """Keeson base key words. Presets and memory differ per app; see each profile."""

    PRESET_FLAT = 0x8000000
    PRESET_ZERO_G = 0x1000
    PRESET_MEMORY_1 = 0x2000  # KSBT "Read", Lounge
    PRESET_MEMORY_2 = 0x4000  # KSBT "TV"
    PRESET_MEMORY_3 = 0x8000  # KSBT anti-snore
    PRESET_MEMORY_4 = 0x10000  # KSBT "M"
    PRESET_LOUNGE = PRESET_MEMORY_1
    PRESET_TV = PRESET_MEMORY_2
    PRESET_ANTI_SNORE = PRESET_MEMORY_3

    MOTOR_HEAD_UP = codec.HEAD_UP
    MOTOR_HEAD_DOWN = codec.HEAD_DOWN
    MOTOR_FEET_UP = codec.FOOT_UP
    MOTOR_FEET_DOWN = codec.FOOT_DOWN
    MOTOR_TILT_UP = codec.TILT_UP
    MOTOR_TILT_DOWN = codec.TILT_DOWN
    MOTOR_LUMBAR_UP = codec.LUMBAR_UP
    MOTOR_LUMBAR_DOWN = codec.LUMBAR_DOWN

    MASSAGE_HEAD_UP = 0x800
    MASSAGE_HEAD_DOWN = 0x800000
    MASSAGE_FOOT_UP = 0x400
    MASSAGE_FOOT_DOWN = 0x1000000
    MASSAGE_STEP = 0x100
    MASSAGE_TIMER_STEP = 0x200
    # BaseI4/I5 wave and intensity keys, confirmed on GlideAway ComfortBase Odessa.
    MASSAGE_WAVE_STEP = 0x10000000
    MASSAGE_WAVE_PREVIOUS = 0x4000000
    MASSAGE_INTENSITY_1 = 0x80000
    MASSAGE_INTENSITY_2 = 0x100000
    MASSAGE_INTENSITY_3 = 0x200000
    # Sleep Harmony all-zone massage stop.
    MASSAGE_ALL_STOP = 0x2000000

    TOGGLE_SAFETY_LIGHTS = 0x20000
    TOGGLE_LIGHTS = TOGGLE_SAFETY_LIGHTS


class SinoCommands:
    """Sino (Dynasty, BetterLiving) words: discrete lights, absolute massage levels."""

    LIGHT_ON = 0x31000001
    LIGHT_OFF = 0x31000000
    MASSAGE_HEAD_INTENSITY_BASE = 0x10000010  # + level 0..10
    MASSAGE_FOOT_INTENSITY_BASE = 0x11000010  # + level 0..10
    MASSAGE_HEAD_WAVE_BASE = 0x10000020  # + pattern 1..10


@dataclass(frozen=True, kw_only=True)
class Release:
    """Cleanup after a hold, an explicit stop or (with ``after_tap``) a one-shot action."""

    steps: tuple[Step, ...] = ((0, codec.RELEASE),)
    on_stop: bool = True
    """An explicit stop sends the steps without their waits; otherwise it sends nothing."""
    after_tap: bool = False
    guarded: bool = False
    """Touch-up release: STOP ends the wait early and cancellation cannot suppress the write."""


@dataclass(frozen=True, kw_only=True)
class MemorySave:
    words: Mapping[int, int]
    repeats: int = 1
    repeat_ms: int = 100
    wait_first: bool = False
    """Wait before every write instead of between writes."""


_EMPTY: Final[Mapping[int, int]] = MappingProxyType({})


@dataclass(frozen=True, kw_only=True)
class KeesonProfile:
    key: str
    carrier: Carrier = "k1"
    header: int = 0xE5
    order: ByteOrder = "little"
    side: int | None = None
    """Side byte of the nine-byte K1 frame."""
    single_side: bool = False
    """Left/Right side frames (``codec.side_frame``) are proven for this route."""
    split_sides: Mapping[str, int] = MappingProxyType({})
    """Selector bytes of an A/B split-bed choice; a side sends the nine-byte E6 frame.

    The A/B labels are the app's own and establish no Left/Right orientation.
    """
    transport: TransportKey = "base"
    notify: TransportKey = "base"
    fixed_write: bool = False
    """The app writes only to the transport's write role, with no fallback search."""
    no_response: bool = False
    """Android's default write type: without response when the characteristic offers it."""
    hold: tuple[int, int] | None
    """App hold cadence (writes, interval ms) for the stored default; ``None`` keeps it."""
    three_motor_hold: tuple[int, int] | None = None
    refresh_ms: int | None = None
    """Fixed held-key refresh interval of an app controller, whatever the configured cadence."""
    release: Release = Release()
    tap_wait_ms: int = 0
    """The app sleeps this long before every one-shot write."""
    presets: Mapping[Preset, int] = MappingProxyType({})
    """Words the preset actions send."""
    unlisted_presets: frozenset[Preset] = frozenset()
    """Presets the actions send but no entity exposes."""
    memory: Mapping[int, int] = _EMPTY
    """Recall words by slot."""
    memory_slots: int = 0
    memory_save: MemorySave | None = None
    lights: Lights | None = "toggle"
    lights_listed: bool = True
    massage: Massage = "step"
    massage_off: int | None = None
    wave_controls: bool = False
    tilt: bool = True
    lumbar: bool = True
    keeson_motor_names: bool = True
    """Head, tilt and feet motors are labelled back, head and legs."""
    position_feedback: bool = False
    status_poll_ms: int | None = None
    status_timer: bool = False
    held_controls: Mapping[str, tuple[int, bool]] = MappingProxyType({})
    """App controls by name: (word, refreshed while held)."""


K = KeesonCommands
_BASE_PRESETS: Final[Mapping[Preset, int]] = {"flat": K.PRESET_FLAT, "zero_g": K.PRESET_ZERO_G}
_KSBT_PRESETS: Final[Mapping[Preset, int]] = {
    **_BASE_PRESETS,
    "lounge": K.PRESET_LOUNGE,
    "tv": K.PRESET_TV,
    "anti_snore": K.PRESET_ANTI_SNORE,
}
_TV_UNLISTED: Final[Mapping[Preset, int]] = {**_BASE_PRESETS, "tv": K.PRESET_TV}
_GENERIC_MEMORY: Final[Mapping[int, int]] = {
    1: K.PRESET_MEMORY_1,
    2: K.PRESET_MEMORY_2,
    3: K.PRESET_MEMORY_3,
    4: K.PRESET_MEMORY_4,
}
_KSBT_MEMORY: Final[Mapping[int, int]] = {
    1: K.PRESET_MEMORY_1,
    2: K.PRESET_MEMORY_2,
    3: K.PRESET_MEMORY_4,
}

# Ergomotion 4.0 3.7 (com.sfd.hump) proves the P1 Left/Right frames that BASE and
# ERGOMOTION send for a split base on one address; the auto-detected tables do not.
BASE: Final = KeesonProfile(
    key="base",
    single_side=True,
    hold=(3, 400),
    presets={**_BASE_PRESETS},
    memory=_GENERIC_MEMORY,
    memory_slots=4,
    wave_controls=True,
)
ERGOMOTION: Final = KeesonProfile(
    key="ergomotion",
    single_side=True,
    hold=(10, 100),
    presets=_KSBT_PRESETS,
    memory=_GENERIC_MEMORY,
    memory_slots=4,
    position_feedback=True,
)
SERTA: Final = KeesonProfile(
    key="serta",
    hold=(10, 100),
    presets=_TV_UNLISTED,
    unlisted_presets=frozenset({"tv"}),
    memory=_GENERIC_MEMORY,
    memory_slots=4,
)
OKIN: Final = KeesonProfile(
    key="okin",
    header=0xE6,
    hold=(10, 100),
    three_motor_hold=(5, 200),
    presets=_TV_UNLISTED,
    unlisted_presets=frozenset({"tv"}),
    memory=_GENERIC_MEMORY,
    memory_slots=4,
)
# BetterLiving CB1322 boxes (com.betterliving.bed): OKIN frames with their own memory words.
_CB1322_MEMORY: Final[Mapping[int, int]] = {1: 0x10000, 2: 0x40000}
CB1322: Final = replace(
    OKIN,
    key="cb1322",
    memory=_CB1322_MEMORY,
    memory_slots=2,
    memory_save=MemorySave(words=_CB1322_MEMORY, repeats=30, repeat_ms=100),
)
SINO: Final = KeesonProfile(
    key="sino",
    order="big",
    hold=(10, 100),
    three_motor_hold=(5, 200),
    presets=_TV_UNLISTED,
    unlisted_presets=frozenset({"tv"}),
    memory=_GENERIC_MEMORY,
    memory_slots=4,
    lights="discrete",
    massage="absolute",
    keeson_motor_names=False,
)
# BetterLiving BED_DEFAULT (com.betterliving.bed) presets on the Sino frame.
BETTERLIVING: Final = replace(
    SINO,
    key="betterliving",
    presets={
        "flat": 0x01000002,
        "zero_g": 0x01000001,
        "anti_snore": 0x01000004,
        "tv": K.PRESET_TV,
    },
    memory={1: 0x01000008, 2: 0x01000009},
    memory_slots=2,
    memory_save=MemorySave(words={1: 0x20000008, 2: 0x20000009}),
)
JSON: Final = KeesonProfile(
    key="json",
    carrier="json",
    transport="json",
    notify="json",
    hold=(10, 100),
    presets=_KSBT_PRESETS,
    memory=_GENERIC_MEMORY,
    memory_slots=4,
    keeson_motor_names=False,
)
# Direct P2 remotes stop by ending the refresh; the SFD apps then poll status three times.
KSBT: Final = KeesonProfile(
    key="ksbt",
    carrier="p2",
    transport="ksbt",
    hold=(10, 100),
    release=Release(steps=((300, codec.STATUS_QUERY),) * 3, on_stop=False),
    presets=_KSBT_PRESETS,
    memory=_KSBT_MEMORY,
    memory_slots=3,
)
# Ergomotion Sync: KSBT03C boxes have no tilt motor and no release write.
KSBT03C: Final = replace(
    KSBT, key="ksbt03c", hold=(4, 300), release=Release(steps=()), no_response=True, tilt=False
)
KSBT_CR: Final = KeesonProfile(
    key="ksbt_cr",
    carrier="p2_side",
    transport="ksbt",
    hold=(4, 300),
    presets=_KSBT_PRESETS,
    memory=_GENERIC_MEMORY,
    memory_slots=2,
)
KSBT04C: Final = KeesonProfile(
    key="ksbt04c",
    carrier="p2_checked",
    transport="ksbt",
    hold=(4, 300),
    presets=_KSBT_PRESETS,
    memory=_KSBT_MEMORY,
    memory_slots=3,
    lights=None,
)
# Sleep Harmony (com.keeson.ssbaudio) labels Reading/TV/Snore as M1/M2/M3.
SLEEP_HARMONY: Final = replace(
    KSBT04C,
    key="sleep_harmony",
    release=Release(steps=((200, codec.RELEASE),), after_tap=True),
    memory={1: K.PRESET_MEMORY_1, 2: K.PRESET_MEMORY_2, 3: K.PRESET_MEMORY_3},
    massage_off=K.MASSAGE_ALL_STOP,
)
SLEEP_HARMONY_BASE_I5: Final = replace(
    SLEEP_HARMONY, key="sleep_harmony_base_i5", carrier="k1", header=0xE6, side=0, transport="base"
)
_PURPLE_RELEASE: Final = Release(steps=((0, codec.p2(codec.RELEASE, "p2_padded")),), after_tap=True)
PURPLE: Final = KeesonProfile(
    key="purple",
    hold=(10, 100),
    release=_PURPLE_RELEASE,
    presets={**_BASE_PRESETS, "lounge": K.PRESET_LOUNGE, "anti_snore": K.PRESET_ANTI_SNORE},
    memory={1: K.PRESET_MEMORY_4, 2: K.PRESET_MEMORY_2},
    memory_slots=2,
    memory_save=MemorySave(
        words={1: K.PRESET_MEMORY_4, 2: K.PRESET_MEMORY_2},
        repeats=26,
        repeat_ms=200,
        wait_first=True,
    ),
    lights_listed=False,
)
_PURPLE_PLUS_MEMORY: Final[Mapping[int, int]] = {
    1: K.PRESET_MEMORY_4,
    2: K.PRESET_MEMORY_1,
    3: K.PRESET_MEMORY_2,
}
PURPLE_PLUS: Final = replace(
    PURPLE,
    key="purple_plus",
    carrier="p2_padded",
    transport="ksbt",
    presets={**_BASE_PRESETS, "anti_snore": K.PRESET_ANTI_SNORE},
    memory=_PURPLE_PLUS_MEMORY,
    memory_slots=3,
    memory_save=MemorySave(words=_PURPLE_PLUS_MEMORY, repeats=26, repeat_ms=200, wait_first=True),
    lights_listed=True,
)
# Adjustable Lite 1.0.2 (com.keeson.adjustablelite): MI/MII/MIII labels; release only
# cancels the 300 ms refresh; both remotes poll 00 B0 every 500 ms.
ADJUSTABLE_LITE: Final = KeesonProfile(
    key="adjustable_lite",
    carrier="p2",
    transport="ksbt",
    notify="ksbt",
    fixed_write=True,
    no_response=True,
    hold=(4, 300),
    release=Release(steps=()),
    presets={**_BASE_PRESETS},
    memory={1: K.PRESET_MEMORY_4, 2: K.PRESET_MEMORY_1, 3: K.PRESET_MEMORY_2},
    memory_slots=3,
    massage="none",
    tilt=False,
    lumbar=False,
    status_poll_ms=500,
)
ADJUSTABLE_LITE_KSBT03C: Final = replace(
    ADJUSTABLE_LITE,
    key="adjustable_lite_ksbt03c",
    presets={**_BASE_PRESETS, "anti_snore": K.PRESET_ANTI_SNORE},
    massage="zone_steps",
    status_timer=True,
)
# Restonic BT Remote 1.2.0 (com.keeson.restonicBT): holds refresh every 100 ms; touch-up
# writes one zero frame 100 ms later. Remote A holds Zero G; remote B taps it, and adds
# the combined back glyphs, the bulb and ZZZ (whose effect the app does not prove).
_RESTONIC_COMMON: Final[dict[str, tuple[int, bool]]] = {
    "head_up": (K.MOTOR_HEAD_UP, True),
    "head_down": (K.MOTOR_HEAD_DOWN, True),
    "feet_up": (K.MOTOR_FEET_UP, True),
    "feet_down": (K.MOTOR_FEET_DOWN, True),
    "flat": (K.PRESET_FLAT, False),
}
RESTONIC_A_CONTROLS: Final[Mapping[str, tuple[int, bool]]] = MappingProxyType(
    {**_RESTONIC_COMMON, "zero_g": (K.PRESET_ZERO_G, True)}
)
RESTONIC_B_CONTROLS: Final[Mapping[str, tuple[int, bool]]] = MappingProxyType(
    {
        **_RESTONIC_COMMON,
        "back_legs_up": (K.MOTOR_HEAD_UP | K.MOTOR_FEET_UP, True),
        "back_legs_down": (K.MOTOR_HEAD_DOWN | K.MOTOR_FEET_DOWN, True),
        "zero_g": (K.PRESET_ZERO_G, False),
        "light": (K.TOGGLE_SAFETY_LIGHTS, False),
        "zzz": (K.PRESET_ANTI_SNORE, False),
    }
)
RESTONIC_A: Final = KeesonProfile(
    key="restonic_a",
    fixed_write=True,
    no_response=True,
    hold=(10, 100),
    release=Release(steps=((100, codec.RELEASE),), after_tap=True, guarded=True),
    presets={**_BASE_PRESETS},
    lights=None,
    massage="none",
    tilt=False,
    lumbar=False,
    held_controls=RESTONIC_A_CONTROLS,
)
RESTONIC_B: Final = replace(
    RESTONIC_A, key="restonic_b", lights="toggle", held_controls=RESTONIC_B_CONTROLS
)
# INNOVA 2.0 (com.ore.sfm): holds every 100 ms, touch-up zero key 100 ms later, and
# sendSingleMessage sleeps 100 ms before every one-shot write. Keys live in beds/innova.py.
INNOVA: Final = KeesonProfile(
    key="innova",
    fixed_write=True,
    hold=(10, 100),
    refresh_ms=100,
    release=Release(steps=((100, codec.RELEASE),), guarded=True),
    tap_wait_ms=100,
    presets={**_BASE_PRESETS},
    # Memory A/B stream while held.
    memory={1: K.PRESET_MEMORY_1, 2: K.PRESET_MEMORY_2},
    memory_slots=2,
)
# Okin apps (beds/keeson_okin_apps.py): big-endian E5 frames, holds every 100 ms.
SIMON_LI: Final = KeesonProfile(
    key="simon_li",
    order="big",
    fixed_write=True,
    hold=None,
    refresh_ms=100,
    release=Release(steps=((10, codec.RELEASE),), guarded=True),
)
OKIN_SEATING: Final = KeesonProfile(
    key="okin_seating",
    order="big",
    fixed_write=True,
    hold=None,
    refresh_ms=100,
    release=Release(steps=((10, codec.RELEASE),), guarded=True),
)
HEAL_EVERY_NIGHT: Final = KeesonProfile(
    key="heal_every_night",
    order="big",
    fixed_write=True,
    hold=None,
    refresh_ms=100,
    release=Release(steps=((100, codec.RELEASE),), guarded=True),
)
# ORE comfort-bed apps (beds/ore_comfort_bed.py). Each accepted report independently
# proves the same frames and timing: holds every 100 ms after each write, and a
# 100 ms sleep before every one-shot write, the zero word included.
_ORE: Final = KeesonProfile(
    key="ore",
    order="big",
    fixed_write=True,
    hold=None,
    refresh_ms=100,
    release=Release(steps=((100, codec.RELEASE),)),
    tap_wait_ms=100,
)
AMERICANSTAR: Final = replace(_ORE, key="americanstar")
AVANTI_BASES: Final = replace(_ORE, key="avanti_bases")
BEDSENSE_BASES: Final = replace(_ORE, key="bedsense_bases")
DYNASTY_BASES: Final = replace(_ORE, key="dynasty_bases")
MAXCOIL_UNA: Final = replace(_ORE, key="maxcoil_una")
# Bed types whose controllers keep their key tables, sessions and timing, over the
# nine-byte E6 frame. Only the frame is profile data here.
_E6: Final = KeesonProfile(key="e6", header=0xE6, side=0, hold=None)
GLIDEAWAY_MOTION: Final = replace(_E6, key="glideaway_motion")  # row068
MALOUF_LEGACY_OKIN: Final = replace(_E6, key="malouf_legacy_okin")
SLEEPYS_BOX15: Final = replace(_E6, key="sleepys_box15")
SCOTT_LIVING: Final = replace(_E6, key="scott_living", side=1)
# AdjustaMattress (row067): model P1 sends E6 frames, P2 big-endian E5 frames.
ADJUSTAMATTRESS: Final = replace(_E6, key="adjustamattress")
ADJUSTAMATTRESS_P2: Final = KeesonProfile(key="adjustamattress_p2", order="big", hold=None)
# Split-bed A/B selection of the SBI/Q-Plus and Rondure apps: Both is the E5 frame.
_AB_SIDES: Final[Mapping[str, int]] = MappingProxyType({"side_a": 0x01, "side_b": 0x02})
SBI: Final = KeesonProfile(key="sbi", hold=None, split_sides=_AB_SIDES)
RONDURE: Final = KeesonProfile(key="rondure", hold=None, split_sides=_AB_SIDES)
COOLBASE: Final = KeesonProfile(key="coolbase", hold=None)  # com.keeson.coolbase 1.0.0
# BF and Cherish (beds/bf_cherish.py), Comfort Enhancements: big-endian E5 frames.
BF: Final = KeesonProfile(key="bf", order="big", hold=None)
CHERISH: Final = KeesonProfile(key="cherish", order="big", hold=None)
COMFORT_ENHANCEMENTS: Final = KeesonProfile(key="comfort_enhancements", order="big", hold=None)

PROFILES: Final[dict[str, KeesonProfile]] = {
    profile.key: profile
    for profile in (
        BASE,
        ERGOMOTION,
        SERTA,
        OKIN,
        CB1322,
        SINO,
        BETTERLIVING,
        JSON,
        KSBT,
        KSBT03C,
        KSBT_CR,
        KSBT04C,
        SLEEP_HARMONY,
        SLEEP_HARMONY_BASE_I5,
        PURPLE,
        PURPLE_PLUS,
        ADJUSTABLE_LITE,
        ADJUSTABLE_LITE_KSBT03C,
        RESTONIC_A,
        RESTONIC_B,
        INNOVA,
        SIMON_LI,
        OKIN_SEATING,
        HEAL_EVERY_NIGHT,
        AMERICANSTAR,
        AVANTI_BASES,
        BEDSENSE_BASES,
        DYNASTY_BASES,
        MAXCOIL_UNA,
        GLIDEAWAY_MOTION,
        MALOUF_LEGACY_OKIN,
        SLEEPYS_BOX15,
        SCOTT_LIVING,
        ADJUSTAMATTRESS,
        ADJUSTAMATTRESS_P2,
        SBI,
        RONDURE,
        COOLBASE,
        BF,
        CHERISH,
        COMFORT_ENHANCEMENTS,
    )
}


# Cluster033 apps (beds/cluster033.py): the Tempur Curve, Q-Plus, Serta MP Remote,
# Omazz, Ergomotion, ROW Control, Ergo Slim and TEMPUR AU apps, chosen by hand with
# a layout. Each accepted report proves its own key table; repeated masks are
# separate package receipts, not inferred family equivalence.


@dataclass(frozen=True, slots=True)
class AppAction:
    key: str
    name: str
    mask: int
    mode: Literal["held", "single", "pulse", "held_zeros", "tap_zeros"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AppProfile:
    """One cluster033 app layout over the K1 frame (P2 for Q-Plus MX)."""

    key: str
    """The app's bed type; it names the frozen vectors and the app's caller rules."""
    app: str
    layout: str
    actions: tuple[AppAction, ...]
    alarm: AlarmTableScheduleSpec | None
    p2_keys: frozenset[int] | None = None
    """Keys the layout's private P2 builder accepts; any other key is sent as zero."""
    rename_units: int = 14
    """UTF-16 units the rename caller accepts; 0 when the app has no name writer."""
    rename_trimmed: bool = True
    """The rename caller applies Java ``String.trim``; otherwise outer spaces are rejected."""
    clock: bool = True
    clock_init_delay_ms: int | None = None
    shutdown_count: int = 0
    shutdown_delay_ms: int = 400


APP_LAYOUTS: Final[dict[str, tuple[str, ...]]] = {
    "tempur_curve": ("standard",),
    "qplus_app": ("H", "M1", "M2", "M3", "MX"),
    "serta_mp_remote": ("standard",),
    "omazz_adjusto_iii": ("RemoteB",),
    "ergomotion_app": ("B1", "B2", "C1", "D1"),
    "row_control": ("Elevate", "Lifestyle", "Curve", "Lifestyle Plus", "Zero-G Box"),
    "ergo_slim": ("A", "B", "C"),
    "tempur_au": ("B1", "B2", "C1", "D1", "E1"),
}
DEFAULT_LAYOUTS: Final[dict[str, str]] = {
    "tempur_curve": "standard",
    "qplus_app": "M2",
    "serta_mp_remote": "standard",
    "omazz_adjusto_iii": "RemoteB",
    "ergomotion_app": "B2",
    "row_control": "Elevate",
    "ergo_slim": "A",
    "tempur_au": "B2",
}
APP_NAMES: Final[dict[str, str]] = {
    "tempur_curve": "Tempur Curve",
    "qplus_app": "Q-Plus Adjustable Remote",
    "serta_mp_remote": "Serta MP Remote",
    "omazz_adjusto_iii": "Omazz Adjusto III",
    "ergomotion_app": "Ergomotion",
    "row_control": "ROW Control",
    "ergo_slim": "Ergo Slim",
    "tempur_au": "TEMPUR AU",
}

_ACTIONS: Final[dict[tuple[str, str], tuple[AppAction, ...]]] = {
    ("tempur_curve", "standard"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("massage_timer", "Massage Timer", 0x200, "pulse"),
        AppAction("massage_foot_add", "Massage Foot Add", 0x400, "pulse"),
        AppAction("massage_head_add", "Massage Head Add", 0x800, "pulse"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("tv_III", "Tv Iii", 0x4000, "held"),
        AppAction("anti_snore_I", "Anti Snore I", 0x8000, "held"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
        AppAction("lounge_II", "Lounge Ii", 0x2000, "held"),
    ),
    ("omazz_adjusto_iii", "RemoteB"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("demonstration", "Demonstration", 0x40000000, "held"),
        AppAction("TV", "Tv", 0x4000, "held"),
        AppAction("music", "Music", 0x10000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("zg", "Zg", 0x1000, "single"),
        AppAction("ubb", "Ubb", 0x20000, "single"),
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_timer", "Massage Timer", 0x200, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
        AppAction("massage_all", "Massage All", 0x100, "pulse"),
    ),
    ("ergomotion_app", "B1"): (
        AppAction("head_up", "HeadUp", 0x1, "held"),
        AppAction("head_down", "HeadDown", 0x2, "held"),
        AppAction("foot_up", "FootUp", 0x4, "held"),
        AppAction("foot_down", "FootDown", 0x8, "held"),
        AppAction("flat", "Flat", 0x8000000, "tap_zeros"),
        AppAction("timer", "Timer", 0x200, "tap_zeros"),
        AppAction("zg", "Zg", 0x1000, "tap_zeros"),
        AppAction("masheadadd", "MasHeadAdd", 0x800, "tap_zeros"),
        AppAction("masfootadd", "MasFootAdd", 0x400, "tap_zeros"),
        AppAction("reset", "Reset", 0x8001000, "held_zeros"),
        AppAction("level", "Level", 0x100, "tap_zeros"),
        AppAction("lounge", "Lounge", 0x2000, "held_zeros"),
        AppAction("tv", "Tv", 0x4000, "held_zeros"),
    ),
    ("ergomotion_app", "B2"): (
        AppAction("head_up", "HeadUp", 0x1, "held"),
        AppAction("head_down", "HeadDown", 0x2, "held"),
        AppAction("foot_up", "FootUp", 0x4, "held"),
        AppAction("foot_down", "FootDown", 0x8, "held"),
        AppAction("flat", "Flat", 0x8000000, "tap_zeros"),
        AppAction("timer", "Timer", 0x200, "tap_zeros"),
        AppAction("zg", "Zg", 0x1000, "tap_zeros"),
        AppAction("masheadadd", "MasHeadAdd", 0x800, "tap_zeros"),
        AppAction("masfootadd", "MasFootAdd", 0x400, "tap_zeros"),
        AppAction("reset", "Reset", 0x8001000, "held_zeros"),
        AppAction("level1", "Level1", 0x80000, "tap_zeros"),
        AppAction("level2", "Level2", 0x100000, "tap_zeros"),
        AppAction("level3", "Level3", 0x200000, "tap_zeros"),
    ),
    ("ergomotion_app", "C1"): (
        AppAction("head_up", "HeadUp", 0x1, "held"),
        AppAction("head_down", "HeadDown", 0x2, "held"),
        AppAction("foot_up", "FootUp", 0x4, "held"),
        AppAction("foot_down", "FootDown", 0x8, "held"),
        AppAction("flat", "Flat", 0x8000000, "tap_zeros"),
        AppAction("timer", "Timer", 0x200, "tap_zeros"),
        AppAction("zg", "Zg", 0x1000, "tap_zeros"),
        AppAction("masheadadd", "MasHeadAdd", 0x800, "tap_zeros"),
        AppAction("masfootadd", "MasFootAdd", 0x400, "tap_zeros"),
        AppAction("reset", "Reset", 0x8001000, "held_zeros"),
        AppAction("level", "Level", 0x100, "tap_zeros"),
        AppAction("lounge", "Lounge", 0x2000, "held_zeros"),
        AppAction("tv", "Tv", 0x4000, "held_zeros"),
        AppAction("light", "Light", 0x20000, "tap_zeros"),
        AppAction("masfootmin", "MasFootMin", 0x1000000, "tap_zeros"),
        AppAction("masheadmin", "MasHeadMin", 0x800000, "tap_zeros"),
    ),
    ("ergomotion_app", "D1"): (
        AppAction("head_up", "HeadUp", 0x1, "held"),
        AppAction("head_down", "HeadDown", 0x2, "held"),
        AppAction("foot_up", "FootUp", 0x4, "held"),
        AppAction("foot_down", "FootDown", 0x8, "held"),
        AppAction("flat", "Flat", 0x8000000, "tap_zeros"),
        AppAction("timer", "Timer", 0x200, "tap_zeros"),
        AppAction("zg", "Zg", 0x1000, "tap_zeros"),
        AppAction("masheadadd", "MasHeadAdd", 0x800, "tap_zeros"),
        AppAction("masfootadd", "MasFootAdd", 0x400, "tap_zeros"),
        AppAction("reset", "Reset", 0x8001000, "held_zeros"),
        AppAction("level", "Level", 0x100, "tap_zeros"),
        AppAction("lounge", "Lounge", 0x2000, "held_zeros"),
        AppAction("tv", "Tv", 0x4000, "held_zeros"),
        AppAction("light", "Light", 0x20000, "tap_zeros"),
        AppAction("masfootmin", "MasFootMin", 0x1000000, "tap_zeros"),
        AppAction("masheadmin", "MasHeadMin", 0x800000, "tap_zeros"),
        AppAction("tiltup", "TiltUp", 0x10, "held_zeros"),
        AppAction("tiltdown", "TiltDown", 0x20, "held_zeros"),
        AppAction("lumbarup", "LumbarUp", 0x40, "held_zeros"),
        AppAction("lumbardown", "LumbarDown", 0x80, "held_zeros"),
    ),
    ("ergo_slim", "A"): (
        AppAction("reset", "Reset", 0x8001000, "held"),
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("massage_head_min", "Massage Head Min", 0x800000, "pulse"),
        AppAction("massage_foot_min", "Massage Foot Min", 0x1000000, "pulse"),
        AppAction("level", "Level", 0x2000000, "single"),
        AppAction("zero_gravity", "Zero Gravity", 0x1000, "single"),
        AppAction("flat", "Flat", 0x8000000, "pulse"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("light", "Light", 0x20000, "single"),
    ),
    ("ergo_slim", "B"): (
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_timer", "Massage Timer", 0x200, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
        AppAction("ubb", "Ubb", 0x20000, "single"),
        AppAction("massage_all", "Massage All", 0x100, "pulse"),
        AppAction("music", "Music", 0x10000, "held"),
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("flat", "Flat", 0x8000000, "pulse"),
        AppAction("anti_snore", "Anti Snore", 0x8000, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("zero_gravity", "Zero Gravity", 0x1000, "single"),
    ),
    ("ergo_slim", "C"): (
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_timer", "Massage Timer", 0x200, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
        AppAction("m3_out", "M3 Out", 0x10, "held"),
        AppAction("ubb", "Ubb", 0x20000, "single"),
        AppAction("m3_in", "M3 In", 0x20, "held"),
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("zero_gravity", "Zero Gravity", 0x1000, "single"),
        AppAction("memory_4", "Memory 4", 0x8000, "held"),
        AppAction("memory_2", "Memory 2", 0x2000, "held"),
        AppAction("memory_3", "Memory 3", 0x4000, "held"),
        AppAction("flat", "Flat", 0x8000000, "pulse"),
    ),
    ("tempur_au", "B1"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_foot_add", "Massage Foot Add", 0x400, "pulse"),
        AppAction("massage_head_add", "Massage Head Add", 0x800, "pulse"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
    ),
    ("tempur_au", "B2"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_foot_add", "Massage Foot Add", 0x400, "pulse"),
        AppAction("massage_head_add", "Massage Head Add", 0x800, "pulse"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("memory_level_1", "Memory Level 1", 0x80000, "single"),
        AppAction("memory_level_2", "Memory Level 2", 0x100000, "single"),
        AppAction("memory_level_3", "Memory Level 3", 0x200000, "single"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
    ),
    ("tempur_au", "C1"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_foot_add", "Massage Foot Add", 0x400, "pulse"),
        AppAction("massage_head_add", "Massage Head Add", 0x800, "pulse"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("massage_head_decrease", "Massage Head Decrease", 0x800000, "pulse"),
        AppAction("massage_foot_decrease", "Massage Foot Decrease", 0x1000000, "pulse"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
    ),
    ("tempur_au", "D1"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("tilt_up", "Tilt Up", 0x10, "held"),
        AppAction("tilt_down", "Tilt Down", 0x20, "held"),
        AppAction("lumbar_up", "Lumbar Up", 0x40, "held"),
        AppAction("lumbar_down", "Lumbar Down", 0x80, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_foot_add", "Massage Foot Add", 0x400, "pulse"),
        AppAction("massage_head_add", "Massage Head Add", 0x800, "pulse"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("massage_head_decrease", "Massage Head Decrease", 0x800000, "pulse"),
        AppAction("massage_foot_decrease", "Massage Foot Decrease", 0x1000000, "pulse"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
    ),
    ("tempur_au", "E1"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("lumbar_up", "Lumbar Up", 0x40, "held"),
        AppAction("lumbar_down", "Lumbar Down", 0x80, "held"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_foot_add", "Massage Foot Add", 0x400, "pulse"),
        AppAction("massage_head_add", "Massage Head Add", 0x800, "pulse"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("anti_snooze", "Anti Snooze", 0x8000, "single"),
        AppAction("music", "Music", 0x10000, "single"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
    ),
    ("row_control", "Elevate"): (
        AppAction("reset", "Reset", 0x08001000, "held"),
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("anti_snore", "Anti Snore", 0x8000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
    ),
    ("row_control", "Lifestyle"): (
        AppAction("reset", "Reset", 0x08001000, "held"),
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("anti_snore", "Anti Snore", 0x8000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
    ),
    ("row_control", "Curve"): (
        AppAction("reset", "Reset", 0x08001000, "held"),
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("anti_snore", "Anti Snore", 0x8000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
    ),
    ("row_control", "Lifestyle Plus"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("anti_snore", "Anti Snore", 0x8000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("lounge", "Lounge", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_head", "Massage Head", 0x800, "pulse"),
        AppAction("massage_foot", "Massage Foot", 0x400, "pulse"),
    ),
    ("row_control", "Zero-G Box"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("anti_snore", "Anti Snore", 0x8000, "held"),
        AppAction("tv", "Tv", 0x4000, "held"),
        AppAction("lounge", "Lounge", 0x10000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("zero_g", "Zero G", 0x1000, "single"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("timer", "Timer", 0x200, "pulse"),
        AppAction("massage_head", "Massage Head", 0x50, "held"),
        AppAction("massage_foot", "Massage Foot", 0xA0, "held"),
    ),
    ("qplus_app", "H"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("tilt_up", "Tilt Up", 0x10, "held"),
        AppAction("tilt_down", "Tilt Down", 0x20, "held"),
        AppAction("lumbar_up", "Lumbar Up", 0x40, "held"),
        AppAction("lumbar_down", "Lumbar Down", 0x80, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("zero_g", "Zero_G", 0x1000, "single"),
        AppAction("read", "Read", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
        AppAction("massage_head", "Massage Head", 0x800, "single"),
        AppAction("massage_foot", "Massage Foot", 0x400, "single"),
        AppAction("music", "Music", 0x4000, "held"),
        AppAction("tv", "TV", 0x8000, "held"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("lumbar_massage", "Lumbar Massage", 0x400000, "single"),
        AppAction("massage_mode_3", "Massage Mode 3", 0x80000, "single"),
        AppAction("massage_mode_1", "Massage Mode 1", 0x100000, "single"),
        AppAction("massage_mode_2", "Massage Mode 2", 0x200000, "single"),
    ),
    ("qplus_app", "M1"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("zero_g", "Zero_G", 0x1000, "single"),
        AppAction("read", "Read", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
        AppAction("massage_head", "Massage Head", 0x800, "single"),
        AppAction("massage_foot", "Massage Foot", 0x400, "single"),
        AppAction("music", "Music", 0x4000, "held"),
        AppAction("tv", "TV", 0x8000, "held"),
        AppAction("light", "Light", 0x20000, "single"),
        AppAction("lumbar_massage", "Lumbar Massage", 0x400000, "single"),
    ),
    ("qplus_app", "M2"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("tilt_up", "Tilt Up", 0x10, "held"),
        AppAction("tilt_down", "Tilt Down", 0x20, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("zero_g", "Zero_G", 0x1000, "single"),
        AppAction("read", "Read", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
        AppAction("massage_head", "Massage Head", 0x800, "single"),
        AppAction("massage_foot", "Massage Foot", 0x400, "single"),
        AppAction("tv", "TV", 0x4000, "held"),
        AppAction("anti_snore", "Anti-snore", 0x8000, "single"),
    ),
    ("qplus_app", "M3"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("level", "Level", 0x100, "single"),
        AppAction("zero_g", "Zero_G", 0x1000, "single"),
        AppAction("read", "Read", 0x2000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("reset", "Reset", 0x8001000, "held"),
    ),
    ("qplus_app", "MX"): (
        AppAction("head_up", "Head Up", 0x1, "held"),
        AppAction("head_down", "Head Down", 0x2, "held"),
        AppAction("foot_up", "Foot Up", 0x4, "held"),
        AppAction("foot_down", "Foot Down", 0x8, "held"),
        AppAction("tilt_up", "Tilt Up", 0x10, "held"),
        AppAction("tilt_down", "Tilt Down", 0x20, "held"),
        AppAction("anti_snore", "Anti-snore", 0x8000, "held"),
        AppAction("mx_memory1", "MX Memory 1", 0x10000, "held"),
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("light", "Light", 0x4000, "single"),
        AppAction("massage_head", "Massage head", 0x800, "pulse"),
        AppAction("massage_foot", "Massage foot", 0x400, "pulse"),
        AppAction("massage_timer", "Massage timer", 0x200, "pulse"),
    ),
    ("serta_mp_remote", "standard"): (
        AppAction("flat", "Flat", 0x8000000, "single"),
        AppAction("foot_down", "Foot down", 0x8, "held"),
        AppAction("foot_up", "Foot up", 0x4, "held"),
        AppAction("head_down", "Head down", 0x2, "held"),
        AppAction("head_up", "Head up", 0x1, "held"),
        AppAction("level", "Massage pattern icon (btnLevel)", 0x100, "single"),
        AppAction("lounge", "Lounge preset icon", 0x2000, "held"),
        AppAction("lumbardown", "Lumbar down (unlabeled touch area)", 0x80, "held"),
        AppAction("lumbarup", "Lumbar up (unlabeled touch area)", 0x40, "held"),
        AppAction("m4", "Preset M4 icon (distinct from local memory slot 4)", 0x8000, "single"),
        AppAction("masfootadd", "Foot massage increase", 0x400, "single"),
        AppAction("masfootmin", "Foot massage decrease", 0x1000000, "single"),
        AppAction("masheadadd", "Head massage increase", 0x800, "single"),
        AppAction("masheadmin", "Head massage decrease", 0x800000, "single"),
        AppAction("reset", "RESET-labeled remote action", 0x8001000, "held"),
        AppAction("tiltdown", "Tilt down (unlabeled touch area)", 0x20, "held"),
        AppAction("tiltup", "Tilt up (unlabeled touch area)", 0x10, "held"),
        AppAction("timer", "Massage TIMER / ALL OFF", 0x200, "single"),
        AppAction("tv", "TV preset icon", 0x4000, "held"),
        AppAction("zg", "ZERO-G preset", 0x1000, "single"),
    ),
}
# Q-Plus MX's sparse P2 builder.
_MX_KEYS: Final = frozenset(
    {
        *(1 << bit for bit in range(6)),
        0x200,
        0x400,
        0x800,
        0x2000,
        0x4000,
        0x8000,
        0x10000,
        0x20000,
        0x800000,
        0x1000000,
        0x2000000,
        0x4000000,
        0x8000000,
        0x40000000,
    }
)


# Ergomotion 4.0 (com.sfd.hump 3.7). Its product catalog
# (``ergomotion4_profiles.py``) supplies the actions, so the layout only names
# the selected product's style.
ERGOMOTION_4: Final = "ergomotion_4"


def ergomotion_4_profile(style: str) -> AppProfile:
    """The Ergomotion 4.0 app profile for one catalog product style."""
    return AppProfile(
        key=ERGOMOTION_4,
        app="Ergomotion 4.0",
        layout=style,
        actions=(),
        alarm=AlarmTableScheduleSpec(128, 3),
        shutdown_count=1,
        shutdown_delay_ms=0,
    )


def app_profile(app: str, layout: str | None = None) -> AppProfile:
    """Validate a manual app/layout choice without advertisement inference."""
    layout = layout or DEFAULT_LAYOUTS[app]
    if layout not in APP_LAYOUTS[app]:
        raise ValueError(f"Unknown {APP_NAMES[app]} layout: {layout}")
    alarm = (
        None
        if app == "serta_mp_remote"
        else AlarmTableScheduleSpec(
            0 if app in ("omazz_adjusto_iii", "ergomotion_app") else 128,
            16 if app == "qplus_app" else 3,
        )
    )
    return AppProfile(
        key=app,
        app=APP_NAMES[app],
        layout=layout,
        actions=_ACTIONS[app, layout],
        alarm=alarm,
        p2_keys=_MX_KEYS if (app, layout) == ("qplus_app", "MX") else None,
        rename_units=0
        if app == "omazz_adjusto_iii"
        else 15
        if app in ("row_control", "ergomotion_app")
        else 14,
        rename_trimmed=app != "qplus_app",
        clock=app not in ("serta_mp_remote", "qplus_app"),
        clock_init_delay_ms=2000
        if app in ("tempur_curve", "row_control", "tempur_au")
        else 0
        if app == "ergo_slim"
        else None,
        shutdown_count=4
        if app in ("qplus_app", "ergo_slim")
        else 2
        if app in ("tempur_curve", "row_control", "tempur_au")
        else 0,
        shutdown_delay_ms=200 if app in ("qplus_app", "ergo_slim") else 400,
    )


SERTA_MEMORY_KEYS: Final = frozenset(
    f"serta_mp_memory_{slot}_{axis}" for slot in range(1, 5) for axis in ("head", "foot")
)


def is_ksbt03c_name(name: str | None) -> bool:
    """KSBT03C boxes (for example Ergomotion RIO 5.0); KSBT03CR is a different box."""
    normalized = (name or "").strip().lower()
    return normalized.startswith("ksbt03c") and not normalized.startswith("ksbt03cr")


def resolve(
    variant: str,
    device_name: str | None,
    *,
    ksbt_service: bool = False,
    betterliving: bool = False,
    cb1322: bool = False,
) -> KeesonProfile:
    """Return the profile a variant selects for this device name and GATT layout."""
    name = (device_name or "").strip().lower()
    if variant == "ksbt" and is_ksbt03c_name(device_name):
        return KSBT03C
    if variant == "sleep_harmony" and name.startswith("base-i5."):
        return SLEEP_HARMONY_BASE_I5
    if variant == "purple" and (name.startswith("ksbt04c") or ksbt_service):
        return PURPLE_PLUS
    # Adjustable Lite shows its KSBT03C remote on this case-sensitive token.
    if variant == "adjustable_lite" and "KSBT03C" in (device_name or ""):
        return ADJUSTABLE_LITE_KSBT03C
    if variant == "sino" and betterliving:
        return BETTERLIVING
    if variant == "okin" and cb1322:
        return CB1322
    return PROFILES.get(variant, BASE)


def encode(
    profile: KeesonProfile, word: int, device_id: str = "unknown", *, side: Side | None = None
) -> bytes:
    """Encode one word in the profile's carrier; JSON zero words release (``ctrm`` 0).

    ``side`` selects one half of a split base and needs a ``single_side`` profile.
    """
    if side is not None:
        if not profile.single_side:
            raise ValueError("This Keeson profile has no proven single-side frame")
        return codec.side_frame(word, side)
    if profile.carrier == "k1":
        return codec.frame(word, header=profile.header, order=profile.order, side=profile.side)
    if profile.carrier == "json":
        return codec.json_command(word, device_id, ctrm=int(word != 0), km=1, keykt=0)
    return codec.p2(word, profile.carrier)
