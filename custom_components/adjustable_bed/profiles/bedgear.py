"""Bedgear 2.0.1 (row A12): independent name gates and control layouts.

Hand-transcribed from the accepted COMMANDS/VARIANTS and selector evidence.
Manual model names do not select a wire route.
"""

from dataclasses import dataclass
from typing import ClassVar, Literal

from ..execution import STREAM_HOLD, ExecutionCapabilities
from .motomotion import name_character, name_length

Release = Literal["stop", "fallback", "none"]


@dataclass(frozen=True)
class Control:
    key: str
    letter: str
    release: Release = "none"
    held: bool = True


def eligible(name: str | None) -> bool:
    return name is not None and name_length(name) == 14 and "HHC" in name


def panel(name: str | None) -> str:
    """Keep the source's selector priority, case and UTF-16 indexing."""
    if name is None or name_length(name) < 10:
        return "PanelOne"
    a, b = name_character(name, 8), name_character(name, 9)
    pair = a + b
    if pair == "15":
        return "PanelA"
    if pair in ("35", "45", "85"):
        return "PanelD"
    if a == "4" or pair in ("25", "55"):
        return "PanelFour"
    if a == "9" and b in "5678":
        return "WR1140"
    if pair in ("65", "75"):
        return "PanelThree"
    return dict(
        zip(
            "012356789ABCDE",
            (
                "PanelZero",
                "PanelOne",
                "PanelTwo",
                "PanelThree",
                "PanelFive",
                "PanelSix",
                "PanelSeven",
                "PanelEight",
                "PanelNine",
                "PanelA",
                "PanelFour",
                "PanelD",
                "PanelSixZG",
                "PanelE",
            ),
            strict=True,
        )
    ).get(a, "PanelOne")


@dataclass(frozen=True)
class BedgearProfile:
    name: str
    key: ClassVar[str] = "bedgear"
    execution: ExecutionCapabilities = STREAM_HOLD
    refresh_ms: ClassVar[int] = 100
    stop_count: ClassVar[int] = 5
    stop_interval_ms: ClassVar[int] = 30
    fallback_count: ClassVar[int] = 3

    def __post_init__(self) -> None:
        if not eligible(self.name):
            raise ValueError("Enter the exact 14 UTF-16-unit Bedgear Bluetooth name containing HHC")

    def char(self, index: int) -> str:
        return name_character(self.name, index)

    @property
    def panel(self) -> str:
        return panel(self.name)

    @property
    def wrapped(self) -> bool:
        return self.char(11) == "M"

    @property
    def timer(self) -> bool:
        return self.char(10) != "B"

    @property
    def rgb(self) -> bool:
        return self.char(10) == "D"

    @property
    def alarm(self) -> bool:
        return self.char(11) == "E"

    @property
    def sync(self) -> bool:
        return self.char(13) == "X"

    @property
    def axes(self) -> tuple[tuple[str, str, str], ...]:
        p, a, b = self.panel, self.char(8), self.char(9)
        zones = ("head", "foot")
        if p in ("PanelE", "PanelFive"):
            zones = ("actuator",)
        elif p == "PanelA":
            zones = ("head", "foot", "lumbar")
        elif p == "PanelD":
            zones = ("head", "foot", {"3": "neck", "4": "lumbar", "8": "tilt"}.get(a, "neck"))
        elif p == "PanelZero":
            zones = ("head", "foot", "combined", "tilt")
        elif p == "WR1140":
            zones = {
                "5": ("head", "foot", "tilt"),
                "6": ("head", "foot"),
                "7": ("neck", "head", "lumbar", "foot"),
                "8": ("head", "lumbar", "foot"),
            }[b]
        elif p in ("PanelOne", "PanelTwo", "PanelThree", "PanelFour"):
            if (
                p in ("PanelOne", "PanelTwo")
                or (p == "PanelThree" and a == "3")
                or (p == "PanelFour" and a == "4")
            ):
                zones = {
                    "1": ("head",),
                    "2": ("head", "foot"),
                    "3": ("neck", "head", "foot"),
                    "4": ("neck", "head", "lumbar", "foot")
                    if p in ("PanelThree", "PanelFour")
                    else ("head", "foot"),
                }.get(b, ("head", "foot"))
            if a + b in ("25", "65"):
                zones = ("head", "lumbar", "foot")
            elif a + b == "55":
                zones = ("neck", "head", "foot", "tilt")
            elif a + b == "75":
                zones = ("neck", "head", "lumbar", "foot")
        result = []
        for zone in zones:
            letters = {
                "head": "KL",
                "actuator": "KL",
                "foot": "MN",
                "neck": "PQ",
                "combined": "pq",
                "tilt": "pq" if p == "PanelFour" else "PQ",
                "lumbar": "pq",
            }[zone]
            if zone == "lumbar" and (
                p == "PanelD" or a + b in ("25", "65") or (p == "PanelA" and self.char(13) != "H")
            ):
                letters = "PQ"
            result.append((zone, *letters))
        return tuple(result)

    @property
    def memory_slots(self) -> int:
        return (
            2
            if self.panel
            in (
                "PanelA",
                "PanelD",
                "PanelEight",
                "PanelFour",
                "PanelSeven",
                "PanelThree",
                "PanelTwo",
                "PanelZero",
                "WR1140",
            )
            else 0
        )

    @property
    def light(self) -> bool:
        return self.memory_slots > 0 or self.panel == "PanelE"

    @property
    def presets(self) -> tuple[tuple[str, str], ...]:
        if self.panel in ("PanelA", "PanelEight", "PanelFour", "PanelThree", "WR1140"):
            return (("flat", "O"), ("anti_snore", "R"), ("tv", "S"), ("zero_g", "T"))
        if self.panel == "PanelE":
            return (("anti_snore", "R"),)
        if self.panel == "PanelSixZG":
            return (("zero_g", "T"),)
        return (("flat", "O"),)

    @property
    def controls(self) -> tuple[Control, ...]:
        controls = [
            Control(
                f"{axis}_{direction}",
                letter,
                "fallback"
                if self.panel == "PanelZero" and axis == "tilt" and direction == "down"
                else "stop",
            )
            for axis, up, down in self.axes
            for direction, letter in (("up", up), ("down", down))
        ]
        fallback = self.panel in (
            "PanelA",
            "PanelD",
            "PanelEight",
            "PanelFive",
            "PanelSeven",
            "PanelSix",
            "PanelSixZG",
            "PanelZero",
        )
        controls.extend(
            Control("preset_" + key, letter, "fallback" if fallback else "none")
            for key, letter in self.presets
        )
        controls.extend(
            Control(f"memory_{slot}", letter)
            for slot, letter in enumerate("UV"[: self.memory_slots], 1)
        )
        if self.light:
            controls.append(Control("light_toggle", "A", held=False))
        if self.panel in ("PanelD", "PanelFour", "PanelSeven", "PanelTwo", "WR1140"):
            controls.extend(
                Control("massage_" + key, letter, held=False)
                for key, letter in (("head", "C"), ("foot", "B"), ("stop", "D"))
            )
        elif self.panel == "PanelZero":
            controls.extend(
                Control("massage_" + key, letter, "fallback")
                for key, letter in (
                    ("head_up", "G"),
                    ("head_down", "H"),
                    ("head_stop", "J"),
                    ("foot_up", "E"),
                    ("foot_down", "F"),
                    ("foot_stop", "I"),
                )
            )
        return tuple(controls)
