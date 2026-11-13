"""Symphony's product dispatch, source parser boundaries and owned movement."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.adjustable_bed.beds.symphony import state
from custom_components.adjustable_bed.beds.symphony import state_keys as k
from custom_components.adjustable_bed.beds.symphony.controller import SymphonyController
from custom_components.adjustable_bed.profiles import symphony as app
from tests.hold_lease_wire import virtual_clock
from tests.state_helpers import state_writer
from tests.test_controller_contract import _FactoryCoordinator


def bed(product="0", selector=4):
    coordinator = _FactoryCoordinator()
    coordinator.handle_controller_state_updates = state_writer(coordinator.controller_state)
    ctrl = SymphonyController(coordinator, app.SymphonyProfile(app.PRODUCTS[product], selector))
    coordinator.client = SimpleNamespace(is_connected=True)
    ctrl._link, ctrl._ready = coordinator.client, True
    ctrl._writer = SimpleNamespace(uuid="writer", properties=["write"])
    ctrl._reader = SimpleNamespace(uuid="notify")
    return ctrl


@pytest.mark.parametrize("product", app.PRODUCTS)
@pytest.mark.parametrize("selector", (0, 2, 3, 4, 5, 6, 7, 8, 9))
def test_all_144_dispatch_cells_are_independent(product, selector):
    ctrl = bed(product, selector)
    spec = app.PRODUCTS[product]
    assert tuple(row.key for row in ctrl.motor_control_specs) == (
        *spec.axes,
        *(("head_foot",) if spec.combined else ()),
    )
    assert ctrl.app.wire == ("P1" if selector == 4 else "P2" if selector in (8, 9) else "P3")
    assert ctrl.app.position_wire == (
        "P1" if product == "15" else "P3" if product == "10" else ctrl.app.wire
    )
    assert ctrl.supports_massage == (selector in (8, 9) or spec.massage is not None)
    assert ctrl.supports_single_address_pairing == (product in ("10", "15"))
    assert ctrl.execution.hold == "latched" and not ctrl.execution.concurrent
    assert all(row.hold and row.hold.stop_scope == "side" for row in ctrl.motor_control_specs)
    assert not ctrl.position_number_specs
    assert ctrl.supports_lights == (product not in ("2", "20"))
    assert ctrl.memory_slot_count == (0 if product == "1" else 1 if product == "20" else 2)
    assert bool(ctrl.app.saves) == (product in ("12", "13", "20"))


@pytest.mark.parametrize(
    "name,manufacturer,expected",
    [
        ("", {}, 2),
        ("SLEEP", {}, 2),
        ("X-SLEEP", {89: bytes((0, 1, 2, 3, 4, 5, 128))}, 9),
        ("SMARTBED", {89: bytes((0, 1, 2, 3, 5))}, 5),
        ("SMARTBED417", {}, 6),
        ("SMARTBED7404", {}, 7),
        ("smartbed7411", {}, 8),
        ("Smartbed8401", {}, 8),
        ("SMARTBEDD6 OKIN SLEEP", {89: bytes(7)}, 4),
        ("unknown", {}, 0),
    ],
)
def test_scan_overwrite_order(name, manufacturer, expected):
    assert app.selector_from_scan(name, manufacturer) == expected
    assert app.selector_from_scan(name, manufacturer, 6) == 6
    assert not app.scan_matches("SLEEP", {})
    assert app.logical_name({89: bytes((255, 1, 2, 3, 4, 5, 6))}) == "010203040506"


@pytest.mark.parametrize(
    "selector,release,delay",
    [
        (4, ["e6fe16000000000005"], 0.3),
        (3, ["05020000000000"], 0.1),
        (9, ["aa000001010400000000", "aa0000010200"], 0),
    ],
)
@pytest.mark.parametrize("ack", (0, 0.02, 2))
async def test_latched_duration_absorbs_fast_and_slow_ack(selector, release, delay, ack):
    ctrl = bed("0", selector)
    writes = []
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()

        async def write(frame, **kwargs):
            writes.append((loop.time() - start, frame.hex(), kwargs))
            if not kwargs.get("cancel_event"):
                await asyncio.sleep(ack)

        ctrl.write_command = write
        await ctrl.hold_control("head_up", 1000)
        assert len(writes) == 1 + len(release)
        assert [row[1] for row in writes[1:]] == release
        assert writes[1][0] == pytest.approx(1 + delay)
        assert all(not row[2]["cancel_event"].is_set() for row in writes[1:])


async def test_cancel_captures_original_side_and_repeated_cancel_waits_for_cleanup():
    ctrl = bed("15", 4)
    writes = []
    ctrl.write_command = AsyncMock(side_effect=lambda frame, **kwargs: writes.append(frame.hex()))
    with virtual_clock():
        with ctrl.side_scope("right"):
            task = asyncio.create_task(ctrl.hold_control("head_up", 30000))
        await asyncio.sleep(0.1)
        ctrl._coordinator.cancel_command.set()
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert writes == ["e6fe164000000002c3", "e6fe16000000000203"]


async def test_disconnect_discards_old_fragment_callbacks_and_delayed_stop():
    ctrl = bed("15", 4)
    old_link, old_generation = ctrl._link, ctrl._generation
    ctrl._notify(old_generation, old_link, bytes.fromhex("f4fe16") + bytes(17))
    assert ctrl._assembler.pending
    ctrl.write_command = AsyncMock()
    with virtual_clock():
        task = asyncio.create_task(ctrl._cleanup(app.stops(ctrl.app, 2), old_generation, old_link))
        await asyncio.sleep(0.01)
        ctrl.on_disconnect()
        ctrl._link = ctrl._coordinator.client = SimpleNamespace(is_connected=True)
        ctrl._ready = True
        ctrl._notify(old_generation, old_link, b"\x01\x02\x03")
        await task
    assert ctrl._assembler.pending == b""
    ctrl.write_command.assert_not_awaited()


def test_dispatch_buffers_only_original_twenty_byte_fe16():
    parser = state.Assembler()
    prefix = b"\x00\xfe\x16" + bytes(17)
    assert parser.feed(prefix) is None
    assert parser.feed(b"\x01") is None and parser.pending == prefix
    assert parser.feed(b"\x01\x02\x03") == prefix + b"\x01\x02\x03"
    p2 = bytes.fromhex("2a0000078109") + bytes(14)
    assert parser.feed(p2) == p2 and not parser.pending


@pytest.mark.parametrize(
    "packet,expected",
    [
        ("2a000006810b0024360000040058025902", state.Massage(True, 2, 4, 1, 2, False)),
        ("2a000006810b0024360100040058025902", state.Massage(True, 0, 0, 1, 2, True)),
        ("2a000006810b0000000000040058025902", state.Massage(False, 0, 0, 0, 0, False)),
    ],
)
def test_source_sonic_massage_valid_notifications(packet, expected):
    assert state.soundwave(bytes.fromhex(packet)) == expected


@pytest.mark.parametrize(
    "product,selector,packet,side,expected",
    [
        ("0", 3, "a50c0e003e05071e0001", 1, state.Alarm(True, 62, 5, 7, 30)),
        ("3", 5, "a50c0e003e0207300001", 1, state.Alarm(True, 62, 2, 7, 30)),
        ("1", 5, "a50c0e003e0107300001", 1, state.Alarm(True, 62, 1, 7, 48)),
        ("20", 4, "ed8003071e3e11", 1, state.Alarm(True, 62, 17, 7, 30)),
        ("15", 4, "ed800300000000071e3e11083b810d00", 2, state.Alarm(True, 129, 13, 8, 59)),
        ("10", 6, "a50cff003e05071e0001008105083b0001", 2, state.Alarm(True, 129, 5, 8, 59)),
        ("12", 9, "2a0000038107013e0501071e00", 1, state.Alarm(True, 62, 5, 7, 30, 0)),
    ],
)
def test_all_seven_alarm_consumers_keep_their_source_fields(
    product, selector, packet, side, expected
):
    assert (
        state.alarm(
            app.SymphonyProfile(app.PRODUCTS[product], selector), bytes.fromhex(packet), side
        )
        == expected
    )


@pytest.mark.parametrize(
    "frame", ["2a000007810901", "2a0000078109010203", "2a0000038107013e0500", "2a000006810b0000"]
)
def test_short_matching_p2_packets_cannot_partially_corrupt_state(frame):
    ctrl = bed("12", 9)
    before = dict(ctrl._coordinator.controller_state)
    ctrl._notify(ctrl._generation, ctrl._link, bytes.fromhex(frame))
    assert ctrl._coordinator.controller_state == before


async def test_p2_source_fields_exact_light_length_and_disabled_alarm_cache():
    ctrl = bed("12", 9)

    def notify(packet):
        ctrl._notify(ctrl._generation, ctrl._link, bytes.fromhex(packet))

    notify("2a0000048106020300000032")
    values = ctrl._coordinator.controller_state
    assert (values[k.COLOR], values[k.BRIGHTNESS], values[k.LIGHT_ON]) == (3, 50, True)
    notify("2a000004810602070000005000")
    assert values[k.COLOR] == 3
    notify("2a0000038107013e0501071e00")
    notify("2a000003810701000000000000")
    assert values[k.ALARM] is False and values[k.WEEK] == 62 and values[k.HOUR] == 7
    notify("2a000007810901020300000100000000")
    assert values[k.SNORE] is True and values[k.STRENGTH] == 3 and values[k.PRIVACY] is True


def test_premier_F1_time_projection_and_other_five_consumers():
    packet = bytearray.fromhex("f4fe1600000000000000000305000000000000000004")
    profile = app.SymphonyProfile(app.PRODUCTS["3"], 4)
    value = state.legacy_massage(profile, bytes(packet), 1)
    assert value.running and value.timer_index == 0 and value.wave is None
    packet[19] = 3
    assert state.legacy_massage(profile, bytes(packet), 1).timer_index == 3
    for product in ("0", "11", "14", "15", "10"):
        profile = app.SymphonyProfile(app.PRODUCTS[product], 4)
        value = state.legacy_massage(profile, bytes(packet), 1)
        assert value.running and value.timer_index == 3 and value.wave == 4
        assert (value.foot is not None) == (product in ("14", "15"))


def test_alarm_bindings_and_opposite_side_time_predicate():
    p1 = bytes.fromhex("ed800300000000071e3e11083b800d3c")
    split = app.SymphonyProfile(app.PRODUCTS["15"], 4)
    assert state.alarm(split, p1, 1) == state.Alarm(True, 62, 17, 7, 30)
    assert state.alarm(split, p1, 2).enabled is False
    assert state.alarm(app.SymphonyProfile(app.PRODUCTS["0"], 4), p1, 1) is None
    dual = bytearray.fromhex("a50c0e003e05071e000100803e05071e0001")
    dual[11:17] = bytes((129, 5, 7, 30, 0, 1))
    assert state.opposite_alarm_conflict(bytes(dual), 1, 7, 30)
    dual[11] = 0  # No week overlap is required.
    assert state.opposite_alarm_conflict(bytes(dual), 1, 7, 30)
    dual[16] = 2
    assert not state.opposite_alarm_conflict(bytes(dual), 1, 7, 30)
    with pytest.raises(ValueError):
        state.opposite_alarm_conflict(bytes(dual[:14]), 1, 7, 30)


async def test_unknown_light_companion_requires_explicit_fields_and_child_mode_allows_stop():
    ctrl = bed("12", 9)
    ctrl.write_command = AsyncMock()
    with virtual_clock(), pytest.raises(ValueError, match="both"):
        await ctrl.set_light(color=3)
    ctrl.write_command.assert_awaited_once_with(bytes.fromhex("2a0000048100"))
    ctrl.write_command.reset_mock()
    await ctrl.set_light(color=3, brightness=50)
    assert ctrl.write_command.call_args_list[0].args[0].hex() == "aa0000040105020300000032"
    ctrl.local.child = True
    with pytest.raises(ValueError, match="child"):
        await ctrl.hold_control("head_up", 1000)
    await ctrl.stop_all()
    assert ctrl.write_command.call_args.args[0].hex() == "aa0000010200"


@pytest.mark.parametrize(
    "product,selector,name,expected",
    [
        ("12", 4, "zero_g", "aa000001030101"),
        ("20", 4, "reading", "05020000200000"),
        ("20", 9, "tv", "05020000400000"),
    ],
)
async def test_fixed_preset_builders_do_not_inherit_generic_selector(
    product, selector, name, expected
):
    ctrl = bed(product, selector)
    ctrl.write_command = AsyncMock()
    with virtual_clock():
        await ctrl.recall(name)
    assert ctrl.write_command.call_args_list[0].args[0].hex() == expected
    ctrl.write_command.reset_mock()
    with virtual_clock():
        await ctrl.recall(name, save=True)
    assert ctrl.write_command.await_count == ((3 if selector == 9 else 2) if product == "20" else 1)


@pytest.mark.parametrize(
    "protocol,firmware,expected",
    [
        ("SENSOR_VOICE", "1.1", True),
        ("SENSOR_VOICE", "2", True),
        ("SENSOR_VOICE", "1.0", False),
        ("sensor_voice", "2.0", False),
        ("SENSOR_VOICE", "bad", False),
    ],
)
def test_exact_voice_firmware_gate(protocol, firmware, expected):
    assert state.offline_voice(protocol, firmware) is expected
