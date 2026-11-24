"""Simmons Blue layout, link and action behavior through the shared integration."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.simmons_blue import SimmonsBlueController
from custom_components.adjustable_bed.button import _combined_button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_SIMMONS_BLUE,
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_new_bed,
)
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data
from custom_components.adjustable_bed.profiles import simmons_blue as app
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_shared_action_hardening import beds, set_alarm

_BALANCE = ("first_up", "first_down")
_MOTION = (*_BALANCE, "second_up", "second_down", "flat", "relax", "tv", "anti_snore")
_COMBINED = (*_MOTION, "combined_up", "combined_down")

NOW = datetime(2026, 11, 24, 13, 45, 6)
CLOCK = bytes.fromhex("05 02 07 04 1a 0b 18 02 0d 2d 06 00")
ALARM_2 = bytes.fromhex("a5 0d 00 00 82 06 08 0f 00 01")
DISABLE_2 = bytes.fromhex("05 02 07 06 00 09 08 0f 00 00 00 00")
QUERY_2 = b"\x00\xd0"
STOP = bytes.fromhex("05 02 00 00 00 00 00")


def _roles(client: MagicMock) -> tuple[MagicMock, MagicMock]:
    write = MagicMock(uuid=NORDIC_UART_WRITE_CHAR_UUID, properties=["write"])
    notify = MagicMock(uuid=NORDIC_UART_READ_CHAR_UUID, properties=["indicate"])
    client.services = [MagicMock(uuid=NORDIC_UART_SERVICE_UUID, characteristics=[write, notify])]
    return write, notify


def _frames(client: MagicMock) -> list[bytes]:
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


def _coordinator() -> MagicMock:
    client = MagicMock(is_connected=True)
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    _roles(client)
    return MagicMock(client=client, cancel_command=asyncio.Event(), motor_pulse_count=5)


async def _connected(coordinator: MagicMock, layout: str) -> SimmonsBlueController:
    controller = SimmonsBlueController(coordinator, app.LAYOUTS[layout])
    await controller.async_discover_capabilities()
    return controller


@pytest.mark.parametrize(
    ("layout", "held"),
    (
        ("balance", _BALANCE),
        ("motion2", _MOTION),
        ("motion3", _COMBINED),
        ("motion4", (*_COMBINED, "incline")),
    ),
)
async def test_setup_layout_reaches_controller(layout, held):
    data = {CONF_BED_TYPE: BED_TYPE_SIMMONS_BLUE, CONF_PRODUCT_TYPE: layout}
    setup = setup_profile_for(data)
    assert setup is not None
    assert setup.questions[0].key == CONF_PRODUCT_TYPE
    assert set(setup.questions[0].options(data) or ()) == {
        "balance",
        "motion2",
        "motion3",
        "motion4",
    }
    assert BED_TYPE_DISPLAY_NAMES[BED_TYPE_SIMMONS_BLUE] == "Simmons Blue app"
    side = per_side_profile(BED_TYPE_SIMMONS_BLUE, None)
    assert side is not None and CONF_PRODUCT_TYPE in side.keys

    coordinator = _coordinator()
    coordinator.entry.data = data
    coordinator.hass.async_add_import_executor_job = AsyncMock(
        side_effect=lambda fn, *args: fn(*args)
    )
    controller = await create_controller(coordinator, BED_TYPE_SIMMONS_BLUE, None, None)
    assert isinstance(controller, SimmonsBlueController)
    assert controller.held_control_options == held
    assert controller.execution.hold == "stream"
    assert not controller.execution.concurrent
    assert not controller.supports_single_address_pairing
    assert controller.memory_slot_count == 2
    assert not controller.supports_discrete_light_control
    assert not controller.supports_motor_control
    assert controller.standard_button_hold_spec("program_memory_1") is None

    specs = {spec.key: spec for spec in controller.controller_button_specs}
    assert specs["first_up"].card.attributes == {
        "card_section": "motors",
        "card_role": "up",
        "card_motor": "first_section",
    }
    assert specs["refresh_alarms"].diagnostic
    assert ("combined_up" in specs) == (layout in {"motion3", "motion4"})
    assert ("incline" in specs) == (layout == "motion4")


def test_shared_smartbed_name_is_only_an_app_choice():
    device = MagicMock(name="SmartBed Blue")
    device.name = "sMaRtBeD Blue"
    info = MagicMock(
        device=device,
        service_uuids=[],
        manufacturer_data={},
        service_data={},
        address="AA:BB:CC:DD:EE:FF",
    )
    info.name = "SmartBed Blue"
    result = detect_new_bed(info)
    assert BED_TYPE_SIMMONS_BLUE in result.ambiguous_types
    assert result.bed_type != BED_TYPE_SIMMONS_BLUE
    device.name = info.name = "Other SmartBed"
    assert BED_TYPE_SIMMONS_BLUE not in (detect_new_bed(info).ambiguous_types or ())


def test_combined_entry_preserves_each_layout():
    pair = build_pair_entry_data(
        {
            CONF_BED_TYPE: BED_TYPE_SIMMONS_BLUE,
            CONF_PRODUCT_TYPE: "balance",
            CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        },
        {
            CONF_BED_TYPE: BED_TYPE_SIMMONS_BLUE,
            CONF_PRODUCT_TYPE: "motion4",
            CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        },
        name="Simmons pair",
    )
    stale_parent_options = {CONF_PRODUCT_TYPE: "motion2"}
    assert effective_child_data(pair, "left", stale_parent_options)[CONF_PRODUCT_TYPE] == "balance"
    assert effective_child_data(pair, "right", stale_parent_options)[CONF_PRODUCT_TYPE] == "motion4"


async def test_session_subscribes_before_clock_and_rejects_old_notifications(monkeypatch):
    coordinator = _coordinator()
    controller = await _connected(coordinator, "balance")
    client = coordinator.client
    notify = client.services[0].characteristics[1]
    client.start_notify.side_effect = [TimeoutError("first"), BleakError("second"), None]

    def write(*_args, **_kwargs):
        assert client.start_notify.await_count == 3

    client.write_gatt_char.side_effect = write
    session = MagicMock(async_start_notify=controller.start_notify, is_current=lambda: True)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.simmons_blue.dt_util.now", lambda: NOW
    )

    await controller.async_on_connect(session)
    client.write_gatt_char.assert_awaited_once_with(
        client.services[0].characteristics[0],
        CLOCK,
        response=True,
    )
    callback = client.start_notify.await_args.args[1]
    callback(notify, bytearray.fromhex("a5 0d 00"))
    coordinator.handle_controller_state_updates.assert_not_called()
    callback(notify, bytearray(ALARM_2))
    assert controller.persisted_app_state == {"2": [0x82, 6, 8, 15, 1]}

    controller.on_disconnect()
    callback(notify, bytearray(10))
    callback(notify, bytearray.fromhex("a5 0d 00 00 00 09 08 0f 00 00"))
    coordinator.handle_controller_state_updates.assert_called_once()
    assert controller.persisted_app_state == {"2": [0x82, 6, 8, 15, 1]}


async def test_gatt_requires_both_roles_under_the_same_service():
    coordinator = _coordinator()
    service = coordinator.client.services[0]
    service.characteristics[0].properties = ["write-without-response"]
    controller = SimmonsBlueController(coordinator, app.LAYOUTS["balance"])
    with pytest.raises(BedNotConnectedError, match="write and notification channels"):
        await controller.async_discover_capabilities()


async def test_flat_and_light_are_single_writes_on_balance():
    coordinator = _coordinator()
    controller = await _connected(coordinator, "balance")
    await controller.preset_flat()
    await controller.lights_toggle()
    assert _frames(coordinator.client) == [
        bytes.fromhex("05 02 08 00 00 00 00"),
        bytes.fromhex("05 02 00 02 00 00 00"),
    ]


async def test_cancelled_write_settles_before_stop_and_other_side_continues():
    left, right = _coordinator(), _coordinator()
    first = await _connected(left, "motion4")
    second = await _connected(right, "motion2")
    entered, allow_write = asyncio.Event(), asyncio.Event()

    async def slow_write(_char: object, frame: bytes, *, response: bool) -> None:
        assert response
        if frame != STOP:
            entered.set()
            await allow_write.wait()

    left.client.write_gatt_char.side_effect = slow_write
    hold = asyncio.create_task(first.hold_control("incline", 60_000))
    await entered.wait()
    hold.cancel()
    await asyncio.sleep(0)
    assert _frames(left.client) == [bytes.fromhex("05 02 00 00 00 10 00")]

    await second.hold_control("second_up", 1)
    assert _frames(right.client) == [bytes.fromhex("05 02 00 00 00 04 00"), STOP]
    allow_write.set()
    with pytest.raises(asyncio.CancelledError):
        await hold
    assert _frames(left.client) == [bytes.fromhex("05 02 00 00 00 10 00"), STOP]


async def test_stop_never_moves_to_a_new_client():
    coordinator = _coordinator()
    controller = await _connected(coordinator, "motion3")
    old_client, new_client = coordinator.client, _coordinator().client

    async def disconnect(*_args, **_kwargs):
        controller.on_disconnect()
        coordinator.client = new_client
        await controller.async_discover_capabilities()

    old_client.write_gatt_char.side_effect = disconnect
    with pytest.raises(BedNotConnectedError):
        await controller.hold_control("combined_up", 1000)
    assert _frames(old_client) == [bytes.fromhex("05 02 00 00 00 50 00")]
    new_client.write_gatt_char.assert_not_awaited()


async def test_hold_that_expires_waiting_for_gatt_never_starts():
    coordinator = _coordinator()
    controller = await _connected(coordinator, "motion2")
    with virtual_clock():
        async with controller.ble_lock:
            hold = asyncio.create_task(controller.hold_control("second_up", 100))
            await asyncio.sleep(0)
            await asyncio.sleep(0.2)
        await hold
    assert _frames(coordinator.client) == [STOP]


async def test_disable_preserves_fresh_time_and_queries_same_slot():
    coordinator = _coordinator()
    controller = await _connected(coordinator, "motion2")
    await controller.start_notify()
    client = coordinator.client
    callback = client.start_notify.await_args.args[1]
    notify = client.services[0].characteristics[1]

    def reply(_char, data, *, response):
        assert response
        if data == QUERY_2:
            callback(notify, bytearray(ALARM_2))

    client.write_gatt_char.side_effect = reply
    request = AlarmRequest(enabled=False, slot=2, reference_time=NOW)
    await controller.check_alarm(request)
    await controller.configure_alarm(request)
    assert _frames(client) == [QUERY_2, DISABLE_2, QUERY_2]
    with pytest.raises(ServiceValidationError, match="slot"):
        await controller.configure_alarm(AlarmRequest(enabled=False, slot=0, reference_time=NOW))
    assert _frames(client) == [QUERY_2, DISABLE_2, QUERY_2]


async def test_native_alarm_action_targets_one_physical_side(hass):
    async with beds(hass, topology="concurrent") as pair:
        for bed, layout in zip(pair.items, ("balance", "motion4"), strict=True):
            client = bed.client
            _roles(client)
            client.write_gatt_char = AsyncMock()
            controller = SimmonsBlueController(bed, app.LAYOUTS[layout])
            await controller.async_discover_capabilities()
            bed._controller = controller
        with virtual_clock():
            await set_alarm(
                hass, [(pair.pair, "right")], slot=1, weekdays=["monday"], wake_action="memory_1"
            )
        left, right = pair.items
        assert _frames(left.client) == []
        assert _frames(right.client) == [
            bytes.fromhex("05 02 07 05 82 05 07 1e 00 01 00 00"),
            bytes.fromhex("00 c0"),
        ]


async def test_alarm_report_after_ack_updates_display_and_persistence():
    coordinator = _coordinator()
    controller = await _connected(coordinator, "motion2")
    await controller.start_notify()
    client = coordinator.client
    notify = client.services[0].characteristics[1]
    callback = client.start_notify.await_args.args[1]
    query_written = asyncio.Event()

    def write(_char, data, *, response):
        assert response
        if data == QUERY_2:
            query_written.set()

    client.write_gatt_char.side_effect = write
    request = AlarmRequest(
        enabled=True, slot=2, wake_action="memory_2", hour=8, minute=15, reference_time=NOW
    )
    task = asyncio.create_task(controller.configure_alarm(request))
    await query_written.wait()
    await asyncio.sleep(0)
    assert not task.done()
    assert controller.persisted_app_state == {}
    callback(notify, bytearray(ALARM_2))
    await task
    assert controller.persisted_app_state == {"2": [0x82, 6, 8, 15, 1]}
    coordinator.handle_controller_state_updates.assert_called_once()


async def test_sequential_stop_reconnects_for_e_balance_flat(hass):
    async with beds(hass, topology="sequential", connected=False) as made:
        pair = made.pair
        assert pair is not None
        bed = made.items[0]
        bed._offline_controller = SimmonsBlueController(bed, app.LAYOUTS["balance"])
        clients = []

        async def connect(**kwargs):
            if bed.is_connected:
                return True
            if not await bed.fake_connect(**kwargs):
                return False
            client = bed.client
            clients.append(client)
            _roles(client)
            client.write_gatt_char = AsyncMock()
            client.stop_notify = AsyncMock()
            controller = SimmonsBlueController(bed, app.LAYOUTS["balance"])
            await controller.async_discover_capabilities()
            bed._controller = controller
            return True

        bed.async_ensure_connected.side_effect = connect
        bed.async_connect.side_effect = connect
        with virtual_clock():
            await pair.async_execute_controller_command(
                lambda ctrl: ctrl.preset_flat(), side="left"
            )
            assert not bed.is_connected
            await pair.async_stop_command(side="left")
        assert [_frames(client) for client in clients] == [
            [bytes.fromhex("05 02 08 00 00 00 00")],
            [STOP],
        ]
        assert not bed.is_connected
        assert not made.items[1].is_connected


async def test_combined_buttons_offer_only_shared_controls(hass):
    async with beds(hass, topology="concurrent") as made:
        pair = made.pair
        assert pair is not None
        for bed, layout in zip(made.items, ("balance", "motion4"), strict=True):
            client = bed.client
            _roles(client)
            client.write_gatt_char = AsyncMock()
            controller = SimmonsBlueController(bed, app.LAYOUTS[layout])
            await controller.async_discover_capabilities()
            bed._controller = controller

        buttons = {
            item.unique_id: item
            for item in _combined_button_entities_for(pair, list(pair.children.values()))
        }
        first = buttons[pair.entity_unique_id("first_up_both")]
        assert first.capability_attributes["card_motor"] == "first_section"
        assert first.extra_state_attributes["held_control"] == "first_up"
        assert pair.entity_unique_id("incline_both") not in buttons
        assert any(
            spec.key == "incline" for spec in made.items[1].controller.controller_button_specs
        )
        first.hass = hass
        with virtual_clock():
            await first.async_press()
        rise = bytes.fromhex("05 02 00 00 00 01 00")
        for bed in made.items:
            assert _frames(bed.client) == [rise] * bed.motor_pulse_count + [STOP]
