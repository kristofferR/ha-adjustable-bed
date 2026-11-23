"""Complete accepted layouts, parser semantics and fenced controller callers."""

from __future__ import annotations

import asyncio
import json
from copy import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.majestichome import controller as bed
from custom_components.adjustable_bed.beds.majestichome.protocol import Alarm, Receiver, decode
from custom_components.adjustable_bed.beds.majestichome.requests import Request
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.majestichome import LAYOUTS
from tests.test_controller_contract import _FactoryCoordinator

ROOT = Path(__file__).parent / "fixtures/majestichome"
GATT = json.loads((ROOT / "gatt.json").read_text())


def test_all_six_gatt_definitions_include_unused_declared_rx_metadata():
    for row, key in zip(GATT, ("n1", "w1", "w2", "w3", "w4", "w5"), strict=True):
        route = codec.TRANSPORTS[key]
        assert (
            route.service_uuid.lower(),
            route.write_uuid.lower(),
            route.notify_uuid.lower(),
        ) == tuple(row[name].lower() for name in ("service", "write", "declared_notify"))
        assert route.single == (row["wire"] == "P1")


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    sleep = asyncio.sleep

    async def delay(self, milliseconds):
        now[0] += milliseconds / 1000
        await sleep(0)
        return not self._coordinator.cancel_command.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MajesticHomeController, "_delay", delay)
    monkeypatch.setattr(bed, "FIRST_WRITE_MS", 0)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.goodvibe.controller.QUEUE_MS", 0)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.goodvibe.controller.MENU_PROBE_S", 0)
    return now


def make(product="FARM", route=1, properties=("write",)):
    c = _FactoryCoordinator()
    c.handle_controller_state_updates = MagicMock()
    c.record_command_trace = MagicMock()
    c.client = MagicMock(is_connected=True)
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    row = GATT[route]
    tx = SimpleNamespace(uuid=row["write"].lower(), properties=list(properties), handle=1)
    rx = SimpleNamespace(uuid="first-notify", properties=["notify"], handle=2)
    c.client.services = [SimpleNamespace(uuid=row["service"].upper(), characteristics=[tx, rx])]
    obj = bed.MajesticHomeController(c, product=product)
    c.controller = obj
    return obj, c


def written(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


def notify(c, value):
    call = c.client.start_notify.call_args
    call.args[1](call.args[0], bytearray.fromhex(value))


@pytest.mark.parametrize(
    "product", json.loads((ROOT / "products.json").read_text()), ids=lambda p: p["id"]
)
def test_all_ordered_product_groups_overrides_and_saves(product):
    key = product["identifier"] or "none"
    layout = LAYOUTS[key]
    groups = product["groups"]
    expected = [
        (c["code"], c["save_code"])
        for group in ("motor", "massage", "preset")
        for c in groups[group]
    ]
    assert [(c.code, c.save) for c in layout.controls] == expected
    assert [layout.control(key).code for key in layout.alarms] == [
        c["code"] for c in groups["alarm_preset"]
    ]


@pytest.mark.parametrize("v", json.loads((ROOT / "parser.json").read_text()), ids=lambda v: v["id"])
def test_every_accepted_parser_fixture(v):
    assert decode(bytes.fromhex(v["frame"])) == v["expected"]


def test_stream_fragment_checksum_delimiter_and_excluded_ota_boundaries():
    literal = bytes.fromhex("6e09010078")
    packet = bytes.fromhex("6e200d0501020100071e2ef9f0")
    rx = Receiver()
    assert rx.feed(packet[:4]) == []
    assert rx.feed(packet[4:]) == [packet]
    damaged = packet[:-1] + bytes((packet[-1] ^ 1,))
    assert rx.feed(damaged) == []
    assert rx.feed(literal[:3]) == [literal[:3]]
    assert rx.feed(literal[3:]) == []
    assert not rx.feed(b"\x00")
    assert rx.feed(bytes.fromhex("6e23a06e9f")) == [bytes.fromhex("6e23a0")]
    assert rx.feed(literal) == [bytes.fromhex("6e9f"), literal]
    assert rx.feed(bytes.fromhex("6e900002ff")) == [bytes.fromhex("6e900002ff")]
    assert decode(bytes.fromhex("6e900002ff")) == {"version": 2}
    assert Receiver().feed(bytes.fromhex("6e2000")) == []
    ota = bytes.fromhex("6e4000060000")
    assert Receiver().feed(ota + literal) == [literal]
    assert decode(codec.record_20_len(6, 4, 3, (0, 0, 1))) == {}


@pytest.mark.parametrize("route", range(6))
@pytest.mark.parametrize("product", ("FARM", "JLRM", "JGRN", "JHRN", "none"))
async def test_all_gatt_routes_startup_and_every_control(clock, route, product):
    obj, c = make(product, route, ("write", "write-without-response"))
    await obj.start_notify()
    raw = route == 0
    packets = written(c)
    assert packets[0] == ("00" if raw else "6e02010071")
    assert packets[-1] == ("01" if raw else "6e08010178")
    assert len(packets) == (4 if obj.layout.alarms else 2)
    assert c.client.start_notify.call_args.args[0].uuid == "first-notify"
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)
    for control in obj.layout.controls:
        for save in (False, True) if control.save is not None else (False,):
            c.client.write_gatt_char.reset_mock()
            if control.held:
                await obj.hold_control(control.key, 250)
                assert written(c) == [codec.function(control.code, single=raw).hex()] * 2 + [
                    codec.function(110, single=raw).hex()
                ]
            else:
                await obj.action(control.key, save=save)
                assert written(c) == [
                    codec.function(control.save if save else control.code, single=raw).hex()
                ]


@pytest.mark.parametrize(
    "v", json.loads((ROOT / "lifecycle.json").read_text()), ids=lambda v: v["id"]
)
async def test_actual_lifecycle_callers_match_all_five_fixtures(clock, v):
    obj, c = make()
    await obj.start_notify()
    c.client.write_gatt_char.reset_mock()
    if v["kind"] == "sustain":
        # These immutable fixtures describe app enqueue gestures, including a
        # sub-100 ms release, independently of the finite HA action minimum.
        await obj._run_hold_window("head_up", v["release_ms"])
        actual = ["stop" if p == "6e01006edd" else "move" for p in written(c)]
    else:
        await obj.action("memory_1", save=v["kind"] == "save")
        actual = ["save" if p == "6e01002b9a" else "recall" for p in written(c)]
    assert actual == v["expected_queue_actions"]


async def test_transport_property_and_multi_service_header_order(clock):
    obj, c = make(route=0)
    c.client.services.append(SimpleNamespace(uuid=GATT[1]["service"], characteristics=[]))
    await obj.start_notify()
    assert obj._link.legacy is False
    assert obj._link.tx.uuid == GATT[0]["write"].lower()
    assert written(c)[0] == "6e02010071"
    assert all(call.kwargs["response"] for call in c.client.write_gatt_char.call_args_list)
    obj, _ = make(properties=("write-without-response",))
    with pytest.raises(ValueError, match="write and notify"):
        await obj.start_notify()


async def test_slow_write_consumes_deadline_and_cleanup_uses_fresh_cancel(clock):
    obj, c = make()
    await obj.start_notify()
    c.client.write_gatt_char.reset_mock()

    async def delayed(_char, packet, **kwargs):
        if packet.hex() == "6e01002493":
            clock[0] += 1
            c.cancel_command.set()

    c.client.write_gatt_char.side_effect = delayed
    await obj.hold_control("head_up", 250)
    assert written(c) == ["6e01002493", "6e01006edd"]


async def test_callbacks_and_alarm_plans_are_physical_session_owned(clock):
    obj, c = make()
    await obj.start_notify()
    notify(c, "6e09010078")
    notify(c, "6e200d0501020100071e2ef9f0")
    assert obj.alarms[1] == Alarm(1, 0, 7, 30, 46, 249)
    plan = obj.prepare(Request("toggle", number=1, enabled=False))
    assert plan.packets[0].hex() == "6e0d200501010100071e2ef8ee"
    await obj.execute_prepared(plan)
    assert obj.alarms[1].repeat == 249
    with pytest.raises(ValueError, match="Query current"):
        obj.prepare(Request("toggle", number=1))
    callback = c.client.start_notify.call_args
    obj.on_disconnect()
    callback.args[1](callback.args[0], bytearray.fromhex("6e09010078"))
    assert not obj.observations and not obj.alarms
    with pytest.raises(ConnectionError):
        obj.validate_plan(plan)


async def test_same_address_and_client_cannot_transfer_a_running_owner(clock):
    obj, c = make()
    await obj.start_notify()
    other = copy(c)
    obj._coordinator = other
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(ConnectionError, match="physical controller"):
        await obj.action("flat")
    assert not written(c)


async def test_alarm_modes_allocator_and_unknown_received_toggle_fields(clock):
    obj, c = make()
    await obj.start_notify()
    notify(c, "6e09010078")
    with pytest.raises(ValueError, match="full alarm list"):
        obj.prepare(Request("new"))
    for key in obj.layout.alarms:
        packet = obj.prepare(Request("set", number=7, preset=key, weekdays=(0, 6))).packets[0]
        assert packet[10] == obj.layout.control(key).code and packet[11] == 131
    obj.alarms[1] = Alarm(1, 99, 22, 45, 250, 131)
    with pytest.raises(ValueError, match="full alarm list"):
        obj.prepare(Request("new"))
    assert obj.prepare(Request("new", number=2)).packets[0][6] == 2
    toggle = obj.prepare(Request("toggle", number=1, enabled=False)).packets[0]
    assert list(toggle[6:12]) == [1, 99, 22, 45, 250, 130]
    obj._stale.add(1)
    with pytest.raises(ValueError, match="Query current"):
        obj.prepare(Request("toggle", number=1))


def test_no_factory_reset_or_unproven_writer_exposure():
    for layout in LAYOUTS.values():
        assert all("factory" not in control.key for control in layout.controls)


def test_preset_saves_use_the_save_placement():
    from custom_components.adjustable_bed.card import CARD_PRESET_SAVE

    controller, _ = make("FARM")
    saves = [spec for spec in controller.controller_button_specs if spec.name.startswith("Save ")]
    assert {spec.name for spec in saves} >= {"Save Zero Gravity", "Save Anti-Snore"}
    for spec in saves:
        if spec.key.startswith("majestichome_memory_"):
            # A memory save is offered in the card's Set mode; it asks no second time.
            assert spec.translation_key.startswith("program_memory_")
            assert not spec.requires_confirmation
        else:
            assert spec.card == CARD_PRESET_SAVE and spec.translation_key == "catalog_save"
            assert spec.requires_confirmation


async def test_timer_keys_are_one_select_and_level_keys_one_number_per_zone(clock):
    obj, c = make("FARM")
    await obj.start_notify()
    keys = {spec.key for spec in obj.controller_button_specs}
    assert not keys & {f"majestichome_{key}" for key in bed._FOLDED}
    assert "majestichome_massage_off" in keys
    assert obj.auto_enable_massage and obj.massage_timer_can_turn_off
    assert obj.massage_timer_options == [10, 20, 30]
    assert obj.massage_intensity_zones == ["head", "foot"] and obj.massage_intensity_max == 3
    cases = [
        (lambda: obj.set_massage_timer(20), "massage_20"),
        (lambda: obj.set_massage_timer(0), "massage_off"),
        (lambda: obj.set_massage_intensity("head", 2), "head_massage_2"),
        (lambda: obj.set_massage_intensity("foot", 3), "foot_massage_3"),
    ]
    for call, key in cases:
        c.client.write_gatt_char.reset_mock()
        await call()
        sent = written(c)
        c.client.write_gatt_char.reset_mock()
        await obj.action(key)
        assert sent == written(c), key


async def test_all_off_resets_the_timer_and_both_levels(clock):
    obj, c = make("FARM")
    await obj.start_notify()
    c.handle_controller_state_updates.reset_mock()
    await obj.action("massage_off")
    (updates,) = [call.args for call in c.handle_controller_state_updates.call_args_list][-1:]
    assert {str(update.key): update.value for update in updates} == {
        "massage_timer": 0,
        "massage_head_intensity": 0,
        "massage_foot_intensity": 0,
    }


@pytest.mark.parametrize("product", ["FARM", "JLRM", "JGRN", "JHRN"])
async def test_every_offered_massage_level_and_timer_sends_a_frame(clock, product):
    obj, c = make(product)
    await obj.start_notify()
    for zone in obj.massage_intensity_zones:
        low = obj.massage_intensity_min(zone)
        # A zone offers off only with its own off key.
        assert low == (0 if any(k.key == f"{zone}_massage_off" for k in obj.layout.controls) else 1)
        for level in range(low, obj.massage_intensity_max + 1):
            c.client.write_gatt_char.reset_mock()
            await obj.set_massage_intensity(zone, level)
            assert written(c), (zone, level)
    timers = [*obj.massage_timer_options, *((0,) if obj.massage_timer_can_turn_off else ())]
    for minutes in timers:
        c.client.write_gatt_char.reset_mock()
        await obj.set_massage_timer(minutes)
        assert written(c), minutes
