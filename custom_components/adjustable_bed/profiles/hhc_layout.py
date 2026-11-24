"""Shared HHC letter layouts used by L2 Motion and MoodBase."""

from dataclasses import dataclass
from typing import ClassVar

from ..execution import STREAM_HOLD, ExecutionCapabilities
from .bedgear import Control, eligible, panel
from .motomotion import name_character


@dataclass(frozen=True)
class HhcLetterLayout:
    name: str
    execution: ExecutionCapabilities = STREAM_HOLD
    refresh_ms: ClassVar[int] = 100
    stop_count: ClassVar[int] = 5
    stop_interval_ms: ClassVar[int] = 30
    fallback_count: ClassVar[int] = 3
    delayed_first_tick: ClassVar[bool] = True
    alarm_indices: ClassVar[tuple[int, int, int]] = (8, 9, 11)
    panel_d_h_extra: ClassVar[bool] = False
    panel_zero_massage_held: ClassVar[bool] = True

    def __post_init__(self) -> None:
        if not eligible(self.name):
            raise ValueError("Enter the exact Bluetooth name containing HHC")

    def char(self, index: int) -> str:
        return name_character(self.name, index)

    @property
    def panel(self) -> str:
        return panel(self.name)

    @property
    def wrapped(self) -> bool:
        return self.char(11) == "M"

    @property
    def alarm(self) -> bool:
        return self.char(11) == "E"

    @property
    def sync(self) -> bool:
        return self.char(13) == "X"

    @property
    def axes(self) -> tuple[tuple[str, str, str], ...]:
        layout, t, v = self.panel, self.char(8), self.char(9)
        zones = ("head", "foot")
        if layout in ("PanelE", "PanelFive"):
            zones = ("head",)
        elif layout == "PanelA":
            zones = ("head", "foot", "lumbar")
        elif layout == "PanelD":
            zones = ("head", "foot", {"3": "neck", "4": "lumbar", "8": "tilt"}.get(t, "neck"))
        elif layout == "PanelZero":
            zones = ("head", "foot", "combined", "tilt")
        elif layout == "WR1140":
            zones = {
                "5": ("head", "foot", "tilt"),
                "6": zones,
                "7": ("neck", "head", "lumbar", "foot"),
                "8": ("head", "lumbar", "foot"),
            }[v]
        elif layout in ("PanelOne", "PanelTwo", "PanelThree", "PanelFour"):
            if (
                layout in ("PanelOne", "PanelTwo")
                or (layout == "PanelThree" and t == "3")
                or (layout == "PanelFour" and t == "4")
            ):
                zones = {
                    "1": ("head",),
                    "2": ("head", "foot"),
                    "3": ("neck", "head", "foot"),
                    "4": ("neck", "head", "lumbar", "foot")
                    if layout in ("PanelThree", "PanelFour")
                    else ("neck", "head", "foot")
                    if layout == "PanelOne"
                    else ("head", "foot"),
                }.get(v, ("neck", "head", "foot") if layout == "PanelOne" else ("head", "foot"))
            zones = {
                "25": ("head", "lumbar", "foot"),
                "55": ("neck", "head", "foot", "tilt"),
                "65": ("head", "lumbar", "foot"),
                "75": ("neck", "head", "lumbar", "foot"),
            }.get(t + v, zones)
        result = []
        for zone in zones:
            letters = {
                "head": "KL",
                "foot": "MN",
                "neck": "PQ",
                "combined": "pq",
                "tilt": "pq" if layout == "PanelFour" else "PQ",
                "lumbar": "pq",
            }[zone]
            if zone == "lumbar" and (
                layout == "PanelD"
                or t + v in ("25", "65")
                or (layout == "PanelA" and self.char(13) != "H")
            ):
                letters = "PQ"
            if (
                layout == "PanelD"
                and len(result) == 2
                and self.panel_d_h_extra
                and self.char(13) == "H"
            ):
                letters = "pq"
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
            return (("flat", "O"), ("anti_snore", "R"))
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
        filler = self.panel in (
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
            Control(
                "preset_" + key,
                letter,
                "fallback" if filler or (self.panel == "PanelE" and key == "flat") else "none",
            )
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
                Control(
                    "massage_" + key,
                    letter,
                    "fallback" if self.panel_zero_massage_held else "none",
                    self.panel_zero_massage_held,
                )
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
