"""PowersBedding app routes, native HA controls, delivery and session safety."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.keeson.powersbedding import (
    LEVEL,
    PowersBeddingController,
)
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import powersbedding as app
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from scripts.wire_snapshot import FakeClock, FakeServices, virtual_time
from tests.test_controller_contract import _FactoryCoordinator

MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"


def gatt(uart=False, manufacturer=False, properties=("write",)):
    transport = codec.TRANSPORTS["ksbt" if uart else "base"]
    services = {transport.service_uuid: [transport.write_uuid]}
    services.setdefault(transport.service_uuid if uart else codec.JALON_NOTIFY_SERVICE, []).append(
        transport.notify_uuid
    )
    if manufacturer:
        services["0000180a-0000-1000-8000-00805f9b34fb"] = [MANUFACTURER]
    return FakeServices(
        {
            "services": services,
            "properties": {transport.write_uuid: properties, transport.notify_uuid: ["notify"]},
        }
    )


def make_bed(*, name="okin-Powers", manufacturer=None, properties=("write",)):
    coordinator = _FactoryCoordinator()
    coordinator.record_command_trace = MagicMock()
    coordinator.handle_controller_state_updates = lambda *updates: (
        coordinator.controller_state.update({u.key: u.value for u in updates})
    )
    coordinator.name = coordinator.ble_device_name = name
    coordinator.entry.data = {const.CONF_BLE_DEVICE_NAME: name}
    client = SimpleNamespace(
        is_connected=True,
        services=gatt(name.startswith("smartbed"), manufacturer is not None, properties),
        read_gatt_char=AsyncMock(return_value=manufacturer),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    coordinator.client = client
    bed = PowersBeddingController(coordinator)
    coordinator.controller = bed
    return coordinator, client, bed


def packets(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize(
    "name,manufacturer,route,uart",
    [
        ("okin-1", None, "p1", False),
        ("okin-1", b"other", "p1", False),
        ("okin-1", b"BLE-4.0 Module", "p2", False),
        ("smartbed-1", None, "p3", True),
        ("smartbed-1", b"other", "p1", True),
        ("smartbed-1", b"BLE-4.0 Module", "p2", True),
        ("smartbed-1", b"BLE-4.0 Module\x00", "p1", True),
    ],
)
async def test_manufacturer_changes_packet_route_without_changing_live_destination(
    name, manufacturer, route, uart
):
    _, client, bed = make_bed(name=name, manufacturer=manufacturer)
    await bed.async_discover_capabilities()
    await bed.preset_flat()
    assert packets(client) == [app.normal(route, app.PROFILES[route].presets["flat"])]
    assert (
        client.write_gatt_char.call_args.args[0].uuid
        == codec.TRANSPORTS["ksbt" if uart else "base"].write_uuid
    )
    assert bed.capability_snapshot() == {"route": route}
    assert bed.supports_massage_timer == (route == "p1")
    assert bed.supports_discrete_light_control == (route == "p1")
    assert not bed.supports_single_address_pairing


async def test_properties_missing_roles_and_changed_table_refuse_without_writes():
    for properties in ((), ("read",)):
        _, client, bed = make_bed(properties=properties)
        with pytest.raises(BedNotConnectedError):
            await bed.async_discover_capabilities()
        assert packets(client) == []
    _, client, bed = make_bed()
    await bed.async_discover_capabilities()
    client.services = gatt()
    with pytest.raises(BedNotConnectedError):
        await bed.preset_flat()
    assert packets(client) == []


@pytest.mark.parametrize(
    "route,name,manufacturer",
    [("p1", "okin-1", None), ("p2", "okin-1", b"BLE-4.0 Module"), ("p3", "smartbed-1", None)],
)
async def test_held_movement_and_programming_have_distinct_releases(route, name, manufacturer):
    _, client, bed = make_bed(name=name, manufacturer=manufacturer)
    await bed.async_discover_capabilities()
    with virtual_time(FakeClock()):
        await bed.hold_control("both_up", 250)
    assert packets(client) == [app.normal(route, w) for w in (5, 5, 5, 0, 0)]
    client.write_gatt_char.reset_mock()
    with virtual_time(FakeClock()):
        await bed.program_memory(1)
    expected = 0x20000008 if route == "p1" else 0x10000
    assert packets(client) == [app.normal(route, expected)] * (2 if route == "p1" else 60)


async def test_cancel_during_inflight_write_settles_then_sends_both_release_frames():
    coordinator, client, bed = make_bed()
    await bed.async_discover_capabilities()

    async def cancel(*args, **kwargs):
        if client.write_gatt_char.await_count == 1:
            coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = cancel
    with virtual_time(FakeClock()), pytest.raises(asyncio.CancelledError):
        await bed.hold_control("head_up", 1000)
    assert packets(client) == [app.normal("p1", w) for w in (1, 0, 0)]


async def test_p1_preset_second_tap_and_massage_sequence_are_exact():
    _, client, bed = make_bed()
    await bed.async_discover_capabilities()
    await bed.preset_memory(1)
    await bed.lights_on()
    await bed.preset_memory(1)
    assert packets(client) == [app.normal("p1", w) for w in (0x01000008, 0x31000001, 0x01000000)]
    client.write_gatt_char.reset_mock()
    clock = FakeClock()
    with virtual_time(clock):
        await bed.massage_sequence(True)
        await bed.massage_off()
    assert packets(client) == [
        app.normal("p1", w)
        for w in (
            0x10000030,
            0x11000011,
            0x11000011,
            0x10000011,
            0x10000011,
            0x10000021,
            0x10000021,
            0x11000010,
            0x11000010,
            0x10000010,
            0x10000010,
            0x10000020,
            0x10000020,
        )
    ]
    assert clock.now == pytest.approx(0.5)


async def test_stale_callback_and_retained_link_restart_are_fenced():
    coordinator, client, bed = make_bed(name="smartbed-1")
    await bed.async_discover_capabilities()
    await bed.start_notify()
    old = client.start_notify.call_args.args[1]
    notify = bed._live().notify
    old(notify, bytearray.fromhex("a50b00000100010204"))
    assert coordinator.controller_state[LEVEL["head"]] == 1
    await bed.stop_notify()
    old(notify, bytearray.fromhex("a50b00000100010808"))
    assert coordinator.controller_state[LEVEL["head"]] is None
    await bed.async_resume_session()
    assert client.start_notify.await_count == 2
    bed.on_disconnect()
    old(notify, bytearray.fromhex("a50b00000100010808"))
    assert coordinator.controller_state[LEVEL["head"]] is None
    with pytest.raises(BedNotConnectedError):
        await bed.preset_flat()


async def test_p3_massage_followup_and_alarm_reply_stop_are_owned_and_bounded():
    _, client, bed = make_bed(name="smartbed-1")
    await bed.async_discover_capabilities()
    await bed.start_notify()
    with virtual_time(FakeClock()):
        await bed.massage_step("head_up")
    assert packets(client) == [app.normal("p3", 0x800), b"\x00\xb0"]
    receive = client.start_notify.call_args.args[1]
    notify = bed._live().notify
    client.write_gatt_char.reset_mock()

    async def reply(char, packet, **kwargs):
        if packet == b"\x00\xc0":
            receive(notify, bytearray.fromhex("a50c0000be05071e0001"))

    client.write_gatt_char.side_effect = reply
    with virtual_time(FakeClock()):
        await bed.query_alarm()
    assert packets(client) == [b"\x00\xc0", app.normal("p3", 0)]
    receive(
        notify, bytearray.fromhex("a50c")
    )  # No unsolicited STOP outside the read's ownership window.
    await asyncio.sleep(0)
    assert len(packets(client)) == 2
    await bed.stop_notify()


async def test_native_setup_entities_service_and_sent_state(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    mock_async_ble_device_from_address.return_value.name = "okin-Powers"
    address = "AA:BB:CC:DD:15:50"
    mock_bleak_client.services = gatt()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="PowersBedding",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "PowersBedding",
            const.CONF_BLE_DEVICE_NAME: "okin-Powers",
            const.CONF_BED_TYPE: "powersbedding",
            const.CONF_HAS_MASSAGE: True,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    bed = coordinator.controller
    assert isinstance(bed, PowersBeddingController)
    assert entry.data["capabilities"]["powersbedding"] == {"route": "p1"}
    registry = er.async_get(hass)
    light = registry.async_get_entity_id("light", const.DOMAIN, f"{address}_under_bed_lights")
    timer = registry.async_get_entity_id("select", const.DOMAIN, f"{address}_massage_timer")
    level = registry.async_get_entity_id(
        "number", const.DOMAIN, f"{address}_controller_number_powersbedding_head"
    )
    assert light and timer and level
    try:
        mock_bleak_client.write_gatt_char.reset_mock()
        with virtual_time(FakeClock()):
            await hass.services.async_call("light", "turn_on", {"entity_id": light}, blocking=True)
            await hass.services.async_call(
                "select", "select_option", {"entity_id": timer, "option": "20 min"}, blocking=True
            )
            await hass.services.async_call(
                "number", "set_value", {"entity_id": level, "value": 3}, blocking=True
            )
        assert hass.states.get(light).state == "on"
        assert hass.states.get(timer).state == "20 min"
        assert float(hass.states.get(level).state) == 3
        assert hass.states.get(level).attributes["assumed_state"] is True
        assert hass.states.get(timer).attributes["assumed_state"] is True
        assert coordinator.controller_state[MASSAGE_TIMER_MINUTES] == 20
        assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True
        assert packets(mock_bleak_client) == [
            app.normal("p1", w) for w in (0x31000001, 0x10000031, 0x10000013)
        ]
        mock_bleak_client.write_gatt_char.side_effect = BleakError("failed")
        with virtual_time(FakeClock()), pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": level, "value": 2}, blocking=True
            )
        assert coordinator.controller_state[LEVEL["head"]] == 3
    finally:
        mock_bleak_client.write_gatt_char.side_effect = None
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_owns_layout_and_side_settings_and_public_preflight():
    from homeassistant.util import dt as dt_util

    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES

    coordinator, client, _ = make_bed()
    bed = await create_controller(coordinator, "powersbedding", "auto", client)
    assert isinstance(bed, PowersBeddingController)
    assert SETUP_PROFILES["powersbedding"].owns[const.CONF_MOTOR_COUNT] == 2
    assert const.CONF_BLE_DEVICE_NAME in per_side_profile("powersbedding", None).keys
    assert bed.execution.declared == {"hold"}
    for bad in (
        AlarmRequest(enabled=True, hour=24, reference_time=dt_util.now()),
        AlarmRequest(enabled=True, wake_action="flat", reference_time=dt_util.now()),
    ):
        with pytest.raises(ServiceValidationError):
            bed.validate_alarm(bad)
    assert packets(client) == []


async def test_level_and_timer_intent_settle_when_final_write_is_cancelled():
    coordinator, client, bed = make_bed()
    await bed.async_discover_capabilities()

    async def cancel(*args, **kwargs):
        coordinator.cancel_command.set()

    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
    )

    context = CommandContext(
        scheduler_token=object(),
        cancel_event=coordinator.cancel_command,
        admitted_stop_epoch=0,
        intent_id="delivery",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        client.write_gatt_char.side_effect = cancel
        with pytest.raises(asyncio.CancelledError):
            await bed.set_level("head", 3)
        assert bed.persisted_app_state["head"] == 3
        assert coordinator.controller_state[LEVEL["head"]] == 3
        coordinator.cancel_command.clear()
        with pytest.raises(asyncio.CancelledError):
            await bed.set_massage_timer(20)
        assert bed._timer_level == 2
        assert coordinator.controller_state[MASSAGE_TIMER_MINUTES] == 20
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)


async def test_changed_session_during_manufacturer_read_cannot_replace_new_link():
    _, client, bed = make_bed(manufacturer=b"BLE-4.0 Module")
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed_read(*args):
        started.set()
        await finish.wait()
        return b"BLE-4.0 Module"

    client.read_gatt_char.side_effect = delayed_read
    old = asyncio.create_task(bed.async_discover_capabilities())
    await started.wait()
    client.read_gatt_char.side_effect = None
    await bed.async_discover_capabilities()
    current = bed._live()
    finish.set()
    with pytest.raises(BedNotConnectedError):
        await old
    assert bed._live() is current


@pytest.mark.parametrize(
    "route,name,manufacturer",
    [("p1", "okin-1", None), ("p2", "okin-1", b"BLE-4.0 Module"), ("p3", "smartbed-1", None)],
)
async def test_alarm_duplicate_schedule_clock_and_read_sequence(route, name, manufacturer, freezer):
    from homeassistant.util import dt as dt_util

    freezer.move_to("2026-11-27 06:45:30+00:00")
    _, client, bed = make_bed(name=name, manufacturer=manufacturer)
    await bed.async_discover_capabilities()
    now = dt_util.now()
    request = AlarmRequest(
        enabled=True,
        hour=7,
        minute=30,
        weekdays=(0, 1, 2, 3, 4),
        wake_action="memory_1",
        reference_time=now,
    )
    with virtual_time(FakeClock()):
        await bed.configure_alarm(request)
    massage, mode = app.wake_mode(route, "memory_1", False)
    frame = app.alarm_fields(route, 7, 30, -66, massage, mode, now)
    expected = [frame, frame, app.clock(route, now)]
    if (query := app.alarm_query(route)) is not None:
        expected.append(query)
    assert packets(client) == expected


async def test_reconnect_persists_new_route_and_reconciles_controls(
    hass, mock_coordinator_connected, mock_bleak_client,
    mock_async_ble_device_from_address, enable_custom_integrations,
):
    address = "AA:BB:CC:DD:15:59"
    mock_async_ble_device_from_address.return_value.name = "okin-Powers"
    mock_bleak_client.services = gatt()
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="PowersBedding", unique_id=address,
        data={CONF_ADDRESS: address, CONF_NAME: "PowersBedding",
              const.CONF_BED_TYPE: "powersbedding", const.CONF_BLE_DEVICE_NAME: "okin-Powers",
              const.CONF_HAS_MASSAGE: True, const.CONF_DISABLE_ANGLE_SENSING: True,
              const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    try:
        assert entry.data["capabilities"]["powersbedding"] == {"route": "p1"}
        assert await coordinator.async_disconnect("intentional")
        mock_bleak_client.services = gatt(False, True)
        mock_bleak_client.read_gatt_char = AsyncMock(return_value=b"BLE-4.0 Module")
        assert await coordinator.async_connect()
        assert coordinator.controller._live_route() == "p2"
        assert entry.data["capabilities"]["powersbedding"] == {"route": "p2"}
        assert await coordinator.async_disconnect("intentional")
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        assert registry.async_get_entity_id(
            "button", const.DOMAIN, f"{address}_powersbedding_toggle"
        ) is not None
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
