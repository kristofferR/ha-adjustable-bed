"""Pairlink's opt-in local BlueZ GATT server transport.

The ordinary Pairlink route remains a Home Assistant/Bleak central client. This
module owns only the separate Linux host-peripheral registration. Its caller
supplies the frozen, artifact-backed profile; the module has no production UUID,
flag, or advertisement defaults.

The server objects are exported directly to BlueZ over a private system-bus
connection. They do not register scanners, change adapter state, or manage
Home Assistant's Bluetooth lifecycle.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import socket
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from dbus_fast.aio import MessageBus
    from dbus_fast.message import Message

_BLUEZ_SERVICE = "org.bluez"
_ADAPTER_INTERFACE = "org.bluez.Adapter1"
_GATT_MANAGER_INTERFACE = "org.bluez.GattManager1"
_ADVERTISING_MANAGER_INTERFACE = "org.bluez.LEAdvertisingManager1"
_OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
_GATT_SERVICE_INTERFACE = "org.bluez.GattService1"
_GATT_CHARACTERISTIC_INTERFACE = "org.bluez.GattCharacteristic1"
_DEVICE_INTERFACE = "org.bluez.Device1"
_ADVERTISEMENT_INTERFACE = "org.bluez.LEAdvertisement1"
_DBUS_INTERFACE = "org.freedesktop.DBus"
_DBUS_PATH = "/org/freedesktop/DBus"
_BLUEZ_OWNER_MATCH = (
    "type='signal',sender='org.freedesktop.DBus',"
    "interface='org.freedesktop.DBus',member='NameOwnerChanged'"
)
_BLUEZ_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
_BLUEZ_PEER_REMOVED_MATCH = (
    "type='signal',sender='org.bluez',path='/',"
    "interface='org.freedesktop.DBus.ObjectManager',member='InterfacesRemoved'"
)
_APPLICATION_PATH = "/org/homeassistant/adjustable_bed/pairlink"
_SERVICE_PATH = f"{_APPLICATION_PATH}/service0"
_WRITE_CHARACTERISTIC_PATH = f"{_SERVICE_PATH}/char0"
_NOTIFY_CHARACTERISTIC_PATH = f"{_SERVICE_PATH}/char1"
_PEER_WRITE_CALL_PATH = _WRITE_CHARACTERISTIC_PATH
_ADVERTISEMENT_PATH = "/org/homeassistant/adjustable_bed/pairlink_advertisement"
_MAX_ATTRIBUTE_VALUE_LENGTH = 512
_DEFAULT_BLUEZ_IO_TIMEOUT = 10.0
_SAFE_BLUEZ_ERROR_CATEGORIES = frozenset(
    {
        "permission denied",
        "BlueZ service unavailable",
        "BlueZ object unavailable",
        "BlueZ method unavailable",
        "not registered",
        "capability unsupported",
        "already registered",
        "BlueZ rejected the supplied profile",
        "BlueZ rejected advertisement length",
        "BlueZ call failed",
    }
)
_BLUEZ_PREFLIGHT_PROPERTIES = {
    _ADAPTER_INTERFACE: frozenset({"Address", "Powered"}),
    _GATT_MANAGER_INTERFACE: frozenset(),
    _ADVERTISING_MANAGER_INTERFACE: frozenset(
        {
            "SupportedInstances",
            "ActiveInstances",
            "SupportedIncludes",
            "CanSetTxPower",
            "MinTxPower",
            "MaxTxPower",
        }
    ),
    _DEVICE_INTERFACE: frozenset({"Adapter", "Address", "Connected"}),
}
_DBUS_OBJECT_PATH_PATTERN = re.compile(r"/(?:[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*)?")


class PairlinkTransportError(RuntimeError):
    """Sanitized transport failure without BlueZ payloads or error strings."""


class PairlinkTransportCapabilityError(PairlinkTransportError):
    """The selected local host cannot provide this Pairlink transport role."""


class PairlinkTransportStateError(PairlinkTransportError):
    """The Pairlink local server is not in a state that permits this operation."""


class PairlinkGattFlag(StrEnum):
    """Gatt flags supported by this narrow Pairlink server boundary."""

    READ = "read"
    WRITE = "write"
    WRITE_WITHOUT_RESPONSE = "write-without-response"
    NOTIFY = "notify"
    INDICATE = "indicate"


class PairlinkGattPermission(StrEnum):
    """Source permission facts that BlueZ's characteristic flags may not express."""

    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class PairlinkGattDescriptorProfile:
    """Accepted CCC descriptor facts; BlueZ owns its live per-peer state."""

    uuid: str
    characteristic_uuid: str
    flags: tuple[PairlinkGattFlag, ...]
    read_value: bytes | None = None
    permissions: tuple[PairlinkGattPermission, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.uuid, str) or not isinstance(self.characteristic_uuid, str):
            raise TypeError("Pairlink descriptor UUIDs must be strings")
        _validate_uuid(self.uuid, "Pairlink descriptor UUID")
        _validate_uuid(self.characteristic_uuid, "Pairlink descriptor parent UUID")
        if type(self.flags) is not tuple or not self.flags:
            raise TypeError("Pairlink descriptor flags must be a non-empty immutable tuple")
        if any(not isinstance(flag, PairlinkGattFlag) for flag in self.flags):
            raise TypeError("Pairlink descriptor flags must use PairlinkGattFlag values")
        if any(flag not in (PairlinkGattFlag.READ, PairlinkGattFlag.WRITE) for flag in self.flags):
            raise ValueError("Pairlink descriptor flags support only read and write")
        if len(set(self.flags)) != len(self.flags):
            raise ValueError("Pairlink descriptor flags must be unique")
        if (PairlinkGattFlag.READ in self.flags) != (self.read_value is not None):
            raise ValueError("Pairlink descriptor read flags require an explicit read value")
        if self.read_value is not None and (
            not isinstance(self.read_value, bytes) or len(self.read_value) > 512
        ):
            raise ValueError("Pairlink descriptor read value must fit the GATT limit")
        if self.permissions is not None and (
            type(self.permissions) is not tuple
            or any(
                not isinstance(permission, PairlinkGattPermission)
                for permission in self.permissions
            )
            or len(set(self.permissions)) != len(self.permissions)
        ):
            raise TypeError("Pairlink descriptor permissions must be distinct immutable values")


class _BackendState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"


AdvertisementInclude = Literal["tx-power", "appearance", "local-name", "rsi"]
AdapterTransport = Literal["local", "proxy", "unknown"]


@dataclass(frozen=True, slots=True)
class PairlinkHostAdapterInventoryEntry:
    """One current scanner source from Home Assistant's public inventory.

    For a host BlueZ scanner, Home Assistant's source is the adapter address.
    ``active`` must reflect the current scanner inventory, not a saved routing
    preference. ``adapter`` is the scanner's Linux adapter name (for example,
    an ``hciN`` identifier) from that same public inventory.
    """

    source: str
    transport: AdapterTransport
    adapter: str
    active: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not isinstance(self.adapter, str):
            raise TypeError("Bluetooth source and adapter must be strings")
        if not isinstance(self.transport, str):
            raise TypeError("Bluetooth transport must be a string")
        if self.transport not in ("local", "proxy", "unknown"):
            raise ValueError("Unsupported Home Assistant Bluetooth transport")
        if type(self.active) is not bool:
            raise TypeError("Bluetooth inventory active state must be boolean")


@dataclass(frozen=True, slots=True)
class PairlinkPeerIdentity:
    """Current BlueZ identity bound to one peer write on the selected adapter."""

    adapter_path: str
    device_path: str
    address: str
    connection_generation: int

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) for value in (self.adapter_path, self.device_path, self.address)
        ):
            raise TypeError("Pairlink peer identity fields must be strings")
        normalized = _normalize_peer_address(self.address)
        if normalized is None or normalized != self.address:
            raise ValueError("Pairlink peer address must be a normalized six-byte MAC")
        if _DBUS_OBJECT_PATH_PATTERN.fullmatch(self.adapter_path) is None:
            raise ValueError("Pairlink adapter path must be a D-Bus object path")
        if re.fullmatch(r"/org/bluez/hci[0-9]+", self.adapter_path) is None:
            raise ValueError("Pairlink adapter path must identify a BlueZ hci adapter")
        if _DBUS_OBJECT_PATH_PATTERN.fullmatch(self.device_path) is None:
            raise ValueError("Pairlink device path must be a D-Bus object path")
        expected_device_path = f"{self.adapter_path}/dev_{normalized.replace(':', '_')}"
        if self.device_path != expected_device_path:
            raise ValueError("Pairlink device path must match its current adapter and address")
        if (
            isinstance(self.connection_generation, bool)
            or not isinstance(self.connection_generation, int)
            or self.connection_generation < 1
        ):
            raise ValueError("Pairlink peer connection generation must be positive")


class PairlinkPeerLifecycleKind(StrEnum):
    """Verified physical-link and notify-subscription transitions."""

    CONNECTED = "connected"
    NOTIFY_SUBSCRIBED = "notify_subscribed"
    NOTIFY_UNSUBSCRIBED = "notify_unsubscribed"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class PairlinkPeerLifecycleEvent:
    """One BlueZ lifecycle event bound to an exact current peer identity."""

    kind: PairlinkPeerLifecycleKind
    peer: PairlinkPeerIdentity
    mtu: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PairlinkPeerLifecycleKind):
            raise TypeError("Pairlink lifecycle kind must use its typed enum")
        if not isinstance(self.peer, PairlinkPeerIdentity):
            raise TypeError("Pairlink lifecycle requires a verified peer identity")
        if self.kind is PairlinkPeerLifecycleKind.NOTIFY_SUBSCRIBED:
            if isinstance(self.mtu, bool) or not isinstance(self.mtu, int) or self.mtu < 3:
                raise ValueError("Pairlink subscription requires a negotiated MTU")
        elif self.mtu is not None:
            raise ValueError("Only a Pairlink subscription event carries an MTU")


PairlinkPeerWriteCallback = Callable[[PairlinkPeerIdentity, bytes], Awaitable[None] | None]
PairlinkPeerDisconnectCallback = Callable[[PairlinkPeerIdentity], None]
PairlinkPeerLifecycleCallback = Callable[[PairlinkPeerLifecycleEvent], None]
PeerIdentityResolver = Callable[[str], Awaitable[PairlinkPeerIdentity]]
PairlinkPeripheralRoleGate = Callable[[], bool]
PairlinkPeerNotifyAcquireCallback = Callable[
    [Mapping[str, object]], Awaitable[tuple[socket.socket, int]]
]


@dataclass(slots=True)
class _PeerNotifySession:
    """One BlueZ-acquired notification socket bound to one peer generation."""

    identity: PairlinkPeerIdentity
    local_socket: socket.socket
    mtu: int


@dataclass(frozen=True, slots=True)
class PairlinkAdvertisementProfile:
    """Artifact-backed properties for this Pairlink advertisement."""

    advertisement_type: str
    service_uuids: tuple[str, ...]
    local_name: str | None
    includes: tuple[AdvertisementInclude, ...]
    manufacturer_data: tuple[tuple[int, bytes], ...] = ()
    start_delay_ms: int = 0
    timeout_seconds: int | None = None
    minimum_interval_ms: int | None = None
    maximum_interval_ms: int | None = None
    tx_power_dbm: int | None = None
    source_advertise_mode: int | None = None
    source_tx_power_level: int | None = None
    source_include_tx_power: bool | None = None

    def __post_init__(self) -> None:
        if (
            type(self.service_uuids) is not tuple
            or type(self.includes) is not tuple
            or type(self.manufacturer_data) is not tuple
        ):
            raise TypeError("Advertisement profile collections must be immutable tuples")
        if not isinstance(self.advertisement_type, str):
            raise TypeError("Advertisement type must be a string")
        if self.advertisement_type not in ("peripheral", "broadcast"):
            raise ValueError("Unsupported BlueZ advertisement type")
        _validate_uuid_list(self.service_uuids, "advertisement service UUID")
        if self.local_name is not None:
            if not isinstance(self.local_name, str):
                raise TypeError("Advertisement local name must be a string when supplied")
            if not self.local_name:
                raise ValueError("Advertisement local name must be non-empty when supplied")
        if any(not isinstance(value, str) for value in self.includes):
            raise TypeError("Advertisement includes must be strings")
        if len(set(self.includes)) != len(self.includes):
            raise ValueError("Advertisement includes must be unique")
        if not set(self.includes) <= {"tx-power", "appearance", "local-name", "rsi"}:
            raise ValueError("Unsupported BlueZ advertisement include")
        if (
            isinstance(self.start_delay_ms, bool)
            or not isinstance(self.start_delay_ms, int)
            or self.start_delay_ms < 0
        ):
            raise ValueError("Advertisement start delay must be a non-negative integer")
        if self.timeout_seconds is not None and (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 0 <= self.timeout_seconds <= 0xFFFF
        ):
            raise ValueError("Advertisement timeout must fit an unsigned 16-bit value")
        for name, value in (
            ("minimum advertising interval", self.minimum_interval_ms),
            ("maximum advertising interval", self.maximum_interval_ms),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFF
            ):
                raise ValueError(f"{name.capitalize()} must fit an unsigned 16-bit value")
        if (
            self.minimum_interval_ms is None
        ) != (self.maximum_interval_ms is None):
            raise ValueError("Both Pairlink advertising interval bounds must be supplied together")
        if (
            self.minimum_interval_ms is not None
            and self.maximum_interval_ms is not None
            and self.minimum_interval_ms > self.maximum_interval_ms
        ):
            raise ValueError("Pairlink advertising interval bounds are reversed")
        if self.tx_power_dbm is not None and (
            isinstance(self.tx_power_dbm, bool)
            or not isinstance(self.tx_power_dbm, int)
            or not -0x8000 <= self.tx_power_dbm <= 0x7FFF
        ):
            raise ValueError("Advertisement transmit power must fit a signed 16-bit value")
        for name, value in (
            ("source advertisement mode", self.source_advertise_mode),
            ("source transmit power level", self.source_tx_power_level),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF
            ):
                raise ValueError(f"{name.capitalize()} must fit one byte")
        if (
            self.source_include_tx_power is not None
            and type(self.source_include_tx_power) is not bool
        ):
            raise TypeError("Source include-TX-power value must be boolean")
        company_ids: set[int] = set()
        for entry in self.manufacturer_data:
            if type(entry) is not tuple or len(entry) != 2:
                raise TypeError("Manufacturer data must contain immutable ID/value pairs")
            company_id, value = entry
            if (
                isinstance(company_id, bool)
                or not isinstance(company_id, int)
                or not 0 <= company_id <= 0xFFFF
            ):
                raise ValueError("Manufacturer ID must fit an unsigned 16-bit value")
            if not isinstance(value, bytes) or len(value) > 29:
                raise ValueError("Manufacturer data must fit the accepted 29-byte payload")
            if company_id in company_ids:
                raise ValueError("Manufacturer IDs must be unique")
            company_ids.add(company_id)


@dataclass(frozen=True, slots=True)
class PairlinkPeripheralProfile:
    """Caller-supplied, immutable Pairlink GATT and advertisement profile.

    The supported tree has one service, one peer-write characteristic, and one
    host-notify characteristic. UUIDs and characteristic flags are required
    constructor arguments so the transport cannot silently choose protocol
    values. ``advertisement=None`` means the accepted route does not advertise.
    """

    service_uuid: str
    write_characteristic_uuid: str
    notify_characteristic_uuid: str
    write_flags: tuple[PairlinkGattFlag, ...]
    notify_flags: tuple[PairlinkGattFlag, ...]
    advertisement: PairlinkAdvertisementProfile | None
    write_read_value: bytes | None = None
    notify_read_value: bytes | None = None
    notify_descriptor: PairlinkGattDescriptorProfile | None = None
    write_permissions: tuple[PairlinkGattPermission, ...] | None = None
    notify_permissions: tuple[PairlinkGattPermission, ...] | None = None

    def __post_init__(self) -> None:
        if type(self.write_flags) is not tuple or type(self.notify_flags) is not tuple:
            raise TypeError("Pairlink GATT flags must be immutable tuples")
        if self.advertisement is not None and not isinstance(
            self.advertisement, PairlinkAdvertisementProfile
        ):
            raise TypeError("Pairlink advertisement must use its typed profile")
        if self.notify_descriptor is not None and not isinstance(
            self.notify_descriptor, PairlinkGattDescriptorProfile
        ):
            raise TypeError("Pairlink notify descriptor must use its typed profile")
        for permissions in (self.write_permissions, self.notify_permissions):
            if permissions is not None and (
                type(permissions) is not tuple
                or any(
                    not isinstance(permission, PairlinkGattPermission) for permission in permissions
                )
                or len(set(permissions)) != len(permissions)
            ):
                raise TypeError("Pairlink GATT permissions must be distinct immutable values")
        for flag_set, value, name in (
            (self.write_flags, self.write_read_value, "peer-write"),
            (self.notify_flags, self.notify_read_value, "host-notify"),
        ):
            if value is not None and (not isinstance(value, bytes) or len(value) > 512):
                raise ValueError(f"{name} read value must fit the GATT attribute limit")
            if (PairlinkGattFlag.READ in flag_set) != (value is not None):
                raise ValueError(f"{name} read flags require an explicit read value")
        uuids = (
            self.service_uuid,
            self.write_characteristic_uuid,
            self.notify_characteristic_uuid,
        )
        if any(not isinstance(value, str) for value in uuids):
            raise TypeError("Pairlink GATT UUIDs must be strings")
        for value in uuids:
            _validate_uuid(value, "Pairlink GATT UUID")
        if len({value.casefold() for value in uuids}) != len(uuids):
            raise ValueError("Pairlink service and characteristic UUIDs must be distinct")
        if self.notify_descriptor is not None and (
            self.notify_descriptor.characteristic_uuid.casefold()
            != self.notify_characteristic_uuid.casefold()
        ):
            raise ValueError("Pairlink notify descriptor must belong to the notify characteristic")
        if self.notify_descriptor is not None:
            descriptor_uuid = self.notify_descriptor.uuid.casefold()
            if descriptor_uuid not in {
                "2902",
                "00002902-0000-1000-8000-00805f9b34fb",
            }:
                raise ValueError("BlueZ-managed Pairlink notify descriptor must be the CCCD")
            if (
                set(self.notify_descriptor.flags)
                != {
                    PairlinkGattFlag.READ,
                    PairlinkGattFlag.WRITE,
                }
                or self.notify_descriptor.read_value != b"\x01\x00"
            ):
                raise ValueError("Pairlink CCCD source profile does not match accepted evidence")

        allowed_write_flags = {
            PairlinkGattFlag.READ,
            PairlinkGattFlag.WRITE,
            PairlinkGattFlag.WRITE_WITHOUT_RESPONSE,
        }
        if any(not isinstance(flag, PairlinkGattFlag) for flag in self.write_flags):
            raise TypeError("Peer-write flags must use PairlinkGattFlag values")
        if (
            not self.write_flags
            or not set(self.write_flags) <= allowed_write_flags
            or not set(self.write_flags)
            & {PairlinkGattFlag.WRITE, PairlinkGattFlag.WRITE_WITHOUT_RESPONSE}
        ):
            raise ValueError("Peer-write flags must describe a supported write operation")
        if len(set(self.write_flags)) != len(self.write_flags):
            raise ValueError("Peer-write flags must be unique")

        allowed_notify_flags = {
            PairlinkGattFlag.READ,
            PairlinkGattFlag.NOTIFY,
            PairlinkGattFlag.INDICATE,
        }
        if any(not isinstance(flag, PairlinkGattFlag) for flag in self.notify_flags):
            raise TypeError("Host-notify flags must use PairlinkGattFlag values")
        if (
            not self.notify_flags
            or not set(self.notify_flags) <= allowed_notify_flags
            or not set(self.notify_flags) & {PairlinkGattFlag.NOTIFY, PairlinkGattFlag.INDICATE}
        ):
            raise ValueError("Host-notify flags must describe notifications or indications")
        if len(set(self.notify_flags)) != len(self.notify_flags):
            raise ValueError("Host-notify flags must be unique")


def _validate_source_profile_compatibility(profile: PairlinkPeripheralProfile) -> None:
    """Validate BlueZ-relevant requirements without treating Android metadata as gates.

    BlueZ owns each peer's CCCD and reports subscriptions through AcquireNotify.
    Android descriptor callbacks, permission bits, and advertise-mode integers
    are retained as evidence metadata but have no public BlueZ equivalent.
    """
    if profile.advertisement is None:
        return
    if "tx-power" in profile.advertisement.includes:
        raise PairlinkTransportCapabilityError(
            "Pairlink advertisement cannot request a TxPower AD include"
        )


class PairlinkBlueZBus(Protocol):
    """Small injectable boundary for BlueZ calls and exported objects."""

    @property
    def is_connected(self) -> bool: ...

    async def async_connect(self) -> None: ...

    async def async_get_managed_objects(
        self,
    ) -> Mapping[str, Mapping[str, Mapping[str, object]]]: ...

    async def async_watch_bluez_owner(self, callback: Callable[[], None]) -> None: ...

    async def async_unwatch_bluez_owner(self) -> None: ...

    async def async_watch_peer_disconnect(
        self, adapter_path: str, callback: Callable[[str, bool], None]
    ) -> None: ...

    async def async_unwatch_peer_disconnect(self) -> None: ...

    async def async_watch_peer_write_producer(self, characteristic_path: str) -> None: ...

    async def async_unwatch_peer_write_producer(self) -> None: ...

    async def async_watch_peer_notify_acquire(
        self,
        characteristic_path: str,
        callback: PairlinkPeerNotifyAcquireCallback,
    ) -> None: ...

    async def async_unwatch_peer_notify_acquire(self) -> None: ...

    async def async_register_application(
        self, adapter_path: str, application_path: str
    ) -> None: ...

    async def async_unregister_application(
        self, adapter_path: str, application_path: str
    ) -> None: ...

    async def async_register_advertisement(
        self, adapter_path: str, advertisement_path: str
    ) -> None: ...

    async def async_unregister_advertisement(
        self, adapter_path: str, advertisement_path: str
    ) -> None: ...

    def export(self, object_path: str, interface: object) -> None: ...

    def unexport(self, object_path: str, interface_name: str) -> None: ...

    async def async_wait_for_disconnect(self) -> None: ...

    async def async_disconnect(self) -> None: ...


class _DisconnectWaiter(Protocol):
    """Typed view of dbus-fast's async disconnect wait method."""

    async def wait_for_disconnect(self) -> None: ...


BusFactory = Callable[[], PairlinkBlueZBus]
_IoResult = TypeVar("_IoResult")


@runtime_checkable
class _VariantLike(Protocol):
    @property
    def signature(self) -> str: ...

    @property
    def value(self) -> object: ...


@runtime_checkable
class _ExportedNotifier(Protocol):
    def emit_properties_changed(self, changed_properties: dict[str, object]) -> None: ...


class _NotificationState:
    """Peer subscription state for the local notify characteristic."""

    def __init__(self, is_owned: Callable[[], bool]) -> None:
        self._is_owned = is_owned
        self._subscriptions: set[PairlinkPeerIdentity] = set()
        self._notifier: _ExportedNotifier | None = None

    @property
    def notifying(self) -> bool:
        return bool(self._subscriptions)

    def bind(self, notifier: _ExportedNotifier) -> None:
        self._notifier = notifier

    def peer_acquired(self, peer: PairlinkPeerIdentity) -> None:
        if not self._is_owned():
            raise PairlinkTransportStateError("Pairlink GATT server is not ready")
        was_notifying = self.notifying
        self._subscriptions.add(peer)
        if not was_notifying:
            try:
                self._emit_notifying_changed(True)
            except PairlinkTransportError:
                self._subscriptions.discard(peer)
                raise

    def peer_released(self, peer: PairlinkPeerIdentity) -> None:
        if peer not in self._subscriptions:
            return
        self._subscriptions.remove(peer)
        if not self.notifying:
            self._emit_notifying_changed(False)

    def publish_to_peer(self, peer: PairlinkPeerIdentity, value: bytes) -> None:
        if not self._is_owned() or peer not in self._subscriptions:
            raise PairlinkTransportStateError("Pairlink peer has no active notify session")
        if len(value) > _MAX_ATTRIBUTE_VALUE_LENGTH:
            raise PairlinkTransportError("Pairlink notification exceeds the GATT attribute limit")

        # The FFD2 read value is source-defined and immutable. Peer notification
        # bytes travel only through the matching acquired socket.
        del value

    def reset(self) -> None:
        self._subscriptions.clear()
        self._notifier = None

    def _emit_notifying_changed(self, value: bool) -> None:
        if self._notifier is None:
            raise PairlinkTransportStateError("Pairlink GATT notifier is not owned")
        try:
            self._notifier.emit_properties_changed({"Notifying": value})
        except Exception:
            raise PairlinkTransportError(
                "BlueZ could not update Pairlink notification subscription state"
            ) from None


@dataclass(frozen=True, slots=True)
class _ExportedObjects:
    gatt_objects: tuple[tuple[str, str, object], ...]
    advertisement_object: object | None
    notification_state: _NotificationState


class PairlinkPeripheralBackend:
    """Own one evidence-configured Pairlink local server on a host BlueZ adapter."""

    def __init__(
        self,
        *,
        bus_factory: BusFactory | None = None,
        io_timeout_seconds: float = _DEFAULT_BLUEZ_IO_TIMEOUT,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if io_timeout_seconds <= 0:
            raise ValueError("BlueZ I/O timeout must be positive")
        self._bus_factory = bus_factory
        self._io_timeout_seconds = io_timeout_seconds
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._bus: PairlinkBlueZBus | None = None
        self._state = _BackendState.STOPPED
        self._adapter_path: str | None = None
        self._profile: PairlinkPeripheralProfile | None = None
        self._host_adapter_source: str | None = None
        self._peer_write_callback: PairlinkPeerWriteCallback | None = None
        self._peer_disconnect_callback: PairlinkPeerDisconnectCallback | None = None
        self._peer_lifecycle_callback: PairlinkPeerLifecycleCallback | None = None
        self._peripheral_role_gate: PairlinkPeripheralRoleGate | None = None
        self._exported_objects: _ExportedObjects | None = None
        self._exported_gatt_objects: list[tuple[str, str]] = []
        self._advertisement_exported = False
        self._application_registration_attempted = False
        self._application_registered = False
        self._advertisement_registration_attempted = False
        self._advertisement_released = False
        self._bluez_available = True
        self._ready = False
        self._peer_disconnect_watch_started = False
        self._peer_write_producer_watch_started = False
        self._peer_notify_acquire_watch_started = False
        self._peer_addresses: dict[str, str] = {}
        self._peer_generations: dict[str, int] = {}
        self._connected_peers: set[PairlinkPeerIdentity] = set()
        self._peer_notify_sessions: dict[PairlinkPeerIdentity, _PeerNotifySession] = {}
        self._next_peer_generation = 0
        self._disconnect_task: asyncio.Task[None] | None = None
        self._peer_connect_tasks: set[asyncio.Task[None]] = set()
        self._lifecycle_task: asyncio.Task[None] | None = None
        self._background_cleanup_error: PairlinkTransportError | None = None

    @property
    def is_ready(self) -> bool:
        """Return true only after all required BlueZ registrations succeed."""
        return self._state is _BackendState.READY and self._ready

    @property
    def adapter_path(self) -> str | None:
        """Return the exact current BlueZ adapter path selected from HA inventory."""
        return self._adapter_path if self.is_ready else None

    async def async_start(
        self,
        *,
        host_adapter_source: str,
        adapter_inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
        profile: PairlinkPeripheralProfile,
        on_peer_write: PairlinkPeerWriteCallback,
        on_peer_disconnect: PairlinkPeerDisconnectCallback | None = None,
        on_peer_lifecycle: PairlinkPeerLifecycleCallback | None = None,
        is_peripheral_role_active: PairlinkPeripheralRoleGate | None = None,
    ) -> None:
        """Export and register the caller's Pairlink profile on one local adapter."""
        self._require_linux()
        if not isinstance(profile, PairlinkPeripheralProfile):
            raise TypeError("Pairlink profile must use the immutable typed profile")
        if not callable(on_peer_write):
            raise TypeError("Pairlink peer-write callback must be callable")
        if on_peer_disconnect is not None and not callable(on_peer_disconnect):
            raise TypeError("Pairlink peer-disconnect callback must be callable")
        if on_peer_lifecycle is not None and not callable(on_peer_lifecycle):
            raise TypeError("Pairlink peer lifecycle callback must be callable")
        if is_peripheral_role_active is not None and not callable(is_peripheral_role_active):
            raise TypeError("Pairlink peripheral role gate must be callable")
        if profile.notify_descriptor is not None:
            if not _role_gate_is_active(is_peripheral_role_active):
                raise PairlinkTransportCapabilityError(
                    "Pairlink peripheral role is not active for the source descriptor callbacks"
                )
        selected = _select_inventory_entry(host_adapter_source, adapter_inventory)
        _validate_source_profile_compatibility(profile)

        async with self._lock:
            if self._state is _BackendState.READY:
                if (
                    self._host_adapter_source == host_adapter_source
                    and self._adapter_path == f"/org/bluez/{selected.adapter}"
                    and self._profile == profile
                    and self._peer_write_callback == on_peer_write
                    and self._peer_disconnect_callback == on_peer_disconnect
                    and self._peer_lifecycle_callback == on_peer_lifecycle
                    and self._peripheral_role_gate == is_peripheral_role_active
                ):
                    return
                raise PairlinkTransportStateError(
                    "Pairlink peripheral backend is already started with another profile"
                )
            if self._state is not _BackendState.STOPPED:
                raise PairlinkTransportStateError(
                    "Pairlink peripheral backend is already changing state"
                )

            self._state = _BackendState.STARTING
            self._host_adapter_source = host_adapter_source
            self._profile = profile
            self._peer_write_callback = on_peer_write
            self._peer_disconnect_callback = on_peer_disconnect
            self._peer_lifecycle_callback = on_peer_lifecycle
            self._peripheral_role_gate = is_peripheral_role_active
            self._bluez_available = True
            self._background_cleanup_error = None
            self._peer_addresses.clear()
            self._peer_generations.clear()
            self._connected_peers.clear()

            try:
                bus = self._bus_factory() if self._bus_factory is not None else _new_dbus_fast_bus()
                self._bus = bus
                await self._await_io("connecting to the system D-Bus", bus.async_connect())
                await self._await_io(
                    "watching the BlueZ service owner",
                    bus.async_watch_bluez_owner(self._on_bluez_disappeared),
                )
                self._disconnect_task = asyncio.create_task(self._watch_disconnect(bus))
                managed_objects = await self._await_io(
                    "reading BlueZ adapter capabilities",
                    bus.async_get_managed_objects(),
                )
                self._ensure_bluez_available()
                adapter_path = _resolve_bluez_adapter(
                    host_adapter_source,
                    selected,
                    managed_objects,
                    profile.advertisement,
                )
                self._adapter_path = adapter_path
                can_set_tx_power = _can_set_advertisement_tx_power(
                    adapter_path,
                    managed_objects,
                    profile.advertisement,
                )
                self._peer_disconnect_watch_started = True
                await self._await_io(
                    "watching Pairlink peer disconnects",
                    bus.async_watch_peer_disconnect(adapter_path, self._on_peer_connection_changed),
                )
                exported = _build_dbus_objects(
                    profile,
                    on_peer_write,
                    self._resolve_peer_identity,
                    self._is_gatt_owned,
                    self._on_advertisement_released,
                    is_peripheral_role_active,
                    can_set_tx_power=can_set_tx_power,
                )
                self._exported_objects = exported
                for object_path, interface_name, interface in exported.gatt_objects:
                    bus.export(object_path, interface)
                    self._exported_gatt_objects.append((object_path, interface_name))

                self._ensure_bluez_available()
                self._peer_write_producer_watch_started = True
                await self._await_io(
                    "verifying the Pairlink write producer",
                    bus.async_watch_peer_write_producer(_PEER_WRITE_CALL_PATH),
                )
                self._peer_notify_acquire_watch_started = True
                await self._await_io(
                    "verifying the Pairlink notify producer",
                    bus.async_watch_peer_notify_acquire(
                        _NOTIFY_CHARACTERISTIC_PATH,
                        self._acquire_peer_notify,
                    ),
                )
                self._ensure_bluez_available()
                self._application_registration_attempted = True
                await self._await_io(
                    "registering the Pairlink GATT application",
                    bus.async_register_application(adapter_path, _APPLICATION_PATH),
                )
                self._ensure_bluez_available()
                self._application_registered = True

                if profile.advertisement is not None:
                    if exported.advertisement_object is None:
                        raise PairlinkTransportError(
                            "Pairlink advertisement object was not created"
                        )
                    bus.export(_ADVERTISEMENT_PATH, exported.advertisement_object)
                    self._advertisement_exported = True
                    self._ensure_bluez_available()
                    if profile.advertisement.start_delay_ms:
                        await self._sleep(profile.advertisement.start_delay_ms / 1000)
                        self._ensure_bluez_available()
                    self._advertisement_registration_attempted = True
                    await self._await_io(
                        "registering the Pairlink LE advertisement",
                        bus.async_register_advertisement(adapter_path, _ADVERTISEMENT_PATH),
                    )
                    self._ensure_bluez_available()
                    if self._advertisement_released:
                        raise PairlinkTransportStateError(
                            "BlueZ released the Pairlink advertisement during startup"
                        )

                self._ready = True
                self._state = _BackendState.READY
            except asyncio.CancelledError:
                self._ready = False
                await self._cleanup_cancelled_start()
                raise
            except PairlinkTransportError as err:
                self._ready = False
                await self._cleanup_failed_start(err)
                raise
            except Exception:
                self._ready = False
                failure = PairlinkTransportError("Pairlink local BlueZ server setup failed")
                await self._cleanup_failed_start(failure)
                raise failure from None

    async def async_notify(self, value: bytes) -> None:
        """Reject identity-free local notifications instead of broadcasting them."""
        if not isinstance(value, bytes):
            raise TypeError("Pairlink notification value must be bytes")
        raise PairlinkTransportCapabilityError(
            "Pairlink notifications require a verified peer identity"
        )

    async def async_notify_to_peer(
        self,
        peer: PairlinkPeerIdentity,
        value: bytes,
        *,
        validate_send: Callable[[], None] | None = None,
    ) -> None:
        """Queue one notification through the exact peer's acquired BlueZ socket."""
        if not isinstance(peer, PairlinkPeerIdentity):
            raise TypeError("Pairlink notification peer must use the immutable identity record")
        if not isinstance(value, bytes):
            raise TypeError("Pairlink notification value must be bytes")
        async with self._lock:
            if not self.is_ready or self._exported_objects is None:
                if self._background_cleanup_error is not None:
                    raise PairlinkTransportStateError(
                        "Pairlink peripheral backend stopped after a BlueZ transport error"
                    ) from self._background_cleanup_error
                raise PairlinkTransportStateError("Pairlink peripheral backend is not ready")
            session = self._peer_notify_sessions.get(peer)
            if (
                session is None
                or peer.adapter_path != self._adapter_path
                or self._peer_generations.get(peer.device_path) != peer.connection_generation
                or self._peer_addresses.get(peer.device_path) != peer.address
            ):
                raise PairlinkTransportStateError("Pairlink peer notify session is not current")
            if not _role_gate_is_active(self._peripheral_role_gate):
                raise PairlinkTransportStateError("Pairlink peripheral role is not active")
            if len(value) > min(_MAX_ATTRIBUTE_VALUE_LENGTH, session.mtu - 3):
                raise PairlinkTransportError("Pairlink notification exceeds the peer MTU")
            # Keep action validation and socket admission in the same lock turn.
            if validate_send is not None:
                validate_send()
            try:
                sent = session.local_socket.send(value)
            except BlockingIOError:
                raise PairlinkTransportStateError("Pairlink peer notify queue is full") from None
            except OSError:
                self._on_peer_notify_unsubscribed(peer)
                raise PairlinkTransportStateError("Pairlink peer notify subscription closed") from None
            if sent != len(value):
                self._on_peer_notify_unsubscribed(peer)
                raise PairlinkTransportStateError(
                    "Pairlink peer notify did not accept the complete value"
                )
            self._exported_objects.notification_state.publish_to_peer(peer, value)

    async def _acquire_peer_notify(
        self, options: Mapping[str, object]
    ) -> tuple[socket.socket, int]:
        """Create a peer-scoped socket only for a current BlueZ Device1 request."""
        _validate_read_options(
            options,
            lambda _name, message: PairlinkTransportCapabilityError(message),
        )
        device_option = options.get("device")
        mtu_option = options.get("mtu")
        if (
            not isinstance(device_option, _VariantLike)
            or device_option.signature != "o"
            or not isinstance(device_option.value, str)
            or not isinstance(mtu_option, _VariantLike)
            or mtu_option.signature != "q"
            or type(mtu_option.value) is not int
            or mtu_option.value < 3
        ):
            raise PairlinkTransportCapabilityError(
                "Pairlink notify peer or negotiated MTU is invalid"
            )
        link_option = options.get("link")
        if isinstance(link_option, _VariantLike) and link_option.value != "LE":
            raise PairlinkTransportCapabilityError("Pairlink notify link is not Bluetooth LE")

        async with self._lock:
            if not self.is_ready or self._exported_objects is None:
                raise PairlinkTransportStateError("Pairlink local server is not ready")
            if not _role_gate_is_active(self._peripheral_role_gate):
                raise PairlinkTransportStateError("Pairlink peripheral role is not active")
            peer = await self._resolve_peer_identity(device_option.value)
            if peer in self._peer_notify_sessions:
                raise PairlinkTransportStateError("Pairlink peer already has a notify session")

            local_socket: socket.socket | None = None
            bluez_socket: socket.socket | None = None
            try:
                local_socket, bluez_socket = socket.socketpair(
                    socket.AF_UNIX,
                    socket.SOCK_SEQPACKET,
                )
                local_socket.setblocking(False)
                session = _PeerNotifySession(peer, local_socket, mtu_option.value)
                self._peer_notify_sessions[peer] = session
                asyncio.get_running_loop().add_reader(
                    local_socket.fileno(),
                    self._on_peer_notify_socket_ready,
                    peer,
                )
                self._exported_objects.notification_state.peer_acquired(peer)
                self._notify_peer_lifecycle(
                    PairlinkPeerLifecycleEvent(
                        PairlinkPeerLifecycleKind.NOTIFY_SUBSCRIBED,
                        peer,
                        mtu_option.value,
                    )
                )
                return bluez_socket, mtu_option.value
            except Exception:
                self._peer_notify_sessions.pop(peer, None)
                if local_socket is not None:
                    local_socket.close()
                if bluez_socket is not None:
                    bluez_socket.close()
                raise

    def _on_peer_notify_socket_ready(self, peer: PairlinkPeerIdentity) -> None:
        """Drop exact peer session when BlueZ closes its acquired socket."""
        session = self._peer_notify_sessions.get(peer)
        if session is None:
            return
        try:
            incoming = session.local_socket.recv(2)
        except BlockingIOError:
            return
        except OSError:
            incoming = b""
        if incoming == b"\x01":
            # BlueZ may report an indication confirmation on an INDICATE
            # profile. Pairlink's accepted production profile is NOTIFY-only.
            if (
                self._profile is not None
                and PairlinkGattFlag.INDICATE in self._profile.notify_flags
            ):
                return
        elif incoming:
            self._background_cleanup_error = PairlinkTransportStateError(
                "Pairlink peer notify socket received an unexpected value"
            )
        self._on_peer_notify_unsubscribed(peer)

    def _on_peer_connection_changed(self, device_path: str, connected: bool) -> None:
        """Use Device1.Connected for physical generation changes only."""
        if connected is not True:
            self._on_peer_disconnected(device_path)
            return
        task = asyncio.create_task(
            self._async_peer_connected(device_path, self._peer_generations.get(device_path))
        )
        self._peer_connect_tasks.add(task)
        task.add_done_callback(self._peer_connect_tasks.discard)

    async def _async_peer_connected(
        self, device_path: str, expected_generation: int | None
    ) -> None:
        try:
            if self._peer_generations.get(device_path) != expected_generation:
                return
            peer = await self._resolve_peer_identity(device_path)
            if (
                expected_generation is not None
                and peer.connection_generation == expected_generation
                and self._peer_generations.get(device_path) == expected_generation
            ):
                self._notify_peer_connected(peer, connection_observed=True)
        except asyncio.CancelledError:
            raise
        except PairlinkTransportError:
            return

    def _notify_peer_connected(
        self, peer: PairlinkPeerIdentity, *, connection_observed: bool = False
    ) -> None:
        if peer in self._connected_peers and not connection_observed:
            return
        self._connected_peers.add(peer)
        self._notify_peer_lifecycle(
            PairlinkPeerLifecycleEvent(PairlinkPeerLifecycleKind.CONNECTED, peer)
        )

    def _notify_peer_lifecycle(self, event: PairlinkPeerLifecycleEvent) -> None:
        callback = self._peer_lifecycle_callback
        if callback is not None:
            callback(event)

    def _on_peer_notify_unsubscribed(self, peer: PairlinkPeerIdentity) -> None:
        self._close_peer_notify_session(peer, notify_unsubscribed=False)
        self._notify_peer_lifecycle(
            PairlinkPeerLifecycleEvent(PairlinkPeerLifecycleKind.NOTIFY_UNSUBSCRIBED, peer)
        )

    async def _resolve_peer_identity(self, device_path: str) -> PairlinkPeerIdentity:
        """Verify a WriteValue peer against the current selected-adapter inventory."""
        bus = self._bus
        adapter_path = self._adapter_path
        if (
            bus is None
            or adapter_path is None
            or self._state not in (_BackendState.STARTING, _BackendState.READY)
            or not self._application_registered
            or not self._bluez_available
        ):
            raise PairlinkTransportStateError("Pairlink local server is not ready")
        if (
            not isinstance(device_path, str)
            or _DBUS_OBJECT_PATH_PATTERN.fullmatch(device_path) is None
        ):
            raise PairlinkTransportCapabilityError("Pairlink peer identity is invalid")
        if not device_path.startswith(f"{adapter_path}/dev_"):
            raise PairlinkTransportCapabilityError(
                "Pairlink peer is not connected through the selected BlueZ adapter"
            )

        managed_objects = await self._await_io(
            "verifying the Pairlink peer identity",
            bus.async_get_managed_objects(),
        )
        self._ensure_bluez_available()
        interfaces = managed_objects.get(device_path)
        device = interfaces.get(_DEVICE_INTERFACE) if interfaces is not None else None
        if device is None:
            raise PairlinkTransportCapabilityError(
                "Pairlink peer is not a current BlueZ Device1 object"
            )
        address = device.get("Address")
        peer_adapter = device.get("Adapter")
        connected = device.get("Connected")
        normalized_address = _normalize_peer_address(address) if isinstance(address, str) else None
        expected_device_path = (
            f"{adapter_path}/dev_{normalized_address.replace(':', '_')}"
            if normalized_address is not None
            else None
        )
        previous_address = self._peer_addresses.get(device_path)
        if previous_address is not None and (
            connected is not True
            or peer_adapter != adapter_path
            or expected_device_path != device_path
            or normalized_address != previous_address
            or not self._is_gatt_owned()
        ):
            # A disconnected or remapped Device1 path ends the old session even
            # if its PropertiesChanged signal was missed during a bus handoff.
            self._on_peer_disconnected(device_path)
        if (
            peer_adapter != adapter_path
            or normalized_address is None
            or expected_device_path != device_path
            or connected is not True
            or not self._is_gatt_owned()
        ):
            raise PairlinkTransportCapabilityError(
                "Pairlink peer address, adapter, or connection state did not match BlueZ"
            )

        mapped_paths: list[str] = []
        for path, object_interfaces in managed_objects.items():
            peer = object_interfaces.get(_DEVICE_INTERFACE)
            peer_address = peer.get("Address") if peer is not None else None
            if (
                peer is not None
                and peer.get("Adapter") == adapter_path
                and isinstance(peer_address, str)
                and _normalize_peer_address(peer_address) == normalized_address
            ):
                mapped_paths.append(path)
        if mapped_paths != [device_path]:
            if device_path in self._peer_generations:
                self._on_peer_disconnected(device_path)
            raise PairlinkTransportCapabilityError(
                "Pairlink peer address is ambiguous on the selected BlueZ adapter"
            )
        generation = self._peer_generations.get(device_path)
        if previous_address != normalized_address or generation is None:
            self._next_peer_generation += 1
            generation = self._next_peer_generation
            self._peer_addresses[device_path] = normalized_address
            self._peer_generations[device_path] = generation
        identity = PairlinkPeerIdentity(
            adapter_path,
            device_path,
            normalized_address,
            generation,
        )
        self._notify_peer_connected(identity)
        return identity

    async def async_stop(self) -> None:
        """Unregister and release only this backend's BlueZ objects."""
        async with self._lock:
            if self._state is _BackendState.STOPPED and self._bus is None:
                return
            self._state = _BackendState.STOPPING
            self._ready = False
            preserve_lifecycle_task = self._lifecycle_task is asyncio.current_task()
            peer_cleanup_error = self._notify_active_peer_disconnects()
            try:
                await self._shield_cleanup(preserve_lifecycle_task=preserve_lifecycle_task)
            except PairlinkTransportError as cleanup_error:
                if peer_cleanup_error is not None:
                    raise PairlinkTransportError(
                        "Pairlink peer session and BlueZ cleanup both failed"
                    ) from cleanup_error
                raise
            finally:
                self._reset_state()
            if peer_cleanup_error is not None:
                raise peer_cleanup_error

    async def _await_io(self, action: str, operation: Awaitable[_IoResult]) -> _IoResult:
        try:
            async with asyncio.timeout(self._io_timeout_seconds):
                return await operation
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise PairlinkTransportCapabilityError(
                f"Timed out while {action}; check host BlueZ availability and permissions"
            ) from None
        except PairlinkTransportError:
            raise
        except Exception as err:
            category = getattr(err, "category", None)
            suffix = (
                f" ({category})"
                if isinstance(category, str) and category in _SAFE_BLUEZ_ERROR_CATEGORIES
                else ""
            )
            raise PairlinkTransportCapabilityError(
                f"BlueZ could not complete {action}{suffix}"
            ) from None

    async def _cleanup_failed_start(self, original: PairlinkTransportError) -> None:
        try:
            await self._shield_cleanup()
        except PairlinkTransportError as cleanup_error:
            self._reset_state()
            raise PairlinkTransportError(
                f"{original}; local BlueZ cleanup also reported an error"
            ) from cleanup_error
        self._reset_state()

    async def _cleanup_cancelled_start(self) -> None:
        try:
            await self._shield_cleanup()
        finally:
            self._reset_state()

    async def _shield_cleanup(self, *, preserve_lifecycle_task: bool = False) -> None:
        cleanup_task = asyncio.create_task(
            self._cleanup_resources(preserve_lifecycle_task=preserve_lifecycle_task)
        )
        try:
            error = await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            error = await cleanup_task
            if error is not None:
                self._background_cleanup_error = error
            raise
        if error is not None:
            raise error

    async def _cleanup_resources(
        self, *, preserve_lifecycle_task: bool = False
    ) -> PairlinkTransportError | None:
        bus = self._bus
        adapter_path = self._adapter_path
        exported = self._exported_objects
        errors: list[str] = []
        self._close_all_peer_notify_sessions()

        if bus is not None and self._bluez_available and bus.is_connected:
            if self._advertisement_registration_attempted and adapter_path is not None:
                try:
                    await self._await_io(
                        "unregistering the Pairlink LE advertisement",
                        bus.async_unregister_advertisement(adapter_path, _ADVERTISEMENT_PATH),
                    )
                except PairlinkTransportError as err:
                    if "not registered" not in str(err) and "unavailable" not in str(err):
                        errors.append("advertisement unregister")

        if bus is not None and self._advertisement_exported:
            try:
                bus.unexport(_ADVERTISEMENT_PATH, _ADVERTISEMENT_INTERFACE)
            except Exception:
                errors.append("advertisement object unexport")
            self._advertisement_exported = False

        if (
            bus is not None
            and self._bluez_available
            and bus.is_connected
            and self._application_registration_attempted
            and adapter_path is not None
        ):
            try:
                await self._await_io(
                    "unregistering the Pairlink GATT application",
                    bus.async_unregister_application(adapter_path, _APPLICATION_PATH),
                )
            except PairlinkTransportError as err:
                if "not registered" not in str(err) and "unavailable" not in str(err):
                    errors.append("application unregister")

        if bus is not None and exported is not None:
            for object_path, interface_name in reversed(self._exported_gatt_objects):
                try:
                    bus.unexport(object_path, interface_name)
                except Exception:
                    errors.append("GATT object unexport")
            self._exported_gatt_objects.clear()
            exported.notification_state.reset()

        if bus is not None:
            await self._cancel_disconnect_watcher()
            for task in tuple(self._peer_connect_tasks):
                if task is not asyncio.current_task():
                    await self._cancel_task(task)
            self._peer_connect_tasks.clear()
            if self._peer_disconnect_watch_started:
                try:
                    await self._await_io(
                        "removing the Pairlink peer disconnect watch",
                        bus.async_unwatch_peer_disconnect(),
                    )
                except PairlinkTransportError as err:
                    if "not registered" not in str(err) and "unavailable" not in str(err):
                        errors.append("peer disconnect watch removal")
                self._peer_disconnect_watch_started = False
            if self._peer_write_producer_watch_started:
                try:
                    await self._await_io(
                        "removing the Pairlink write producer check",
                        bus.async_unwatch_peer_write_producer(),
                    )
                except PairlinkTransportError as err:
                    if "not registered" not in str(err) and "unavailable" not in str(err):
                        errors.append("peer write producer check removal")
                self._peer_write_producer_watch_started = False
            if self._peer_notify_acquire_watch_started:
                try:
                    await self._await_io(
                        "removing the Pairlink notify producer check",
                        bus.async_unwatch_peer_notify_acquire(),
                    )
                except PairlinkTransportError as err:
                    if "not registered" not in str(err) and "unavailable" not in str(err):
                        errors.append("peer notify producer check removal")
                self._peer_notify_acquire_watch_started = False
            try:
                await self._await_io(
                    "removing the BlueZ owner watch", bus.async_unwatch_bluez_owner()
                )
            except PairlinkTransportError as err:
                if "not registered" not in str(err) and "unavailable" not in str(err):
                    errors.append("BlueZ owner watch removal")
            try:
                await self._await_io(
                    "disconnecting from the system D-Bus",
                    bus.async_disconnect(),
                )
            except PairlinkTransportError:
                errors.append("system D-Bus disconnect")

        if self._lifecycle_task is not None:
            lifecycle_task = self._lifecycle_task
            self._lifecycle_task = None
            if not preserve_lifecycle_task and lifecycle_task is not asyncio.current_task():
                await self._cancel_task(lifecycle_task)

        if errors:
            return PairlinkTransportError(
                "Pairlink BlueZ cleanup had failures: " + ", ".join(errors)
            )
        return None

    async def _cancel_disconnect_watcher(self) -> None:
        task = self._disconnect_task
        self._disconnect_task = None
        if task is not None and task is not asyncio.current_task():
            await self._cancel_task(task)

    @staticmethod
    async def _cancel_task(task: asyncio.Task[None]) -> None:
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            if not task.cancelled():
                raise

    async def _watch_disconnect(self, bus: PairlinkBlueZBus) -> None:
        try:
            await bus.async_wait_for_disconnect()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._background_cleanup_error = PairlinkTransportError(
                "The system D-Bus connection was lost"
            )
        self._on_bluez_disappeared()

    def _on_bluez_disappeared(self) -> None:
        if self._state not in (_BackendState.STARTING, _BackendState.READY):
            return
        self._bluez_available = False
        self._ready = False
        if self._lifecycle_task is None or self._lifecycle_task.done():
            self._lifecycle_task = asyncio.create_task(self._stop_after_bluez_loss())

    def _on_advertisement_released(self) -> None:
        if self._state not in (_BackendState.STARTING, _BackendState.READY):
            return
        self._advertisement_released = True
        self._advertisement_registration_attempted = False
        self._ready = False
        if self._exported_objects is not None:
            self._exported_objects.notification_state.reset()
        if self._lifecycle_task is None or self._lifecycle_task.done():
            self._lifecycle_task = asyncio.create_task(self._stop_after_bluez_loss())

    def _on_peer_disconnected(self, device_path: str) -> None:
        adapter_path = self._adapter_path
        if (
            adapter_path is None
            or not isinstance(device_path, str)
            or not device_path.startswith(f"{adapter_path}/dev_")
        ):
            return
        identity = self._cached_peer_identity(device_path)
        if identity is None:
            for session_identity in tuple(self._peer_notify_sessions):
                if session_identity.device_path == device_path:
                    self._close_peer_notify_session(
                        session_identity,
                        notify_unsubscribed=False,
                    )
            self._peer_addresses.pop(device_path, None)
            self._peer_generations.pop(device_path, None)
            return
        callback = self._peer_disconnect_callback
        self._connected_peers.discard(identity)
        cleanup_error = self._close_peer_notify_session(
            identity,
            notify_unsubscribed=False,
        )
        try:
            if callback is not None:
                callback(identity)
            self._notify_peer_lifecycle(
                PairlinkPeerLifecycleEvent(PairlinkPeerLifecycleKind.DISCONNECTED, identity)
            )
        except Exception:
            self._background_cleanup_error = PairlinkTransportStateError(
                "Pairlink peer session cleanup callback failed"
            )
            self._ready = False
            if self._lifecycle_task is None or self._lifecycle_task.done():
                self._lifecycle_task = asyncio.create_task(self._stop_after_peer_callback_error())
            return
        self._peer_addresses.pop(device_path, None)
        self._peer_generations.pop(device_path, None)
        if cleanup_error is not None:
            self._background_cleanup_error = cleanup_error
            self._ready = False
            if self._lifecycle_task is None or self._lifecycle_task.done():
                self._lifecycle_task = asyncio.create_task(self._stop_after_peer_callback_error())

    def _cached_peer_identity(self, device_path: str) -> PairlinkPeerIdentity | None:
        adapter_path = self._adapter_path
        address = self._peer_addresses.get(device_path)
        generation = self._peer_generations.get(device_path)
        if adapter_path is None or address is None or generation is None:
            return None
        return PairlinkPeerIdentity(adapter_path, device_path, address, generation)

    def _notify_active_peer_disconnects(self) -> PairlinkTransportError | None:
        callback = self._peer_disconnect_callback
        failures = False
        for device_path in tuple(self._peer_generations):
            identity = self._cached_peer_identity(device_path)
            if identity is not None:
                self._connected_peers.discard(identity)
                if self._close_peer_notify_session(
                    identity,
                    notify_unsubscribed=False,
                ) is not None:
                    failures = True
                try:
                    if callback is not None:
                        callback(identity)
                    self._notify_peer_lifecycle(
                        PairlinkPeerLifecycleEvent(
                            PairlinkPeerLifecycleKind.DISCONNECTED,
                            identity,
                        )
                    )
                except Exception:
                    failures = True
            self._peer_addresses.pop(device_path, None)
            self._peer_generations.pop(device_path, None)
        self._close_all_peer_notify_sessions()
        if failures:
            return PairlinkTransportStateError(
                "Pairlink peer session cleanup callback failed during shutdown"
            )
        return None

    def _close_peer_notify_session(
        self,
        peer: PairlinkPeerIdentity,
        *,
        notify_unsubscribed: bool = True,
    ) -> PairlinkTransportError | None:
        session = self._peer_notify_sessions.pop(peer, None)
        if session is None:
            return None
        try:
            asyncio.get_running_loop().remove_reader(session.local_socket.fileno())
        except RuntimeError:
            pass
        session.local_socket.close()
        if self._exported_objects is None:
            return None
        try:
            self._exported_objects.notification_state.peer_released(peer)
        except PairlinkTransportError as err:
            return err
        if notify_unsubscribed:
            self._notify_peer_lifecycle(
                PairlinkPeerLifecycleEvent(
                    PairlinkPeerLifecycleKind.NOTIFY_UNSUBSCRIBED,
                    peer,
                )
            )
        return None

    def _close_all_peer_notify_sessions(self) -> None:
        for peer in tuple(self._peer_notify_sessions):
            self._close_peer_notify_session(peer)

    async def _stop_after_peer_callback_error(self) -> None:
        try:
            await self.async_stop()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._background_cleanup_error = PairlinkTransportStateError(
                "Pairlink backend cleanup failed after peer session cleanup error"
            )

    async def _stop_after_bluez_loss(self) -> None:
        try:
            await self.async_stop()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._background_cleanup_error = PairlinkTransportError(
                "Pairlink backend cleanup failed after BlueZ stopped providing the server"
            )

    def _is_gatt_owned(self) -> bool:
        return (
            self._application_registered
            and self._ready
            and self._state in (_BackendState.STARTING, _BackendState.READY)
        )

    def _ensure_bluez_available(self) -> None:
        if not self._bluez_available:
            raise PairlinkTransportCapabilityError(
                "BlueZ stopped providing the Pairlink server during startup"
            )

    def _reset_state(self) -> None:
        self._bus = None
        self._state = _BackendState.STOPPED
        self._adapter_path = None
        self._profile = None
        self._host_adapter_source = None
        self._peer_write_callback = None
        self._peer_disconnect_callback = None
        self._peer_lifecycle_callback = None
        self._peripheral_role_gate = None
        self._exported_objects = None
        self._exported_gatt_objects.clear()
        self._advertisement_exported = False
        self._application_registration_attempted = False
        self._application_registered = False
        self._advertisement_registration_attempted = False
        self._advertisement_released = False
        self._bluez_available = True
        self._ready = False
        self._peer_disconnect_watch_started = False
        self._peer_write_producer_watch_started = False
        self._peer_notify_acquire_watch_started = False
        self._peer_addresses.clear()
        self._peer_generations.clear()
        self._connected_peers.clear()
        self._peer_connect_tasks.clear()
        self._close_all_peer_notify_sessions()
        self._disconnect_task = None
        self._lifecycle_task = None

    @staticmethod
    def _require_linux() -> None:
        if not sys.platform.startswith("linux"):
            raise PairlinkTransportCapabilityError(
                "Pairlink local peripheral mode is available only on Linux with BlueZ"
            )


def _select_inventory_entry(
    source: str,
    inventory: tuple[PairlinkHostAdapterInventoryEntry, ...],
) -> PairlinkHostAdapterInventoryEntry:
    if not isinstance(source, str) or type(inventory) is not tuple:
        raise TypeError("Bluetooth source and inventory must use their typed values")
    if any(not isinstance(entry, PairlinkHostAdapterInventoryEntry) for entry in inventory):
        raise TypeError("Bluetooth inventory contains an untyped source entry")
    matches = [entry for entry in inventory if entry.source == source]
    if len(matches) != 1:
        raise PairlinkTransportCapabilityError(
            "Selected Pairlink source is missing or ambiguous in "
            "Home Assistant's current Bluetooth inventory"
        )
    selected = matches[0]
    if selected.transport != "local":
        raise PairlinkTransportCapabilityError(
            "Pairlink peripheral mode requires a host-local BlueZ source"
        )
    if not selected.active:
        raise PairlinkTransportCapabilityError(
            "Selected Pairlink host Bluetooth source is not active"
        )
    if re.fullmatch(r"hci[0-9]+", selected.adapter) is None:
        raise PairlinkTransportCapabilityError(
            "Selected Home Assistant source does not identify a supported BlueZ adapter"
        )
    if _normalize_adapter_address(source) is None:
        raise PairlinkTransportCapabilityError(
            "Selected Home Assistant source does not identify a BlueZ adapter address"
        )
    return selected


def _resolve_bluez_adapter(
    source: str,
    selected: PairlinkHostAdapterInventoryEntry,
    managed_objects: Mapping[str, Mapping[str, Mapping[str, object]]],
    advertisement: PairlinkAdvertisementProfile | None,
) -> str:
    normalized_source = _normalize_adapter_address(source)
    if normalized_source is None:
        raise PairlinkTransportCapabilityError(
            "Selected Pairlink source does not map to a BlueZ adapter address"
        )

    if re.fullmatch(r"hci[0-9]+", selected.adapter) is None:
        raise PairlinkTransportCapabilityError(
            "Selected Home Assistant source does not identify a supported BlueZ adapter"
        )
    expected_path = f"/org/bluez/{selected.adapter}"
    interfaces = managed_objects.get(expected_path)
    if interfaces is None or _ADAPTER_INTERFACE not in interfaces:
        raise PairlinkTransportCapabilityError(
            "Selected Home Assistant source does not map to its current BlueZ adapter path"
        )
    adapter_properties = interfaces[_ADAPTER_INTERFACE]
    address = adapter_properties.get("Address")
    address_matches: list[str] = []
    for object_path, candidate_interfaces in managed_objects.items():
        candidate_adapter = candidate_interfaces.get(_ADAPTER_INTERFACE)
        candidate_address = (
            candidate_adapter.get("Address") if candidate_adapter is not None else None
        )
        if isinstance(candidate_address, str) and candidate_address.upper() == normalized_source:
            address_matches.append(object_path)
    if (
        not isinstance(address, str)
        or address.upper() != normalized_source
        or address_matches != [expected_path]
    ):
        raise PairlinkTransportCapabilityError(
            "Selected local source does not map uniquely to the current BlueZ adapter address"
        )

    powered = adapter_properties.get("Powered")
    if type(powered) is not bool or not powered:
        raise PairlinkTransportCapabilityError(
            "Selected BlueZ adapter is not powered and available"
        )
    if _GATT_MANAGER_INTERFACE not in interfaces:
        raise PairlinkTransportCapabilityError(
            "Selected BlueZ adapter does not expose GattManager1"
        )

    if advertisement is not None:
        manager = interfaces.get(_ADVERTISING_MANAGER_INTERFACE)
        if manager is None:
            raise PairlinkTransportCapabilityError(
                "Selected BlueZ adapter does not expose LEAdvertisingManager1"
            )
        supported_instances = _manager_count(manager, "SupportedInstances")
        active_instances = _manager_count(manager, "ActiveInstances")
        if supported_instances < 1 or active_instances >= supported_instances:
            raise PairlinkTransportCapabilityError(
                "Selected BlueZ adapter has no available LE advertisement instance"
            )
        if advertisement.includes:
            supported_includes = manager.get("SupportedIncludes")
            if not isinstance(supported_includes, (tuple, list)) or not all(
                isinstance(value, str) for value in supported_includes
            ):
                raise PairlinkTransportCapabilityError(
                    "BlueZ did not report supported advertisement includes"
                )
            if not set(advertisement.includes) <= set(supported_includes):
                raise PairlinkTransportCapabilityError(
                    "Selected BlueZ adapter does not support the required advertisement includes"
                )

    if selected.source != source:
        raise PairlinkTransportCapabilityError(
            "Selected Pairlink source changed during BlueZ adapter resolution"
        )
    return expected_path


def _manager_count(properties: Mapping[str, object], name: str) -> int:
    value = properties.get(name)
    if type(value) is not int or value < 0:
        raise PairlinkTransportCapabilityError(
            "BlueZ advertisement manager did not report valid instance capacity"
        )
    return value


def _can_set_advertisement_tx_power(
    adapter_path: str,
    managed_objects: Mapping[str, Mapping[str, Mapping[str, object]]],
    advertisement: PairlinkAdvertisementProfile | None,
) -> bool:
    """Use +1 dBm only when BlueZ reports a compatible optional range."""
    if advertisement is None or advertisement.tx_power_dbm is None:
        return False
    interfaces = managed_objects.get(adapter_path)
    manager = interfaces.get(_ADVERTISING_MANAGER_INTERFACE) if interfaces is not None else None
    if manager is None:
        return False

    raw_capability = manager.get("CanSetTxPower")
    capability = getattr(raw_capability, "value", raw_capability)
    if type(capability) is not bool or not capability:
        return False

    raw_minimum = manager.get("MinTxPower")
    raw_maximum = manager.get("MaxTxPower")
    minimum = getattr(raw_minimum, "value", raw_minimum)
    maximum = getattr(raw_maximum, "value", raw_maximum)
    if (
        type(minimum) is not int
        or type(maximum) is not int
        or not -0x8000 <= minimum <= 0x7FFF
        or not -0x8000 <= maximum <= 0x7FFF
    ):
        return False
    return minimum <= advertisement.tx_power_dbm <= maximum


def _normalize_adapter_address(value: str) -> str | None:
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", value) is None:
        return None
    return value.upper()


def _normalize_peer_address(value: str) -> str | None:
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", value) is None:
        return None
    return value.upper()


def _role_gate_is_active(gate: PairlinkPeripheralRoleGate | None) -> bool:
    if gate is None:
        return False
    try:
        return gate() is True
    except Exception:
        return False


def _validate_uuid(value: str, description: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{description} must be a string")
    if re.fullmatch(r"[0-9A-Fa-f]{4}|[0-9A-Fa-f]{8}", value):
        return
    try:
        UUID(value)
    except AttributeError, TypeError, ValueError:
        raise ValueError(f"Invalid {description}") from None


def _validate_uuid_list(values: tuple[str, ...], description: str) -> None:
    for value in values:
        _validate_uuid(value, description)
    if len({value.casefold() for value in values}) != len(values):
        raise ValueError(f"Duplicate {description}s are not allowed")


def _build_dbus_objects(
    profile: PairlinkPeripheralProfile,
    on_peer_write: PairlinkPeerWriteCallback,
    resolve_peer_identity: PeerIdentityResolver,
    is_gatt_owned: Callable[[], bool],
    on_advertisement_released: Callable[[], None],
    is_peripheral_role_active: PairlinkPeripheralRoleGate | None,
    *,
    can_set_tx_power: bool,
) -> _ExportedObjects:
    """Build the dbus-fast service interfaces lazily on Linux only."""
    try:
        from dbus_fast import DBusError, Variant
        from dbus_fast.constants import PropertyAccess
        from dbus_fast.service import ServiceInterface, dbus_method, dbus_property
    except ImportError:
        raise PairlinkTransportCapabilityError(
            "Pairlink peripheral mode requires Home Assistant's dbus-fast runtime"
        ) from None

    def dbus_method_with_signatures(
        input_signatures: Mapping[str, str], output_signature: str | None
    ) -> Callable[[Callable[..., object]], Callable[..., None]]:
        def decorate(function: Callable[..., object]) -> Callable[..., None]:
            annotations = dict(function.__annotations__)
            for argument_name, signature in input_signatures.items():
                annotations[argument_name] = signature
            if output_signature is None:
                annotations.pop("return", None)
            else:
                annotations["return"] = output_signature
            function.__annotations__ = annotations
            return dbus_method()(function)

        return decorate

    def dbus_property_with_signature(
        *, name: str, signature: str, disabled: bool = False
    ) -> Callable[[Callable[..., object]], property]:
        def decorate(function: Callable[..., object]) -> property:
            annotations = dict(function.__annotations__)
            annotations["return"] = signature
            function.__annotations__ = annotations
            return dbus_property(
                access=PropertyAccess.READ,
                name=name,
                disabled=disabled,
            )(function)

        return decorate

    write_path = _WRITE_CHARACTERISTIC_PATH
    notify_path = _NOTIFY_CHARACTERISTIC_PATH
    service_path = _SERVICE_PATH
    advertisement = profile.advertisement
    notification_state = _NotificationState(is_gatt_owned)

    async def resolve_request_peer(options: Mapping[str, object]) -> PairlinkPeerIdentity:
        device_option = options.get("device")
        if (
            not isinstance(device_option, _VariantLike)
            or device_option.signature != "o"
            or not isinstance(device_option.value, str)
        ):
            raise DBusError(
                "org.bluez.Error.NotAuthorized",
                "Pairlink peer identity could not be verified",
            )
        try:
            return await resolve_peer_identity(device_option.value)
        except asyncio.CancelledError:
            raise
        except PairlinkTransportError:
            raise DBusError(
                "org.bluez.Error.NotAuthorized",
                "Pairlink peer identity could not be verified",
            ) from None

    class ObjectManager(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(_OBJECT_MANAGER_INTERFACE)

        @dbus_method_with_signatures({}, "a{oa{sa{sv}}}")
        def GetManagedObjects(self) -> dict[str, dict[str, dict[str, object]]]:
            managed: dict[str, dict[str, dict[str, object]]] = {
                service_path: {
                    _GATT_SERVICE_INTERFACE: {
                        "UUID": Variant("s", profile.service_uuid),
                        "Primary": Variant("b", True),
                    }
                },
                write_path: {
                    _GATT_CHARACTERISTIC_INTERFACE: {
                        "UUID": Variant("s", profile.write_characteristic_uuid),
                        "Service": Variant("o", service_path),
                        "Flags": Variant("as", [flag.value for flag in profile.write_flags]),
                        "Value": Variant("ay", profile.write_read_value or b""),
                    }
                },
                notify_path: {
                    _GATT_CHARACTERISTIC_INTERFACE: {
                        "UUID": Variant("s", profile.notify_characteristic_uuid),
                        "Service": Variant("o", service_path),
                        "Flags": Variant("as", [flag.value for flag in profile.notify_flags]),
                        "Value": Variant("ay", profile.notify_read_value or b""),
                        "Notifying": Variant("b", notification_state.notifying),
                        "NotifyAcquired": Variant("b", True),
                    }
                },
            }
            return managed

    class GattService(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(_GATT_SERVICE_INTERFACE)

        @dbus_property_with_signature(name="UUID", signature="s")
        def UUID(self) -> str:
            return profile.service_uuid

        @dbus_property_with_signature(name="Primary", signature="b")
        def Primary(self) -> bool:
            return True

        @dbus_property_with_signature(name="Includes", signature="ao")
        def Includes(self) -> list[str]:
            return []

    class WriteCharacteristic(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(_GATT_CHARACTERISTIC_INTERFACE)

        @dbus_property_with_signature(name="UUID", signature="s")
        def UUID(self) -> str:
            return profile.write_characteristic_uuid

        @dbus_property_with_signature(name="Service", signature="o")
        def Service(self) -> str:
            return service_path

        @dbus_property_with_signature(name="Flags", signature="as")
        def Flags(self) -> list[str]:
            return [flag.value for flag in profile.write_flags]

        @dbus_property_with_signature(name="Value", signature="ay")
        def Value(self) -> bytes:
            return profile.write_read_value or b""

        @dbus_method_with_signatures({"options": "a{sv}"}, "ay")
        def ReadValue(self, options: Mapping[str, object]) -> bytes:
            return _read_characteristic_value(
                profile.write_read_value, options, is_gatt_owned, DBusError
            )

        # BlueZ GattCharacteristic1.WriteValue is WriteValue(ay, a{sv}) -> ().
        @dbus_method_with_signatures({"value": "ay", "options": "a{sv}"}, None)
        async def WriteValue(self, value: bytes, options: Mapping[str, object]) -> None:
            _validate_write_options(options, DBusError)
            if not is_gatt_owned():
                raise DBusError("org.bluez.Error.NotPermitted", "Pairlink server is not ready")
            if not isinstance(value, bytes):
                raise DBusError(
                    "org.bluez.Error.InvalidArguments", "Pairlink GATT value is invalid"
                )
            if len(value) > _MAX_ATTRIBUTE_VALUE_LENGTH:
                raise DBusError(
                    "org.bluez.Error.InvalidValueLength",
                    "Pairlink GATT value exceeds the GATT attribute limit",
                )
            identity = await resolve_request_peer(options)
            try:
                callback_result = on_peer_write(identity, memoryview(value).tobytes())
                if inspect.isawaitable(callback_result):
                    await callback_result
            except Exception:
                raise DBusError("org.bluez.Error.Failed", "Pairlink write handler failed") from None

    class NotifyCharacteristic(ServiceInterface):
        def __init__(self) -> None:
            super().__init__(_GATT_CHARACTERISTIC_INTERFACE)

        @dbus_property_with_signature(name="UUID", signature="s")
        def UUID(self) -> str:
            return profile.notify_characteristic_uuid

        @dbus_property_with_signature(name="Service", signature="o")
        def Service(self) -> str:
            return service_path

        @dbus_property_with_signature(name="Flags", signature="as")
        def Flags(self) -> list[str]:
            return [flag.value for flag in profile.notify_flags]

        @dbus_property_with_signature(name="Value", signature="ay")
        def Value(self) -> bytes:
            return profile.notify_read_value or b""

        @dbus_property_with_signature(name="Notifying", signature="b")
        def Notifying(self) -> bool:
            return notification_state.notifying

        @dbus_property_with_signature(name="NotifyAcquired", signature="b")
        def NotifyAcquired(self) -> bool:
            return True

        @dbus_method_with_signatures({"options": "a{sv}"}, "ay")
        def ReadValue(self, options: Mapping[str, object]) -> bytes:
            return _read_characteristic_value(
                profile.notify_read_value, options, is_gatt_owned, DBusError
            )

        @dbus_method_with_signatures({"options": "a{sv}"}, "hq")
        def AcquireNotify(self, options: Mapping[str, object]) -> tuple[int, int]:
            _validate_read_options(options, DBusError)
            raise DBusError(
                "org.bluez.Error.NotSupported",
                "Pairlink per-peer notification producer is unavailable",
            )

        @dbus_method_with_signatures({}, None)
        def StartNotify(self) -> None:
            raise DBusError(
                "org.bluez.Error.NotSupported",
                "Pairlink notifications require a verified peer session",
            )

        @dbus_method_with_signatures({}, None)
        def StopNotify(self) -> None:
            raise DBusError(
                "org.bluez.Error.NotSupported",
                "Pairlink notifications require a verified peer session",
            )

    interfaces: list[tuple[str, str, object]] = [
        (_APPLICATION_PATH, _OBJECT_MANAGER_INTERFACE, ObjectManager()),
        (_SERVICE_PATH, _GATT_SERVICE_INTERFACE, GattService()),
        (
            _WRITE_CHARACTERISTIC_PATH,
            _GATT_CHARACTERISTIC_INTERFACE,
            WriteCharacteristic(),
        ),
    ]
    notify_characteristic = NotifyCharacteristic()
    if not isinstance(notify_characteristic, _ExportedNotifier):
        raise PairlinkTransportError("Pairlink notifier does not expose properties")
    notification_state.bind(notify_characteristic)
    interfaces.append(
        (
            _NOTIFY_CHARACTERISTIC_PATH,
            _GATT_CHARACTERISTIC_INTERFACE,
            notify_characteristic,
        )
    )

    class Advertisement(ServiceInterface):
        def __init__(self, advertisement_profile: PairlinkAdvertisementProfile) -> None:
            super().__init__(_ADVERTISEMENT_INTERFACE)
            self._advertisement_profile = advertisement_profile

        @dbus_property_with_signature(name="Type", signature="s")
        def Type(self) -> str:
            return self._advertisement_profile.advertisement_type

        @dbus_property_with_signature(name="ServiceUUIDs", signature="as")
        def ServiceUUIDs(self) -> list[str]:
            return list(self._advertisement_profile.service_uuids)

        @dbus_property_with_signature(
            name="LocalName",
            signature="s",
            disabled=advertisement is None or advertisement.local_name is None,
        )
        def LocalName(self) -> str:
            return self._advertisement_profile.local_name or ""

        @dbus_property_with_signature(name="Includes", signature="as")
        def Includes(self) -> list[str]:
            return list(self._advertisement_profile.includes)

        @dbus_property_with_signature(
            name="Timeout",
            signature="q",
            disabled=advertisement is None or advertisement.timeout_seconds is None,
        )
        def Timeout(self) -> int:
            return self._advertisement_profile.timeout_seconds or 0

        @dbus_property_with_signature(
            name="MinInterval",
            signature="q",
            disabled=(
                advertisement is None or advertisement.minimum_interval_ms is None
            ),
        )
        def MinInterval(self) -> int:
            return self._advertisement_profile.minimum_interval_ms or 0

        @dbus_property_with_signature(
            name="MaxInterval",
            signature="q",
            disabled=(
                advertisement is None or advertisement.maximum_interval_ms is None
            ),
        )
        def MaxInterval(self) -> int:
            return self._advertisement_profile.maximum_interval_ms or 0

        @dbus_property_with_signature(
            name="TxPower",
            signature="n",
            disabled=(
                advertisement is None
                or advertisement.tx_power_dbm is None
                or not can_set_tx_power
            ),
        )
        def TxPower(self) -> int:
            return self._advertisement_profile.tx_power_dbm or 0

        @dbus_property_with_signature(name="ManufacturerData", signature="a{qv}")
        def ManufacturerData(self) -> dict[int, object]:
            return {
                company_id: Variant("ay", value)
                for company_id, value in self._advertisement_profile.manufacturer_data
            }

        @dbus_method_with_signatures({}, None)
        def Release(self) -> None:
            on_advertisement_released()

    advertisement_object: object | None = None
    if advertisement is not None:
        advertisement_object = Advertisement(advertisement)

    return _ExportedObjects(
        gatt_objects=tuple(interfaces),
        advertisement_object=advertisement_object,
        notification_state=notification_state,
    )


def _validate_write_options(
    options: Mapping[str, object],
    dbus_error_type: Callable[[str, str], Exception],
) -> None:
    if not isinstance(options, Mapping):
        raise dbus_error_type(
            "org.bluez.Error.InvalidArguments", "Pairlink write options are invalid"
        )

    signatures = {
        "offset": "q",
        "type": "s",
        "device": "o",
        "mtu": "q",
        "link": "s",
        "prepare-authorize": "b",
    }
    for name, raw_value in options.items():
        if not isinstance(name, str) or not isinstance(raw_value, _VariantLike):
            raise dbus_error_type(
                "org.bluez.Error.InvalidArguments", "Pairlink write options are invalid"
            )
        expected_signature = signatures.get(name)
        if expected_signature is None:
            continue
        if raw_value.signature != expected_signature:
            raise dbus_error_type(
                "org.bluez.Error.InvalidArguments", "Pairlink write options are invalid"
            )

        value = raw_value.value
        if name in ("offset", "mtu"):
            if type(value) is not int or not 0 <= value <= 0xFFFF:
                raise dbus_error_type(
                    "org.bluez.Error.InvalidArguments",
                    "Pairlink write options are invalid",
                )
            if name == "mtu" and value == 0:
                raise dbus_error_type(
                    "org.bluez.Error.InvalidArguments",
                    "Pairlink write options are invalid",
                )
        elif name == "type":
            if value not in ("command", "request", "reliable"):
                raise dbus_error_type(
                    "org.bluez.Error.InvalidArguments",
                    "Pairlink write options are invalid",
                )
        elif (
            name == "device"
            and (not isinstance(value, str) or _DBUS_OBJECT_PATH_PATTERN.fullmatch(value) is None)
        ) or (name == "link" and value not in ("LE", "BR/EDR")):
            raise dbus_error_type(
                "org.bluez.Error.InvalidArguments", "Pairlink write options are invalid"
            )
        elif name == "prepare-authorize":
            if type(value) is not bool:
                raise dbus_error_type(
                    "org.bluez.Error.InvalidArguments",
                    "Pairlink write options are invalid",
                )


def _read_characteristic_value(
    value: bytes | None,
    options: Mapping[str, object],
    is_gatt_owned: Callable[[], bool],
    dbus_error_type: Callable[[str, str], Exception],
) -> bytes:
    _validate_read_options(options, dbus_error_type)
    if not is_gatt_owned():
        raise dbus_error_type("org.bluez.Error.NotPermitted", "Pairlink server is not ready")
    if value is None:
        raise dbus_error_type(
            "org.bluez.Error.NotPermitted", "Pairlink characteristic is not readable"
        )
    offset_option = options.get("offset")
    raw_offset = offset_option.value if isinstance(offset_option, _VariantLike) else 0
    if type(raw_offset) is not int:
        raise dbus_error_type(
            "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
        )
    offset = raw_offset
    if offset > len(value):
        raise dbus_error_type(
            "org.bluez.Error.InvalidOffset", "Pairlink read offset exceeds the value length"
        )
    return value[offset:]


def _validate_read_options(
    options: Mapping[str, object],
    dbus_error_type: Callable[[str, str], Exception],
) -> None:
    if not isinstance(options, Mapping):
        raise dbus_error_type(
            "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
        )
    signatures = {"offset": "q", "device": "o", "mtu": "q", "link": "s"}
    for name, raw_value in options.items():
        if not isinstance(name, str) or not isinstance(raw_value, _VariantLike):
            raise dbus_error_type(
                "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
            )
        expected_signature = signatures.get(name)
        if expected_signature is None:
            continue
        if raw_value.signature != expected_signature:
            raise dbus_error_type(
                "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
            )
        value = raw_value.value
        if name in ("offset", "mtu"):
            if type(value) is not int or not 0 <= value <= 0xFFFF:
                raise dbus_error_type(
                    "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
                )
            if name == "mtu" and value == 0:
                raise dbus_error_type(
                    "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
                )
        elif (
            name == "device"
            and (not isinstance(value, str) or _DBUS_OBJECT_PATH_PATTERN.fullmatch(value) is None)
            or name == "link"
            and value not in ("LE", "BR/EDR")
        ):
            raise dbus_error_type(
                "org.bluez.Error.InvalidArguments", "Pairlink read options are invalid"
            )


def _new_dbus_fast_bus() -> PairlinkBlueZBus:
    return _DbusFastBlueZBus()


class _DbusFastBlueZBus:
    """Lazy dbus-fast adapter that issues only the required BlueZ calls."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._owner_handler: Callable[[Message], Message | bool | None] | None = None
        self._owner_match_attempted = False
        self._peer_disconnect_handler: Callable[[Message], Message | bool | None] | None = None
        self._peer_match_rules: list[str] = []
        self._peer_write_producer_handler: Callable[[Message], Message | bool | None] | None = None
        self._peer_notify_acquire_handler: Callable[[Message], Message | bool | None] | None = None
        self._peer_notify_acquire_callback: PairlinkPeerNotifyAcquireCallback | None = None
        self._peer_notify_acquire_tasks: set[asyncio.Task[None]] = set()
        self._bluez_owner: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._bus is not None and self._bus.connected

    async def async_connect(self) -> None:
        try:
            from dbus_fast import BusType
            from dbus_fast.aio import MessageBus
        except ImportError:
            raise PairlinkTransportCapabilityError(
                "Pairlink peripheral mode requires Home Assistant's dbus-fast runtime"
            ) from None
        bus = MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=True)
        self._bus = bus
        try:
            await bus.connect()
        except asyncio.CancelledError:
            bus.disconnect()
            self._bus = None
            raise
        except Exception:
            bus.disconnect()
            self._bus = None
            raise PairlinkTransportCapabilityError(
                "Could not connect to the system D-Bus for BlueZ; check host permissions"
            ) from None

    async def async_get_managed_objects(
        self,
    ) -> Mapping[str, Mapping[str, Mapping[str, object]]]:
        from dbus_fast import Variant
        from dbus_fast.message import Message

        response = await self._call(
            Message(
                destination=_BLUEZ_SERVICE,
                path="/",
                interface=_OBJECT_MANAGER_INTERFACE,
                member="GetManagedObjects",
            )
        )
        if not isinstance(response, list) or len(response) != 1:
            raise PairlinkTransportCapabilityError("BlueZ returned an invalid adapter inventory")
        raw_objects = response[0]
        if not isinstance(raw_objects, Mapping):
            raise PairlinkTransportCapabilityError("BlueZ returned an invalid adapter inventory")

        result: dict[str, dict[str, dict[str, object]]] = {}
        for raw_path, raw_interfaces in raw_objects.items():
            if not isinstance(raw_path, str) or not isinstance(raw_interfaces, Mapping):
                raise PairlinkTransportCapabilityError("BlueZ returned malformed adapter data")
            interfaces: dict[str, dict[str, object]] = {}
            for raw_name, raw_properties in raw_interfaces.items():
                if not isinstance(raw_name, str):
                    raise PairlinkTransportCapabilityError("BlueZ returned malformed adapter data")
                required_properties = _BLUEZ_PREFLIGHT_PROPERTIES.get(raw_name)
                if required_properties is None:
                    continue
                if not isinstance(raw_properties, Mapping):
                    raise PairlinkTransportCapabilityError("BlueZ returned malformed adapter data")
                properties: dict[str, object] = {}
                for raw_key, raw_value in raw_properties.items():
                    if not isinstance(raw_key, str):
                        raise PairlinkTransportCapabilityError(
                            "BlueZ returned malformed adapter properties"
                        )
                    if raw_key not in required_properties:
                        continue
                    if isinstance(raw_value, Variant):
                        if raw_name == _ADVERTISING_MANAGER_INTERFACE:
                            signature = {
                                "CanSetTxPower": "b",
                                "MinTxPower": "n",
                                "MaxTxPower": "n",
                            }.get(raw_key)
                            if signature is not None and raw_value.signature != signature:
                                continue
                        properties[raw_key] = raw_value.value
                    else:
                        properties[raw_key] = raw_value
                interfaces[raw_name] = properties
            result[raw_path] = interfaces
        return result

    async def async_watch_bluez_owner(self, callback: Callable[[], None]) -> None:
        from dbus_fast.constants import MessageType
        from dbus_fast.message import Message

        bus = self._require_bus()

        def on_message(message: Message) -> Message | bool | None:
            if (
                message.message_type is not MessageType.SIGNAL
                or message.interface != _DBUS_INTERFACE
                or message.member != "NameOwnerChanged"
            ):
                return None
            body: object = message.body
            if not isinstance(body, list) or len(body) != 3:
                return None
            name, old_owner, new_owner = body
            if name == _BLUEZ_SERVICE:
                previous_owner = self._bluez_owner
                self._bluez_owner = new_owner if isinstance(new_owner, str) and new_owner else None
                if previous_owner is not None and previous_owner != self._bluez_owner:
                    callback()
            return None

        self._owner_handler = on_message
        bus.add_message_handler(on_message)
        self._owner_match_attempted = True
        try:
            await self._call(
                Message(
                    destination="org.freedesktop.DBus",
                    path=_DBUS_PATH,
                    interface=_DBUS_INTERFACE,
                    member="AddMatch",
                    signature="s",
                    body=[_BLUEZ_OWNER_MATCH],
                )
            )
        except Exception:
            bus.remove_message_handler(on_message)
            self._owner_handler = None
            raise

    async def async_unwatch_bluez_owner(self) -> None:
        from dbus_fast.message import Message

        bus = self._bus
        handler = self._owner_handler
        self._owner_handler = None
        if bus is not None and handler is not None:
            bus.remove_message_handler(handler)
        if self._owner_match_attempted and self.is_connected:
            self._owner_match_attempted = False
            await self._call(
                Message(
                    destination="org.freedesktop.DBus",
                    path=_DBUS_PATH,
                    interface=_DBUS_INTERFACE,
                    member="RemoveMatch",
                    signature="s",
                    body=[_BLUEZ_OWNER_MATCH],
                )
            )

    async def async_watch_peer_disconnect(
        self, adapter_path: str, callback: Callable[[str, bool], None]
    ) -> None:
        from dbus_fast.constants import MessageType
        from dbus_fast.message import Message

        bus = self._require_bus()
        if _DBUS_OBJECT_PATH_PATTERN.fullmatch(adapter_path) is None or not callable(callback):
            raise PairlinkTransportCapabilityError("Pairlink peer watch is invalid")
        properties_match = (
            "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',"
            f"member='PropertiesChanged',path_namespace='{adapter_path}'"
        )

        def on_message(message: Message) -> Message | bool | None:
            path = message.path
            if message.message_type is not MessageType.SIGNAL or not isinstance(path, str):
                return None
            if (
                message.interface == _BLUEZ_PROPERTIES_INTERFACE
                and message.member == "PropertiesChanged"
            ):
                if not path.startswith(f"{adapter_path}/dev_"):
                    return None
                body = message.body
                if not isinstance(body, list) or len(body) != 3 or body[0] != _DEVICE_INTERFACE:
                    return None
                changed, invalidated = body[1], body[2]
                connected_value = changed.get("Connected") if isinstance(changed, Mapping) else None
                current = getattr(connected_value, "value", connected_value)
                if type(current) is bool:
                    callback(path, current)
                elif isinstance(invalidated, (list, tuple)) and "Connected" in invalidated:
                    callback(path, False)
                return None
            if (
                message.interface == _OBJECT_MANAGER_INTERFACE
                and message.member == "InterfacesRemoved"
                and path == "/"
            ):
                body = message.body
                if (
                    isinstance(body, list)
                    and len(body) == 2
                    and isinstance(body[0], str)
                    and body[0].startswith(f"{adapter_path}/dev_")
                    and isinstance(body[1], (list, tuple))
                    and _DEVICE_INTERFACE in body[1]
                ):
                    callback(body[0], False)
            return None

        self._peer_disconnect_handler = on_message
        bus.add_message_handler(on_message)
        for rule in (properties_match, _BLUEZ_PEER_REMOVED_MATCH):
            try:
                await self._call(
                    Message(
                        destination="org.freedesktop.DBus",
                        path=_DBUS_PATH,
                        interface=_DBUS_INTERFACE,
                        member="AddMatch",
                        signature="s",
                        body=[rule],
                    )
                )
            except Exception:
                bus.remove_message_handler(on_message)
                self._peer_disconnect_handler = None
                raise
            self._peer_match_rules.append(rule)

    async def async_unwatch_peer_disconnect(self) -> None:
        from dbus_fast.message import Message

        bus = self._bus
        handler = self._peer_disconnect_handler
        self._peer_disconnect_handler = None
        if bus is not None and handler is not None:
            bus.remove_message_handler(handler)
        if not self.is_connected:
            self._peer_match_rules.clear()
            return

        failures = 0
        for rule in reversed(self._peer_match_rules):
            try:
                await self._call(
                    Message(
                        destination="org.freedesktop.DBus",
                        path=_DBUS_PATH,
                        interface=_DBUS_INTERFACE,
                        member="RemoveMatch",
                        signature="s",
                        body=[rule],
                    )
                )
            except Exception:
                failures += 1
        self._peer_match_rules.clear()
        if failures:
            raise PairlinkTransportError("Pairlink peer disconnect watch removal failed")

    async def async_watch_peer_write_producer(self, characteristic_path: str) -> None:
        from dbus_fast.constants import MessageType
        from dbus_fast.message import Message

        bus = self._require_bus()
        if (
            characteristic_path != _PEER_WRITE_CALL_PATH
            or _DBUS_OBJECT_PATH_PATTERN.fullmatch(characteristic_path) is None
        ):
            raise PairlinkTransportCapabilityError("Pairlink write producer path is invalid")

        def on_message(message: Message) -> Message | bool | None:
            if (
                message.message_type is not MessageType.METHOD_CALL
                or message.path != characteristic_path
                or message.interface != _GATT_CHARACTERISTIC_INTERFACE
                or message.member != "WriteValue"
            ):
                return None
            if self._bluez_owner is not None and message.sender == self._bluez_owner:
                return None
            return Message.new_error(
                message,
                "org.bluez.Error.NotAuthorized",
                "Pairlink peer identity could not be verified",
            )

        self._peer_write_producer_handler = on_message
        bus.add_message_handler(on_message)

    async def async_watch_peer_notify_acquire(
        self,
        characteristic_path: str,
        callback: PairlinkPeerNotifyAcquireCallback,
    ) -> None:
        from dbus_fast.constants import MessageType
        from dbus_fast.message import Message

        bus = self._require_bus()
        if (
            characteristic_path != _NOTIFY_CHARACTERISTIC_PATH
            or _DBUS_OBJECT_PATH_PATTERN.fullmatch(characteristic_path) is None
            or not callable(callback)
        ):
            raise PairlinkTransportCapabilityError("Pairlink notify producer path is invalid")
        self._peer_notify_acquire_callback = callback

        def on_message(message: Message) -> Message | bool | None:
            if (
                message.message_type is not MessageType.METHOD_CALL
                or message.path != characteristic_path
                or message.interface != _GATT_CHARACTERISTIC_INTERFACE
                or message.member != "AcquireNotify"
            ):
                return None
            if self._bluez_owner is None or message.sender != self._bluez_owner:
                return Message.new_error(
                    message,
                    "org.bluez.Error.NotAuthorized",
                    "Pairlink notify producer could not be verified",
                )
            if (
                message.signature != "a{sv}"
                or not isinstance(message.body, list)
                or len(message.body) != 1
                or not isinstance(message.body[0], Mapping)
            ):
                return Message.new_error(
                    message,
                    "org.bluez.Error.InvalidArguments",
                    "Pairlink notify request is invalid",
                )
            task = asyncio.create_task(self._reply_peer_notify_acquire(message, message.body[0]))
            self._peer_notify_acquire_tasks.add(task)
            task.add_done_callback(self._peer_notify_acquire_tasks.discard)
            return True

        self._peer_notify_acquire_handler = on_message
        bus.add_message_handler(on_message)

    async def _reply_peer_notify_acquire(
        self, message: Message, options: Mapping[str, object]
    ) -> None:
        from dbus_fast.message import Message

        bus = self._bus
        callback = self._peer_notify_acquire_callback
        if bus is None or callback is None or not bus.connected:
            return
        try:
            fd_socket, mtu = await callback(options)
        except asyncio.CancelledError:
            raise
        except PairlinkTransportStateError:
            await bus.send(
                Message.new_error(
                    message,
                    "org.bluez.Error.NotPermitted",
                    "Pairlink peer notification is not ready",
                )
            )
            return
        except PairlinkTransportError:
            await bus.send(
                Message.new_error(
                    message,
                    "org.bluez.Error.NotAuthorized",
                    "Pairlink peer notification could not be verified",
                )
            )
            return
        except Exception:
            await bus.send(
                Message.new_error(
                    message,
                    "org.bluez.Error.Failed",
                    "Pairlink peer notification setup failed",
                )
            )
            return

        try:
            await bus.send(
                Message.new_method_return(
                    message,
                    signature="hq",
                    body=[0, mtu],
                    unix_fds=[fd_socket.fileno()],
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Closing the offered endpoint below gives the local socket HUP;
            # the backend then drops the matching session generation.
            return
        finally:
            fd_socket.close()

    async def async_unwatch_peer_notify_acquire(self) -> None:
        bus = self._bus
        handler = self._peer_notify_acquire_handler
        self._peer_notify_acquire_handler = None
        self._peer_notify_acquire_callback = None
        if bus is not None and handler is not None:
            bus.remove_message_handler(handler)
        tasks = tuple(self._peer_notify_acquire_tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._peer_notify_acquire_tasks.clear()

    async def async_unwatch_peer_write_producer(self) -> None:
        bus = self._bus
        handler = self._peer_write_producer_handler
        self._peer_write_producer_handler = None
        if bus is not None and handler is not None:
            bus.remove_message_handler(handler)

    async def async_register_application(self, adapter_path: str, application_path: str) -> None:
        from dbus_fast.message import Message

        await self._call(
            Message(
                destination=_BLUEZ_SERVICE,
                path=adapter_path,
                interface=_GATT_MANAGER_INTERFACE,
                member="RegisterApplication",
                signature="oa{sv}",
                body=[application_path, {}],
            )
        )

    async def async_unregister_application(self, adapter_path: str, application_path: str) -> None:
        from dbus_fast.message import Message

        await self._call(
            Message(
                destination=_BLUEZ_SERVICE,
                path=adapter_path,
                interface=_GATT_MANAGER_INTERFACE,
                member="UnregisterApplication",
                signature="o",
                body=[application_path],
            )
        )

    async def async_register_advertisement(
        self, adapter_path: str, advertisement_path: str
    ) -> None:
        from dbus_fast.message import Message

        await self._call(
            Message(
                destination=_BLUEZ_SERVICE,
                path=adapter_path,
                interface=_ADVERTISING_MANAGER_INTERFACE,
                member="RegisterAdvertisement",
                signature="oa{sv}",
                body=[advertisement_path, {}],
            )
        )

    async def async_unregister_advertisement(
        self, adapter_path: str, advertisement_path: str
    ) -> None:
        from dbus_fast.message import Message

        await self._call(
            Message(
                destination=_BLUEZ_SERVICE,
                path=adapter_path,
                interface=_ADVERTISING_MANAGER_INTERFACE,
                member="UnregisterAdvertisement",
                signature="o",
                body=[advertisement_path],
            )
        )

    def export(self, object_path: str, interface: object) -> None:
        from dbus_fast.service import ServiceInterface

        bus = self._require_bus()
        if not isinstance(interface, ServiceInterface):
            raise PairlinkTransportError("Pairlink exported object has an invalid interface")
        bus.export(object_path, interface)

    def unexport(self, object_path: str, interface_name: str) -> None:
        bus = self._require_bus()
        bus.unexport(object_path, interface_name)

    async def async_wait_for_disconnect(self) -> None:
        bus = self._require_bus()
        waiter: _DisconnectWaiter = bus
        await waiter.wait_for_disconnect()

    async def async_disconnect(self) -> None:
        bus = self._bus
        self._bus = None
        if bus is not None and bus.connected:
            bus.disconnect()

    async def _call(self, message: Message) -> object:
        from dbus_fast.constants import MessageType

        response = await self._require_bus().call(message)
        if response is None:
            raise PairlinkTransportError("BlueZ returned no D-Bus response")
        if response.message_type is MessageType.ERROR:
            raise _BlueZCallError(_bluez_error_category(response.error_name))
        if message.destination == _BLUEZ_SERVICE and isinstance(response.sender, str):
            self._bluez_owner = response.sender
        body: object = response.body
        return body

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise PairlinkTransportStateError("System D-Bus connection is not open")
        return self._bus


class _BlueZCallError(RuntimeError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _bluez_error_category(error_name: str | None) -> str:
    categories = {
        "org.freedesktop.DBus.Error.AccessDenied": "permission denied",
        "org.freedesktop.DBus.Error.NameHasNoOwner": "BlueZ service unavailable",
        "org.freedesktop.DBus.Error.ServiceUnknown": "BlueZ service unavailable",
        "org.freedesktop.DBus.Error.UnknownObject": "BlueZ object unavailable",
        "org.freedesktop.DBus.Error.UnknownMethod": "BlueZ method unavailable",
        "org.bluez.Error.DoesNotExist": "not registered",
        "org.bluez.Error.NotPermitted": "permission denied",
        "org.bluez.Error.NotAuthorized": "permission denied",
        "org.bluez.Error.NotSupported": "capability unsupported",
        "org.bluez.Error.AlreadyExists": "already registered",
        "org.bluez.Error.InvalidArguments": "BlueZ rejected the supplied profile",
        "org.bluez.Error.InvalidLength": "BlueZ rejected advertisement length",
    }
    if error_name is None:
        return "BlueZ call failed"
    return categories.get(error_name, "BlueZ call failed")
