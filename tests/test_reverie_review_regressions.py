"""Production boundaries exposed by independent Reverie component review."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from dbus_fast import Variant
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    async_setup_entry,
    async_unload_entry,
    bluetooth_transport,
)
from custom_components.adjustable_bed.beds import reverie_pairlink_transport as transport
from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import decrypt_user_frame
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.reverie_services import (
    SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
)
from tests.test_reverie_pairlink import _controller, _join_central
from tests.test_reverie_pairlink_production import (
    _adapter_objects,
    _device_for_address,
    _drain_socket,
    _entry,
    _local_setup,
    _login_packet,
    _manufacturer_data,
    _recv,
    _scanners,
    _send_peer_write,
    _subscribe_peer,
)
from tests.test_reverie_pairlink_transport import _PEER_PATH, _SOURCE, FakeBlueZBus, _device

_KEY = bytes.fromhex("10203040")
_FULL_COMFORT = {
    "head_position": 20,
    "foot_position": 30,
    "lumbar_position": 40,
    "head_massage": 0,
    "foot_massage": 0,
    "timer_byte": 0,
    "mode": 0,
}
_SIX_COMFORT = {key: value for key, value in _FULL_COMFORT.items() if key != "lumbar_position"}


@pytest.mark.parametrize(
    ("key", "signature", "value"),
    [
        ("MinTxPower", "i", -20),
        ("MaxTxPower", "i", 10),
        ("MinTxPower", "u", 0),
        ("MaxTxPower", "q", 10),
        ("MinTxPower", "y", 0),
        ("MaxTxPower", "x", 10),
    ],
)
async def test_bluez_inventory_drops_optional_power_with_wrong_wire_type(
    monkeypatch, key, signature, value
):
    manager = "org.bluez.LEAdvertisingManager1"
    properties = {
        "CanSetTxPower": Variant("b", True),
        "MinTxPower": Variant("n", -20),
        "MaxTxPower": Variant("n", 10),
    }
    properties[key] = Variant(signature, value)
    wire = transport._DbusFastBlueZBus()
    monkeypatch.setattr(
        wire, "_call", AsyncMock(return_value=[{"/org/bluez/hci3": {manager: properties}}])
    )

    inventory = await wire.async_get_managed_objects()

    normalized = inventory["/org/bluez/hci3"][manager]
    assert key not in normalized
    assert normalized["CanSetTxPower"] is True
    other = "MaxTxPower" if key == "MinTxPower" else "MinTxPower"
    assert normalized[other] == properties[other].value


async def test_a7_setters_send_the_source_dashboard_envelope():
    controller, client, runtime, tasks = _controller()
    client.mtu_size = 64
    await _join_central(controller, client, runtime, tasks)
    client.writes.clear()
    try:
        await controller.set_light_level(100)
        await controller.set_light_color((0, 255, 128))
        assert [
            decrypt_user_frame(wire, event_key=runtime.current_event_key, device_key=_KEY)[10:]
            for _, wire, _ in client.writes
        ] == [bytes.fromhex(value) for value in ("01a71064", "01a71100", "01a712ff", "01a71380")]
    finally:
        await controller.stop_notify()


@asynccontextmanager
async def _ready_local(hass, monkeypatch, model):
    base = _entry()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=model,
        unique_id=base.unique_id,
        data={**base.data, "protocol_variant": model},
        options=dict(base.options),
    )
    advertisement = _manufacturer_data(bed_type=145 if model == "Harmoniq Upgrade" else 144)
    monkeypatch.setattr(
        bluetooth, "async_current_scanners", lambda _: _scanners(((_SOURCE, "hci3"),))
    )
    monkeypatch.setattr(
        bluetooth_transport, "classify_scanner", lambda _: bluetooth_transport.TransportClass.LOCAL
    )
    monkeypatch.setattr(
        bluetooth,
        "async_last_service_info",
        lambda *args, **kwargs: SimpleNamespace(
            address=entry.data["address"],
            name=model,
            manufacturer_data=advertisement,
            service_uuids=(),
            service_data={},
        ),
    )
    bus = FakeBlueZBus(managed_objects=_adapter_objects("hci3", _SOURCE, {_PEER_PATH: _device()}))
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", lambda: bus)
    entry.add_to_hass(hass)
    with patch.object(
        hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None)
    ):
        await async_setup_entry(hass, entry)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    sock = await _subscribe_peer(bus, _PEER_PATH)
    try:
        await _send_peer_write(bus, _PEER_PATH, _login_packet())
        _recv(sock)
        await _send_peer_write(bus, _PEER_PATH, bytes.fromhex("023108"))
        _recv(sock)
        await hass.async_block_till_done()
        await asyncio.sleep(0)
        await hass.async_block_till_done()
        _drain_socket(sock)
        yield entry, coordinator, sock
    finally:
        sock.close()
        await async_unload_entry(hass, entry)
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.mark.parametrize(
    ("model", "values", "expected_frames"),
    [("R510L", _FULL_COMFORT, 8), ("Harmoniq Upgrade", _SIX_COMFORT, 7)],
)
async def test_alarm_service_accepts_each_profiles_complete_fields(
    hass, monkeypatch, enable_custom_integrations, model, values, expected_frames
):
    async with _ready_local(hass, monkeypatch, model) as (entry, coordinator, sock):
        device = _device_for_address(hass, entry.data["address"])
        await hass.services.async_call(
            DOMAIN,
            SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
            {"device_id": device.id, "comfort": values},
            blocking=True,
        )
        packets = [_recv(sock) for _ in range(expected_frames)]
        assert all(packets)
        assert decrypt_user_frame(
            packets[-1], event_key=coordinator._pairlink_runtime.current_event_key, device_key=_KEY
        )[10:] == bytes.fromhex("01a71500")
        with pytest.raises(BlockingIOError):
            extra = _recv(sock)
            pytest.fail(f"Unexpected packet after comfort: {extra.hex()}")


@pytest.mark.parametrize(
    ("model", "values"), [("R510L", _SIX_COMFORT), ("Harmoniq Upgrade", _FULL_COMFORT)]
)
async def test_alarm_service_rejects_missing_or_unsupported_lumbar_without_writes(
    hass, monkeypatch, enable_custom_integrations, model, values
):
    async with _ready_local(hass, monkeypatch, model) as (entry, _, sock):
        device = _device_for_address(hass, entry.data["address"])
        with pytest.raises(ServiceValidationError, match="lumbar|every supported value"):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_REVERIE_PAIRLINK_ALARM_COMFORT,
                {"device_id": device.id, "comfort": values},
                blocking=True,
            )
        with pytest.raises(BlockingIOError):
            _recv(sock)


async def test_ready_local_number_uses_local_transport_without_connecting_a_central(
    hass, monkeypatch, enable_custom_integrations
):
    async with _ready_local(hass, monkeypatch, "R510L") as (_, coordinator, sock):
        central_connect = AsyncMock(return_value=False)
        monkeypatch.setattr(coordinator, "async_ensure_connected", central_connect)
        monkeypatch.setattr(coordinator, "_async_read_seek_position", AsyncMock(return_value=None))
        number = next(
            entity
            for entity in _number_entities_for(hass, coordinator)
            if entity.entity_description.key == "back_position"
        )
        await number.async_set_native_value(35)
        central_connect.assert_not_awaited()
        assert decrypt_user_frame(
            _recv(sock), event_key=coordinator._pairlink_runtime.current_event_key, device_key=_KEY
        )[10:] == bytes.fromhex("01012300")


async def test_replaced_backup_check_cannot_send_after_acquire_notify_contention(
    hass, monkeypatch, enable_custom_integrations
):
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    timers = []
    sockets = []
    original_later = hass.loop.call_later

    @dataclass
    class Timer:
        delay: float
        callback: Callable[..., None]
        args: tuple[object, ...]

        def cancel(self):
            pass

        def fire(self):
            self.callback(*self.args)

    def later(delay, callback, *args, context=None):
        if getattr(callback, "__self__", None) is controller:
            timer = Timer(delay, callback, args)
            timers.append(timer)
            return timer
        return original_later(delay, callback, *args, context=context)

    monkeypatch.setattr(hass.loop, "call_later", later)
    release_inventory = asyncio.Event()
    acquire = welcome = None
    try:
        primary = await _subscribe_peer(bus, _PEER_PATH)
        sockets.append(primary)
        await _send_peer_write(bus, _PEER_PATH, _login_packet())
        _recv(primary)
        await _send_peer_write(bus, _PEER_PATH, bytes.fromhex("023108"))
        assert _recv(primary) == bytes.fromhex("0120")
        address = "22:33:44:55:66:77"
        path = "/org/bluez/hci3/dev_" + address.replace(":", "_")
        bus.managed_objects[path] = _device(address)
        backup = await _subscribe_peer(bus, path)
        sockets.append(backup)
        original_inventory = bus.async_get_managed_objects
        inventory_entered = asyncio.Event()
        calls = 0

        async def inventory():
            nonlocal calls
            calls += 1
            if calls == 1:
                inventory_entered.set()
                await release_inventory.wait()
            return await original_inventory()

        monkeypatch.setattr(bus, "async_get_managed_objects", inventory)
        third_address = "33:44:55:66:77:88"
        third_path = "/org/bluez/hci3/dev_" + third_address.replace(":", "_")
        bus.managed_objects[third_path] = _device(third_address)
        acquire = asyncio.create_task(_subscribe_peer(bus, third_path))
        async with asyncio.timeout(2):
            await inventory_entered.wait()
            next(t for t in timers if t.callback.__name__ == "_enqueue_backup_check").fire()
            await asyncio.sleep(0)
            welcome = asyncio.create_task(_send_peer_write(bus, path, bytes.fromhex("023108")))
            await asyncio.sleep(0)
            assert controller._runtime.primary_mac == address
            release_inventory.set()
            sockets.append(await acquire)
            await welcome
            await hass.async_block_till_done()
        assert _recv(backup) == bytes.fromhex("0120")
        with pytest.raises(BlockingIOError):
            _recv(backup)
    finally:
        release_inventory.set()
        for task in (acquire, welcome):
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        for sock in sockets:
            sock.close()
        await async_unload_entry(hass, entry)
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
