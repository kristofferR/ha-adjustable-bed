"""Actual setup/registry/backend transfer probes, isolated from cover platform code."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import bluetooth
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    async_setup_entry,
    async_unload_entry,
    bluetooth_transport,
    pairing,
)
from custom_components.adjustable_bed.beds.reverie import pairlink_transport as transport
from custom_components.adjustable_bed.const import DOMAIN
from tests.test_reverie_pairlink_production import (
    _adapter_objects,
    _device_for_address,
    _entry,
    _local_setup,
    _login_packet,
    _manufacturer_data,
    _recv,
    _scanners,
    _send_peer_write,
    _subscribe_peer,
)
from tests.test_reverie_pairlink_transport import FakeBlueZBus, _device

SOURCES = (("AA:BB:CC:DD:EE:01", "hci3"), ("AA:BB:CC:DD:EE:02", "hci4"))


class TrackedBus(FakeBlueZBus):
    active = None
    events_all = None

    async def async_register_application(self, adapter_path, application_path):
        assert adapter_path not in self.active, "two local backend owners on one adapter"
        await super().async_register_application(adapter_path, application_path)
        self.active[adapter_path] = self
        self.events_all.append(("start", adapter_path))

    async def async_unregister_application(self, adapter_path, application_path):
        await super().async_unregister_application(adapter_path, application_path)
        if self.active.get(adapter_path) is self:
            self.active.pop(adapter_path)
        self.events_all.append(("stop", adapter_path))


async def fixture_pair(hass, monkeypatch, *, mixed=False, central_side=1, mode=None):
    active, trace = {}, []
    monkeypatch.setattr(TrackedBus, "active", active)
    monkeypatch.setattr(TrackedBus, "events_all", trace)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    monkeypatch.setattr("custom_components.adjustable_bed.async_watch_profile_recommendations", AsyncMock())
    originals, original_buses, sockets = [], [], []
    for i, (source, adapter) in enumerate(SOURCES):
        entry = _entry(address=f"00:10:20:30:40:{61+i}", host_source=source)
        bus = TrackedBus(managed_objects=_adapter_objects(
            adapter, source, {f"/org/bluez/{adapter}/dev_11_22_33_44_55_{66+i}":
                             _device(f"11:22:33:44:55:{66+i}", adapter_path=f"/org/bluez/{adapter}")},
        ))
        if mixed and i == central_side:
            # Mixed pair retains an existing central non-local child.
            entry = _entry(address=entry.data["address"], host_source=source, role="central")
            entry.add_to_hass(hass)
            from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
            coordinator = AdjustableBedCoordinator(hass, entry)
            await coordinator.async_prime_offline_controller()
            hass.data[DOMAIN][entry.entry_id] = coordinator
            from homeassistant.config_entries import ConfigEntryState
            entry.mock_state(hass, ConfigEntryState.LOADED)
        else:
            coordinator = await _local_setup(hass, monkeypatch, entry, bus, scanners=_scanners(SOURCES))
            path = f"/org/bluez/{adapter}/dev_11_22_33_44_55_{66+i}"
            sock = await _subscribe_peer(bus, path)
            await _send_peer_write(bus, path, _login_packet())
            _recv(sock)
            await _send_peer_write(bus, path, b"\x02\x31\x08")
            _recv(sock)
            from tests.test_reverie_pairlink_production import _drain_socket, _send_state_selector
            await _send_state_selector(bus, path, coordinator._pairlink_runtime, 1, 35)
            assert coordinator.controller_state["back_position"] == 35
            await hass.async_block_till_done()
            _drain_socket(sock)
            sockets.append(sock)
        originals.append(coordinator)
        original_buses.append(bus)
    entries = [original.entry for original in originals]
    devices = [_device_for_address(hass, entry.data["address"]) for entry in entries]
    if mixed:
        devices[central_side] = dr.async_get(hass).async_get_or_create(
            config_entry_id=entries[central_side].entry_id,
            identifiers={(DOMAIN, entries[central_side].data["address"])},
        )
    registry = er.async_get(hass)
    rows = [registry.async_get_or_create(
        "number", DOMAIN, f'{entry.data["address"]}_massage_wave_intensity',
        config_entry=entry, suggested_object_id=f"lease_side_{i}",
    ) for i, entry in enumerate(entries)]
    data = pairing.build_pair_entry_data(
        {**entries[0].data, **entries[0].options}, {**entries[1].data, **entries[1].options},
        name="Transferred pair", connection_mode=mode, left_origin=(entries[0].entry_id, entries[0].unique_id),
        right_origin=(entries[1].entry_id, entries[1].unique_id),
    )
    pair = MockConfigEntry(domain=DOMAIN, title="Transferred pair", unique_id=data["pair_id"], data=data)
    pair.add_to_hass(hass)
    monkeypatch.setattr(bluetooth, "async_current_scanners", lambda _: _scanners(SOURCES))
    monkeypatch.setattr(bluetooth_transport, "classify_scanner", lambda _: bluetooth_transport.TransportClass.LOCAL)
    monkeypatch.setattr(bluetooth, "async_last_service_info", lambda *a, **k: SimpleNamespace(
        name="R510L", manufacturer_data=_manufacturer_data(), service_uuids=(), service_data={},
    ))
    # This lane drives transfer explicitly, not real status/clock intervals.
    from tests.test_reverie_pairlink_production import _drain_socket
    for original in originals:
        controller = original.controller
        if controller is not None:
            controller._set_active_control_session(False)
            controller._cancel_clock_sync()
    await hass.async_block_till_done()
    for sock in sockets:
        _drain_socket(sock)
    return pair, originals, original_buses, devices, rows, active, trace, sockets


@pytest.mark.parametrize("mode", ["concurrent", "sequential"])
@pytest.mark.parametrize(("mixed", "central_side"), [(False, 1), (True, 1), (True, 0)])
async def test_trusted_absorbed_local_leases_transfer_and_preserve_side_ids(
    hass, monkeypatch, enable_custom_integrations, mixed, central_side, mode,
):
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch, mixed=mixed, central_side=central_side, mode=mode)
    old_runtimes = [original._pairlink_runtime for original in originals]
    new_buses = [TrackedBus(managed_objects=_adapter_objects(adapter, source, {})) for source, adapter in SOURCES]
    iterator = iter(bus for i, bus in enumerate(new_buses) if not mixed or i != central_side)
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", lambda: next(iterator))
    if mixed:
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
        async def connect_central(coordinator):
            assert coordinator.entry.data.get("pairlink_role") == "central"
            return True
        monkeypatch.setattr(AdjustableBedCoordinator, "async_connect", connect_central)
    await async_setup_entry(hass, pair)
    parent = hass.data[DOMAIN][pair.entry_id]
    for i, side in enumerate(("left", "right")):
        child = parent.children[side]
        assert child.address == originals[i].address
        assert dr.async_get(hass).async_get(devices[i].id).config_entry_id == pair.entry_id
        assert er.async_get(hass).async_get(rows[i].entity_id).id == rows[i].id
        assert er.async_get(hass).async_get(rows[i].entity_id).config_entry_id == pair.entry_id
        if mixed and i == central_side:
            assert child.entry.data["pairlink_role"] == "central"
            continue
        old = old_runtimes[i]
        assert old.is_closed and old.peer_sessions == {}
        current = child._pairlink_runtime
        assert current is not old and not current.joined and current.peer_sessions == {}
        assert current.disconnected_transport_ready is False
        assert current.peripheral_backend.is_ready
        assert "back_position" not in child.controller_state
        adapter = SOURCES[i][1]
        assert active[f"/org/bluez/{adapter}"] is new_buses[i]
        assert hass.data[DOMAIN]["_pairlink_local_profile_leases"][adapter] == f"{pair.entry_id}:{side}:{child.address}"
    for sock in sockets:
        assert _recv(sock) == b""
    await async_unload_entry(hass, pair)
    await pair._async_process_on_unload(hass)
    assert active == {}
    for sock in sockets:
        sock.close()


async def test_unrelated_lease_is_rejected_before_any_backend_or_registry_mutation(
    hass, monkeypatch, enable_custom_integrations,
):
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch)
    hass.data[DOMAIN]["_pairlink_local_profile_leases"]["hci4"] = "unrelated-entry"
    before = list(trace)
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, pair)
    assert trace == before
    assert hass.data[DOMAIN]["_pairlink_local_profile_leases"]["hci3"] == originals[0].entry.entry_id
    for i, original in enumerate(originals):
        assert not original._pairlink_runtime.is_closed
        assert er.async_get(hass).async_get(rows[i].entity_id).config_entry_id == original.entry.entry_id
        await original.async_shutdown()
    for sock in sockets:
        sock.close()


@pytest.mark.parametrize("failure", ["first_backend", "second_backend", "registry", "unloaded_registry", "cancel_second", "cancel_rollback"])
async def test_failed_takeover_restores_original_backends_and_leases_without_stale_sessions(
    hass, monkeypatch, enable_custom_integrations, failure,
):
    if failure == "unloaded_registry":
        # A loaded source has an already-set-up integration in a real HA host.
        # Seed that lifecycle before adding entries, so reloading one original
        # cannot bootstrap every synthetic fixture entry concurrently.
        from homeassistant.setup import async_setup_component
        assert await async_setup_component(hass, DOMAIN, {})
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch)
    old_runtimes = [original._pairlink_runtime for original in originals]
    old_controllers = [original.controller for original in originals]
    old_peers = [runtime.prepare_send().peer for runtime in old_runtimes]
    created = []
    reached_block = asyncio.Event()
    order = (0, 1, 0) if failure == "first_backend" else (0, 1, 1, 0)
    def new_bus():
        i = len(created)
        source, adapter = SOURCES[order[i]]
        failing_index = 0 if failure == "first_backend" else 1
        fail = failure in ("first_backend", "second_backend", "cancel_rollback") and i == failing_index
        block = (failure == "cancel_second" and i == 1) or (failure == "cancel_rollback" and i == 2)
        bus = TrackedBus(
            managed_objects=_adapter_objects(adapter, source, {}),
            fail_at="register-advertisement" if fail else None,
            block_at="register-advertisement" if block else None,
        )
        created.append(bus)
        if block:
            reached_block.set()
        return bus
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", new_bus)
    if failure in ("registry", "unloaded_registry"):
        async def remove_rejected(entry_id):
            if failure == "unloaded_registry":
                assert await hass.config_entries.async_unload(entry_id)
            raise RuntimeError("injected registry removal refusal")
        monkeypatch.setattr(hass.config_entries, "async_remove", remove_rejected)
    if failure.startswith("cancel"):
        task = asyncio.create_task(async_setup_entry(hass, pair))
        await asyncio.wait_for(reached_block.wait(), timeout=2)
        blocked = created[-1]
        await asyncio.wait_for(blocked.operation_started.wait(), timeout=2)
        task.cancel()
        if failure == "cancel_rollback":
            blocked.release_operation.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises((ConfigEntryNotReady, RuntimeError)):
            await async_setup_entry(hass, pair)
    for i, original in enumerate(originals):
        assert hass.config_entries.async_get_entry(original.entry.entry_id) is original.entry
        restored = hass.data[DOMAIN][original.entry.entry_id]
        if failure == "unloaded_registry":
            assert restored is not original and original._shutting_down
            originals[i] = restored
            original = restored
        else:
            assert restored is original
        current = original._pairlink_runtime
        assert current is not old_runtimes[i] and old_runtimes[i].is_closed
        assert current.peripheral_backend.is_ready
        assert current.peer_sessions == {} and not current.joined
        assert current.disconnected_transport_ready is False
        with pytest.raises(ConnectionError, match="closed"):
            await old_controllers[i]._async_handle_peripheral_peer_write(
                old_peers[i], b"\x02\x31\x08",
            )
        assert not original._pairing_transfer_active
        assert original.client is None and not original.is_connected
        assert not original.controller_state.get("back_position")
        assert hass.data[DOMAIN]["_pairlink_local_profile_leases"][SOURCES[i][1]] == original.entry.entry_id
        assert er.async_get(hass).async_get(rows[i].entity_id).config_entry_id == original.entry.entry_id
        assert dr.async_get(hass).async_get(devices[i].id).config_entry_id == original.entry.entry_id
    # A restored original can authenticate a new physical session and publish
    # only newly received state; the previous generation's head35 is absent.
    from tests.test_reverie_pairlink_production import _send_state_selector
    original = originals[0]
    bus = active["/org/bluez/hci3"]
    peer_path = "/org/bluez/hci3/dev_11_22_33_44_55_66"
    bus.managed_objects[peer_path] = _device("11:22:33:44:55:66", adapter_path="/org/bluez/hci3")
    fresh_socket = await _subscribe_peer(bus, peer_path)
    await _send_peer_write(bus, peer_path, _login_packet(bytes.fromhex("aabbccdd")))
    _recv(fresh_socket)
    await _send_peer_write(bus, peer_path, b"\x02\x31\x08")
    _recv(fresh_socket)
    assert original._pairlink_runtime.prepare_send().device_key == bytes.fromhex("aabbccdd")
    assert original.controller_state.get("back_position") is None
    await _send_state_selector(
        bus, peer_path, original._pairlink_runtime, 1, 28,
        device_key=bytes.fromhex("aabbccdd"),
    )
    assert original.controller_state["back_position"] == 28
    fresh_socket.close()
    for original in originals:
        await original.async_shutdown()
    assert active == {}
    for sock in sockets:
        sock.close()


@pytest.mark.parametrize("forgery", ["address", "origin_unique_id", "runtime_entry"])
async def test_absorbed_identity_must_match_the_trusted_entry_and_runtime_before_mutation(
    hass, monkeypatch, enable_custom_integrations, forgery,
):
    from copy import deepcopy
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch)
    if forgery == "runtime_entry":
        hass.data[DOMAIN][originals[0].entry.entry_id] = originals[1]
    else:
        data = deepcopy(dict(pair.data))
        left = data["pair_children"][0]
        if forgery == "address":
            left["absorbed_entry_id"] = originals[1].entry.entry_id
        else:
            left["origin_unique_id"] = "unrelated-unique-id"
        hass.config_entries.async_update_entry(pair, data=data)
    before = list(trace)
    leases = dict(hass.data[DOMAIN]["_pairlink_local_profile_leases"])
    with pytest.raises(ConfigEntryNotReady, match="Absorbed bed"):
        await async_setup_entry(hass, pair)
    assert trace == before
    assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == leases
    for original in originals:
        await original.async_shutdown()
    for sock in sockets:
        sock.close()


async def test_retired_local_entry_never_uses_central_fallback(
    hass, monkeypatch, enable_custom_integrations,
):
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch)
    original = originals[0]
    central = AsyncMock(side_effect=AssertionError("local role reached central connection"))
    monkeypatch.setattr(original, "_async_connect_attempts_locked", central)
    await original.async_release_for_pairing_transfer()
    with pytest.raises(ConnectionError, match="ownership is being transferred"):
        await original.async_execute_controller_command(lambda controller: controller.stop_all())
    original.finish_pairing_transfer()
    assert await original.async_connect() is False
    with pytest.raises(ConnectionError):
        await original.async_stop_command()
    central.assert_not_awaited()
    for original in originals:
        await original.async_shutdown()
    for sock in sockets:
        sock.close()


@pytest.mark.parametrize("retained_side", ["left", "right"])
async def test_partial_registry_refusal_restores_only_its_source_and_keeps_committed_side(
    hass, monkeypatch, enable_custom_integrations, retained_side,
):
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch)
    retained = 0 if retained_side == "left" else 1
    created = []
    def new_bus():
        index = (0, 1, retained)[len(created)]
        source, adapter = SOURCES[index]
        bus = TrackedBus(managed_objects=_adapter_objects(adapter, source, {}))
        created.append(bus)
        return bus
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", new_bus)
    real_remove = hass.config_entries.async_remove
    async def remove_one(entry_id):
        if entry_id == originals[retained].entry.entry_id:
            raise RuntimeError("injected one-side registry refusal")
        return await real_remove(entry_id)
    monkeypatch.setattr(hass.config_entries, "async_remove", remove_one)
    await async_setup_entry(hass, pair)
    parent = hass.data[DOMAIN][pair.entry_id]
    committed_side = "right" if retained_side == "left" else "left"
    assert set(parent.children) == {committed_side}
    retained_original = originals[retained]
    assert retained_original._pairlink_runtime.peripheral_backend.is_ready
    assert not retained_original._pairlink_runtime.joined
    assert retained_original.controller_state.get("back_position") is None
    assert er.async_get(hass).async_get(rows[retained].entity_id).config_entry_id == retained_original.entry.entry_id
    assert dr.async_get(hass).async_get(devices[retained].id).config_entry_id == retained_original.entry.entry_id
    committed = 1 - retained
    assert er.async_get(hass).async_get(rows[committed].entity_id).config_entry_id == pair.entry_id
    assert dr.async_get(hass).async_get(devices[committed].id).config_entry_id == pair.entry_id
    leases = hass.data[DOMAIN]["_pairlink_local_profile_leases"]
    assert leases[SOURCES[retained][1]] == retained_original.entry.entry_id
    await async_unload_entry(hass, pair)
    await pair._async_process_on_unload(hass)
    assert set(active) == {f"/org/bluez/{SOURCES[retained][1]}"}
    assert leases == {SOURCES[retained][1]: retained_original.entry.entry_id}
    await retained_original.async_shutdown()
    for sock in sockets:
        sock.close()


async def test_source_runtime_is_revalidated_under_transfer_locks(
    hass, monkeypatch, enable_custom_integrations,
):
    pair, originals, buses, devices, rows, active, trace, sockets = await fixture_pair(hass, monkeypatch)
    original = originals[0]
    captured = original._pairlink_runtime
    before = list(trace)
    original._pairlink_runtime = None
    try:
        with pytest.raises(ConnectionError, match="runtime changed before transfer"):
            await original.async_release_for_pairing_transfer(expected_pairlink_runtime=captured)
        assert trace == before
        assert captured.peripheral_backend.is_ready
        assert not original._pairing_transfer_active
    finally:
        original._pairlink_runtime = captured
        for source in originals:
            await source.async_shutdown()
        for sock in sockets:
            sock.close()
