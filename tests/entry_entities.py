"""Add hand-built entities the way platform setup does."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from pytest_homeassistant.common import MockEntityPlatform

from custom_components.adjustable_bed.const import DOMAIN


async def async_add_entry_entities(
    hass: HomeAssistant, entry: ConfigEntry, domain: str, entities: Iterable[Entity]
) -> None:
    """Add entities through a platform bound to ``entry``.

    The domain's ``EntityComponent`` would add them without a config entry,
    which HA stops accepting for entities with device info in 2027.8.
    """
    platform = MockEntityPlatform(hass, domain=domain, platform_name=DOMAIN)
    platform.config_entry = entry
    await platform.async_add_entities(entities)
