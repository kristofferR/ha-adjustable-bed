"""Process-local app intent for one physical target, never measured device state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .app_session import app_session, drop_app_sessions

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ControlType = int | Literal["other"]


def _integer(value: int, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Intent value must be an integer from {minimum} to {maximum}")


@dataclass(slots=True)
class VibradormAppFloorIntent:
    """Current process intent and remembered brightness, independent of BLE state."""

    level: int = 0
    default_level: int = 6

    def __post_init__(self) -> None:
        _integer(self.level, 0, 8)
        _integer(self.default_level, 1, 8)


@dataclass(slots=True)
class VibradormAppTimerIntent:
    """Pending process timer selection; zero means no minutes selected yet."""

    enabled: bool = False
    minutes: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("Timer enabled intent must be a boolean")
        _integer(self.minutes, 0, 60)


@dataclass(slots=True)
class VibradormAppMassageIntent:
    effect: int = 0
    speed: int = 1
    zones: tuple[int, int] = (0, 0)
    saved_zones: tuple[int, int] = (3, 3)
    saved_effect: int = 1
    saved_speed: int = 1
    flags: tuple[bool, bool] = (False, False)
    saved_flags: tuple[bool, bool] = (False, False)
    automatic: int = 8
    individual: int = 10
    zone_states: tuple[int, int] = (8, 8)
    wave: int = 8

    def indicators(self) -> None:
        if all(self.zones):
            if self.effect:
                self.automatic, self.wave, self.individual, self.zone_states = 7, 7, 10, (8, 8)
            else:
                self.individual, self.zone_states = 9, (7, 7)
        if not any(self.zones):
            self.wave, self.zone_states = 8, (8, 8)
        states = list(self.zone_states)
        for index, flag in enumerate(self.flags):
            if flag:
                self.individual, states[index] = 9, 7
        self.zone_states = (states[0], states[1])
        self.wave = 7 if self.effect else 8

    def callback(self, code: int) -> bool:
        """Mutate the distinct saved settings/flags; return whether OFF is written."""
        zones, saved = list(self.zones), list(self.saved_zones)
        flags, saved_flags = list(self.flags), list(self.saved_flags)
        if code in (1, 2, 3, 4):
            index = 0 if code < 3 else 1
            zones[index] = (
                min(5, zones[index] + 1)
                if code in (1, 3)
                else max(1 if self.effect else 0, zones[index] - 1)
            )
        elif code in (5, 6):
            index = code - 5
            if not zones[index]:
                zones[index], flags[index] = saved[index] or 3, True
            else:
                saved[index], saved_flags[index], zones[index], flags[index] = (
                    zones[index],
                    flags[index],
                    0,
                    False,
                )
        elif code == 7:
            self.effect, self.speed = self.saved_effect, self.saved_speed
            zones = saved.copy()
            if not any(zones):
                zones = [3, 3]
        elif code == 8:
            saved, zones = zones.copy(), [0, 0]
            self.saved_effect, self.saved_speed, self.effect, self.speed = (
                self.effect,
                self.speed,
                0,
                1,
            )
        elif code == 9:
            flags = saved_flags.copy()
            for index, flag in enumerate(flags):
                if flag:
                    zones[index] = saved[index] or 3
        elif code == 10:
            saved_flags, flags = flags.copy(), [False, False]
            for index, flag in enumerate(saved_flags):
                if flag:
                    saved[index], zones[index] = zones[index], 0
        self.zones, self.saved_zones = (zones[0], zones[1]), (saved[0], saved[1])
        self.flags, self.saved_flags = (flags[0], flags[1]), (saved_flags[0], saved_flags[1])
        return code in (8, 10)


@dataclass(slots=True)
class VibradormAppSessionIntent:
    """Explicit floor and timer holders shared across same-process reconnects."""

    floor: VibradormAppFloorIntent = field(default_factory=VibradormAppFloorIntent)
    timer: VibradormAppTimerIntent = field(default_factory=VibradormAppTimerIntent)
    massage: VibradormAppMassageIntent = field(default_factory=VibradormAppMassageIntent)
    mood: dict[str, str | int] = field(default_factory=dict)


def _address(address: str) -> str:
    target = address.upper()
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", target) is None:
        raise ValueError("App intent requires an exact physical Bluetooth address")
    return target


def _key(
    address: str, app_profile: str, control_type: ControlType, remote: str | None,
) -> tuple[str, str, ControlType, str | None]:
    if app_profile not in ("caresse", "werkmeister", "vmat"):
        raise ValueError("Unknown app profile")
    if app_profile == "vmat":
        from .vibradorm_vmat_profiles import get_vmat_remote

        if control_type != get_vmat_remote(remote).control_type or isinstance(control_type, bool):
            raise ValueError("VMAT control type must match its exact remote")
    elif remote is not None:
        raise ValueError("VMAT remote cannot be used with another app")
    if control_type != "other":
        _integer(control_type, -1, 9 if app_profile == "vmat" else 7)
    if app_profile == "werkmeister" and control_type not in (5, 7):
        raise ValueError("Invalid Werkmeister control type")
    return (_address(address), app_profile, control_type, remote)


def get_vibradorm_app_session_intent(
    hass: HomeAssistant, address: str, *, app_profile: str, control_type: ControlType,
    remembered_floor_default: int,
    remote: str | None = None,
) -> VibradormAppSessionIntent:
    """Get exact-target intent; a cold configured process starts with level zero."""
    _integer(remembered_floor_default, 1, 8)
    target, *profile = _key(address, app_profile, control_type, remote)
    # Changing back to an earlier profile does not resurrect its old session.
    intent = app_session(
        hass, target, ("vibradorm_app", *profile), VibradormAppSessionIntent
    )
    intent.floor.default_level = remembered_floor_default
    return intent


def mark_vibradorm_app_selection(
    hass: HomeAssistant, address: str, *, app_profile: str, control_type: ControlType,
    remembered_floor_default: int = 6,
    remote: str | None = None,
) -> VibradormAppSessionIntent:
    """Seed successful fresh selection in this process without a persisted flag."""
    _integer(remembered_floor_default, 1, 8)
    if remembered_floor_default != 6:
        raise ValueError("A fresh app selection remembers brightness six")
    _key(address, app_profile, control_type, remote)
    clear_vibradorm_app_session_intent(hass, address)
    intent = get_vibradorm_app_session_intent(
        hass, address, app_profile=app_profile, control_type=control_type,
        remembered_floor_default=remembered_floor_default,
        remote=remote,
    )
    intent.floor.level = 6
    return intent


def clear_vibradorm_app_session_intent(hass: HomeAssistant, address: str) -> None:
    """Forget only a changed physical target/profile, never ordinary BLE teardown."""
    drop_app_sessions(hass, _address(address))
