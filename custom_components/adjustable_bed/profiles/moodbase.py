"""MoodBase's HHC layout, command fields and independent Bluetooth name flags."""

from typing import ClassVar, Final

from ..codec import motomotion
from ..const import BED_TYPE_MOODBASE
from .bedgear import eligible
from .hhc_layout import HhcLetterLayout

LAYOUT_EXAMPLES: Final = (
    "15",
    "35",
    "E1",
    "81",
    "51",
    "44",
    "91",
    "13",
    "71",
    "61",
    "D1",
    "34",
    "23",
    "01",
    "97",
    "25",
    "55",
    "65",
    "75",
    "95",
    "96",
    "98",
    "41",
    "42",
    "43",
    "31",
    "32",
    "11",
    "12",
    "21",
    "22",
    "45",
    "85",
    "C1",
    "B1",
    "Z4",
)

SERVICE_MARKER: Final = "ffe0"
CHARACTERISTIC_MARKER: Final = "ffe1"
CHARACTERISTIC_UUID: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"
CARRIER_SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
COLOR_COMMANDS: Final = (315, 316, 317)
COLOR_INTERVAL_MS: Final = 100
SETTINGS_DELAY_MS: Final = 50
TIMER_COMMAND: Final = 319
SYNC_MODE_COMMAND: Final = 33049
SYNC_ENABLE: Final = 12
SYNC_DISABLE: Final = 15
SAVE_SNORE: Final = "W"
TIMER_DEFAULT_MINUTES: Final = 10
TIMER_MAX_MINUTES: Final = 23 * 60 + 59
VIBRATION_MAX: Final = 22


def receiver_hint(name: str | None, service_uuids: list[str]) -> bool:
    """Corroborate the shared HHC carrier, without identifying a companion app."""
    return eligible(name) and any(SERVICE_MARKER in uuid.lower() for uuid in service_uuids)


def lighting_frame(command: int, value: int) -> bytes:
    """MoodBase puts the value in the first decimal field."""
    return motomotion.ascii_command(value, command)


class MoodBaseProfile(HhcLetterLayout):
    key: ClassVar[str] = BED_TYPE_MOODBASE
    panel_d_h_extra = True
    panel_zero_massage_held = False

    @property
    def timer(self) -> bool:
        return self.wrapped

    @property
    def rgb(self) -> bool:
        return self.wrapped and self.char(10) == "D"

    @property
    def vibration(self) -> bool:
        return self.char(10) == "B"
