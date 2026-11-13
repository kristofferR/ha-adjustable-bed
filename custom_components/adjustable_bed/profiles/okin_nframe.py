"""Profiles over the Okin N-frame codec.

32-bit: ``OKIMAT`` serves ``okimat`` and ``okin_uuid``, whose keys come from the
selected handset's remote table. ``DEWERTOKIN`` serves ``dewertokin`` and
``okin_handle``, and ``RF_ECO_BT`` the ``okin_rf_eco_bt`` stair lift.
``CUSTOMATIC_PROFILES`` are the Customatic Clarity, Jerome's and Remedy 1.0.1
apps. ``LEGGETT_PROFILES`` are Prodigy 2L 1.2, Prodigy 2 2.2.0, Prodigy CE 1.2.0
and U Series 2.1, chosen by the ``leggett_okin`` entry's app profile.

40-bit: ``OKIN_DOT`` (DOT handset tables), ``OKIN_CB24``, ``SIMMONS_PROFILES``
(chosen by the Bluetooth name), ``DOUBLESLEEP``, ``SLEEPYS_BOX25_LEGACY``,
``STARCODE_ABM5_4_PROFILES`` (one per command selector) and ``ESHINE_PROFILES``
(the eShine app's product selectors).

App profiles come from their accepted APK Protocol Audit report; Okimat,
DewertOkin, RF ECO BT, CB24, DOT, Sleepy's legacy CB25 and AdjustableM5X4 keep
the pre-v5 controllers' frames.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Final, Literal, TypedDict

from ..const import (
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_ESHINE_OKIN,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_DOT,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_MOTIONBED,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_RESIDENT,
    BED_TYPE_RIZE_REMEDY_II,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_TRANQUIL,
    BED_TYPE_ZSERIES,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CB24_BED_SELECTION_DEFAULT,
    OKIN_CST_VARIANT_AVIADA,
    OKIN_CST_VARIANT_BOB,
    OKIN_CST_VARIANT_CAREFREE,
    OKIN_CST_VARIANT_CLARITY,
    OKIN_CST_VARIANT_CONTEMPO,
    OKIN_CST_VARIANT_MF900,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    OKIN_CST_VARIANT_RESIDENT,
    OKIN_CST_VARIANT_SANCTUARY,
    OKIN_CST_VARIANT_SUPPORT,
)
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities

WriteMode = Literal["response", "no_response", "characteristic"]
Envelope = Literal["plain", "gateway", "gateway_detected", "revision_selector", "keeson_e6"]


@dataclass(frozen=True, kw_only=True)
class Hold:
    """Held movement: refresh one frame, then release with STOP frames."""

    repeat_ms: int | None
    """Refresh interval; ``None`` follows the entry's motor pulse delay."""
    repeats: int | None = None
    """Fixed refresh count; ``None`` follows the entry's motor pulse count."""
    releases: int
    """STOP frames after the hold; 0 ends it by ending the refresh."""
    release_ms: int = 0
    """Spacing between STOP frames."""
    release_after_ms: int = 0
    """Wait between the last refresh and the first STOP."""


@dataclass(frozen=True, kw_only=True)
class Tap:
    """A fixed burst of one frame, then a number of STOP frames."""

    repeats: int = 1
    repeat_ms: int = 0
    """Spacing between writes, and the wait after the last one when it releases."""
    releases: int = 0


@dataclass(frozen=True, kw_only=True)
class OkinNFrameProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    name: str
    bed_types: tuple[str, ...]
    width: int = 4
    """Command word width in bytes."""
    write: WriteMode
    envelope: Envelope
    """How the route picks the plain frame or the RF-Gateway envelope.

    ``keeson_e6`` routes carry the same 32-bit word in a Keeson E6 frame
    (``codec/keeson.py``) instead of an N-frame, except for ``plain_keys``.
    """
    plain_keys: frozenset[str] = frozenset()
    """Keys a ``keeson_e6`` route still sends as plain N-frames."""
    axes: tuple[str, ...] = ()
    """Motor axes in the app's order. Empty: the handset's remote table decides."""
    keys: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    """Named command words. Empty: the handset's remote table holds them.

    40-bit profiles name the 32-bit key word; the selector byte follows it.
    """
    long_keys: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    """64-bit words a 40-bit profile sends as ``08 02`` frames."""
    selectors: tuple[int, ...] = (0,)
    """Selector bytes a 40-bit route can send after the key word."""
    hold: Hold
    recall: Tap | None = None
    """Presets and memory recall."""
    memory_recall: Tap | None = None
    """Memory recall, when it differs from the presets."""
    memory_slots: int = 0
    memory_save: Tap | None = None
    long_press: Tap | None = None
    """Sync and child lock: keys the handset streams for seconds."""
    control_mode: Tap | None = None
    """Persistent press-and-hold or press-and-release handset setting."""
    tap: Tap = Tap()
    """Lights and massage keys."""
    product: CstProduct | None = None
    """A 96-bit CST product's capabilities and field routing."""


# OKIN Motion Bed 1.0 (2), com.okin.motionbed, accepted row150. These are
# app words, not the gateway handset table. 05/0A have unverified mechanics.
OKIN_MOTIONBED: Final = OkinNFrameProfile(
    key="okin_motionbed",
    name="OKIN Motion Bed",
    bed_types=(BED_TYPE_OKIN_MOTIONBED,),
    write="response",
    envelope="gateway",
    axes=("back", "middle", "legs"),
    keys=MappingProxyType({
        "back_up": 0x01, "back_down": 0x02,
        "middle_up": 0x05, "middle_down": 0x0A,
        "legs_up": 0x04, "legs_down": 0x08,
        "stop": 0,
        "preset_stop": 0x21000000,
        "zero_g": 0x21000001, "flat": 0x21000002,
        "memory_1": 0x21000004, "memory_2": 0x21000006,
        "save_memory_1": 0x20000014, "save_memory_2": 0x20000016,
        "light_parameter_0": 0x31000000, "light_parameter_1": 0x31000001,
    }),
    hold=Hold(repeat_ms=200, releases=1),
    execution=STREAM_HOLD,
    recall=Tap(),
    memory_slots=2,
    memory_save=Tap(),
)


OKIMAT: Final = OkinNFrameProfile(
    key="okimat",
    name="Okimat handset table",
    bed_types=(BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID),
    write="response",
    envelope="gateway_detected",
    hold=Hold(repeat_ms=None, releases=1),
    recall=Tap(repeats=100, repeat_ms=300, releases=1),
    # A handset's own MemoSave hold timing replaces this default.
    memory_save=Tap(repeats=10, repeat_ms=200),
    long_press=Tap(repeats=60, repeat_ms=100, releases=1),
)

DEWERTOKIN: Final = OkinNFrameProfile(
    key="dewertokin",
    name="DewertOkin",
    bed_types=(BED_TYPE_DEWERTOKIN, BED_TYPE_OKIN_HANDLE),
    write="response",
    envelope="gateway_detected",
    axes=("head", "feet"),
    keys=MappingProxyType(
        {
            "head_up": 0x00000001,
            "head_down": 0x00000002,
            "feet_up": 0x00000004,
            "feet_down": 0x00000008,
            "flat": 0x10000000,
            "zero_g": 0x00004000,
            "tv": 0x00003000,
            "anti_snore": 0x00008000,
            "memory_1": 0x00001000,
            "memory_2": 0x00002000,
            "massage_wave": 0x80000000,
            "massage_head": 0x00000800,
            "massage_foot": 0x00000400,
            "massage_off": 0x02000000,
            "light": 0x00020000,
        }
    ),
    hold=Hold(repeat_ms=None, releases=1),
    recall=Tap(repeats=100, repeat_ms=300, releases=1),
    memory_slots=2,
)

RF_ECO_BT_REFRESH_MS: Final = 100

RF_ECO_BT: Final = OkinNFrameProfile(
    key="okin_rf_eco_bt",
    name="OKIN Smart Remote RF ECO BT stair lift",
    bed_types=(BED_TYPE_OKIN_RF_ECO_BT,),
    write="response",
    envelope="plain",
    axes=("stair",),
    keys=MappingProxyType({"stair_out": 0x00000001, "stair_in": 0x00000002}),
    hold=Hold(repeat_ms=RF_ECO_BT_REFRESH_MS, releases=0),
)

CUSTOMATIC_MOTOR_KEYS: Final = MappingProxyType(
    {
        "back_up": 0x01,
        "back_down": 0x02,
        "legs_up": 0x04,
        "legs_down": 0x08,
        "lumbar_up": 0x10,
        "lumbar_down": 0x20,
    }
)
CUSTOMATIC_MEMORY_KEYS: Final = MappingProxyType(
    {
        "flat": 0x08000000,
        "zg": 0x00001000,
        "anti": 0x00008000,
        "program": 0x80000000,
        "incline": 0x00004000,
    }
)
CUSTOMATIC_REFRESH_MS: Final = 120
CUSTOMATIC_HOLD: Final = Hold(repeat_ms=CUSTOMATIC_REFRESH_MS, releases=1, release_after_ms=100)
"""Motor holds refresh on one 120 ms lane, then one STOP 100 ms after the last write.

Memory holds end without a release frame (``releases`` applies to motors only).
"""
CUSTOMATIC_APP_HOLD_MS: Final = 2700
"""The app's Saved/Reset confirmation threshold, not a hardware acknowledgement."""


def _customatic(
    key: str, name: str, bed_type: str, axes: tuple[str, ...], flat: int, flat_repeats: int
) -> OkinNFrameProfile:
    keys = {k: v for k, v in CUSTOMATIC_MOTOR_KEYS.items() if k.rsplit("_", 1)[0] in axes}
    if key != "jeromes":
        keys |= {f"memory_{k}": v for k, v in CUSTOMATIC_MEMORY_KEYS.items()}
        keys["light"] = 0x00020000
    else:
        keys["restored_flat"] = 0x08000000
    return OkinNFrameProfile(
        key=key,
        name=name,
        bed_types=(bed_type,),
        write="characteristic",
        envelope="plain",
        axes=axes,
        keys=MappingProxyType({**keys, "flat": flat}),
        hold=CUSTOMATIC_HOLD,
        # Each app streams a held motor mask until release, ORs held motors into
        # one shared mask and clears only a released motor's bit (clarity,
        # jeromes, remedy, row028).
        execution=ExecutionCapabilities(
            hold="stream", concurrent=frozenset(f"motor:{axis}" for axis in axes)
        ),
        recall=Tap(repeats=flat_repeats),
    )


CUSTOMATIC_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        "clarity": _customatic(
            "clarity",
            "Customatic Clarity",
            BED_TYPE_CUSTOMATIC_CLARITY,
            ("back", "legs"),
            0x08000000,
            1,
        ),
        "jeromes": _customatic(
            "jeromes",
            "Customatic Jerome's",
            BED_TYPE_CUSTOMATIC_JEROMES,
            ("back", "legs"),
            0x10000000,
            3,
        ),
        "remedy": _customatic(
            "remedy",
            "Customatic Remedy",
            BED_TYPE_CUSTOMATIC_REMEDY,
            ("back", "legs", "lumbar"),
            0x08000000,
            1,
        ),
    }
)

# Semantics come from the layout bindings in Prodigy CE 1.2.0, not from the
# app's own FBP_KEYCODE_* names: several are wrong for this hardware (0x800000
# is declared LIGHT_INTENSITY_DOWN but bound to head massage down).
_LEGGETT_KEYS: Final = {
    "head_up": 0x1,
    "head_down": 0x2,
    "feet_up": 0x4,
    "feet_down": 0x8,
    "pillow_up": 0x10,
    "pillow_down": 0x20,
    "lumbar_up": 0x40,
    "lumbar_down": 0x80,
    # FLAT is a held key; the memories and Snore are recalls the box completes.
    "flat": 0x8000000,
    "memory_1": 0x1000,
    "memory_2": 0x2000,
    "memory_3": 0x4000,  # ships pre-assigned as the Snore position
    "memory_4": 0x8000,
    "anti_snore": 0x4000,
    # Arms the box to overwrite the next held slot; not a recall.
    "memory_store": 0x10000,
    "massage_head_up": 0x800,
    "massage_head_down": 0x800000,
    "massage_foot_up": 0x400,
    "massage_foot_down": 0x1000000,
    "massage_step": 0x100,
    "massage_wave_step": 0x10000000,
    "light": 0x20000,
    "control_mode_press_and_hold": 0x08010000,
    "control_mode_press_and_release": 0x01800000,
    "sleep_cancel": 0xFF200000,
}
LeggettKey = Literal["prodigy2l", "prodigy2", "prodigy4", "useries"]
LEGGETT_REFRESH_MS: Final = 100
LEGGETT_HOLD: Final = Hold(repeat_ms=LEGGETT_REFRESH_MS, releases=4, release_ms=100)
"""The app streams a held key, then exactly four zero frames (MaxZeroCount 3)."""
LEGGETT_FLAT_HOLD_MS: Final = 30_000
"""How long the integration streams the held FLAT key: a usability choice."""
LEGGETT_STORE_HOLD_MS: Final = (5_000, 2_000)
"""Arm with the store key, then hold the slot key, both at 100 ms."""
LEGGETT_CONTROL_MODE: Final = Tap(repeats=55, repeat_ms=100, releases=1)
"""The settings dialog's 55 attempts, then one explicit zero frame."""
LEGGETT_EXECUTION: Final = ExecutionCapabilities(hold="stream")
"""Prodigy 2 and 2L stream a held key until release (p2, p2l); composition is unproven."""
CU170_EXECUTION: Final = ExecutionCapabilities(
    hold="stream",
    sustain_ms=217,
    concurrent=frozenset({"motor:head", "motor:feet", "motor:pillow", "motor:lumbar"}),
)
"""Prodigy CE: held keys OR into one word and a release removes one key (p4, #516).

Its CU170 box stops motion 217-218 ms after the last frame (#368, #483).
"""
USERIES_EXECUTION: Final = ExecutionCapabilities(
    hold="stream", concurrent=frozenset({"motor:head", "motor:feet", "motor:pillow"})
)
"""U Series ORs held keys in its output accumulator; a release removes one (useries)."""
USERIES_SLEEP_MINUTES: Final = (15, 30, 45, 60, 75, 90)
_USERIES_SLEEP_ACTIONS: Final = {0: 0x00100000, 1: 0, 2: 0x00010000, 3: 0x00020000}


def _leggett(
    key: LeggettKey, name: str, axes: tuple[str, ...], memory_slots: int, *, settings: bool
) -> OkinNFrameProfile:
    # Only the keys this app can send: its axes, memories and settings.
    motors = {
        f"{axis}_{d}" for axis in ("head", "feet", "pillow", "lumbar") for d in ("up", "down")
    }
    memories = {f"memory_{slot}" for slot in range(1, 5)}
    keys = {
        name: word
        for name, word in _LEGGETT_KEYS.items()
        if (name not in motors or name.rsplit("_", 1)[0] in axes)
        and (name not in memories or int(name[-1]) <= memory_slots)
        and (settings or not name.startswith("control_mode_"))
    }
    keys["alarm_cancel"] = 0xFD000000 if key == "useries" else 0xFD200000
    if key == "prodigy4":
        # Hardware-confirmed on CU170 in #368: interrupts latched recall and store.
        keys["cu170_stop"] = 0x40000
    return OkinNFrameProfile(
        key=key,
        name=name,
        # ``leggett_platt`` reaches these profiles through its ``okin`` variant.
        bed_types=(BED_TYPE_LEGGETT_OKIN, BED_TYPE_LEGGETT_PLATT),
        # CU170 hardware accepts unconfirmed writes. Waiting for a response
        # pushes the stream past its 217-218 ms motion watchdog on proxies.
        write="no_response",
        envelope="revision_selector",
        axes=axes,
        keys=MappingProxyType(keys),
        hold=LEGGETT_HOLD,
        execution={"prodigy4": CU170_EXECUTION, "useries": USERIES_EXECUTION}.get(
            key, LEGGETT_EXECUTION
        ),
        # A recall is a fixed burst with no terminator: the box completes the
        # move itself, and a release could cancel it.
        recall=Tap(repeats=10, repeat_ms=100),
        memory_slots=memory_slots,
        control_mode=LEGGETT_CONTROL_MODE if settings else None,
        # Lights and massage are held keys: one write, one interval, then release.
        tap=Tap(repeat_ms=LEGGETT_REFRESH_MS, releases=4),
    )


LEGGETT_PROFILES: Final[Mapping[LeggettKey, OkinNFrameProfile]] = MappingProxyType(
    {
        "prodigy2l": _leggett(
            "prodigy2l", "Prodigy 2L", ("head", "feet", "lumbar"), 4, settings=True
        ),
        "prodigy2": _leggett("prodigy2", "Prodigy 2", ("head", "feet", "pillow"), 4, settings=True),
        "prodigy4": _leggett(
            "prodigy4", "Prodigy CE", ("head", "feet", "pillow", "lumbar"), 4, settings=True
        ),
        "useries": _leggett("useries", "U Series", ("head", "feet", "pillow"), 2, settings=False),
    }
)


def _integer_range(name: str, value: int, lower: int, upper: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer between {lower} and {upper}")


def leggett_sleep_timer(profile: OkinNFrameProfile, minutes: int, action: int) -> tuple[int, bool]:
    """Return a sleep-timer word and whether it bypasses the revision-0 envelope.

    Prodigy actions are favorite slots 1..4 and always travel as a plain frame.
    U-Series actions are flat=0 and memory 1..3 and use the normal key framing;
    its third sleep action is distinct from a direct recall button.
    """
    if profile.key == "useries":
        _integer_range("sleep action", action, 0, 3)
        _integer_range("sleep minutes", minutes, 15, 90)
        if minutes not in USERIES_SLEEP_MINUTES:
            raise ValueError("U-Series sleep minutes must be a multiple of 15")
        return 0xFF000000 | _USERIES_SLEEP_ACTIONS[action] | minutes, False
    _integer_range("favorite slot", action, 1, 4)
    # All three apps disable 00:00 in their sleep picker. Their defensive
    # zero-to-1440 branch is not an additional selectable duration.
    _integer_range("sleep minutes", minutes, 1, 1439)
    return 0xFF000000 | (action - 1) << 16 | minutes, True


def leggett_alarm(profile: OkinNFrameProfile, minutes: int | None) -> int:
    """Return an alarm word; ``None`` cancels (U-Series stop differs from Prodigy)."""
    if minutes is None:
        return profile.keys["alarm_cancel"]
    _integer_range("alarm minutes", minutes, 1, 1440)
    return 0xFD000000 + minutes


# 40-bit routes: ``05 02 <32-bit key> <selector>``.

OKIN_DOT: Final = replace(
    OKIMAT,
    key="okin_dot",
    name="DewertOkin DOT handset table",
    bed_types=(BED_TYPE_OKIN_DOT,),
    width=5,
    write="no_response",
    envelope="plain",
    # Memory keys are tap-to-recall, hold-to-save: one press, then STOP.
    memory_recall=Tap(releases=1),
)

OKIN_CB24: Final = OkinNFrameProfile(
    key="okin_cb24",
    name="OKIN SmartBed CB24",
    bed_types=(BED_TYPE_OKIN_CB24,),
    width=5,
    write="no_response",
    envelope="plain",
    axes=("head", "feet"),
    keys=MappingProxyType(
        {
            "head_up": 0x1,
            "head_down": 0x2,
            "feet_up": 0x4,
            "feet_down": 0x8,
            "flat": 0x8000000,
            "zero_g": 0x1000,
            "memory_1": 0x2000,  # also Lounge
            "memory_2": 0x4000,  # also TV/PC
            "anti_snore": 0x8000,
            "memory_3": 0x10000,
            "light": 0x20000,
            "massage_head_up": 0x800,
            "massage_head_down": 0x800000,
            "massage_foot_up": 0x400,
            "massage_foot_down": 0x1000000,
            "massage_toggle": 0x100,
            "massage_off": 0x2000000,
            "massage_wave_step": 0x10000000,
            "massage_intensity_up": 0xC00,
            "massage_intensity_down": 0x1800000,
        }
    ),
    selectors=(CB24_BED_SELECTION_DEFAULT, CB24_BED_SELECTION_A, CB24_BED_SELECTION_B),
    hold=Hold(repeat_ms=None, releases=1),
    # One packet: the app repeats presets only while a finger is down, and a
    # 5.2 s hold saves the position instead.
    recall=Tap(),
    memory_slots=3,
)

SIMMONS_REFRESH_MS: Final = 300
SIMMONS_SAVE_HOLD_MS: Final = 5500
"""Custom Mode is saved by holding its recall key past the help's 5 s."""
_SIMMONS_KEYS: Final = MappingProxyType(
    {
        "head_up": 0x1,
        "head_down": 0x2,
        "legs_up": 0x4,
        "legs_down": 0x8,
        "flat": 0x08000000,
        "zero_g": 0x1000,
        "tv": 0x4000,
        "anti_snore": 0x8000,
        "memory": 0x10000,
        "light": 0x20000,
        # Inclined layout: physical roles are unverified; middle reuses zero-G.
        "inclined_left": 0x10,
        "inclined_middle": 0x1000,
        "inclined_right": 0x20,
    }
)


def _simmons(key: str, name: str, *, okin: bool) -> OkinNFrameProfile:
    return OkinNFrameProfile(
        key=key,
        name=name,
        bed_types=(BED_TYPE_SIMMONS,),
        width=5,
        # OKIN names use Android's default acknowledged write.
        write="response" if okin else "no_response",
        envelope="keeson_e6" if okin else "plain",
        # The app's inclined builders never check the protocol.
        plain_keys=frozenset({"inclined_left", "inclined_middle", "inclined_right"}),
        axes=("back", "legs"),
        keys=_SIMMONS_KEYS,
        # Every control, held or tapped, ends with two STOPs 100 and 400 ms
        # after its release.
        hold=Hold(repeat_ms=SIMMONS_REFRESH_MS, releases=2, release_after_ms=100, release_ms=300),
        execution=STREAM_HOLD,
        recall=Tap(releases=2),
        memory_slots=1,
        tap=Tap(releases=2),
    )


SIMMONS_PROFILES: Final = MappingProxyType(
    {
        "smartbed": _simmons("simmons_smartbed", "SIMMONS SmartBed names", okin=False),
        "okin": _simmons("simmons_okin", "SIMMONS OKIN names", okin=True),
    }
)

DOUBLESLEEP_REFRESH_MS: Final = 300
DOUBLESLEEP: Final = OkinNFrameProfile(
    key="doublesleep",
    name="OKIN SleepEase",
    bed_types=(BED_TYPE_DOUBLESLEEP,),
    width=5,
    write="no_response",
    envelope="plain",
    axes=("head", "feet", "lumbar", "pillow", "hip"),
    # The SleepDriver (P1) key words by the app's command index; index 1 is the
    # all-zero STOP. XiaoBao (P2) and P3 send their own packet families.
    keys=MappingProxyType(
        {
            "1": 0x00000000,
            "2": 0x00000001,
            "3": 0x00000002,
            "4": 0x00000004,
            "5": 0x00000008,
            "8": 0x00000040,
            "9": 0x00000080,
            "10": 0x00000010,
            "11": 0x00000020,
            "12": 0x40000000,
            "13": 0x80000000,
            "14": 0x00010000,
            "15": 0x00040000,
            "16": 0x00008000,
            "17": 0x00002000,
            "18": 0x00004000,
            "19": 0x00001000,
            "26": 0x08000000,
            "28": 0x00000100,
            "29": 0x00000100,
            "31": 0x00000200,
            "35": 0x00000800,
            "36": 0x00800000,
            "37": 0x00000400,
            "38": 0x10000000,
            "40": 0x10000000,
            "41": 0x04000000,
            "58": 0x00020000,
        }
    ),
    # Motors and P1 presets refresh every 300 ms, then one STOP, on every driver.
    hold=Hold(repeat_ms=DOUBLESLEEP_REFRESH_MS, releases=1),
    memory_slots=2,
)

SLEEPYS_BOX25_RECALL: Final = Tap(repeats=3, repeat_ms=100, releases=1)
"""A preset is its key x3 at 100 ms, then a STOP 100 ms later that commits it."""
SLEEPYS_BOX25_STORE: Final = Tap(repeats=110, repeat_ms=100)

SLEEPYS_BOX25_LEGACY: Final = OkinNFrameProfile(
    key="sleepys_box25",
    name="Sleepy's Elite legacy CB25",
    bed_types=(BED_TYPE_SLEEPYS_BOX25,),
    width=5,
    write="no_response",
    envelope="plain",
    axes=("head", "foot", "lumbar", "neck"),
    # Named as the StarCode actions (``Box25Commands``) the controller translates.
    keys=MappingProxyType(
        {
            "head_up": 0x1,
            "head_down": 0x2,
            "foot_up": 0x4,
            "foot_down": 0x8,
            "lumbar_up": 0x10,
            "lumbar_down": 0x20,
            "neck_tilt_up": 0x40,
            "neck_tilt_down": 0x80,
            "motor_stop": 0x0,
            "preset_flat": 0x08000000,
            "preset_tv": 0x4000,
            "preset_zero_gravity": 0x1000,
            "preset_anti_snore": 0x8000,
            "preset_lounge": 0x2000,
            "preset_memory_1": 0x10000,
            "preset_memory_2": 0x40000,
            "store_memory_1": 0x08010000,
            "store_memory_2": 0x08040000,
            "massage_toggle": 0x80000,
            "massage_exit": 0x02000000,
            "massage_head_up": 0x800,
            "massage_head_down": 0x800000,
            "massage_foot_up": 0x400,
            "massage_foot_down": 0x01000000,
            "massage_intensity_up": 0xC00,
            "massage_intensity_down": 0x01800000,
        }
    ),
    long_keys=MappingProxyType(
        {
            "light_toggle": 0x0002000000000000,
            "massage_wave1": 0x80000,
            "massage_wave2": 0x100000,
            "massage_wave3": 0x200000,
        }
    ),
    # The app's one sender, shared with the StarCode dialect: motors follow the
    # entry's pulse settings.
    hold=Hold(repeat_ms=None, releases=1),
    recall=SLEEPYS_BOX25_RECALL,
    memory_slots=2,
    memory_save=SLEEPYS_BOX25_STORE,
)

# AdjustableM5X4: the command selector picks the frame family. These selectors
# send 40-bit key frames; BOX15 and BOX1220 move with Keeson E6 and A5 5A
# frames, BOX25_STAR with StarCode, so only their shared keys are here.
_ABM_BASE: Final = {
    "headUp": 0x1,
    "headDown": 0x2,
    "footUp": 0x4,
    "footDown": 0x8,
    "unionUp": 0x5,
    "unionDown": 0xA,
    "stop": 0x0,
    "flatPosition": 0x08000000,
    "tv": 0x4000,
    "lounge": 0x2000,
    "zeroGravity": 0x1000,
    "anti": 0x8000,
    "m1": 0x10000,
    "saveM1": 0x10000,
    "saveTv": 0x80004000,
    "saveLounge": 0x80002000,
    "saveZeroGravity": 0x80001000,
}
_ABM_SHARED: Final = {
    "resetMemory": 0x88000000,
    "massageOnOff": 0x80000,
    "turnonUnderbedLighting": 0x20000,
    "turnoffUnderbedLighting": 0x20000,
}
_ABM_MASSAGE: Final = {
    "headStrengthAdd": 0x800,
    "headStrengthReduce": 0x800000,
    "footStrengthAdd": 0x400,
    "footStrengthReduce": 0x01000000,
    "waveAdd": 0x10000000,
    "waveReduce": 0x04000000,
}
_ABM_LIGHT_TOGGLE: Final = {"underbedLighting": 0x0002000000000000}
_ABM_SWITCHES: Final = ("turnonUnderbedLighting", "turnoffUnderbedLighting")
STARCODE_ABM5_4_REFRESH_MS: Final = 100
"""The app's one control timer: held keys refresh every 100 ms, then STOP."""
STARCODE_ABM5_4_FLAT_HOLD_MS: Final = 600
STARCODE_ABM5_4_SAVE_HOLD_MS: Final = 6000
"""Saves and reset hold their key through the app's six-second confirmation."""


def _abm(
    key: str, selectors: str, keys: Mapping[str, int], long_keys: Mapping[str, int]
) -> OkinNFrameProfile:
    return OkinNFrameProfile(
        key=key,
        name=f"AdjustableM5X4 {selectors}",
        bed_types=(BED_TYPE_STARCODE_ABM5_4,),
        width=5,
        write="no_response",
        envelope="plain",
        axes=("head", "foot"),
        keys=MappingProxyType(dict(keys)),
        long_keys=MappingProxyType(dict(long_keys)),
        # BOX15 and BOX1220 move and stop with their own frames.
        hold=Hold(repeat_ms=STARCODE_ABM5_4_REFRESH_MS, releases=1 if "stop" in keys else 0),
        execution=STREAM_HOLD,
        memory_slots=1,
    )


_ABM_DEFAULT: Final = _abm(
    "starcode_abm5_4",
    "none, BOX24, BOX1221, BOX2422, BOX2442",
    _ABM_BASE | _ABM_SHARED,
    _ABM_LIGHT_TOGGLE,
)
STARCODE_ABM5_4_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        **dict.fromkeys(("none", "BOX24", "BOX1221", "BOX2422", "BOX2442"), _ABM_DEFAULT),
        "BOX3633": _abm(
            "starcode_abm5_4_box3633",
            "BOX3633",
            {k: v for k, v in (_ABM_BASE | _ABM_SHARED).items() if k not in _ABM_SWITCHES}
            | _ABM_MASSAGE
            | {"underbedLighting": 0x20000},
            {"turnonUnderbedLighting": 0x40, "turnoffUnderbedLighting": 0x80},
        ),
        # BOX25 switches the light with ``04 E0`` setting frames.
        "BOX25": _abm(
            "starcode_abm5_4_box25",
            "BOX25",
            {k: v for k, v in (_ABM_BASE | _ABM_SHARED).items() if k not in _ABM_SWITCHES}
            | _ABM_MASSAGE
            | {"change2White": 0x20004},
            _ABM_LIGHT_TOGGLE,
        ),
        "BOX15": _abm("starcode_abm5_4_box15", "BOX15", _ABM_SHARED, {}),
        "BOX1220": _abm("starcode_abm5_4_box1220", "BOX1220", _ABM_SHARED | _ABM_MASSAGE, {}),
    }
)

# eShine (com.okin.eshine 1.1.8, row122): one key table in the app's order; each
# product selector exposes part of it.
ESHINE_KEYS: Final = MappingProxyType(
    {
        "massage_wave": 0x10000000,
        "stop": 0x00000000,
        "tv": 0x00004000,
        "anti_snore": 0x00008000,
        "zero_g": 0x00001000,
        "feet_down": 0x00000008,
        "feet_up": 0x00000004,
        "head_down": 0x00000002,
        "head_up": 0x00000001,
        "pillow_down": 0x00000020,
        "pillow_up": 0x00000010,
        "light": 0x00020000,
        "flat": 0x08000000,
        "reading": 0x00002000,
        "massage_foot_strength": 0x00000400,
        "massage_head_strength": 0x00000800,
        "massage_timer": 0x00000200,
        "massage_off": 0x02000000,
        "massage_on": 0x00000100,
        "flat_zero_g": 0x08001000,
    }
)
ESHINE_REFRESH_MS: Final = 300
"""Held keys write at once, then every 300 ms; one STOP follows 200 ms after release."""


def _eshine(key: str, name: str, *, massage: bool, pillow: bool) -> OkinNFrameProfile:
    return OkinNFrameProfile(
        key=key,
        name=name,
        bed_types=(BED_TYPE_ESHINE_OKIN,),
        width=5,
        write="no_response",
        envelope="plain",
        axes=("head", "feet", "pillow") if pillow else ("head", "feet"),
        keys=MappingProxyType(
            {
                action: word
                for action, word in ESHINE_KEYS.items()
                if (massage or not action.startswith(("massage_", "light")))
                and (pillow or not action.startswith("pillow_"))
            }
        ),
        # Presets and the light are held keys too; massage keys are one write.
        hold=Hold(repeat_ms=ESHINE_REFRESH_MS, releases=1, release_after_ms=200),
        execution=STREAM_HOLD,
    )


ESHINE_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        "eshine_e2000": _eshine("eshine_e2000", "eShine E2000", massage=False, pillow=False),
        "eshine_e30003100": _eshine(
            "eshine_e30003100", "eShine E3000 / E3100", massage=True, pillow=False
        ),
        "eshine_e5000": _eshine("eshine_e5000", "eShine E5000", massage=True, pillow=True),
    }
)


# 96-bit routes: ``0C 02 <primary 32-bit field> <secondary 32-bit field> 00 00 00 00``.

CST_REFRESH_MS: Final = 100
"""Every CST app's timer: held keys refresh, and the two release STOPs follow, at 100 ms."""
CST_PRESS: Final = Tap(repeats=6, repeat_ms=CST_REFRESH_MS, releases=2)
"""A preset or button press: the key six times, then the two STOPs."""
CST_RELEASE: Final = {
    "releases": 2,
    "release_ms": CST_REFRESH_MS,
    "release_after_ms": CST_REFRESH_MS,
}
"""Two STOPs, 100 and 200 ms after the release."""


class CstMotorCommands:
    """Motor field command values (bytes 2-5)."""

    STOP = 0x00000000
    HEAD_UP = 0x00000001
    HEAD_DOWN = 0x00000002
    FOOT_UP = 0x00000004
    FOOT_DOWN = 0x00000008
    LUMBAR_UP = 0x00000010
    LUMBAR_DOWN = 0x00000020


class CstRemoteCommands:
    """Remote action command values.

    The CST app chooses the first or second 32-bit field per action. Call sites
    pass these values to codec.frame96() in the matching field.
    """

    STOP = 0x00000000
    FLAT = 0x08000000
    ZERO_G = 0x00001000
    LOUNGE = 0x00002000
    READING = LOUNGE
    INCLINE = 0x00004000
    ANTI_SNORE = 0x00008000
    SAVE_ZERO_G = FLAT | ZERO_G
    SAVE_LOUNGE = FLAT | LOUNGE
    SAVE_READING = SAVE_LOUNGE
    SAVE_INCLINE = FLAT | INCLINE
    LIGHT_TOGGLE = 0x00020000
    LIGHT_ON = 0x00000040
    LIGHT_OFF = 0x00000080
    MASSAGE_OFF = 0x02000000
    MASSAGE_INTENSITY = 0x00000C00
    MASSAGE_INTENSITY_MINUS = 0x01800000
    MASSAGE_WAVE_1 = 0x00080000
    MASSAGE_WAVE_2 = 0x00100000
    MASSAGE_WAVE_3 = 0x00200000
    MASSAGE_FULL_BODY = 0x00000100
    MASSAGE_HEAD_UP = 0x00000800
    MASSAGE_HEAD_DOWN = 0x00800000
    MASSAGE_FOOT_UP = 0x00000400
    MASSAGE_FOOT_DOWN = 0x01000000
    MASSAGE_TIMER_STEP = 0x00000200
    MEMORY_M = 0x00010000
    SAVE_MEMORY_M = FLAT | MEMORY_M


CstControlCommands = CstRemoteCommands


@dataclass(frozen=True)
class CstFields:
    """The two independently routed 32-bit fields in a CST frame."""

    primary: int = 0
    secondary: int = 0


@dataclass(frozen=True)
class CstMemorySlot:
    """A product profile's named recall/program pair."""

    name: str
    recall: int
    program: int


class CstMassageFields(TypedDict, total=False):
    """Optional zoned massage actions for fixed product profiles."""

    massage_head_up: CstFields
    massage_head_down: CstFields
    massage_foot_up: CstFields
    massage_foot_down: CstFields


@dataclass(frozen=True)
class CstProduct:
    """Capabilities and product-specific command routing for one CST app."""

    key: str
    memory_slots: tuple[CstMemorySlot, ...]
    massage_style: Literal["none", "global", "zoned", "increase_only"]
    motors: tuple[str, ...] = ("head", "feet")
    lounge: bool = True
    incline: bool = True
    lights: bool = True
    reading: bool = False
    light_toggle_only: bool = False
    memory_save_response_feedback: bool = False
    massage_toggle: CstFields | None = None
    massage_head_up: CstFields | None = None
    massage_head_down: CstFields | None = None
    massage_foot_up: CstFields | None = None
    massage_foot_down: CstFields | None = None
    massage_timer_step: CstFields | None = None


_MEMORY_ZERO_G = CstMemorySlot(
    "Zero Gravity", CstRemoteCommands.ZERO_G, CstRemoteCommands.SAVE_ZERO_G
)
_MEMORY_INCLINE = CstMemorySlot(
    "Incline", CstRemoteCommands.INCLINE, CstRemoteCommands.SAVE_INCLINE
)
_MEMORY_LOUNGE = CstMemorySlot("Lounge", CstRemoteCommands.LOUNGE, CstRemoteCommands.SAVE_LOUNGE)
_MEMORY_READING = CstMemorySlot(
    "Reading", CstRemoteCommands.READING, CstRemoteCommands.SAVE_READING
)
_MEMORY_M = CstMemorySlot("M", CstRemoteCommands.MEMORY_M, CstRemoteCommands.SAVE_MEMORY_M)
_THREE_MEMORIES = (_MEMORY_ZERO_G, _MEMORY_INCLINE, _MEMORY_LOUNGE)

_ZONED_SANCTUARY: CstMassageFields = {
    "massage_head_up": CstFields(primary=CstRemoteCommands.MASSAGE_HEAD_UP),
    "massage_head_down": CstFields(primary=CstRemoteCommands.MASSAGE_HEAD_DOWN),
    "massage_foot_up": CstFields(primary=CstRemoteCommands.MASSAGE_FOOT_UP),
    "massage_foot_down": CstFields(primary=CstRemoteCommands.MASSAGE_FOOT_DOWN),
}
_ZONED_BOB: CstMassageFields = {
    **_ZONED_SANCTUARY,
    "massage_head_down": CstFields(
        primary=CstRemoteCommands.MASSAGE_HEAD_DOWN,
        secondary=CstRemoteCommands.MASSAGE_HEAD_DOWN,
    ),
    "massage_foot_down": CstFields(
        primary=CstRemoteCommands.MASSAGE_FOOT_DOWN,
        secondary=CstRemoteCommands.MASSAGE_FOOT_DOWN,
    ),
}
_ZONED_SUPPORT: CstMassageFields = {
    **_ZONED_BOB,
    "massage_foot_down": CstFields(secondary=CstRemoteCommands.MASSAGE_FOOT_DOWN),
}

CST_PRODUCTS: Final[dict[str, CstProduct]] = {
    OKIN_CST_VARIANT_SANCTUARY: CstProduct(
        key=OKIN_CST_VARIANT_SANCTUARY,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G, _MEMORY_LOUNGE),
        massage_style="zoned",
        massage_toggle=CstFields(secondary=CstRemoteCommands.MASSAGE_FULL_BODY),
        **_ZONED_SANCTUARY,
    ),
    OKIN_CST_VARIANT_RESIDENT: CstProduct(
        key=OKIN_CST_VARIANT_RESIDENT,
        memory_slots=(*_THREE_MEMORIES, _MEMORY_M),
        lights=False,
        massage_style="zoned",
        massage_timer_step=CstFields(primary=CstRemoteCommands.MASSAGE_TIMER_STEP),
        **_ZONED_SANCTUARY,
    ),
    OKIN_CST_VARIANT_AVIADA: CstProduct(
        key=OKIN_CST_VARIANT_AVIADA,
        motors=("head", "feet", "lumbar"),
        memory_slots=_THREE_MEMORIES,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_BOB: CstProduct(
        key=OKIN_CST_VARIANT_BOB,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G, _MEMORY_LOUNGE),
        massage_style="zoned",
        massage_toggle=CstFields(secondary=CstRemoteCommands.MASSAGE_FULL_BODY),
        **_ZONED_BOB,
    ),
    OKIN_CST_VARIANT_CONTEMPO: CstProduct(
        key=OKIN_CST_VARIANT_CONTEMPO,
        motors=("head", "feet", "lumbar"),
        memory_slots=_THREE_MEMORIES,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_CAREFREE: CstProduct(
        key=OKIN_CST_VARIANT_CAREFREE,
        lounge=False,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G,),
        massage_style="none",
    ),
    OKIN_CST_VARIANT_CLARITY: CstProduct(
        key=OKIN_CST_VARIANT_CLARITY,
        memory_slots=_THREE_MEMORIES,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_MF900: CstProduct(
        key=OKIN_CST_VARIANT_MF900,
        motors=("head", "feet", "lumbar"),
        memory_slots=_THREE_MEMORIES,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_SUPPORT: CstProduct(
        key=OKIN_CST_VARIANT_SUPPORT,
        motors=("head", "feet", "lumbar"),
        memory_slots=_THREE_MEMORIES,
        massage_style="zoned",
        **_ZONED_SUPPORT,
    ),
    OKIN_CST_VARIANT_NECTAR_MOVE: CstProduct(
        key=OKIN_CST_VARIANT_NECTAR_MOVE,
        lounge=False,
        reading=True,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G, _MEMORY_READING),
        light_toggle_only=True,
        memory_save_response_feedback=True,
        massage_style="increase_only",
    ),
}


def cst_word(primary: int = 0, secondary: int = 0) -> int:
    """The 96-bit CST word of two 32-bit fields; its last 32 bits stay zero."""
    return primary << 64 | secondary << 32


def _cst_keys(product: CstProduct) -> dict[str, int]:
    """Every word a CST product's supported controls send, by control."""
    m, r = CstMotorCommands, CstRemoteCommands
    keys = {
        "head_up": m.HEAD_UP,
        "head_down": m.HEAD_DOWN,
        "foot_up": m.FOOT_UP,
        "foot_down": m.FOOT_DOWN,
        "flat": r.FLAT,
        "zero_g": r.ZERO_G,
        "anti_snore": r.ANTI_SNORE,
    }
    if "lumbar" in product.motors:
        keys |= {"lumbar_up": m.LUMBAR_UP, "lumbar_down": m.LUMBAR_DOWN}
    if product.lounge or product.reading:
        keys["lounge"] = r.LOUNGE
    if product.incline:
        keys["incline"] = r.INCLINE
    for slot, memory in enumerate(product.memory_slots, 1):
        keys |= {f"memory_{slot}": memory.recall, f"save_memory_{slot}": memory.program}
    words = {name: cst_word(value) for name, value in keys.items()}
    if product.lights:
        words["light_toggle"] = cst_word(r.LIGHT_TOGGLE)
        if not product.light_toggle_only:
            words |= {"light_on": cst_word(0, r.LIGHT_ON), "light_off": cst_word(0, r.LIGHT_OFF)}
    style = product.massage_style
    if style in ("global", "zoned") or product.massage_timer_step is not None:
        waves = (r.MASSAGE_WAVE_1, r.MASSAGE_WAVE_2, r.MASSAGE_WAVE_3)
        words |= {f"wave_{index}": cst_word(0, wave) for index, wave in enumerate(waves, 1)}
    if style not in ("none", "increase_only"):
        words["massage_off"] = cst_word(r.MASSAGE_OFF)
    if style in ("global", "increase_only"):
        words["massage_intensity_up"] = cst_word(r.MASSAGE_INTENSITY)
    if style == "global":
        words["massage_intensity_down"] = cst_word(r.MASSAGE_INTENSITY_MINUS)
    for name in (
        "massage_toggle",
        "massage_head_up",
        "massage_head_down",
        "massage_foot_up",
        "massage_foot_down",
        "massage_timer_step",
    ):
        if (fields := getattr(product, name)) is not None:
            words[name] = cst_word(fields.primary, fields.secondary)
    return words


_CST_NAMES: Final = {
    OKIN_CST_VARIANT_SANCTUARY: "Rize Sanctuary",
    OKIN_CST_VARIANT_RESIDENT: "Rize Resident",
    OKIN_CST_VARIANT_AVIADA: "Rize Aviada",
    OKIN_CST_VARIANT_BOB: "Rize Bob",
    OKIN_CST_VARIANT_CONTEMPO: "Rize Contempo",
    OKIN_CST_VARIANT_CAREFREE: "Rize II Carefree",
    OKIN_CST_VARIANT_CLARITY: "Rize II Clarity",
    OKIN_CST_VARIANT_MF900: "Rize MF900",
    OKIN_CST_VARIANT_SUPPORT: "Support",
    OKIN_CST_VARIANT_NECTAR_MOVE: "Nectar Move",
}


def _cst(
    product: CstProduct,
    name: str,
    bed_type: str,
    keys: Mapping[str, int],
    *,
    write: WriteMode = "response",
    hold: Hold,
    recall: Tap,
    tap: Tap,
) -> OkinNFrameProfile:
    return OkinNFrameProfile(
        key=product.key,
        name=name,
        bed_types=(bed_type,),
        width=12,
        write=write,
        envelope="plain",
        axes=product.motors,
        keys=MappingProxyType(dict(keys)),
        memory_slots=len(product.memory_slots),
        product=product,
        hold=hold,
        execution=STREAM_HOLD,
        recall=recall,
        tap=tap,
    )


CST_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        key: _cst(
            product,
            _CST_NAMES[key],
            BED_TYPE_OKIN_CST,
            _cst_keys(product),
            # Nectar Move refreshes a held axis every 100 ms and sends a press
            # once; the others follow the entry's pulses and press six times.
            hold=Hold(
                repeat_ms=CST_REFRESH_MS if key == OKIN_CST_VARIANT_NECTAR_MOVE else None,
                **CST_RELEASE,
            ),
            recall=Tap(releases=2) if key == OKIN_CST_VARIANT_NECTAR_MOVE else CST_PRESS,
            tap=Tap(releases=2) if key == OKIN_CST_VARIANT_NECTAR_MOVE else CST_PRESS,
        )
        for key, product in CST_PRODUCTS.items()
    }
)


# OKIN Bedding apps over the CST frame: Jordan's Serenity 1.0.1 (S01), Jordan's
# Tranquil 1.0.2 and the Customatic Z-Series 1.0.4 Z-230/Z-280 pages. Each
# action table is its own app's, as (primary, secondary) field values.
SERENITY_ACTIONS: Final = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "selector_4_up": (0x10, 0),
    "selector_4_down": (0x20, 0),
    "selector_5_up": (0x40, 0),
    "selector_5_down": (0x80, 0),
    "flat": (0x08000000, 0),
    "zero_g": (0x1000, 0),
    "memory_1": (0x10000, 0),
    "tv": (0x4000, 0),
    "memory_2": (0x40000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_tv": (0x08004000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
    "massage_toggle": (0x100, 0),
    "light_toggle": (0x20000, 0),
    "leisure": (0x2000, 0),
    "anti_snore": (0x8000, 0),
    "wave_1": (0, 0x80000),
    "wave_2": (0, 0x100000),
    "wave_3": (0, 0x200000),
    "massage_off": (0x02000000, 0),
    "light_on": (0, 0x40),
    "light_off": (0, 0x80),
}
SERENITY_SAVE_CODES: Final = {
    "save_zero_g": 5,
    "save_memory_1": 4,
    "save_tv": 6,
    "save_memory_2": 8,
}

# Jordan's Tranquil 1.0.2 live Z280 remote/massage pages plus its Activity
# voice switch. Lounge is a touch button here (op9), and there is no TV.
TRANQUIL_ACTIONS: Final = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "selector_4_up": (0x10, 0),
    "selector_4_down": (0x20, 0),
    "selector_5_up": (0x40, 0),
    "selector_5_down": (0x80, 0),
    "flat": (0x08000000, 0),
    "zero_g": (0x1000, 0),
    "lounge": (0x2000, 0),
    "memory_1": (0x10000, 0),
    "memory_2": (0x40000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_lounge": (0x08002000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
    "massage_toggle": (0x100, 0),
    "light_toggle": (0x20000, 0),
    "anti_snore": (0x8000, 0),
    "wave_1": (0, 0x80000),
    "wave_2": (0, 0x100000),
    "wave_3": (0, 0x200000),
    "massage_off": (0x02000000, 0),
    "light_on": (0, 0x40),
    "light_off": (0, 0x80),
}

# Customatic Z-Series 1.0.4. Voice is unbound, so there are no waves, massage
# off or discrete light frames. Builder op5 emits 0x10/0x20 in this app.
_ZSERIES_COMMON_ACTIONS = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "flat": (0x08000000, 0),
    "anti_snore": (0x8000, 0),
    "memory_1": (0x10000, 0),
    "zero_g": (0x1000, 0),
    "tv": (0x4000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_tv": (0x08004000, 0),
    "light_toggle": (0x20000, 0),
    "massage_toggle": (0x100, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
}
ZSERIES_Z230_ACTIONS: Final = {
    **_ZSERIES_COMMON_ACTIONS,
    "head_foot_up": (0x05, 0),
    "head_foot_down": (0x0A, 0),
    "massage_intensity_cycle": (0x0C00, 0),
}
ZSERIES_Z280_ACTIONS: Final = {
    **_ZSERIES_COMMON_ACTIONS,
    "selector_5_up": (0x10, 0),
    "selector_5_down": (0x20, 0),
    "memory_2": (0x40000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
}


def _two_axis_product(
    key: str,
    memory_slots: tuple[CstMemorySlot, ...],
    *,
    lounge: bool,
) -> CstProduct:
    return CstProduct(
        key=key,
        lounge=lounge,
        incline=False,
        memory_slots=memory_slots,
        massage_style="zoned",
        massage_toggle=CstFields(primary=0x100),
    )


_M1 = CstMemorySlot("M1", 0x10000, 0x08010000)
_M2 = CstMemorySlot("M2", 0x40000, 0x08040000)


BEDDING_SAVE_HOLD_MS: Final = 5000
"""The apps' save-help gesture, not a hardware threshold."""
BEDDING_HOLD: Final = Hold(repeat_ms=CST_REFRESH_MS, **CST_RELEASE)
"""Every action streams at 100 ms until its deadline, then two STOPs at +100/+200 ms."""
_BEDDING: Final = (
    ("serenity", "Jordan's Serenity", BED_TYPE_SERENITY, SERENITY_ACTIONS, (_M1, _M2), True),
    ("tranquil", "Jordan's Tranquil", BED_TYPE_TRANQUIL, TRANQUIL_ACTIONS, (_M1, _M2), True),
    ("zseries_z230", "Customatic Z-230", BED_TYPE_ZSERIES, ZSERIES_Z230_ACTIONS, (_M1,), False),
    ("zseries_z280", "Customatic Z-280", BED_TYPE_ZSERIES, ZSERIES_Z280_ACTIONS, (_M1, _M2), False),
)
_BEDDING_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        key: _cst(
            _two_axis_product(key, memories, lounge=lounge),
            name,
            bed_type,
            {action: cst_word(*fields) for action, fields in actions.items()},
            # The apps' write type is framework default; HA follows the properties.
            write="characteristic",
            hold=BEDDING_HOLD,
            recall=Tap(releases=2),
            tap=Tap(releases=2),
        )
        for key, name, bed_type, actions, memories, lounge in _BEDDING
    }
)


# Row180 com.okin.bedding.rizeii 1.0.1 (2): all 24 live rows, including STOP.
# The axes are the live UI's head, foot and lumbar, not ConfigManager.motorNumber.
RIZE_REMEDY_II_ACTIONS: Final = {
    "head_up": (1, 0), "head_down": (2, 0),
    "foot_up": (4, 0), "foot_down": (8, 0),
    "lumbar_up": (0x10, 0), "lumbar_down": (0x20, 0),
    "flat": (0x08000000, 0), "anti_snore": (0x8000, 0),
    "lounge": (0x2000, 0), "zero_g": (0x1000, 0), "incline": (0x4000, 0),
    "save_lounge": (0x08002000, 0), "save_zero_g": (0x08001000, 0),
    "save_incline": (0x08004000, 0),
    "light_toggle": (0x20000, 0), "light_on": (0, 0x40), "light_off": (0, 0x80),
    "wave_1": (0, 0x80000), "wave_2": (0, 0x100000), "wave_3": (0, 0x200000),
    "massage_intensity_up": (0x0C00, 0), "massage_intensity_down": (0x01800000, 0),
    "massage_off": (0x02000000, 0),
}
RIZE_REMEDY_II: Final = _cst(
    CstProduct(
        key="rize_remedy_ii", memory_slots=(
            CstMemorySlot("Zero Gravity", 0x1000, 0x08001000),
            CstMemorySlot("Incline", 0x4000, 0x08004000),
            CstMemorySlot("Leisure", 0x2000, 0x08002000),
        ), massage_style="global", motors=("head", "feet", "lumbar"),
    ),
    "Rize Remedy II", BED_TYPE_RIZE_REMEDY_II,
    {"stop": 0, **{action: cst_word(*fields) for action, fields in RIZE_REMEDY_II_ACTIONS.items()}},
    write="characteristic", hold=BEDDING_HOLD, recall=Tap(releases=2), tap=Tap(releases=2),
)
BEDDING_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {**_BEDDING_PROFILES, "rize_remedy_ii": RIZE_REMEDY_II}
)


# 64-bit routes: ``08 02 <64-bit word>``.

OKIN_64BIT_KEYS: Final = MappingProxyType(
    {
        "stop": 0x0000000000000000,
        "head_up": 0x0000000100000000,
        "head_down": 0x0000000200000000,
        "foot_up": 0x0000000400000000,
        "foot_down": 0x0000000800000000,
        "lumbar_up": 0x0000001000000000,
        "lumbar_down": 0x0000002000000000,
        "flat": 0x0800000000000000,
        "zero_g": 0x0000100000000000,
        "lounge": 0x0000200000000000,
        "tv_pc": 0x0000400000000000,
        "anti_snore": 0x0000800000000000,
        "memory_1": 0x0001000000000000,
        "memory_2": 0x0004000000000000,
        "massage_switch": 0x0000010000000000,
        "strength_up": 0x00000C0000000000,
        "strength_down": 0x0180000000000000,
        "wave_mode": 0x1000000000000000,
        "light_toggle": 0x0002000000000000,
        "light_on": 0x0000000000000040,
        "light_off": 0x0000000000000080,
    }
)


def _okin_64bit(key: str, name: str, *, response: bool) -> OkinNFrameProfile:
    return OkinNFrameProfile(
        key=key,
        name=name,
        bed_types=(BED_TYPE_OKIN_64BIT,),
        width=8,
        write="response" if response else "no_response",
        envelope="plain",
        axes=("head", "feet", "lumbar"),
        keys=OKIN_64BIT_KEYS,
        # Motors refresh at the entry's pulses, then one STOP; presets, memory,
        # lights and massage are one write without a STOP.
        hold=Hold(repeat_ms=None, releases=1),
        recall=Tap(),
        memory_slots=2,
    )


OKIN_64BIT_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        # Protocol 25_42_02 and 36_33_04a of com.okin.bedding.adjustbed.
        "nordic": _okin_64bit("okin_64bit_nordic", "OKIN 64-bit Nordic UART", response=False),
        "custom": _okin_64bit("okin_64bit_custom", "OKIN 64-bit OKIN service", response=True),
    }
)

ADJUSTABLE_LUMBAR_REFRESH_MS: Final = 100
"""Held controls write at once, then every 100 ms."""
ADJUSTABLE_LUMBAR_SAVE_HOLD_MS: Final = 6000
"""The app reports "Setup" after a Flat+preset chord is held 6 s (its help says 5 s)."""
ADJUSTABLE_LUMBAR_KEYS: Final = MappingProxyType(
    {
        "head_up": 0x0000000100000000,
        "head_down": 0x0000000200000000,
        "feet_up": 0x0000000400000000,
        "feet_down": 0x0000000800000000,
        "lumbar_up": 0x0000001000000000,
        "lumbar_down": 0x0000002000000000,
        "stop": 0x0000000000000000,
        "flat": 0x0800000000000000,
        "anti_snore": 0x0000800000000000,
        "lounge": 0x0000200000000000,
        "incline": 0x0000400000000000,
        "zero_g": 0x0000100000000000,
        "save_anti_snore": 0x0800800000000000,
        "save_lounge": 0x0800200000000000,
        "save_incline": 0x0800400000000000,
        "save_zero_g": 0x0800100000000000,
        "light": 0x0002000000000000,
        "wave_1": 0x0000000000080000,
        "wave_2": 0x0000000000100000,
        "wave_3": 0x0000000000200000,
        "massage_stop": 0x0200000000000000,
        "massage_up": 0x00000C0000000000,
        "massage_down": 0x0180000000000000,
        "massage_on": 0x0000010000000000,
        "voice_stop": 0x0000000000000000,
    }
)
"""The 25_42_02 and 36_33_04a tables: one set of 64-bit words."""


def _lumbar(key: str, name: str, *, response: bool) -> OkinNFrameProfile:
    return OkinNFrameProfile(
        key=key,
        name=name,
        bed_types=(BED_TYPE_ADJUSTABLE_LUMBAR,),
        width=8,
        write="response" if response else "no_response",
        envelope="plain",
        axes=("head", "feet", "lumbar"),
        keys=ADJUSTABLE_LUMBAR_KEYS,
        # Every release is a STOP at once and another 300 ms later.
        hold=Hold(repeat_ms=ADJUSTABLE_LUMBAR_REFRESH_MS, releases=2, release_ms=300),
        execution=STREAM_HOLD,
        recall=Tap(releases=2),
        tap=Tap(releases=2),
    )


ADJUSTABLE_LUMBAR_PROFILES: Final[Mapping[str, OkinNFrameProfile]] = MappingProxyType(
    {
        # 35_22_01 sends StarCode ``5A`` frames instead (codec/okin_5a.py).
        "36_33_04a": _lumbar(
            "adjustable_lumbar_okin", "Adjustable bed (Lumbar) 36_33_04a", response=True
        ),
        "25_42_02": _lumbar(
            "adjustable_lumbar_star", "Adjustable bed (Lumbar) 25_42_02", response=False
        ),
    }
)


# Resident Adjustable Base 1.0.0 (unit160), the only live 36_33_01a catalog.
# Frozen literals, not the similarly named Rize Resident CST app.
RESIDENT: Final = OkinNFrameProfile(
    key="resident",
    name="Resident Adjustable Base",
    bed_types=(BED_TYPE_RESIDENT,),
    width=8,
    write="response",
    envelope="plain",
    axes=("head", "feet"),
    keys=MappingProxyType(
        {
            "stop": 0x0000000000000000,
            "head_up": 0x0000000100000000,
            "head_down": 0x0000000200000000,
            "foot_up": 0x0000000400000000,
            "foot_down": 0x0000000800000000,
            "head_foot_up": 0x0000000500000000,
            "head_foot_down": 0x0000000A00000000,
            "flat": 0x0800000000000000,
            "zero_g": 0x0000100000000000,
            "tv_pc": 0x0000400000000000,
            "lounge": 0x0000200000000000,
            "anti_snore": 0x0000800000000000,
            "memory_1": 0x0001000000000000,
            "memory_2": 0x0004000000000000,
            "light_toggle": 0x0002000000000000,
            "massage_switch": 0x0000010000000000,
            "massage_off": 0x0200000000000000,
            "strength_up": 0x00000C0000000000,
            "strength_down": 0x0180000000000000,
            "massage_timer": 0x0000020000000000,
        }
    ),
    hold=Hold(repeat_ms=300, releases=2, release_ms=300),
    execution=STREAM_HOLD,
    recall=Tap(releases=2),
    tap=Tap(releases=2),
    memory_slots=2,
)
RESIDENT_NOTIFY_RETRIES_MS: Final = (350, 350, 300)
RESIDENT_CLOCK_DELAY_MS: Final = 300
RESIDENT_CLOCK_QUERY_DELAY_MS: Final = 100
RESIDENT_INFO_DELAY_MS: Final = 1000
RESIDENT_QUERY_DELAY_MS: Final = 300
RESIDENT_NAME_PREFIXES: Final = ("okin", "smartbed")
