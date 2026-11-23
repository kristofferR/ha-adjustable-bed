"""Types for the connect-time hooks declared on ``BedController``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from bleak import BleakClient
    from homeassistant.core import HomeAssistant


class ControllerSession(Protocol):
    """Coordinator services available to one connection's startup hooks."""

    @property
    def hass(self) -> HomeAssistant: ...

    @property
    def entry_id(self) -> str: ...

    @property
    def address(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str:
        """The Device Information model, or a generic description."""
        ...

    @property
    def client(self) -> BleakClient | None: ...

    @property
    def angle_sensing_disabled(self) -> bool: ...

    def disable_angle_sensing(self) -> None:
        """Turn angle sensing off for this coordinator, before notifications start."""

    def is_current(self) -> bool:
        """Whether this session's link is still the coordinator's live connection."""
        ...

    async def async_start_notify(self) -> None:
        """Start notifications as the coordinator's angle-sensing setting allows."""

    async def async_record_verified_bond(self) -> None:
        """Record that a protocol read proved this link is bonded."""

    def persist_capability_snapshot(self) -> None:
        """Persist ``capability_snapshot()`` as ``capability_snapshot_policy`` declares."""

    def store_device_info(self, manufacturer: str | None, model: str | None) -> None:
        """Store Device Information read by the controller itself."""


@dataclass(frozen=True, slots=True)
class CapabilitySnapshotPolicy:
    """How a controller's ``capability_snapshot()`` persists.

    The snapshot is stored in the entry's ``capabilities`` under the bed type
    and handed back to the factory as ``capability_snapshot`` on the next
    connection and for offline entity priming.
    """

    # Persist only for a paired side, whose offline twin mints entities from it.
    paired_side_only: bool = False
    # Write without reloading now; capability-gated entities reload once the
    # link is released. Otherwise the write reloads the entry and the live
    # controller becomes the offline capability controller.
    deferred_reload: bool = False
    # Also persist after each operation: the first command can resolve it.
    after_operations: bool = False
