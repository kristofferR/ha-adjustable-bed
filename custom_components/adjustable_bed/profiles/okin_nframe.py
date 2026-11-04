"""Profiles over the Okin N-frame codec (32-bit command words).

``OKIMAT`` serves the ``okimat`` and ``okin_uuid`` bed types, whose keys come
from the selected handset's remote table. ``DEWERTOKIN`` serves ``dewertokin``
and ``okin_handle``, and ``RF_ECO_BT`` the ``okin_rf_eco_bt`` stair lift; these
three are pre-v5 routes without an accepted APK report. ``CUSTOMATIC_PROFILES``
are the Customatic Clarity, Jerome's and Remedy 1.0.1 apps, one per bed type.
``LEGGETT_PROFILES`` are Prodigy 2L 1.2, Prodigy 2 2.2.0, Prodigy CE 1.2.0 and
U Series 2.1, chosen by the ``leggett_okin`` entry's app profile. Every app
profile comes from its accepted APK Protocol Audit report.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal

from ..const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
)

WriteMode = Literal["response", "no_response", "characteristic"]
Envelope = Literal["plain", "gateway_detected", "revision_selector"]


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
    name: str
    bed_types: tuple[str, ...]
    width: int = 4
    """Command word width in bytes."""
    write: WriteMode
    envelope: Envelope
    """How the route picks the plain frame or the RF-Gateway envelope."""
    axes: tuple[str, ...] = ()
    """Motor axes in the app's order. Empty: the handset's remote table decides."""
    keys: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    """Named command words. Empty: the handset's remote table holds them."""
    hold: Hold
    recall: Tap | None = None
    """Presets and memory recall."""
    memory_slots: int = 0
    memory_save: Tap | None = None
    long_press: Tap | None = None
    """Sync and child lock: keys the handset streams for seconds."""
    control_mode: Tap | None = None
    """Persistent press-and-hold or press-and-release handset setting."""
    tap: Tap = Tap()
    """Lights and massage keys."""


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
