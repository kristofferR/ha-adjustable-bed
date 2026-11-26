"""ErgoBed Control's HHC selectors and settings records."""

from dataclasses import replace
from datetime import datetime
from math import floor
from typing import ClassVar, Final

from ..codec import motomotion
from ..const import BED_TYPE_ERGOBED
from .bedgear import Control
from .bedgear import eligible as hhc_name
from .hhc_layout import HhcLetterLayout
from .motomotion import name_character

SERVICE_MARKER: Final = "ffe0"
CHARACTERISTIC_MARKER: Final = "ffe1"
STARTUP_DELAY_MS: Final = 500
SETTINGS_INTERVAL_MS: Final = 50
COLOR_COMMANDS: Final = (315, 316, 317)
TIMER_COMMAND: Final = 319
TIMER_MAX_SECONDS: Final = 540
ALARM_HEADERS: Final = ("0017", "0118", "0219")
LAYOUT_EXAMPLES: Final = (
    "01",
    "11",
    "12",
    "13",
    "19",
    "15",
    "21",
    "22",
    "23",
    "29",
    "25",
    "31",
    "32",
    "33",
    "34",
    "35",
    "41",
    "42",
    "43",
    "44",
    "46",
    "45",
    "51",
    "55",
    "61",
    "65",
    "71",
    "75",
    "81",
    "85",
    "91",
    "95",
    "96",
    "97",
    "98",
    "A1",
    "B1",
    "C1",
    "D1",
)


def eligible(name: str | None) -> bool:
    return isinstance(name, str) and hhc_name(name) and name_character(name, 8) in "0123456789ABCD"


def clock_frame(now: datetime) -> bytes:
    return motomotion.decimal_fields(f"{now.hour}{now.minute}{now.second}", "1100", record_type="A")


def color_frame(command: int, value: int) -> bytes:
    return motomotion.ascii_command(command, int(value / 255 * 120))


def rounded_timer_seconds(seconds: float) -> int:
    # The slider's nonnegative range makes half-up rounding equivalent to LibcRound.
    return floor(seconds + 0.5)


def timer_frame(seconds: float) -> bytes:
    return motomotion.ascii_command(TIMER_COMMAND, rounded_timer_seconds(seconds))


def alarm_frame(hour: int, minute: int, strength: int) -> bytes:
    return motomotion.decimal_fields(ALARM_HEADERS[strength], f"{hour:02d}{minute:02d}00")


class ErgoBedProfile(HhcLetterLayout):
    key: ClassVar[str] = BED_TYPE_ERGOBED
    panel_a_h_extra = False
    panel_three_y4_extra = False

    def __post_init__(self) -> None:
        if not eligible(self.name):
            raise ValueError("HHC name has no supported ErgoBed Control panel")

    @property
    def wrapped(self) -> bool:
        return False

    @property
    def sync(self) -> bool:
        return False

    @property
    def timer(self) -> bool:
        return True

    @property
    def rgb(self) -> bool:
        return self.char(10) == "D"

    @property
    def controls(self) -> tuple[Control, ...]:
        return tuple(replace(control, release="none") for control in super().controls)
