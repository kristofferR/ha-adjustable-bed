"""Explicit entity-facing runtime shared by physical and paired bed views."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Coroutine, Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from homeassistant.helpers.device_registry import ChildDeviceInfo, DeviceInfo

from .beds.base import BedController, SideBoundController

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import ChildEntryView

type ControllerCommand = Callable[[BedController], Coroutine[object, object, None]]


class EntityRuntime(Protocol):
    """Only identity, state, subscriptions and operations consumed by entities."""

    @property
    def entry(self) -> ConfigEntry | ChildEntryView: ...

    @property
    def entity_side(self) -> str | None: ...

    @property
    def address(self) -> str: ...

    def entity_unique_id(self, key: str) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def bed_type(self) -> str: ...

    @property
    def has_massage(self) -> bool: ...

    @property
    def disable_angle_sensing(self) -> bool: ...

    @property
    def controller(self) -> BedController | SideBoundController | None: ...

    @property
    def capability_controller(self) -> BedController | SideBoundController | None: ...

    @property
    def position_data(self) -> dict[str, float]: ...

    @property
    def controller_state(self) -> Mapping[str, object]: ...

    @property
    def is_connected(self) -> bool: ...

    @property
    def is_connecting(self) -> bool: ...

    @property
    def last_connected(self) -> datetime | None: ...

    @property
    def last_disconnected(self) -> datetime | None: ...

    @property
    def last_disconnect_reason(self) -> str | None: ...

    @property
    def connection_source(self) -> str | None: ...

    @property
    def connection_rssi(self) -> int | None: ...

    @property
    def device_info(self) -> DeviceInfo | ChildDeviceInfo: ...

    async def async_disconnect(
        self, reason: str = "intentional", *, serialize_with_commands: bool = False
    ) -> bool: ...

    async def async_ensure_connected(self, reset_timer: bool = True) -> bool: ...

    async def async_execute_controller_query[T](
        self,
        query_fn: Callable[[BedController], Coroutine[object, object, T]],
        cancel_running: bool = False,
        skip_disconnect: bool = False,
        preemptible: bool = True,
        run_if: Callable[[], bool] | None = None,
    ) -> T: ...

    def register_position_callback(
        self, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]: ...

    def register_controller_state_callback(
        self, callback_fn: Callable[[dict[str, object]], None]
    ) -> Callable[[], None]: ...

    def register_connection_state_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]: ...

    async def async_execute_controller_command(
        self,
        command_fn: ControllerCommand,
        *,
        cancel_running: bool = True,
        skip_disconnect: bool = False,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None: ...

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: ControllerCommand,
        move_down_fn: ControllerCommand,
        move_stop_fn: ControllerCommand,
    ) -> None: ...

    async def async_stop_command(self) -> None: ...

    async def async_stop_motor(
        self, stop_fn: ControllerCommand, resource: str, *, stream_member: bool = True
    ) -> None:
        """Stop one motor at once, never behind another motor's command (#516)."""
        ...


class EntityRuntimeView(ABC):
    """Explicit read/query forwarding; subclasses own movement routing."""

    @property
    @abstractmethod
    def _entity_source(self) -> EntityRuntime:
        """Runtime supplying this view's identity and state."""

    @property
    def entry(self) -> ConfigEntry | ChildEntryView:
        return self._entity_source.entry

    @property
    def entity_side(self) -> str | None:
        return self._entity_source.entity_side

    @property
    def address(self) -> str:
        return self._entity_source.address

    def entity_unique_id(self, key: str) -> str:
        return self._entity_source.entity_unique_id(key)

    @property
    def name(self) -> str:
        return self._entity_source.name

    @property
    def bed_type(self) -> str:
        return self._entity_source.bed_type

    @property
    def has_massage(self) -> bool:
        return self._entity_source.has_massage

    @property
    def disable_angle_sensing(self) -> bool:
        return self._entity_source.disable_angle_sensing

    @property
    def controller(self) -> BedController | SideBoundController | None:
        return self._entity_source.controller

    @property
    def capability_controller(self) -> BedController | SideBoundController | None:
        return self._entity_source.capability_controller

    @property
    def position_data(self) -> dict[str, float]:
        return self._entity_source.position_data

    @property
    def controller_state(self) -> Mapping[str, object]:
        return self._entity_source.controller_state

    @property
    def is_connected(self) -> bool:
        return self._entity_source.is_connected

    @property
    def is_connecting(self) -> bool:
        return self._entity_source.is_connecting

    @property
    def last_connected(self) -> datetime | None:
        return self._entity_source.last_connected

    @property
    def last_disconnected(self) -> datetime | None:
        return self._entity_source.last_disconnected

    @property
    def last_disconnect_reason(self) -> str | None:
        return self._entity_source.last_disconnect_reason

    @property
    def connection_source(self) -> str | None:
        return self._entity_source.connection_source

    @property
    def connection_rssi(self) -> int | None:
        return self._entity_source.connection_rssi

    @property
    def device_info(self) -> DeviceInfo | ChildDeviceInfo:
        return self._entity_source.device_info

    async def async_disconnect(
        self, reason: str = "intentional", *, serialize_with_commands: bool = False
    ) -> bool:
        return await self._entity_source.async_disconnect(
            reason, serialize_with_commands=serialize_with_commands
        )

    async def async_ensure_connected(self, reset_timer: bool = True) -> bool:
        return await self._entity_source.async_ensure_connected(reset_timer)

    async def async_execute_controller_query[T](
        self,
        query_fn: Callable[[BedController], Coroutine[object, object, T]],
        cancel_running: bool = False,
        skip_disconnect: bool = False,
        preemptible: bool = True,
        run_if: Callable[[], bool] | None = None,
    ) -> T:
        return await self._entity_source.async_execute_controller_query(
            query_fn, cancel_running, skip_disconnect, preemptible, run_if
        )

    def register_position_callback(
        self, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]:
        return self._entity_source.register_position_callback(callback_fn)

    def register_controller_state_callback(
        self, callback_fn: Callable[[dict[str, object]], None]
    ) -> Callable[[], None]:
        return self._entity_source.register_controller_state_callback(callback_fn)

    def register_connection_state_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        return self._entity_source.register_connection_state_callback(callback_fn)
