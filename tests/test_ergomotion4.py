"""Accepted com.sfd.hump 3.7 byte, timing, product and side conformance."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.alarm_table import (
    AlarmTableSchedule,
    OneTimeAlarmRecord,
    WeeklyAlarmRecord,
)
from custom_components.adjustable_bed.beds.ergomotion4 import (
    CONF_MASSAGE_KEYS,
    CONF_MODEL_KEYS,
    CONF_PRODUCT_NAME,
    CONF_RGB,
    RX_UUIDS,
    SILENT_RX,
    TX_UUIDS,
    Ergomotion4Controller,
    custom_product,
    p2_frame,
    parse_status,
)
from custom_components.adjustable_bed.beds.keeson import KeesonController
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.ergomotion4_profiles import ACTIONS, PRODUCTS
from custom_components.adjustable_bed.pairing import supports_single_address_pairing

FIXTURES = Path(__file__).parent / "fixtures/ergomotion4"
VECTORS = json.loads((FIXTURES / "test-vectors.json").read_text())
CASES = json.loads((FIXTURES / "commands.json").read_text())
CATALOG = json.loads((FIXTURES / "catalog.json").read_text())


@pytest.fixture
def hold_clock(monkeypatch):
    clock = SimpleNamespace(milliseconds=0.0)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.ergomotion4.monotonic",
        lambda: clock.milliseconds / 1000,
    )
    return clock


def coordinator(product="H", **data):
    result = MagicMock()
    result.entry.data = {"bed_type": "ergomotion_4", "product_type": product, **data}
    result.client.is_connected = True
    result.client.write_gatt_char = AsyncMock()
    result.client.start_notify = AsyncMock()
    result.client.stop_notify = AsyncMock()
    result.cancel_command = asyncio.Event()
    result._cancel_command = result.cancel_command
    result.motor_pulse_count = 1
    result.observed_ble_device_name = "KSBT03CP123"
    result.controller_state = {}
    result.handle_controller_state_updates.side_effect = result.controller_state.update
    rx = MagicMock(uuid="0000ffe4-0000-1000-8000-00805f9b34fb", properties=["notify"])
    tx = MagicMock(uuid="0000ffe9-0000-1000-8000-00805f9b34fb", properties=["write"])
    service = MagicMock(characteristics=[rx, tx])
    result.client.services = [service]
    return result


async def ready(product="H", **data):
    coord = coordinator(product, **data)
    ctrl = Ergomotion4Controller(coord)
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.start_notify()
    coord.client.write_gatt_char.reset_mock()
    ctrl._wait.reset_mock()
    return ctrl, coord


def packets(coord):
    return [bytes(call.args[1]) for call in coord.client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    "vector",
    [v for v in VECTORS if v["id"].startswith("P1-") and v["id"] != "P1-ui-A"],
    ids=lambda v: v["id"],
)
def test_p1_side_vectors(vector):
    side = {"Both": None, "Left": 2, "Right": 1}[vector["inputs"]["side"]]
    key = vector["inputs"]["key"] & 0xFFFFFFFF
    frame = codec.frame(key) if side is None else codec.frame(key, header=0xE6, side=side)
    assert frame.hex() == vector["expected_bytes"]


@pytest.mark.parametrize(
    "vector",
    [v for v in VECTORS if v["id"].startswith(("P2-key-", "custom-", "RGB-"))],
    ids=lambda v: v["id"],
)
def test_p2_custom_rgb_vectors(vector):
    data = vector["inputs"]
    if vector["id"].startswith("P2-"):
        frame = p2_frame(data["key"])
    elif vector["id"].startswith("custom-"):
        frame = codec.custom_massage(data["key"])
    else:
        frame = codec.rgb((data["r"], data["g"], data["b"]), inverted=data["invert"])
    assert frame.hex() == vector["expected_bytes"]


def test_p2_unsupported_key_does_not_become_arbitrary_command():
    assert p2_frame(0xDEADBEEF).hex() == "040200000000"
    assert codec.custom_massage(9).hex() == "07d000000000000000"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
async def test_artifact_command_sequences(case, hold_clock):
    extra = {}
    if case["product"] == "custom":
        # The accepted union includes simple-foot and singleton-head gates
        # absent from the acquired 21-row snapshot. Exercise explicit keys.
        extra = {CONF_MODEL_KEYS: ["k2"], CONF_MASSAGE_KEYS: ["m5"]}
    ctrl, coord = await ready(case["product"], **extra)
    ctrl._light = True
    ctrl._rgb = (127, 200, 255)
    trace = []

    async def write(_char, payload, **_kwargs):
        trace.append(["write", bytes(payload).hex()])

    async def wait(milliseconds, **_kwargs):
        trace.append(["wait", milliseconds])
        hold_clock.milliseconds += milliseconds
        return False

    coord.client.write_gatt_char.side_effect = write
    ctrl._wait.side_effect = wait
    side = {"Both": "both", "Left": "left", "Right": "right"}[case["side"]]
    action = ACTIONS[case["command"]]
    bound = ctrl.bind_side(side)
    await bound._run_action(action.key)
    expected = case["press"] + ([["wait", 100]] + case["release"] if case["held"] else [])
    assert trace == expected
    assert ctrl.command_side is None


@pytest.mark.parametrize("row", CATALOG, ids=lambda r: r["id"])
def test_exact_catalog_gates(row):
    product = PRODUCTS[row["name"]]
    assert set(product.commands) == set(row["initial_command_ids"])
    assert set(product.commands + product.light_commands) == set(row["light_on_command_ids"])
    if row["route_variant"] == "V01":
        keys = row["runtime_keys"]
        custom = custom_product(
            row["name"],
            tuple(keys["model_key"]),
            tuple(keys["massage_key"]),
            keys["light"],
            keys["rgb"],
        )
        assert set(custom.commands) == set(product.commands)
        assert set(custom.light_commands) == set(product.light_commands)
        assert custom.rgb == product.rgb


@pytest.mark.parametrize(
    "vector", [v for v in VECTORS if v["id"].startswith("notify-")], ids=lambda v: v["id"]
)
def test_notification_vectors(vector):
    data = vector["inputs"]
    parsed = parse_status(
        bytes.fromhex(vector["expected_bytes"]), data["style"], dynamic=data["dynamic"]
    )
    expected = vector["expected_state"] or {}
    if "rgb" in expected:
        expected = {**expected, "rgb": tuple(expected["rgb"])}
    assert parsed == expected


@pytest.mark.parametrize("bits", range(4))
@pytest.mark.parametrize("side", ("both", "left", "right"))
def test_notification_side_bits(bits, side):
    frame = bytearray(19)
    frame[0], frame[14], frame[16] = 241, 3, bits
    accepted = not bits or (bool(bits & 2) == (side == "right"))
    assert parse_status(bytes(frame), "H", side=side) == ({"timer": 3} if accepted else {})


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, -1), (1, 1), (600, 1), (601, 2), (1200, 2), (1201, 3), (1800, 3), (1801, -1)],
)
def test_timer_cutoffs(seconds, expected):
    frame = bytearray(18)
    frame[:3] = b"\xa5\x0b\x0f"
    frame[3:5] = seconds.to_bytes(2, "big")
    assert parse_status(bytes(frame), "H")["timer"] == expected


async def test_one_session_last_write_match_all_notifications_and_stale_callbacks():
    coord = coordinator("M19")
    chars = [MagicMock(uuid=u, properties=["write"]) for u in sorted(TX_UUIDS)]
    receives = [MagicMock(uuid=u, properties=["notify"]) for u in sorted(RX_UUIDS)]
    coord.client.services[0].characteristics = chars + receives
    ctrl = Ergomotion4Controller(coord)
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.start_notify()
    assert ctrl._tx is chars[-1]
    assert coord.client.start_notify.await_count == len(receives)
    assert packets(coord) == [b"\x00\xb0"] * 3
    callbacks = [call.args[1] for call in coord.client.start_notify.await_args_list]
    frame = bytearray(19)
    frame[12] = 1
    silent = next(i for i, c in enumerate(receives) if c.uuid == SILENT_RX)
    coord.handle_controller_state_updates.reset_mock()
    callbacks[silent](receives[silent], frame)
    coord.handle_controller_state_updates.assert_not_called()
    callbacks[0](receives[0], frame)
    assert coord.controller_state["under_bed_lights_on"] is True
    await ctrl.stop_notify()
    coord.handle_controller_state_updates.reset_mock()
    callbacks[0](receives[0], frame)
    coord.handle_controller_state_updates.assert_not_called()
    assert coord.client.stop_notify.await_count == len(receives)


async def test_side_state_is_not_published_as_both_sides():
    ctrl, coord = await ready()
    frame = bytearray(19)
    frame[0], frame[14], frame[16] = 241, 3, 2
    ctrl._parse_notification(bytes(frame))
    assert coord.controller_state["right_app_timer_status"] == 3
    assert coord.controller_state["left_app_timer_status"] is None
    assert coord.controller_state["app_timer_status"] is None
    specs = ctrl.bind_side("right").controller_state_sensor_specs
    assert specs[0].state_key == "right_app_timer_status"


@pytest.mark.parametrize("product", PRODUCTS)
async def test_product_session_init_and_pairing_contract(product):
    coord = coordinator(product)
    ctrl = Ergomotion4Controller(coord)
    ctrl._wait = AsyncMock(return_value=False)
    await ctrl.start_notify()
    p1 = PRODUCTS[product].protocol == "P1"
    assert ctrl.supports_single_address_pairing is p1
    assert supports_single_address_pairing("ergomotion_4", product_type=product) is p1
    assert packets(coord) == (
        [bytes.fromhex("e5fe160000000006")]
        if p1 or PRODUCTS[product].style == "M30"
        else [b"\x00\xb0"] * 3
    )
    if not p1:
        with pytest.raises(ValueError, match="side selector"):
            ctrl.bind_side("left")._frame(1)


@pytest.mark.parametrize("variant", ["base", "ergomotion"])
async def test_legacy_p1_side_routing_and_cancelled_release(variant):
    coord = coordinator()
    coord.motor_pulse_delay_ms = 100
    coord.client.services = None
    ctrl = KeesonController(coord, variant=variant)
    ctrl._write_to_characteristic = AsyncMock()
    for side, expected in (
        ("left", "e6fe16010000000202"),
        ("right", "e6fe16010000000103"),
        ("both", "e5fe160100000005"),
    ):
        assert ctrl.bind_side(side)._build_command(1).hex() == expected
    assert ctrl.supports_single_address_pairing
    assert supports_single_address_pairing("keeson", variant)
    assert ctrl._build_command(1).hex() == "e5fe160100000005"
    assert not supports_single_address_pairing("keeson", "auto")
    assert not supports_single_address_pairing("keeson", "ksbt")


async def test_cancelled_hold_releases_original_side_on_fresh_event():
    ctrl, coord = await ready()

    async def cancel(_milliseconds, **_kwargs):
        coord.cancel_command.set()
        return True

    ctrl._wait.side_effect = cancel
    await ctrl.bind_side("left").hold_control("c054", 1000)
    assert packets(coord) == [
        bytes.fromhex("e6fe16010000000202"),
        bytes.fromhex("e6fe16000000000203"),
    ]
    # A replacement/disconnected session never receives old cleanup.
    coord.cancel_command.clear()
    coord.client.write_gatt_char.reset_mock()

    async def disconnect(_milliseconds, **_kwargs):
        ctrl.on_disconnect()
        return True

    ctrl._wait.side_effect = disconnect
    await ctrl.bind_side("right").hold_control("c054", 1000)
    assert packets(coord) == [bytes.fromhex("e6fe16010000000103")]


@pytest.mark.parametrize("ordinary_press", (False, True))
@pytest.mark.parametrize("write_ms", (0, 100, 175, 1100))
async def test_hold_deadline_includes_transport_time(hold_clock, ordinary_press, write_ms):
    ctrl, coord = await ready()
    coord.motor_pulse_count = 10
    writes = []

    async def write(_char, payload, **_kwargs):
        writes.append((hold_clock.milliseconds, bytes(payload).hex()))
        hold_clock.milliseconds += write_ms

    async def wait(milliseconds, **_kwargs):
        hold_clock.milliseconds += milliseconds
        return False

    coord.client.write_gatt_char.side_effect = write
    ctrl._wait.side_effect = wait
    bound = ctrl.bind_side("left")
    if ordinary_press:
        await bound._run_action("c054")
    else:
        await bound.hold_control("c054", 1000)

    assert all(at < 1000 for at, _ in writes[:-1])
    assert {payload for _, payload in writes[:-1]} == {"e6fe16010000000202"}
    assert writes[-1] == (max(1000, write_ms), "e6fe16000000000203")
    # Release begins at the deadline, or as soon as an in-flight write returns.
    assert len(writes) == {0: 11, 100: 6, 175: 5, 1100: 2}[write_ms]


async def test_failed_pulse_still_attempts_release():
    ctrl, coord = await ready()
    coord.client.write_gatt_char.side_effect = [RuntimeError("failed"), None]
    with pytest.raises(RuntimeError, match="failed"):
        await ctrl.bind_side("right")._run_action("c059")
    assert packets(coord)[-1].hex() == "e6fe16000000000104"


async def test_rgb_and_brightness_require_light_state_and_selected_product():
    ctrl, coord = await ready("4194RGB")
    with pytest.raises(ValueError, match="light-on"):
        await ctrl.set_light_color((127, 200, 255))
    with pytest.raises(ValueError, match="light-on"):
        await ctrl._run_action("c027")
    ctrl._light = True
    await ctrl.set_light_color((127, 200, 255))
    assert packets(coord)[-1].hex() == "0a02000000000101bb80370000"
    await ctrl._run_action("c029")
    assert packets(coord)[-1].hex() == "0a02000000000101bbb3876600"
    with pytest.raises(ValueError, match="unavailable"):
        await ctrl._run_action("c054")


async def test_rename_clock_and_alarm_vectors():
    ctrl, coord = await ready("M30")
    vector = next(v for v in VECTORS if v["id"] == "rename")
    await ctrl.rename_device(vector["inputs"]["text"])
    assert packets(coord)[-1].hex() == vector["expected_bytes"]
    for name in ("", "x" * 17):
        with pytest.raises(ValueError):
            ctrl.validate_device_rename(name)
    now = datetime(2026, 11, 3, 21, 7, 40, tzinfo=ZoneInfo("Europe/Oslo"))
    with patch("custom_components.adjustable_bed.beds.keeson_layout_app.dt_util.now", return_value=now):
        await ctrl.sync_clock()
    assert packets(coord)[-1].hex() == next(
        v["expected_bytes"] for v in VECTORS if v["id"] == "clock"
    )
    # Accepted relative table has 3661 seconds until its one-time target.
    schedule = AlarmTableSchedule(
        weekly=(WeeklyAlarmRecord(enabled=True, hour=7, minute=30, weekdays=(0, 6), wake=True),),
        one_time=(OneTimeAlarmRecord(enabled=True, hour=22, minute=9, wake=True),),
        dispatch="both",
        reference_time=now.replace(minute=7, second=59),
    )
    await ctrl.configure_alarm_table_schedule(schedule)
    expected = [
        next(v["expected_bytes"] for v in VECTORS if v["id"] == key)
        for key in ("alarm-True", "alarm-False")
    ]
    assert [f.hex() for f in packets(coord)[-2:]] == expected
    await ctrl.stop_wake_routine()
    assert packets(coord)[-1].hex() == "e180049a"


@pytest.mark.parametrize(
    "product,name,expected",
    [
        ("M14", "KSBT03CPabc", "040248000000"),
        ("M21", "KSBT03CWabc", "040200011000"),
        ("Flex3 Massage", "KSBT03CPabc", "040248000000"),
        ("20th Anniversary", "anything", "040200011000"),
    ],
)
async def test_meditation_product_and_name_gates(product, name, expected):
    ctrl, coord = await ready(product)
    coord.observed_ble_device_name = name
    await ctrl._run_action("meditation_start")
    assert packets(coord) == [bytes.fromhex(expected), b"\x00\xb0", b"\x00\xb0", b"\x00\xb0"]
    await ctrl._run_action("meditation_stop")
    assert packets(coord)[-4].hex() == "040208000000"
    coord.observed_ble_device_name = "unrelated"
    if product != "20th Anniversary":
        with pytest.raises(ValueError, match="do not admit"):
            await ctrl._run_action("meditation_start")


@pytest.mark.parametrize(
    "vector",
    json.loads((FIXTURES / "seekbar-test-vectors.json").read_text()),
    ids=lambda v: v["id"],
)
async def test_rgb_picker_and_java_brightness_vectors(vector):
    inp = vector["inputs"]
    product = {"C383": "M16", "C384": "M19"}.get(inp["command_id"], "custom")
    ctrl, coord = await ready(
        product, **{CONF_PRODUCT_NAME: inp["selected_name"], "has_light": True, CONF_RGB: True}
    )
    ctrl._light = True
    await ctrl._send_rgb(tuple(inp["rgb"]), round(inp["light_level"] * 100))
    assert packets(coord)[-1].hex() == vector["expected_bytes"]


@pytest.mark.parametrize(
    "vector",
    json.loads((FIXTURES / "catalog-test-vectors.json").read_text()),
    ids=lambda v: v["id"],
)
async def test_catalog_action_bytes(vector):
    if "expected_state" in vector:
        inp = vector["inputs"]
        state = parse_status(
            bytes.fromhex(vector["expected_bytes"]), inp["style"], dynamic=inp["dynamic"]
        )
        expected = dict(vector["expected_state"])
        if "rgb" in expected:
            expected["rgb"] = tuple(expected["rgb"])
        assert state == expected
        return
    if vector["id"].startswith("catalog-query-"):
        ctrl, coord = await ready()
        await ctrl._queries((300, 600, 900))
        assert packets(coord) == [bytes.fromhex(vector["expected_bytes"])] * 3
        return
    if vector["id"].startswith("catalog-init-"):
        coord = coordinator("EZI MAID")
        ctrl = Ergomotion4Controller(coord)
        ctrl._wait = AsyncMock(return_value=False)
        await ctrl.start_notify()
        assert packets(coord) == [bytes.fromhex(vector["expected_bytes"])]
        return
    row = next(r for r in CATALOG if r["id"] == vector["inputs"]["catalog_id"])
    ctrl, coord = await ready(row["name"])
    ctrl._light = True
    if "source_command_id" in vector:
        await ctrl._run_action(ACTIONS[vector["source_command_id"]].key)
    else:
        inp = vector["inputs"]
        await ctrl.set_light_color((inp["r"], inp["g"], inp["b"]))
    assert packets(coord)[0].hex() == vector["expected_bytes"]


async def test_configuration_and_actual_entity_exposure(hass):
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.config_flow import (
        _add_keeson_layout_app_schema_fields,
        _normalize_keeson_layout_app_data,
    )
    from custom_components.adjustable_bed.detection import get_bed_type_options

    data = {"bed_type": "ergomotion_4", "product_type": "M30"}
    schema = {}
    _add_keeson_layout_app_schema_fields(schema, data)
    _normalize_keeson_layout_app_data(data)
    assert data["disable_angle_sensing"] is True
    assert data["has_massage"] is False
    assert any(choice["value"] == "ergomotion_4" for choice in get_bed_type_options())
    ctrl, coord = await ready("M30")
    coord.controller = coord.capability_controller = ctrl
    coord.entity_unique_id.side_effect = lambda key: key
    coord.entity_translation_key.side_effect = lambda key: key
    entities = [entity for entity in _button_entities_for(hass, coord) if hasattr(entity, "_spec")]
    assert {entity._spec.key for entity in entities} == {a.key for a in ctrl._actions()} | {
        "dismiss_alarm"
    }


async def test_options_cannot_switch_paired_p1_to_p2(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import DOMAIN

    data = {
        "address": "AA:BB:CC:DD:EE:FF",
        "bed_type": "ergomotion_4",
        "product_type": "H",
        "pair_id": "pair_hump",
        "pair_mode": "single_address",
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_settings({"product_type": "M19"})
    assert result["type"] == "form"
    assert result["errors"] == {"base": "single_address_pairing_unsupported"}
    assert dict(entry.data) == data


async def test_reconnected_session_does_not_receive_old_queries():
    ctrl, coord = await ready("M19")
    old = ctrl._session_cancel

    async def reconnect(_milliseconds, **_kwargs):
        old.set()
        ctrl._session_cancel = asyncio.Event()
        return False

    ctrl._wait.side_effect = reconnect
    await ctrl._queries((300, 600, 900), cleanup=True)
    assert packets(coord) == []


def test_discovery_ledger_has_complete_coverage_and_resolvable_proofs():
    import ast
    from collections import Counter

    root = Path(__file__).parents[1]
    ledger = json.loads((FIXTURES / "ledger.json").read_text())
    items = ledger["items"]
    assert len(items) == ledger["counts"]["total_items"] == 892
    assert len({i["id"] for i in items}) == len(items)
    assert dict(Counter(i["disposition"] for i in items)) == ledger["counts"]["dispositions"]
    live_commands = {i["source_command_id"] for i in items if i["id"].startswith("command:")}
    assert len(live_commands) == 385
    assert {c["command"].split("_")[0] for c in CASES} == {
        cid for cid in live_commands if cid < "C376"
    }
    assert len([i for i in items if i["id"].startswith("candidate:")]) == 423
    assert len([i for i in items if i["id"].startswith("catalog:")]) == 21
    assert len([i for i in items if i["id"].startswith("route:")]) == 27
    for item in items:
        assert item["evidence"]
        if item["disposition"] == "EXCLUDED":
            assert item["reason_ref"] in ledger["reasons"]
            assert item["id"] in ledger["exclusion_inventory"][item["reason_ref"]]
        else:
            assert item["proof_ref"] in ledger["proofs"]
    for proof in ledger["proofs"].values():
        for reference in proof["code"] + proof["tests"]:
            if "::" not in reference:
                path, line = reference.rsplit(":", 1)
                assert 0 < int(line) <= len((root / path).read_text().splitlines())
                continue
            path, symbol = reference.split("::")
            tree = ast.parse((root / path).read_text())
            names = {
                n.name
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }
            names.update(n.id for n in ast.walk(tree) if isinstance(n, ast.Name))
            assert symbol.split(".")[-1] in names, reference


async def test_native_paired_runtime_routes_left_right_and_both_on_one_connection(hass, hold_clock):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    original = {
        "address": "AA:BB:CC:DD:EE:FF",
        "bed_type": "ergomotion_4",
        "product_type": "H",
        "name": "Split",
        "disable_angle_sensing": True,
    }
    data = build_single_address_pair_entry_data(original, name="Split")
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4)
    entry.add_to_hass(hass)
    inner = AdjustableBedCoordinator(hass, entry)
    inner._client = coordinator().client
    ctrl = Ergomotion4Controller(inner)
    async def wait(milliseconds, **_kwargs):
        hold_clock.milliseconds += milliseconds
        return False

    ctrl._wait = AsyncMock(side_effect=wait)
    await ctrl.start_notify()
    inner._controller = inner._offline_controller = ctrl
    inner._ready = True
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    try:
        with (
            patch.object(inner, "async_connect", AsyncMock(return_value=True)),
            patch.object(inner, "async_ensure_connected", AsyncMock(return_value=True)),
        ):
            for side, expected in (
                ("left", ["e6fe16010000000202", "e6fe16000000000203"]),
                ("right", ["e6fe16010000000103", "e6fe16000000000104"]),
                ("both", ["e5fe160100000005", "e5fe160000000006"]),
            ):
                inner.client.write_gatt_char.reset_mock()
                await pair.async_execute_controller_command(
                    lambda bound: bound.hold_control("c054", 100), side=side
                )
                assert [p.hex() for p in packets(inner)] == expected
        assert pair.children["left"].address == pair.children["right"].address
        assert pair.children["left"].operation_identity == pair.children["right"].operation_identity
        assert ctrl.command_side is None
    finally:
        inner._cancel_disconnect_timer()
        await inner._command_scheduler.async_shutdown()


@pytest.mark.parametrize("bed_type,variant", (("ergomotion", "auto"), ("keeson", "ergomotion")))
@pytest.mark.parametrize("stored_preference", (False, None))
async def test_legacy_split_suppresses_unscoped_positions(hass, bed_type, variant, stored_preference):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.cover import _cover_entities_for
    from custom_components.adjustable_bed.number import _position_number_specs
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    original = {
        "address": "AA:BB:CC:DD:EE:FF",
        "bed_type": bed_type,
        "protocol_variant": variant,
        "name": "Split",
    }
    if stored_preference is not None:
        original["disable_angle_sensing"] = stored_preference
    data = build_single_address_pair_entry_data(original, name="Split")
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4)
    entry.add_to_hass(hass)
    inner = AdjustableBedCoordinator(hass, entry)
    ctrl = KeesonController(inner, variant="ergomotion")
    inner._controller = inner._offline_controller = ctrl
    pair = SingleAddressPairedCoordinator(hass, entry, inner)
    assert inner.disable_angle_sensing is True
    inner._apply_runtime_bed_type_correction(bed_type)
    assert inner.disable_angle_sensing is True
    assert entry.data.get("disable_angle_sensing") is stored_preference
    inner._position_data.update(back=42.0, legs=17.0)
    for side in (*pair.children.values(), pair._single_both):
        updates = []
        side.register_position_callback(updates.append)
        side._sync_position_state()
        assert side.disable_angle_sensing is True
        assert side.position_data == {}
        assert updates == []
        assert _position_number_specs(side) == ()
        covers = _cover_entities_for(hass, side)
        assert covers
        assert all(cover.current_cover_position is None for cover in covers)

    with patch.object(ctrl, "start_notify", new_callable=AsyncMock) as notify:
        await inner.async_start_notify()
        notify.assert_not_awaited()

    # Restoring standalone controls keeps the user's feedback preference.
    standalone = AdjustableBedCoordinator(hass, MockConfigEntry(domain=DOMAIN, data=original))
    assert standalone.disable_angle_sensing is (stored_preference is None)


def _reported_light(ctrl, enabled):
    frame = bytearray(18)
    frame[:3] = b"\xa5\x0b\x0f"
    frame[12] = int(enabled)
    ctrl._parse_notification(bytes(frame))


def _rgb_entity(ctrl, coord):
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedLight

    coord.controller = coord.capability_controller = ctrl
    coord.entity_side = None
    coord.entity_unique_id.side_effect = lambda key: key
    coord.entity_translation_key.side_effect = lambda key: key
    entity = AdjustableBedLight(coord, LIGHT_DESCRIPTION)
    entity.async_write_ha_state = MagicMock()

    def update(values):
        coord.controller_state.update(values)
        entity._handle_light_state(values)

    coord.handle_controller_state_updates.side_effect = update

    async def execute(command, **_kwargs):
        await command(ctrl)

    coord.async_execute_controller_command = AsyncMock(side_effect=execute)
    return entity


async def test_rgb_entity_tracks_reported_power_and_disconnect():
    ctrl, coord = await ready("M19")
    entity = _rgb_entity(ctrl, coord)
    for enabled in (True, False, True):
        _reported_light(ctrl, enabled)
        assert entity.is_on is enabled
        assert coord.controller_state["ergomotion4_light"] is enabled
        assert coord.controller_state["under_bed_lights_on"] is enabled
    ctrl.on_disconnect()
    assert coord.controller_state["under_bed_lights_on"] is None
    assert coord.controller_state["ergomotion4_light"] is None
    assert entity.is_on is False


@pytest.mark.parametrize("enabled", (True, False))
async def test_rgb_entity_power_waits_for_report_before_color(enabled):
    ctrl, coord = await ready("M19")
    entity = _rgb_entity(ctrl, coord)
    _reported_light(ctrl, not enabled)
    deliveries = []

    async def write(_char, payload, **_kwargs):
        if bytes(payload) == bytes.fromhex("040200020000"):

            async def deliver():
                await asyncio.sleep(0)
                # The toggle has been acknowledged but its power report has
                # not arrived. No RGB write is admitted in this interval.
                assert all(not p.startswith(b"\x09\x0a") for p in packets(coord))
                _reported_light(ctrl, enabled)

            deliveries.append(asyncio.create_task(deliver()))

    coord.client.write_gatt_char.side_effect = write
    if enabled:
        await entity.async_turn_on(rgb_color=(127, 200, 255))
        assert packets(coord)[-1].hex() == "090a00020000017fc8ff00"
    else:
        await entity.async_turn_off()
        assert packets(coord) == [bytes.fromhex("040200020000")] + [b"\x00\xb0"] * 3
    await asyncio.gather(*deliveries)
    assert entity.is_on is enabled
    # Repeating the requested state is idempotent, without another toggle.
    count = len(packets(coord))
    await (ctrl.lights_on() if enabled else ctrl.lights_off())
    assert len(packets(coord)) == count


async def test_rgb_power_confirmation_timeout_never_sends_unguarded_color():
    ctrl, coord = await ready("M19")
    entity = _rgb_entity(ctrl, coord)
    _reported_light(ctrl, False)
    with (
        patch(
            "custom_components.adjustable_bed.beds.ergomotion4.LIGHT_POWER_CONFIRM_TIMEOUT_SECONDS",
            0,
        ),
        pytest.raises(TimeoutError),
    ):
        await entity.async_turn_on(rgb_color=(127, 200, 255))
    assert all(not p.startswith(b"\x09\x0a") for p in packets(coord))
    assert ctrl._light is False


@pytest.mark.parametrize("interruption", ("disconnect", "replacement", "cancel"))
async def test_rgb_power_confirmation_stays_on_original_session(interruption):
    ctrl, coord = await ready("M19")
    ctrl._light = False
    ctrl.lights_toggle = AsyncMock()
    task = asyncio.create_task(ctrl.lights_on())
    await asyncio.sleep(0)
    if interruption == "cancel":
        coord.cancel_command.set()
        error = asyncio.CancelledError
    else:
        ctrl._session_cancel.set()
        if interruption == "replacement":
            ctrl._session_cancel = asyncio.Event()
            ctrl._light = True
        else:
            ctrl.on_disconnect()
        error = ConnectionError
    with pytest.raises(error):
        await task
    assert packets(coord) == []


@pytest.mark.parametrize(
    "keys,expected",
    [
        (("o1", "o2", "o5", "o3"), {"C043", "C044"}),
        (("o1", "o5", "o2", "o3", "o4"), {"C043", "C044", "C045"}),
        (("o1", "o2", "o3", "o4"), {"C043", "C044", "C045", "C046"}),
    ],
)
def test_custom_preset_ancestor_gates_keep_o5_slot_consumption(keys, expected):
    # Frozen showRemoteType chooses three visible slots unless all o1..o4
    # exist. dealTagAction consumes a slot even when the tag is inert o5.
    product = custom_product("Other", keys, (), False, False)
    assert set(product.commands) & {"C043", "C044", "C045", "C046"} == expected
