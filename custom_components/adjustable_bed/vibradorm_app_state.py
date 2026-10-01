"""Process-local app intent for one physical target, never measured device state."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ControlType = int | Literal["other"]
_STATE_NAMESPACE = "adjustable_bed_vibradorm_app_session_intents"


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
class VibradormAppSessionIntent:
    """Explicit floor and timer holders shared across same-process reconnects."""

    floor: VibradormAppFloorIntent = field(default_factory=VibradormAppFloorIntent)
    timer: VibradormAppTimerIntent = field(default_factory=VibradormAppTimerIntent)


@dataclass(slots=True)
class _IntentCache:
    targets: dict[tuple[str, str, ControlType], VibradormAppSessionIntent] = field(default_factory=dict)


def _address(address: str) -> str:
    target = address.upper()
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", target) is None:
        raise ValueError("App intent requires an exact physical Bluetooth address")
    return target


def _key(address: str, app_profile: str, control_type: ControlType) -> tuple[str, str, ControlType]:
    if app_profile not in ("caresse", "werkmeister"):
        raise ValueError("Unknown app profile")
    if control_type != "other":
        _integer(control_type, -1, 7)
    if app_profile == "werkmeister" and control_type not in (5, 7):
        raise ValueError("Invalid Werkmeister control type")
    return (_address(address), app_profile, control_type)


def _cache(hass: HomeAssistant) -> _IntentCache:
    cached = hass.data.get(_STATE_NAMESPACE)
    if not isinstance(cached, _IntentCache):
        cached = _IntentCache()
        hass.data[_STATE_NAMESPACE] = cached
    return cached


def get_vibradorm_app_session_intent(
    hass: HomeAssistant, address: str, *, app_profile: str, control_type: ControlType,
    remembered_floor_default: int,
) -> VibradormAppSessionIntent:
    """Get exact-target intent; a cold configured process starts with level zero."""
    _integer(remembered_floor_default, 1, 8)
    key = _key(address, app_profile, control_type)
    cache = _cache(hass)
    # Changing back to an earlier profile must not resurrect its old session.
    for existing in tuple(cache.targets):
        if existing[0] == key[0] and existing != key:
            del cache.targets[existing]
    intent = cache.targets.get(key)
    if intent is None:
        intent = VibradormAppSessionIntent(
            floor=VibradormAppFloorIntent(default_level=remembered_floor_default)
        )
        cache.targets[key] = intent
    else:
        intent.floor.default_level = remembered_floor_default
    return intent


def mark_vibradorm_app_selection(
    hass: HomeAssistant, address: str, *, app_profile: str, control_type: ControlType,
    remembered_floor_default: int = 6,
) -> VibradormAppSessionIntent:
    """Seed successful fresh selection in this process without a persisted flag."""
    _integer(remembered_floor_default, 1, 8)
    if remembered_floor_default != 6:
        raise ValueError("A fresh app selection remembers brightness six")
    _key(address, app_profile, control_type)
    clear_vibradorm_app_session_intent(hass, address)
    intent = get_vibradorm_app_session_intent(
        hass, address, app_profile=app_profile, control_type=control_type,
        remembered_floor_default=remembered_floor_default,
    )
    intent.floor.level = 6
    return intent


def clear_vibradorm_app_session_intent(hass: HomeAssistant, address: str) -> None:
    """Forget only a changed physical target/profile, never ordinary BLE teardown."""
    target = _address(address)
    cached = hass.data.get(_STATE_NAMESPACE)
    if isinstance(cached, _IntentCache):
        for key in tuple(cached.targets):
            if key[0] == target:
                del cached.targets[key]
