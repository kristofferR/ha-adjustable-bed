"""Ordered Motion Bed app name selection, independent of shared BLE transport."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .motion_bed_state import MotionBedContext, MotionBedRoute, PresetVariant

MotionBedSurface = Literal["home", "motor", "air", "thermal", "hub"]
MovementLayout = Literal[
    "W1", "W2", "W3", "W4", "W6", "W7", "W8", "W10", "W11", "W12",
    "W13", "W14", "W18", "modular",
]

RAW_NAME_MARKERS = (
    "QMS-430", "QMS-443", "QMS-444", "QMS-DFQ", "QMS-DQ", "QMS-H02",
    *(f"QMS-I{i}6" for i in range(10)), "QMS-IQ", "QMS-JQ-D", "QMS-KQ-H",
    *(f"QMS-L{i}4" for i in range(10)), "QMS-LQ", "QMS-MQ", "QMS-NQ",
    "QMS2", "QMS3", "QMS4", "S3-2", "S3-3", "S3-4", "S4-4", "S4-N",
    "S4-Y", "S5-Y", "S6-Y", "SealyMF", "TL-A", "TL-B", "TL-Q", "TL-W",
)
PRESET_VARIANTS: tuple[PresetVariant, ...] = (
    "K1", "K2", "K2M", "K3", "K4", "K5", "K8", "K9", "K11", "modular",
)
MOVEMENT_LAYOUTS: tuple[MovementLayout, ...] = (
    "W1", "W2", "W3", "W4", "W6", "W7", "W8", "W10", "W11", "W12",
    "W13", "W14", "W18", "modular",
)
_TITLE_REPLACEMENTS = str.maketrans({"<": "C", ":": "A", ";": "B", "=": "D", ">": "E", "?": "F"})


def accepts_motion_bed_name(raw_name: str) -> bool:
    """The app uses case-sensitive contains, including interior matches."""
    return bool(raw_name) and any(marker in raw_name for marker in RAW_NAME_MARKERS)


def motion_bed_saved_title(raw_name: str) -> str:
    return raw_name.translate(_TITLE_REPLACEMENTS)


@dataclass(frozen=True, slots=True)
class MotionBedSelection:
    surface: MotionBedSurface
    preset: PresetVariant
    movement: MovementLayout
    saved_title: str
    alternate_identity: bool = False

    @property
    def route(self) -> MotionBedRoute:
        contexts: frozenset[MotionBedContext]
        if self.surface == "home":
            # Hidden tabs still own registered notification receivers.
            contexts = frozenset({"home", "preset", "massage", "light", "smart_sleep", "fault_settings"})
        elif self.surface == "hub":
            contexts = frozenset({"module_startup", "fault_settings"})
        else:
            contexts = frozenset({self.surface, "fault_settings"})
        return MotionBedRoute(self.preset, self.alternate_identity, contexts)


def select_motion_bed(
    raw_name: str,
    *,
    restored: bool = False,
    preset_override: PresetVariant | None = None,
    movement_override: MovementLayout | None = None,
) -> MotionBedSelection:
    """Select the app's ordered route or an explicit same-target retained layout.

    Only explicitly configured/restored profiles use the fallback. A shared FFE1
    service is never sufficient evidence to select this app.
    """
    if not restored and not accepts_motion_bed_name(raw_name):
        raise ValueError("Name is outside the Motion Bed app whitelist; select an explicit profile")
    title = motion_bed_saved_title(raw_name)
    surface: MotionBedSurface = "home"
    modular_routes: tuple[tuple[str, MotionBedSurface], ...] = (("TL-Q", "hub"), ("TL-A", "air"), ("TL-B", "motor"), ("TL-W", "thermal"))
    for marker, candidate in modular_routes:
        if marker in title:
            surface = candidate
            break
    alternate = any(marker in title for marker in ("QMS-MQ", "QMS2", "S3-2", "QMS3"))
    preset: PresetVariant = "K2M"
    movement: MovementLayout = "W2"
    if surface != "home":
        preset, movement = "modular", "modular"
    elif not title or any(marker in title for marker in ("QMS-IQ", "QMS-LQ", *(f"QMS-I{i}6" for i in range(10)), *(f"QMS-L{i}4" for i in range(10)))):
        preset, movement = "K1", "W1"
    elif any(marker in title for marker in ("QMS-JQ-D", "QMS4", "S4-N")):
        preset, movement = "K2M", "W2"
    elif any(marker in title for marker in ("QMS-NQ", "QMS3")):
        preset, movement = ("K2" if "QMS3-N93-327" in title else "K2M"), "W3"
    elif any(marker in title for marker in ("QMS-MQ", "QMS2", "SealyMF")):
        preset, movement = "K2M", "W4"
    elif any(marker in title for marker in ("QMS-KQ-H", "QMS-H02")):
        preset, movement = "K3", "W6"
    elif any(marker in title for marker in ("QMS-DFQ", "QMS-430", "QMS-444")):
        preset, movement = "K4", "W7"
    elif any(marker in title for marker in ("QMS-DQ", "QMS-443")):
        preset, movement = "K5", "W8"
    elif "S3-2" in title:
        preset, movement = "K2M", "W10"
    elif "S3-3" in title:
        preset, movement = "K8", "W11"
    elif "S3-4" in title:
        preset, movement = "K9", "W11"
    elif "S4-Y" in title:
        preset, movement = "K11", "W12"
    elif "S5-Y" in title:
        preset, movement = "K11", "W13"
    elif "S6-Y" in title:
        preset, movement = "K11", "W14"
    elif "S4-4" in title:
        preset, movement = "K2M", "W18"
    if preset_override is not None:
        if preset_override not in PRESET_VARIANTS:
            raise ValueError("Unknown Motion Bed preset layout")
        preset = preset_override
    if movement_override is not None:
        if movement_override not in MOVEMENT_LAYOUTS:
            raise ValueError("Unknown Motion Bed movement layout")
        movement = movement_override
    if surface != "home" and (preset != "modular" or movement != "modular"):
        raise ValueError("Standalone modules and hubs require their modular layout")
    if surface == "home" and (preset == "modular" or movement == "modular"):
        raise ValueError("Home retained layouts cannot cross into modular surfaces")
    return MotionBedSelection(surface, preset, movement, title, alternate)
