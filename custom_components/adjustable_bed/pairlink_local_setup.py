"""Pairlink's local peripheral role: adapter leases, setup and transfers.

A peripheral-role Pairlink entry runs a local BlueZ profile instead of a Bleak
central connection. Each selected adapter is leased to one owner, and a paired
entry can take over the lease of the single entry it absorbs.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    BED_TYPE_REVERIE_PAIRLINK,
    CONF_BED_TYPE,
    CONF_PAIRLINK_HOST_SOURCE,
    CONF_PAIRLINK_ROLE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    PAIRLINK_ROLE_PERIPHERAL,
)
from .controller_factory import create_controller
from .coordinator import AdjustableBedCoordinator
from .pairing import KEY_ABSORBED_ENTRY_ID, get_child, is_paired

if TYPE_CHECKING:
    from .beds.reverie_pairlink_runtime import PairlinkRuntime
    from .beds.reverie_pairlink_transport import PairlinkHostAdapterInventoryEntry
    from .paired_coordinator import PairedBedCoordinator

_LOGGER = logging.getLogger(__name__)

PAIRLINK_LOCAL_PROFILE_LEASES_KEY = "_pairlink_local_profile_leases"


@dataclass(frozen=True, slots=True)
class PairlinkLocalLeaseTransfer:
    side: str
    original: AdjustableBedCoordinator
    entry: ConfigEntry
    runtime: PairlinkRuntime
    source: str
    adapter: str
    owner: str


def _trusted_absorbed_single(
    hass: HomeAssistant, entry: ConfigEntry, side: str, child: AdjustableBedCoordinator,
) -> tuple[ConfigEntry | None, AdjustableBedCoordinator | None]:
    """Validate a descriptor before it can identify an existing lease owner."""
    if not child.entry.data.get(KEY_ABSORBED_ENTRY_ID):
        return None, None
    descriptor = get_child(entry.data, side)
    absorbed_id = descriptor.get(KEY_ABSORBED_ENTRY_ID) if descriptor is not None else None
    if not absorbed_id:
        return None, None
    original = hass.config_entries.async_get_entry(absorbed_id)
    if original is None:
        return None, None
    if (
        is_paired(original.data)
        or str(original.data.get(CONF_ADDRESS, "")).upper() != child.address
        or original.data.get(CONF_BED_TYPE) != child.bed_type
        or (
            descriptor is not None
            and descriptor.get("origin_unique_id") is not None
            and descriptor.get("origin_unique_id") != original.unique_id
        )
    ):
        raise ConfigEntryNotReady("Absorbed bed identity does not match its paired side")
    coordinator = hass.data.get(DOMAIN, {}).get(absorbed_id)
    if coordinator is not None and (
        not isinstance(coordinator, AdjustableBedCoordinator)
        or coordinator.entry is not original
        or coordinator.address != child.address
    ):
        raise ConfigEntryNotReady("Absorbed bed runtime does not match its config entry")
    return original, coordinator


def release_pairlink_local_reservations(
    hass: HomeAssistant,
    roles: list[tuple[str, AdjustableBedCoordinator, str, str, str]],
    transfers: list[PairlinkLocalLeaseTransfer],
) -> None:
    """Keep predecessor reservations held until their rollback or commit."""
    retained = {transfer.adapter for transfer in transfers}
    for _side, _child, _source, adapter, owner in roles:
        if adapter not in retained:
            release_pairlink_local_profile_lease(hass, owner, adapter)


async def async_restore_pairlink_local_transfers(
    hass: HomeAssistant, parent: PairedBedCoordinator | None,
    transfers: list[PairlinkLocalLeaseTransfer],
    inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
) -> None:
    """Settle source restoration before propagating caller cancellation."""
    if not transfers:
        return
    task = hass.async_create_task(
        async_restore_pairlink_local_sources(hass, parent, transfers, inventory),
        "adjustable_bed.pairlink_transfer_rollback",
    )
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Keep cleanup isolated from every caller cancellation.
            cancelled = True
    task.result()
    if cancelled:
        raise asyncio.CancelledError


async def async_restore_pairlink_local_sources(
    hass: HomeAssistant, parent: PairedBedCoordinator | None,
    transfers: list[PairlinkLocalLeaseTransfer],
    inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
) -> None:
    """Restore surviving singles only after their replacement server has stopped."""
    failures: list[Exception] = []
    for transfer in reversed(transfers):
        original = transfer.original
        entry = transfer.entry
        if hass.config_entries.async_get_entry(entry.entry_id) is not entry:
            # Removing a source entry is the registry transaction's commit point.
            continue
        try:
            if parent is not None:
                await parent.async_remove_child(transfer.side)
            leases = hass.data[DOMAIN][PAIRLINK_LOCAL_PROFILE_LEASES_KEY]
            if leases.get(transfer.adapter) != transfer.owner:
                raise ConfigEntryNotReady("Pairlink transfer reservation changed before rollback")
            current = hass.data[DOMAIN].get(entry.entry_id)
            unloaded = (
                current is None
                and original._shutting_down
                and entry.state is ConfigEntryState.NOT_LOADED
            )
            if current is not original and not unloaded:
                raise ConfigEntryNotReady("Pairlink source runtime changed before rollback")
            leases[transfer.adapter] = entry.entry_id
            if unloaded:
                if not await hass.config_entries.async_setup(entry.entry_id):
                    raise ConfigEntryNotReady("Could not reload the original Pairlink local entry")
            elif transfer.runtime.is_closed:
                async with original._command_lock, original._lock:
                    if original._pairlink_runtime is not None:
                        raise ConfigEntryNotReady("Pairlink source runtime changed during rollback")
                    await async_start_paired_pairlink_local_child(
                        hass, original, host_adapter_source=transfer.source,
                        adapter_inventory=inventory,
                    )
        except Exception as err:
            failures.append(err)
        finally:
            original.finish_pairing_transfer()
    if failures:
        raise ExceptionGroup("Pairlink local source restoration failed", failures)


def release_pairlink_local_profile_lease(
    hass: HomeAssistant,
    entry_id: str,
    adapter: str,
) -> None:
    """Release one integration-local lease after the entry-owned backend stops."""
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return
    leases = domain_data.get(PAIRLINK_LOCAL_PROFILE_LEASES_KEY)
    if isinstance(leases, dict) and leases.get(adapter) == entry_id:
        leases.pop(adapter, None)


async def async_setup_pairlink_local_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    finish: Callable[[], Awaitable[None]],
) -> bool:
    """Start a selected Pairlink peripheral role without Bleak central.

    Returns False, without side effects, unless the entry selects the
    peripheral role. ``finish`` completes the entry setup once the local
    profile runs; its failure releases the profile like any other.
    """
    from .beds.reverie_pairlink import ReveriePairlinkController
    from .beds.reverie_pairlink_profile import pairlink_host_adapter_inventory

    data = {**entry.data, **entry.options}
    if data.get(CONF_PAIRLINK_ROLE) != PAIRLINK_ROLE_PERIPHERAL:
        return False
    host_adapter_source = data.get(CONF_PAIRLINK_HOST_SOURCE)
    if not isinstance(host_adapter_source, str) or not host_adapter_source:
        raise ConfigEntryNotReady(
            "Select the exact active local Bluetooth source for Pairlink peripheral mode"
        )

    adapter_inventory = pairlink_host_adapter_inventory(hass)
    source_matches = [
        item for item in adapter_inventory if item.source == host_adapter_source
    ]
    if (
        len(source_matches) != 1
        or source_matches[0].transport != "local"
        or not source_matches[0].active
        or re.fullmatch(r"hci[0-9]+", source_matches[0].adapter) is None
    ):
        raise ConfigEntryNotReady(
            "The selected Pairlink source must map to one active local BlueZ adapter"
        )
    adapter = source_matches[0].adapter

    leases = hass.data[DOMAIN].setdefault(PAIRLINK_LOCAL_PROFILE_LEASES_KEY, {})
    if not isinstance(leases, dict):
        raise ConfigEntryNotReady("Pairlink local profile ownership state is unavailable")
    current_owner = leases.get(adapter)
    if current_owner is not None and current_owner != entry.entry_id:
        raise ConfigEntryNotReady(
            "Another Adjustable Bed entry already owns a Pairlink local profile on this adapter"
        )
    leases[adapter] = entry.entry_id
    entry.async_on_unload(
        lambda: release_pairlink_local_profile_lease(
            hass,
            entry.entry_id,
            adapter,
        )
    )

    service_info = bluetooth.async_last_service_info(
        hass,
        entry.data[CONF_ADDRESS],
        connectable=True,
    )
    manufacturer_data = (
        getattr(service_info, "manufacturer_data", None)
        if service_info is not None
        else None
    )
    device_name = getattr(service_info, "name", None) if service_info is not None else None

    try:
        controller = await create_controller(
            coordinator=coordinator,
            bed_type=BED_TYPE_REVERIE_PAIRLINK,
            protocol_variant=entry.data.get(CONF_PROTOCOL_VARIANT),
            client=None,
            device_name=device_name if isinstance(device_name, str) else None,
            manufacturer_data=(
                manufacturer_data if isinstance(manufacturer_data, dict) else None
            ),
        )
        if not isinstance(controller, ReveriePairlinkController):
            raise ConfigEntryNotReady("Pairlink factory returned an incompatible controller")
        coordinator._controller = controller
        await controller.async_start_peripheral(
            host_adapter_source=host_adapter_source,
            adapter_inventory=adapter_inventory,
        )
        coordinator.cache_capability_controller()
        await finish()
    except BaseException as err:
        release_pairlink_local_profile_lease(hass, entry.entry_id, adapter)
        try:
            await coordinator.async_shutdown()
        except Exception:  # noqa: BLE001 - preserve the concrete setup failure
            _LOGGER.exception("Pairlink peripheral cleanup failed during setup")
        if isinstance(err, asyncio.CancelledError):
            raise
        if isinstance(err, ConfigEntryNotReady):
            raise
        raise ConfigEntryNotReady(
            f"Could not start Pairlink peripheral on the selected local Bluetooth source: {err}"
        ) from err
    return True


def preflight_paired_pairlink_local_roles(
    hass: HomeAssistant,
    entry: ConfigEntry,
    children: Mapping[str, AdjustableBedCoordinator],
) -> tuple[
    tuple[PairlinkHostAdapterInventoryEntry, ...],
    list[tuple[str, AdjustableBedCoordinator, str, str, str]],
    list[PairlinkLocalLeaseTransfer],
]:
    """Validate every source and conflict before reserving any selected adapter."""
    from .beds.reverie_pairlink_profile import pairlink_host_adapter_inventory

    inventory = pairlink_host_adapter_inventory(hass)
    selected: list[tuple[str, AdjustableBedCoordinator, str, str, str]] = []
    transfers: list[PairlinkLocalLeaseTransfer] = []
    for side, child in children.items():
        if child.bed_type != BED_TYPE_REVERIE_PAIRLINK:
            continue
        data = {**child.entry.data, **child.entry.options}
        if data.get(CONF_PAIRLINK_ROLE) != PAIRLINK_ROLE_PERIPHERAL:
            continue
        source = data.get(CONF_PAIRLINK_HOST_SOURCE)
        if not isinstance(source, str) or not source:
            raise ConfigEntryNotReady(
                f"Select an exact active local Bluetooth source for the {side} Pairlink child"
            )
        matches = [item for item in inventory if item.source == source]
        if (
            len(matches) != 1
            or matches[0].transport != "local"
            or not matches[0].active
            or re.fullmatch(r"hci[0-9]+", matches[0].adapter) is None
        ):
            raise ConfigEntryNotReady(
                f"The {side} Pairlink source must map to one active local BlueZ adapter"
            )
        adapter = matches[0].adapter
        owner = f"{entry.entry_id}:{side}:{child.address.upper()}"
        selected.append((side, child, source, adapter, owner))

    adapters = [item[3] for item in selected]
    if len(set(adapters)) != len(adapters):
        raise ConfigEntryNotReady(
            "Paired Pairlink local children need distinct unambiguous BlueZ adapters"
        )
    if not selected:
        return inventory, selected, transfers

    originals = {
        side: _trusted_absorbed_single(hass, entry, side, child)
        for side, child in children.items()
    }
    domain_data = hass.data.setdefault(DOMAIN, {})
    leases = domain_data.setdefault(PAIRLINK_LOCAL_PROFILE_LEASES_KEY, {})
    if not isinstance(leases, dict):
        raise ConfigEntryNotReady("Pairlink local profile ownership state is unavailable")
    for side, _child, source, adapter, owner in selected:
        current_owner = leases.get(adapter)
        original, coordinator = originals[side]
        if current_owner is not None and current_owner != owner:
            runtime = coordinator._pairlink_runtime if coordinator is not None else None
            if (
                original is None or coordinator is None
                or current_owner != original.entry_id
                or runtime is None or not runtime.is_peripheral_role_active
                or runtime.peripheral_backend is None or not runtime.peripheral_backend.is_ready
                or runtime.host_adapter_source != source
                or runtime.host_adapter_path != f"/org/bluez/{adapter}"
                or {**original.data, **original.options}.get(CONF_PAIRLINK_ROLE) != PAIRLINK_ROLE_PERIPHERAL
            ):
                raise ConfigEntryNotReady(
                    "Another Adjustable Bed entry already owns a Pairlink local profile on this adapter"
                )
            transfers.append(PairlinkLocalLeaseTransfer(
                side, coordinator, original, runtime, source, adapter, owner,
            ))
        elif coordinator is not None and coordinator._pairlink_runtime is not None:
            runtime = coordinator._pairlink_runtime
            if runtime.peripheral_backend is not None:
                raise ConfigEntryNotReady("Absorbed local backend has no matching source lease")

    for _side, _child, _source, adapter, owner in selected:
        leases[adapter] = owner
        entry.async_on_unload(
            lambda adapter=adapter, owner=owner: release_pairlink_local_profile_lease(
                hass, owner, adapter
            )
        )
    return inventory, selected, transfers


async def async_start_paired_pairlink_local_child(
    hass: HomeAssistant,
    child: AdjustableBedCoordinator,
    *,
    host_adapter_source: str,
    adapter_inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
) -> None:
    """Start one prevalidated child-owned local Pairlink backend."""
    from .beds.reverie_pairlink import ReveriePairlinkController

    address = child.entry.data.get(CONF_ADDRESS)
    if not isinstance(address, str):
        raise ConfigEntryNotReady("Paired Pairlink child has no physical address")
    service_info = bluetooth.async_last_service_info(hass, address, connectable=True)
    manufacturer_data = (
        getattr(service_info, "manufacturer_data", None) if service_info is not None else None
    )
    device_name = getattr(service_info, "name", None) if service_info is not None else None
    controller = await create_controller(
        coordinator=child,
        bed_type=BED_TYPE_REVERIE_PAIRLINK,
        protocol_variant=child.entry.data.get(CONF_PROTOCOL_VARIANT),
        client=None,
        device_name=device_name if isinstance(device_name, str) else None,
        manufacturer_data=(
            manufacturer_data if isinstance(manufacturer_data, dict) else None
        ),
    )
    if not isinstance(controller, ReveriePairlinkController):
        raise ConfigEntryNotReady("Pairlink factory returned an incompatible child controller")
    child._controller = controller
    await controller.async_start_peripheral(
        host_adapter_source=host_adapter_source,
        adapter_inventory=adapter_inventory,
    )
    child.cache_capability_controller()
