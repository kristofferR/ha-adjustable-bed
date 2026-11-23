"""Production regressions for Reverie receive, shutdown and comfort ownership."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

import custom_components.adjustable_bed as integration
from custom_components.adjustable_bed import async_unload_entry
from custom_components.adjustable_bed.beds.reverie.pairlink_runtime import PairlinkRole
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services
from tests.test_reverie_pairlink_production import (
    _PEER_PATH,
    _device,
    _drain_socket,
    _entry,
    _local_setup,
    _login_packet,
    _peer_path,
    _recv,
    _send_peer_write,
    _subscribe_peer,
)
from tests.test_reverie_pairlink_sdk_wiring import (
    _composition,
    _decoded,
    _local_canonical,
    _message,
    _network,
    _notify,
    _ping,
    _ready,
)
from tests.test_reverie_pairlink_transport import FakeBlueZBus
from tests.test_reverie_session_lane import _central


async def test_central_ready_status_requests_source_ping_and_starts_rtt(monkeypatch):
    controller, client, runtime, tasks = await _ready()
    monkeypatch.setattr(controller, "_sdk_now_ms", lambda: 1000)
    await _notify(client, tasks, _network(2))
    assert client.writes.pop(0)[1] == b"\x01\x1a"
    assert _decoded(client, runtime) == [
        b"\x03" + bytes.fromhex("FFFFFFFF") + b"\xfe" + runtime.own_virtual_address
    ]
    assert controller._sdk_entry_state.started_ms == 1000
    monkeypatch.setattr(controller, "_sdk_now_ms", lambda: 1123)
    await _notify(client, tasks, _ping())
    assert controller._sdk_devices[0].rtt == 123


async def test_local_current_notification_starts_source_rtt(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, sock, _entry):
        runtime = controller._runtime
        assert runtime.role is PairlinkRole.PERIPHERAL
        snapshot = controller._capture_current_send_snapshot()
        monkeypatch.setattr(controller, "_sdk_now_ms", lambda: 2000)
        frame = b"\x03" + bytes.fromhex("FFFFFFFF") + b"\xfe" + runtime.own_virtual_address
        await controller._async_send_profile_frame(frame, snapshot)
        _recv(sock)
        assert controller._sdk_entry_state.started_ms == 2000
        monkeypatch.setattr(controller, "_sdk_now_ms", lambda: 2123)
        await _send_peer_write(bus, _PEER_PATH, _ping())
        assert any(bean is not None and bean.rtt == 123 for bean in controller._sdk_devices)


@pytest.mark.parametrize("new_peer", [False, True])
async def test_exit_fences_local_admission_and_backup_payload_before_status_save(
    hass, monkeypatch, enable_custom_integrations, new_peer
):
    monkeypatch.setattr(integration, "async_watch_profile_recommendations", AsyncMock())
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _sock, entry):
        runtime = controller._runtime
        address = "22:33:44:55:66:77"
        path = _peer_path("hci3", address)
        bus.managed_objects[path] = _device(address)
        socket = None
        if not new_peer:
            socket = await _subscribe_peer(bus, path)
        started, release = (asyncio.Event(), asyncio.Event())
        save = controller._sdk_metadata.save_status

        async def blocked_save():
            started.set()
            await release.wait()
            await save()

        monkeypatch.setattr(controller._sdk_metadata, "save_status", blocked_save)
        shutdown = asyncio.create_task(runtime.async_shutdown())
        try:
            await started.wait()
            assert not runtime.is_closed
            if new_peer:
                socket = await _subscribe_peer(bus, path)
                assert address not in runtime.peer_sessions
            else:
                await _send_peer_write(bus, path, b"\x01\x00" + bytes(4))
                assert runtime.peer_sessions[address].device_type is None
                with pytest.raises(BlockingIOError):
                    _recv(socket)
        finally:
            release.set()
            await shutdown
            if socket is not None:
                socket.close()


@pytest.mark.parametrize("rejoin", [False, True])
async def test_queued_nonprimary_write_cannot_resurrect_ended_identity(
    hass, monkeypatch, enable_custom_integrations, rejoin
):
    """Actual primary composition persistence delays an actual backup WriteValue."""
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _sock, _entry):
        runtime = controller._runtime
        address = "22:33:44:55:66:77"
        path = _peer_path("hci3", address)
        bus.managed_objects[path] = _device(address)
        old_socket = await _subscribe_peer(bus, path)
        sockets = [old_socket]
        old = runtime.peer_sessions[address].identity
        assert runtime.primary_mac != address
        epoch = runtime.epoch
        store = controller._sdk_io._store
        actual_save = store.async_save
        saving, release = (asyncio.Event(), asyncio.Event())

        async def blocked_save(snapshot):
            saving.set()
            await release.wait()
            await actual_save(snapshot)

        monkeypatch.setattr(store, "async_save", blocked_save)
        primary_task = asyncio.create_task(
            _send_peer_write(bus, _PEER_PATH, _message(1, data=_composition()))
        )
        await saving.wait()
        pending = asyncio.create_task(_send_peer_write(bus, path, bytes.fromhex("03FFFFFFFF20")))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not pending.done()
        assert len(controller._sdk_receive_lock._waiters) == 1
        try:
            bus.managed_objects[path] = _device(address, connected=False)
            assert bus.peer_disconnect_callback is not None
            bus.peer_disconnect_callback(path, False)
            assert runtime.epoch == epoch
            assert address not in runtime.peer_sessions
            current = None
            if rejoin:
                bus.managed_objects[path] = _device(address, connected=True)
                sockets.append(await _subscribe_peer(bus, path))
                current = runtime.peer_sessions[address].identity
                assert current.connection_generation > old.connection_generation
                assert runtime.peer_sessions[address].subscribed
            release.set()
            await asyncio.gather(primary_task, pending)
            actual = runtime.peer_sessions.get(address)
            receipt = {
                "old_generation": old.connection_generation,
                "new_generation": current.connection_generation if current else None,
                "after_pending_generation": actual.identity.connection_generation
                if actual
                else None,
                "after_pending_subscribed": actual.subscribed if actual else None,
                "entry_epoch_unchanged": epoch == runtime.epoch,
            }
            if current is None:
                assert actual is None, receipt
            else:
                assert actual.identity == current and actual.subscribed, receipt
        finally:
            release.set()
            await asyncio.gather(primary_task, pending, return_exceptions=True)
            for sock in sockets:
                sock.close()


async def test_primary_disconnect_epoch_fences_queued_write(
    hass, monkeypatch, enable_custom_integrations
):
    """Passing control: the same race is fenced when the disconnected peer is primary."""
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _sock, _entry):
        runtime = controller._runtime
        old_epoch = runtime.epoch
        async with controller._sdk_receive_lock:
            pending = asyncio.create_task(
                _send_peer_write(bus, _PEER_PATH, bytes.fromhex("03FFFFFFFF20"))
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            bus.managed_objects[_PEER_PATH] = _device(connected=False)
            assert bus.peer_disconnect_callback is not None
            bus.peer_disconnect_callback(_PEER_PATH, False)
            assert runtime.epoch != old_epoch
        await pending
        assert not runtime.peer_sessions


async def _real_p2_service(hass, monkeypatch):
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_reverie_session_lane import _central

    coordinator = await _central(hass)
    from homeassistant.config_entries import ConfigEntryState

    coordinator.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id, identifiers={(DOMAIN, coordinator.address)}
    )
    await async_register_services(hass)
    now = [0.0]
    monkeypatch.setattr(coordinator.controller, "_comfort_now", lambda: now[0])
    await coordinator.controller.start_notify()
    callback = coordinator.client.start_notify.await_args.args[1]

    async def submit(comfort):
        await hass.services.async_call(
            DOMAIN,
            "reverie_set_comfort",
            {"device_id": device.id, "comfort": comfort},
            blocking=True,
        )

    async def notify(t, head, foot, massage=0):
        now[0] = t
        callback(None, bytearray((0, 0, head, foot, massage, 0, 0, 0, 0)))
        await hass.async_block_till_done()

    return (coordinator, submit, notify)


async def test_p2_changed_sample_restarts_source_stability_delay(
    hass, monkeypatch, mock_coordinator_connected
):
    coordinator, submit, notify = await _real_p2_service(hass, monkeypatch)
    try:
        await submit({"head_position": 25, "foot_position": 40})
        writes = coordinator.client.write_gatt_char
        writes.reset_mock()
        await notify(0.0, 10, 20)
        await notify(0.001, 10, 20)
        assert [c.args[1].hex() for c in writes.await_args_list] == ["5551191d"]
        await notify(2.1, 11, 20)
        await notify(2.101, 11, 20)
        wire = [c.args[1].hex() for c in writes.await_args_list]
        assert wire == ["5551191d"]
    finally:
        await coordinator.async_shutdown()


async def test_p2_equal_head_does_not_delay_first_unequal_foot(
    hass, monkeypatch, mock_coordinator_connected
):
    coordinator, submit, notify = await _real_p2_service(hass, monkeypatch)
    try:
        await submit({"head_position": 25, "foot_position": 40})
        writes = coordinator.client.write_gatt_char
        writes.reset_mock()
        await notify(0.0, 25, 20)
        await notify(0.001, 25, 20)
        wire = [c.args[1].hex() for c in writes.await_args_list]
        assert wire == ["5552282f"]
    finally:
        await coordinator.async_shutdown()


async def test_p2_comfort_compares_source_raw_massage_feedback(
    hass, monkeypatch, mock_coordinator_connected
):
    coordinator, submit, notify = await _real_p2_service(hass, monkeypatch)
    try:
        await submit({"head_massage": 4})
        writes = coordinator.client.write_gatt_char
        writes.reset_mock()
        await notify(0.0, 0, 0, 4)
        await notify(0.001, 0, 0, 4)
        wire = [c.args[1].hex() for c in writes.await_args_list]
        assert wire == []
    finally:
        await coordinator.async_shutdown()


async def _public_route(hass, monkeypatch):
    coordinator = await _central(hass)
    coordinator.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id, identifiers={(DOMAIN, coordinator.address)}
    )
    await async_register_services(hass)
    clock = [0.0]
    monkeypatch.setattr(coordinator.controller, "_comfort_now", lambda: clock[0])
    await coordinator.controller.start_notify()
    callback = coordinator.client.start_notify.await_args.args[1]

    async def submit(comfort):
        await hass.services.async_call(
            DOMAIN,
            "reverie_set_comfort",
            {"device_id": device.id, "comfort": comfort},
            blocking=True,
        )

    def emit(at, *, head, foot=20, massage=0):
        clock[0] = at
        callback(None, bytearray((0, 0, head, foot, massage, 0, 0, 0, 0)))

    async def notify(at, *, head, foot=20, massage=0):
        emit(at, head=head, foot=foot, massage=massage)
        await hass.async_block_till_done()

    return (coordinator, clock, submit, notify, emit)


async def test_service_notify_route_loses_first_eligible_write_when_sample_changes_in_queue(
    hass, monkeypatch, mock_coordinator_connected
):
    coordinator, _clock, submit, notify, emit = await _public_route(hass, monkeypatch)
    try:
        await submit({"head_position": 25})
        writes = coordinator.client.write_gatt_char
        writes.reset_mock()
        async with coordinator._command_lock:
            emit(0.0, head=10)
            emit(0.001, head=10)
            await asyncio.sleep(0)
            emit(0.002, head=11)
            emit(2.003, head=11)
        await hass.async_block_till_done()
        assert [call.args[1].hex() for call in writes.await_args_list] == ["5551191d"]
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("stage", ["waiting_feedback", "queued", "remaining_field"])
async def test_public_stop_cancels_p2_comfort_without_notification_replay(
    hass, monkeypatch, mock_coordinator_connected, stage
):
    coordinator, _clock, submit, notify, emit = await _public_route(hass, monkeypatch)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id, identifiers={(DOMAIN, coordinator.address)}
    )

    async def stop():
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": device.id}, blocking=True
        )

    try:
        await submit({"head_position": 25, "foot_position": 40})
        writes = coordinator.client.write_gatt_char
        writes.reset_mock()
        if stage == "queued":
            async with coordinator._command_lock:
                emit(0.0, head=10)
                emit(0.001, head=10)
                await asyncio.sleep(0)
                stopping = asyncio.create_task(stop())
                await asyncio.sleep(0)
            await stopping
        else:
            if stage == "remaining_field":
                await notify(0.0, head=10)
                await notify(0.001, head=10)
                assert [call.args[1].hex() for call in writes.await_args_list] == ["5551191d"]
                writes.reset_mock()
            await stop()

        await notify(2.002, head=10)
        await notify(4.003, head=10)
        assert [call.args[1].hex() for call in writes.await_args_list] == ["55ffaa"]
        assert coordinator.controller._comfort_request is None
        assert not coordinator.controller._comfort_writes

        await submit({"head_position": 30})
        writes.reset_mock()
        await notify(4.1, head=10)
        await notify(4.101, head=10)
        assert [call.args[1].hex() for call in writes.await_args_list] == ["55511e1a"]
    finally:
        await coordinator.async_shutdown()


async def test_known_connection_observation_emits_status3_without_reinitializing(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _sock, _entry):
        runtime = controller._runtime
        statuses = []
        controller._sdk_status_delegate = statuses.append
        address = "22:33:44:55:66:77"
        path = _peer_path("hci3", address)
        bus.managed_objects[path] = _device(address)
        backup_socket = await _subscribe_peer(bus, path)
        try:
            backup = runtime.peer_sessions[address]
            identity = backup.identity
            key = backup.provisioning.local_private_key
            peer_generation = backup.state_generation
            entry_generation = runtime.state_generation
            assert statuses == []
            assert bus.peer_disconnect_callback is not None
            bus.peer_disconnect_callback(path, True)
            await hass.async_block_till_done()
            assert statuses == [3]
            assert runtime.peer_sessions[address] is backup
            assert backup.identity == identity and backup.subscribed
            assert backup.provisioning.local_private_key is key
            assert backup.state_generation == peer_generation
            assert runtime.state_generation == entry_generation
            await _send_peer_write(bus, path, bytes.fromhex("03FFFFFFFF20"))
            assert statuses == [3]
            runtime._mesh_callback_present = False
            bus.peer_disconnect_callback(path, True)
            await hass.async_block_till_done()
            assert statuses == [3]
            assert backup.provisioning.local_private_key is key
        finally:
            backup_socket.close()


async def test_stale_connected_observation_cannot_signal_rejoined_generation(
    hass, monkeypatch, enable_custom_integrations
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _sock, _entry):
        runtime = controller._runtime
        statuses = []
        controller._sdk_status_delegate = statuses.append
        address = "22:33:44:55:66:77"
        path = _peer_path("hci3", address)
        bus.managed_objects[path] = _device(address)
        first = await _subscribe_peer(bus, path)
        old = runtime.peer_sessions[address].identity
        assert bus.peer_disconnect_callback is not None
        bus.peer_disconnect_callback(path, True)
        bus.managed_objects[path] = _device(address, connected=False)
        bus.peer_disconnect_callback(path, False)
        bus.managed_objects[path] = _device(address)
        fresh = await _subscribe_peer(bus, path)
        try:
            current = runtime.peer_sessions[address]
            assert current.identity.connection_generation > old.connection_generation
            key = current.provisioning.local_private_key
            await hass.async_block_till_done()
            assert statuses == []
            assert runtime.peer_sessions[address] is current
            assert current.subscribed and current.provisioning.local_private_key is key
        finally:
            first.close()
            fresh.close()


@pytest.mark.parametrize("primary", [False, True])
async def test_connected_status_uses_source_backup_membership_after_welcome(
    hass, monkeypatch, enable_custom_integrations, primary
):
    async with _local_canonical(hass, monkeypatch) as (controller, bus, _sock, _entry):
        runtime = controller._runtime
        statuses = []
        controller._sdk_status_delegate = statuses.append
        address = runtime.primary_mac if primary else "22:33:44:55:66:77"
        assert address is not None
        path = _PEER_PATH if primary else _peer_path("hci3", address)
        extra = None
        if not primary:
            bus.managed_objects[path] = _device(address)
            extra = await _subscribe_peer(bus, path)
        try:
            session = runtime.peer_sessions[address]
            before = (
                session.identity,
                session.provisioning.local_private_key,
                session.state_generation,
                runtime.state_generation,
            )
            assert session.source_backup_member is not primary
            assert bus.peer_disconnect_callback is not None
            bus.peer_disconnect_callback(path, True)
            await hass.async_block_till_done()
            assert statuses == ([] if primary else [3])
            assert session.source_backup_member

            bus.peer_disconnect_callback(path, True)
            await hass.async_block_till_done()
            assert statuses == ([3] if primary else [3, 3])
            assert runtime.peer_sessions[address] is session
            assert before == (
                session.identity,
                session.provisioning.local_private_key,
                session.state_generation,
                runtime.state_generation,
            )
        finally:
            if extra is not None:
                extra.close()


@pytest.mark.asyncio
async def test_ha_unload_fences_peer_callbacks_before_persistence(
    hass, monkeypatch, enable_custom_integrations
):
    del enable_custom_integrations
    monkeypatch.setattr(integration, "async_watch_profile_recommendations", AsyncMock())
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    backend = runtime.peripheral_backend
    assert backend is not None and backend.is_ready
    primary = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet())
    assert _recv(primary).startswith(b"\x02\x19")
    await _send_peer_write(bus, _PEER_PATH, b"\x021\x08")
    assert _recv(primary) == b"\x01 "
    _drain_socket(primary)
    start_save, release_save = (asyncio.Event(), asyncio.Event())
    original_save = controller._sdk_metadata.save_status

    async def blocked_save():
        start_save.set()
        await release_save.wait()
        await original_save()

    monkeypatch.setattr(controller._sdk_metadata, "save_status", blocked_save)
    processed: list[bytes] = []
    process = runtime.process_transport_packet

    def observe_process(payload, *args, **kwargs):
        processed.append(payload)
        return process(payload, *args, **kwargs)

    monkeypatch.setattr(runtime, "process_transport_packet", observe_process)
    unload = asyncio.create_task(async_unload_entry(hass, entry))
    backup_address = "22:33:44:55:66:77"
    backup_path = _peer_path("hci3", backup_address)
    backup = None
    late_write = None
    try:
        await asyncio.wait_for(start_save.wait(), timeout=2)
        observed_exiting_before_save_release = runtime.is_exiting
        observed_backend_ready_during_save = backend.is_ready
        observed_runtime_open_during_save = not runtime.is_closed
        bus.managed_objects[backup_path] = _device(backup_address)
        backup = await _subscribe_peer(bus, backup_path)
        admitted_during_save = backup_address in runtime.peer_sessions
        provisioned_during_save = bool(
            runtime.peer_sessions.get(backup_address)
            and runtime.peer_sessions[backup_address].provisioning.initialized
        )
        payload = b"\x01\x00" + bytes(4)
        late_write = asyncio.create_task(_send_peer_write(bus, backup_path, payload))
        await asyncio.sleep(0)
        write_waited_behind_exit_lock = not late_write.done()
        release_save.set()
        await asyncio.wait_for(late_write, timeout=2)
        assert runtime.is_exiting or runtime.is_closed
    finally:
        release_save.set()
        await asyncio.wait_for(unload, timeout=3)
        primary.close()
        if backup is not None:
            backup.close()
    assert observed_exiting_before_save_release is True
    assert observed_backend_ready_during_save is True
    assert observed_runtime_open_during_save is True
    assert admitted_during_save is False
    assert provisioned_during_save is False
    assert write_waited_behind_exit_lock is False
    assert payload not in processed
    assert late_write is not None and late_write.done() and (late_write.exception() is None)
    assert runtime.is_closed and (not backend.is_ready)
    assert runtime.peer_sessions == {} and runtime.admitted_peer_count == 0
    assert bus.peer_notify_acquire_callback is None and (not bus.exports)
