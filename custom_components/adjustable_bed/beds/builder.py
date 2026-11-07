"""What a bed module's controller builder receives from the factory."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bleak import BleakClient

    from ..coordinator import AdjustableBedCoordinator
    from .base import BedController


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildContext:
    """One controller build: the entry, the route and what the link observed."""

    coordinator: AdjustableBedCoordinator
    bed_type: str
    variant: str | None
    # None for a client-free controller minted from stored configuration.
    client: BleakClient | None
    device_name: str | None = None
    advertisement_name: str | None = None
    manufacturer_data: dict[int, bytes] | None = None
    # Device Information Service manufacturer (0x2A29) and model (0x2A24).
    ble_manufacturer: str | None = None
    ble_model: str | None = None

    @property
    def data(self) -> Mapping[str, Any]:
        """Return the config entry data."""
        return self.coordinator.entry.data

    @property
    def live_device_name(self) -> str | None:
        """Return the BLE name only on a live link.

        Offline the factory receives the display name, which a name rule must
        never read.
        """
        return self.device_name if self.client is not None else None

    def stored_capabilities(self, namespace: str) -> Mapping[str, Any] | None:
        """Return the capability snapshot this bed stored under ``namespace``."""
        stored = self.data.get("capabilities")
        snapshot = stored.get(namespace) if isinstance(stored, dict) else None
        return snapshot if isinstance(snapshot, Mapping) else None

    def has_characteristic(self, service_uuid: str, char_uuid: str) -> bool:
        """Return True if the live link exposes this service/characteristic pair."""
        if self.client is None or self.client.services is None:
            return False
        service_uuid = service_uuid.lower()
        for service in self.client.services:
            if str(service.uuid).lower() == service_uuid and service.get_characteristic(
                char_uuid.lower()
            ):
                return True
        return False

    async def preload(self, module: str) -> None:
        """Import a ``beds`` module in the import executor, off the event loop."""
        await self.coordinator.hass.async_add_import_executor_job(
            import_module, f".{module}", __package__
        )


type ControllerBuilder = Callable[[BuildContext], Awaitable[BedController]]
