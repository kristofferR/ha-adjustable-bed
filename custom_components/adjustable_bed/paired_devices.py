"""Native child-device identity and reversible paired-device migration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_PAIR_MODE, DOMAIN, PAIR_MODE_SINGLE_ADDRESS
from .pairing import KEY_ABSORBED_ENTRY_ID, get_child

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .paired_coordinator import PairedBedCoordinator

KEY_PHYSICAL_DEVICES = "pair_physical_devices"
DEVICE_REMOVAL_TIMEOUT = 5.0
_LOGGER = logging.getLogger(__name__)
_METADATA_FIELDS = (
    "name",
    "manufacturer",
    "model",
    "model_id",
    "hw_version",
    "sw_version",
    "serial_number",
    "configuration_url",
)


def side_identifier(coordinator: PairedBedCoordinator, side: str) -> tuple[str, str]:
    """Keep physical identities for two-link pairs; namespace logical sides."""
    if coordinator.entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
        return DOMAIN, f"{coordinator.pair_id}_{side}"
    return DOMAIN, coordinator.children[side].address


def child_device_info(coordinator: PairedBedCoordinator, side: str) -> dr.ChildDeviceInfo:
    """Describe a side without exposing physical-only fields on a child.

    A two-address side keeps its own bed's name. A single-address side shares
    the physical bed's name, so its device name carries the side and its
    entities' names need not.
    """
    registry = dr.async_get(coordinator.hass)
    parent_identifier = next(iter(coordinator.device_info.get("identifiers", set())))
    parent = registry.async_get_device_by_identifier(parent_identifier, coordinator.entry.entry_id)
    if parent is None:
        raise RuntimeError("Paired parent device must be registered before its entities")
    name = coordinator.children[side].name
    if coordinator.entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS:
        return dr.ChildDeviceInfo(
            identifiers={side_identifier(coordinator, side)},
            parent_device_id=parent.id,
            translation_key=f"{side}_side",
            translation_placeholders={"name": name},
        )
    return dr.ChildDeviceInfo(
        identifiers={side_identifier(coordinator, side)},
        parent_device_id=parent.id,
        name=name,
    )


def async_register_children(hass: HomeAssistant, coordinator: PairedBedCoordinator) -> None:
    """Migrate old full side devices in place, retaining hardware metadata."""
    registry = dr.async_get(hass)
    entry = coordinator.entry
    metadata = dict(entry.data.get(KEY_PHYSICAL_DEVICES, {}))
    sides = {
        side: child
        for side, child in coordinator.children.items()
        if not (
            entry.data.get(CONF_PAIR_MODE) != PAIR_MODE_SINGLE_ADDRESS
            and (source_id := (get_child(entry.data, side) or {}).get(KEY_ABSORBED_ENTRY_ID))
            and hass.config_entries.async_get_entry(source_id) is not None
        )
    }
    for side, child in sides.items():
        identifier = side_identifier(coordinator, side)
        existing = registry.async_get_device_by_identifier(identifier, entry.entry_id)
        if existing is not None:
            metadata[side] = {
                **{key: getattr(existing, key) for key in _METADATA_FIELDS},
                "connections": sorted(existing.connections),
            }
        else:
            info = child.device_info
            metadata[side] = {
                **metadata.get(side, {}),
                **{
                    key: info.get(key)
                    for key in _METADATA_FIELDS
                    if info.get(key) is not None and key not in metadata.get(side, {})
                },
            }
    # Persist before conversion: child records deliberately have no hardware fields.
    if metadata != entry.data.get(KEY_PHYSICAL_DEVICES):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, KEY_PHYSICAL_DEVICES: metadata}
        )
    for side in sides:
        registry.async_get_or_create_child_from_info(
            config_entry_id=entry.entry_id, device_info=child_device_info(coordinator, side)
        )


async def async_restore_full_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: dr.ChildDeviceEntry,
    side: str,
) -> dr.DeviceEntry:
    """Restore a side to a full device while its config entry is unloaded.

    HA supports full-to-child conversion, but the reverse uses its deleted-device
    restoration API. Detach entity rows until the removal event has been consumed
    so HA cannot delete them. The deleted record retains the device id and user
    customizations; the config entry retains physical metadata.
    """
    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    if registry.async_get(device.id) is None:
        raise ValueError(f"Child device {device.id} no longer exists")
    rows = tuple(er.async_entries_for_device(entities, device.id, include_disabled_entities=True))
    removed: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    removal_completed = False
    restore_succeeded = False
    deadline = asyncio.get_running_loop().time() + DEVICE_REMOVAL_TIMEOUT

    @callback
    def on_removed(event: Event[dr.EventDeviceRegistryUpdatedData]) -> None:
        if event.data["action"] == "remove" and event.data["device_id"] == device.id:
            if not removed.done():
                removed.set_result(None)

    unsub = hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, on_removed)
    try:
        for row in rows:
            entities.async_update_entity(row.entity_id, device_id=None)
        registry.async_remove_device(device.id)
        removal_completed = True
        async with asyncio.timeout_at(deadline):
            await asyncio.shield(removed)
        metadata = entry.data.get(KEY_PHYSICAL_DEVICES, {}).get(side, {})
        restored = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers=set(device.identifiers),
            connections={tuple(value) for value in metadata.get("connections", [])},
            **{key: metadata[key] for key in _METADATA_FIELDS if key in metadata},
        )
        if restored.id != device.id:
            raise RuntimeError("Home Assistant did not restore the original side device id")
        restore_succeeded = True
        return restored
    finally:
        try:
            if registry.async_get(device.id) is None:
                # Roll back a failed restore before reattaching rows. The removal
                # event must finish first, including on cancellation.
                if removal_completed and not removed.done():
                    try:
                        async with asyncio.timeout_at(deadline):
                            await asyncio.shield(removed)
                    except TimeoutError:
                        _LOGGER.warning("Device removal event missing for %s", device.id)
                registry.async_get_or_create_child(
                    config_entry_id=entry.entry_id,
                    identifiers=set(device.identifiers),
                    parent_device_id=device.parent_device_id,
                    name=device.name,
                )
        except Exception:
            _LOGGER.exception("Could not restore child device %s during rollback", device.id)
        finally:
            try:
                reattach_error: Exception | None = None
                if registry.async_get(device.id) is not None:
                    for row in rows:
                        try:
                            entities.async_update_entity(row.entity_id, device_id=device.id)
                        except Exception as err:
                            reattach_error = reattach_error or err
                            _LOGGER.exception("Could not reattach entity %s", row.entity_id)
                else:
                    _LOGGER.error("Device %s is missing; entity rows retained for recovery", device.id)
                if restore_succeeded and reattach_error is not None:
                    raise reattach_error
            finally:
                unsub()
                registry.async_config_entry_unloaded(entry.entry_id)
