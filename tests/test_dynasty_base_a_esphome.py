"""Exercise late replies through the installed ESPHome client and API matcher."""

import asyncio
from collections.abc import Buffer, Callable, Iterable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aioesphomeapi._frame_helper.plain_text import APIPlaintextFrameHelper
from aioesphomeapi.api_pb2 import BluetoothDeviceConnectionResponse, BluetoothGATTReadResponse
from aioesphomeapi.client import APIClient
from aioesphomeapi.connection import APIConnection, ConnectionParams, ConnectionState
from aioesphomeapi.zeroconf import ZeroconfManager
from bleak import BleakClient
from bleak.exc import BleakError
from bleak_esphome.backend.client import ESPHomeClient
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.ble_diagnostics import BLEDiagnosticRunner
from custom_components.adjustable_bed.profiles import dynasty_base_a as app
from custom_components.adjustable_bed.runtime_data import loaded_runtime
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_dynasty_base_a import ADDRESS, connected, entry, gatt, written


class _Transport(asyncio.Transport):
    def __init__(self) -> None:
        self.requests = 0
        self.on_request: Callable[[], None] | None = None

    def writelines(self, list_of_data: Iterable[Buffer]) -> None:
        self.requests += 1
        if self.on_request is not None:
            self.on_request()

    def is_closing(self) -> bool:
        return False


class _Proxy:
    """Real protobuf registration/matching/timeout; only socket I/O is replaced."""

    def __init__(self, *, backend_timeout: float = 30) -> None:
        self.address = int(ADDRESS.replace(":", ""), 16)
        self.handle = 4
        self.backend_timeout = backend_timeout
        params = ConnectionParams(
            ["unit-test"], 6053, None, "test", 20, ZeroconfManager(), None, None, None
        )
        self.connection = APIConnection(params, None, False, "test")
        self.connection._handshake_complete = True
        self.connection.is_connected = True
        self.connection.connection_state = ConnectionState.CONNECTED
        helper = APIPlaintextFrameHelper(self.connection, "test", "test")
        self.transport = _Transport()
        helper.connection_made(self.transport)
        self.connection._frame_helper = helper
        self.api = APIClient("unit-test", 6053)
        self.api._connection = self.connection
        self.backend = SimpleNamespace(
            _client=self.api,
            _address_as_int=self.address,
            _raise_if_not_connected=lambda: None,
            _description="test",
            _async_ble_device_disconnected=lambda: None,
        )

    async def read(self, char):
        return await ESPHomeClient.read_gatt_char(self.backend, char, timeout=self.backend_timeout)

    def reply(self, power: int, *, handle: int | None = None) -> None:
        response = BluetoothGATTReadResponse(
            address=self.address,
            handle=self.handle if handle is None else handle,
            data=bytes([0] * 10 + [power]),
        )
        self.connection.process_packet(74, response.SerializeToString())

    def disconnect(self) -> None:
        response = BluetoothDeviceConnectionResponse(address=self.address, connected=False, error=0)
        self.connection.process_packet(69, response.SerializeToString())

    def reply_soon(self, power: int) -> None:
        asyncio.get_running_loop().call_soon(self.reply, power)


async def test_installed_esphome_matcher_accepts_late_reply_after_waiter_cancellation():
    """Negative control: the dependency has no read-request generation identifier."""
    proxy = _Proxy()
    char = SimpleNamespace(handle=proxy.handle)
    old = asyncio.create_task(proxy.read(char))
    await asyncio.sleep(0)
    assert proxy.transport.requests == 1
    old.cancel()
    with pytest.raises(asyncio.CancelledError):
        await old
    newer = asyncio.create_task(proxy.read(char))
    await asyncio.sleep(0)
    assert proxy.transport.requests == 2
    proxy.reply(255)  # Old off snapshot now satisfies the newer request.
    assert (await newer)[10] == 255


async def test_native_power_waits_for_esphome_drain_and_discards_late_off_snapshot(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    proxy, client = _Proxy(), mock_bleak_client
    client.services, client.read_gatt_char.side_effect = gatt("p2"), proxy.read
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = loaded_runtime(hass, e.entry_id)
    registry = er.async_get(hass)

    async def press(key):
        entity = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_dynasty_base_a_{key}"
        )
        await hass.services.async_call("button", "press", {"entity_id": entity}, blocking=True)

    def answer():
        if proxy.transport.requests in (1, 2, 5):
            proxy.reply_soon(255)
        elif proxy.transport.requests == 4:
            proxy.reply_soon(0)

    proxy.transport.on_request = answer
    with virtual_clock():
        await press("foot_massage")  # A correlated off status establishes the initial cache.
        assert target.controller._massage_on is False
        client.write_gatt_char.reset_mock()
        await press("massage_power")  # Fresh off read; on write succeeds; read 3 exceeds budget.
        pending = target.controller._status_read
        assert pending is not None and not pending.task.done()
        assert target.controller._massage_on is None
        with raises_key("dynasty_base_a_status_required"):
            await press("massage_power")
        assert proxy.transport.requests == 3  # No second waiter can borrow the late reply.
        proxy.reply(255, handle=5)
        assert not pending.task.done()
        proxy.reply(255)  # Delayed off snapshot belongs only to the abandoned request.
        await pending.task
        assert target.controller._massage_on is None
        await press("massage_power")  # Read 4 is fresh on status, so choose the off word.
        assert written(client) == [app.frame("p2", 0x200000), app.frame("p2", 0x2000000)]
        assert proxy.transport.requests == 5
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_support_capture_does_not_compete_for_pending_proxy_status(
    hass, mock_coordinator_connected, mock_bleak_client
):
    proxy, client = _Proxy(), mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    client.read_gatt_char.side_effect = proxy.read
    with virtual_clock():
        await target.async_execute_controller_command(lambda c: c.action("foot_massage"))
        pending = ctrl._status_read
        assert pending is not None and not pending.task.done()
        assert proxy.transport.requests == 1

        runner = BLEDiagnosticRunner(hass, ADDRESS, coordinator=target, capture_duration=0)
        runner._client = client
        runner._using_coordinator_connection = True
        services = await runner._enumerate_services()
        status = services[0].characteristics[1]
        assert status.uuid == app.codec.TRANSPORTS["dynasty_p2"].notify_uuid
        assert status.properties == ["read"]
        assert status.read_error == "Skipped: reads are owned by the active controller"
        assert proxy.transport.requests == 1
        assert not pending.task.done()

        proxy.reply(255)  # Only the controller's discarded waiter receives this old off state.
        await pending.task
        assert ctrl._massage_on is None
        client.write_gatt_char.reset_mock()
        proxy.transport.on_request = lambda: proxy.reply_soon(
            0 if proxy.transport.requests == 2 else 255
        )
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
        assert written(client) == [app.frame("p2", 0x2000000)]
        assert proxy.transport.requests == 3
        assert ctrl._massage_on is False
    await target.async_shutdown()


@pytest.mark.parametrize("end", ["deadline", "cancel"])
async def test_native_movement_releases_while_esphome_waiter_stays_attached(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, end
):
    proxy, client = _Proxy(), mock_bleak_client
    client.services, client.read_gatt_char.side_effect = gatt("p2"), proxy.read
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = loaded_runtime(hass, e.entry_id)
    registry = er.async_get(hass)
    device = next(
        v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
    )
    events = []
    with virtual_clock() as clock:
        started = clock.now

        async def write(_char, payload, **_kwargs):
            events.append((clock.now - started, bytes(payload)))

        def answer():
            if proxy.transport.requests <= 3:
                proxy.reply_soon(255)
            elif end == "cancel":
                asyncio.get_running_loop().call_later(0.04, target.cancel_command.set)

        client.write_gatt_char.side_effect = write
        proxy.transport.on_request = answer
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {
                "device_id": device,
                "control": "head_up",
                "duration": 0.1,
            },
            blocking=True,
        )
        zero, move = app.frame("p2", 0), app.frame("p2", 1)
        assert [payload for _, payload in events] == [zero] * 3 + [move] + [zero] * 3
        assert events[4][0] == pytest.approx(0.1 if end == "deadline" else 0.04)
        assert proxy.transport.requests == 4
        pending = target.controller._status_read
        assert pending is not None and not pending.task.done()
        proxy.reply(255)
        await pending.task
        assert target.controller._massage_on is None
    client.write_gatt_char.side_effect = None
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("control", ["head_up", "flat"])
async def test_slow_esphome_replies_do_not_delay_held_refreshes(
    hass, mock_coordinator_connected, mock_bleak_client, control
):
    proxy, client = _Proxy(), mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    client.read_gatt_char.side_effect = proxy.read
    word = app.controls("p2", "40")[control]
    motion, zero = app.frame("p2", word), app.frame("p2", 0)
    last_write = zero
    events = []
    with virtual_clock() as clock:
        started = clock.now

        async def write(_char, payload, **_kwargs):
            nonlocal last_write
            last_write = bytes(payload)
            events.append((clock.now - started, last_write))

        def answer():
            if last_write == motion:
                asyncio.get_running_loop().call_later(0.25, proxy.reply, 255)
            else:
                proxy.reply_soon(255)

        client.write_gatt_char.side_effect = write
        proxy.transport.on_request = answer
        await target.async_execute_controller_command(lambda c: c.hold_control(control, 400))
        assert [t for t, p in events if p == motion] == pytest.approx([0, 0.1, 0.2, 0.3])
        if control == "head_up":
            assert [t for t, p in events if p == zero][-3:] == pytest.approx([0.4] * 3)
        assert proxy.transport.requests == (5 if control == "head_up" else 2)
        pending = ctrl._status_read
        assert pending is not None and not pending.task.done()
        assert ctrl._massage_on is None
        await pending.task
        assert ctrl._massage_on is None  # Late snapshot cannot become branch state.
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


async def test_esphome_backend_timeout_requires_new_connection_before_trusting_status(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = False
    with virtual_clock():
        proxy = _Proxy(backend_timeout=0.05)
        client.read_gatt_char.side_effect = proxy.read
        with raises_key("dynasty_base_a_reconnect_required"):
            await target.async_execute_controller_command(lambda c: c.action("massage_power"))
        client.write_gatt_char.assert_not_called()
        assert ctrl._massage_on is None
        assert ctrl._status_read is None
        assert proxy.transport.requests == 1
        with raises_key("dynasty_base_a_reconnect_required"):
            await target.async_execute_controller_command(lambda c: c.action("massage_power"))
        await ctrl.async_discover_capabilities()  # Same physical client is still untrusted.
        with raises_key("dynasty_base_a_reconnect_required"):
            await target.async_execute_controller_command(lambda c: c.action("massage_power"))
        assert proxy.transport.requests == 1
        proxy.reply(255)  # Orphaned response is ignored; this client cannot issue another read.
        proxy.disconnect()
        newer = MagicMock(spec=BleakClient)
        newer.is_connected, newer.services = True, gatt("p2")
        newer.write_gatt_char = AsyncMock()
        newer.read_gatt_char = AsyncMock(side_effect=proxy.read)
        target._client = newer
        await ctrl.async_discover_capabilities()
        proxy.transport.on_request = lambda: proxy.reply_soon(0)
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
        assert written(newer) == [app.frame("p2", 0x2000000)]
        assert proxy.transport.requests == 3  # Fresh preflight status and post-write status.
        target._client = client
    await target.async_shutdown()


async def test_esphome_disconnect_drains_retired_request_without_cancelling_waiter(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    with virtual_clock():
        proxy = _Proxy()
        client.read_gatt_char.side_effect = proxy.read
        await target.async_execute_controller_command(lambda c: c.action("foot_massage"))
        pending = ctrl._status_read
        assert pending is not None and not pending.task.done()
        ctrl.on_disconnect()
        assert not pending.task.done()
        proxy.disconnect()  # Actual backend connection-state matcher retires the request.
        with pytest.raises(BleakError):
            await pending.task
        assert ctrl._status_read is None
        assert ctrl._massage_on is None
        proxy.reply(255)
        assert ctrl._massage_on is None
    await target.async_shutdown()
