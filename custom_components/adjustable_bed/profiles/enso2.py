"""ENSO Sleep Control receiver and remote layout profiles over Richmat 6E."""

from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

from ..codec import richmat
from ..execution import STREAM_HOLD

TRANSPORTS: Final = tuple(richmat.TRANSPORTS[key] for key in ("w1", "w2", "n1", "w4"))
EXCLUDED_CODES: Final = frozenset({"WFRM", "FWRM", "RMCS", "TEST"})
MANUAL_PREFIXES: Final = ("209A05", "Cool Touch")
MANUAL_LAYOUTS: Final = frozenset({"QRRM"})

INIT: Final = richmat.frame(0x6E, 0x02, 1, 0)
ALARM_QUERY: Final = richmat.frame(0x6E, 0x08, 1, 1)
LED_QUERY: Final = richmat.frame(0x6E, 0x0A, 0, 1)
AROMA_QUERY: Final = richmat.frame(0x6E, 0x1A, 0, 0)

ALARM_ACTIONS: Final = {
    "tv": 0x58,
    "anti_snore": 0x46,
    "zero_g": 0x45,
    "lounge": 0x59,
    "memory_1": 0x2E,
    "memory_2": 0x2F,
    "memory_3": 0x30,
    "flat_sleep": 0xF6,
    "wake_mode_1": 0xB0,
    "wake_mode_2": 0xB1,
}
ALARM_MASSAGE: Final = {"head": 0x4C, "feet": 0x4E, "both": 0x5D}
# TV, anti-snore, zero gravity, lounge and memories 1–3 (both, head, feet).
ALARM_COMBINED: Final = {
    0x58: (0x77, 0x7A, 0x7D),
    0x46: (0x78, 0x7B, 0x7E),
    0x45: (0x79, 0x7C, 0x7F),
    0x59: (0xAC, 0xAD, 0xAE),
    0x2E: (0x81, 0x82, 0x83),
    0x2F: (0xA6, 0xA7, 0xA8),
    0x30: (0xA9, 0xAA, 0xAB),
}
SELECTED_MOTOR_KEYS: Final = {53: (0x3F, 0x40), 54: (0x41, 0x42), 55: (0x71, 0x72)}
# The popup shows 10, 20 and 30 minutes; the slider's stops are labelled 0, 2H, 3H and 5H.
MASSAGE_TIMER_CODES: Final = {10: 0x5F, 20: 0x63, 30: 0x61}
MASSAGE_SLIDER_MINUTES: Final = {0: 0, 120: 2, 180: 3, 300: 5}


class Control(NamedTuple):
    label: str
    status: int
    framed: int | None
    raw: int | None
    alternate: int | None
    threshold_ms: int
    tag: str
    behavior: str
    alternate_label: str
    raw_label: str | None

    @property
    def name(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", self.label.lower()).strip("_")

    @property
    def is_save(self) -> bool:
        return self.label.startswith("Save ")

    @property
    def is_axis_selector(self) -> bool:
        return self.tag in ("51", "52")

    @property
    def can_hold(self) -> bool:
        return not self.is_save and (self.status == 1 or self.behavior in ("armed", "selectable"))

    def key(self, raw: bool) -> int | None:
        return self.raw if raw else self.framed


@dataclass(frozen=True, slots=True)
class Layout:
    name: str
    mode_count: int
    alarm_tags: frozenset[int]
    controls: dict[str, Control]
    raw_controls: dict[str, Control]
    pages: tuple[str, ...]
    direct_alarm: bool

    execution = STREAM_HOLD


def _controls(
    rows: list[int], all_controls: list[Control], *, raw: bool = False
) -> dict[str, Control]:
    controls: dict[str, Control] = {}
    for index in rows:
        control = all_controls[index]
        if raw and control.raw_label is not None:
            control = control._replace(label=control.raw_label)
        name = control.name
        if name in controls:
            name = f"{name}_{index}"
        controls[name] = control
    return controls


with gzip.open(Path(__file__).parent.parent / "beds/enso2/layouts.json.gz", "rt") as stream:
    _data = json.load(stream)

_CONTROLS = [Control(*row) for row in _data["controls"]]
LAYOUTS: Final = {
    code: Layout(
        code,
        modes,
        frozenset(int(tag, 16) for tag in tags),
        _controls(rows, _CONTROLS),
        _controls(rows, _CONTROLS, raw=True),
        tuple(pages),
        direct,
    )
    for code, (modes, tags, rows, pages, direct) in _data["layouts"].items()
}
ALIASES: Final[dict[str, str]] = _data["aliases"]
LAYOUT_CHOICES: Final = {
    code: code for code in sorted(LAYOUTS) if code not in MANUAL_LAYOUTS and not LAYOUTS[code].pages
}
SCAN_PREFIXES: Final = tuple(
    sorted(
        {
            *LAYOUTS,
            *MANUAL_PREFIXES,
            *(key for key in ALIASES if key not in ("B6RU", "ZR90", "COOL")),
        }
    )
)


_UPPER_SCAN_PREFIXES: Final = tuple(prefix.upper() for prefix in SCAN_PREFIXES)


def admitted_name(name: str | None) -> bool:
    """The scan gate precedes aliases and uses the untrimmed name."""
    return bool(name and len(name.strip()) >= 4 and name.upper().startswith(_UPPER_SCAN_PREFIXES))


def advertised_layout(name: str | None) -> str | None:
    """Suggest a usable layout only after app-specific prefix admission."""
    if name is None or not admitted_name(name):
        return None
    upper = name.upper()
    for size in range(9, 3, -1):
        prefix = upper[:size]
        if prefix in ALIASES:
            return ALIASES[prefix]
    return upper[:4] if upper[:4] in LAYOUTS else None


def setup_choices(name: str | None) -> dict[str, str]:
    """List direct layouts; show the shipped subpage relationship when detected."""
    layout = LAYOUTS.get(advertised_layout(name) or "")
    if layout is None or not layout.pages:
        return LAYOUT_CHOICES
    return {**LAYOUT_CHOICES, **{page: f"{page} ({layout.name})" for page in layout.pages}}


def tick_ms(name: str | None, *, raw: bool) -> int:
    prefix = (name or "").strip()[:4].upper()
    if prefix in ("TWRM", "MLRM"):
        return 110
    return 170 if raw and prefix == "6BRM" else 150


def key_frame(key: int, mode: int, *, raw: bool) -> bytes:
    return richmat.encode("nordic", key) if raw else richmat.command(key, mode)


def aroma_frames(*values: int) -> tuple[bytes, ...]:
    return tuple(
        richmat.frame(0x6E, selector, 0, value)
        for selector, value in zip((0x1B, 0x1C, 0x1D), values, strict=True)
    )


def massage_timer_frame(layout: str, value: int) -> bytes:
    fallback = 0x8B if layout == "D9RM" else 0x5E
    if layout == "Y6RM":
        code = MASSAGE_TIMER_CODES.get(value, fallback)
    else:
        code = {0: fallback, 2: 0x5F, 3: 0x63, 5: 0x61}.get(value, value)
    return richmat.command(code)
