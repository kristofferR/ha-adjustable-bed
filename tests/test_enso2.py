"""Enso 2 transport selection, layout gates and connection-owned END delivery."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.enso2 import receive as rx
from custom_components.adjustable_bed.beds.enso2.controller import Enso2Controller, _select_link
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import enso2 as app
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock


def service(transport, *, incomplete=False):
    write = SimpleNamespace(
        uuid=transport.write_uuid,
        handle=5,
        properties=["write-without-response"],
    )
    notify = SimpleNamespace(uuid=transport.notify_uuid, handle=6, properties=["notify"])
    by_uuid = {write.uuid: write} if incomplete else {write.uuid: write, notify.uuid: notify}
    return SimpleNamespace(
        uuid=transport.service_uuid,
        characteristics=list(by_uuid.values()),
        get_characteristic=by_uuid.get,
    )


async def bed(layout="E3RM", route=0, *, name=None):
    client = SimpleNamespace(
        services=[service(app.TRANSPORTS[route])],
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        is_connected=True,
        write_gatt_char=AsyncMock(),
    )
    state = {}
    coordinator = SimpleNamespace(
        address="AA:BB:CC:DD:EE:FF",
        bed_type="enso2",
        client=client,
        cancel_command=asyncio.Event(),
        record_command_trace=Mock(),
        save_app_state=Mock(),
        handle_controller_state_updates=lambda *updates: state.update(
            (update.key, update.value) for update in updates
        ),
        name="Test bed",
    )
    controller = Enso2Controller(coordinator, app.LAYOUTS[layout], name or layout)
    coordinator._controller = controller
    coordinator._offline_controller = None
    coordinator.cache_capability_controller = partial(
        AdjustableBedCoordinator.cache_capability_controller, coordinator
    )
    await controller.async_discover_capabilities()
    return controller, coordinator, client, state


def frames(client):
    return [args.args[1].hex() for args in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("route", range(4))
def test_fixed_role_order_and_missing_characteristic_block_fallback(route):
    expected = app.TRANSPORTS[route]
    earlier = service(expected)
    client = SimpleNamespace(
        services=[*map(service, reversed(app.TRANSPORTS[route + 1 :])), earlier]
    )
    link = _select_link(client, True)
    assert link.write.uuid == expected.write_uuid
    assert link.raw is expected.single
    client.services[-1] = service(expected, incomplete=True)
    with raises_key("enso2_gatt_missing"):
        _select_link(client, True)


def test_property_fallback_requires_opt_in_and_selects_exact_third_service():
    command = service(app.TRANSPORTS[1])
    command.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
    fallback = service(app.TRANSPORTS[2])
    fallback.uuid = "bed-specific-service"
    client = SimpleNamespace(services=[object(), object(), fallback])
    client.services[:2] = [SimpleNamespace(uuid=str(i)) for i in (0, 1)]
    with raises_key("enso2_gatt_missing"):
        _select_link(client, False)
    assert _select_link(client, True).write is fallback.characteristics[0]
    client.services[2] = command
    with raises_key("enso2_gatt_missing"):
        _select_link(client, True)


@pytest.mark.parametrize(
    ("route", "steps"),
    [
        (0, ["6e02010071", "6e08010178", "6e0a000179", "6e1a000088"]),
        (2, ["6e08010178", "6e0a000179", "6e1a000088"]),
    ],
)
async def test_current_layout_admits_startup_alarm_query(route, steps):
    controller, _, client, _ = await bed("A9RM", route)
    with virtual_clock():
        await controller.async_on_connect(None)
    assert frames(client) == steps
    assert client.start_notify.await_args.args[0] is client.services[0].characteristics[1]
    controller, _, client, _ = await bed("E3RM", route)
    with virtual_clock():
        await controller.async_on_connect(None)
    assert "6e08010178" not in frames(client)
    assert controller.alarm_capability is None


@pytest.mark.parametrize(
    ("route", "recall", "save", "end"),
    [(0, "6e01002e9d", "6e01002b9a", "6e01006edd"), (2, "2e", "2b", "6e")],
)
async def test_e3rm_program_has_independent_payload_and_cleanup(route, recall, save, end):
    controller, coordinator, client, _ = await bed(route=route)
    recall_button = next(
        item for item in controller.controller_button_specs if item.key == "enso2_memory_1"
    )
    save_button = next(
        item
        for item in controller.controller_button_specs
        if item.key == "enso2_memory_1_alternate"
    )
    assert recall_button.hold is not None
    assert save_button.hold is None and save_button.requires_confirmation
    with virtual_clock():
        await controller.hold_control("memory_1", 301)
        await save_button.press_fn(controller)
    assert frames(client) == [recall] * 3 + [end, save, end]

    async def stop_after_delivery(*args, **kwargs):
        coordinator.cancel_command.set()

    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = stop_after_delivery
    with virtual_clock():
        await controller.hold_control("memory_1", 1000)
    assert frames(client) == [recall, end]


async def test_task_cancellation_waits_for_in_flight_write_then_releases():
    controller, _, client, _ = await bed()
    started = asyncio.Event()
    resume = asyncio.Event()

    async def pause_write(_characteristic, data, *, response):
        if data.hex() == "6e01002e9d":
            started.set()
            await resume.wait()

    client.write_gatt_char.side_effect = pause_write
    with virtual_clock():
        operation = asyncio.create_task(controller.hold_control("memory_1", 1000))
        await started.wait()
        operation.cancel()
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
    assert frames(client) == ["6e01002e9d", "6e01006edd"]


async def test_end_never_writes_to_replacement_connection():
    controller, coordinator, client, _ = await bed()
    replacement = await bed()

    async def replace_link(*args, **kwargs):
        controller.on_disconnect()
        coordinator.client = replacement[2]
        await controller.async_discover_capabilities()
        coordinator.cancel_command.set()

    client.write_gatt_char.side_effect = replace_link
    with virtual_clock():
        await controller.hold_control("memory_1", 1000)
    assert frames(client) == ["6e01002e9d"]
    assert frames(replacement[2]) == []


async def test_u3rm_selector_and_numbered_framed_mode():
    controller, _, client, _ = await bed("U3RM")
    with virtual_clock():
        await controller.hold_control("selected_motor_up", 100)
        await controller.press("lounge", alternate=True)
        await controller.hold_control("selected_motor_up", 100)
    assert frames(client) == [
        "6e01003fae",
        "6e01006edd",
        "6e010065d4",
        "6e01006edd",
        "6e010071e0",
        "6e01006edd",
    ]

    controller, _, client, _ = await bed("BTRM")
    await controller.set_mode("mode_3")
    with virtual_clock():
        await controller.hold_control("motor_1_up", 100)
    assert frames(client) == ["6e01022495", "6e01026edf"]
    controller, _, _, _ = await bed("BTRM", 2)
    with raises_key("enso2_control_unavailable"):
        await controller.set_mode("mode_3")


async def test_layout_gates_hold_alt_program_and_gvrm_alternate_zone():
    controller, _, client, _ = await bed("YFRM")
    assert "memory_1" not in controller.held_control_options
    assert not any(spec.key == "enso2_save_memory_1" for spec in controller.controller_button_specs)
    with virtual_clock():
        await controller.press("press_and_hold")
        assert "memory_1" in controller.held_control_options
        await controller.program_memory(1)
        await controller.hold_control("memory_1", 100)
    assert frames(client) == [
        "6e01002291",
        "6e01006edd",
        "6e01002b9a",
        "6e01006edd",
        "6e01002e9d",
        "6e01006edd",
    ]
    controller, _, client, _ = await bed("GVRM")
    assert "memory_1" not in controller.held_control_options
    with virtual_clock():
        await controller.hold_control("head_adjustment_up", 100)
    assert frames(client) == ["6e010031a0", "6e01006edd"]


async def test_alarm_uses_layout_and_synthesizes_two_massage_zones(monkeypatch):
    controller, _, client, _ = await bed("A9RM")
    alarm = AlarmRequest(
        enabled=True,
        hour=22,
        minute=31,
        wake_action="tv",
        massage_zone="both",
        reference_time=datetime(2026, 7, 14, 22, 30, tzinfo=UTC),
    )
    monkeypatch.setattr(dt_util, "now", lambda: alarm.reference_time)
    with raises_key("enso2_alarm_unavailable"):
        await controller.check_alarm(alarm)
    await controller.start_notify()
    sender, callback = client.start_notify.await_args.args
    callback(sender, bytearray.fromhex("6e0901"))
    callback(sender, bytearray.fromhex("0078"))
    with virtual_clock():
        await controller.configure_alarm(alarm)
    assert frames(client) == ["6e05010074", "6e060077eb"]


@pytest.mark.parametrize(
    ("start", "now", "hour", "minute", "enabled", "countdown"),
    [
        ("2026-03-29T00:30", "2026-03-29T00:30", 2, 30, True, "6e053c00af"),
        ("2026-10-25T00:30", "2026-10-25T00:30", 2, 30, True, "6e05b40027"),
        ("2026-10-25T01:45", "2026-10-25T01:45", 1, 30, True, "6e052d00a0"),
        ("2026-07-14T06:00", "2026-07-14T06:02", 6, 5, True, "6e05030076"),
        ("2026-03-29T00:30", "2026-03-29T00:30", 2, 30, False, "6e05000073"),
    ],
    ids=["spring-forward", "fall-back", "repeated-hour", "connection-delay", "disable"],
)
async def test_alarm_counts_real_minutes_to_the_selected_occurrence(
    monkeypatch, start, now, hour, minute, enabled, countdown
):
    zone = ZoneInfo("Europe/London")
    alarm = AlarmRequest(
        enabled=enabled,
        hour=hour,
        minute=minute,
        wake_action="tv",
        reference_time=datetime.fromisoformat(start).replace(tzinfo=zone),
    )
    monkeypatch.setattr(dt_util, "now", lambda: datetime.fromisoformat(now).replace(tzinfo=zone))
    controller, _, client, _ = await bed("A9RM")
    controller._received(rx.ALARM_PRESENT)
    with virtual_clock():
        await controller.configure_alarm(alarm)
    assert frames(client) == [countdown, "6e060058cc" if enabled else "6e06000074"]


def test_receiver_recovers_from_noise_bad_checksums_and_combined_notifications():
    receiver = rx.Receiver()
    assert receiver.feed(bytes.fromhex("ab6e090100796e0e00")) == ()
    assert receiver.feed(bytes.fromhex("037f6e1a000189")) == (rx.LIGHT_ON, rx.AROMA_PRESENT)
    assert receiver.feed(bytes.fromhex("6e9000000732376e07010177")) == (rx.ALARM_SET,)


def test_name_aliases_are_suggestions_and_known_shared_names_stay_ambiguous():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    assert app.advertised_layout("MPE_HJ006-1") == "BNRM"
    assert app.advertised_layout("200IV2") == "A8RM"
    assert app.advertised_layout("B6RU") is None
    assert app.advertised_layout("L&P ADJBED") is None
    assert app.advertised_layout(" 6BRM") is None
    assert app.advertised_layout("Cool Touch") is not None
    assert app.advertised_layout("209A05") is None
    assert app.setup_choices("ZRS0")["B8TT"] == "B8TT (ZRS0)"
    assert not app.EXCLUDED_CODES.intersection(app.LAYOUT_CHOICES)
    info = SimpleNamespace(
        name="6BRM",
        service_uuids=[app.TRANSPORTS[0].service_uuid],
        manufacturer_data={},
        address="AA:BB:CC:DD:EE:FF",
        bed_type="enso2",
        service_data={},
        source="test",
        connectable=True,
    )
    result = detect_bed_type_detailed(info)
    assert result.bed_type != "enso2"
    assert "enso2" in result.ambiguous_types


async def test_accessories_use_live_capability_and_fixed_frames_on_raw_routes():
    controller, _, client, state = await bed("D9RM", 2)
    with raises_key("enso2_light_unavailable"):
        await controller.set_light_color((18, 52, 86))
    with raises_key("enso2_aroma_unavailable"):
        await controller.set_aroma(60, 1, 12)
    await controller.start_notify()
    sender, callback = client.start_notify.await_args.args
    callback(sender, bytearray.fromhex("6e0e00037f6e1a000189"))
    assert state["under_bed_lights_on"] is True
    with virtual_clock():
        await controller.set_light_color((18, 52, 86))
        await controller.set_light_duration(300)
        await controller.set_aroma(60, 1, 12)
        await controller.set_timer_position(0)
    assert frames(client) == [
        "6e0cff128b6e0d345605",
        "6e0b012ca6",
        "6e1b003cc5",
        "6e1c00018b",
        "6e1d000c97",
        "6e01008bfa",
    ]
    controller.on_disconnect()
    callback(sender, bytearray.fromhex("6e0e00037f"))
    assert state["under_bed_lights_on"] is None


async def test_u3rm_restores_the_selected_motor_after_a_ble_handoff():
    controller, coordinator, _, _ = await bed("U3RM")
    with virtual_clock():
        await controller.press("lounge")
    coordinator.save_app_state.assert_called_once_with(controller)

    reconnected, _, client, _ = await bed("U3RM")
    reconnected.restore_persisted_app_state(controller.persisted_app_state)
    with virtual_clock():
        await reconnected.hold_control("selected_motor_up", 100)
    assert frames(client) == ["6e010071e0", "6e01006edd"]


async def test_raw_legacy_action_uses_its_own_label_and_payload():
    framed, _, _, _ = await bed("ONRM")
    raw, _, client, _ = await bed("ONRM", 2)

    key = "enso2_massage_timer_10_minutes"
    assert any(button.key == key for button in framed.controller_button_specs)
    assert not raw.controller_button_available(key)
    massage_off = next(
        button for button in raw.controller_button_specs if button.key == "enso2_massage_off"
    )
    assert massage_off.name == "Massage off"
    with virtual_clock():
        await massage_off.press_fn(raw)
    assert frames(client) == ["39", "6e"]


async def test_opted_in_read_only_response_role_keeps_raw_keys():
    _, coordinator, client, _ = await bed(route=2)
    third = service(app.TRANSPORTS[2])
    third.uuid = "bed-specific-service"
    read_only = SimpleNamespace(uuid="read-only", handle=7, properties=["read"])
    third.characteristics.append(read_only)
    client.services = [SimpleNamespace(uuid=str(i)) for i in (1, 2)] + [third]

    controller = Enso2Controller(coordinator, app.LAYOUTS["E3RM"], None, property_fallback=True)
    await controller.async_discover_capabilities()
    assert not controller.requires_notification_channel
    await controller.async_on_connect(None)
    client.start_notify.assert_not_called()
    assert frames(client) == []

    with virtual_clock():
        await controller.hold_control("memory_1", 100)
    assert frames(client) == ["2e", "6e"]
    with raises_key("enso2_light_unavailable"):
        await controller.set_light_color((0, 0, 0))


async def test_duration_is_only_supported_on_the_current_held_memory_slot():
    controller, _, client, _ = await bed("U3RM")
    assert not controller.supports_memory_recall_duration(1)
    with raises_key("preset_duration_not_supported"):
        await controller.recall_memory(1, hold_ms=5000)
    assert frames(client) == []

    controller, _, client, _ = await bed("YFRM")
    assert not controller.supports_memory_recall_duration(1)
    with virtual_clock():
        await controller.press("press_and_hold")
        client.write_gatt_char.reset_mock()
        await controller.recall_memory(1, hold_ms=300)
    assert frames(client) == ["6e01002e9d", "6e01002e9d", "6e01006edd"]


async def test_numbered_motors_are_admitted_by_the_shared_timed_move_plan():
    from contextlib import asynccontextmanager
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import TIMED_MOVE_MOTOR_OPTIONS
    from custom_components.adjustable_bed.services import _timed_move_plan

    controller, coordinator, client, _ = await bed()
    for spec in controller.motor_control_specs:
        assert spec.key in TIMED_MOVE_MOTOR_OPTIONS

    @asynccontextmanager
    async def validated(*args):
        yield controller

    with patch("custom_components.adjustable_bed.services._side_validation", validated):
        command, _, _, _ = await _timed_move_plan(
            coordinator, coordinator, [], "motor_1", "up", 100
        )
        with raises_key("invalid_motor_for_bed_type"):
            await _timed_move_plan(coordinator, coordinator, [], "motor_7", "up", 100)
    with virtual_clock():
        await command(controller)
    assert frames(client) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize("hold", [False, True])
async def test_goto_preset_preflights_the_latest_offline_gesture_on_each_bed(hass, hold):
    from unittest.mock import patch

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import select, target

    old, _, _, _ = await bed("YFRM")
    old.restore_persisted_app_state({"hold": not hold})
    latest, coordinator, _, _ = await bed("YFRM")
    latest.restore_persisted_app_state(old.persisted_app_state)
    coordinator._offline_controller = old

    with virtual_clock():
        await latest.async_on_connect(None)
        await latest.press("press_and_hold" if hold else "press_and_release")
    latest.on_disconnect()
    coordinator._controller = None
    first = target(supports_held_memory_recall=True)
    second = target(bed_type="enso2")
    second[0].capability_controller = coordinator._offline_controller

    async def reconnect(command, **kwargs):
        current, _, _, _ = await bed("YFRM")
        current.restore_persisted_app_state(latest.persisted_app_state)
        with virtual_clock():
            await command(current)

    second[0].async_execute_controller_command.side_effect = reconnect
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets") as resolver:
        select(resolver, first, second)
        data = {"device_id": ["first", "second"], "preset": 1, "duration": 1}
        if hold:
            await hass.services.async_call(DOMAIN, "goto_preset", data, blocking=True)
            first[1].recall_memory.assert_awaited_once_with(1, hold_ms=1000)
            second[0].async_execute_controller_command.assert_awaited_once()
        else:
            with raises_key("preset_duration_not_supported"):
                await hass.services.async_call(DOMAIN, "goto_preset", data, blocking=True)
            first[1].recall_memory.assert_not_awaited()
            second[0].async_execute_controller_command.assert_not_awaited()
