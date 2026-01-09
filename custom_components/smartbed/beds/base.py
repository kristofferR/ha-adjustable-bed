"""Base class for bed controllers."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..coordinator import SmartBedCoordinator

_LOGGER = logging.getLogger(__name__)


class BedController(ABC):
    """Abstract base class for bed controllers."""

    def __init__(self, coordinator: SmartBedCoordinator) -> None:
        """Initialize the controller."""
        self._coordinator = coordinator

    @property
    def client(self):
        """Return the BLE client."""
        return self._coordinator._client

    @property
    @abstractmethod
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""

    @abstractmethod
    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
    ) -> None:
        """Write a command to the bed."""

    @abstractmethod
    async def start_notify(
        self, callback: Callable[[str, float], None]
    ) -> None:
        """Start listening for position notifications."""

    @abstractmethod
    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""

    # Motor control methods
    @abstractmethod
    async def move_head_up(self) -> None:
        """Move head up."""

    @abstractmethod
    async def move_head_down(self) -> None:
        """Move head down."""

    @abstractmethod
    async def move_head_stop(self) -> None:
        """Stop head motor."""

    @abstractmethod
    async def move_legs_up(self) -> None:
        """Move legs up."""

    @abstractmethod
    async def move_legs_down(self) -> None:
        """Move legs down."""

    @abstractmethod
    async def move_legs_stop(self) -> None:
        """Stop legs motor."""

    @abstractmethod
    async def stop_all(self) -> None:
        """Stop all motors."""

    # Preset methods
    @abstractmethod
    async def preset_flat(self) -> None:
        """Go to flat position."""

    @abstractmethod
    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""

    @abstractmethod
    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""

    # Feature methods (may not be available on all beds)
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        raise NotImplementedError

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        raise NotImplementedError

    async def lights_toggle(self) -> None:
        """Toggle under-bed lights."""
        raise NotImplementedError

    async def massage_off(self) -> None:
        """Turn off massage."""
        raise NotImplementedError

    async def massage_toggle(self) -> None:
        """Toggle massage."""
        raise NotImplementedError

    async def massage_head_toggle(self) -> None:
        """Toggle head massage."""
        raise NotImplementedError

    async def massage_foot_toggle(self) -> None:
        """Toggle foot massage."""
        raise NotImplementedError

    async def massage_intensity_up(self) -> None:
        """Increase massage intensity."""
        raise NotImplementedError

    async def massage_intensity_down(self) -> None:
        """Decrease massage intensity."""
        raise NotImplementedError

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        raise NotImplementedError

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        raise NotImplementedError

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        raise NotImplementedError

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        raise NotImplementedError

    async def massage_mode_step(self) -> None:
        """Step through massage modes."""
        raise NotImplementedError

