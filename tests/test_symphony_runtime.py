"""Actual HA service routing, scheduler leases and Symphony GATT sessions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.symphony import state_keys as k
from custom_components.adjustable_bed.beds.symphony.controller import (
    NUS,
    NUS_NOTIFY,
    NUS_WRITE,
    SymphonyController,
)
from custom_components.adjustable_bed.command_scheduler import (
    CommandOutcome,
    PreparedCommandInvalidated,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import symphony as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock


class Services(list):
    def get_service(self, uuid):
        return next((s for s in self if s.uuid == uuid), None)

    def get_characteristic(self, uuid):
        return next(
            (char for service in self for char in service.characteristics if char.uuid == uuid),
            None,
        )


async def target(hass, monkeypatch, product="12", selector=9, side=1):
    rows = hass.data.setdefault("symphony_test_targets", [])
    address = f"AA:33:00:00:00:{len(rows) + 1:02X}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=address,
        title="Symphony",
        data={
            "address": address,
            "name": "Symphony",
            "bed_type": "symphony",
            "product_type": product,
            "protocol_variant": str(selector),
            "symphony_side": "right" if side == 2 else "left",
            "disable_angle_sensing": True,
            "motor_pulse_count": 1,
            "motor_pulse_delay_ms": 100,
            "disconnect_after_command": False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    tx = SimpleNamespace(uuid=NUS_WRITE, properties=["write"], handle=1, descriptors=[])
    rx = SimpleNamespace(uuid=NUS_NOTIFY, properties=["notify"], handle=2, descriptors=[])
    service = SimpleNamespace(
        uuid=NUS,
        characteristics=[tx, rx],
        get_characteristic=lambda uuid: {NUS_WRITE: tx, NUS_NOTIFY: rx}.get(uuid),
    )
    receivers = []
    client = SimpleNamespace(
        is_connected=True,
        services=Services([service]),
        start_notify=AsyncMock(side_effect=lambda char, fn: receivers.append(fn)),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    controller = SymphonyController(
        coordinator, app.SymphonyProfile(app.PRODUCTS[product], selector, side)
    )
    coordinator._controller, coordinator._ready = controller, True
    await controller.start_notify()
    monkeypatch.setattr(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
    monkeypatch.setattr(coordinator, "_async_refresh_controller_auth", AsyncMock())
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coordinator.device_info
    )
    entry.mock_state(hass, ConfigEntryState.LOADED)
    rows.append(coordinator)
    return coordinator, controller, client, receivers, device.id


@pytest.fixture(autouse=True)
async def cleanup(hass):
    yield
    for coordinator in hass.data.get("symphony_test_targets", []):
        await coordinator.async_shutdown()
        coordinator.entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


def packets(client):
    return [call.args[1].hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("service", ("timed_move", "hold_control"))
async def test_card_movement_renewals_outlive_ordinary_pulses_and_stop_once(
    hass, monkeypatch, service
):
    coordinator, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    data = {"device_id": [device], "hold_owner": "card", "hold_generation": 1}
    data.update(
        {"motor": "head", "direction": "up", "duration_ms": 100}
        if service == "timed_move"
        else {"control": "head_up", "duration": 0.1}
    )

    async def call():
        await hass.services.async_call(DOMAIN, service, data, blocking=True)

    sent = asyncio.Event()

    async def write(_char, frame, **kwargs):
        if frame == bytes.fromhex("aa000001010401000000"):
            sent.set()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(call())
        await sent.wait()
        for _ in range(5):
            await asyncio.sleep(0.05)
            await call()
            assert packets(client) == ["aa000001010401000000"]
        await task
    assert packets(client) == ["aa000001010401000000", "aa000001010400000000", "aa0000010200"]
    assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED
    assert controller.motor_pulse_settings() == (1, 100)


async def test_stop_to_later_target_during_connect_rejects_whole_service(hass, monkeypatch):
    first = await target(hass, monkeypatch)
    second = await target(hass, monkeypatch)
    await async_register_services(hass)
    coordinator, controller, client, _, device = second
    coordinator._controller = None
    entered, release = asyncio.Event(), asyncio.Event()
    first_connect = True

    async def connect(**kwargs):
        nonlocal first_connect
        if first_connect:
            first_connect = False
            entered.set()
            await release.wait()
        coordinator._controller = controller
        return True

    monkeypatch.setattr(coordinator, "async_ensure_connected", connect)
    task = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "symphony_set_light",
            {
                "device_id": [first[4], device],
                "color": 3,
                "brightness": 50,
            },
            blocking=True,
        )
    )
    await entered.wait()
    # STOP increments its epoch even while no controller is available.
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    client.write_gatt_char.reset_mock()
    release.set()
    with pytest.raises(PreparedCommandInvalidated):
        await task
    assert packets(first[2]) == packets(client) == []


async def test_live_preflight_rejects_later_product_before_first_requested_write(hass, monkeypatch):
    first = await target(hass, monkeypatch)
    second = await target(hass, monkeypatch, product="2")
    await async_register_services(hass)
    second[0]._controller = None

    async def connect(**kwargs):
        second[0]._controller = second[1]
        return True

    monkeypatch.setattr(second[0], "async_ensure_connected", connect)
    with pytest.raises(ServiceValidationError, match="SoundWave"):
        await hass.services.async_call(
            DOMAIN,
            "symphony_set_light",
            {"device_id": [first[4], second[4]], "color": 3, "brightness": 50},
            blocking=True,
        )
    assert packets(first[2]) == packets(second[2]) == []
    assert second[0].async_ensure_connected is connect


async def test_excluded_unsolicited_history_cannot_replace_bed_callback_or_emit_ack(
    hass, monkeypatch
):
    _, controller, client, receivers, _ = await target(hass, monkeypatch)
    callback = receivers[0]
    with virtual_clock():
        callback(None, bytes.fromhex("2a000007820101") + bytes(20))
        callback(None, bytes.fromhex("2a000007830100") + bytes(20))
        await asyncio.sleep(0.3)
        assert not packets(client)
        callback(None, bytes.fromhex("2a0000048106020300000032"))
        assert controller._coordinator.controller_state[k.COLOR] == 3
        await controller.light_action(False)
    assert packets(client) == ["aa00000401050000", "2a0000048100"]
    assert receivers == [callback]


async def test_reconnect_retires_real_subscription_and_old_local_publisher(hass, monkeypatch):
    coordinator, old, client, receivers, _ = await target(hass, monkeypatch)
    old_callback = receivers[0]
    await old.stop_notify()
    replacement = SymphonyController(coordinator, old.app)
    coordinator._controller = replacement
    await replacement.start_notify()
    old_callback(None, bytes.fromhex("2a0000048106020700000050"))
    assert coordinator.controller_state[k.COLOR] is None
    receivers[1](None, bytes.fromhex("2a0000048106020300000032"))
    assert coordinator.controller_state[k.COLOR] == 3
    assert old.local is replacement.local
    assert client.stop_notify.await_count == 1


async def test_single_address_both_routes_two_captured_side_frames_and_stops(hass, monkeypatch):
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.paired_devices import async_register_children

    coordinator, _, client, _, device = await target(hass, monkeypatch, product="15", selector=4)
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={**coordinator.entry.data, "pair_id": "symphony-split", "pair_mode": "single_address"},
    )
    pair = SingleAddressPairedCoordinator(hass, coordinator.entry, coordinator)
    hass.data[DOMAIN][coordinator.entry.entry_id] = pair
    async_register_children(hass, pair)
    await async_register_services(hass)
    try:
        with virtual_clock():
            await hass.services.async_call(
                DOMAIN,
                "symphony_preset",
                {
                    "device_id": [device],
                    "side": "both",
                    "preset": "memory_1",
                },
                blocking=True,
            )
        assert packets(client) == [
            "e6fe16000001000103",
            "e6fe16000000000104",
            "e6fe16000001000202",
            "e6fe16000000000203",
        ]
        client.write_gatt_char.reset_mock()
        with virtual_clock():
            await hass.services.async_call(
                DOMAIN, "stop_all", {"device_id": [device]}, blocking=True
            )
        assert packets(client) == ["e6fe16000000000104", "e6fe16000000000203"]
    finally:
        await pair.async_shutdown()


async def test_real_platform_builders_retire_product_specific_controls(hass, monkeypatch):
    from custom_components.adjustable_bed.cover import AdjustableBedCover
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from tests.test_entity_sweep import async_setup_platforms_and_sweep

    coordinator, controller, _, _, _ = await target(hass, monkeypatch, product="13")
    created = await async_setup_platforms_and_sweep(hass, coordinator.entry, coordinator)
    assert {e.entity_description.key for e in created if isinstance(e, AdjustableBedCover)} == set(
        controller.app.product.axes
    )
    assert len([e for e in created if isinstance(e, AdjustableBedControllerNumber)]) == 2
    coordinator._controller = SymphonyController(
        coordinator, app.SymphonyProfile(app.PRODUCTS["2"], 4)
    )
    changed = await async_setup_platforms_and_sweep(hass, coordinator.entry, coordinator)
    assert not any(isinstance(e, AdjustableBedControllerNumber) for e in changed)
    assert {e.entity_description.key for e in changed if isinstance(e, AdjustableBedCover)} == {
        "head",
        "feet",
        "elevation",
    }


async def test_queued_real_gatt_write_cannot_cross_session_generation(hass, monkeypatch):
    _, controller, client, _, _ = await target(hass, monkeypatch)
    await controller._ble_lock.acquire()
    task = asyncio.create_task(
        controller.write_command(app.movement(controller.app, "head", True, 1))
    )
    await asyncio.sleep(0)
    controller.on_disconnect()
    # Even a backend reusing the client object cannot rescue the old generation.
    controller._ready = True
    controller._ble_lock.release()
    with pytest.raises(ConnectionError, match="earlier Symphony session"):
        await task
    assert packets(client) == []


async def test_registered_bounded_motion_does_not_stretch_for_slow_gatt_ack(hass, monkeypatch):
    _, _, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    elapsed = []

    async def write(_char, frame, **kwargs):
        elapsed.append((asyncio.get_running_loop().time(), frame.hex()))
        if frame == bytes.fromhex("aa000001010401000000"):
            await asyncio.sleep(2)

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {"device_id": [device], "motor": "head", "direction": "up", "duration_ms": 1000},
            blocking=True,
        )
    assert elapsed[1][0] - elapsed[0][0] == pytest.approx(1)
    assert [packet for _, packet in elapsed] == [
        "aa000001010401000000",
        "aa000001010400000000",
        "aa0000010200",
    ]


async def test_actual_coordinator_connect_and_disconnect_rebuilds_owned_session(
    hass,
    monkeypatch,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_establish_connection,
):
    coordinator, old, client, _, _ = await target(hass, monkeypatch)
    mock_bleak_client.services = client.services
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    old.on_disconnect()
    coordinator._client = coordinator._controller = coordinator._offline_controller = None
    with virtual_clock():
        assert await coordinator.async_connect()
    live = coordinator.controller
    assert isinstance(live, SymphonyController) and live is not old
    writes = packets(mock_bleak_client)
    assert writes[0] == "2a000005810901ffff00002225124b"
    assert "2a0000078100" in writes and "2a0000068100" in writes
    assert mock_establish_connection.call_args.kwargs["timeout"] == 8
    coordinator._intentional_disconnect = True
    mock_bleak_client.is_connected = False
    coordinator._on_disconnect(mock_bleak_client)
    assert coordinator.controller is None and not live._ready


async def test_registered_split_alarm_hydrates_peer_and_repeats_captured_frame(hass, monkeypatch):
    _, controller, client, receivers, device = await target(
        hass, monkeypatch, product="15", selector=4, side=2
    )
    await async_register_services(hass)

    async def write(_char, frame, **kwargs):
        if frame == bytes.fromhex("e180039b"):
            receivers[0](None, bytes.fromhex("ed800300000000071e3e11083b810d00"))

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "symphony_set_alarm",
            {
                "device_id": [device],
                "enabled": True,
                "time": "09:15:00",
                "weekdays": [1],
                "wake_mode": "memory_1",
            },
            blocking=True,
        )
    writes = packets(client)
    assert writes[2:4] == ["e180039b", "e180039b"]
    assert writes[4:] == ["ed800300000000071e3e11090f821170"] * 2 + ["e180039b"]
    assert controller._alarm_cache is not None


@pytest.fixture
async def split_pair(hass, monkeypatch):
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.paired_devices import async_register_children

    coordinator, controller, client, receivers, device = await target(
        hass, monkeypatch, product="15", selector=4
    )
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={
            **coordinator.entry.data,
            "pair_id": "symphony-alarm-split",
            "pair_mode": "single_address",
        },
    )
    pair = SingleAddressPairedCoordinator(hass, coordinator.entry, coordinator)
    hass.data[DOMAIN][coordinator.entry.entry_id] = pair
    async_register_children(hass, pair)
    await async_register_services(hass)
    try:
        yield pair, controller, client, receivers, device
    finally:
        await pair.async_shutdown()


async def test_review_S1_both_split_alarm_writes_one_composed_peer_table(hass, split_pair):
    _, _, client, receivers, device = split_pair

    async def write(_char, frame, **kwargs):
        if frame == bytes.fromhex("e180039b"):
            # Query replies remain the old observed table. Neither edit may
            # depend on a timely/correlated post-write notification.
            receivers[0](None, bytes.fromhex("ed800300000000071e3e11083b810d00"))

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "symphony_set_alarm",
            {
                "device_id": [device],
                "side": "both",
                "enabled": True,
                "time": "09:15:00",
                "weekdays": [1],
                "wake_mode": "memory_1",
            },
            blocking=True,
        )
    tables = [packet for packet in packets(client) if packet.startswith("ed8003")]
    assert tables == ["ed800300000000090f8211090f821139"] * 2


@pytest.mark.parametrize("action", ("timed_move", "hold_control"))
async def test_review_S2_both_lease_is_rejected_before_any_motion_or_claim(
    hass, split_pair, action
):
    from custom_components.adjustable_bed.button import (
        _paired_hold_lease_attributes,
        _paired_motor_hold_spec,
    )

    pair, _, client, _, device = split_pair
    assert not pair.supports_simultaneous_side_holds
    assert _paired_hold_lease_attributes(pair, control="head_up") == {}
    assert _paired_motor_hold_spec(pair, "head") is None
    data = {"device_id": [device], "side": "both", "hold_owner": "card", "hold_generation": 1}
    data.update(
        {"motor": "head", "direction": "up", "duration_ms": 100}
        if action == "timed_move"
        else {"control": "head_up", "duration": 0.1}
    )
    with pytest.raises(ServiceValidationError, match="simultaneous side execution"):
        await hass.services.async_call(DOMAIN, action, data, blocking=True)
    assert packets(client) == []


@pytest.mark.parametrize("side", (1, 2))
def test_review_S4_split_alarm_requires_complete_peer_table_even_for_left(side):
    cache = bytes.fromhex("ed800300000000071e3e1100")
    with pytest.raises(ValueError, match="complete current-session"):
        app.alarm(
            app.SymphonyProfile(app.PRODUCTS["15"], 4),
            enabled=True,
            hour=9,
            minute=15,
            week=130,
            mode="memory_1",
            side=side,
            cache=cache,
        )


@pytest.fixture
async def sequential_pair(hass, monkeypatch):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import async_register_children

    triples = {
        side: await target(hass, monkeypatch, product="15", selector=4)
        for side in ("left", "right")
    }
    sticky = set()
    connections = []
    controllers = []
    for side, (coordinator, _controller, client, receivers, _) in triples.items():

        async def disconnect(
            reason="intentional",
            *,
            serialize_with_commands=False,
            side=side,
            coordinator=coordinator,
            client=client,
        ):
            if side in sticky:
                return False
            if coordinator.controller is not None:
                coordinator.controller.on_disconnect()
            client.is_connected = False
            coordinator._controller = coordinator._client = None
            return True

        async def connect(side=side, coordinator=coordinator, client=client):
            assert all(not row[2].is_connected for key, row in triples.items() if key != side), (
                "sequential path opened overlapping links"
            )
            if coordinator.controller is not None and client.is_connected:
                return True
            connections.append(side)
            client.is_connected = True
            coordinator._client = client
            current = SymphonyController(coordinator, app.SymphonyProfile(app.PRODUCTS["15"], 4))
            coordinator._controller = current
            controllers.append(current)
            await current.start_notify()
            return True

        async def ensure(reset_timer=True, coordinator=coordinator):
            return (
                True
                if coordinator.controller is not None and coordinator.is_connected
                else await coordinator.async_connect()
            )

        async def write(_char, frame, *, response=True, receivers=receivers):
            if frame == bytes.fromhex("e180039b"):
                receivers[-1](None, bytes.fromhex("ed800300000000071e3e11083b810d00"))

        monkeypatch.setattr(coordinator, "async_connect", connect)
        monkeypatch.setattr(coordinator, "async_disconnect", disconnect)
        monkeypatch.setattr(coordinator, "async_ensure_connected", ensure)
        client.write_gatt_char.side_effect = write
    # A peer connected out-of-band must be released before Left preflight.
    await triples["left"][0].async_disconnect()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Sequential Symphony",
        data={"pair_id": "symphony-two-link", "pair_connection_mode": "sequential"},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(
        hass, entry, {side: row[0] for side, row in triples.items()}, connection_mode="sequential"
    )
    hass.data[DOMAIN][entry.entry_id] = pair
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **pair.device_info
    )
    async_register_children(hass, pair)
    await async_register_services(hass)
    try:
        yield pair, triples, device.id, sticky, connections, controllers
    finally:
        sticky.clear()
        await pair.async_shutdown()
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.mark.parametrize("side", ("left", "both"))
async def test_review_S3_sequential_alarm_rehydrates_inside_executing_session(
    hass, sequential_pair, side
):
    _, triples, device, _, connections, controllers = sequential_pair
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "symphony_set_alarm",
            {
                "device_id": [device],
                "side": side,
                "enabled": True,
                "time": "09:15:00",
                "weekdays": [1],
                "wake_mode": "memory_1",
            },
            blocking=True,
        )
    tables = [packet for packet in packets(triples["left"][2]) if packet.startswith("ed8003")]
    assert tables == ["ed800300000000090f8211083b810d13"] * 2
    selected = ["left", "right"] if side == "both" else ["left"]
    assert connections == selected * 2 and len(controllers) == len(selected) * 2
    assert all(not current._ready for current in controllers)
    if side == "left":
        assert packets(triples["right"][2]) == []
    else:
        assert [packet for packet in packets(triples["right"][2]) if packet.startswith("ed8003")] == tables


@pytest.mark.parametrize(
    "stuck,side,expected_connects", [("right", "left", []), ("left", "both", ["left"])]
)
async def test_review_S5_sequential_preflight_aborts_on_failed_peer_or_own_release(
    hass, sequential_pair, stuck, side, expected_connects
):
    from custom_components.adjustable_bed.paired_coordinator import PairedSideError

    _, triples, device, sticky, connections, _ = sequential_pair
    sticky.add(stuck)
    with virtual_clock(), pytest.raises(PairedSideError):
        await hass.services.async_call(
            DOMAIN,
            "symphony_preset",
            {
                "device_id": [device],
                "side": side,
                "preset": "memory_1",
            },
            blocking=True,
        )
    assert connections == expected_connects
    assert all(packets(row[2]) == [] for row in triples.values())
