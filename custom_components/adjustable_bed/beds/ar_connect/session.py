"""Concrete GATT/session fencing shared by AR Connect's two independent routes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ...errors import BedNotConnectedError
from ..base import BedController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(slots=True)
class Link:
    client: BleakClient
    generation: int
    address: str
    roles: dict[str, BleakGATTCharacteristic] = field(default_factory=dict)
    subscriptions: dict[str, object] = field(default_factory=dict)
    ready: bool = False


class ArSessionController(BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.link: Link | None = None

    def bind(self) -> Link:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        self.link = Link(client, self._coordinator.connection_generation, self._coordinator.address)
        return self.link

    def live(self, expected: Link | None = None, *, ready: bool = True) -> Link:
        link = self.link
        if (
            link is None
            or expected is not None
            and expected is not link
            or self._coordinator.controller is not self
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address != link.address
            or self._coordinator.connection_generation != link.generation
            or ready
            and not link.ready
        ):
            raise BedNotConnectedError()
        return link

    def current(self, link: Link) -> bool:
        try:
            self.live(link)
        except BedNotConnectedError:
            return False
        return True

    def role(
        self, link: Link, key: str, service: str, uuid: str, *properties: str
    ) -> BleakGATTCharacteristic:
        svc = link.client.services.get_service(service)
        char = svc.get_characteristic(uuid) if svc is not None else None
        if char is None or any(prop not in char.properties for prop in properties):
            raise BedNotConnectedError()
        link.roles[key] = char
        return char

    async def read(self, link: Link, key: str) -> bytes:
        self.live(link, ready=False)
        async with self.ble_lock, asyncio.timeout(30):
            self.live(link, ready=False)
            value = await link.client.read_gatt_char(link.roles[key])
        self.live(link, ready=False)
        return bytes(value)

    async def subscribe(self, link: Link, key: str, receive: Callable[[bytes], None]) -> None:
        self.live(link, ready=False)
        if key in link.subscriptions:
            return
        token = object()
        link.subscriptions[key] = token

        def handler(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self.live(link, ready=False)
            except BedNotConnectedError:
                return
            if link.subscriptions.get(key) is token:
                self.forward_raw_notification(link.roles[key].uuid, bytes(data))
                receive(bytes(data))

        try:
            async with asyncio.timeout(15):
                await link.client.start_notify(link.roles[key], handler)
            self.live(link, ready=False)
        except BaseException:
            link.subscriptions.pop(key, None)
            raise

    async def frame(
        self,
        link: Link,
        key: str,
        value: bytes,
        *,
        cancel: asyncio.Event | None = None,
        startup: bool = False,
        response: bool | None = None,
        before_write: Callable[[], None] | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        self.live(link, ready=not startup)
        char = link.roles[key]
        # Native Android retains the discovered characteristic's mode. HA selects
        # an advertised operation, preferring acknowledged writes when available.
        mode = "write" in char.properties if response is None else response
        if ("write" if mode else "write-without-response") not in char.properties:
            raise BedNotConnectedError()

        def check() -> None:
            self.live(link, ready=not startup)
            if before_write is not None:
                before_write()

        await self._write_gatt_with_retry(
            char.uuid,
            value,
            cancel_event=cancel,
            characteristic=char,
            expected_client=link.client,
            response=mode,
            before_write=check,
            on_write=(lambda: on_write() if on_write is not None and self.current(link) else None),
            track_command_write=not startup,
            settle_write=True,
            write_timeout=15 if response is True else 30,
        )
        self.live(link, ready=not startup)

    async def stop_notify(self) -> None:
        link = self.link
        if link is None:
            return
        keys = tuple(link.subscriptions)
        link.subscriptions.clear()
        # Invalidate callbacks before the first await, even if stop_notify fails.
        for key in keys:
            try:
                self.live(link, ready=False)
                async with asyncio.timeout(1):
                    await link.client.stop_notify(link.roles[key])
            except BleakError, TimeoutError:
                continue
            except BedNotConnectedError:
                return

    def on_disconnect(self) -> None:
        if self.link is not None:
            self.link.subscriptions.clear()
            self.link.ready = False
        self.link = None

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0

    async def unavailable(self, memory_num: int = 0) -> None:
        raise self.not_supported("motor or memory control")

    move_head_up = move_head_down = move_back_up = move_back_down = unavailable
    move_legs_up = move_legs_down = move_feet_up = move_feet_down = unavailable
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = unavailable
    preset_flat = preset_memory = program_memory = unavailable
