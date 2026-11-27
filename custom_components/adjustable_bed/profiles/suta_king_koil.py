"""King Koil 1.16.12 (com.suta.king_koil), independent M510 controls."""

from typing import Final, Literal

from .truemotion import Axis, Profile, Zone

__all__ = ["Zone"]
type AlarmOperation = Literal["SA", "CA", "DA"]

SERVICE_UUID: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
PREFIX: Final = "SUTA-"
PROFILE: Final = Profile(
    "king_koil_m510",
    (Axis("back", "BACK"), Axis("legs", "FOOT"), Axis("combined", "TWO")),
    ("M1", "SNORE", "TV", "ZEROG", "FLAT", "M8", "SWING"),
    ("M1", "SNORE", "TV", "ZEROG"),
    dedicated_stop=True,
)
RECALL_COUNT: Final = 5
SAVE_COUNT: Final = 3
SAVE_DELAY_MS: Final = 5000
REPEAT_MS: Final = 100
MASSAGE_STEPS: Final = ("00", "20", "33", "50")
MASSAGE_MODES: Final = ("00", "10", "20", "30")


def alarm(
    operation: Literal["SA", "CA", "DA"], day: int, hour: int, minute: int, loop: str = "01"
) -> str:
    if (
        day not in range(7)
        or hour not in range(24)
        or minute not in range(60)
        or loop not in ("00", "01")
    ):
        raise ValueError("Choose a weekday, time and loop value offered by the bed")
    return f"AT+{operation}=0{day}{hour:02d}{minute:02d}" + (loop if operation == "SA" else "01")


def clock(year: int, month: int, day: int, hour: int, minute: int) -> str:
    return f"AT+SD={year % 100:02d}{month:02d}{day:02d}{hour:02d}{minute:02d}"
