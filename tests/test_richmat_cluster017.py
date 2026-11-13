"""Four explicit apps, source getters, safe sessions and real public callers."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import resource_controller as bed
from custom_components.adjustable_bed.beds.richmat_classic import resource_protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, selected_operand
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.resource_receive import (
    ResourceReceiveState,
)
from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport
from custom_components.adjustable_bed.profiles.richmat_resource_apps import APPS, worker_interval
from tests.test_richmat_classic import packets


def controller(app="lady_americana", layout="O0RM", wire="FRAMED"):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:71"
    coordinator.cancel_command = asyncio.Event()
    coordinator.entry.data = {
        "protocol_variant": app,
        "product_type": layout,
        "motor_pulse_count": 1,
        "ble_device_name": "6BRM-bed",
    }
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    ctrl = bed.ResourceBedController(coordinator)
    coordinator.controller = ctrl
    write = SimpleNamespace(uuid="write", properties=["write"], handle=71)
    notify = SimpleNamespace(uuid="notify", properties=["notify"], handle=72)
    ctrl._session = Transport(coordinator.client, write, notify, wire)
    ctrl._worker.set_interval(worker_interval(app, "6BRM-bed", wire == "RAW"))
    return ctrl, coordinator


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    original_sleep = asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await original_sleep(0)

    async def wait(milliseconds, cancel):
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    monkeypatch.setattr(bed.ResourceBedController, "_wait", staticmethod(wait))
    return now


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("wire", ["RAW", "FRAMED"])
async def test_actual_xml_actions_and_release_use_app_wire_and_clock(clock, app, wire):
    ctrl, coordinator = controller(app, "6BRM", wire)
    await ctrl.execute_action(1, hold_ms=350)
    expected = "34" if wire == "RAW" else "6e01002493"
    assert packets(coordinator)[0] == expected
    assert packets(coordinator)[-1] == ("6e" if wire == "RAW" else "6e01006edd")
    assert ctrl._worker.tick_ms == (170 if wire == "RAW" else 150)
    assert not ctrl.execution.concurrent
    assert ctrl.execution.hold_for("richmat_classic_1") == "stream"


@pytest.mark.parametrize("app", APPS)
def test_complete_member_layout_scope_and_controls(app):
    catalog = load_catalog(app)
    assert len(catalog.models) == 243
    assert sum(len(m.aliases) for m in catalog.models.values()) == 12
    for layout in APPS[app].excluded_layouts:
        with pytest.raises(ValueError, match="outside"):
            controller(app, layout)
    for layout in ("UYRM", "VYRM"):
        ctrl, _ = controller(app, layout)
        action = next(c for c in ctrl._controls if c.short == "3B")
        assert action.excluded_short is (app in ("lady_americana", "sta2"))
        keys = {s.key for s in ctrl.controller_button_specs}
        assert (f"richmat_classic_{action.node}" in keys) is (app in ("acaa", "zerogravity"))
    if app != "zerogravity":
        for layout in ("BBRM", "OVRM", "W8RM"):
            assert controller(app, layout)[0].held_control_options
    assert controller(app, "WLRM")[0].controller_button_specs


def test_advertisement_timing_does_not_inherit_other_apps_name_rules():
    for app in APPS:
        assert worker_interval(app, "6BRM-advertised", True) == 170
        assert worker_interval(app, "6BRM-advertised", False) == 150
        for name in ("TWRM", "MLRM", None):
            assert worker_interval(app, name, True) == 150
            assert worker_interval(app, name, False) == 150


@pytest.mark.parametrize("app", APPS)
async def test_generic_memory_three_and_47_do_not_expand_xml_or_stop_capabilities(clock, app):
    ctrl, coordinator = controller(app, "WARM")
    assert ctrl.memory_slot_count == 0
    await ctrl.execute_request(p.Request("bed_command", command="memory_three"))
    assert packets(coordinator) == ["6e0100309f", "6e01006edd"]
    coordinator.client.write_gatt_char.reset_mock()
    await ctrl.execute_request(p.Request("bed_command", command="voice_stop_request"))
    assert packets(coordinator) == ["6e010047b6", "6e01006edd"]
    coordinator.client.write_gatt_char.reset_mock()
    await ctrl.stop_all()
    assert packets(coordinator) == ["6e01006edd"]


@pytest.mark.parametrize("app", APPS)
async def test_direct_settings_query_alarm_and_light_without_movement_wrapping(clock, app):
    ctrl, coordinator = controller(app, wire="RAW")
    await ctrl.execute_request(p.Request("query"))
    assert packets(coordinator) == ["6e08010178", "6e0a000179", "6e1a000088"]
    coordinator.client.write_gatt_char.reset_mock()
    # Direct alarm buttons/metadata are independent of Settings visibility.
    actions = ctrl._alarm_actions()
    zg = next(key for key, code in actions.items() if code == 0x45)
    await ctrl.execute_request(p.Request("alarm", actions=(zg,)))
    assert packets(coordinator) == ["6e05a00013", "6e060545be"]
    assert ctrl._receive.alarm_enabled is None
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError, match="LED"):
        await ctrl.execute_request(p.Request("lamp_timeout", seconds=300))
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6E0E00037F"))
    await ctrl.execute_request(p.Request("lamp_timeout", seconds=300))
    await ctrl.execute_request(p.Request("rgb", color=(1, 221, 255)))
    assert packets(coordinator) == ["6e0b002da6", "6e0cff017a6e0dddff57"]
    assert ctrl.controller_number_specs[0].state_key is bed.LAMP_TIMEOUT


async def test_slow_inflight_write_settles_without_refresh_burst_after_deadline(clock):
    ctrl, coordinator = controller(layout="6BRM")

    async def slow(_char, packet, **kwargs):
        if packet == bytes.fromhex("6e01002493"):
            clock[0] += 2

    coordinator.client.write_gatt_char.side_effect = slow
    await ctrl.execute_action(1, hold_ms=300)
    assert packets(coordinator) == ["6e01002493", "6e01006edd"]


async def test_cancel_during_att_write_settles_before_captured_release(clock):
    ctrl, coordinator = controller(layout="6BRM")
    started, finish = asyncio.Event(), asyncio.Event()
    original_sleep = asyncio.sleep

    async def write(_char, packet, **kwargs):
        if packet == bytes.fromhex("6e01002493"):
            started.set()
            await finish.wait()

    coordinator.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(ctrl.execute_action(1, hold_ms=1000))
    await started.wait()
    task.cancel()
    await original_sleep(0)
    assert len(packets(coordinator)) == 1
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert packets(coordinator) == ["6e01002493", "6e01006edd"]


async def test_new_session_cannot_receive_old_cleanup_or_callback(clock):
    ctrl, coordinator = controller(layout="6BRM")
    old = ctrl._session
    with ctrl._transaction():
        ctrl.on_disconnect()
        ctrl._session = replace(old)
        await ctrl._release()
        with pytest.raises(ConnectionError, match="captured"):
            await ctrl._send(b"\x24")
    ctrl._notification(old, old.notify, bytearray.fromhex("6E09010078"))
    assert not ctrl._receive.alarm_capable
    assert packets(coordinator) == []


def test_signed_fragment_parser_unchecked_ten_and_session_boundary():
    state = ResourceReceiveState()

    def feed(data):
        state.feed(bytes.fromhex(data), app="lady_americana", layout="O0RM")

    feed("6E1A000189")
    assert state.last_value is None and state.buffer == "6e1a000189"
    feed("6E09010078")
    assert state.last_value == "6e1a0001896e09010078" and not state.alarm_capable
    feed("6E1A")
    feed("000101")
    assert state.last_value == "6e1a000101"
    assert not state.aroma_capable
    feed("00" * 1000)
    assert state.buffer == ""
    feed("6E09010078")
    assert state.alarm_capable


@pytest.mark.parametrize("app", APPS)
async def test_gvrm_null_and_u3rm_mutable_selector_are_not_hardware_sides(clock, app):
    ctrl, coordinator = controller(app, "GVRM", "RAW")
    ctrl._select("head_foot", "foot")
    await ctrl.execute_action(2, hold_ms=150)
    assert packets(coordinator) == []
    assert not ctrl.supports_single_address_pairing
    ctrl, coordinator = controller(app, "U3RM")
    button = next(c for c in ctrl._controls if c.tag == "51")
    ctrl._selection = Selection(press_flag="55")
    assert selected_operand(button, "FRAMED", 1, ctrl._selection) == b"\x71"
    await ctrl.execute_action(button.node, hold_ms=150)
    assert packets(coordinator) == ["6e010071e0", "6e01006edd"]


def test_alarm_ownership_order_combinations_and_unreachable_helpers():
    all_outputs = set()
    for layout in load_catalog("lady_americana").models:
        if layout == "WFRM":
            continue
        ctrl, _ = controller(layout=layout)
        choices = ctrl._alarm_actions()
        from itertools import combinations

        for count in range(1, len(choices) + 1):
            for keys in combinations(choices, count):
                try:
                    all_outputs.add(p.alarm_action(choices, keys))
                except ValueError:
                    pass
    assert all_outputs == {
        0x2E,
        0x2F,
        0x45,
        0x46,
        0x4C,
        0x4E,
        0x58,
        0x59,
        0x5D,
        0x77,
        0x78,
        0x79,
        0x7B,
        0x7C,
        0x7E,
        0x7F,
        0x81,
        0x82,
        0x83,
    }
    assert not {0x30, 0x80, 0x7A, 0x7D} & all_outputs
