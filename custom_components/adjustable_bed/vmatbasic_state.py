"""Exact-target mood intent for a continuous HA control session, without feedback."""

import re
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

_NAMESPACE = "adjustable_bed_vmatbasic_session_intents"


@dataclass(slots=True)
class VMatBasicSessionIntent:
    """The selected fragment color and brightness, never measured hardware state."""

    palette: str = "col20"
    brightness: int = 100
    effect: str | None = None
    speed: int | None = None


@dataclass(slots=True)
class _TargetIntent:
    profile: str
    intent: VMatBasicSessionIntent


def get_vmatbasic_session_intent(
    hass: HomeAssistant, address: str, profile: str
) -> VMatBasicSessionIntent:
    """Preserve a same-target session across BLE reconstruction, not a cold HA start."""
    target = address.upper()
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", target) is None:
        raise ValueError("V-MAT Basic intent requires an exact physical Bluetooth address")
    if profile not in ("basic", "cbi", "xtbox"):
        raise ValueError("Unknown V-MAT Basic profile")
    cache = hass.data.setdefault(_NAMESPACE, {})
    previous = cache.get(target)
    if not isinstance(previous, _TargetIntent) or previous.profile != profile:
        previous = _TargetIntent(profile, VMatBasicSessionIntent())
        cache[target] = previous
    return previous.intent
