"""The TEST and RMCS layouts, which held only a factory motor test and motor programming.

A v5 beta could save one. Nothing tells which layout the bed really uses, so
such a bed loads without controls or a connection until a layout is chosen in
Configure, which refuses the saved one.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ...const import CONF_PRODUCT_TYPE

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

REMOVED_LAYOUTS: Final = frozenset({"TEST", "RMCS"})


async def async_load_removed_layout_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    finish: Callable[[], Awaitable[None]],
) -> bool:
    """Load a bed saved on a removed layout without connecting to it."""
    del hass, coordinator
    if str(entry.data.get(CONF_PRODUCT_TYPE, "")).strip().upper() not in REMOVED_LAYOUTS:
        return False
    _LOGGER.warning(
        "%s uses a factory-test layout that is no longer offered; choose its layout in Configure",
        entry.title,
    )
    await finish()
    return True
