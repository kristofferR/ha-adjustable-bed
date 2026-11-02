"""Production-path Pairlink tests with fake Bluetooth and BlueZ transports."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import Protocol, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dbus_fast import DBusError, Variant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import async_setup_entry, async_unload_entry
from custom_components.adjustable_bed.beds import reverie_pairlink_transport as transport
from custom_components.adjustable_bed.beds.reverie_pairlink_profile import (
    build_pairlink_peripheral_profile,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
    PAIRLINK_BROADCAST_ADDRESS,
    PAIRLINK_LOW_POWER_NOTIFY_UUID,
    PAIRLINK_LOW_POWER_WRITE_UUID,
    build_user_frame,
    comfort_payloads,
    dashboard_payload,
    decrypt_login_block,
    derive_event_key_from_seed,
    encrypt_login_block,
    encrypt_user_frame,
    fragment_central_frame,
    status_sync_payloads,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
    PairlinkRuntime,
    PairlinkSendSnapshot,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE_PAIRLINK,
    CONF_PAIRLINK_HOME_ID,
    CONF_PAIRLINK_HOST_SOURCE,
    CONF_PAIRLINK_PASSWORD_HEX,
    CONF_PAIRLINK_PASSWORD_TEXT,
    CONF_PAIRLINK_ROLE,
    DOMAIN,
    PAIRLINK_ROLE_CENTRAL,
    PAIRLINK_ROLE_PERIPHERAL,
)
from custom_components.adjustable_bed.services import (
    SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
    SERVICE_REVERIE_SET_COMFORT,
)
from tests.test_reverie_pairlink_transport import (
    _PEER_ADDRESS,
    _PEER_PATH,
    FakeBlueZBus,
    _device,
    _interface,
    _write_value,
)

_BED_ADDRESS = "00:10:20:30:40:50"
_HOST_SOURCE = "AA:BB:CC:DD:EE:FF"
_HOME_ID = 5566
_PASSWORD = b"1122"
_PRIMARY_SESSION_KEY = bytes.fromhex("10203040")
_BACKUP_SESSION_KEY = bytes.fromhex("A1A2A3A4")


class _ReadValueMethod(Protocol):
    __wrapped__: Callable[[object, Mapping[str, object]], bytes]


class _ReadValueCharacteristic(Protocol):
    ReadValue: _ReadValueMethod


class _GattCharacteristic:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid
        self.properties = ["write", "write-without-response"]
        self.max_write_without_response_size = 20
        self.descriptors: list[object] = []


class _GattService:
    def __init__(self, uuid: str, *characteristics: str) -> None:
        self.uuid = uuid
        self.characteristics = [_GattCharacteristic(value) for value in characteristics]


def _manufacturer_data(home_id: int = _HOME_ID, *, bed_type: int = 144) -> dict[int, bytes]:
    payload = (
        b"\xFF\xFF\xC0\x00\x01"
        + home_id.to_bytes(4, "little")
        + bytes((bed_type, 37, 48))
        + bytes.fromhex("102030405060")
    )
    assert len(payload) == 18
    return {int.from_bytes(payload[:2], "little"): payload[2:]}


def _entry(
    *,
    address: str = _BED_ADDRESS,
    title: str = "Pairlink bed",
    host_source: str = _HOST_SOURCE,
    role: str = PAIRLINK_ROLE_PERIPHERAL,
    model: str = "R510L",
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=address,
        data={
            "address": address,
            "name": title,
            "bed_type": BED_TYPE_REVERIE_PAIRLINK,
            "protocol_variant": model,
            "motor_count": 2,
            "has_massage": True,
            "disable_angle_sensing": False,
        },
        options={
            CONF_PAIRLINK_ROLE: role,
            CONF_PAIRLINK_HOST_SOURCE: host_source,
        },
    )


def _scanners(sources: tuple[tuple[str, str], ...]) -> list[object]:
    return [SimpleNamespace(source=source, adapter=adapter) for source, adapter in sources]


def _adapter_objects(
    adapter: str,
    address: str,
    peers: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> dict[str, dict[str, dict[str, object]]]:
    adapter_path = f"/org/bluez/{adapter}"
    objects: dict[str, dict[str, dict[str, object]]] = {
        adapter_path: {
            "org.bluez.Adapter1": {"Address": address, "Powered": True},
            "org.bluez.GattManager1": {},
            "org.bluez.LEAdvertisingManager1": {
                "SupportedInstances": 2,
                "ActiveInstances": 1,
                "SupportedIncludes": ("local-name",),
                "CanSetTxPower": True,
            },
        }
    }
    objects.update(
        {path: {name: dict(properties) for name, properties in interfaces.items()}
         for path, interfaces in peers.items()}
    )
    return objects


def _peer_path(adapter: str, address: str) -> str:
    return f"/org/bluez/{adapter}/dev_{address.replace(':', '_')}"


def _login_context() -> bytes:
    home = _HOME_ID.to_bytes(4, "little")
    return b"".join(
        bytes((home_byte, password_byte))
        for home_byte, password_byte in zip(home, _PASSWORD, strict=True)
    ) + b"LOGINKEY"


def _login_packet(
    session_key: bytes = _PRIMARY_SESSION_KEY,
    *,
    home_id: int = _HOME_ID,
) -> bytes:
    plain = home_id.to_bytes(4, "little") + session_key + b"ignored!"
    return b"\x01\x19" + encrypt_login_block(plain, login_key=_login_context())


async def _local_setup(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    entry: MockConfigEntry,
    bus: FakeBlueZBus,
    *,
    scanners: list[object] | None = None,
) -> object:
    from homeassistant.components import bluetooth

    from custom_components.adjustable_bed import bluetooth_transport

    monkeypatch.setattr(
        bluetooth,
        "async_current_scanners",
        lambda _hass: scanners or _scanners(((_HOST_SOURCE, "hci3"),)),
    )
    monkeypatch.setattr(
        bluetooth_transport,
        "classify_scanner",
        lambda _scanner: bluetooth_transport.TransportClass.LOCAL,
    )
    model = entry.data["protocol_variant"]
    service_info = SimpleNamespace(
        address=entry.data["address"],
        name=model,
        manufacturer_data=_manufacturer_data(bed_type=145 if model == "Harmoniq Upgrade" else 144),
        service_uuids=(),
        service_data={},
    )
    monkeypatch.setattr(
        bluetooth,
        "async_last_service_info",
        lambda *_args, **_kwargs: service_info,
    )
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", lambda: bus)
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=None),
    ):
        assert await async_setup_entry(hass, entry)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return hass.data[DOMAIN][entry.entry_id]


async def _subscribe_peer(
    bus: FakeBlueZBus,
    peer_path: str,
    *,
    mtu: int = 64,
) -> socket.socket:
    bluez_socket, negotiated_mtu = await bus.acquire_notify(
        {
            "device": Variant("o", peer_path),
            "mtu": Variant("q", mtu),
            "link": Variant("s", "LE"),
        }
    )
    assert negotiated_mtu >= 64
    bluez_socket.setblocking(False)
    return bluez_socket


async def _send_peer_write(
    bus: FakeBlueZBus,
    peer_path: str,
    value: bytes,
) -> None:
    characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)
    await _write_value(characteristic, value, {"device": Variant("o", peer_path)})


async def _send_state_selector(
    bus: FakeBlueZBus,
    peer_path: str,
    runtime: PairlinkRuntime,
    selector: int,
    value: int,
    *,
    device_key: bytes = _PRIMARY_SESSION_KEY,
    encrypted: bool = True,
) -> None:
    """Feed one encrypted, source-shaped state event through registered WriteValue."""
    event = build_user_frame(
        b"\x02\xA7" + bytes((selector, value)),
        destination=PAIRLINK_BROADCAST_ADDRESS,
        channel=32,
        own_virtual_address=bytes(4),
    )
    wire_value = (
        encrypt_user_frame(
            event,
            event_key=runtime.current_event_key,
            device_key=device_key,
        )
        if encrypted
        else event
    )
    await _send_peer_write(bus, peer_path, wire_value)


def _read_characteristic(
    bus: FakeBlueZBus,
    path: str,
) -> bytes:
    characteristic = _interface(bus, path)
    method = cast(_ReadValueCharacteristic, characteristic).ReadValue.__wrapped__
    return method(characteristic, {})


def _recv(socket_: socket.socket) -> bytes:
    return socket_.recv(512)


def _drain_socket(socket_: socket.socket) -> None:
    while True:
        try:
            _recv(socket_)
        except BlockingIOError:
            return


def _device_for_address(hass: HomeAssistant, address: str) -> dr.DeviceEntry | None:
    identifier = (DOMAIN, address)
    registry = dr.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.unique_id != address:
            continue
        if device := next(
            (
                device
                for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
                if identifier in device.identifiers
            ),
            None,
        ):
            return device
    return None


def _expected_status_sync_frames(runtime: PairlinkRuntime) -> tuple[bytes, bytes]:
    snapshot = runtime.prepare_send()
    assert snapshot.device_key is not None
    frames = tuple(
        encrypt_user_frame(
            build_user_frame(
                payload,
                destination=PAIRLINK_BROADCAST_ADDRESS,
                channel=32,
                own_virtual_address=snapshot.own_virtual_address,
            ),
            event_key=snapshot.event_key,
            device_key=snapshot.device_key,
        )
        for payload in status_sync_payloads()
    )
    assert len(frames) == 2
    return frames[0], frames[1]


async def test_pairlink_profile_projects_lumbar_only_for_harmoniq_entities(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    from custom_components.adjustable_bed.cover import _cover_entities_for

    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry(model="Harmoniq Upgrade")
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller

    assert controller.model_id == "Harmoniq Upgrade"
    assert controller.has_lumbar_support is False
    covers = _cover_entities_for(hass, coordinator)
    assert tuple(entity.entity_description.key for entity in covers) == ("back", "legs")
    assert all(
        entity.entity_description.hold is not None
        and "lumbar" not in (
            entity.entity_description.hold.up_control,
            entity.entity_description.hold.down_control,
        )
        for entity in covers
    )
    assert "lumbar_up" not in controller.held_control_options
    await async_unload_entry(hass, entry)


@pytest.mark.parametrize(
    ("role", "requires_local_transport"),
    ((PAIRLINK_ROLE_CENTRAL, False), (PAIRLINK_ROLE_PERIPHERAL, True)),
)
async def test_offline_factory_builds_entry_runtime_without_transport_start(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    requires_local_transport: bool,
) -> None:
    from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    bus_factory_calls = 0

    def unexpected_bus() -> FakeBlueZBus:
        nonlocal bus_factory_calls
        bus_factory_calls += 1
        raise AssertionError("offline Pairlink construction must not open BlueZ")

    monkeypatch.setattr(transport, "_new_dbus_fast_bus", unexpected_bus)
    entry = _entry(role=role)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(
        coordinator,
        BED_TYPE_REVERIE_PAIRLINK,
        "R510L",
        None,
        device_name=None,
        manufacturer_data=None,
    )

    assert isinstance(controller, ReveriePairlinkController)
    runtime = coordinator._pairlink_runtime
    assert runtime is not None
    assert runtime is controller._runtime
    assert runtime.credentials.home_id_origin.value == "declared_ha_policy"
    assert runtime.credentials.home_id_le == _HOME_ID.to_bytes(4, "little")
    assert runtime.peripheral_backend is None
    assert runtime.host_adapter_path is None
    assert controller.requires_disconnected_transport is requires_local_transport
    assert controller.disconnected_transport_ready is False
    assert bus_factory_calls == 0

    live_controller = await create_controller(
        coordinator,
        BED_TYPE_REVERIE_PAIRLINK,
        "R510L",
        None,
        device_name="R510L",
        manufacturer_data=_manufacturer_data(_HOME_ID + 1),
    )
    assert isinstance(live_controller, ReveriePairlinkController)
    assert live_controller._runtime is runtime
    assert runtime.credentials.home_id_le == (_HOME_ID + 1).to_bytes(4, "little")
    assert runtime.credentials.home_id_origin.value == "advertisement"
    assert bus_factory_calls == 0
    await coordinator.async_shutdown()


async def test_pairlink_option_flow_requires_current_local_source_and_exact_credentials(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from homeassistant.components import bluetooth

    from custom_components.adjustable_bed import bluetooth_transport
    from custom_components.adjustable_bed.config_flow import (
        _pairlink_settings_schema,
        _validate_pairlink_option_values,
    )

    local = SimpleNamespace(source=_HOST_SOURCE, adapter="hci3")
    proxy = SimpleNamespace(source="proxy-source", adapter="proxy-1")
    monkeypatch.setattr(bluetooth, "async_current_scanners", lambda _hass: [local, proxy])
    monkeypatch.setattr(
        bluetooth_transport,
        "classify_scanner",
        lambda scanner: (
            bluetooth_transport.TransportClass.LOCAL
            if scanner is local
            else bluetooth_transport.TransportClass.PROXY
        ),
    )
    monkeypatch.setattr(
        bluetooth,
        "async_last_service_info",
        lambda *_args, **_kwargs: SimpleNamespace(manufacturer_data=_manufacturer_data()),
    )

    schema = _pairlink_settings_schema(hass, {})
    assert schema
    valid_values = {
        CONF_PAIRLINK_ROLE: PAIRLINK_ROLE_PERIPHERAL,
        CONF_PAIRLINK_HOST_SOURCE: _HOST_SOURCE,
    }
    assert (
        _validate_pairlink_option_values(
            hass,
            {},
            valid_values,
        )
        == {}
    )
    assert valid_values[CONF_PAIRLINK_HOME_ID] is None
    assert valid_values[CONF_PAIRLINK_PASSWORD_TEXT] == "1122"
    assert valid_values[CONF_PAIRLINK_PASSWORD_HEX] is None

    invalid_values = {
        CONF_PAIRLINK_ROLE: PAIRLINK_ROLE_PERIPHERAL,
        CONF_PAIRLINK_HOST_SOURCE: "proxy-source",
        CONF_PAIRLINK_PASSWORD_HEX: "4142434Z",
    }
    errors = _validate_pairlink_option_values(
        hass,
        {},
        invalid_values,
    )
    assert errors == {
        CONF_PAIRLINK_HOST_SOURCE: "pairlink_local_source_unavailable",
        CONF_PAIRLINK_PASSWORD_HEX: "invalid_pairlink_password",
    }


async def test_entry_setup_registered_service_and_two_peer_clear_route(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime

    assert coordinator.client is None
    assert controller.requires_disconnected_transport is True
    assert runtime.disconnected_transport_ready is False
    assert bus.application_registered is True
    assert bus.advertisement_registered is True
    assert [event[0] for event in bus.events].index("register-application") < [
        event[0] for event in bus.events
    ].index("register-advertisement")
    assert runtime.credentials.home_id_le == _HOME_ID.to_bytes(4, "little")
    assert runtime.credentials.home_id_origin.value == "advertisement"

    profile = build_pairlink_peripheral_profile(
        home_id=_HOME_ID,
        local_join_bt_mac=runtime.local_join_bt_mac,
    )
    assert profile.write_characteristic_uuid == PAIRLINK_LOW_POWER_WRITE_UUID
    assert profile.notify_characteristic_uuid == PAIRLINK_LOW_POWER_NOTIFY_UUID
    assert profile.write_flags == (transport.PairlinkGattFlag.READ, transport.PairlinkGattFlag.WRITE)
    assert profile.notify_flags == (transport.PairlinkGattFlag.READ, transport.PairlinkGattFlag.NOTIFY)
    assert profile.notify_descriptor is None
    assert profile.advertisement is not None
    assert profile.advertisement.minimum_interval_ms == 100
    assert profile.advertisement.maximum_interval_ms == 100
    assert profile.advertisement.tx_power_dbm == 1
    assert "tx-power" not in profile.advertisement.includes

    primary_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    login_reply = _recv(primary_socket)
    expected_login = encrypt_login_block(
        _HOME_ID.to_bytes(4, "little")
        + _PASSWORD
        + _PRIMARY_SESSION_KEY
        + b"\x04" * 4,
        login_key=_login_context(),
    )
    assert login_reply == b"\x02\x19" + expected_login
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(primary_socket) == b"\x01\x20"
    assert runtime.joined is True
    assert runtime.primary_mac == _PEER_ADDRESS
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert controller._active_control_session is True
    assert tuple(_recv(primary_socket) for _ in range(2)) == _expected_status_sync_frames(
        runtime
    )

    for selector, value in ((1, 20), (2, 30), (3, 40), (5, 30), (6, 40), (12, 2), (14, 4)):
        await _send_state_selector(bus, _PEER_PATH, runtime, selector, value)
    assert controller._state == {
        "back_position": 20,
        "legs_position": 30,
        "reverie_pairlink_head2_position": 40,
        "massage_head_intensity": 3,
        "massage_foot_intensity": 5,
        "reverie_massage_mode": 2,
        "reverie_massage_timer": 4,
    }

    device = _device_for_address(hass, _BED_ADDRESS)
    assert device is not None
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REVERIE_SET_COMFORT,
        {"device_id": [device.id], "comfort": {"head_position": 35}},
        blocking=True,
    )
    encrypted_comfort = tuple(
        encrypt_user_frame(
            build_user_frame(
                payload,
                destination=PAIRLINK_BROADCAST_ADDRESS,
                channel=32,
                own_virtual_address=bytes(4),
            ),
            event_key=runtime.current_event_key,
            device_key=_PRIMARY_SESSION_KEY,
        )
        for payload in comfort_payloads(
            values={
                "head_position": 35,
                "foot_position": 30,
                "lumbar_position": 40,
                "head_massage": 3,
                "foot_massage": 5,
                "timer_byte": 4,
                "mode": 2,
            },
            current={
                "head_position": 20,
                "foot_position": 30,
                "lumbar_position": 40,
                "head_massage": 3,
                "foot_massage": 5,
                "timer_byte": 4,
                "mode": 2,
            },
            force=False,
        )
    )
    assert tuple(_recv(primary_socket) for _ in encrypted_comfort) == encrypted_comfort
    assert _read_characteristic(bus, transport._NOTIFY_CHARACTERISTIC_PATH) == b"\x66"

    backup_address = "22:33:44:55:66:77"
    backup_path = _peer_path("hci3", backup_address)
    bus.managed_objects[backup_path] = _device(backup_address)
    backup_socket = await _subscribe_peer(bus, backup_path)
    await _send_peer_write(bus, backup_path, b"\x01\x00" + bytes(4))
    assert _recv(backup_socket) == b"\x02\x00" + bytes(4) + _PASSWORD
    assert backup_address not in runtime._peer_keys
    assert runtime.peer_sessions[backup_address].device_type == 0
    await _send_peer_write(bus, backup_path, b"\x02\x31\x08")
    assert _recv(backup_socket) == b"\x01\x20"
    assert runtime.primary_mac == backup_address
    assert runtime.peer_sessions[backup_address].device_type == 0
    assert runtime._peer_keys[_PEER_ADDRESS] == _PRIMARY_SESSION_KEY

    first_seed = bytes.fromhex("01020304")
    old_event_key = runtime.current_event_key
    await _send_peer_write(
        bus,
        _PEER_PATH,
        b"\x01\x02" + bytes(8) + first_seed,
    )
    assert runtime.current_event_key == derive_event_key_from_seed(first_seed)
    assert runtime.current_event_key != old_event_key

    backup_event = build_user_frame(
        b"\x02\xA7\x01\x37",
        destination=PAIRLINK_BROADCAST_ADDRESS,
        channel=32,
        own_virtual_address=bytes(4),
    )
    encrypted_backup_event = encrypt_user_frame(
        backup_event,
        event_key=runtime.current_event_key,
        device_key=_PRIMARY_SESSION_KEY,
    )
    await _send_peer_write(bus, _PEER_PATH, encrypted_backup_event)
    assert controller._peer_states[_PEER_ADDRESS]["back_position"] == 55
    assert "back_position" not in controller._state

    selector_event = build_user_frame(
        b"\x02\xA8\xFF\x20",
        destination=PAIRLINK_BROADCAST_ADDRESS,
        channel=32,
        own_virtual_address=bytes(4),
    )
    await _send_peer_write(bus, backup_path, selector_event)
    await hass.async_block_till_done()
    query_payloads = tuple(
        bytes((0x01, 0xA7, 0x20, selector))
        for selector in (*range(1, 9), 14)
    )
    assert tuple(_recv(backup_socket) for _ in query_payloads) == tuple(
        build_user_frame(
            payload,
            destination=PAIRLINK_BROADCAST_ADDRESS,
            channel=32,
            own_virtual_address=bytes(4),
        )
        for payload in query_payloads
    )

    for selector, value in ((1, 20), (2, 30), (3, 40), (5, 30), (6, 40), (12, 2), (14, 4)):
        await _send_state_selector(
            bus,
            backup_path,
            runtime,
            selector,
            value,
            encrypted=False,
        )

    device = _device_for_address(hass, _BED_ADDRESS)
    assert device is not None
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REVERIE_SET_COMFORT,
        {"device_id": [device.id], "comfort": {"head_position": 35}},
        blocking=True,
    )
    first_action = _recv(backup_socket)
    second_action = _recv(backup_socket)
    assert first_action == build_user_frame(
        bytes.fromhex("01A71701"),
        destination=PAIRLINK_BROADCAST_ADDRESS,
        channel=32,
        own_virtual_address=bytes(4),
    )
    assert second_action == build_user_frame(
        bytes.fromhex("01012300"),
        destination=PAIRLINK_BROADCAST_ADDRESS,
        channel=32,
        own_virtual_address=bytes(4),
    )

    alarm_values = {
        "head_position": 20,
        "foot_position": 30,
        "lumbar_position": 40,
        "head_massage": 0,
        "foot_massage": 5,
        "timer_byte": 4,
        "mode": 2,
    }
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
        {"device_id": [device.id], "comfort": alarm_values},
        blocking=True,
    )
    forced_frames = tuple(
        build_user_frame(
            payload,
            destination=PAIRLINK_BROADCAST_ADDRESS,
            channel=32,
            own_virtual_address=bytes(4),
        )
        for payload in comfort_payloads(values=alarm_values, current=None, force=True)
    )
    assert len(forced_frames) == 8
    assert tuple(_recv(backup_socket) for _ in forced_frames) == forced_frames
    assert _read_characteristic(bus, transport._NOTIFY_CHARACTERISTIC_PATH) == b"\x66"
    with pytest.raises(BlockingIOError):
        _recv(primary_socket)

    assert _read_characteristic(bus, transport._NOTIFY_CHARACTERISTIC_PATH) == b"\x66"
    assert _read_characteristic(bus, transport._WRITE_CHARACTERISTIC_PATH) == b"\x44"

    primary_socket.close()
    backup_socket.close()
    await async_unload_entry(hass, entry)


async def test_local_runtime_unload_cancels_controller_timers_without_central_client(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime

    class FakeTimer:
        def __init__(self, callback: Callable[..., None], args: tuple[object, ...]) -> None:
            self.callback = callback
            self.args = args
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    timers: list[FakeTimer] = []
    loop = hass.loop
    original_call_later = loop.call_later

    def call_later(delay: float, callback: Callable[..., None], *args: object) -> object:
        if getattr(callback, "__self__", None) is controller and getattr(
            callback, "__name__", ""
        ) in {"_enqueue_backup_check", "_enqueue_status_sync"}:
            timer = FakeTimer(callback, args)
            timers.append(timer)
            return timer
        return original_call_later(delay, callback, *args)

    monkeypatch.setattr(loop, "call_later", call_later)
    peer_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(peer_socket).startswith(b"\x02\x19")
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(peer_socket) == b"\x01\x20"
    assert controller._active_control_session is True
    assert {timer.callback.__name__ for timer in timers} == {
        "_enqueue_backup_check",
        "_enqueue_status_sync",
    }

    peer_socket.close()
    await async_unload_entry(hass, entry)

    assert coordinator.client is None
    assert runtime.is_closed is True
    assert all(timer.cancelled for timer in timers)
    assert controller._status_sync_timer is None
    assert controller._backup_check_timer is None


async def test_local_welcome_backup_exit_timer_and_primary_disconnect_cleanup(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime

    class FakeTimer:
        def __init__(self, delay: float, callback: Callable[..., None], args: tuple[object, ...]) -> None:
            self.delay = delay
            self.callback = callback
            self.args = args
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

        def fire(self) -> None:
            if not self.cancelled:
                self.callback(*self.args)

        def fire_even_if_cancelled(self) -> None:
            self.callback(*self.args)

    timers: list[FakeTimer] = []
    loop = hass.loop
    original_call_later = loop.call_later

    def call_later(delay: float, callback: Callable[..., None], *args: object) -> object:
        if (
            getattr(callback, "__self__", None) is controller
            and getattr(callback, "__name__", "") == "_enqueue_backup_check"
        ):
            timer = FakeTimer(delay, callback, args)
            timers.append(timer)
            return timer
        return original_call_later(delay, callback, *args)

    monkeypatch.setattr(loop, "call_later", call_later)
    primary_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(primary_socket).startswith(b"\x02\x19")
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x07")
    assert timers == []
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(primary_socket) == b"\x01\x20"
    assert runtime.peripheral_stop_adv_after_welcome is True
    assert [timer.delay for timer in timers] == [1]

    backup_address = "22:33:44:55:66:77"
    backup_path = _peer_path("hci3", backup_address)
    bus.managed_objects[backup_path] = _device(backup_address)
    backup_socket = await _subscribe_peer(bus, backup_path)
    backup_identity = runtime.peer_sessions[backup_address].identity
    assert backup_identity is not None

    from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
        PairlinkPeerLifecycleEvent,
        PairlinkPeerLifecycleKind,
    )

    controller._handle_peripheral_peer_lifecycle(
        PairlinkPeerLifecycleEvent(
            PairlinkPeerLifecycleKind.NOTIFY_UNSUBSCRIBED,
            backup_identity,
        )
    )
    assert runtime.peer_sessions[backup_address].connected is True
    assert runtime.peer_sessions[backup_address].subscribed is False
    assert runtime.joined is True
    assert runtime.primary_mac == _PEER_ADDRESS
    controller._handle_peripheral_peer_lifecycle(
        PairlinkPeerLifecycleEvent(
            PairlinkPeerLifecycleKind.NOTIFY_SUBSCRIBED,
            backup_identity,
            23,
        )
    )

    timers[0].fire()
    await hass.async_block_till_done()
    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
        PAIRLINK_EXIT_COMMAND,
    )

    assert _recv(backup_socket) == PAIRLINK_EXIT_COMMAND
    assert [timer.delay for timer in timers] == [1, 0.8]

    backend = runtime.peripheral_backend
    assert backend is not None
    original_notify = backend.async_notify_to_peer

    async def fail_backup_send(_peer: object, _value: bytes) -> None:
        raise RuntimeError("simulated backup write failure")

    monkeypatch.setattr(backend, "async_notify_to_peer", fail_backup_send)
    timers[1].fire()
    await hass.async_block_till_done()
    assert [timer.delay for timer in timers] == [1, 0.8, 0.8]
    with pytest.raises(BlockingIOError):
        _recv(backup_socket)
    monkeypatch.setattr(backend, "async_notify_to_peer", original_notify)

    timers[2].fire()
    await hass.async_block_till_done()
    assert _recv(backup_socket) == PAIRLINK_EXIT_COMMAND
    assert [timer.delay for timer in timers] == [1, 0.8, 0.8, 0.8]
    pending = timers[3]
    primary_session = runtime.peer_sessions[_PEER_ADDRESS]
    assert primary_session.provisioning.initialized is True
    assert runtime._peer_keys[_PEER_ADDRESS]

    bus.managed_objects[_PEER_PATH] = _device(connected=False)
    assert bus.peer_disconnect_callback is not None
    bus.peer_disconnect_callback(_PEER_PATH, False)
    await hass.async_block_till_done()

    assert pending.cancelled is True
    assert _recv(backup_socket) == PAIRLINK_EXIT_COMMAND
    assert runtime.joined is False
    assert runtime.primary_mac is None
    assert runtime.own_virtual_address == bytes(4)
    assert runtime.own_virtual_address_assigned is False
    assert runtime._peer_keys == {}
    assert primary_session.provisioning.initialized is False
    retained_backup = runtime.peer_sessions[backup_address]
    assert retained_backup.connected is True
    assert retained_backup.subscribed is True
    assert retained_backup.backup is False
    assert retained_backup.provisioning.initialized is False
    with pytest.raises(BlockingIOError):
        _recv(backup_socket)

    pending.fire_even_if_cancelled()
    await hass.async_block_till_done()
    assert len(timers) == 4
    assert controller._backup_check_timer is None
    assert _recv(primary_socket) == b""

    primary_socket.close()
    backup_socket.close()
    await async_unload_entry(hass, entry)
    assert runtime.is_closed is True


async def test_local_active_status_loop_rearms_and_stops_on_physical_disconnect(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    scheduled_delays: list[float] = []

    def capture_schedule(_generation: int, *, delay_seconds: float) -> None:
        scheduled_delays.append(delay_seconds)

    monkeypatch.setattr(controller, "_schedule_status_sync", capture_schedule)
    peer_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(peer_socket).startswith(b"\x02\x19")
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(peer_socket) == b"\x01\x20"
    assert controller._active_control_session is True
    assert scheduled_delays == [0]

    generation = controller._status_sync_generation
    await controller._async_run_status_sync(generation)
    assert tuple(_recv(peer_socket) for _ in range(2)) == _expected_status_sync_frames(
        runtime
    )
    assert scheduled_delays == [0, 1]

    bus.managed_objects[_PEER_PATH] = _device(connected=False)
    assert bus.peer_disconnect_callback is not None
    bus.peer_disconnect_callback(_PEER_PATH, False)
    assert controller._active_control_session is False
    await controller._async_run_status_sync(generation)
    # BlueZ closes the acquired socket on Device1 disconnect; b"" is EOF, while
    # any stale A8/A9 write would be returned before EOF.
    assert _recv(peer_socket) == b""
    assert scheduled_delays == [0, 1]

    peer_socket.close()
    await async_unload_entry(hass, entry)
    assert runtime.is_closed is True
    assert runtime.admitted_peer_count == 0
    assert runtime.event_key_history == ((bytes(4), bytes(4), bytes(16)),) * 5
    assert runtime.credentials.password == bytes(4)
    assert bus.application_registered is False
    assert bus.advertisement_registered is False


async def test_registered_write_value_selects_six_through_nine_byte_events(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    peer_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    _recv(peer_socket)
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    _recv(peer_socket)
    await hass.async_block_till_done()
    while True:
        try:
            _recv(peer_socket)
        except BlockingIOError:
            break

    events: list[tuple[int, bytes | None, bool]] = []
    sdk_frames: list[bytes] = []
    controller.set_mesh_event_callback(
        lambda event_type, data, broadcast: events.append(
            (event_type, data, broadcast)
        )
    )
    controller._consume_sdk_frame = lambda effect: sdk_frames.append(effect.frame)

    for size in range(6, 10):
        await _send_peer_write(
            bus,
            _PEER_PATH,
            b"\x03" + b"\xff" * 4 + b"\x20" + bytes(range(size - 6)),
        )

    assert events == [
        (0x20, bytes(range(size - 6)), True)
        for size in range(6, 10)
    ]
    assert sdk_frames == []
    assert runtime.primary_mac == _PEER_ADDRESS
    await async_unload_entry(hass, entry)
    peer_socket.close()


async def test_local_hold_release_stays_with_captured_peer_after_primary_drift(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime

    primary_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet(_PRIMARY_SESSION_KEY))
    _recv(primary_socket)
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(primary_socket) == b"\x01\x20"
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert controller._active_control_session is True
    _drain_socket(primary_socket)

    backup_address = "22:33:44:55:66:77"
    backup_path = _peer_path("hci3", backup_address)
    bus.managed_objects[backup_path] = _device(backup_address)
    backup_socket = await _subscribe_peer(bus, backup_path)
    await _send_peer_write(bus, backup_path, b"\x01\x00" + bytes(4))
    assert _recv(backup_socket) == b"\x02\x00" + bytes(4) + _PASSWORD

    release_sleep = asyncio.Event()
    sleep_started = asyncio.Event()

    async def wait_for_release(_delay: float) -> None:
        sleep_started.set()
        await release_sleep.wait()

    def expected_frame(command: bytes) -> bytes:
        return encrypt_user_frame(
            build_user_frame(
                command,
                destination=PAIRLINK_BROADCAST_ADDRESS,
                channel=32,
                own_virtual_address=bytes(4),
            ),
            event_key=runtime.current_event_key,
            device_key=_PRIMARY_SESSION_KEY,
        )

    with monkeypatch.context() as temporary_patch:
        temporary_patch.setattr(asyncio, "sleep", wait_for_release)

        async def hold(selected: object) -> None:
            assert selected is controller
            await selected.hold_control("back_up", 100)

        hold_task = asyncio.create_task(
            coordinator.async_execute_controller_command(
                hold,
                resource="reverie:pairlink:captured-hold-test",
                read_positions_after_operation=False,
            )
        )
        await asyncio.wait_for(sleep_started.wait(), timeout=1)
        press = expected_frame(dashboard_payload(1, 0xFF))
        assert _recv(primary_socket) == press

        await _send_peer_write(bus, backup_path, b"\x02\x31\x08")
        assert _recv(backup_socket) == b"\x01\x20"
        assert runtime.primary_mac == backup_address

        release_sleep.set()
        await hold_task

    release = expected_frame(dashboard_payload(3, 0))
    assert _recv(primary_socket) == release
    with pytest.raises(BlockingIOError):
        _recv(backup_socket)

    primary_socket.close()
    backup_socket.close()
    await async_unload_entry(hass, entry)


async def test_local_diagnostic_cleanup_stays_with_captured_peer_after_primary_drift(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime

    primary_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet(_PRIMARY_SESSION_KEY))
    _recv(primary_socket)
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(primary_socket) == b"\x01\x20"
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    _drain_socket(primary_socket)

    captured = controller._capture_current_send_snapshot()

    def expected_frame(
        command: bytes, *, snapshot: PairlinkSendSnapshot
    ) -> bytes:
        assert snapshot.device_key is not None
        return encrypt_user_frame(
            build_user_frame(
                command,
                destination=PAIRLINK_BROADCAST_ADDRESS,
                channel=32,
                own_virtual_address=snapshot.own_virtual_address,
            ),
            event_key=snapshot.event_key,
            device_key=snapshot.device_key,
        )

    await controller.async_start_diagnostic()
    assert _recv(primary_socket) == expected_frame(
        dashboard_payload(79, 20), snapshot=captured
    )
    assert _recv(primary_socket) == expected_frame(
        dashboard_payload(92, 0), snapshot=captured
    )
    generation = controller._diagnostic_generation

    backup_address = "22:33:44:55:66:77"
    backup_path = _peer_path("hci3", backup_address)
    bus.managed_objects[backup_path] = _device(backup_address)
    backup_socket = await _subscribe_peer(bus, backup_path)
    await _send_peer_write(bus, backup_path, b"\x01\x00" + bytes(4))
    assert _recv(backup_socket) == b"\x02\x00" + bytes(4) + _PASSWORD
    await _send_peer_write(bus, backup_path, b"\x02\x31\x08")
    assert _recv(backup_socket) == b"\x01\x20"
    assert runtime.primary_mac == backup_address
    _drain_socket(primary_socket)
    _drain_socket(backup_socket)

    diagnostic_timer = controller._diagnostic_timer
    assert diagnostic_timer is not None
    diagnostic_timer.cancel()
    controller._enqueue_diagnostic_stop(captured, generation)
    await hass.async_block_till_done()
    release_snapshot = runtime.prepare_release_snapshot(captured)
    assert _recv(primary_socket) == expected_frame(
        dashboard_payload(72, 0), snapshot=release_snapshot
    )
    assert _recv(primary_socket) == expected_frame(
        dashboard_payload(93, 0), snapshot=release_snapshot
    )
    with pytest.raises(BlockingIOError):
        _recv(backup_socket)

    primary_socket.close()
    backup_socket.close()
    await async_unload_entry(hass, entry)


async def test_local_native_reply_runs_under_command_operation_then_cancels_and_unloads(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    assert coordinator.client is None

    peer_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(peer_socket).startswith(b"\x02\x19")
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(peer_socket) == b"\x01\x20"

    operation_started = asyncio.Event()

    async def hold_existing_command_lane(selected: object) -> None:
        assert selected is controller
        operation_started.set()
        await asyncio.Event().wait()

    command_task = asyncio.create_task(
        coordinator.async_execute_controller_command(
            hold_existing_command_lane,
            cancel_running=False,
            resource="reverie:pairlink:handshake-barrier",
            read_positions_after_operation=False,
        )
    )
    await asyncio.wait_for(operation_started.wait(), timeout=1)

    replacement_session = bytes.fromhex("AABBCCDD")
    await asyncio.wait_for(
        _send_peer_write(
            bus,
            _PEER_PATH,
            _login_packet(session_key=replacement_session),
        ),
        timeout=1,
    )
    reply = _recv(peer_socket)
    assert reply.startswith(b"\x02\x19")
    assert decrypt_login_block(reply[2:], login_key=_login_context())[8:12] == replacement_session
    assert runtime._peer_keys[_PEER_ADDRESS] == _PRIMARY_SESSION_KEY

    command_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await command_task
    assert coordinator._client is None

    peer_socket.close()
    await async_unload_entry(hass, entry)
    assert runtime.is_closed is True
    assert bus.application_registered is False
    assert bus.advertisement_registered is False


async def test_registered_local_provisioning_keeps_p256_state_per_physical_peer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
        _derive_provision_confirmation,
        _derive_provision_data,
    )

    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime

    second_address = "22:33:44:55:66:77"
    second_path = _peer_path("hci3", second_address)
    bus.managed_objects[second_path] = _device(second_address)
    first_socket = await _subscribe_peer(bus, _PEER_PATH, mtu=100)
    second_socket = await _subscribe_peer(bus, second_path, mtu=100)

    capability = b"\x02\x31\x01" + bytes(7)
    await _send_peer_write(bus, _PEER_PATH, capability)
    assert _recv(first_socket) == b"\x01\x31\x02\x00\x00\x00"
    first_public_reply = _recv(first_socket)
    assert first_public_reply[:3] == b"\x01\x31\x03"
    assert len(first_public_reply) == 67
    first_state = runtime.peer_sessions[_PEER_ADDRESS].provisioning
    assert first_state.stage == 2
    assert first_state.initialized is True
    assert first_state.source_mac == _PEER_ADDRESS
    assert first_state.extension == _HOME_ID.to_bytes(4, "little")

    await _send_peer_write(bus, second_path, capability)
    assert _recv(second_socket) == b"\x01\x31\x02\x00\x00\x00"
    second_public_reply = _recv(second_socket)
    assert second_public_reply[:3] == b"\x01\x31\x03"
    assert second_public_reply[3:] != first_public_reply[3:]
    second_state = runtime.peer_sessions[second_address].provisioning
    assert second_state.stage == 2
    assert second_state.local_private_key is not first_state.local_private_key

    # The nonzero capability callback is retained but has no ordinary-app
    # response and does not advance the source state machine.
    capability_peer = "33:44:55:66:77:88"
    capability_path = _peer_path("hci3", capability_peer)
    bus.managed_objects[capability_path] = _device(capability_peer)
    capability_socket = await _subscribe_peer(bus, capability_path, mtu=100)
    await _send_peer_write(
        bus,
        capability_path,
        b"\x02\x31\x01" + bytes.fromhex("01000000000000"),
    )
    capability_state = runtime.peer_sessions[capability_peer].provisioning
    assert capability_state.capability == bytes.fromhex("01000000000000")
    assert capability_state.source_mac == capability_peer
    assert capability_state.stage == 0
    with pytest.raises(BlockingIOError):
        _recv(capability_socket)

    # The source guard consumes exactly 64 coordinate bytes; a short peer point
    # cannot advance either peer's independent setup state.
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x03" + bytes(63))
    assert first_state.stage == 2
    with pytest.raises(BlockingIOError):
        _recv(first_socket)

    peer_private = ec.generate_private_key(ec.SECP256R1())
    peer_public = peer_private.public_key().public_bytes(
        Encoding.X962,
        PublicFormat.UncompressedPoint,
    )
    local_public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(),
        b"\x04" + first_public_reply[3:],
    )
    shared_secret = peer_private.exchange(ec.ECDH(), local_public_key)
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x03" + peer_public[1:])
    confirmation_salt, expected_confirmation = _derive_provision_confirmation(
        capability=first_state.capability,
        start=first_state.start,
        local_public_key=first_state.local_public_key,
        peer_public_key=peer_public[1:],
        shared_secret=shared_secret,
        local_random=first_state.local_random,
        auth=first_state.auth,
    )
    assert _recv(first_socket) == b"\x01\x31\x05" + expected_confirmation
    assert first_state.confirmation_salt == confirmation_salt
    assert first_state.stage == 3
    assert second_state.stage == 2

    # Native subtype 05 consumes, but does not compare, the peer confirmation.
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x05" + bytes(16))
    local_random_reply = _recv(first_socket)
    assert local_random_reply == b"\x01\x31\x06" + first_state.local_random
    assert first_state.stage == 4

    peer_random = bytes(range(16, 32))
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x06" + peer_random)
    _, session_key, _, ciphertext = _derive_provision_data(
        confirmation_salt=confirmation_salt,
        shared_secret=shared_secret,
        local_random=first_state.local_random,
        peer_random=peer_random,
        plaintext=(
            bytes.fromhex("5566AABB")
            + b"\x05\x01"
            + _HOME_ID.to_bytes(4, "little")
            + b"\x05\x04"
            + _PASSWORD
            + b"\x02\x03\xA6"
            + b"\x05\xFF"
            + _HOME_ID.to_bytes(4, "little")
        ),
    )
    assert _recv(first_socket) == b"\x01\x31\x07" + ciphertext
    assert first_state.session_key == session_key
    assert first_state.stage == 5
    assert second_state.stage == 2
    assert repr(first_state).find(_PASSWORD.decode()) == -1

    first_socket.close()
    second_socket.close()
    capability_socket.close()
    await async_unload_entry(hass, entry)
    assert runtime.is_closed is True
    assert runtime.peer_sessions == {}
    assert bus.application_registered is False
    assert bus.advertisement_registered is False


async def test_local_native_subtype04_uses_only_current_initialized_transcript(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
        _derive_provision_confirmation,
    )

    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    runtime = coordinator.controller._runtime
    peer_socket = await _subscribe_peer(bus, _PEER_PATH, mtu=100)
    peer_state = runtime.peer_sessions[_PEER_ADDRESS].provisioning

    # The source subtype has no length/state guard, but an uninitialized native
    # curve/key block is not a successful host transcript.
    peer_state.clear()
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x04")
    assert peer_state.stage == 0
    with pytest.raises(BlockingIOError):
        _recv(peer_socket)

    peer = runtime.peer_sessions[_PEER_ADDRESS].identity
    assert peer is not None
    runtime.initialize_peer_provisioning(
        peer,
        extension=_HOME_ID.to_bytes(4, "little"),
    )
    peer_state = runtime.peer_sessions[_PEER_ADDRESS].provisioning
    _salt, expected = _derive_provision_confirmation(
        capability=bytes(7),
        start=bytes(3),
        local_public_key=peer_state.local_public_key,
        peer_public_key=bytes(64),
        shared_secret=bytes(32),
        local_random=peer_state.local_random,
        auth=bytes(16),
    )

    # Native subtype 04 ignores its payload length/state, calculates the
    # current initialized transcript, sends opcode 05 and sets state 3.
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x04ignored")
    assert _recv(peer_socket) == b"\x01\x31\x05" + expected
    assert peer_state.stage == 3
    peer_socket.close()
    await async_unload_entry(hass, entry)
    assert runtime.is_closed is True


async def test_local_provisioning_fails_closed_when_native_init_cannot_create_key(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    del enable_custom_integrations
    from custom_components.adjustable_bed.beds import reverie_pairlink_runtime

    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller

    def unavailable_key_provider(_curve: object) -> object:
        raise RuntimeError("synthetic P-256 provider failure")

    monkeypatch.setattr(
        reverie_pairlink_runtime.ec,
        "generate_private_key",
        unavailable_key_provider,
    )
    peer_socket = await _subscribe_peer(bus, _PEER_PATH, mtu=100)
    state = controller._runtime.peer_sessions[_PEER_ADDRESS].provisioning
    assert state.initialized is False

    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x01" + bytes(7))
    assert state.stage == 0
    with pytest.raises(BlockingIOError):
        _recv(peer_socket)
    assert controller._runtime.disconnected_transport_ready is False

    peer_socket.close()
    await async_unload_entry(hass, entry)
    assert controller._runtime.is_closed is True
    assert bus.application_registered is False
    assert bus.advertisement_registered is False


async def test_exported_write_identity_failures_and_subscription_lifetime(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    write_characteristic = _interface(bus, transport._WRITE_CHARACTERISTIC_PATH)

    with pytest.raises(DBusError):
        await _write_value(write_characteristic, b"\x01\x19", {})
    with pytest.raises(DBusError):
        await _write_value(
            write_characteristic,
            b"\x01\x19",
            {"device": Variant("s", _PEER_PATH)},
        )
    wrong_adapter_path = _peer_path("hci4", _PEER_ADDRESS)
    with pytest.raises(DBusError):
        await _write_value(
            write_characteristic,
            b"\x01\x19",
            {"device": Variant("o", wrong_adapter_path)},
        )

    bus.managed_objects[_PEER_PATH] = _device("22:33:44:55:66:77")
    with pytest.raises(DBusError):
        await _write_value(
            write_characteristic,
            b"\x01\x19",
            {"device": Variant("o", _PEER_PATH)},
        )
    assert runtime.peer_sessions == {}
    assert runtime.admitted_peer_count == 0

    bus.managed_objects[_PEER_PATH] = _device()
    bluez_socket = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(bluez_socket).startswith(b"\x02\x19")
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(bluez_socket) == b"\x01\x20"
    await _send_state_selector(bus, _PEER_PATH, runtime, 1, 35)
    assert controller._state["back_position"] == 35
    old_peer = runtime.peer_sessions[_PEER_ADDRESS].identity
    old_snapshot = runtime.prepare_send()
    old_epoch = runtime.epoch

    bluez_socket.close()
    for _ in range(3):
        await asyncio.sleep(0)
    session_after_unsubscribe = runtime.peer_sessions[_PEER_ADDRESS]
    assert session_after_unsubscribe.connected is True
    assert session_after_unsubscribe.subscribed is False
    assert runtime.joined is True
    assert runtime._peer_keys[_PEER_ADDRESS] == _PRIMARY_SESSION_KEY
    assert runtime.epoch == old_epoch
    assert runtime.snapshot_is_current(old_snapshot) is False

    resubscribed_socket = await _subscribe_peer(bus, _PEER_PATH)
    assert runtime.peer_sessions[_PEER_ADDRESS].connected is True
    assert runtime.peer_sessions[_PEER_ADDRESS].subscribed is True
    assert runtime.joined is True
    assert runtime.epoch == old_epoch
    assert runtime.peer_sessions[_PEER_ADDRESS].identity == old_peer

    bus.managed_objects[_PEER_PATH] = _device(connected=False)
    assert bus.peer_disconnect_callback is not None
    bus.peer_disconnect_callback(_PEER_PATH, False)
    assert runtime.peer_sessions == {}
    assert runtime.joined is False
    assert runtime.admitted_peer_count == 0
    assert "back_position" not in controller._state
    assert runtime.epoch > old_epoch

    bus.managed_objects[_PEER_PATH] = _device()
    fresh_socket = await _subscribe_peer(bus, _PEER_PATH)
    fresh_identity = runtime.peer_sessions[_PEER_ADDRESS].identity
    assert fresh_identity is not None and old_peer is not None
    assert fresh_identity.connection_generation > old_peer.connection_generation
    assert fresh_identity != old_peer
    assert runtime.snapshot_is_current(old_snapshot) is False
    assert runtime.disconnected_transport_ready is False
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(fresh_socket) == b"\x02\x19" + encrypt_login_block(
        _HOME_ID.to_bytes(4, "little")
        + _PASSWORD
        + _PRIMARY_SESSION_KEY
        + b"\x04" * 4,
        login_key=_login_context(),
    )
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    assert _recv(fresh_socket) == b"\x01\x20"
    assert runtime.disconnected_transport_ready is True
    assert "back_position" not in controller._state
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    _drain_socket(fresh_socket)
    device = _device_for_address(hass, _BED_ADDRESS)
    assert device is not None
    with pytest.raises(ServiceValidationError, match="cannot preserve foot_position"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_REVERIE_SET_COMFORT,
            {"device_id": [device.id], "comfort": {"head_position": 35}},
            blocking=True,
        )
    with pytest.raises(BlockingIOError):
        _recv(fresh_socket)
    fresh_snapshot = runtime.prepare_send()
    rejoin_payload = bytes.fromhex("0101FF00")
    await controller.async_send_payload(rejoin_payload)
    assert _recv(fresh_socket) == encrypt_user_frame(
        build_user_frame(
            rejoin_payload,
            destination=PAIRLINK_BROADCAST_ADDRESS,
            channel=32,
            own_virtual_address=fresh_snapshot.own_virtual_address,
        ),
        event_key=fresh_snapshot.event_key,
        device_key=_PRIMARY_SESSION_KEY,
    )

    resubscribed_socket.close()
    fresh_socket.close()
    await async_unload_entry(hass, entry)
    assert runtime.is_closed is True
    with pytest.raises(ConnectionError):
        runtime.peer_connected(cast(transport.PairlinkPeerIdentity, old_peer))


async def test_central_entry_factory_routes_real_notify_callback_and_action(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
    mock_async_ble_device_from_address: MagicMock,
    mock_coordinator_connected: None,
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cryptography")
    del mock_coordinator_connected, enable_custom_integrations
    from homeassistant.components import bluetooth

    from custom_components.adjustable_bed import bluetooth_transport
    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
        PAIRLINK_NOTIFY_UUID,
        PAIRLINK_SERVICE_UUID,
        PAIRLINK_WRITE_UUID,
    )

    mock_async_ble_device_from_address.return_value.address = _BED_ADDRESS
    mock_bleak_client.address = _BED_ADDRESS
    mock_bleak_client.services = [
        _GattService(PAIRLINK_SERVICE_UUID, PAIRLINK_WRITE_UUID, PAIRLINK_NOTIFY_UUID)
    ]
    service_info = SimpleNamespace(
        address=_BED_ADDRESS,
        name="R510L",
        manufacturer_data=_manufacturer_data(),
        service_uuids=(PAIRLINK_SERVICE_UUID,),
        service_data={},
    )
    monkeypatch.setattr(
        bluetooth,
        "async_last_service_info",
        lambda *_args, **_kwargs: service_info,
    )
    monkeypatch.setattr(
        bluetooth_transport,
        "classify_scanner",
        lambda _scanner: bluetooth_transport.TransportClass.LOCAL,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Central Pairlink bed",
        unique_id=_BED_ADDRESS,
        data={
            "address": _BED_ADDRESS,
            "name": "Central Pairlink bed",
            "bed_type": BED_TYPE_REVERIE_PAIRLINK,
            "protocol_variant": "R510L",
            "motor_count": 2,
            "has_massage": True,
            "disable_angle_sensing": False,
        },
    )
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=None),
    ):
        assert await async_setup_entry(hass, entry)
    entry.mock_state(hass, ConfigEntryState.LOADED)

    coordinator = hass.data[DOMAIN][entry.entry_id]
    controller = coordinator.controller
    runtime = coordinator._pairlink_runtime
    assert runtime is controller._runtime
    assert controller.requires_disconnected_transport is False
    assert runtime.role.value == "central"
    assert coordinator.client is mock_bleak_client
    notify = mock_bleak_client.start_notify.await_args.args[1]
    assert runtime._central_provisioning.initialized is True
    assert runtime._central_provisioning.source_mac == _BED_ADDRESS

    notify(None, bytearray(b"\x01\x19short"))
    notify(None, bytearray(_login_packet(home_id=_HOME_ID + 1)))
    await hass.async_block_till_done()
    assert runtime.admitted_peer_count == 0
    assert runtime.central_add_pending is True
    assert mock_bleak_client.write_gatt_char.await_args_list == []

    # The accepted fixed-mode provision-init owner is tied to this connected
    # central target and its current HomeID. A real registered raw callback
    # consumes subtype 01 and returns the native setup frames.
    notify(None, bytearray(b"\x02\x31\x01" + bytes(7)))
    await hass.async_block_till_done()
    assert runtime._central_provisioning.stage == 2
    assert runtime._central_provisioning.source_mac == _BED_ADDRESS
    setup_writes = mock_bleak_client.write_gatt_char.await_args_list
    assert setup_writes[0].args == (
        PAIRLINK_WRITE_UUID,
        b"\x01\x31\x02\x00\x00\x00",
    )
    setup_public = b"\x01\x31\x03" + runtime._central_provisioning.local_public_key
    assert tuple(call.args[1] for call in setup_writes[1:]) == fragment_central_frame(
        setup_public,
        att_mtu=mock_bleak_client.mtu_size,
    )

    async with coordinator._command_lock:
        notify(None, bytearray(_login_packet()))
        await hass.async_block_till_done()
    expected_login = encrypt_login_block(
        _HOME_ID.to_bytes(4, "little")
        + _PASSWORD
        + _PRIMARY_SESSION_KEY
        + b"\x04" * 4,
        login_key=_login_context(),
    )
    assert mock_bleak_client.write_gatt_char.await_args_list[-1].args == (
        PAIRLINK_WRITE_UUID,
        b"\x02\x19" + expected_login,
    )
    notify(None, bytearray(_login_packet(session_key=_BACKUP_SESSION_KEY)))
    await hass.async_block_till_done()
    assert runtime._peer_keys[_BED_ADDRESS] == _PRIMARY_SESSION_KEY
    duplicate_plaintext = decrypt_login_block(
        mock_bleak_client.write_gatt_char.await_args_list[-1].args[1][2:],
        login_key=_login_context(),
    )
    assert duplicate_plaintext[8:12] == _BACKUP_SESSION_KEY

    notify(None, bytearray(b"\x02\x31\x08"))
    await hass.async_block_till_done()
    assert runtime.own_virtual_address == bytes(4)
    notify(None, bytearray(b"\x04\x04\x21\x01\x0A\x11"))
    await hass.async_block_till_done()
    assert runtime.own_virtual_address == bytes(4)
    notify(None, bytearray(b"\x04\x04\x22\x22\x33\x44"))
    await hass.async_block_till_done()
    assert runtime.own_virtual_address == bytes.fromhex("11223344")
    device = _device_for_address(hass, _BED_ADDRESS)
    assert device is not None
    snapshot = runtime.prepare_send(mtu=mock_bleak_client.mtu_size)
    first_write = len(mock_bleak_client.write_gatt_char.await_args_list)
    comfort = {
        "head_position": 35,
        "foot_position": 30,
        "lumbar_position": 40,
        "head_massage": 3,
        "foot_massage": 5,
        "timer_byte": 4,
        "mode": 2,
    }
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REVERIE_SET_COMFORT,
        {"device_id": [device.id], "comfort": comfort},
        blocking=True,
    )
    assert runtime.joined is True
    expected_writes = tuple(
        fragment
        for payload in comfort_payloads(
            values=comfort,
            current=None,
            force=False,
        )
        for fragment in fragment_central_frame(
            encrypt_user_frame(
                build_user_frame(
                    payload,
                    destination=PAIRLINK_BROADCAST_ADDRESS,
                    channel=32,
                    own_virtual_address=snapshot.own_virtual_address,
                ),
                event_key=snapshot.event_key,
                device_key=cast(bytes, snapshot.device_key),
            ),
            att_mtu=snapshot.mtu,
        )
    )
    actual_writes = tuple(
        call.args[1]
        for call in mock_bleak_client.write_gatt_char.await_args_list[first_write:]
        if call.args[0] == PAIRLINK_WRITE_UUID
    )
    assert actual_writes == expected_writes

    old_handler = notify
    await coordinator.async_disconnect(reason="Pairlink callback generation test")
    mock_bleak_client.is_connected = False
    stale_count = runtime.admitted_peer_count
    old_handler(None, bytearray(_login_packet(session_key=_BACKUP_SESSION_KEY)))
    assert runtime.admitted_peer_count == stale_count
    assert runtime.joined is False
    await coordinator.async_shutdown()
    assert runtime.is_closed is True


@pytest.mark.parametrize("second_ready", [False, True])
async def test_all_target_pairlink_preflight_rejects_later_unready_or_unknown_bed_before_writes(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
    second_ready: bool,
) -> None:
    del enable_custom_integrations
    first_source = "AA:BB:CC:DD:EE:FF"
    second_source = "AA:BB:CC:DD:EE:01"
    first_peer_path = _peer_path("hci3", _PEER_ADDRESS)
    second_peer_address = "22:33:44:55:66:77"
    second_peer_path = _peer_path("hci4", second_peer_address)
    first_bus = FakeBlueZBus(
        managed_objects=_adapter_objects(
            "hci3",
            first_source,
            {first_peer_path: _device(_PEER_ADDRESS, adapter_path="/org/bluez/hci3")},
        )
    )
    second_bus = FakeBlueZBus(
        managed_objects=_adapter_objects(
            "hci4",
            second_source,
            {second_peer_path: _device(second_peer_address, adapter_path="/org/bluez/hci4")},
        )
    )
    buses = iter((first_bus, second_bus))
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", lambda: next(buses))
    scanners = _scanners(((first_source, "hci3"), (second_source, "hci4")))
    first_entry = _entry(address=_BED_ADDRESS, title="First Pairlink", host_source=first_source)
    second_address = "00:10:20:30:40:51"
    second_entry = _entry(
        address=second_address,
        title="Second Pairlink",
        host_source=second_source,
    )
    first_coordinator = await _local_setup(
        hass,
        monkeypatch,
        first_entry,
        first_bus,
        scanners=scanners,
    )
    second_coordinator = await _local_setup(
        hass,
        monkeypatch,
        second_entry,
        second_bus,
        scanners=scanners,
    )
    first_socket = await _subscribe_peer(first_bus, first_peer_path)
    await _send_peer_write(first_bus, first_peer_path, _login_packet())
    _recv(first_socket)
    await _send_peer_write(first_bus, first_peer_path, b"\x02\x31\x08")
    _recv(first_socket)
    first_runtime = first_coordinator._pairlink_runtime
    assert first_runtime is not None
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert first_coordinator.controller._active_control_session is True
    assert tuple(_recv(first_socket) for _ in range(2)) == _expected_status_sync_frames(
        first_runtime
    )
    for selector, value in ((1, 20), (2, 30), (3, 40), (5, 30), (6, 40), (12, 2), (14, 4)):
        await _send_state_selector(first_bus, first_peer_path, first_runtime, selector, value)
    second_socket: socket.socket | None = None
    if second_ready:
        second_socket = await _subscribe_peer(second_bus, second_peer_path)
        await _send_peer_write(second_bus, second_peer_path, _login_packet())
        _recv(second_socket)
        await _send_peer_write(second_bus, second_peer_path, b"\x02\x31\x08")
        assert _recv(second_socket) == b"\x01\x20"
        await hass.async_block_till_done()
        await asyncio.sleep(0)
        await hass.async_block_till_done()
        assert second_coordinator.controller._active_control_session is True
        assert tuple(_recv(second_socket) for _ in range(2)) == _expected_status_sync_frames(
            second_coordinator._pairlink_runtime
        )
    assert first_coordinator.controller.disconnected_transport_ready is True
    assert second_coordinator.controller.disconnected_transport_ready is second_ready

    first_device = _device_for_address(hass, _BED_ADDRESS)
    second_device = _device_for_address(hass, second_address)
    assert first_device is not None and second_device is not None
    expected_error = (
        "Pairlink comfort cannot preserve foot_position"
        if second_ready
        else "local Pairlink session is not ready"
    )
    with pytest.raises(Exception, match=expected_error):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_REVERIE_SET_COMFORT,
            {
                "device_id": [first_device.id, second_device.id],
                "comfort": {"head_position": 35},
            },
            blocking=True,
        )
    assert first_coordinator._command_scheduler.has_pending is False
    assert second_coordinator._command_scheduler.has_pending is False
    with pytest.raises(BlockingIOError):
        _recv(first_socket)
    if second_socket is not None:
        with pytest.raises(BlockingIOError):
            _recv(second_socket)

    first_socket.close()
    if second_socket is not None:
        second_socket.close()
    await async_unload_entry(hass, first_entry)
    await async_unload_entry(hass, second_entry)


async def test_all_target_pairlink_preflight_revalidates_and_dispatches_both_live_peers(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    pytest.importorskip("cryptography")
    del enable_custom_integrations
    first_source = "AA:BB:CC:DD:EE:FF"
    second_source = "AA:BB:CC:DD:EE:01"
    first_peer_address = _PEER_ADDRESS
    second_peer_address = "22:33:44:55:66:77"
    first_peer_path = _peer_path("hci3", first_peer_address)
    second_peer_path = _peer_path("hci4", second_peer_address)
    first_bus = FakeBlueZBus(
        managed_objects=_adapter_objects(
            "hci3",
            first_source,
            {
                first_peer_path: _device(
                    first_peer_address,
                    adapter_path="/org/bluez/hci3",
                )
            },
        )
    )
    second_bus = FakeBlueZBus(
        managed_objects=_adapter_objects(
            "hci4",
            second_source,
            {
                second_peer_path: _device(
                    second_peer_address,
                    adapter_path="/org/bluez/hci4",
                )
            },
        )
    )
    scanners = _scanners(((first_source, "hci3"), (second_source, "hci4")))
    first_entry = _entry(
        address=_BED_ADDRESS,
        title="First Pairlink",
        host_source=first_source,
    )
    second_bed_address = "00:10:20:30:40:51"
    second_entry = _entry(
        address=second_bed_address,
        title="Second Pairlink",
        host_source=second_source,
    )
    first_coordinator = await _local_setup(
        hass,
        monkeypatch,
        first_entry,
        first_bus,
        scanners=scanners,
    )
    second_coordinator = await _local_setup(
        hass,
        monkeypatch,
        second_entry,
        second_bus,
        scanners=scanners,
    )
    first_controller = first_coordinator.controller
    second_controller = second_coordinator.controller
    first_runtime = first_coordinator._pairlink_runtime
    second_runtime = second_coordinator._pairlink_runtime
    assert first_runtime is not None and second_runtime is not None
    first_socket = await _subscribe_peer(first_bus, first_peer_path)
    second_socket = await _subscribe_peer(second_bus, second_peer_path)
    await _send_peer_write(first_bus, first_peer_path, _login_packet(_PRIMARY_SESSION_KEY))
    _recv(first_socket)
    await _send_peer_write(first_bus, first_peer_path, b"\x02\x31\x08")
    assert _recv(first_socket) == b"\x01\x20"
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert first_controller._active_control_session is True
    assert tuple(_recv(first_socket) for _ in range(2)) == _expected_status_sync_frames(
        first_runtime
    )
    await _send_peer_write(
        second_bus,
        second_peer_path,
        _login_packet(_BACKUP_SESSION_KEY),
    )
    _recv(second_socket)
    await _send_peer_write(second_bus, second_peer_path, b"\x02\x31\x08")
    assert _recv(second_socket) == b"\x01\x20"
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    assert second_controller._active_control_session is True
    assert tuple(_recv(second_socket) for _ in range(2)) == _expected_status_sync_frames(
        second_runtime
    )
    assert first_controller.disconnected_transport_ready is True
    assert second_controller.disconnected_transport_ready is True

    first_device = _device_for_address(hass, _BED_ADDRESS)
    second_device = _device_for_address(hass, second_bed_address)
    assert first_device is not None and second_device is not None
    comfort = {
        "head_position": 35,
        "foot_position": 30,
        "lumbar_position": 40,
        "head_massage": 3,
        "foot_massage": 5,
        "timer_byte": 4,
        "mode": 2,
    }

    second_peer = second_runtime.peer_sessions[second_peer_address].identity
    assert second_peer is not None
    original_prepare = second_coordinator.async_prepare_command_operation

    async def prepare_then_stale(operation, **kwargs):
        handle = await original_prepare(operation, **kwargs)
        second_runtime.mark_peer_state_changed(second_peer)
        return handle

    with patch.object(
        second_coordinator,
        "async_prepare_command_operation",
        new=prepare_then_stale,
    ), pytest.raises(ServiceValidationError, match="state changed during preflight"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_REVERIE_SET_COMFORT,
            {
                "device_id": [first_device.id, second_device.id],
                "comfort": comfort,
            },
            blocking=True,
        )
    for peer_socket in (first_socket, second_socket):
        with pytest.raises(BlockingIOError):
            _recv(peer_socket)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_REVERIE_SET_COMFORT,
        {"device_id": [first_device.id, second_device.id], "comfort": comfort},
        blocking=True,
    )
    for runtime, peer_socket in (
        (first_runtime, first_socket),
        (second_runtime, second_socket),
    ):
        snapshot = runtime.prepare_send()
        expected = tuple(
            encrypt_user_frame(
                build_user_frame(
                    payload,
                    destination=PAIRLINK_BROADCAST_ADDRESS,
                    channel=32,
                    own_virtual_address=snapshot.own_virtual_address,
                ),
                event_key=snapshot.event_key,
                device_key=cast(bytes, snapshot.device_key),
            )
            for payload in comfort_payloads(
                values=comfort,
                current=None,
                force=False,
            )
        )
        assert tuple(_recv(peer_socket) for _ in expected) == expected

    alarm_values = {
        "head_position": 20,
        "foot_position": 30,
        "lumbar_position": 40,
        "head_massage": 0,
        "foot_massage": 5,
        "timer_byte": 4,
        "mode": 2,
    }
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
        {"device_id": [first_device.id, second_device.id], "comfort": alarm_values},
        blocking=True,
    )
    for runtime, peer_socket in (
        (first_runtime, first_socket),
        (second_runtime, second_socket),
    ):
        snapshot = runtime.prepare_send()
        expected = tuple(
            encrypt_user_frame(
                build_user_frame(
                    payload,
                    destination=PAIRLINK_BROADCAST_ADDRESS,
                    channel=32,
                    own_virtual_address=snapshot.own_virtual_address,
                ),
                event_key=snapshot.event_key,
                device_key=cast(bytes, snapshot.device_key),
            )
            for payload in comfort_payloads(values=alarm_values, current=None, force=True)
        )
        assert len(expected) == 8
        assert tuple(_recv(peer_socket) for _ in expected) == expected

    sign_event = (
        b"\x03"
        + PAIRLINK_BROADCAST_ADDRESS
        + b"\x12\x30"
        + bytes.fromhex(second_peer_address.replace(":", ""))[::-1]
        + b"\x00"
    )
    sign_frame = encrypt_user_frame(
        sign_event,
        event_key=second_runtime.current_event_key,
        device_key=_BACKUP_SESSION_KEY,
    )
    await _send_peer_write(second_bus, second_peer_path, sign_frame)
    await hass.async_block_till_done()
    assert second_runtime.sign_gate.device_signs[second_peer_address] == "0"
    assert second_runtime.sign_gate.sign_all is False
    for peer_socket in (first_socket, second_socket):
        with pytest.raises(BlockingIOError):
            _recv(peer_socket)

    with pytest.raises(ServiceValidationError, match="signing state"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_REVERIE_SET_COMFORT,
            {"device_id": [first_device.id, second_device.id], "comfort": comfort},
            blocking=True,
        )
    for peer_socket in (first_socket, second_socket):
        with pytest.raises(BlockingIOError):
            _recv(peer_socket)

    first_socket.close()
    second_socket.close()
    await async_unload_entry(hass, first_entry)
    await async_unload_entry(hass, second_entry)


async def test_local_profile_reservation_covers_adapter_aliases_before_bus_open(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    del enable_custom_integrations
    alias_source = _HOST_SOURCE.lower()
    scanners = _scanners(((_HOST_SOURCE, "hci3"), (alias_source, "hci3")))
    first_bus = FakeBlueZBus()
    first_entry = _entry()
    await _local_setup(
        hass,
        monkeypatch,
        first_entry,
        first_bus,
        scanners=scanners,
    )

    second_bus = FakeBlueZBus()
    second_entry = _entry(address="00:10:20:30:40:51", host_source=alias_source)
    from homeassistant.components import bluetooth

    from custom_components.adjustable_bed import (
        _async_setup_pairlink_local_entry,
        bluetooth_transport,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    monkeypatch.setattr(
        bluetooth,
        "async_current_scanners",
        lambda _hass: scanners,
    )
    monkeypatch.setattr(
        bluetooth_transport,
        "classify_scanner",
        lambda _scanner: bluetooth_transport.TransportClass.LOCAL,
    )
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", lambda: second_bus)
    second_coordinator = AdjustableBedCoordinator(hass, second_entry)
    with pytest.raises(ConfigEntryNotReady, match="already owns a Pairlink local profile"):
        await _async_setup_pairlink_local_entry(hass, second_entry, second_coordinator)

    assert second_bus.events == []
    assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {"hci3": first_entry.entry_id}
    await async_unload_entry(hass, first_entry)
    await first_entry._async_process_on_unload(hass)
    await second_coordinator.async_shutdown()
    assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {}


async def test_paired_local_children_start_distinct_selected_backends(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
) -> None:
    del enable_custom_integrations
    from homeassistant.components import bluetooth

    from custom_components.adjustable_bed import (
        _async_start_paired_pairlink_local_child,
        _preflight_paired_pairlink_local_roles,
    )
    from custom_components.adjustable_bed.beds import (
        reverie_pairlink_profile,
        reverie_pairlink_runtime,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    first_source = "AA:BB:CC:DD:EE:01"
    second_source = "AA:BB:CC:DD:EE:02"
    inventory = (
        transport.PairlinkHostAdapterInventoryEntry(first_source, "local", "hci3", True),
        transport.PairlinkHostAdapterInventoryEntry(second_source, "local", "hci4", True),
    )
    monkeypatch.setattr(
        reverie_pairlink_profile,
        "pairlink_host_adapter_inventory",
        lambda _hass: inventory,
    )
    generated_join_addresses = iter(
        (bytes.fromhex("010203040506"), bytes.fromhex("111213141516"))
    )
    monkeypatch.setattr(
        reverie_pairlink_profile,
        "generate_pairlink_local_join_bt_mac",
        lambda: next(generated_join_addresses),
    )
    first_entry = _entry(address="00:10:20:30:40:61", host_source=first_source)
    second_entry = _entry(address="00:10:20:30:40:62", host_source=second_source)
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)
    first_child = AdjustableBedCoordinator(hass, first_entry)
    second_child = AdjustableBedCoordinator(hass, second_entry)

    unload_callbacks: list[Callable[[], None]] = []
    parent = SimpleNamespace(
        entry_id="pairlink-pair-test",
        async_on_unload=unload_callbacks.append,
    )
    selected_inventory, roles, transfers = _preflight_paired_pairlink_local_roles(
        hass,
        parent,
        {"left": first_child, "right": second_child},
    )
    assert selected_inventory == inventory
    assert transfers == []
    assert [role[3] for role in roles] == ["hci3", "hci4"]

    entries_by_address = {
        first_entry.data["address"]: first_entry,
        second_entry.data["address"]: second_entry,
    }
    monkeypatch.setattr(
        bluetooth,
        "async_last_service_info",
        lambda _hass, address, **_kwargs: SimpleNamespace(
            manufacturer_data=_manufacturer_data(), name="R510L"
        )
        if address in entries_by_address
        else None,
    )
    started: list[tuple[str, str, object]] = []

    class FakePeripheralBackend:
        adapter_path: str | None = None

        async def async_start(self, *, host_adapter_source, adapter_inventory, profile,
                              on_peer_write, on_peer_lifecycle,
                              is_peripheral_role_active) -> None:
            del on_peer_write, on_peer_lifecycle, is_peripheral_role_active
            adapter = next(
                item.adapter for item in adapter_inventory
                if item.source == host_adapter_source
            )
            self.adapter_path = f"/org/bluez/{adapter}"
            started.append((host_adapter_source, adapter, profile))

        async def async_notify(self, _value: bytes) -> None:
            return None

        async def async_stop(self) -> None:
            return None

    monkeypatch.setattr(
        reverie_pairlink_runtime,
        "PairlinkPeripheralBackend",
        FakePeripheralBackend,
    )
    for side, child, source, _adapter, _owner in roles:
        await _async_start_paired_pairlink_local_child(
            hass,
            child,
            host_adapter_source=source,
            adapter_inventory=selected_inventory,
        )
        assert side in ("left", "right")
        assert child.controller is not None
        assert child.controller.requires_disconnected_transport is True
        assert child.controller._runtime.peripheral_backend is not None

    assert [(source, adapter) for source, adapter, _profile in started] == [
        (first_source, "hci3"),
        (second_source, "hci4"),
    ]
    assert first_child.controller._runtime is not second_child.controller._runtime
    assert first_child.controller._runtime.local_join_bt_mac != (
        second_child.controller._runtime.local_join_bt_mac
    )

    await first_child.async_shutdown()
    await second_child.async_shutdown()
    for callback in unload_callbacks:
        callback()
    assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {}

