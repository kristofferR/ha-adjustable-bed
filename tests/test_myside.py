"""My Side's product gates, physical sessions, gestures and alarm callers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.myside import controller as bed
from custom_components.adjustable_bed.beds.myside.protocol import Alarm, parse
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import myside as app
from tests.state_helpers import state_writer
from tests.test_wire_snapshot import _load_tool


@pytest.fixture
async def clock(monkeypatch):
    tool = _load_tool()
    clock = tool.FakeClock()
    monkeypatch.setattr(bed, "monotonic", lambda: clock.now)
    with tool.virtual_time(clock):
        yield clock


def make(hass, product="79", routes=("w1",), address="AA:BB:CC:DD:EE:67"):
    c = MagicMock()
    c.hass = hass
    c.address = address
    c.cancel_command = asyncio.Event()
    c.controller_state = {}
    c.handle_controller_state_updates.side_effect = state_writer(c.controller_state)
    c.client.is_connected = True
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    c.client.services = [
        SimpleNamespace(
            uuid=codec.TRANSPORTS[key].service_uuid,
            characteristics=[
                SimpleNamespace(
                    uuid=codec.TRANSPORTS[key].write_uuid,
                    properties=["write", *(["write-without-response"] if key == "n1" else [])],
                    handle=i * 2 + 1,
                ),
                SimpleNamespace(
                    uuid=codec.TRANSPORTS[key].notify_uuid, properties=["notify"], handle=i * 2 + 2
                ),
            ],
        )
        for i, key in enumerate(routes)
    ]
    c.controller = bed.MySideController(c, product=product)
    return c


def writes(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("product", app.PROFILES)
async def test_products_startup_native_controls_and_gates(hass, clock, product):
    c = make(hass, product)
    ctrl = c.controller
    await ctrl.start_notify()
    expected = ["6e08010178", "6e0a000179", "6e15010185"]
    assert writes(c)[:3] == expected
    assert len(writes(c)) == 3 + int(ctrl.profile.coaxing) + int(ctrl.profile.sleep)
    assert ctrl.memory_slot_count == ctrl.profile.memories
    assert ctrl.supports_massage is ctrl.profile.coaxing
    assert not ctrl.supports_lights
    assert not ctrl.supports_single_address_pairing
    assert {s.key for s in ctrl.motor_control_specs} == {"back", "legs"}
    assert all(s.hold is not None for s in ctrl.motor_control_specs)
    assert ctrl.execution.hold == "stream" and not ctrl.execution.concurrent
    assert not ctrl.position_number_specs
    if not ctrl.profile.coaxing:
        for key in (
            "memory3",
            "zero_gravity",
            "coaxing_mode",
            "massage_head_strengthen",
            "head_and_foot_up",
        ):
            with pytest.raises(ServiceValidationError):
                await ctrl.press(key)
        with pytest.raises(ServiceValidationError):
            ctrl.validate_operation("query")
    await ctrl.stop_notify()
    assert c.controller_state[str(bed.ALARMS)] == []


@pytest.mark.parametrize("routes,single", [(("w1", "n1"), True), (("n1", "w1"), False)])
async def test_independent_handles_and_encoding(hass, clock, routes, single):
    c = make(hass, routes=routes)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    await c.controller.preset_memory(1)
    call = c.client.write_gatt_char.await_args
    assert call.args[0] is c.client.services[0].characteristics[0]
    assert call.args[1] == codec.function(0x2E, single=single)
    assert call.kwargs["response"] is (routes[0] != "n1")
    assert c.client.start_notify.await_args.args[0] is c.client.services[0].characteristics[1]


async def test_direction_first_tick_refresh_and_cancel_cleanup(hass, clock):
    c = make(hass)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    times = []

    async def write(*args, **kwargs):
        times.append(clock.now)
        if len(times) == 2:
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = write
    start = clock.now
    await c.controller.hold_control("head_up", 1000)
    assert writes(c) == ["6e01002493", "6e01002493", "6e01006edd"]
    assert times == pytest.approx([start + 0.1, start + 0.2, start + 0.3])


async def test_task_cancellation_during_write_finishes_then_releases(hass, clock):
    c = make(hass)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == codec.command(0x24):
            started.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.controller.hold_control("head_up", 1000))
    await started.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert writes(c) == ["6e01002493", "6e01006edd"]


@pytest.mark.parametrize(
    "control", ["flat", "massage_timer10", "massage_timer20", "massage_timer30"]
)
@pytest.mark.parametrize("duration,long", [(2999, False), (3000, True)])
async def test_text_threshold_has_no_stop(hass, clock, control, duration, long):
    c = make(hass)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    await c.controller.hold_control(control, duration)
    code = 0 if long else 0x31 if control == "flat" else app.MASSAGE[control]
    assert writes(c) == [codec.command(code).hex()]


async def test_stop_cancels_pending_text_without_late_movement(hass, clock):
    c = make(hass)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    c.cancel_command.set()
    await c.controller.hold_control("flat", 3000)
    assert writes(c) == []


async def test_strength_single_press_and_release_save_icons(hass, clock):
    c = make(hass)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    await c.controller.press("massage_head_strengthen")
    await c.controller.press("zero_gravity", save=True)
    await c.controller.program_memory(3)
    assert writes(c) == ["6e01004cbb", "6e01006edd", "6e010066d5", "6e01002d9c"]
    with pytest.raises(ServiceValidationError):
        await c.controller.press("flat", save=True)


async def test_alarm_projection_parser_state_and_product_gates(hass, clock):
    c = make(hass)
    ctrl = c.controller
    await ctrl.start_notify()
    c.client.write_gatt_char.reset_mock()
    link = ctrl._link
    # Unknown updates do not invent alarms. Fresh list records are keyed by number.
    await ctrl.operation("query")
    c.client.write_gatt_char.reset_mock()
    reply = codec.record_20_len(5, 1, 3, (1, 55, 6, 30, 69, 169))
    ctrl._notification(link, link.rx, bytearray(reply))
    assert ctrl.alarms == []
    reply = codec.record_20_len(5, 1, 2, (1, 55, 6, 30, 69, 169))
    ctrl._notification(link, link.rx, bytearray(reply))
    ctrl._notification(link, link.rx, bytearray(reply))
    assert len(ctrl.alarms) == 1
    await ctrl.operation("enable", alarm_id=1, enabled=False)
    ctrl._notification(link, link.rx, bytearray(reply))
    await ctrl.operation(
        "edit", alarm_id=1, hour=6, minute=30, mode="zero_gravity", weekdays=(0, 2, 4)
    )
    assert writes(c) == ["6e0d200501010137061e45a8eb", "6e0d200501010100061e45a9b5"]
    ctrl._notification(link, link.rx, bytearray(reply))
    await ctrl.operation("delete", alarm_id=1)
    assert ctrl.alarms == []
    for operation in ("edit", "enable", "delete"):
        with pytest.raises(ServiceValidationError):
            ctrl.validate_operation(operation, alarm_id=1)
    for value in (reply[:-1], reply[:-1] + b"\x00", bytes([reply[0], reply[1], 12]) + reply[3:]):
        assert parse(value) is None
    # Split safe HA framing is infrastructure, not a claim of complete app parser parity.
    name = codec.record_20_len(6, 1, 3, (0, *b"RM-001"))
    ctrl._notification(link, link.rx, bytearray(name[:5]))
    ctrl._notification(link, link.rx, bytearray(name[5:]))
    assert ctrl.sleep_name == "RM-001"
    basic = make(hass, "76", address="AA:BB:CC:DD:EE:68")
    await basic.controller.start_notify()
    for data in (name, bytes.fromhex("6e0e00037f"), bytes.fromhex("6e09010078")):
        basic.controller._notification(
            basic.controller._link, basic.controller._link.rx, bytearray(data)
        )
    assert not basic.controller.features and basic.controller.sleep_name is None


async def test_alarm_add_requires_delivered_delete_within_app_slots(hass, clock):
    c = make(hass)
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    await c.controller.operation("query")
    link = c.controller._link
    for n in (1, 3, 4, 5, 6, 7):
        c.controller._notification(
            link, link.rx, bytearray(codec.record_20_len(5, 1, 2, (n, 55, 6, 30, 69, 169)))
        )
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await c.controller.operation("add", hour=7, mode="memory1")
    assert writes(c) == []
    c.controller._notification(
        link, link.rx, bytearray(codec.record_20_len(5, 1, 2, (2, 0, 7, 0, 46, 1)))
    )
    await c.controller.operation("delete", alarm_id=2)
    c.client.write_gatt_char.reset_mock()
    await c.controller.operation("add", hour=7, mode="memory1")
    assert writes(c) == [Alarm(2, 0, 7, 0, 46, 1).frame().hex()]
    with pytest.raises(ServiceValidationError):
        c.controller.validate_operation("add", mode="memory1")


async def test_replacement_rejects_old_callbacks_and_pending_commands(hass, clock):
    c = make(hass)
    old = c.controller
    await old.start_notify()
    old_link = old._link
    c.controller = bed.MySideController(c, product="76")
    await c.controller.start_notify()
    c.client.write_gatt_char.reset_mock()
    old._notification(old_link, old_link.rx, bytearray(codec.record_20_len(6, 1, 3, (0, *b"OLD"))))
    with pytest.raises(ConnectionError):
        await old.preset_flat()
    await old.stop_notify()
    assert not c.client.stop_notify.await_count
    assert c.controller._link is not None
    assert writes(c) == []


def test_explicit_product_selection_and_scan_semantics(hass):
    for value in ("", "auto", "80", "Deep Relax Smart"):
        with pytest.raises(ServiceValidationError):
            make(hass, value)
    assert app.scan_matches("prefix-QRRM-suffix")
    assert app.scan_matches("vendor-BED-123")
    assert not app.scan_matches("qrrm") and not app.scan_matches(None)
