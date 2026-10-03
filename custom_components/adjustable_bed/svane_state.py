"""Target-local Svane app sessions and preferences, separate from measured device state."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .app_session import app_session

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SvaneProfile = Literal["multi", "jmc"]
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
    svane_multi_slots(value)
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


def svane_multi_slots(value: object) -> dict[int, tuple[bytes, bytes]]:
    """Validate persisted P1 slots: opaque head/feet bytes read from this bed."""
    if not isinstance(value, Mapping) or value.get("multi_slots") is None:
        return {}
    stored = value["multi_slots"]
    if not isinstance(stored, Mapping):
        raise ValueError("Svane P1 memory must be an object")
    result: dict[int, tuple[bytes, bytes]] = {}
    for slot, axes in stored.items():
        if slot not in ("1", "2") or not isinstance(axes, list) or len(axes) != 2:
            raise ValueError("Svane P1 memory has two slots of head and feet bytes")
        if any(
            not isinstance(raw, str) or re.fullmatch(r"(?:[0-9a-fA-F]{2})+", raw) is None
            for raw in axes
        ):
            raise ValueError("Svane P1 memory axes are nonempty opaque bytes")
        result[int(slot)] = (bytes.fromhex(axes[0]), bytes.fromhex(axes[1]))
    return result


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

    def restore(self, preferences: Mapping[str, object]) -> None:
        """Apply stored preferences after validating all of them."""
        intensity, slots = svane_preferences(preferences)
        multi_slots = svane_multi_slots(preferences)
        self.intensity, self.jmc_slots, self.multi_slots = intensity, slots, multi_slots

    def preferences(self) -> dict[str, object]:
        preferences: dict[str, object] = {
            "intensity": self.intensity,
            "slots": [raw.hex() for raw in self.jmc_slots],
        }
        if self.multi_slots:
            # Saved P1 positions survive restarts, unlike the app's process memory.
            preferences["multi_slots"] = {
                str(slot): [head.hex(), feet.hex()]
                for slot, (head, feet) in sorted(self.multi_slots.items())
            }
        return preferences


def get_svane_session(hass: HomeAssistant, address: str, profile: SvaneProfile) -> SvaneSession:
    """Retain physical intent over same-process BLE rebuilds and entry reloads."""
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address.upper()) is None:
        raise ValueError("Svane session requires an exact physical address")
    if profile not in ("multi", "jmc"):
        raise ValueError("Unknown Svane app profile")
    return app_session(hass, address, ("svane", profile), SvaneSession)


def svane_profile_for_selected_name(name: str | None) -> SvaneProfile:
    """Source rule for a newly selected app target, never an existing entry migration."""
    return "jmc" if name is not None and "JMC" in name else "multi"


def is_svane_discovery_name(name: str | None) -> bool:
    """Exact app allowlist; known manual targets may bypass this scan filter."""
    return name in ("Svane Bed", "JMC400")
