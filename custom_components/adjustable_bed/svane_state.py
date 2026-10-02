"""Target-local Svane app caches, separate from measured device state."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SvaneProfile = Literal["multi", "jmc"]
CONF_SVANE_PREFERENCES = "svane_remote_preferences"
_NAMESPACE = "adjustable_bed_svane_remote_sessions"
_DEFAULT_SLOTS = (bytes.fromhex("81388113"), bytes.fromhex("82738204"))


def integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Expected integer from {minimum} to {maximum}")
    return value


def svane_preferences(value: object) -> tuple[int, tuple[bytes, bytes]]:
    """Validate preferences before I/O; defaults never count as observed position."""
    if value is None:
        return 90, _DEFAULT_SLOTS
    if not isinstance(value, Mapping):
        raise ValueError("Svane preferences must be an object")
    intensity = integer(value.get("intensity", 90), 5, 100)
    if intensity % 5:
        raise ValueError("Svane intensity uses steps of five")
    slots = value.get("slots")
    if slots is None:
        return intensity, _DEFAULT_SLOTS
    if not isinstance(slots, list) or len(slots) != 2:
        raise ValueError("Svane requires two raw memory slots")
    result = []
    for raw in slots:
        if not isinstance(raw, str) or re.fullmatch(r"[0-9a-fA-F]{8}", raw) is None:
            raise ValueError("Svane JMC memory is four opaque bytes")
        result.append(bytes.fromhex(raw))
    return intensity, (result[0], result[1])


@dataclass(slots=True)
class SvaneSession:
    """Local intent and raw cache, never an ACK or physical measurement."""

    intensity: int = 90
    light_on: bool = False
    light_intent_known: bool = False
    light_step: int = 5
    head: bytes | None = None
    feet: bytes | None = None
    position: bytes | None = None
    observations: dict[str, str] = field(default_factory=dict)
    multi_slots: dict[int, tuple[bytes, bytes]] = field(default_factory=dict)
    jmc_slots: tuple[bytes, bytes] = _DEFAULT_SLOTS
    head_release_epoch: int = 0
    feet_release_epoch: int = 0

    def preferences(self) -> dict[str, object]:
        return {"intensity": self.intensity, "slots": [raw.hex() for raw in self.jmc_slots]}


@dataclass(slots=True)
class _Sessions:
    targets: dict[tuple[str, SvaneProfile], SvaneSession] = field(default_factory=dict)


def get_svane_session(
    hass: HomeAssistant,
    address: str,
    profile: SvaneProfile,
    preferences: object = None,
) -> SvaneSession:
    """Retain physical intent over same-process BLE rebuilds and entry reloads."""
    address = address.upper()
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address) is None:
        raise ValueError("Svane session requires an exact physical address")
    if profile not in ("multi", "jmc"):
        raise ValueError("Unknown Svane app profile")
    intensity, slots = svane_preferences(preferences)
    cache = hass.data.get(_NAMESPACE)
    if not isinstance(cache, _Sessions):
        cache = _Sessions()
        hass.data[_NAMESPACE] = cache
    for key in tuple(cache.targets):
        if key[0] == address and key[1] != profile:
            del cache.targets[key]
    key = (address, profile)
    session = cache.targets.get(key)
    if session is None:
        session = SvaneSession(intensity=intensity, jmc_slots=slots)
        cache.targets[key] = session
    return session


def clear_svane_session(hass: HomeAssistant, address: str) -> None:
    """Reset only an explicitly changed physical app profile."""
    cache = hass.data.get(_NAMESPACE)
    if isinstance(cache, _Sessions):
        for key in tuple(cache.targets):
            if key[0] == address.upper():
                del cache.targets[key]


def svane_profile_for_selected_name(name: str | None) -> SvaneProfile:
    """Source rule for a newly selected app target, never an existing entry migration."""
    return "jmc" if name is not None and "JMC" in name else "multi"


def is_svane_discovery_name(name: str | None) -> bool:
    """Exact app allowlist; known manual targets may bypass this scan filter."""
    return name in ("Svane Bed", "JMC400")
