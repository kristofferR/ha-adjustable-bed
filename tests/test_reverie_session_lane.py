"""Independent production-path probes for the resumed session/routine lane."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.reverie import ReverieController
from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie_nightstand import ReverieNightstandController
from custom_components.adjustable_bed.const import (
    BED_TYPE_REVERIE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


async def _central(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Session lane",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_REVERIE,
            CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    return coordinator


@pytest.mark.parametrize("retain_old", [False, True])
@pytest.mark.parametrize("stop", [False, True])
async def test_central_reconnect_dispatches_only_current_controller(
    hass, mock_coordinator_connected, monkeypatch, retain_old, stop,
):
    coordinator = await _central(hass)
    old = coordinator.controller
    fresh = ReverieController(coordinator, model="9T")
    old_call = AsyncMock()
    fresh_call = AsyncMock()
    monkeypatch.setattr(old, "stop_all", old_call)
    monkeypatch.setattr(fresh, "stop_all", fresh_call)
    coordinator._controller = old if retain_old else None

    async def reconnect(**kwargs):
        coordinator._controller = fresh
        return True

    ensure = AsyncMock(side_effect=reconnect)
    monkeypatch.setattr(coordinator, "async_ensure_connected", ensure)
    if stop:
        await coordinator.async_stop_command()
    else:
        await coordinator.async_execute_controller_command(
            lambda controller: controller.stop_all(), read_positions_after_operation=False,
        )
    ensure.assert_awaited_once()
    fresh_call.assert_awaited_once()
    old_call.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("equal_after_wait", [False, True])
async def test_p2_queued_sample_is_revalidated_inside_real_command_lane(
    hass, mock_coordinator_connected, monkeypatch, equal_after_wait,
):
    coordinator = await _central(hass)
    controller = coordinator.controller
    now = 0.0
    monkeypatch.setattr(controller, "_comfort_now", lambda: now)
    writes = coordinator.client.write_gatt_char
    await coordinator.async_execute_controller_command(
        lambda current: current.async_set_comfort(
            ReverieComfortRequest(head_position=25)
        ), read_positions_after_operation=False,
    )
    count = writes.call_count
    sample = bytearray((0, 0, 10, 0, 0, 0, 0, 0, 0))
    # Hold the real wire lane, so the eligible callback queues through the
    # production scheduler, then deliver newer feedback before it is admitted.
    async with coordinator._command_lock:
        controller._parse_position_data(sample)
        now = 0.001
        controller._parse_position_data(sample)
        await asyncio.sleep(0)
        newer = bytearray((0, 0, 25 if equal_after_wait else 11, 0, 0, 0, 0, 0, 0))
        controller._parse_position_data(newer)
    await hass.async_block_till_done()
    assert writes.call_count == count
    assert len(controller._comfort_writes) == 1
    # Only a fresh unchanged callback can consume the outstanding field.
    now = 2.002
    controller._parse_position_data(newer)
    await hass.async_block_till_done()
    assert writes.call_count == count + (0 if equal_after_wait else 1)
    assert controller._comfort_request is None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("model", ["9T", "R510L"])
@pytest.mark.parametrize("exit_kind", ["complete", "cancel", "replace", "disconnect", "failure"])
async def test_routine_connection_owner_releases_on_every_exit(
    hass, mock_coordinator_connected, monkeypatch, model, exit_kind,
):
    coordinator = await _central(hass)
    if model == "9T":
        controller = coordinator.controller
        request = ReverieComfortRequest(25, 40, None, 0, 0)
    else:
        controller = ReverieNightstandController(coordinator, model=model)
        coordinator._controller = controller
        request = ReverieComfortRequest(25, 40, 0, 0, 0)
    await coordinator.async_execute_controller_command(
        lambda current: current.async_start_routine([(request, 1), (request, 1)]),
        read_positions_after_operation=False,
    )
    async def settle_comfort():
        if model == "9T":
            clock = iter((0.0, 0.001))
            monkeypatch.setattr(controller, "_comfort_now", lambda: next(clock))
            sample = bytearray((0, 0, 25, 40, 0, 0, 0, 0, 0))
            controller._parse_position_data(sample)
            controller._parse_position_data(sample)
            await hass.async_block_till_done()

    await settle_comfort()
    assert coordinator._command_connection_holds == 1
    assert coordinator._disconnect_timer is None
    timer = controller._routine_timer
    assert timer is not None
    if exit_kind == "complete":
        # Fire the production timer callback through scheduler ownership.
        timer.cancel()
        controller._enqueue_routine_step(controller._routine_generation)
        await hass.async_block_till_done()
        await settle_comfort()
        assert coordinator._command_connection_holds == 1
        controller._routine_timer.cancel()
        controller._enqueue_routine_step(controller._routine_generation)
        await hass.async_block_till_done()
    elif exit_kind == "cancel":
        controller._cancel_routine()
    elif exit_kind == "replace":
        await coordinator.async_execute_controller_command(
            lambda current: current.async_start_routine([]),
            read_positions_after_operation=False,
        )
    elif exit_kind == "disconnect":
        await coordinator.async_disconnect(reason="lane explicit teardown")
    else:
        # Failure in a later real scheduled write must clear pending ownership.
        async def failed(*args, **kwargs):
            raise ConnectionError("injected write failure")
        method = "_apply_composer_values" if model == "9T" else "_write_routine_comfort"
        monkeypatch.setattr(controller, method, failed)
        timer.cancel()
        with pytest.raises(ConnectionError, match="injected write failure"):
            await coordinator.async_execute_controller_command(
                lambda current: current._run_routine_step(current._routine_generation),
                read_positions_after_operation=False,
            )
    assert coordinator._command_connection_holds == 0
    assert controller._routine_timer is None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("mode", ["concurrent", "sequential"])
async def test_paired_local_setup_keeps_both_backends_without_a_peer(
    hass, monkeypatch, enable_custom_integrations, mode,
):
    from types import SimpleNamespace

    from homeassistant.components import bluetooth

    from custom_components.adjustable_bed import (
        async_setup_entry,
        async_unload_entry,
        bluetooth_transport,
        pairing,
    )
    from custom_components.adjustable_bed.beds import reverie_pairlink_transport as transport
    from tests.test_reverie_pairlink_production import (
        _adapter_objects,
        _entry,
        _manufacturer_data,
        _scanners,
    )
    from tests.test_reverie_pairlink_transport import FakeBlueZBus

    sources = (("AA:BB:CC:DD:EE:01", "hci3"), ("AA:BB:CC:DD:EE:02", "hci4"))
    entries = [
        _entry(address=f"00:10:20:30:40:{61+i}", host_source=source)
        for i, (source, adapter) in enumerate(sources)
    ]
    data = pairing.build_pair_entry_data(
        {**entries[0].data, **entries[0].options},
        {**entries[1].data, **entries[1].options},
        name="Pairlink local pair", connection_mode=mode,
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Local pair", unique_id=data["pair_id"], data=data)
    entry.add_to_hass(hass)
    buses = [
        FakeBlueZBus(managed_objects=_adapter_objects(adapter, source, {}))
        for source, adapter in sources
    ]
    iterator = iter(buses)
    stopped = []
    original_stop = transport.PairlinkPeripheralBackend.async_stop

    async def record_stop(backend):
        if backend.adapter_path is not None:
            stopped.append(backend.adapter_path)
        await original_stop(backend)

    monkeypatch.setattr(transport.PairlinkPeripheralBackend, "async_stop", record_stop)
    monkeypatch.setattr(transport, "_new_dbus_fast_bus", lambda: next(iterator))
    monkeypatch.setattr(bluetooth, "async_current_scanners", lambda _hass: _scanners(sources))
    monkeypatch.setattr(bluetooth_transport, "classify_scanner", lambda _: bluetooth_transport.TransportClass.LOCAL)
    monkeypatch.setattr(bluetooth, "async_last_service_info", lambda *args, **kwargs: SimpleNamespace(
        name="R510L", manufacturer_data=_manufacturer_data(), service_uuids=(), service_data={},
    ))
    monkeypatch.setattr("custom_components.adjustable_bed.async_watch_profile_recommendations", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    assert await async_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert len(coordinator.children) == 2
    for child in coordinator.children.values():
        assert child.client is None
        runtime = child._pairlink_runtime
        assert runtime is not None and runtime.peripheral_backend.is_ready
        assert child.controller.disconnected_transport_ready is False
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    assert await async_unload_entry(hass, entry)
    await entry._async_process_on_unload(hass)
    assert hass.data[DOMAIN]["_pairlink_local_profile_leases"] == {}
    assert stopped == ["/org/bluez/hci4", "/org/bluez/hci3"]


@pytest.mark.parametrize("variant", [None, "auto", "Other"])
async def test_nightstand_actual_factory_preserves_only_legacy_default_lumbar(
    hass, mock_coordinator_connected, variant,
):
    from custom_components.adjustable_bed.const import BED_TYPE_REVERIE_NIGHTSTAND
    entry = MockConfigEntry(
        domain=DOMAIN, title="Legacy Nightstand",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FE", CONF_BED_TYPE: BED_TYPE_REVERIE_NIGHTSTAND,
            CONF_MOTOR_COUNT: 3, CONF_HAS_MASSAGE: True, CONF_DISABLE_ANGLE_SENSING: False,
            **({"protocol_variant": variant} if variant is not None else {}),
        }, unique_id="AA:BB:CC:DD:EE:FE",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    assert coordinator.controller.has_lumbar_support is (variant != "Other")
    await coordinator.async_shutdown()


async def test_legacy_wave_registry_id_survives_actual_platform_setup(
    hass, mock_coordinator_connected, enable_custom_integrations,
):
    from homeassistant.helpers import entity_registry as er
    entry = MockConfigEntry(
        domain=DOMAIN, title="Legacy Reverie",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FD", CONF_BED_TYPE: BED_TYPE_REVERIE,
            CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: True, CONF_DISABLE_ANGLE_SENSING: False,
        }, unique_id="AA:BB:CC:DD:EE:FD",
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    original = registry.async_get_or_create(
        "number", DOMAIN, "AA:BB:CC:DD:EE:FD_massage_wave_intensity",
        config_entry=entry, suggested_object_id="my_existing_wave_automation",
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    current = registry.async_get(original.entity_id)
    assert current is not None and current.id == original.id
    assert current.unique_id == original.unique_id
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert hass.states.get(original.entity_id) is not None
    await hass.services.async_call(
        "number", "set_value", {"entity_id": original.entity_id, "value": 1}, blocking=True,
    )
    assert coordinator.client.write_gatt_char.call_args.args[1] == bytes.fromhex("554114")
    await hass.async_block_till_done()
    assert float(hass.states.get(original.entity_id).state) == 1
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(("level", "wire"), [
    (0, "554015"), (1, "554114"), (9, "55491c"), (10, "55410445"),
])
async def test_legacy_wave_exposed_domain_uses_source_decimal_text(
    hass, mock_coordinator_connected, level, wire,
):
    coordinator = await _central(hass)
    await coordinator.async_execute_controller_command(
        lambda current: current.set_massage_intensity("wave", level),
        read_positions_after_operation=False,
    )
    assert coordinator.client.write_gatt_char.call_args.args[1] == bytes.fromhex(wire)
    await coordinator.async_shutdown()


@pytest.mark.parametrize(("side", "wire"), [
    ("1", "0019283608040400000000"),
    ("2", "0011281e08040400000000"),
])
async def test_stk_routine_preserves_distinct_source_read_axes(
    hass, mock_coordinator_connected, side, wire,
):
    from custom_components.adjustable_bed.const import (
        BED_TYPE_REVERIE_NIGHTSTAND,
        REVERIE_NIGHTSTAND_FOOT_POSITION_UUID,
        REVERIE_NIGHTSTAND_HEAD_POSITION_UUID,
        REVERIE_NIGHTSTAND_LUMBAR_UUID,
    )
    entry = MockConfigEntry(
        domain=DOMAIN, title="STK source read",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FC", CONF_BED_TYPE: BED_TYPE_REVERIE_NIGHTSTAND,
            CONF_MOTOR_COUNT: 3, CONF_HAS_MASSAGE: True, CONF_DISABLE_ANGLE_SENSING: False,
            "protocol_variant": "STK",
        }, unique_id="AA:BB:CC:DD:EE:FC",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_connect()
    values = {
        REVERIE_NIGHTSTAND_HEAD_POSITION_UUID: bytes((17,)),
        REVERIE_NIGHTSTAND_FOOT_POSITION_UUID: bytes((33,)),
        REVERIE_NIGHTSTAND_LUMBAR_UUID: bytes((54,)),
    }
    coordinator.client.read_gatt_char = AsyncMock(side_effect=lambda uuid: values[uuid])
    await coordinator.controller.read_positions()
    assert coordinator.controller_state["reverie_stk_head_position"] == 17
    assert coordinator.controller_state["reverie_stk_head2_position"] == 54
    coordinator.controller._set_stk_side(side)
    request = ReverieComfortRequest(25, 40, 30, 1, 2)
    coordinator.client.write_gatt_char.reset_mock()
    await coordinator.async_execute_controller_command(
        lambda current: current.async_set_comfort(request), read_positions_after_operation=False,
    )
    coordinator.client.write_gatt_char.assert_not_awaited()
    await coordinator.async_execute_controller_command(
        lambda current: current.async_start_routine([(request, 1)]), read_positions_after_operation=False,
    )
    assert coordinator.client.write_gatt_char.call_args.args[1] == bytes.fromhex(wire)
    await coordinator.async_shutdown()
    assert coordinator._command_connection_holds == 0


async def test_a8_a9_actual_join_timer_rearm_and_stale_unload():
    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
        decrypt_user_frame,
        status_sync_payloads,
    )
    from tests.test_reverie_pairlink import _controller, _join_central
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    loop = controller._coordinator.hass.loop
    active = controller._status_sync_timer
    clock = controller._clock_sync_timer
    assert active.delay == 0
    assert clock.delay == 5
    client.writes.clear()
    active.fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    assert len(client.writes) == 2
    plain = [
        decrypt_user_frame(value, event_key=runtime.current_event_key,
                           device_key=bytes.fromhex("10203040"))[-4:]
        for _, value, _ in client.writes
    ]
    assert plain == list(status_sync_payloads())
    next_tick = controller._status_sync_timer
    assert next_tick.delay == 1
    assert controller._clock_sync_timer is clock
    assert len([call for call in loop.calls if call.delay == 5]) == 1
    await controller.stop_notify()
    controller.on_disconnect()
    assert next_tick.cancelled and clock.cancelled
    before = len(client.writes)
    # Even direct delivery of an already-dispatched stale callback is harmless.
    next_tick.callback(*next_tick.args)
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    assert len(client.writes) == before


@pytest.mark.parametrize("failure", [False, True])
async def test_p2_current_notification_write_failure_or_replacement_keeps_ownership(
    hass, mock_coordinator_connected, monkeypatch, failure,
):
    coordinator = await _central(hass)
    controller = coordinator.controller
    await controller.async_set_comfort(ReverieComfortRequest(head_position=25))
    monkeypatch.setattr(controller, "_comfort_now", lambda: 0.0)
    sample = bytes((0, 0, 10, 0, 0, 0, 0, 0, 0))
    controller._comfort_sample = sample
    controller._comfort_sample_stable = True
    controller._comfort_pending_sample = sample
    controller._comfort_advance_queued = True
    count = coordinator.client.write_gatt_char.call_count
    sequence = controller._comfort_sequence
    if failure:
        coordinator.client.write_gatt_char.side_effect = ConnectionError("production write failure")
        with pytest.raises(ConnectionError, match="production write failure"):
            await controller._run_comfort_write(sequence, sample)
        assert controller._comfort_request is None
    else:
        coordinator._controller = ReverieController(coordinator, model="9T")
        await controller._run_comfort_write(sequence, sample)
        assert not controller._comfort_writes
        assert coordinator._command_connection_holds == 0
        assert controller._comfort_advance_queued is False
        assert coordinator.client.write_gatt_char.call_count == count
    await coordinator.async_shutdown()


@pytest.mark.parametrize("transition", ["reauthenticate", "disconnect"])
async def test_held_release_uses_current_auth_for_the_same_physical_peer(
    hass, monkeypatch, enable_custom_integrations, transition,
):
    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
        dashboard_payload,
        decrypt_user_frame,
    )
    from tests.test_reverie_pairlink_production import (
        _PRIMARY_SESSION_KEY,
        _drain_socket,
        _entry,
        _local_setup,
        _login_packet,
        _recv,
        _send_peer_write,
        _subscribe_peer,
    )
    from tests.test_reverie_pairlink_transport import _PEER_PATH, FakeBlueZBus, _device
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    sock = await _subscribe_peer(bus, _PEER_PATH)
    await _send_peer_write(bus, _PEER_PATH, _login_packet(_PRIMARY_SESSION_KEY))
    _recv(sock)
    await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
    _recv(sock)
    await hass.async_block_till_done()
    await asyncio.sleep(0)
    await hass.async_block_till_done()
    _drain_socket(sock)
    started, proceed = asyncio.Event(), asyncio.Event()
    original_sleep = asyncio.sleep

    async def hold_clock(delay):
        if delay == 0.1:
            started.set()
            await proceed.wait()
        else:
            await original_sleep(0)

    with monkeypatch.context() as context:
        context.setattr(asyncio, "sleep", hold_clock)
        task = asyncio.create_task(coordinator.async_execute_controller_command(
            lambda current: current.hold_control("back_up", 100),
            read_positions_after_operation=False,
        ))
        await asyncio.wait_for(started.wait(), timeout=1)
        press = _recv(sock)
        assert decrypt_user_frame(press, event_key=runtime.current_event_key,
                                  device_key=_PRIMARY_SESSION_KEY)[-4:] == dashboard_payload(1, 255)
        if transition == "reauthenticate":
            key = bytes.fromhex("aabbccdd")
            await _send_peer_write(bus, _PEER_PATH, _login_packet(key))
            _recv(sock)
            # The accepted source retains the first key-table entry for a known
            # MAC. Rotate the event seed through its actual native callback.
            previous_event_key = runtime.current_event_key
            seed_packet = bytearray(14)
            seed_packet[:2] = b"\x01\x02"
            seed_packet[10:14] = bytes.fromhex("01020304")
            await _send_peer_write(bus, _PEER_PATH, bytes(seed_packet))
            assert runtime.current_event_key != previous_event_key
            current_key = runtime.prepare_send().device_key
            assert current_key == _PRIMARY_SESSION_KEY
            _drain_socket(sock)
            proceed.set()
            await task
            release = _recv(sock)
            assert decrypt_user_frame(release, event_key=runtime.current_event_key,
                                      device_key=current_key)[-4:] == dashboard_payload(3, 0)
        else:
            bus.managed_objects[_PEER_PATH] = _device(connected=False)
            assert bus.peer_disconnect_callback is not None
            bus.peer_disconnect_callback(_PEER_PATH, False)
            proceed.set()
            with pytest.raises(ConnectionError):
                await task
            assert _recv(sock) == b""
    sock.close()
    await coordinator.async_shutdown()


async def test_pairlink_central_routine_uses_real_coordinator_hold_and_timer_dispatch(
    hass,
):
    from custom_components.adjustable_bed.const import BED_TYPE_REVERIE_PAIRLINK
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.test_reverie_pairlink import _GattClient, _login_packet
    from tests.test_reverie_pairlink_production import _entry

    entry = _entry(role="central")
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = _GattClient()
    client.disconnect = AsyncMock()
    coordinator._client = client
    controller = await create_controller(coordinator, BED_TYPE_REVERIE_PAIRLINK, "R510L", client)
    coordinator._controller = controller
    await controller.start_notify()
    notify_callback = client.notify_callback
    assert notify_callback is not None
    notify_callback(None, bytearray(_login_packet()))
    await hass.async_block_till_done()
    notify_callback(None, bytearray(b"\x02\x31\x08"))
    await hass.async_block_till_done()
    request = ReverieComfortRequest(25, 40, 30, 1, 2, 3, 4)
    await coordinator.async_execute_controller_command(
        lambda current: current.async_start_routine([(request, 1), (request, 1)]),
        read_positions_after_operation=False,
    )
    timer = controller._routine_timer
    assert timer is not None
    assert coordinator._command_connection_holds == 1
    assert coordinator._disconnect_timer is None
    writes = len(client.writes)
    timer.cancel()
    controller._enqueue_routine_step(controller._routine_generation)
    await hass.async_block_till_done()
    assert len(client.writes) > writes
    assert controller._routine_timer is None
    assert coordinator._command_connection_holds == 0
    await coordinator.async_shutdown()
