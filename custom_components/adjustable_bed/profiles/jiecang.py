"""Profiles over the Jiecang codec.

``LEGACY`` serves the ``jiecang`` and ``comfort_motion`` bed types. The
``jiecang_app`` bed type selects one of ``APP_PROFILES``: Comfort Motion 2.2.1,
Dreamask (ERGOBALANCE) 1.0.8, Dreamotion 1.0.5 and Dream Motion HD 1.0.4, each
from its accepted APK Protocol Audit report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from ..codec import jiecang as codec
from ..codec.jiecang import BILATERAL, STANDARD, Axis, MassageZone, Preset, TransportKey, Wake
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities

Layout = Literal[
    "standard_2",
    "standard_3_neck",
    "standard_3_lumbar",
    "standard_3_hi_low",
    "standard_3_split_upper",
    "standard_4_legacy",
    "standard_4_bilateral",
    "split_series",
    "split_after_bilateral",
]
Schedule = tuple[tuple[int, bytes], ...]
"""Frames at absolute millisecond offsets; equal offsets keep their order."""


@dataclass(frozen=True, kw_only=True)
class Hold:
    """Held movement: refresh one motion frame, then release."""

    repeat_ms: int
    repeats: int | None = None
    """Fixed refresh count; ``None`` follows the entry's motor pulse count."""
    final_frame: bool = False
    """The app sends one more motion frame when a hold ends normally."""
    releases: Schedule
    """Cleanup after the last frame. An explicit stop sends it from offset 0."""


@dataclass(frozen=True, kw_only=True)
class Tap:
    """One-shot action: write, wait, then send the release frame if any."""

    repeats: int = 1
    repeat_ms: int = 100
    release_after_ms: int = 0
    release: bytes | None = None


@dataclass(frozen=True)
class NameRule:
    """Device names the app accepts, as a full-match pattern."""

    pattern: str
    error: str
    encoding: str = "ascii"

    def encode(self, name: str) -> bytes:
        if re.fullmatch(self.pattern, name, re.ASCII) is None:
            raise ValueError(self.error)
        return name.encode(self.encoding)


@dataclass(frozen=True, kw_only=True)
class JiecangProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    layouts: dict[Layout, tuple[Axis, ...]]
    """Selectable physical layouts. Empty: the motor-count layout of the legacy route."""
    transports: tuple[TransportKey, ...]
    """Transports this profile drives, in the app's selection order."""
    hold: Hold
    recall: Tap
    """Presets and memory recall."""
    memory_save: Tap
    memory_slots: int
    memory_payload: bytes
    massage_levels: tuple[int, ...]
    """Wire byte for each user-facing massage level, starting at off."""
    fixed_rate: bool = False
    """Repeats keep absolute offsets; otherwise each waits its interval after a write."""
    bootstrap: Schedule = ()
    """Queries sent after notifications start."""
    name_rule: NameRule | None = None


def _repeat_pairs(*offsets: tuple[int, bytes]) -> Schedule:
    """The apps send each startup query twice, 100 ms apart."""
    return tuple((offset + repeat, command) for offset, command in offsets for repeat in (0, 100))


QUERY_SOFTWARE: Final = codec.query(b"\x40\x00")
QUERY_LIGHT: Final = codec.query(b"\x01\x00")
QUERY_HARDWARE: Final = codec.query(b"\x40")
QUERY_VIBRATION: Final = codec.query(b"\x08")
QUERY_ALARM: Final = codec.query(b"\x10")

APP_LAYOUT_AXES: Final[dict[Layout, tuple[Axis, ...]]] = {
    "standard_2": ("back", "legs", "both"),
    "standard_3_neck": ("back", "legs", "head"),
    "standard_3_lumbar": ("back", "legs", "lumbar"),
    "standard_3_hi_low": ("back", "legs", "bed_height"),
    "standard_3_split_upper": ("back", "legs", "right_back", "both_backs"),
    "standard_4_legacy": ("head", "back", "lumbar", "legs"),
    "standard_4_bilateral": (
        "back",
        "both_backs",
        "right_back",
        "legs",
        "both_legs",
        "right_legs",
    ),
    "split_series": ("back", "legs", "right_back", "both_backs"),
    "split_after_bilateral": ("back", "legs", "right_back", "both_backs"),
}
BILATERAL_LAYOUTS: Final[frozenset[Layout]] = frozenset(
    {"standard_4_bilateral", "split_after_bilateral"}
)
# Dream Motion HD has neither bilateral layout.
_DREAMHD_LAYOUT_AXES: Final[dict[Layout, tuple[Axis, ...]]] = {
    layout: axes for layout, axes in APP_LAYOUT_AXES.items() if layout not in BILATERAL_LAYOUTS
}

LEGACY: Final = JiecangProfile(
    key="legacy",
    layouts={},
    transports=("g3", "g1"),
    hold=Hold(repeat_ms=50, repeats=25, releases=((0, codec.SHORT_RELEASE),)),
    recall=Tap(repeats=3, repeat_ms=100),
    memory_save=Tap(),
    memory_slots=3,
    memory_payload=STANDARD,
    massage_levels=tuple(range(11)),
)
COMFORT_MOTION: Final = JiecangProfile(
    key="comfort_motion",
    # The app lists its axes in this order.
    layouts={
        "standard_2": ("back", "both", "legs"),
        "standard_3_neck": ("head", "back", "legs"),
        "standard_4_legacy": ("head", "back", "lumbar", "legs"),
    },
    transports=("g1", "g2"),
    hold=Hold(repeat_ms=100, releases=((100, codec.SHORT_RELEASE),)),
    recall=Tap(release_after_ms=100, release=codec.SHORT_RELEASE),
    memory_save=Tap(),
    memory_slots=2,
    memory_payload=STANDARD,
    massage_levels=(0, 2, 3, 4),
    bootstrap=(
        (200, codec.query(b"\x01")),
        (300, codec.query(b"\x01")),
        (400, QUERY_HARDWARE),
        (500, QUERY_HARDWARE),
        (600, QUERY_VIBRATION),
        (700, QUERY_VIBRATION),
    ),
    name_rule=NameRule(
        r"[._0-9A-Za-z]{1,18}",
        "Comfort Motion names use 1..18 ASCII letters, digits, dot or underscore",
    ),
)
_DREAM_NAME: Final = NameRule(
    r"[0-9A-Za-z]{1,20}", "Name must contain 1..20 ASCII letters or digits"
)
_DREAM_BOOTSTRAP: Final = _repeat_pairs(
    (0, QUERY_SOFTWARE),
    (800, QUERY_LIGHT),
    (1000, codec.query(b"\x50")),
    (1200, QUERY_HARDWARE),
    (1400, QUERY_VIBRATION),
    (1600, QUERY_ALARM),
    (1800, QUERY_SOFTWARE),
)
DREAMASK: Final = JiecangProfile(
    key="dreamask",
    execution=STREAM_HOLD,
    fixed_rate=True,
    layouts=APP_LAYOUT_AXES,
    transports=("g3", "g1", "g2"),
    hold=Hold(repeat_ms=100, releases=((50, codec.LONG_RELEASE), (150, codec.LONG_RELEASE))),
    recall=Tap(release_after_ms=800, release=codec.LONG_RELEASE),
    memory_save=Tap(repeats=3, repeat_ms=30),
    memory_slots=2,
    memory_payload=BILATERAL,
    massage_levels=(0, 2, 3, 4),
    bootstrap=_DREAM_BOOTSTRAP,
    name_rule=_DREAM_NAME,
)
DREAMOTION: Final = JiecangProfile(
    key="dreamotion",
    execution=STREAM_HOLD,
    fixed_rate=True,
    layouts=APP_LAYOUT_AXES,
    transports=("g3", "g1", "g2"),
    hold=Hold(
        repeat_ms=100,
        final_frame=True,
        releases=((100, codec.SHORT_RELEASE), (800, codec.LONG_RELEASE)),
    ),
    recall=Tap(release_after_ms=800, release=codec.LONG_RELEASE),
    memory_save=Tap(repeats=3, repeat_ms=30),
    memory_slots=2,
    memory_payload=BILATERAL,
    massage_levels=(0, 2, 3, 4),
    bootstrap=_DREAM_BOOTSTRAP,
    name_rule=_DREAM_NAME,
)
DREAMHD: Final = JiecangProfile(
    key="dreamhd",
    execution=STREAM_HOLD,
    fixed_rate=True,
    layouts=_DREAMHD_LAYOUT_AXES,
    transports=("g3", "g1", "g2"),
    hold=Hold(repeat_ms=100, final_frame=True, releases=((100, codec.SHORT_RELEASE),)),
    recall=Tap(release_after_ms=100, release=codec.SHORT_RELEASE),
    memory_save=Tap(repeats=3, repeat_ms=30),
    memory_slots=2,
    memory_payload=STANDARD,
    massage_levels=(0, 2, 3, 4),
    # Dream Motion HD 1.0.4 has no light-status query in its startup burst.
    bootstrap=_repeat_pairs(
        (0, codec.query()),
        (1000, codec.query(b"\x01")),
        (1200, QUERY_HARDWARE),
        (1400, QUERY_VIBRATION),
        (1600, QUERY_ALARM),
        (1800, QUERY_SOFTWARE),
    ),
    name_rule=NameRule(r"[ -~]{1,20}", "Name must contain 1..20 printable ASCII characters"),
)
APP_PROFILES: Final[dict[str, JiecangProfile]] = {
    "comfort_motion": COMFORT_MOTION,
    "dreamask": DREAMASK,
    "dreamotion": DREAMOTION,
    "dreamhd": DREAMHD,
}


def automatic_light_on(profile: JiecangProfile, value: int) -> bool:
    """Dream Motion HD reports automatic light on as non-zero; the other apps as zero."""
    return (value != 0) == (profile is DREAMHD)


def light_toggle_command(profile: JiecangProfile) -> bytes:
    """ERGOBALANCE and Dream Motion toggle with the bilateral payload; other routes with none."""
    return codec.light_toggle(BILATERAL if profile in (DREAMASK, DREAMOTION) else b"")


def is_bilateral(layout: Layout) -> bool:
    """Global controls keep bilateral payloads in the explicit mixed layout."""
    return layout in BILATERAL_LAYOUTS


def motion_payload(layout: Layout | None) -> bytes:
    """Only the fully bilateral layout moves motors with the two-byte payload."""
    return BILATERAL if layout == "standard_4_bilateral" else STANDARD


def motion_command(profile: JiecangProfile, layout: Layout, axis: Axis, up: bool) -> bytes:
    if axis not in profile.layouts.get(layout, ()):
        raise ValueError(f"{axis} is unavailable for {layout}")
    return codec.motion(axis, up, motion_payload(layout))


def memory_command(profile: JiecangProfile, slot: int, *, save: bool = False) -> bytes:
    if not 1 <= slot <= profile.memory_slots:
        raise ValueError(f"memory slot must be between 1 and {profile.memory_slots}")
    return codec.memory(slot, save=save, payload=profile.memory_payload)


def preset_command(layout: Layout | None, preset: Preset) -> bytes:
    bilateral = layout is not None and is_bilateral(layout)
    return codec.preset(preset, BILATERAL if bilateral or preset == "yoga" else STANDARD)


def massage_zones(layout: Layout) -> tuple[MassageZone, ...]:
    if is_bilateral(layout):
        return ("back", "right")
    if layout in ("standard_3_split_upper", "split_series"):
        return ("back", "right", "legs")
    return ("back", "legs")


def massage_command(
    profile: JiecangProfile, layout: Layout, zone: MassageZone, level: int
) -> bytes:
    """Encode a user-facing level; the Dream apps map 0..3 to wire 00/02/03/04."""
    if zone not in massage_zones(layout):
        raise ValueError(f"{zone} massage is unavailable for {layout}")
    if not 0 <= level < len(profile.massage_levels):
        raise ValueError(f"massage level must be between 0 and {len(profile.massage_levels) - 1}")
    return codec.massage(zone, profile.massage_levels[level], bilateral=is_bilateral(layout))


def wake_schedule(
    profile: JiecangProfile,
    layout: Layout,
    wake: Wake,
    back_level: int = 0,
    leg_level: int = 0,
    right_level: int | None = None,
) -> Schedule:
    """Return a Dream app's absolute alarm execution offsets, preserving duplicates.

    Alarm massage always uses standard payloads, including on bilateral layouts.
    Yoga may be stored in the alarm, but the apps have no Yoga wake executor.
    """
    if wake == "yoga":
        raise ValueError("The apps do not execute Yoga wake alarms")
    for level in (back_level, leg_level):
        if not 0 <= level <= 3:
            raise ValueError("alarm massage level must be between 0 and 3")
    dreamhd = profile is DREAMHD
    split = layout in (
        ("standard_3_split_upper", "split_series")
        if dreamhd
        else ("split_series", "split_after_bilateral")
    )
    expected_right = back_level if split else 0
    if right_level is not None and right_level != expected_right:
        raise ValueError("Split alarm right massage must match the back level")
    result: list[tuple[int, bytes]] = []
    zones: list[tuple[int, MassageZone, int]] = [
        (0, "back", back_level),
        (500 if split or dreamhd else 300, "legs", leg_level),
    ]
    if split:
        zones.append((180, "right", back_level))
    for offset, zone, level in zones:
        if level:
            command = codec.massage(zone, profile.massage_levels[level])
            result.extend((offset + delay, command) for delay in (0, 30, 60))
            result.extend((offset + delay, codec.SHORT_RELEASE) for delay in (90, 120, 150))
    if wake in ("memory_1", "memory_2"):
        command = memory_command(profile, int(wake[-1]))
    else:
        command = preset_command(layout, wake)
    result.extend((offset, command) for offset in (800, 830, 860, 890, 920))
    if not dreamhd:
        if wake == "memory_2" and not split:
            result.append((1600, codec.LONG_RELEASE))
        result.extend((offset, codec.LONG_RELEASE) for offset in (1690, 1720))
    return tuple(sorted(result, key=lambda item: item[0]))
