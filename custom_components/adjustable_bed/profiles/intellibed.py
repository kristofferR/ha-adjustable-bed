"""Intellibed Sleep Genius 2.1.67: explicit OLD and HHC non-motion routes.

No STOP, physical refresh timeout or position parser is established. The app's
four-byte HHC voice timer is deliberately outside the exposed binary actions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from ..codec import keeson, motomotion
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

CHOICES: Final = {"old": "Old / white remote", "hhc": "HHC / silver remote"}


def uuid(short: str) -> str:
    return f"0000{short}-0000-1000-8000-00805f9b34fb"


@dataclass(frozen=True, slots=True)
class Action:
    label: str
    command: int
    parameter: int = 0
    delay_ms: int = 0
    light: bool = False


@dataclass(frozen=True, slots=True)
class Profile:
    key: Literal["old", "hhc"]
    write_service: str
    write_uuid: str
    notify_service: str
    notify_uuid: str
    actions: Mapping[str, Action]
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    # The screen dispatches only FFE4, even when HHC subscribes to FFE1.
    ui_notify_uuid: str = uuid("ffe4")

    def encode(self, action: Action) -> bytes:
        if self.key == "old":
            return keeson.frame(action.command)
        return motomotion.binary_command(action.command, action.parameter)


PROFILES: Final[dict[str, Profile]] = {
    "old": Profile(
        "old",
        uuid("ffe5"),
        uuid("ffe9"),
        uuid("ffe0"),
        uuid("ffe4"),
        {
            "head_up": Action("Increase head massage", 0x800, 0, 0, False),
            "head_down": Action("Decrease head massage", 0x800000, 0, 0, False),
            "feet_up": Action("Increase feet massage", 0x400, 0, 0, False),
            "feet_down": Action("Decrease feet massage", 0x1000000, 0, 0, False),
            "massage_off": Action("Stop all massage", 0x2000000, 0, 0, False),
            "timer_cycle": Action("Increase massage timer", 0x200, 0, 0, False),
            "light_toggle": Action("Light toggle", 0x20000, 0, 100, True),
        },
    ),
    "hhc": Profile(
        "hhc",
        uuid("ffe0"),
        uuid("ffe1"),
        uuid("ffe0"),
        uuid("ffe1"),
        {
            "head_up": Action("Increase head massage", 0x8102, 0, 0, False),
            "head_down": Action("Decrease head massage", 0x8104, 0, 0, False),
            "feet_up": Action("Increase feet massage", 0x8103, 0, 0, False),
            "feet_down": Action("Decrease feet massage", 0x8105, 0, 0, False),
            "massage_off": Action("Stop all massage", 0x8100, 0, 0, False),
            "head_off": Action("Head massage off", 0x8279, 0, 100, False),
            "head_low": Action("Head massage low", 0x8279, 40, 100, False),
            "head_medium": Action("Head massage medium", 0x8279, 80, 100, False),
            "head_high": Action("Head massage high", 0x8279, 120, 100, False),
            "feet_off": Action("Feet massage off", 0x827A, 0, 100, False),
            "feet_low": Action("Feet massage low", 0x827A, 40, 100, False),
            "feet_medium": Action("Feet massage medium", 0x827A, 80, 100, False),
            "feet_high": Action("Feet massage high", 0x827A, 120, 100, False),
            "light_on": Action("White light on", 0x80F1, 0, 100, True),
            "light_off": Action("White light off", 0x80F2, 0, 100, True),
        },
    ),
}
