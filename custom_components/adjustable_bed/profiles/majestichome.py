"""Majestic Home 1.0.4/code10400, accepted row151 product lists (E9-E13).

Identifiers describe app layouts, not independently verified hardware models.
No advertised name or service selects a layout. Hardware UNVERIFIED.
"""

from dataclasses import dataclass
from typing import Final

from ..codec.richmat import record
from .richmat import RichmatProfile
from .richmat_app import Action, Product
from .richmat_catalog import Catalog

TICK_MS: Final = 100
QUERY_MS: Final = 300
STOP: Final = 0x6E


@dataclass(frozen=True, slots=True)
class Control:
    key: str
    label: str
    code: int
    group: str
    save: int | None = None
    held: bool = False


@dataclass(frozen=True, slots=True)
class Layout:
    key: str
    controls: tuple[Control, ...]
    alarms: tuple[str, ...] = ()

    def control(self, key: str) -> Control:
        for control in self.controls:
            if control.key == key:
                return control
        raise ValueError("This control is unavailable for the selected Majestic Home product")


HEAD: Final = (
    Control("head_up", "Head Up", 0x24, "motor", held=True),
    Control("head_down", "Head Down", 0x25, "motor", held=True),
)
FOOT: Final = (
    Control("foot_up", "Foot Up", 0x26, "motor", held=True),
    Control("foot_down", "Foot Down", 0x27, "motor", held=True),
)
BOTH: Final = (
    Control("both_up", "Head and Foot Up", 0x29, "motor", held=True),
    Control("both_down", "Head and Foot Down", 0x2A, "motor", held=True),
)
FLAT: Final = Control("flat", "Flat", 0x31, "preset")
LIGHT: Final = Control("light", "Toggle Light", 0x3C, "light")
PRESETS: Final = (
    Control("zero_gravity", "Zero Gravity", 0x45, "preset", 0x66),
    Control("anti_snore", "Anti-Snore", 0x46, "preset", 0x69),
    Control("memory_1", "Memory 1", 0x2E, "preset", 0x2B),
    Control("memory_2", "Memory 2", 0x2F, "preset", 0x2C),
)
MASSAGE: Final = (
    Control("head_massage_1", "Massage: Head Level 1", 0x99, "massage"),
    Control("head_massage_2", "Massage: Head Level 2", 0x9A, "massage"),
    Control("head_massage_3", "Massage: Head Level 3", 0x9B, "massage"),
    Control("foot_massage_1", "Massage: Foot Level 1", 0x9D, "massage"),
    Control("foot_massage_2", "Massage: Foot Level 2", 0x9E, "massage"),
    Control("foot_massage_3", "Massage: Foot Level 3", 0x9F, "massage"),
    Control("massage_constant", "Massage: Constant", 0x3A, "massage"),
    Control("massage_pulse", "Massage: Pulse", 0x38, "massage"),
    Control("massage_wave", "Massage: Wave", 0x39, "massage"),
    Control("massage_off", "Massage: Off", 0x5E, "massage"),
    Control("massage_10", "Massage: Timer 10 Minutes", 0x5F, "massage"),
    Control("massage_20", "Massage: Timer 20 Minutes", 0x63, "massage"),
    Control("massage_30", "Massage: Timer 30 Minutes", 0x61, "massage"),
)
LAYOUTS: Final = {
    "none": Layout("none", ()),
    "JHRN": Layout(
        "JHRN",
        (
            Control("foot_up", "Foot Up", 0x29, "motor", held=True),
            Control("foot_down", "Foot Down", 0x2A, "motor", held=True),
            FLAT,
        ),
    ),
    "JGRN": Layout(
        "JGRN", (*HEAD, *FOOT, *BOTH, FLAT, Control("memory_1", "Memory 1", 0x2E, "preset", 0x2B))
    ),
    "JLRM": Layout(
        "JLRM",
        (
            *HEAD,
            *FOOT,
            Control("lumbar_up", "Lumbar Up", 0x3F, "motor", held=True),
            Control("lumbar_down", "Lumbar Down", 0x40, "motor", held=True),
            FLAT,
            LIGHT,
            *MASSAGE,
            *PRESETS,
        ),
        tuple(c.key for c in PRESETS),
    ),
    "FARM": Layout(
        "FARM",
        (
            *HEAD,
            *FOOT,
            *BOTH,
            FLAT,
            LIGHT,
            Control("head_massage_off", "Massage: Head Off", 0x98, "massage"),
            Control("foot_massage_off", "Massage: Foot Off", 0x9C, "massage"),
            *MASSAGE,
            *PRESETS,
        ),
        tuple(c.key for c in PRESETS),
    ),
}
PROFILE_CHOICES: Final = {key: key for key in ("FARM", "JLRM", "JGRN", "JHRN")}


def resolve_layout(value: str) -> str:
    normalized = value.replace(" ", "").replace("\n", "").upper()
    if normalized in ("", "NONE"):
        return "none"
    if normalized not in PROFILE_CHOICES:
        raise ValueError("Choose the product identifier shown in Majestic Home")
    return normalized


def catalog(key: str) -> Catalog:
    layout = LAYOUTS[key]
    return Catalog(
        "majestichome",
        "Majestic Home",
        RichmatProfile(
            key="majestichome",
            transports=("n1", "w1", "w2", "w3", "w4", "w5"),
            epoch_first_hex=True,
        ),
        {
            c.key: Action(
                c.label,
                "sustainPress" if c.held else "shortPress",
                False,
                False,
                False,
                False,
                c.code,
                c.save or 0,
                c.code,
            )
            for c in layout.controls
        },
        {
            key: Product(
                key,
                tuple(c.key for c in layout.controls),
                layout.alarms,
                (0,),
                False,
                "",
                bool(layout.alarms),
                "deviceSleepMonitoringNone",
                False,
            )
        },
        {},
        record=record,
        reply_gated_menus=True,
        startup=(("deviceFunctionItemExitLimit", 0), ("deviceFunctionItemCheckClock", 1)),
    )
