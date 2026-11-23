"""Focused contract tests for the optional Pairlink local BlueZ server."""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast

import pytest
from dbus_fast import DBusError, Message, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.constants import MessageType

from custom_components.adjustable_bed.beds.reverie import pairlink_transport as transport

_SOURCE = "AA:BB:CC:DD:EE:FF"
_ADAPTER = "hci3"
_ADAPTER_PATH = f"/org/bluez/{_ADAPTER}"
_PEER_ADDRESS = "11:22:33:44:55:66"
_PEER_PATH = f"{_ADAPTER_PATH}/dev_{_PEER_ADDRESS.replace(':', '_')}"


def _device(
    address: str = _PEER_ADDRESS,
    *,
    adapter_path: str = _ADAPTER_PATH,
    connected: bool = True,
) -> dict[str, dict[str, object]]:
    return {
        "org.bluez.Device1": {
            "Adapter": adapter_path,
            "Address": address,
            "Connected": connected,
        }
    }


def _inventory(
    *,
    source: str = _SOURCE,
    adapter: str = _ADAPTER,
    transport_type: transport.AdapterTransport = "local",
    active: bool = True,
) -> tuple[transport.PairlinkHostAdapterInventoryEntry, ...]:
    return (
        transport.PairlinkHostAdapterInventoryEntry(
            source=source,
            transport=transport_type,
            adapter=adapter,
            active=active,
        ),
    )


def _profile(
    *,
    with_advertisement: bool = True,
    with_descriptor: bool = False,
    start_delay_ms: int = 0,
) -> transport.PairlinkPeripheralProfile:
    advertisement = (
        transport.PairlinkAdvertisementProfile(
            advertisement_type="peripheral",
            service_uuids=("1234",),
            local_name="Synthetic Pairlink Fixture",
            includes=("local-name",),
            manufacturer_data=((0, bytes.fromhex("C0FF05010203040506070809")),),
            start_delay_ms=start_delay_ms,
            timeout_seconds=0,
        )
        if with_advertisement
        else None
    )
    return transport.PairlinkPeripheralProfile(
        service_uuid="1234",
        write_characteristic_uuid="1235",
        notify_characteristic_uuid="1236",
        write_flags=(transport.PairlinkGattFlag.READ, transport.PairlinkGattFlag.WRITE),
        notify_flags=(transport.PairlinkGattFlag.READ, transport.PairlinkGattFlag.NOTIFY),
        advertisement=advertisement,
        write_read_value=b"\x44",
        notify_read_value=b"\x66",
        notify_descriptor=(
            transport.PairlinkGattDescriptorProfile(
                uuid="2902",
                characteristic_uuid="1236",
                flags=(transport.PairlinkGattFlag.READ, transport.PairlinkGattFlag.WRITE),
                read_value=b"\x01\x00",
            )
            if with_descriptor
            else None
        ),
    )


def _managed_objects(
    *,
    address: str = _SOURCE,
    powered: bool = True,
    gatt_manager: bool = True,
    advertising_manager: bool = True,
    supported_instances: int = 2,
    active_instances: int = 1,
    supported_includes: tuple[str, ...] = ("local-name",),
    can_set_tx_power: object = False,
    min_tx_power: object = -20,
    max_tx_power: object = 10,
) -> dict[str, dict[str, dict[str, object]]]:
    adapter: dict[str, dict[str, object]] = {
        "org.bluez.Adapter1": {"Address": address, "Powered": powered}
    }
    if gatt_manager:
        adapter["org.bluez.GattManager1"] = {}
    if advertising_manager:
        adapter["org.bluez.LEAdvertisingManager1"] = {
            "SupportedInstances": supported_instances,
            "ActiveInstances": active_instances,
            "SupportedIncludes": supported_includes,
            "CanSetTxPower": can_set_tx_power,
            "MinTxPower": min_tx_power,
            "MaxTxPower": max_tx_power,
        }
    return {_ADAPTER_PATH: adapter, _PEER_PATH: _device()}


class FakeBlueZBus:
    """Minimal bus substitute that records exported objects and BlueZ calls."""

    def __init__(
        self,
        *,
        fail_at: str | None = None,
        block_at: str | None = None,
        release_advertisement_on_register: bool = False,
        managed_objects: Mapping[str, Mapping[str, Mapping[str, object]]] | None = None,
    ) -> None:
        self.fail_at = fail_at
        self.block_at = block_at
        self.release_advertisement_on_register = release_advertisement_on_register
        self.managed_objects: dict[str, dict[str, dict[str, object]]] = (
            _managed_objects()
            if managed_objects is None
            else {
                path: {name: dict(properties) for name, properties in interfaces.items()}
                for path, interfaces in managed_objects.items()
            }
        )
        self.events: list[tuple[str, ...]] = []
        self.exports: dict[tuple[str, str], object] = {}
        self.connected = False
        self.application_registered = False
        self.advertisement_registered = False
        self.owner_callback: Callable[[], None] | None = None
        self.peer_disconnect_callback: Callable[[str, bool], None] | None = None
        self.peer_watch_adapter: str | None = None
        self.peer_write_watch_path: str | None = None
        self.peer_notify_acquire_callback: transport.PairlinkPeerNotifyAcquireCallback | None = None
        self.disconnect_event = asyncio.Event()
        self.connection_lost_event = asyncio.Event()
        self.operation_started = asyncio.Event()
        self.release_operation = asyncio.Event()
        self.export_count = 0

    @property
    def is_connected(self) -> bool:
        return self.connected

    def _fail(self, operation: str) -> None:
        if self.fail_at == operation:
            raise RuntimeError("synthetic failure containing private payload")

    async def _block(self, operation: str) -> None:
        if self.block_at == operation:
            self.operation_started.set()
            await self.release_operation.wait()

    async def async_connect(self) -> None:
        self.events.append(("connect",))
        self.connected = True
        self.disconnect_event.clear()
        self.connection_lost_event.clear()
        await self._block("connect")
        self._fail("connect")

    async def async_get_managed_objects(
        self,
    ) -> Mapping[str, Mapping[str, Mapping[str, object]]]:
        self.events.append(("get-managed-objects",))
        await self._block("managed-objects")
        self._fail("managed-objects")
        return self.managed_objects

    async def async_watch_bluez_owner(self, callback: Callable[[], None]) -> None:
        self.events.append(("watch-owner",))
        self.owner_callback = callback
        await self._block("watch-owner")
        self._fail("watch-owner")

    async def async_unwatch_bluez_owner(self) -> None:
        self.events.append(("unwatch-owner",))
        self.owner_callback = None

    async def async_watch_peer_disconnect(
        self, adapter_path: str, callback: Callable[[str], None]
    ) -> None:
        self.events.append(("watch-peer-disconnect", adapter_path))
        self.peer_watch_adapter = adapter_path
        self.peer_disconnect_callback = callback

    async def async_unwatch_peer_disconnect(self) -> None:
        self.events.append(("unwatch-peer-disconnect",))
        self.peer_watch_adapter = None
        self.peer_disconnect_callback = None

    async def async_watch_peer_write_producer(self, characteristic_path: str) -> None:
        self.events.append(("watch-peer-write-producer", characteristic_path))
        self.peer_write_watch_path = characteristic_path

    async def async_unwatch_peer_write_producer(self) -> None:
        self.events.append(("unwatch-peer-write-producer",))
        self.peer_write_watch_path = None

    async def async_watch_peer_notify_acquire(
        self,
        characteristic_path: str,
        callback: transport.PairlinkPeerNotifyAcquireCallback,
    ) -> None:
        self.events.append(("watch-peer-notify-acquire", characteristic_path))
        self.peer_notify_acquire_callback = callback
        self._fail("watch-peer-notify-acquire")

    async def async_unwatch_peer_notify_acquire(self) -> None:
        self.events.append(("unwatch-peer-notify-acquire",))
        self.peer_notify_acquire_callback = None

    async def acquire_notify(self, options: Mapping[str, object]) -> tuple[socket.socket, int]:
        callback = self.peer_notify_acquire_callback
        if callback is None:
            raise transport.PairlinkTransportStateError("No notify acquisition callback")
        offered_socket, mtu = await callback(options)
        bluez_socket = offered_socket.dup()
        offered_socket.close()
        return bluez_socket, mtu

    async def async_register_application(self, adapter_path: str, application_path: str) -> None:
        self.events.append(("register-application", adapter_path, application_path))
        self.application_registered = True
        await self._block("register-application")
        self._fail("register-application")

    async def async_unregister_application(self, adapter_path: str, application_path: str) -> None:
        self.events.append(("unregister-application", adapter_path, application_path))
        self.application_registered = False

    async def async_register_advertisement(
        self, adapter_path: str, advertisement_path: str
    ) -> None:
        self.events.append(("register-advertisement", adapter_path, advertisement_path))
        self.advertisement_registered = True
        await self._block("register-advertisement")
        if self.release_advertisement_on_register:
            self.advertisement_registered = False
            advertisement = self.exports[
                (transport._ADVERTISEMENT_PATH, "org.bluez.LEAdvertisement1")
            ]
            advertisement.Release()
        self._fail("register-advertisement")

    async def async_unregister_advertisement(
        self, adapter_path: str, advertisement_path: str
    ) -> None:
        self.events.append(("unregister-advertisement", adapter_path, advertisement_path))
        await self._block("unregister-advertisement")
        self.advertisement_registered = False

    def export(self, object_path: str, interface: object) -> None:
        self.events.append(("export", object_path))
        index = self.export_count
        self.export_count += 1
        self._fail(f"export-{index}")
        interface_name = getattr(interface, "name", None)
        if not isinstance(interface_name, str):
            raise TypeError("Synthetic interface must expose its D-Bus name")
        self.exports[(object_path, interface_name)] = interface

    def unexport(self, object_path: str, interface_name: str) -> None:
        self.events.append(("unexport", object_path, interface_name))
        self.exports.pop((object_path, interface_name), None)

    async def async_wait_for_disconnect(self) -> None:
        self.events.append(("wait-for-disconnect",))
        await self.connection_lost_event.wait()

    async def async_disconnect(self) -> None:
        self.events.append(("disconnect",))
        self.connected = False
        self.application_registered = False
        self.advertisement_registered = False
        self.connection_lost_event.set()
        self.disconnect_event.set()

    async def drop_connection(self) -> None:
        self.connected = False
        self.connection_lost_event.set()


class _WriteValueMethod(Protocol):
    __wrapped__: Callable[[object, object, Mapping[str, object]], Awaitable[None]]


class _WriteValueCharacteristic(Protocol):
    WriteValue: _WriteValueMethod


class _ReadValueMethod(Protocol):
    __wrapped__: Callable[[object, Mapping[str, object]], Awaitable[bytes]]


class _ReadValueDescriptor(Protocol):
    ReadValue: _ReadValueMethod


class _GetManagedObjectsMethod(Protocol):
    __wrapped__: Callable[[object], dict[str, dict[str, dict[str, object]]]]


class _ObjectManager(Protocol):
    GetManagedObjects: _GetManagedObjectsMethod


class _WriteValueDescriptor(Protocol):
    WriteValue: _WriteValueMethod


def _interface(bus: FakeBlueZBus, path: str) -> object:
    matches = [
        interface for (object_path, _), interface in bus.exports.items() if object_path == path
    ]
    assert len(matches) == 1
    return matches[0]


async def _write_value(
    characteristic: object,
    value: object,
    options: Mapping[str, object],
) -> None:
    write_method = cast(_WriteValueCharacteristic, characteristic).WriteValue.__wrapped__
    await write_method(characteristic, value, options)


async def _descriptor_read_value(descriptor: object, options: Mapping[str, object]) -> bytes:
    read_method = cast(_ReadValueDescriptor, descriptor).ReadValue.__wrapped__
    return await read_method(descriptor, options)


async def _descriptor_write_value(
    descriptor: object, value: object, options: Mapping[str, object]
) -> None:
    write_method = cast(_WriteValueDescriptor, descriptor).WriteValue.__wrapped__
    await write_method(descriptor, value, options)


def _events(bus: FakeBlueZBus, name: str) -> list[tuple[str, ...]]:
    return [event for event in bus.events if event[0] == name]


async def _start(
    backend: transport.PairlinkPeripheralBackend,
    *,
    profile: transport.PairlinkPeripheralProfile | None = None,
    on_peer_write: transport.PairlinkPeerWriteCallback | None = None,
    on_peer_disconnect: transport.PairlinkPeerDisconnectCallback | None = None,
    is_peripheral_role_active: transport.PairlinkPeripheralRoleGate | None = None,
) -> None:
    callback = on_peer_write if on_peer_write is not None else lambda _peer, _value: None
    await backend.async_start(
        host_adapter_source=_SOURCE,
        adapter_inventory=_inventory(),
        profile=profile or _profile(),
        on_peer_write=callback,
        on_peer_disconnect=on_peer_disconnect,
        is_peripheral_role_active=is_peripheral_role_active,
    )


def test_manufacturer_payload_obeys_the_source_builder_limit() -> None:
    transport.PairlinkAdvertisementProfile(
        advertisement_type="peripheral",
        service_uuids=(),
        local_name=None,
        includes=(),
        manufacturer_data=((0, b"x" * 29),),
    )
    with pytest.raises(ValueError, match="29-byte payload"):
        transport.PairlinkAdvertisementProfile(
            advertisement_type="peripheral",
            service_uuids=(),
            local_name=None,
            includes=(),
            manufacturer_data=((0, b"x" * 30),),
        )


@pytest.mark.parametrize(
    ("inventory", "source"),
    [
        (_inventory(transport_type="proxy"), _SOURCE),
        (_inventory(transport_type="unknown"), _SOURCE),
        (_inventory(active=False), _SOURCE),
        (_inventory(adapter="hci-not-an-index"), _SOURCE),
        (_inventory(), "not-a-bluez-address"),
        ((_inventory()[0], _inventory()[0]), _SOURCE),
        ((), _SOURCE),
    ],
)
async def test_source_must_be_one_active_local_inventory_entry_before_bus_open(
    inventory: tuple[transport.PairlinkHostAdapterInventoryEntry, ...], source: str
) -> None:
    factory_calls = 0

    def make_bus() -> FakeBlueZBus:
        nonlocal factory_calls
        factory_calls += 1
        return FakeBlueZBus()

    backend = transport.PairlinkPeripheralBackend(bus_factory=make_bus)
    with pytest.raises(transport.PairlinkTransportCapabilityError):
        await backend.async_start(
            host_adapter_source=source,
            adapter_inventory=inventory,
            profile=_profile(),
            on_peer_write=lambda _peer, _value: None,
        )
    assert factory_calls == 0


async def test_write_value_calls_must_come_from_the_current_bluez_owner() -> None:
    class MessageHandlerBus:
        def __init__(self) -> None:
            self.handlers: list[Callable[[Message], Message | bool | None]] = []

        def add_message_handler(self, handler: Callable[[Message], Message | bool | None]) -> None:
            self.handlers.append(handler)

        def remove_message_handler(
            self, handler: Callable[[Message], Message | bool | None]
        ) -> None:
            self.handlers.remove(handler)

    dbus_bus = transport._DbusFastBlueZBus()
    message_bus = MessageHandlerBus()
    dbus_bus._bus = cast(MessageBus, message_bus)
    dbus_bus._bluez_owner = ":1.42"
    await dbus_bus.async_watch_peer_write_producer(transport._PEER_WRITE_CALL_PATH)
    assert len(message_bus.handlers) == 1
    filter_message = message_bus.handlers[0]

    accepted = Message(
        message_type=MessageType.METHOD_CALL,
        sender=":1.42",
        path=transport._PEER_WRITE_CALL_PATH,
        interface="org.bluez.GattCharacteristic1",
        member="WriteValue",
        signature="aya{sv}",
        body=[b"accepted-peer-write", {}],
        serial=1,
    )
    assert filter_message(accepted) is None

    spoofed = Message(
        message_type=MessageType.METHOD_CALL,
        sender=":1.99",
        path=transport._PEER_WRITE_CALL_PATH,
        interface="org.bluez.GattCharacteristic1",
        member="WriteValue",
        signature="aya{sv}",
        body=[b"private-payload", {}],
        serial=2,
    )
    rejected = filter_message(spoofed)
    assert isinstance(rejected, Message)
    assert rejected.error_name == "org.bluez.Error.NotAuthorized"
    assert "private-payload" not in str(rejected)

    dbus_bus._bluez_owner = None
    owner_unavailable = filter_message(accepted)
    assert isinstance(owner_unavailable, Message)
    assert owner_unavailable.error_name == "org.bluez.Error.NotAuthorized"

    await dbus_bus.async_unwatch_peer_write_producer()
    assert message_bus.handlers == []


async def test_acquire_notify_requires_bluez_owner_and_transfers_peer_socket() -> None:
    class MessageHandlerBus:
        def __init__(self) -> None:
            self.handlers: list[Callable[[Message], Message | bool | None]] = []
            self.sent: list[Message] = []
            self.received_fds: list[int] = []
            self.sent_event = asyncio.Event()
            self.connected = True

        def add_message_handler(self, handler: Callable[[Message], Message | bool | None]) -> None:
            self.handlers.append(handler)

        def remove_message_handler(
            self, handler: Callable[[Message], Message | bool | None]
        ) -> None:
            self.handlers.remove(handler)

        async def send(self, message: Message) -> None:
            if message.unix_fds:
                self.received_fds.append(os.dup(message.unix_fds[0]))
            self.sent.append(message)
            self.sent_event.set()

    dbus_bus = transport._DbusFastBlueZBus()
    message_bus = MessageHandlerBus()
    dbus_bus._bus = cast(MessageBus, message_bus)
    dbus_bus._bluez_owner = ":1.42"
    local_socket, offered_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    received_options: list[Mapping[str, object]] = []

    async def acquire(options: Mapping[str, object]) -> tuple[socket.socket, int]:
        received_options.append(options)
        return offered_socket, 23

    await dbus_bus.async_watch_peer_notify_acquire(
        transport._NOTIFY_CHARACTERISTIC_PATH,
        acquire,
    )
    handler = message_bus.handlers[0]
    options = {
        "device": Variant("o", _PEER_PATH),
        "mtu": Variant("q", 23),
    }

    spoofed = Message(
        message_type=MessageType.METHOD_CALL,
        sender=":1.99",
        path=transport._NOTIFY_CHARACTERISTIC_PATH,
        interface="org.bluez.GattCharacteristic1",
        member="AcquireNotify",
        signature="a{sv}",
        body=[options],
        serial=11,
    )
    spoofed_result = handler(spoofed)
    assert isinstance(spoofed_result, Message)
    assert spoofed_result.error_name == "org.bluez.Error.NotAuthorized"
    assert not received_options

    accepted = Message(
        message_type=MessageType.METHOD_CALL,
        sender=":1.42",
        path=transport._NOTIFY_CHARACTERISTIC_PATH,
        interface="org.bluez.GattCharacteristic1",
        member="AcquireNotify",
        signature="a{sv}",
        body=[options],
        serial=12,
    )
    assert handler(accepted) is True
    await asyncio.wait_for(message_bus.sent_event.wait(), timeout=1)
    assert received_options == [options]
    reply = message_bus.sent[-1]
    assert reply.signature == "hq"
    assert reply.body == [0, 23]
    assert len(message_bus.received_fds) == 1
    os.write(local_socket.fileno(), b"one peer")
    assert os.read(message_bus.received_fds[0], 32) == b"one peer"

    await dbus_bus.async_unwatch_peer_notify_acquire()
    assert message_bus.handlers == []
    for transferred in message_bus.received_fds:
        os.close(transferred)
    local_socket.close()
    assert offered_socket.fileno() == -1


@pytest.mark.parametrize(
    "objects",
    [
        _managed_objects(address="11:22:33:44:55:66"),
        {
            "/org/bluez/hci4": {
                "org.bluez.Adapter1": {"Address": _SOURCE, "Powered": True},
                "org.bluez.GattManager1": {},
            },
        },
        {
            **_managed_objects(),
            "/org/bluez/hci4": {
                "org.bluez.Adapter1": {"Address": _SOURCE, "Powered": True},
                "org.bluez.GattManager1": {},
            },
        },
        _managed_objects(powered=False),
        _managed_objects(gatt_manager=False),
    ],
)
async def test_bluez_mapping_and_gatt_prerequisites_fail_closed(
    objects: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> None:
    bus = FakeBlueZBus(managed_objects=objects)
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    with pytest.raises(transport.PairlinkTransportCapabilityError):
        await _start(backend, profile=_profile(with_advertisement=False))

    assert not _events(bus, "register-application")
    assert not bus.exports
    assert not bus.connected


@pytest.mark.parametrize(
    "objects",
    [
        _managed_objects(advertising_manager=False),
        _managed_objects(supported_instances=1, active_instances=1),
        _managed_objects(supported_includes=()),
    ],
)
async def test_advertisement_capability_prerequisites_fail_before_registration(
    objects: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> None:
    bus = FakeBlueZBus(managed_objects=objects)
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    with pytest.raises(transport.PairlinkTransportCapabilityError):
        await _start(backend)

    assert not _events(bus, "register-application")
    assert not _events(bus, "register-advertisement")
    assert not bus.exports


async def test_gatt_only_profile_does_not_require_or_register_advertising() -> None:
    bus = FakeBlueZBus(managed_objects=_managed_objects(advertising_manager=False))
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    await _start(backend, profile=_profile(with_advertisement=False))

    assert _events(bus, "register-application")
    assert not _events(bus, "register-advertisement")
    assert not any(path == transport._ADVERTISEMENT_PATH for path, _ in bus.exports)
    await backend.async_stop()


async def test_source_descriptor_profile_requires_active_role_before_opening_bus() -> None:
    factory_calls = 0

    def make_bus() -> FakeBlueZBus:
        nonlocal factory_calls
        factory_calls += 1
        return FakeBlueZBus()

    backend = transport.PairlinkPeripheralBackend(bus_factory=make_bus)
    with pytest.raises(transport.PairlinkTransportCapabilityError, match="role is not active"):
        await backend.async_start(
            host_adapter_source=_SOURCE,
            adapter_inventory=_inventory(),
            profile=_profile(with_descriptor=True),
            on_peer_write=lambda _peer, _value: None,
        )
    assert factory_calls == 0


async def test_source_profile_maps_to_functional_bluez_profile() -> None:
    from custom_components.adjustable_bed.beds.reverie.pairlink_profile import (
        build_pairlink_peripheral_profile,
    )

    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    profile = build_pairlink_peripheral_profile(
        home_id=5566,
        local_join_bt_mac=bytes.fromhex("000102030405"),
    )

    await backend.async_start(
        host_adapter_source=_SOURCE,
        adapter_inventory=_inventory(),
        profile=profile,
        on_peer_write=lambda _peer, _value: None,
        is_peripheral_role_active=lambda: True,
    )

    assert backend.is_ready
    assert _events(bus, "register-application")
    assert _events(bus, "register-advertisement")
    assert not any(name == "org.bluez.GattDescriptor1" for _, name in bus.exports)
    manager = _interface(bus, transport._APPLICATION_PATH)
    managed = manager.GetManagedObjects.__wrapped__(manager)
    notify = managed[transport._NOTIFY_CHARACTERISTIC_PATH][
        "org.bluez.GattCharacteristic1"
    ]
    write = managed[transport._WRITE_CHARACTERISTIC_PATH][
        "org.bluez.GattCharacteristic1"
    ]
    assert write["Flags"].value == ["read", "write"]
    assert write["Value"].value == b"\x44"
    assert notify["Flags"].value == ["read", "notify"]
    assert notify["Value"].value == b"\x66"
    assert profile.advertisement is not None
    assert profile.advertisement.minimum_interval_ms == 100
    assert profile.advertisement.maximum_interval_ms == 100
    assert profile.advertisement.tx_power_dbm == 1
    assert profile.advertisement.includes == ()
    await backend.async_stop()


@pytest.mark.parametrize(
    ("can_set_tx_power", "min_tx_power", "max_tx_power", "enabled"),
    [
        (False, -20, 10, False),
        (True, -20, 10, True),
        (Variant("b", True), Variant("n", -20), Variant("n", 10), True),
        (True, 2, 8, False),
        (True, -8, 0, False),
        (True, -8, 1, True),
        (True, 1, 1, True),
        (True, None, 10, False),
        (True, -20, None, False),
        (True, True, 10, False),
        (True, 1.0, 10, False),
        (True, Variant("s", "-20"), 10, False),
        (True, -32769, 10, False),
        (True, 10, -10, False),
        (1, -20, 10, False),
    ],
)
async def test_production_advertisement_uses_only_reported_optional_power(
    can_set_tx_power: object,
    min_tx_power: object,
    max_tx_power: object,
    enabled: bool,
) -> None:
    from dbus_fast.service import ServiceInterface

    from custom_components.adjustable_bed.beds.reverie.pairlink_profile import (
        build_pairlink_peripheral_profile,
    )

    bus = FakeBlueZBus(
        managed_objects=_managed_objects(
            can_set_tx_power=can_set_tx_power,
            min_tx_power=min_tx_power,
            max_tx_power=max_tx_power,
        )
    )
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    profile = build_pairlink_peripheral_profile(
        home_id=5566,
        local_join_bt_mac=bytes.fromhex("000102030405"),
    )
    await backend.async_start(
        host_adapter_source=_SOURCE,
        adapter_inventory=_inventory(),
        profile=profile,
        on_peer_write=lambda _peer, _value: None,
    )

    try:
        advertisement = _interface(bus, transport._ADVERTISEMENT_PATH)
        properties = {
            prop.name: prop for prop in ServiceInterface._get_properties(advertisement)
        }
        assert properties["TxPower"].disabled is (not enabled)
        assert properties["MinInterval"].disabled is False
        assert properties["MaxInterval"].disabled is False
        assert properties["MinInterval"].prop_getter(advertisement) == 100
        assert properties["MaxInterval"].prop_getter(advertisement) == 100
        assert bus.advertisement_registered
        if enabled:
            assert properties["TxPower"].prop_getter(advertisement) == 1
    finally:
        await backend.async_stop()

async def test_acquire_notify_is_peer_and_role_gated() -> None:
    bus = FakeBlueZBus()
    role_active = True
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        is_peripheral_role_active=lambda: role_active,
    )
    manager = _interface(bus, transport._APPLICATION_PATH)
    managed = cast(_ObjectManager, manager).GetManagedObjects.__wrapped__(manager)
    assert set(managed) == {
        transport._SERVICE_PATH,
        transport._WRITE_CHARACTERISTIC_PATH,
        transport._NOTIFY_CHARACTERISTIC_PATH,
    }
    notify_properties = managed[transport._NOTIFY_CHARACTERISTIC_PATH][
        "org.bluez.GattCharacteristic1"
    ]
    assert notify_properties["NotifyAcquired"] == Variant("b", True)
    assert not any(name == "org.bluez.GattDescriptor1" for _, name in bus.exports)

    notify_characteristic = _interface(bus, transport._NOTIFY_CHARACTERISTIC_PATH)
    assert notify_characteristic.NotifyAcquired is True
    acquired_socket, mtu = await bus.acquire_notify(
        {
            "device": Variant("o", _PEER_PATH),
            "mtu": Variant("q", 23),
            "link": Variant("s", "LE"),
        }
    )
    peer = transport.PairlinkPeerIdentity(
        _ADAPTER_PATH,
        _PEER_PATH,
        _PEER_ADDRESS,
        1,
    )
    assert mtu == 23
    assert notify_characteristic.Notifying is True
    with pytest.raises(transport.PairlinkTransportCapabilityError, match="verified peer"):
        await backend.async_notify(b"broadcast")
    with pytest.raises(transport.PairlinkTransportError, match="peer MTU"):
        await backend.async_notify_to_peer(peer, b"x" * 21)
    await backend.async_notify_to_peer(peer, b"one peer")
    assert acquired_socket.recv(32) == b"one peer"

    role_active = False
    with pytest.raises(transport.PairlinkTransportStateError, match="role is not active"):
        await backend.async_notify_to_peer(peer, b"blocked")
    with pytest.raises(DBusError) as old_start_notify:
        notify_characteristic.StartNotify.__wrapped__(notify_characteristic)
    assert old_start_notify.value.type == "org.bluez.Error.NotSupported"
    await backend.async_stop()
    assert acquired_socket.recv(1) == b""
    acquired_socket.close()


async def test_peer_notify_sessions_route_independently_and_refresh_on_rejoin() -> None:
    second_address = "22:33:44:55:66:77"
    second_path = f"{_ADAPTER_PATH}/dev_{second_address.replace(':', '_')}"
    bus = FakeBlueZBus()
    bus.managed_objects[second_path] = _device(second_address)
    disconnected: list[transport.PairlinkPeerIdentity] = []
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_disconnect=disconnected.append,
        is_peripheral_role_active=lambda: True,
    )

    def options(path: str) -> dict[str, object]:
        return {
            "device": Variant("o", path),
            "mtu": Variant("q", 23),
            "link": Variant("s", "LE"),
        }

    first_socket, _ = await bus.acquire_notify(options(_PEER_PATH))
    second_socket, _ = await bus.acquire_notify(options(second_path))
    first = transport.PairlinkPeerIdentity(_ADAPTER_PATH, _PEER_PATH, _PEER_ADDRESS, 1)
    second = transport.PairlinkPeerIdentity(_ADAPTER_PATH, second_path, second_address, 2)
    assert first != second

    second_socket.setblocking(False)
    await backend.async_notify_to_peer(first, b"first-only")
    assert first_socket.recv(32) == b"first-only"
    with pytest.raises(BlockingIOError):
        second_socket.recv(32)

    await backend.async_notify_to_peer(second, b"second-only")
    assert second_socket.recv(32) == b"second-only"
    assert disconnected == []

    assert bus.peer_disconnect_callback is not None
    bus.peer_disconnect_callback(_PEER_PATH, False)
    assert disconnected == [first]
    assert first_socket.recv(1) == b""
    with pytest.raises(transport.PairlinkTransportStateError, match="not current"):
        await backend.async_notify_to_peer(first, b"stale")

    rejoined_socket, _ = await bus.acquire_notify(options(_PEER_PATH))
    rejoined = transport.PairlinkPeerIdentity(
        _ADAPTER_PATH,
        _PEER_PATH,
        _PEER_ADDRESS,
        3,
    )
    assert rejoined != first
    await backend.async_notify_to_peer(rejoined, b"new-generation")
    assert rejoined_socket.recv(32) == b"new-generation"
    await backend.async_notify_to_peer(second, b"second-still-live")
    assert second_socket.recv(32) == b"second-still-live"

    await backend.async_stop()
    assert disconnected == [first, second, rejoined]
    assert second_socket.recv(1) == b""
    assert rejoined_socket.recv(1) == b""
    first_socket.close()
    second_socket.close()
    rejoined_socket.close()

    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        is_peripheral_role_active=lambda: True,
    )
    after_unload_socket, _ = await bus.acquire_notify(options(_PEER_PATH))
    after_unload = transport.PairlinkPeerIdentity(
        _ADAPTER_PATH,
        _PEER_PATH,
        _PEER_ADDRESS,
        4,
    )
    assert after_unload != rejoined
    await backend.async_stop()
    assert after_unload_socket.recv(1) == b""
    after_unload_socket.close()


async def test_non_linux_is_rejected_before_opening_dbus(monkeypatch: pytest.MonkeyPatch) -> None:
    factory_calls = 0

    def make_bus() -> FakeBlueZBus:
        nonlocal factory_calls
        factory_calls += 1
        return FakeBlueZBus()

    monkeypatch.setattr(transport.sys, "platform", "darwin")
    backend = transport.PairlinkPeripheralBackend(bus_factory=make_bus)

    with pytest.raises(transport.PairlinkTransportCapabilityError, match="Linux"):
        await _start(backend)
    assert factory_calls == 0


async def test_tree_and_subscription_contract() -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    received: list[tuple[transport.PairlinkPeerIdentity, bytes]] = []

    def callback(peer: transport.PairlinkPeerIdentity, value: bytes) -> None:
        received.append((peer, value))

    profile = _profile()

    await _start(
        backend,
        profile=profile,
        on_peer_write=callback,
        is_peripheral_role_active=lambda: True,
    )

    expected_paths = (
        transport._APPLICATION_PATH,
        transport._SERVICE_PATH,
        transport._WRITE_CHARACTERISTIC_PATH,
        transport._NOTIFY_CHARACTERISTIC_PATH,
    )
    assert [event[1] for event in _events(bus, "export")[:4]] == list(expected_paths)
    assert _events(bus, "export")[4][1] == transport._ADVERTISEMENT_PATH
    names = [event[0] for event in bus.events]
    app_registration_index = names.index("register-application")
    advertisement_export_index = next(
        index
        for index, event in enumerate(bus.events)
        if event[:2] == ("export", transport._ADVERTISEMENT_PATH)
    )
    gatt_export_indices = [
        index
        for index, event in enumerate(bus.events)
        if event[:2] == ("export", transport._APPLICATION_PATH)
        or event[:2] == ("export", transport._SERVICE_PATH)
        or event[:2] == ("export", transport._WRITE_CHARACTERISTIC_PATH)
        or event[:2] == ("export", transport._NOTIFY_CHARACTERISTIC_PATH)
    ]
    assert max(gatt_export_indices) < app_registration_index
    assert app_registration_index < advertisement_export_index
    assert names.index("register-advertisement") > advertisement_export_index

    object_manager = _interface(bus, transport._APPLICATION_PATH)
    managed_method = object_manager.GetManagedObjects
    managed = managed_method.__wrapped__(object_manager)
    assert set(managed) == set(expected_paths[1:])
    write_properties = managed[transport._WRITE_CHARACTERISTIC_PATH][
        "org.bluez.GattCharacteristic1"
    ]
    assert write_properties["UUID"].value == "1235"
    assert write_properties["Flags"].value == ["read", "write"]
    assert write_properties["Value"].value == b"\x44"
    assert "Notifying" not in write_properties

    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)
    write_method = next(
        method
        for method in write_characteristic.introspect().methods
        if method.name == "WriteValue"
    )
    assert write_method.in_signature == "aya{sv}"
    assert write_method.out_signature == ""
    read_method = next(
        method for method in write_characteristic.introspect().methods if method.name == "ReadValue"
    )
    assert read_method.in_signature == "a{sv}"
    assert read_method.out_signature == "ay"
    read_value = write_characteristic.ReadValue.__wrapped__
    assert read_value(write_characteristic, {"offset": Variant("q", 0)}) == b"\x44"
    assert read_value(write_characteristic, {"offset": Variant("q", 1)}) == b""
    with pytest.raises(DBusError) as read_offset_error:
        read_value(write_characteristic, {"offset": Variant("q", 2)})
    assert read_offset_error.value.type == "org.bluez.Error.InvalidOffset"
    payload = bytes((1, 2, 3, 4))
    await _write_value(
        write_characteristic,
        payload,
        {
            "offset": Variant("q", 0),
            "type": Variant("s", "request"),
            "device": Variant("o", _PEER_PATH),
            "mtu": Variant("q", 23),
            "link": Variant("s", "LE"),
            "prepare-authorize": Variant("b", False),
        },
    )
    assert received == [
        (
            transport.PairlinkPeerIdentity(_ADAPTER_PATH, _PEER_PATH, _PEER_ADDRESS, 1),
            payload,
        )
    ]
    assert received[0][1] is not payload

    advertisement = _interface(bus, transport._ADVERTISEMENT_PATH)
    assert advertisement.Timeout == 0

    notify_characteristic = _interface(bus, transport._NOTIFY_CHARACTERISTIC_PATH)
    notify_read_value = notify_characteristic.ReadValue.__wrapped__
    assert notify_read_value(notify_characteristic, {"offset": Variant("q", 0)}) == b"\x66"
    assert notify_characteristic.NotifyAcquired is True
    acquire_method = next(
        method
        for method in notify_characteristic.introspect().methods
        if method.name == "AcquireNotify"
    )
    assert acquire_method.in_signature == "a{sv}"
    assert acquire_method.out_signature == "hq"

    class CapturedNotifier:
        def __init__(self) -> None:
            self.changed: list[dict[str, object]] = []

        def emit_properties_changed(self, changed_properties: dict[str, object]) -> None:
            self.changed.append(changed_properties)

    state = backend._exported_objects.notification_state
    notifier = CapturedNotifier()
    state.bind(notifier)
    acquired_socket, _mtu = await bus.acquire_notify(
        {
            "device": Variant("o", _PEER_PATH),
            "mtu": Variant("q", 23),
            "link": Variant("s", "LE"),
        }
    )

    assert notify_characteristic.Notifying is True
    await backend.async_notify_to_peer(received[0][0], b"synthetic")
    assert acquired_socket.recv(32) == b"synthetic"
    assert notifier.changed == [{"Notifying": True}]
    assert notify_characteristic.Value == b"\x66"
    assert notify_read_value(notify_characteristic, {"offset": Variant("q", 0)}) == b"\x66"
    assert notify_read_value(notify_characteristic, {"offset": Variant("q", 1)}) == b""
    with pytest.raises(transport.PairlinkTransportError, match="peer MTU"):
        await backend.async_notify_to_peer(received[0][0], b"x" * 21)
    with pytest.raises(DBusError) as unsupported_start_notify:
        notify_characteristic.StartNotify.__wrapped__(notify_characteristic)
    assert unsupported_start_notify.value.type == "org.bluez.Error.NotSupported"

    try:
        await backend.async_stop()
        with pytest.raises(DBusError) as error:
            notify_characteristic.StartNotify.__wrapped__(notify_characteristic)
        assert error.value.type == "org.bluez.Error.NotSupported"
        with pytest.raises(DBusError) as write_error:
            await _write_value(
                write_characteristic,
                b"must not reach callback",
                {"device": Variant("o", _PEER_PATH)},
            )
        assert write_error.value.type == "org.bluez.Error.NotPermitted"
        assert len(received) == 1
        with pytest.raises(transport.PairlinkTransportStateError, match="not ready"):
            await backend.async_notify_to_peer(received[0][0], b"synthetic")
    finally:
        await backend.async_stop()
        acquired_socket.close()


async def test_write_validation_and_sanitized_callback_errors() -> None:
    bus = FakeBlueZBus()

    def callback(_peer: transport.PairlinkPeerIdentity, _value: bytes) -> None:
        raise RuntimeError("private payload must not escape")

    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(backend, profile=_profile(with_advertisement=False), on_peer_write=callback)
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)

    with pytest.raises(DBusError) as offset_error:
        await _write_value(
            write_characteristic,
            b"payload",
            {"offset": Variant("q", 1), "device": Variant("o", _PEER_PATH)},
        )
    assert offset_error.value.type == "org.bluez.Error.Failed"

    with pytest.raises(DBusError) as length_error:
        await _write_value(write_characteristic, b"x" * 513, {"device": Variant("o", _PEER_PATH)})
    assert length_error.value.type == "org.bluez.Error.InvalidValueLength"

    with pytest.raises(DBusError) as callback_error:
        await _write_value(
            write_characteristic, b"secret bytes", {"device": Variant("o", _PEER_PATH)}
        )
    assert callback_error.value.type == "org.bluez.Error.Failed"
    assert "private payload" not in str(callback_error.value)
    assert "secret bytes" not in str(callback_error.value)

    with pytest.raises(DBusError) as option_error:
        await _write_value(
            write_characteristic, b"payload", {"offset": 4, "device": Variant("o", _PEER_PATH)}
        )
    assert option_error.value.type == "org.bluez.Error.InvalidArguments"

    with pytest.raises(DBusError) as type_error:
        await _write_value(
            write_characteristic,
            b"payload",
            {"type": Variant("s", "unknown"), "device": Variant("o", _PEER_PATH)},
        )
    assert type_error.value.type == "org.bluez.Error.InvalidArguments"

    with pytest.raises(DBusError) as reliable_error:
        await _write_value(
            write_characteristic,
            b"payload",
            {"type": Variant("s", "reliable"), "device": Variant("o", _PEER_PATH)},
        )
    assert reliable_error.value.type == "org.bluez.Error.Failed"

    with pytest.raises(DBusError) as prepare_error:
        await _write_value(
            write_characteristic,
            b"payload",
            {"prepare-authorize": Variant("b", True), "device": Variant("o", _PEER_PATH)},
        )
    assert prepare_error.value.type == "org.bluez.Error.Failed"

    with pytest.raises(DBusError) as bytes_type_error:
        await _write_value(
            write_characteristic, bytearray(b"payload"), {"device": Variant("o", _PEER_PATH)}
        )
    assert bytes_type_error.value.type == "org.bluez.Error.InvalidArguments"
    await backend.async_stop()


async def test_peer_writes_keep_two_current_identities_and_payloads_separate() -> None:
    second_address = "22:33:44:55:66:77"
    second_path = f"{_ADAPTER_PATH}/dev_{second_address.replace(':', '_')}"
    managed_objects = dict(_managed_objects())
    managed_objects[second_path] = _device(second_address)
    bus = FakeBlueZBus(managed_objects=managed_objects)
    sessions: dict[transport.PairlinkPeerIdentity, list[bytes]] = {}

    async def callback(peer: transport.PairlinkPeerIdentity, value: bytes) -> None:
        sessions.setdefault(peer, []).append(value)

    def disconnect(peer: transport.PairlinkPeerIdentity) -> None:
        sessions.pop(peer, None)

    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=callback,
        on_peer_disconnect=disconnect,
    )
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)

    for path, payload in ((_PEER_PATH, b"alpha"), (second_path, b"bravo")):
        await _write_value(
            write_characteristic,
            payload,
            {"device": Variant("o", path), "type": Variant("s", "request")},
        )

    assert sessions == {
        transport.PairlinkPeerIdentity(_ADAPTER_PATH, _PEER_PATH, _PEER_ADDRESS, 1): [b"alpha"],
        transport.PairlinkPeerIdentity(_ADAPTER_PATH, second_path, second_address, 2): [b"bravo"],
    }
    assert bus.peer_disconnect_callback is not None
    bus.peer_disconnect_callback(_PEER_PATH, False)
    assert sessions == {
        transport.PairlinkPeerIdentity(_ADAPTER_PATH, second_path, second_address, 2): [b"bravo"]
    }

    bus.managed_objects[_PEER_PATH] = _device()
    await _write_value(
        _interface(bus, transport._WRITE_CHARACTERISTIC_PATH),
        b"rejoined",
        {"device": Variant("o", _PEER_PATH)},
    )
    assert len(sessions) == 2
    assert any(peer.connection_generation == 3 for peer in sessions)
    await backend.async_stop()
    assert sessions == {}


@pytest.mark.parametrize(
    ("device_path", "device", "options"),
    [
        (_PEER_PATH, _device(), {}),
        (_PEER_PATH, _device(), {"device": Variant("s", _PEER_PATH)}),
        (
            _PEER_PATH,
            _device("22:33:44:55:66:77"),
            {"device": Variant("o", _PEER_PATH)},
        ),
        (
            _PEER_PATH,
            _device(adapter_path="/org/bluez/hci4"),
            {"device": Variant("o", _PEER_PATH)},
        ),
        (
            f"{_ADAPTER_PATH}/peer_without_device_address",
            _device(),
            {"device": Variant("o", f"{_ADAPTER_PATH}/peer_without_device_address")},
        ),
        (
            _PEER_PATH,
            _device(connected=False),
            {"device": Variant("o", _PEER_PATH)},
        ),
        (
            "/org/bluez/hci4/dev_11_22_33_44_55_66",
            _device(adapter_path="/org/bluez/hci4"),
            {"device": Variant("o", "/org/bluez/hci4/dev_11_22_33_44_55_66")},
        ),
    ],
)
async def test_peer_identity_failures_never_reach_the_write_callback(
    device_path: str,
    device: dict[str, dict[str, object]],
    options: dict[str, object],
) -> None:
    managed_objects = dict(_managed_objects())
    managed_objects.pop(_PEER_PATH, None)
    managed_objects[device_path] = device
    bus = FakeBlueZBus(managed_objects=managed_objects)
    received: list[tuple[transport.PairlinkPeerIdentity, bytes]] = []
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=lambda peer, value: received.append((peer, value)),
    )
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)

    with pytest.raises(DBusError) as error:
        await _write_value(write_characteristic, b"not-routed", options)

    assert error.value.type in ("org.bluez.Error.InvalidArguments", "org.bluez.Error.NotAuthorized")
    assert received == []
    assert backend.is_ready
    await backend.async_stop()


async def test_duplicate_current_peer_address_mapping_fails_closed() -> None:
    managed_objects = dict(_managed_objects())
    duplicate_path = f"{_ADAPTER_PATH}/dev_duplicate_peer_alias"
    managed_objects[duplicate_path] = _device()
    bus = FakeBlueZBus(managed_objects=managed_objects)
    received: list[tuple[transport.PairlinkPeerIdentity, bytes]] = []
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=lambda peer, value: received.append((peer, value)),
    )

    with pytest.raises(DBusError) as error:
        await _write_value(
            _interface(bus, transport._WRITE_CHARACTERISTIC_PATH),
            b"ambiguous-peer",
            {"device": Variant("o", _PEER_PATH)},
        )

    assert error.value.type == "org.bluez.Error.NotAuthorized"
    assert received == []
    assert backend.is_ready
    await backend.async_stop()


async def test_peer_write_callback_failure_does_not_echo_identity_or_payload() -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    def fail_with_sensitive_values(peer: transport.PairlinkPeerIdentity, value: bytes) -> None:
        raise RuntimeError(f"{peer.address} private payload {value!r}")

    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=fail_with_sensitive_values,
    )
    with pytest.raises(DBusError) as error:
        await _write_value(
            _interface(bus, transport._WRITE_CHARACTERISTIC_PATH),
            b"private payload",
            {"device": Variant("o", _PEER_PATH)},
        )

    assert error.value.type == "org.bluez.Error.Failed"
    assert _PEER_ADDRESS not in str(error.value)
    assert "private payload" not in str(error.value)
    assert backend.is_ready
    await backend.async_stop()


def test_peer_identity_cannot_guess_a_connection_generation() -> None:
    with pytest.raises(TypeError):
        transport.PairlinkPeerIdentity(_ADAPTER_PATH, _PEER_PATH, _PEER_ADDRESS)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("adapter_path", "device_path", "address", "generation"),
    [
        (
            _ADAPTER_PATH,
            f"{_ADAPTER_PATH}/dev_AA_BB_CC_DD_EE_FF",
            "aa:bb:cc:dd:ee:ff",
            1,
        ),
        (
            "/org/bluez/hci4",
            _PEER_PATH,
            _PEER_ADDRESS,
            1,
        ),
        (
            _ADAPTER_PATH,
            _PEER_PATH,
            "22:33:44:55:66:77",
            1,
        ),
        (_ADAPTER_PATH, _PEER_PATH, _PEER_ADDRESS, True),
    ],
)
def test_peer_identity_rejects_unbound_or_malformed_fields(
    adapter_path: str,
    device_path: str,
    address: str,
    generation: int,
) -> None:
    with pytest.raises(ValueError):
        transport.PairlinkPeerIdentity(adapter_path, device_path, address, generation)


def test_peer_identity_is_immutable() -> None:
    peer = transport.PairlinkPeerIdentity(
        _ADAPTER_PATH,
        _PEER_PATH,
        _PEER_ADDRESS,
        1,
    )

    with pytest.raises(AttributeError):
        peer.__setattr__("address", "22:33:44:55:66:77")


async def test_disconnect_unload_and_rejoin_issue_fresh_peer_identity() -> None:
    bus = FakeBlueZBus()
    identities: list[transport.PairlinkPeerIdentity] = []
    disconnected: list[transport.PairlinkPeerIdentity] = []
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    def callback(peer: transport.PairlinkPeerIdentity, _value: bytes) -> None:
        identities.append(peer)

    def disconnect(peer: transport.PairlinkPeerIdentity) -> None:
        disconnected.append(peer)

    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=callback,
        on_peer_disconnect=disconnect,
    )
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)

    async def write_peer() -> None:
        await _write_value(
            write_characteristic, b"fresh-event", {"device": Variant("o", _PEER_PATH)}
        )

    await write_peer()
    first_generation = identities[-1].connection_generation
    assert bus.peer_disconnect_callback is not None
    bus.managed_objects[_PEER_PATH] = _device(connected=False)
    bus.peer_disconnect_callback(_PEER_PATH, False)
    assert disconnected == [identities[0]]
    with pytest.raises(DBusError) as disconnected_error:
        await write_peer()
    assert disconnected_error.value.type == "org.bluez.Error.NotAuthorized"
    assert len(identities) == 1

    bus.managed_objects[_PEER_PATH] = _device(connected=True)
    await write_peer()
    second_generation = identities[-1].connection_generation
    assert second_generation > first_generation

    await backend.async_stop()
    assert disconnected[-1] == identities[-1]
    assert bus.peer_disconnect_callback is None
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=callback,
        on_peer_disconnect=disconnect,
    )
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)
    await write_peer()
    assert identities[-1].connection_generation > second_generation
    await backend.async_stop()
    assert disconnected[-1] == identities[-1]


async def test_current_disconnected_device_snapshot_cleans_stale_peer_before_rejoin() -> None:
    bus = FakeBlueZBus()
    identities: list[transport.PairlinkPeerIdentity] = []
    disconnected: list[transport.PairlinkPeerIdentity] = []
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_write=lambda peer, _value: identities.append(peer),
        on_peer_disconnect=disconnected.append,
    )
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)
    options = {"device": Variant("o", _PEER_PATH)}

    await _write_value(write_characteristic, b"first", options)
    first = identities[-1]
    bus.managed_objects[_PEER_PATH] = _device(connected=False)
    with pytest.raises(DBusError) as stale_error:
        await _write_value(write_characteristic, b"stale", options)
    assert stale_error.value.type == "org.bluez.Error.NotAuthorized"
    assert disconnected == [first]

    bus.managed_objects[_PEER_PATH] = _device(connected=True)
    await _write_value(write_characteristic, b"rejoined", options)
    assert identities[-1].connection_generation > first.connection_generation
    await backend.async_stop()


async def test_peer_session_cleanup_failure_stops_server_without_leaking_callback_error() -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    secret_text = "AA:BB:CC:DD:EE:FF auth-secret"

    def fail_cleanup(_peer: transport.PairlinkPeerIdentity) -> None:
        raise RuntimeError(secret_text)

    await _start(
        backend,
        profile=_profile(with_advertisement=False),
        on_peer_disconnect=fail_cleanup,
    )
    await _write_value(
        _interface(bus, transport._WRITE_CHARACTERISTIC_PATH),
        b"peer-write",
        {"device": Variant("o", _PEER_PATH)},
    )
    assert bus.peer_disconnect_callback is not None
    bus.peer_disconnect_callback(_PEER_PATH, False)
    await asyncio.wait_for(bus.disconnect_event.wait(), timeout=1)

    assert not backend.is_ready
    assert not bus.exports
    assert secret_text not in str(backend._background_cleanup_error)


async def test_registration_order_and_normal_cleanup_are_reverse_owned_order() -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(backend)
    await backend.async_stop()

    names = [event[0] for event in bus.events]
    register_app = names.index("register-application")
    register_ad = names.index("register-advertisement")
    unregister_ad = names.index("unregister-advertisement")
    unregister_app = names.index("unregister-application")
    assert register_app < register_ad < unregister_ad < unregister_app
    assert names[unregister_ad + 1] == "unexport"
    unexport_paths = [event[1] for event in _events(bus, "unexport")]
    assert unexport_paths == [
        transport._ADVERTISEMENT_PATH,
        transport._NOTIFY_CHARACTERISTIC_PATH,
        transport._WRITE_CHARACTERISTIC_PATH,
        transport._SERVICE_PATH,
        transport._APPLICATION_PATH,
    ]
    assert not bus.exports
    assert not bus.application_registered
    assert not bus.advertisement_registered
    assert not bus.connected


@pytest.mark.parametrize(
    "failure",
    [
        "connect",
        "watch-owner",
        "watch-peer-notify-acquire",
        "managed-objects",
        "export-0",
        "export-1",
        "export-2",
        "export-3",
        "register-application",
        "export-4",
        "register-advertisement",
    ],
)
async def test_partial_start_failure_unwinds_owned_resources(failure: str) -> None:
    bus = FakeBlueZBus(fail_at=failure)
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    with pytest.raises(transport.PairlinkTransportError) as error:
        await _start(backend)

    assert "private payload" not in str(error.value)
    assert not bus.exports
    assert not bus.application_registered
    assert not bus.advertisement_registered
    assert not bus.connected
    assert _events(bus, "disconnect")
    if failure in ("register-application", "export-4", "register-advertisement"):
        assert _events(bus, "unregister-application")
    if failure == "register-advertisement":
        assert _events(bus, "unregister-advertisement")


@pytest.mark.parametrize(
    "operation",
    [
        "connect",
        "watch-owner",
        "managed-objects",
        "register-application",
        "register-advertisement",
    ],
)
async def test_cancelled_pending_registration_unwinds_and_leaves_no_objects(
    operation: str,
) -> None:
    bus = FakeBlueZBus(block_at=operation)
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    start_task = asyncio.create_task(_start(backend))
    await asyncio.wait_for(bus.operation_started.wait(), timeout=1)

    start_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await start_task

    assert not bus.exports
    assert not bus.application_registered
    assert not bus.advertisement_registered
    assert not bus.connected
    if operation == "register-advertisement":
        assert _events(bus, "unregister-advertisement")
    if operation in ("register-application", "register-advertisement"):
        assert _events(bus, "unregister-application")
    else:
        assert not _events(bus, "unregister-application")


async def test_pending_registration_has_bounded_host_io_wait() -> None:
    bus = FakeBlueZBus(block_at="register-application")
    backend = transport.PairlinkPeripheralBackend(
        bus_factory=lambda: bus,
        io_timeout_seconds=0.01,
    )

    with pytest.raises(transport.PairlinkTransportCapabilityError, match="Timed out"):
        await _start(backend, profile=_profile(with_advertisement=False))

    assert bus.operation_started.is_set()
    assert not bus.application_registered
    assert not bus.exports
    assert not bus.connected


async def test_bluez_loss_during_gatt_registration_prevents_advertisement_start() -> None:
    bus = FakeBlueZBus(block_at="register-application")
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    start_task = asyncio.create_task(_start(backend))
    await asyncio.wait_for(bus.operation_started.wait(), timeout=1)
    assert bus.owner_callback is not None

    bus.owner_callback()
    bus.release_operation.set()
    with pytest.raises(transport.PairlinkTransportCapabilityError, match="BlueZ stopped"):
        await start_task

    assert not _events(bus, "register-advertisement")
    assert not bus.exports
    assert not bus.application_registered
    assert not bus.connected


async def test_cancelling_stop_waits_for_shielded_resource_cleanup() -> None:
    bus = FakeBlueZBus(block_at="unregister-advertisement")
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(backend)
    stop_task = asyncio.create_task(backend.async_stop())
    await asyncio.wait_for(bus.operation_started.wait(), timeout=1)

    stop_task.cancel()
    bus.release_operation.set()
    with pytest.raises(asyncio.CancelledError):
        await stop_task

    assert not bus.exports
    assert not bus.application_registered
    assert not bus.advertisement_registered
    assert not bus.connected


async def test_identical_start_and_stop_calls_are_idempotent() -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    def callback(_peer: transport.PairlinkPeerIdentity, _value: bytes) -> None:
        return None

    await _start(backend, on_peer_write=callback)
    await _start(backend, on_peer_write=callback)
    assert len(_events(bus, "register-application")) == 1
    assert len(_events(bus, "register-advertisement")) == 1

    await backend.async_stop()
    await backend.async_stop()
    assert len(_events(bus, "unregister-application")) == 1
    assert len(_events(bus, "unregister-advertisement")) == 1
    assert len(_events(bus, "disconnect")) == 1


async def test_advertisement_release_stops_owned_application() -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(backend)

    advertisement = _interface(bus, transport._ADVERTISEMENT_PATH)
    assert advertisement.Type == "peripheral"
    assert advertisement.ServiceUUIDs == ["1234"]
    assert advertisement.LocalName == "Synthetic Pairlink Fixture"
    assert advertisement.Includes == ["local-name"]
    assert advertisement.ManufacturerData[0].value == bytes.fromhex("C0FF05010203040506070809")
    advertisement.Release()
    await asyncio.wait_for(bus.disconnect_event.wait(), timeout=1)

    assert not _events(bus, "unregister-advertisement")
    assert _events(bus, "unregister-application")
    assert not bus.exports
    assert not bus.connected


async def test_advertisement_release_during_start_unwinds_partial_registration() -> None:
    bus = FakeBlueZBus(release_advertisement_on_register=True)
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)

    with pytest.raises(
        transport.PairlinkTransportStateError,
        match="released the Pairlink advertisement",
    ):
        await _start(backend)

    assert not _events(bus, "unregister-advertisement")
    assert _events(bus, "unregister-application")
    assert not bus.exports
    assert not bus.advertisement_registered
    assert not bus.connected


@pytest.mark.parametrize("loss", ["owner", "connection"])
async def test_bluez_loss_unexports_without_calls_to_a_gone_service(loss: str) -> None:
    bus = FakeBlueZBus()
    backend = transport.PairlinkPeripheralBackend(bus_factory=lambda: bus)
    await _start(backend)

    if loss == "owner":
        assert callable(bus.owner_callback)
        assert bus.owner_callback is not None
        bus.owner_callback()
    else:
        await bus.drop_connection()
    await asyncio.wait_for(bus.disconnect_event.wait(), timeout=1)

    assert not _events(bus, "unregister-advertisement")
    assert not _events(bus, "unregister-application")
    assert not bus.exports
