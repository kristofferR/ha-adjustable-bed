"""Connection-owned writes for Personal Comfort operations and cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient

from ..base import BedController
from ..lifecycle import ControllerSession

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True)
class Owner:
    client: BleakClient
    generation: int
    stop_epoch: int
    cancel: asyncio.Event
    validate: Callable[[], None] | None = None


class PersonalComfortSession(BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._generation = 0

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    def capture(self) -> Owner:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Personal Comfort is disconnected")
        return Owner(
            client, self._generation, self._coordinator.stop_epoch, self._coordinator.cancel_command
        )

    def check_owner(self, owner: Owner, *, cleanup: bool = False) -> None:
        if (
            self.client is not owner.client
            or not owner.client.is_connected
            or self._generation != owner.generation
            or self._coordinator.controller is not self
        ):
            raise ConnectionError("Personal Comfort operation lost its physical session")
        if not cleanup and (
            owner.cancel.is_set() or self._coordinator.stop_epoch != owner.stop_epoch
        ):
            raise asyncio.CancelledError
        if not cleanup and owner.validate is not None:
            owner.validate()

    async def send(
        self,
        owner: Owner,
        characteristic: str,
        packet: bytes,
        *,
        cleanup: bool = False,
        repeat_count: int = 1,
        repeat_ms: int = 100,
        wall_clock_pacing: bool = False,
        deadline: float | None = None,
    ) -> None:
        self.check_owner(owner, cleanup=cleanup)

        def before_write() -> None:
            self.check_owner(owner, cleanup=cleanup)
            if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Personal Comfort hold elapsed")

        await self._write_gatt_with_retry(
            characteristic,
            packet,
            response=True,
            expected_client=owner.client,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_ms,
            cancel_event=asyncio.Event() if cleanup else owner.cancel,
            before_write=before_write,
            wall_clock_pacing=wall_clock_pacing,
        )

    async def pause(self, owner: Owner, seconds: float) -> None:
        deadline = asyncio.get_running_loop().time() + seconds
        while True:
            self.check_owner(owner)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            # A peer's STOP/replacement need not set this side's event.
            interval = min(remaining, 0.1) if owner.validate is not None else remaining
            try:
                async with asyncio.timeout(interval):
                    await owner.cancel.wait()
            except TimeoutError:
                pass

    def on_disconnect(self) -> None:
        self._generation += 1

    def require_gatt(self, roles: list[tuple[str, str, str]]) -> None:
        client = self.client
        if client is None:
            raise ConnectionError("Personal Comfort is disconnected")
        for service_uuid, characteristic_uuid, property_name in roles:
            service = client.services.get_service(service_uuid)
            characteristic = service.get_characteristic(characteristic_uuid) if service else None
            if characteristic is None or not (
                {"notify", "indicate"} & set(characteristic.properties)
                if property_name == "notify"
                else property_name in characteristic.properties
            ):
                raise ValueError(
                    "The selected Personal Comfort controller does not match its Bluetooth services"
                )

    async def async_on_connect(self, session: ControllerSession) -> None:
        # Protocol notifications and initial light reads are required even
        # though these controllers never report bed angles.
        del session
        await self.start_notify()
