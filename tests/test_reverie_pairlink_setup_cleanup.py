"""Failed pairing retires local servers without undoing registry commits."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components import adjustable_bed
from custom_components.adjustable_bed.beds import reverie_pairlink_transport as transport
from custom_components.adjustable_bed.const import DOMAIN
from tests.test_reverie_pairlink_lease_transfer import SOURCES, TrackedBus, fixture_pair
from tests.test_reverie_pairlink_production import (
    _adapter_objects,
    _login_packet,
    _recv,
    _send_peer_write,
    _send_state_selector,
    _subscribe_peer,
)
from tests.test_reverie_pairlink_transport import _device


@pytest.mark.parametrize("via_ha", [False, True])
@pytest.mark.parametrize("committed_side", [None, "left", "right"])
async def test_cancelled_registry_absorption_retires_failed_pair_only(
    hass, monkeypatch, enable_custom_integrations, via_ha, committed_side
):
    if via_ha:
        assert await async_setup_component(hass, DOMAIN, {})
    pair, originals, _, devices, rows, active, _, sockets = await fixture_pair(hass, monkeypatch)
    committed = {"left": 0, "right": 1}.get(committed_side)
    order = [0, 1, *(i for i in (1, 0) if i != committed)]
    created = []

    def new_bus():
        source, adapter = SOURCES[order[len(created)]]
        bus = TrackedBus(managed_objects=_adapter_objects(adapter, source, {}))
        created.append(bus)
        return bus

    monkeypatch.setattr(transport, "_new_dbus_fast_bus", new_bus)
    remove = hass.config_entries.async_remove
    reached_removal = asyncio.Event()
    release_removal = asyncio.Event()

    async def remove_until_cancelled(entry_id):
        index = next(
            i for i, original in enumerate(originals) if original.entry.entry_id == entry_id
        )
        if committed == 0 and index == 0:
            return await remove(entry_id)
        if committed == 1:
            if index == 0:
                raise RuntimeError("Keep the first original so the right-side commit is exercised")
            await remove(entry_id)
        reached_removal.set()
        await release_removal.wait()

    monkeypatch.setattr(hass.config_entries, "async_remove", remove_until_cancelled)
    setup = (
        hass.config_entries.async_setup(pair.entry_id)
        if via_ha
        else adjustable_bed.async_setup_entry(hass, pair)
    )
    task = asyncio.create_task(setup)
    try:
        async with asyncio.timeout(2):
            await reached_removal.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert pair.entry_id not in hass.data[DOMAIN]
        retained = {i for i in (0, 1) if i != committed}
        assert set(active) == {f"/org/bluez/{SOURCES[i][1]}" for i in retained}
        assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {
            SOURCES[i][1]: originals[i].entry.entry_id for i in retained
        }
        for index, original in enumerate(originals):
            expected_owner = pair.entry_id if index == committed else original.entry.entry_id
            assert (
                er.async_get(hass).async_get(rows[index].entity_id).config_entry_id
                == expected_owner
            )
            assert dr.async_get(hass).async_get(devices[index].id).config_entry_id == expected_owner
            assert (hass.config_entries.async_get_entry(original.entry.entry_id) is None) == (
                index == committed
            )
            if index in retained:
                restored = hass.data[DOMAIN][original.entry.entry_id]
                assert restored._pairlink_runtime.peripheral_backend.is_ready
                assert not restored._pairlink_runtime.joined
                assert restored._pairlink_runtime.peer_sessions == {}
                assert not restored.controller_state.get("back_position")
    finally:
        release_removal.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        leaked = hass.data[DOMAIN].pop(pair.entry_id, None)
        if leaked is not None:
            await leaked.async_shutdown()
        for original in originals:
            await original.async_shutdown()
        for sock in sockets:
            sock.close()


async def test_restoration_error_still_removes_pair_and_retires_replacement_backends(
    hass, monkeypatch, enable_custom_integrations
):
    pair, originals, _, _, _, active, _, sockets = await fixture_pair(hass, monkeypatch)
    created = []

    def new_bus():
        source, adapter = SOURCES[len(created)]
        bus = TrackedBus(managed_objects=_adapter_objects(adapter, source, {}))
        created.append(bus)
        return bus

    monkeypatch.setattr(transport, "_new_dbus_fast_bus", new_bus)
    monkeypatch.setattr(
        hass.config_entries, "async_remove", AsyncMock(side_effect=RuntimeError("Removal refused"))
    )
    monkeypatch.setattr(
        adjustable_bed,
        "_async_restore_pairlink_local_sources",
        AsyncMock(side_effect=RuntimeError("Original backend restoration failed")),
    )
    try:
        with pytest.raises(RuntimeError, match="Original backend restoration failed"):
            await adjustable_bed.async_setup_entry(hass, pair)
        assert pair.entry_id not in hass.data[DOMAIN]
        assert active == {}
        assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {}
        assert all(
            hass.config_entries.async_get_entry(x.entry.entry_id) is x.entry for x in originals
        )
    finally:
        leaked = hass.data[DOMAIN].pop(pair.entry_id, None)
        if leaked is not None:
            await leaked.async_shutdown()
        for original in originals:
            await original.async_shutdown()
        for sock in sockets:
            sock.close()


async def _restoration_tick():
    event = asyncio.Event()
    asyncio.get_running_loop().call_soon(event.set)
    await event.wait()


async def _authenticate_restored_source(original, bus, number):
    runtime = original._pairlink_runtime
    assert runtime is not None and runtime.peripheral_backend.is_ready
    assert not runtime.joined and runtime.peer_sessions == {}
    assert original.controller_state.get("back_position") is None
    path = f"/org/bluez/{SOURCES[number][1]}/dev_11_22_33_44_55_{66 + number}"
    bus.managed_objects[path] = _device(
        f"11:22:33:44:55:{66 + number}", adapter_path=f"/org/bluez/{SOURCES[number][1]}"
    )
    sock = await _subscribe_peer(bus, path)
    try:
        await _send_peer_write(bus, path, _login_packet(bytes.fromhex("aabbccdd")))
        _recv(sock)
        await _send_peer_write(bus, path, b"\x021\x08")
        _recv(sock)
        assert runtime.prepare_send().device_key == bytes.fromhex("aabbccdd")
        await _send_state_selector(bus, path, runtime, 1, 28, device_key=bytes.fromhex("aabbccdd"))
        assert original.controller_state["back_position"] == 28
    finally:
        sock.close()


@pytest.mark.parametrize("via_ha", [False, True])
@pytest.mark.parametrize("cancel_count", [1, 2])
async def test_restore_surviving_originals_under_cleanup_cancellation(
    hass, monkeypatch, enable_custom_integrations, via_ha, cancel_count
):
    if via_ha:
        assert await async_setup_component(hass, DOMAIN, {})
    pair, originals, _, devices, rows, active, trace, sockets = await fixture_pair(
        hass, monkeypatch
    )
    old = [x._pairlink_runtime for x in originals]
    created = []
    created_two = asyncio.Event()

    def new_bus():
        i = (0, 1, 1, 0)[len(created)]
        source, adapter = SOURCES[i]
        bus = TrackedBus(
            managed_objects=_adapter_objects(adapter, source, {}),
            block_at="unregister-advertisement" if len(created) == 1 else None,
        )
        created.append(bus)
        if len(created) == 2:
            created_two.set()
        return bus

    monkeypatch.setattr(transport, "_new_dbus_fast_bus", new_bus)

    async def refuse_remove(entry_id):
        raise RuntimeError("independent registry refusal before any commit")

    monkeypatch.setattr(hass.config_entries, "async_remove", refuse_remove)
    task = asyncio.create_task(
        hass.config_entries.async_setup(pair.entry_id)
        if via_ha
        else adjustable_bed.async_setup_entry(hass, pair)
    )
    try:
        async with asyncio.timeout(2):
            await created_two.wait()
            await created[1].operation_started.wait()
            assert pair.entry_id in hass.data[DOMAIN]
            for _ in range(cancel_count):
                task.cancel()
                await _restoration_tick()
                await _restoration_tick()
            assert not task.done()
            assert hass.data[DOMAIN]["_pairlink_local_profile_leases"]["hci4"].startswith(
                pair.entry_id + ":"
            )
            created[1].release_operation.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        snapshot = {
            "pair_present": pair.entry_id in hass.data[DOMAIN],
            "originals_present": [
                hass.config_entries.async_get_entry(x.entry.entry_id) is x.entry for x in originals
            ],
            "fresh_ready": [
                x._pairlink_runtime is not None
                and x._pairlink_runtime is not old[i]
                and (x._pairlink_runtime.peripheral_backend is not None)
                and x._pairlink_runtime.peripheral_backend.is_ready
                for i, x in enumerate(originals)
            ],
            "active": list(active),
            "leases": dict(hass.data[DOMAIN]["_pairlink_local_profile_leases"]),
            "trace": trace,
            "entity_owners": [
                er.async_get(hass).async_get(row.entity_id).config_entry_id for row in rows
            ],
            "device_owners": [
                dr.async_get(hass).async_get(device.id).config_entry_id for device in devices
            ],
            "original_entry_ids": [x.entry.entry_id for x in originals],
            "old_runtime_closed": [x.is_closed for x in old],
            "cancel_count": cancel_count,
            "via_ha": via_ha,
        }
        assert pair.entry_id not in hass.data[DOMAIN], snapshot
        assert snapshot["entity_owners"] == snapshot["original_entry_ids"], snapshot
        assert snapshot["device_owners"] == snapshot["original_entry_ids"], snapshot
        assert all(snapshot["old_runtime_closed"]), snapshot
        assert all(snapshot["fresh_ready"]), snapshot
        assert set(active) == {"/org/bluez/hci3", "/org/bluez/hci4"}, snapshot
        assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {
            SOURCES[i][1]: x.entry.entry_id for i, x in enumerate(originals)
        }, snapshot
        for i, x in enumerate(originals):
            assert (
                er.async_get(hass).async_get(rows[i].entity_id).config_entry_id == x.entry.entry_id
            )
            assert dr.async_get(hass).async_get(devices[i].id).config_entry_id == x.entry.entry_id
            assert er.async_get(hass).async_get(rows[i].entity_id).id == rows[i].id
            await _authenticate_restored_source(x, active[f"/org/bluez/{SOURCES[i][1]}"], i)
    finally:
        for bus in created:
            bus.release_operation.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        failed = hass.data[DOMAIN].pop(pair.entry_id, None)
        if failed is not None:
            await failed.async_shutdown()
        for x in originals:
            await x.async_shutdown()
        for sock in sockets:
            sock.close()
