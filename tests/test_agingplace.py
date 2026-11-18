"""Accepted row069 profile, parser, factory and public HA command behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.app_session import app_session
from custom_components.adjustable_bed.beds.keeson.agingplace import AgingPlaceController
from custom_components.adjustable_bed.beds.keeson.agingplace_state import (
    NUMBERS,
    OCCUPIED,
    TEXT,
    Observations,
)
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import agingplace as app
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

FIXTURES = Path(__file__).parent / "fixtures/agingplace"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
IDENTITY = "KSWF07S123456789"
ALIASES = {
    "iv_light": "light",
    "iv_relax": "massage",
    "iv_zg": "zero_g",
    "iv_snore": "anti_snore",
    "iv_read": "read",
    "iv_flat": "flat",
    "v_head_up": "head_up",
    "v_head_down": "head_down",
    "v_foot_up": "foot_up",
    "v_foot_down": "foot_down",
    "v_bed_up": "bed_up",
    "v_bed_down": "bed_down",
    "iv_in": "in",
    "iv_out": "out",
}


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_profile_reproduces_every_frozen_literal(row):
    action = ALIASES.get(row["action"], row["action"])
    identity = row["inputs"]["dvid"]
    if action in ("brightness", "massage_minutes", "motion_minutes"):
        actual = app.setting(action, row["inputs"]["value"], identity)
    elif action == "device_info":
        actual = app.device_info(identity)
    else:
        actual = app.ACTIONS[action].frame(identity)
    assert actual.hex() == row["expected_bytes"]


@pytest.mark.parametrize(
    "mode,side,selected,incoming,accepted",
    (
        (0, 1, 0, 0, True),
        (1, 1, 0, 0, False),
        (1, 1, 0, 1, True),
        (2, 1, 0, 0, True),
        (1, 2, 1, 0, False),
        (1, 2, 1, 1, True),
    ),
)
def test_live_readings_follow_the_telemetry_side(mode, side, selected, incoming, accepted):
    observations = Observations(mode=mode, bed_side=side, selected_side=selected)
    payload = {
        "dt": 2,
        "di": "another identity",
        "ts": 123,
        "data": {"lb": 0, "si": incoming, "hr": 63, "br": 14, "bm": 4, "sn": 7},
    }
    state = {update.key: update.value for update in observations.consume(payload)}
    assert (OCCUPIED in state) is accepted
    if accepted:
        assert state[OCCUPIED] is True
        assert state[NUMBERS["heart_rate"]] == 63
        assert state[NUMBERS["breathing_rate"]] == 14
    # di is observed metadata, never an invented dvid/ACK admission check.
    assert state[TEXT["di"]] == "another identity"
    payload["data"].update(lb=1)
    state = {update.key: update.value for update in observations.consume(payload)}
    if accepted:
        assert state[OCCUPIED] is False
        assert state[NUMBERS["heart_rate"]] is None
        assert state[NUMBERS["breathing_rate"]] is None


def test_complete_indications_not_stream_reassembly_and_local_info_fields():
    packet = b'{"data":{"MAC":"AA","dspsen":3,"bedmd":7,"ver":11399,"dspver":"d","hardver":"h","pcbver":"p","wifiver":"w"},"di":"observed"}'
    assert codec.parse_json_indication(packet[:30]) is None
    assert codec.parse_json_indication(packet[30:]) is None
    decoded = codec.parse_json_indication(packet)
    observations = Observations(mode=None, bed_side=0, selected_side=0)
    state = {update.key: update.value for update in observations.consume(decoded)}
    assert observations.mode == 1
    assert state[NUMBERS["version"]] == 113
    assert state[TEXT["wifiver"]] == "w"
    assert codec.parse_json_indication(b"\xff") is None
    assert codec.parse_json_indication(b"[]") is None


def test_timers_and_observed_diagnostic_maxima_do_not_invent_currents():
    observations = Observations(mode=0, bed_side=0, selected_side=0)
    for key, (name, total) in app.CYCLE_TOTALS.items():
        state = {u.key: u.value for u in observations.consume({"data": {"timer": 17, "key": key}})}
        assert state[NUMBERS[f"{name}_remaining"]] == total - 17
    observations.consume({"chkStatu": 1, "headPlus": 8, "footPlus": 4})
    state = {
        u.key: u.value
        for u in observations.consume({"chkStatu": 49152, "headPlus": 2, "footPlus": 9})
    }
    assert state[NUMBERS["headPlus"]] == 8
    assert state[NUMBERS["footPlus"]] == 9
    assert state[TEXT["diagnostic_status"]] == "complete"
    assert not any("current" in key or "angle" in key for key in state)


async def test_factory_restore_profile_ids_and_side_owned_setup_fields():
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = {
        "bed_type": "agingplace",
        "ble_device_name": IDENTITY,
        "agingplace_bed_mode": "2",
        "agingplace_bed_side": 2,
        "agingplace_selected_side": 1,
    }
    controller = await create_controller(
        coordinator, "agingplace", "auto", None, device_name="Edited title"
    )
    assert isinstance(controller, AgingPlaceController)
    assert controller.device_id == IDENTITY
    assert controller.observations.mode == 2
    assert resolve_profile_id(coordinator.entry.data) == "agingplace"
    profile = setup_profile_for(coordinator.entry.data)
    assert profile is not None
    settings = profile.settled(coordinator.entry.data)
    assert settings["motor_count"] == 3
    assert settings["has_massage"] is True
    assert settings["disable_angle_sensing"] is True
    assert per_side_profile("agingplace", None).keys >= app.CONFIG_KEYS | {"ble_device_name"}
    assert not controller.supports_single_address_pairing
    assert not controller.position_number_specs
    assert controller.held_control_options == (
        "head_up",
        "head_down",
        "foot_up",
        "foot_down",
        "bed_up",
        "bed_down",
        "in",
        "out",
    )


class Services(list):
    def get_service(self, uuid):
        return next((service for service in self if service.uuid == uuid), None)

    def get_characteristic(self, uuid):
        return next(
            (char for service in self for char in service.characteristics if char.uuid == uuid),
            None,
        )


async def target(hass, monkeypatch, *, mode=0):
    rows = hass.data.setdefault("agingplace_test_targets", [])
    address = f"AA:69:00:00:00:{len(rows) + 1:02X}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=address,
        title="Dawn House",
        data={
            "address": address,
            "name": "Edited title",
            "bed_type": "agingplace",
            "ble_device_name": IDENTITY,
            "agingplace_bed_mode": str(mode),
            "disable_angle_sensing": True,
            "has_massage": True,
            "motor_count": 3,
            "motor_pulse_count": 5,
            "motor_pulse_delay_ms": 200,
            "disconnect_after_command": False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    transport = codec.TRANSPORTS["json"]
    tx = SimpleNamespace(uuid=transport.write_uuid, properties=["write"], handle=1, descriptors=[])
    rx = SimpleNamespace(
        uuid=transport.notify_uuid, properties=["indicate"], handle=2, descriptors=[]
    )
    service = SimpleNamespace(
        uuid=transport.service_uuid,
        characteristics=[tx, rx],
        get_characteristic=lambda uuid: {tx.uuid: tx, rx.uuid: rx}.get(uuid),
    )
    receivers = []
    client = SimpleNamespace(
        is_connected=True,
        mtu_size=260,
        services=Services([service]),
        start_notify=AsyncMock(side_effect=lambda char, fn, **kwargs: receivers.append(fn)),
        stop_notify=AsyncMock(),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
    )
    coordinator._client = client
    controller = await create_controller(coordinator, "agingplace", "auto", client)
    coordinator._controller, coordinator._ready = controller, True
    with virtual_clock():
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
    for coordinator in hass.data.get("agingplace_test_targets", []):
        await coordinator.async_shutdown()
        coordinator.entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


def packets(client):
    return [call.args[1] for call in client.write_gatt_char.call_args_list]


async def test_public_actions_parameters_and_distinct_flat_and_release(hass, monkeypatch):
    _, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    for name in (
        "read",
        "anti_snore",
        "circulation",
        "cancel",
        "release",
        "diagnostic",
        "device_info",
    ):
        await hass.services.async_call(
            DOMAIN, "agingplace_action", {"device_id": [device], "action": name}, blocking=True
        )
    expected = [
        app.ACTIONS[name].frame(IDENTITY)
        for name in ("read", "anti_snore", "circulation", "flat", "release", "diagnostic")
    ]
    assert packets(client) == [*expected, app.device_info(IDENTITY)]
    assert expected[0] == expected[1]
    assert expected[3] != expected[4]
    for name, value in (("brightness", 1), ("massage_minutes", 60), ("motion_minutes", 30)):
        await hass.services.async_call(
            DOMAIN,
            "agingplace_set_setting",
            {"device_id": [device], "setting": name, "value": value},
            blocking=True,
        )
        assert packets(client)[-1] == app.setting(name, value, IDENTITY)
    assert controller._flat_cancel_active


async def test_elapsed_hold_with_slow_write_and_release_on_repeat_cancellation(hass, monkeypatch):
    coordinator, controller, client, _, _ = await target(hass, monkeypatch)
    sent = asyncio.Event()
    finish = asyncio.Event()
    start = app.ACTIONS["in"].frame(IDENTITY)
    release = app.ACTIONS["release"].frame(IDENTITY)

    async def write(_char, frame, **kwargs):
        if frame == start:
            sent.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.hold_control("in", 1000))
    await sent.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert packets(client) == [start]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert packets(client) == [start, release]
    coordinator.cancel_command.clear()


async def test_no_release_or_callback_migrates_to_replacement_session(hass, monkeypatch):
    coordinator, controller, client, receivers, _ = await target(hass, monkeypatch)
    start = asyncio.Event()
    finish = asyncio.Event()

    async def write(*args, **kwargs):
        start.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.hold_control("out", 1000))
    await start.wait()
    controller.on_disconnect()
    replacement = SimpleNamespace(**{**client.__dict__, "write_gatt_char": AsyncMock()})
    coordinator._client = replacement
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    receivers[0](None, bytearray(b'{"data":{"hr":70,"lb":0}}'))
    assert not replacement.write_gatt_char.await_count
    assert coordinator.controller_state.get(NUMBERS["heart_rate"]) is None


async def test_literal_chunk_boundaries_advance_without_retry_and_surface_failure(
    hass, monkeypatch
):
    _, controller, client, _, _ = await target(hass, monkeypatch)
    for size in (259, 260, 261, 520, 521):
        client.write_gatt_char.reset_mock()
        payload = b"x" * size
        await controller.write_command(payload)
        assert packets(client) == [payload[start : start + 260] for start in range(0, size, 260)]
    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = [BleakError("first chunk failed"), None, None]
    with pytest.raises(BleakError, match="first chunk failed"):
        await controller.write_command(b"x" * 521)
    assert [len(frame) for frame in packets(client)] == [260, 260, 1]


async def test_all_target_validation_and_stop_before_lazy_import(hass, monkeypatch):
    from custom_components.adjustable_bed.beds.keeson.controller import KeesonController

    first = await target(hass, monkeypatch)
    second = await target(hass, monkeypatch)
    await async_register_services(hass)
    second[0]._controller = KeesonController(second[0], variant="json")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "agingplace_action",
            {"device_id": [first[4], second[4]], "action": "flat"},
            blocking=True,
        )
    assert not packets(first[2])
    second[0]._controller = second[1]
    from custom_components.adjustable_bed.beds.keeson import agingplace_services

    original = agingplace_services.async_import_modules

    async def stopped(hass, *modules):
        second[0]._command_scheduler.request_stop()
        await original(hass, *modules)

    monkeypatch.setattr(agingplace_services, "async_import_modules", stopped)
    with pytest.raises((ServiceValidationError, RuntimeError)):
        await hass.services.async_call(
            DOMAIN,
            "agingplace_action",
            {"device_id": [first[4], second[4]], "action": "flat"},
            blocking=True,
        )
    assert not packets(first[2])
    assert not packets(second[2])


@pytest.mark.parametrize("connection_mode", ("concurrent", "sequential"))
async def test_native_paired_children_keep_physical_targets(hass, monkeypatch, connection_mode):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import async_register_children

    left = await target(hass, monkeypatch)
    right = await target(hass, monkeypatch)
    for _coordinator, _controller, client, _callbacks, _device in (left, right):

        async def disconnect(link=client):
            link.is_connected = False

        client.disconnect.side_effect = disconnect
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Dawn House pair",
        data={"pair_id": "agingplace-test", "name": "Dawn House pair"},
    )
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left[0], "right": right[0]}, connection_mode=connection_mode
    )
    hass.data[DOMAIN] = {entry.entry_id: pair}
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **pair.device_info)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    async_register_children(hass, pair)
    devices = dr.async_get(hass)
    child = devices.async_get_child_device_by_identifier((DOMAIN, right[0].address), entry.entry_id)
    assert child is not None
    await async_register_services(hass)
    # The real topology must close the other fake physical link before this one.
    try:
        await hass.services.async_call(
            DOMAIN, "agingplace_action", {"device_id": [child.id], "action": "read"}, blocking=True
        )
        assert packets(left[2]) == []
        assert packets(right[2]) == [app.ACTIONS["read"].frame(IDENTITY)]
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "agingplace_action",
                {"device_id": [child.id], "side": "left", "action": "flat"},
                blocking=True,
            )
        assert len(packets(right[2])) == 1
    finally:
        await pair.async_shutdown()
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def test_single_address_pair_cannot_invent_command_sides(hass, monkeypatch):
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator

    coordinator, _, client, _, device = await target(hass, monkeypatch)
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={
            **coordinator.entry.data,
            "pair_id": "agingplace-single",
            "pair_mode": "single_address",
        },
    )
    pair = SingleAddressPairedCoordinator(hass, coordinator.entry, coordinator)
    hass.data[DOMAIN][coordinator.entry.entry_id] = pair
    await async_register_services(hass)
    try:
        with pytest.raises(ServiceValidationError, match="no command-side selector"):
            await hass.services.async_call(
                DOMAIN,
                "agingplace_action",
                {"device_id": [device], "side": "right", "action": "read"},
                blocking=True,
            )
        assert not packets(client)
    finally:
        await pair.async_shutdown()


@pytest.mark.parametrize("source", ("user", "import"))
async def test_real_entry_installs_native_entities_and_public_controls(
    hass,
    monkeypatch,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    source,
):
    from homeassistant.helpers import entity_registry as er

    transport = codec.TRANSPORTS["json"]
    tx = SimpleNamespace(uuid=transport.write_uuid, properties=["write"], handle=1, descriptors=[])
    rx = SimpleNamespace(
        uuid=transport.notify_uuid, properties=["indicate"], handle=2, descriptors=[]
    )
    service = SimpleNamespace(
        uuid=transport.service_uuid,
        characteristics=[tx, rx],
        get_characteristic=lambda uuid: {tx.uuid: tx, rx.uuid: rx}.get(uuid),
    )
    mock_bleak_client.services = Services([service])
    mock_bleak_client._backend = None
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    monkeypatch.setattr(app, "CONNECT_WAIT", 0)
    monkeypatch.setattr(app, "INDICATION_WAIT", 0)
    entry = MockConfigEntry(
        domain=DOMAIN,
        source=source,
        title="Dawn House",
        unique_id="AA:69:00:00:00:FF",
        version=5,
        data={
            "address": "AA:69:00:00:00:FF",
            "name": "Dawn House",
            "bed_type": "agingplace",
            "profile_id": "agingplace",
            "ble_device_name": IDENTITY,
            "disable_angle_sensing": True,
            "has_massage": True,
            "motor_count": 3,
            "agingplace_bed_mode": "auto",
            "agingplace_bed_side": 0,
            "motor_pulse_count": 5,
            "motor_pulse_delay_ms": 200,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    registry = er.async_get(hass)
    entities = [
        entity for entity in registry.entities.values() if entity.config_entry_id == entry.entry_id
    ]
    keys = {entity.translation_key for entity in entities}
    assert {
        "agingplace_circulation",
        "agingplace_in",
        "agingplace_out",
        "agingplace_brightness",
        "agingplace_massage_minutes",
        "agingplace_motion_minutes",
        "agingplace_occupancy",
        "agingplace_heart_rate",
        "agingplace_diagnostic_status",
    } <= keys
    assert (
        not {
            "massage_intensity_up",
            "preset_memory_1",
            "back_angle",
            "legs_angle",
            "agingplace_read",
            "agingplace_cancel",
        }
        & keys
    )
    assert len(coordinator.controller.motor_control_specs) == 3
    mock_bleak_client.write_gatt_char.reset_mock()
    button = next(
        entity for entity in entities if entity.translation_key == "agingplace_circulation"
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": button.entity_id}, blocking=True
    )
    assert packets(mock_bleak_client) == [app.ACTIONS["circulation"].frame(IDENTITY)]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_new_setup_and_configure_apply_the_same_profile(hass, monkeypatch):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _configure_questions,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {"bed_type": "agingplace", "address": "AA:69:00:00:00:00"}
    finish = AsyncMock()
    monkeypatch.setattr(flow, "_finish_with_verify", finish)
    answers = {
        "ble_device_name": IDENTITY,
        "agingplace_bed_mode": "2",
        "agingplace_bed_side": 2,
        "agingplace_selected_side": 1,
    }
    await flow.async_step_profile_questions(answers)
    saved = finish.call_args.args[0]
    assert saved["agingplace_bed_side"] == 2
    assert saved["agingplace_selected_side"] == 1
    assert saved["motor_count"] == 3
    assert saved["has_massage"] is True
    configured = _configure_questions(saved)
    assert configured is not None
    assert {question.key for question in configured.questions} == {
        "ble_device_name",
        *app.CONFIG_KEYS,
    }
    assert resolve_profile_id(saved) == "agingplace"


@pytest.mark.parametrize("mtu_property", (None, "write-without-response", "notify"))
async def test_startup_acquires_mtu_only_with_supported_gatt(hass, monkeypatch, mtu_property):
    _, controller, client, _, _ = await target(hass, monkeypatch)
    await controller.stop_notify()
    if mtu_property is not None:
        client.services.append(
            SimpleNamespace(characteristics=[SimpleNamespace(properties=[mtu_property])])
        )
    acquire = AsyncMock(
        side_effect=RuntimeError("coroutine raised StopIteration") if mtu_property is None else None
    )
    client._backend = SimpleNamespace(_acquire_mtu=acquire)
    client.start_notify.reset_mock()

    with virtual_clock():
        await controller.start_notify()

    assert acquire.await_count == (0 if mtu_property is None else 1)
    client.start_notify.assert_awaited_once()
    assert client.start_notify.call_args.kwargs == {"force_indicate": True}
    await controller.run_action("flat")
    assert packets(client)


async def test_startup_failure_fixed_gatt_and_retired_notification_owner(hass, monkeypatch):
    coordinator, controller, client, callbacks, _ = await target(hass, monkeypatch)
    assert not packets(client)  # indication setup has no query/startup command
    await controller.stop_notify()
    client.start_notify.side_effect = BleakError("indications failed")
    with pytest.raises(BleakError, match="indications failed"):
        await controller.start_notify()
    with pytest.raises(ConnectionError, match="not ready"):
        await controller.run_action("flat")
    callbacks[0](None, bytearray(b'{"data":{"hr":99}}'))
    assert coordinator.controller_state.get(NUMBERS["heart_rate"]) is None
    client.services[0].uuid = "0000ffe5-0000-1000-8000-00805f9b34fb"
    with pytest.raises(ConnectionError, match="requires"):
        await controller.start_notify()
    assert not packets(client)


async def test_observed_shared_provisioning_link_effect_publishes_no_credentials(hass, monkeypatch):
    coordinator, controller, client, callbacks, _ = await target(hass, monkeypatch)
    callbacks[0](None, bytearray(b'{"ssid":"private-network","pswd":"private-password"}'))
    await hass.async_block_till_done()
    assert client.disconnect.await_count == 1
    with pytest.raises(ConnectionError, match="not ready"):
        await controller.run_action("flat")
    assert not any("private-" in str(value) for value in coordinator.controller_state.values())
    assert not packets(client)


async def test_hold_duration_uses_elapsed_time_and_source_fixed_delay(hass, monkeypatch):
    _, controller, client, _, _ = await target(hass, monkeypatch)
    events = []

    async def slow_write(_char, frame, **kwargs):
        events.append((asyncio.get_running_loop().time(), frame))
        await asyncio.sleep(0.25)

    client.write_gatt_char.side_effect = slow_write
    with virtual_clock():
        start = asyncio.get_running_loop().time()
        await controller.hold_control("head_up", 600)
    assert [round((when - start) * 1000) for when, _frame in events] == [0, 450, 700]
    assert events[-1][1] == app.ACTIONS["release"].frame(IDENTITY)


@pytest.mark.parametrize("service", ("timed_move", "hold_control"))
async def test_registered_timed_hold_and_stop_drain_one_source_release(hass, monkeypatch, service):
    _, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    sent = asyncio.Event()
    first = app.ACTIONS["head_up"].frame(IDENTITY)

    async def write(_char, frame, **kwargs):
        if frame == first:
            sent.set()

    client.write_gatt_char.side_effect = write
    data: dict[str, object] = {"device_id": [device]}
    data.update(
        {"motor": "back", "direction": "up", "duration_ms": 10000}
        if service == "timed_move"
        else {"control": "head_up", "duration": 10}
    )
    task = asyncio.create_task(hass.services.async_call(DOMAIN, service, data, blocking=True))
    async with asyncio.timeout(3):
        await sent.wait()
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    await task
    assert packets(client) == [first, app.ACTIONS["release"].frame(IDENTITY)]
    assert not controller._flat_cancel_active


@pytest.mark.parametrize("action", ("circulation", "sleep", "relax_cycle", "diagnostic"))
async def test_registered_stop_during_automatic_start_write_sends_flat(hass, monkeypatch, action):
    coordinator, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    transmitted, complete = asyncio.Event(), asyncio.Event()
    first = app.ACTIONS[action].frame(IDENTITY)

    async def write(_char, frame, **_kwargs):
        if frame == first:
            transmitted.set()
            await complete.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        hass.services.async_call(
            DOMAIN, "agingplace_action", {"device_id": [device], "action": action}, blocking=True
        )
    )
    stopping = None
    try:
        async with asyncio.timeout(3):
            await transmitted.wait()
            stopping = asyncio.create_task(
                hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
            )
            await coordinator.cancel_command.wait()
            assert not stopping.done()
            complete.set()
            await stopping
            await task
        assert packets(client) == [first, app.ACTIONS["flat"].frame(IDENTITY)]
        assert not controller._flat_cancel_active
        assert controller._diagnostic_timeout is None
    finally:
        complete.set()
        pending = [operation for operation in (task, stopping) if operation is not None]
        for operation in pending:
            if not operation.done():
                operation.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.parametrize("retirement", ("disconnect", "replacement"))
@pytest.mark.parametrize(
    "action", ("diagnostic", "brightness", "massage_minutes", "motion_minutes")
)
async def test_retired_write_cannot_publish_state_or_arm_diagnostic_timer(
    hass, monkeypatch, retirement, action
):
    coordinator, controller, client, _, _ = await target(hass, monkeypatch)
    transmitted, complete = asyncio.Event(), asyncio.Event()

    async def write(_char, _frame, **_kwargs):
        transmitted.set()
        await complete.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        controller.run_action(action)
        if action == "diagnostic"
        else controller.set_setting(action, 12)
    )
    try:
        async with asyncio.timeout(3):
            await transmitted.wait()
            timer = controller._diagnostic_timeout
            retired_timeout = timer._callback if timer is not None else None
            controller.on_disconnect()
            if retirement == "replacement":
                replacement = await create_controller(coordinator, "agingplace", "auto", client)
                coordinator._controller = replacement
                with virtual_clock():
                    await replacement.start_notify()
                replacement.forward_controller_state_updates(
                    TEXT["diagnostic_status"]("replacement"),
                    NUMBERS["brightness" if action == "diagnostic" else action](11),
                )
            expected = dict(coordinator.controller_state)
            if retired_timeout is not None:
                retired_timeout()
                assert coordinator.controller_state == expected
            complete.set()
            with pytest.raises(ConnectionError, match="retired session"):
                await task
        assert coordinator.controller_state == expected
        assert controller._diagnostic_timeout is None
        assert controller._diagnostic_quiet is None
        assert controller._flat_cancel_active is (action == "diagnostic")
    finally:
        complete.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def reconnect_target(coordinator, previous):
    """Build a new factory controller on a new fake BLE link, with real HA clocks."""
    receivers = []
    client = SimpleNamespace(
        **{
            **previous.__dict__,
            "is_connected": True,
            "write_gatt_char": AsyncMock(),
            "start_notify": AsyncMock(side_effect=lambda char, fn, **kwargs: receivers.append(fn)),
            "stop_notify": AsyncMock(),
        }
    )

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    coordinator._client = client
    controller = await create_controller(coordinator, "agingplace", "auto", client)
    coordinator._controller, coordinator._ready = controller, True
    with virtual_clock():
        await controller.start_notify()
    return controller, client, receivers


async def idle_target(coordinator, client):
    async def disconnect():
        client.is_connected = False
        coordinator._on_disconnect(client)

    client.disconnect = AsyncMock(side_effect=disconnect)
    coordinator._cancel_disconnect_timer()
    await coordinator._async_idle_disconnect()
    assert coordinator.controller is None
    assert coordinator.client is None


@pytest.mark.parametrize("action", ("circulation", "sleep", "relax_cycle", "diagnostic"))
@pytest.mark.parametrize("release", ("idle", "unexpected"))
async def test_registered_stop_retains_automatic_intent_across_reconnect(
    hass, monkeypatch, action, release
):
    coordinator, old, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": action}, blocking=True
    )
    if release == "idle":
        await idle_target(coordinator, client)
    else:
        client.is_connected = False
        coordinator._on_disconnect(client)
        assert coordinator.controller is None
    replacement, fresh, _ = await reconnect_target(coordinator, client)
    assert replacement is not old
    assert replacement._flat_cancel_active
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    assert packets(fresh) == [app.ACTIONS["flat"].frame(IDENTITY)]
    assert not replacement._flat_cancel_active
    await idle_target(coordinator, fresh)
    _, newest, _ = await reconnect_target(coordinator, fresh)
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    assert packets(newest) == [app.ACTIONS["release"].frame(IDENTITY)]


async def test_automatic_intent_isolated_by_physical_address_and_app_profile(hass, monkeypatch):
    first = await target(hass, monkeypatch)
    second = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN,
        "agingplace_action",
        {"device_id": [first[4]], "action": "circulation"},
        blocking=True,
    )
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [second[4]]}, blocking=True)
    assert packets(second[2]) == [app.ACTIONS["release"].frame(IDENTITY)]
    assert first[1]._flat_cancel_active
    await idle_target(first[0], first[2])
    # The existing exclusive app-session contract forgets the prior profile.
    app_session(hass, first[0].address, ("other-app", "other-profile"), dict)
    replacement, fresh, _ = await reconnect_target(first[0], first[2])
    assert not replacement._flat_cancel_active
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [first[4]]}, blocking=True)
    assert packets(fresh) == [app.ACTIONS["release"].frame(IDENTITY)]


@pytest.mark.parametrize("clear", ("flat", "stop", "completion"))
async def test_owned_automatic_intent_clear_survives_controller_replacement(
    hass, monkeypatch, clear
):
    coordinator, controller, client, receivers, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "diagnostic"}, blocking=True
    )
    if clear == "completion":
        receivers[-1](None, bytearray(b'{"chkStatu":49152}'))
    else:
        service = "agingplace_action" if clear == "flat" else "stop_all"
        data = {"device_id": [device], **({"action": "flat"} if clear == "flat" else {})}
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert not controller._flat_cancel_active
    await idle_target(coordinator, client)
    _, fresh, _ = await reconnect_target(coordinator, client)
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    assert packets(fresh) == [app.ACTIONS["release"].frame(IDENTITY)]


@pytest.mark.parametrize("clear", ("flat", "stop"))
async def test_failed_flat_cannot_forget_automatic_intent(hass, monkeypatch, clear):
    coordinator, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "sleep"}, blocking=True
    )
    client.write_gatt_char.side_effect = BleakError("Flat failed")
    service = "agingplace_action" if clear == "flat" else "stop_all"
    data = {"device_id": [device], **({"action": "flat"} if clear == "flat" else {})}
    with pytest.raises((BleakError, ServiceValidationError)):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert controller._flat_cancel_active
    await idle_target(coordinator, client)
    _, fresh, _ = await reconnect_target(coordinator, client)
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    assert packets(fresh) == [app.ACTIONS["flat"].frame(IDENTITY)]


@pytest.mark.parametrize("action", ("circulation", "sleep", "relax_cycle", "diagnostic"))
async def test_cancelled_flat_before_first_write_retains_automatic_stop(hass, monkeypatch, action):
    coordinator, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": action}, blocking=True
    )
    client.write_gatt_char.reset_mock()
    original = controller.run_action
    after_flat = []

    async def preempt_flat(name):
        if name == "flat":
            coordinator.request_command_cancel()
        try:
            await original(name)
        finally:
            if name == "flat":
                after_flat.append((controller._flat_cancel_active, packets(client)))

    monkeypatch.setattr(controller, "run_action", preempt_flat)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "flat"}, blocking=True
    )
    assert after_flat == [(True, [])]
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    assert packets(client) == [app.ACTIONS["flat"].frame(IDENTITY)]
    assert not controller._flat_cancel_active


@pytest.mark.parametrize("cancel_after", ("first_chunk", "last_chunk"))
async def test_flat_requires_every_chunk_receipt_before_clearing_intent(
    hass, monkeypatch, cancel_after
):
    coordinator, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "sleep"}, blocking=True
    )
    client.write_gatt_char.reset_mock()
    flat = app.ACTIONS["flat"].frame(IDENTITY)
    chunk_bytes = len(flat) // 2
    monkeypatch.setattr(app, "CHUNK_BYTES", chunk_bytes)
    chunks = [flat[start : start + chunk_bytes] for start in range(0, len(flat), chunk_bytes)]
    writes = 0

    async def write(_char, _frame, **_kwargs):
        nonlocal writes
        writes += 1
        if writes == (1 if cancel_after == "first_chunk" else len(chunks)):
            coordinator.request_command_cancel()

    client.write_gatt_char.side_effect = write
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "flat"}, blocking=True
    )
    assert packets(client) == (chunks[:1] if cancel_after == "first_chunk" else chunks)
    assert controller._flat_cancel_active is (cancel_after == "first_chunk")
    client.write_gatt_char.reset_mock(side_effect=True)
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    expected = app.ACTIONS["flat" if cancel_after == "first_chunk" else "release"].frame(IDENTITY)
    assert b"".join(packets(client)) == expected
    assert not controller._flat_cancel_active


async def test_obsolete_diagnostic_completion_cannot_clear_new_cycle_intent(hass, monkeypatch):
    coordinator, _, client, receivers, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "diagnostic"}, blocking=True
    )
    old_receiver = receivers[-1]
    await idle_target(coordinator, client)
    replacement, fresh, new_receivers = await reconnect_target(coordinator, client)
    await hass.services.async_call(
        DOMAIN,
        "agingplace_action",
        {"device_id": [device], "action": "circulation"},
        blocking=True,
    )
    old_receiver(None, bytearray(b'{"chkStatu":49152}'))
    new_receivers[-1](None, bytearray(b'{"chkStatu":49152}'))
    assert replacement._flat_cancel_active
    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
    assert packets(fresh)[-1] == app.ACTIONS["flat"].frame(IDENTITY)


async def test_held_zero_cleanup_cannot_discharge_an_automatic_flat_obligation(hass, monkeypatch):
    coordinator, controller, client, _, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "agingplace_action", {"device_id": [device], "action": "sleep"}, blocking=True
    )
    transmitted, complete = asyncio.Event(), asyncio.Event()
    first = app.ACTIONS["head_up"].frame(IDENTITY)

    async def write(_char, frame, **_kwargs):
        if frame == first:
            transmitted.set()
            await complete.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device], "control": "head_up", "duration": 10},
            blocking=True,
        )
    )
    stopping = None
    try:
        async with asyncio.timeout(3):
            await transmitted.wait()
            stopping = asyncio.create_task(
                hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device]}, blocking=True)
            )
            await coordinator.cancel_command.wait()
            complete.set()
            await stopping
            await task
        assert packets(client) == [
            app.ACTIONS["sleep"].frame(IDENTITY),
            first,
            app.ACTIONS["release"].frame(IDENTITY),
            app.ACTIONS["flat"].frame(IDENTITY),
        ]
        assert not controller._flat_cancel_active
    finally:
        complete.set()
        pending = [operation for operation in (task, stopping) if operation is not None]
        for operation in pending:
            if not operation.done():
                operation.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.parametrize("flag", (1, 49152))
async def test_diagnostic_indications_during_start_write_keep_maxima_and_status(
    hass, monkeypatch, flag
):
    coordinator, controller, client, receivers, device = await target(hass, monkeypatch)
    await async_register_services(hass)
    transmitted, complete = asyncio.Event(), asyncio.Event()
    first = app.ACTIONS["diagnostic"].frame(IDENTITY)

    async def write(_char, frame, **_kwargs):
        if frame == first:
            transmitted.set()
            await complete.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "agingplace_action",
            {"device_id": [device], "action": "diagnostic"},
            blocking=True,
        )
    )
    try:
        async with asyncio.timeout(3):
            await transmitted.wait()
            timer = controller._diagnostic_timeout
            assert timer is not None
            timeout = timer._callback
            assert timeout is not None
            receivers[-1](None, bytearray(b'{"chkStatu":1,"headPlus":8}'))
            receivers[-1](
                None,
                bytearray(json.dumps({"chkStatu": flag, "headPlus": 2, "footPlus": 9}).encode()),
            )
            status = "complete" if flag == 49152 else "running"
            assert coordinator.controller_state[TEXT["diagnostic_status"]] == status
            complete.set()
            await task
        assert coordinator.controller_state[NUMBERS["headPlus"]] == 8
        assert coordinator.controller_state[NUMBERS["footPlus"]] == 9
        assert coordinator.controller_state[TEXT["diagnostic_status"]] == status
        if flag == 49152:
            assert timer.cancelled()
            assert controller._diagnostic_timeout is None
            assert controller._diagnostic_quiet is None
            timeout()
            assert coordinator.controller_state[TEXT["diagnostic_status"]] == "complete"
            assert not controller._flat_cancel_active
        else:
            assert controller._diagnostic_timeout is timer
            assert controller._flat_cancel_active
    finally:
        complete.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
