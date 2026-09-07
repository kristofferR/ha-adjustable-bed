"""Profile and timer differences proven by the four cluster-005 app reports.

Normal key framing and BLE feedback parsing remain in ``beds.leggett_okin``.
Prodigy sleep packets bypass that key framing; U-Series timers use it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

AppProfile = Literal["prodigy2l", "prodigy2", "prodigy4", "useries"]


@dataclass(frozen=True)
class LeggettAppProfile:
    pillow: bool
    lumbar: bool
    memory_slots: int
    settings: bool


LEGGETT_APP_PROFILES: Mapping[AppProfile, LeggettAppProfile] = MappingProxyType(
    {
        "prodigy2l": LeggettAppProfile(False, True, 4, True),
        "prodigy2": LeggettAppProfile(True, False, 4, True),
        "prodigy4": LeggettAppProfile(True, True, 4, True),
        "useries": LeggettAppProfile(True, False, 2, False),
    }
)
SLEEP_CANCEL_KEY = 0xFF200000
USERIES_SLEEP_MINUTES = (15, 30, 45, 60, 75, 90)
_USERIES_SLEEP_ACTIONS = {0: 0x00100000, 1: 0, 2: 0x00010000, 3: 0x00020000}


def _validate_profile(profile: str) -> None:
    if profile not in LEGGETT_APP_PROFILES:
        raise ValueError(f"Unknown Leggett app profile: {profile}")


def _integer_range(name: str, value: int, lower: int, upper: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer between {lower} and {upper}")


def build_sleep_timer(profile: str, minutes: int, action: int) -> int | bytes:
    """Build a timer operation without guessing the connected key revision.

    Prodigy actions are favorite slots 1..4. U-Series actions are flat=0 and
    memory 1..3. Its third sleep action is distinct from a direct recall button.
    """
    _validate_profile(profile)
    if profile == "useries":
        _integer_range("sleep action", action, 0, 3)
        _integer_range("sleep minutes", minutes, 15, 90)
        if minutes not in USERIES_SLEEP_MINUTES:
            raise ValueError("U-Series sleep minutes must be a multiple of 15")
        return 0xFF000000 | _USERIES_SLEEP_ACTIONS[action] | minutes
    _integer_range("favorite slot", action, 1, 4)
    # All three apps disable 00:00 in their sleep picker. Their defensive
    # zero-to-1440 branch is not an additional selectable duration.
    _integer_range("sleep minutes", minutes, 1, 1439)
    return bytes((4, 2, 0xFF, action - 1)) + minutes.to_bytes(2, "big")


def build_alarm(profile: str, minutes: int | None) -> int:
    """Return a normal keycode; U-Series stop differs from Prodigy cancel."""
    _validate_profile(profile)
    if minutes is None:
        return 0xFD000000 if profile == "useries" else 0xFD200000
    _integer_range("alarm minutes", minutes, 1, 1440)
    return 0xFD000000 + minutes
