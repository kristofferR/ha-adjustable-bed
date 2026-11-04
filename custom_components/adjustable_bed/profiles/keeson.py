"""Profiles over the Keeson codec.

Each ``keeson`` protocol variant is a profile here, and so are the routes a
device name or service resolves inside a variant (KSBT03C, Purple Premium Plus,
Sleep Harmony base-i5, the Adjustable Lite KSBT03C remote, and the BetterLiving
and CB1322 auto-detected tables). The ``ergomotion``, ``serta`` and ``okin_ffe``
bed types are aliases of the variant profiles of the same name.

App profiles take their words and timing from their accepted APK Protocol Audit
reports; the other routes keep the frames and timing of the pre-v5 controller.
Timing is per profile and never shared.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final, Literal

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
_PURPLE_RELEASE: Final = Release(
    steps=((0, codec.p2(codec.RELEASE, "p2_padded")),), after_tap=True
)
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
    )
}


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
