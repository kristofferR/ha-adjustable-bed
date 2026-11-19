"""Typed access to ``hass.data[DOMAIN]``.

The dict holds each loaded config entry's runtime under its entry ID, and a few
integration-wide registries under their own ``DomainKey``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator
    from .paired_coordinator import PairedBedCoordinator

type EntryRuntime = AdjustableBedCoordinator | PairedBedCoordinator


class DomainKey[T](str):
    """A key in ``hass.data[DOMAIN]`` that carries the type of its value."""

    __slots__ = ()


def loaded_runtime(hass: HomeAssistant, entry_id: str) -> EntryRuntime | None:
    """Return the runtime a loaded config entry stored, if any."""
    return cast("EntryRuntime | None", hass.data.get(DOMAIN, {}).get(entry_id))


def entry_runtime(hass: HomeAssistant, entry_id: str) -> EntryRuntime:
    """Return the runtime setup stored before forwarding the entry to a platform."""
    return cast("EntryRuntime", hass.data[DOMAIN][entry_id])


def domain_value[T](hass: HomeAssistant, key: DomainKey[T]) -> T | None:
    """Return a registry if one was created."""
    return cast("T | None", hass.data.get(DOMAIN, {}).get(key))


def domain_registry[T](hass: HomeAssistant, key: DomainKey[T], factory: Callable[[], T]) -> T:
    """Return a registry, creating it on first use."""
    return cast("T", hass.data.setdefault(DOMAIN, {}).setdefault(key, factory()))
