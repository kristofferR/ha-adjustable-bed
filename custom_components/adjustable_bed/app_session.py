"""Process-local app sessions, one per physical address and app profile.

Home Assistant rebuilds a controller on every connection, so state a phone app
keeps for as long as it runs (sequence counters, selected presets, light
intent, values shared by a bed's offline and live controllers) lives here. A
session survives reconnects and entry reloads. By default, asking for a
different profile on the same address starts a fresh session and forgets the
others, so changing back never resurrects an old one. Entry removal drops an
address's sessions together with its stored app state
(``app_state_store.async_remove_app_states``).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any, cast

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_KEY = "app_sessions"


def app_session[T](
    hass: HomeAssistant,
    address: str,
    profile: Hashable,
    factory: Callable[[], T],
    *,
    exclusive: bool = True,
) -> T:
    """Return the session for one address and profile, creating it with ``factory``.

    ``profile`` must start with a name unique to the session type, which is what
    makes the returned object's type match ``T``. A non-exclusive profile keeps
    the address's other sessions, for apps whose offline and live controllers
    may resolve different profiles at the same time.
    """
    registry: dict[str, dict[Hashable, Any]] = hass.data.setdefault(DOMAIN, {}).setdefault(_KEY, {})
    sessions = registry.setdefault(address.upper(), {})
    if profile in sessions:
        return cast(T, sessions[profile])
    if exclusive:
        sessions.clear()
    session = sessions[profile] = factory()
    return session


def drop_app_sessions(hass: HomeAssistant, address: str) -> None:
    """Forget an address's sessions (profile change or entry removal)."""
    registry = hass.data.get(DOMAIN, {}).get(_KEY)
    if isinstance(registry, dict):
        registry.pop(address.upper(), None)
