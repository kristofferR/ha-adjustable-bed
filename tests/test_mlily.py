"""MLILY Control 5.0.2, frozen row159 literals and complete product contracts.

Fixtures retain literal inputs/results from reconciliation002, manifest SHA256
8c7de25122ef3af4a43fe2aa38e0aec0ae95b8a697a1dbfd66801378ec3fcfdd.
Service labels from V001-V006 are corrected by CF001, without changing bytes.
These are static artifact tests, not hardware captures.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import astuple
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.goodvibe import protocol as p
from custom_components.adjustable_bed.beds.goodvibe import services as configuration
from custom_components.adjustable_bed.beds.goodvibe.controller import (
    GoodVibeController,
    Link,
    select_link,
)
from custom_components.adjustable_bed.beds.goodvibe.receive import Notifications, common
from custom_components.adjustable_bed.beds.goodvibe.services import Request
from custom_components.adjustable_bed.beds.goodvibe.sleep import sleep_packet
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.profiles.mlily import catalog
from custom_components.adjustable_bed.profiles.mlily_choices import PROFILE_CHOICES
from tests.test_goodvibe_ha import runtime as goodvibe_runtime

FIXTURES = Path(__file__).parent / "fixtures/mlily"


@pytest.fixture(autouse=True)
def no_protocol_waits(monkeypatch):
    monkeypatch.setattr("custom_components.adjustable_bed.beds.goodvibe.controller.QUEUE_MS", 0)


def fixture(name):
    return json.loads(gzip.decompress((FIXTURES / f"{name}.json.gz").read_bytes()))


def runtime(hass, model="6brm"):
    c = goodvibe_runtime(hass)
    c._controller.on_disconnect()
    c._controller = GoodVibeController(c, profile=model, catalog=catalog())
    c._controller._link = Link(c._client, MagicMock(uuid="tx", properties=["write"], handle=1),
                               MagicMock(uuid="rx", properties=["notify"], handle=2), False)
    c._client.write_gatt_char = AsyncMock()
    c._client.mtu_size = 512
    return c


def test_all_12354_control_occurrences_and_catalog_gates():
    app = catalog()
    rows = fixture("controls")
    assert len(rows) == 12354
    occurrences = {}
    for _ordinal, code, key, expected in rows:
        assert list(astuple(app.actions[key])) == expected
        occurrences.setdefault(code, []).append(key)
    assert len([key for key in app.products if "/" not in key]) == 808
    assert set(PROFILE_CHOICES) == {*app.products, "sleep_rm", "sleep_hj"}
    for code, product in app.products.items():
        assert product.actions == tuple(occurrences[code.split("/")[-1]]) if product.actions else True
    assert not {"fwrm", "wfrm", ""} & app.products.keys()
    assert {product.label for product in app.products.values() if product.massage_timer} == {"D1RM", "D9RM"}
    assert {product.label for product in app.products.values() if product.sleep == "deviceSleepMonitoringBle"} == {
        "ETRN", "G1RN", "G2RN", "HNRN", "HQRN", "HSRN", "HURN",
    }
    assert app.products["mhrn/hnrn"] is app.products["hnrn"]


def test_every_inherited_literal_uses_the_richmat_codec():
    count = 0
    for row in fixture("wire"):
        i = row["inputs"]
        if "item" in i:
            item = i["item"]
            long = i["long"]
            single = i["route"] == "legacy"  # CF001: this is the Nordic service.
            code = (
                item.get("long_override") if long else item.get("default_override") if single else None
            )
            if code is None:
                code = item.get("enum_long_command", 0) if long else (
                    item.get("short_override") if item.get("short_override") is not None else item["default_command"]
                )
            got = codec.function(code or 0, i["side"], single=single, action=item["action"])
        elif "code" in i:
            single = i["nordic"] if type(i["nordic"]) is bool else False
            got = codec.function(i["code"], i["side"], single=single)
            if "nordic" in row:
                assert codec.function(i["nordic"], single=True).hex() == row["nordic"].replace(" ", "")
        elif "notification" in i:
            assert common(list(bytes.fromhex(i["notification"])))[0] == (row["event"], None)
            got = bytes.fromhex(i["notification"])
        elif "group" in i:
            # Excluded desk vectors still prove their shared framing, without a desk controller.
            got = codec.frame(0x6E, i["group"], 0, i["command"])
        elif "value" in i:
            got = codec.frame(0x6E, 0x88, int(i["value"] / 100), i["value"] % 100)
        else:
            pytest.fail(row["id"])
        assert got.hex() == row["hex"], row["id"]
        count += 1
    assert count == 23480
    # Remaining per-product side combinations are frozen from the accepted
    # report's independent wire() encoder and original normalized operands.
    for _product, _detail, side, nordic, _long, code, expected in fixture("sides"):
        assert codec.function(code, side, single=nordic).hex() == expected


def test_all_alarm_profile_modes_use_their_exact_catalog_operands():
    app = catalog()
    profiles = fixture("alarm_profiles")
    assert len(profiles) == 136
    assert sum(len(profile["modes"]) for profile in profiles) == 554
    for profile in profiles:
        product = app.products[profile["code"].lower()]
        assert product.repeat_alarm == (profile["kind"] == "repeat")
        assert len(product.alarms) == len(profile["modes"])
        for key, mode in zip(product.alarms, profile["modes"], strict=True):
            action = app.actions[key]
            assert (action.label, action.short, action.recovered_short) == (
                mode["action"], mode["save_code"], mode["edit_recovered_code"],
            )


def test_all_1358_alarm_vectors_preserve_frozen_wire_frames():
    cases = fixture("alarms")
    assert len(cases) == 1358
    for case in cases:
        x, expected = case["inputs"], case["expected_result"]
        frames = expected["constructed_frames"]
        if not frames:
            continue  # UI-only and writer-rejection states have no extra command.
        operation = x["operation"]
        if operation == "single_save":
            got = p.clock(expected["countdown_minutes"], expected["mode_code"])
        elif operation == "single_cancel":
            got = p.clock(0, 0)
        elif operation in ("repeat_save", "repeat_toggle"):
            bean = expected["bean"]
            got = (codec.record_20_len(5, 1, 1, bean),)
        elif operation == "repeat_delete":
            got = (p.delete_alarm(x["bean"][0]),)
        elif operation == "repeat_query":
            got = (p.QUERIES["alarms"],)
        else:
            pytest.fail(operation)
        assert [frame.hex() for frame in got] == frames, case["id"]


def test_corrected_shared_builders_match_frozen_literals():
    for row in fixture("shared"):
        i = row["inputs"]
        match row["builder"]:
            case "generic":
                data = (bytes((i["code"],)) if i.get("nordic") else
                        codec.frame(*i.get("prefix", [0x6E, 1, i.get("side", 0)]), i["code"]))
            case "clock":
                data = b"".join(p.clock(i["minutes"], i["action"]))
            case "light_seconds":
                data = p.light_duration(i["seconds"])
            case "color_channels":
                data = codec.rgb(i["c1"], i["c2"], i["c3"])
            case "alarm":
                data = codec.record_20_len(5, 1, 1, i["fields"])
            case "delete_alarm":
                data = p.delete_alarm(i["identifier"])
            case "sync":
                parts = i["parts"]
                data = codec.record_20_len(8, 2, 1, (*int(i["epoch"]).to_bytes(4, "big"), i["utc_hours"]))
                data += codec.record_20_len(8, 3, 1, (parts[0]-1970, *parts[1:]))
            case "sumframe":
                data = codec.frame(*i["data"])
            case "crc":
                assert codec.is_valid_crc(bytes.fromhex(i["data"] + row["expected_bytes"]))
                continue
            case "sleep_json":
                from custom_components.adjustable_bed.codec import sleep_envelope

                obj = {"id": i["sequence"], "cmd": i["command"]}
                if "value" in i:
                    obj["val"] = i["value"]
                data = sleep_envelope.frame(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode(), i["sequence"])
            case "sleep":
                from custom_components.adjustable_bed.codec import sleep_envelope

                data = sleep_envelope.frame(bytes.fromhex(i["payload"]), i["sequence"], total=i.get("total",1), sequence=i.get("index",0))
            case _:
                pytest.fail(row["builder"])
        assert data.hex() == row["expected_bytes"], row["id"]


def test_binary_reply_parser_matches_mlily_domains_and_fragmentation():
    events = []
    receiver = Notifications(lambda key, value: events.append((key, value)), mlily=True)
    receiver.feed(bytes.fromhex("6e2100008f"))
    assert events[-1] == ("deviceCharacteristicsSubscriptionSnoreEvent", None)
    receiver.feed(codec.frame(0x6E,0x90,0x36,0x44))
    assert events[-1] == ("deviceVersionOneMotorAngleEvent", {"no":1,"status":2,"angle":68})
    receiver.feed(codec.frame(0x6E,0x90,0xAA,0xBC))
    assert events[-1][1] == {"mode":5,"massage1":4,"massage2":7,"massage3":2}
    # The frozen leaf fixture supplies fields, not a checksum-valid notification.
    record = codec.frame(*bytes.fromhex("6e200e010202000190034400c8"))
    receiver.feed(record[:8])
    receiver.feed(record[8:])
    assert events[-1] == ("deviceMotorCurrentHeightStatusEvent", {"height":40.0,"type":3,"angle":68,"monitorHeight":20.0})
    before = list(events)
    receiver.feed(codec.record_20_len(14,1,2,(0,1)))
    assert events == before  # No MLILY consumer for another app's fan domain.
    receiver.feed(bytes.fromhex("6e4000"))
    receiver.feed(bytes.fromhex("00"))
    assert receiver.rejection is not None


async def test_every_profile_builds_its_declared_entities_and_hold_scope(hass):
    c = goodvibe_runtime(hass)
    app = catalog()
    for profile in app.products:
        obj = GoodVibeController(c, profile=profile, catalog=app)
        controls = set(obj.held_control_options)
        for spec in obj.controller_button_specs:
            if spec.hold is not None:
                assert spec.hold.control in controls
        assert (obj.execution.hold_controls or frozenset()) <= controls
        assert obj.supports_single_address_pairing == ({0,1} <= set(obj.product.sides))


async def test_masks_latches_side_routing_and_cancellation(hass):
    c = runtime(hass, "brrm")
    obj = c.controller
    assert obj.choices.release is True
    detail = next(key for key in obj.control_actions if obj.catalog.actions[key].force_long and not obj.catalog.actions[key].hidden)
    with patch.object(obj, "_delay", AsyncMock(return_value=True)):
        await obj.press(detail, 10)
    assert c._client.write_gatt_char.call_args_list[0].args[1] == bytes.fromhex("6e0100006f")
    assert obj.choices.memory is False
    c = runtime(hass, "e3rm")
    obj = c.controller
    memory = next(key for key in obj.control_actions if obj.catalog.actions[key].label == "deviceFunctionItemMemory")
    preset = next(key for key in obj.control_actions if obj.catalog.actions[key].label == "deviceFunctionItemMemoryPosition1")
    with patch.object(obj, "_delay", AsyncMock(return_value=True)):
        await obj.press(memory, 10)
        assert obj.choices.memory is True
        await obj.press(preset, 10)
        assert obj.choices.memory is False
    # The normal callback emits the long operand, then releases with fresh cleanup.
    assert codec.command(obj.catalog.actions[preset].long) in [call.args[1] for call in c._client.write_gatt_char.call_args_list]
    c._cancel_command.set()
    await obj.stop_all()
    assert c._client.write_gatt_char.call_args.args[1] == codec.command(0x6E)


async def test_menus_require_current_product_and_reply(hass):
    c = runtime(hass, "l3rm")
    obj = c.controller
    request = Request("single", action=obj.product.alarms[0], when=datetime(2026,11,11,7,tzinfo=UTC))
    with pytest.raises(ValueError, match="alarm menu"):
        request.validate(obj)
    obj._normal.feed(bytes.fromhex("6e09010078"))
    request.validate(obj)
    assert not obj.menu_available("light")
    obj._normal.feed(bytes.fromhex("6e0e00037f"))
    assert obj.menu_available("light")
    assert not obj.menu_available("sleep")
    with pytest.raises(ValueError, match="snore settings"):
        Request("snore_query").validate(obj)


async def test_repeat_record_dedup_first_id_escalation_and_safe_full_list(hass):
    c = runtime(hass, "mdrn")
    obj = c.controller
    obj._normal.feed(bytes.fromhex("6e09010078"))
    first = [1,0,7,0,69,1]
    second = [1,0,8,0,70,1]
    for row in (first, first, second):
        obj._normal.feed(codec.record_20_len(5,1,2,row))
    assert obj.choices.events["repeat_alarm_records"] == [first, second]
    changed = [1,0,9,0,69,129]
    obj._normal.feed(codec.record_20_len(5,1,3,changed))
    assert obj.choices.events["repeat_alarm_records"] == [changed,second]
    request = Request("toggle", record=tuple(second), enabled=False)
    request.validate(obj)
    assert request.frames(obj) == (codec.record_20_len(5,1,1,(*second[:5],0)),)
    with pytest.raises(ValueError, match="unknown"):
        Request("repeat", record=tuple(second)).validate(obj)
    known = (*second[:4], obj.catalog.actions[obj.product.alarms[0]].short, second[5])
    edited = Request("repeat", record=known)
    edited.validate(obj)
    assert edited.frames(obj)[0][6:10] == bytes((1,0,8,0))
    obj.choices.events["repeat_alarm_records"] = [[n,0,7,0,69,1] for n in range(1,8)]
    with pytest.raises(ValueError, match="Choose alarm_id or alarm_record"):
        Request("repeat", action=obj.product.alarms[0], when=datetime.now(UTC)).plan(obj)


@pytest.fixture
async def alarm_service(hass):
    c = runtime(hass, "mdrn")
    c.controller._normal.feed(bytes.fromhex("6e09010078"))
    configuration.async_register_goodvibe_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
        patch("custom_components.adjustable_bed.beds.goodvibe.controller.asyncio.sleep", AsyncMock()),
    ):
        yield c
    c._client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("cache", ("cold", "queried", "partial", "reconnected", "full"))
async def test_repeat_service_never_allocates_from_an_unproven_list(hass, alarm_service, cache):
    c = alarm_service
    obj = c.controller
    if cache in ("partial", "reconnected", "full"):
        slots = range(1, 8) if cache == "full" else (1, 3, 6)
        for slot in slots:
            obj._normal.feed(codec.record_20_len(5, 1, 2, (slot, 0, 7, 0, 0x56, 1)))
    if cache == "queried":
        await hass.services.async_call(
            DOMAIN, "mlily", {"device_id": "bed", "operation": "alarms"}, blocking=True
        )
        assert c._client.write_gatt_char.await_args.args[1] == p.QUERIES["alarms"]
        c._client.write_gatt_char.reset_mock()
    if cache == "reconnected":
        old = obj._link
        obj.on_disconnect()
        obj._link = Link(old.client, old.tx, old.rx, old.legacy)
        obj._normal.feed(bytes.fromhex("6e09010078"))
    request = Request("repeat", action=obj.product.alarms[0], when=datetime(2026, 11, 11, 7, tzinfo=UTC))
    with pytest.raises(ValueError, match="Choose alarm_id or alarm_record"):
        request.plan(obj)
    with pytest.raises(ValueError, match="Choose alarm_id or alarm_record"):
        await obj.async_execute_goodvibe_request(request)
    with pytest.raises(ServiceValidationError, match="Choose alarm_id or alarm_record"):
        await hass.services.async_call(
            DOMAIN, "mlily",
            {"device_id": "bed", "operation": "repeat", "action": request.action,
             "datetime": request.when}, blocking=True,
        )
    c._client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("edit", (False, True), ids=("explicit-id", "observed-record"))
async def test_repeat_service_keeps_the_explicit_slot_when_cache_changes(hass, alarm_service, edit):
    c = alarm_service
    obj = c.controller
    action = obj.product.alarms[0]
    code = obj.catalog.actions[action].short
    record = (3, 0, 7, 15, code, 0x81)
    data = {"alarm_record": record} if edit else {
        "alarm_id": 3, "action": action, "datetime": datetime(2026, 11, 11, 7, 15, tzinfo=UTC),
        "weekdays": [0],
    }
    original_plan = Request.plan

    def plan_then_receive(request, target):
        planned = original_plan(request, target)
        assert planned.alarm_id == 3
        # A cache change after preflight must not turn an explicit edit into allocation.
        target.choices.events["repeat_alarm_records"] = [
            [slot, 0, 8, 30, code, 1] for slot in range(1, 8)
        ]
        return planned

    with patch.object(Request, "plan", plan_then_receive):
        await hass.services.async_call(
            DOMAIN, "mlily", {"device_id": "bed", "operation": "repeat", **data}, blocking=True,
        )
    frames = [call.args[1] for call in c._client.write_gatt_char.await_args_list]
    assert frames == [p.repeat_alarm(3, 7, 15, code, 0x81), p.QUERIES["alarms"]]


async def test_sleep_sessions_use_distinct_gatt_roles_and_optional_values(hass):
    tx1 = MagicMock(uuid="first", properties=["write-without-response", "notify"])
    tx2 = MagicMock(uuid="last", properties=["write-without-response"])
    rx = MagicMock(uuid="notify", properties=["notify"])
    client = MagicMock(services=[MagicMock(uuid="0000e0ff-3c17-d293-8e48-14fe2e4da212", characteristics=[tx1,rx,tx2])])
    link = select_link(client,2,catalog().profile,strict_sleep=True)
    assert link.tx is tx2 and link.rx is rx
    c = runtime(hass,"sleep_hj")
    obj = c.controller
    await obj.sleep_request("sensitivity")
    sent = b"".join(call.args[1] for call in c._client.write_gatt_char.call_args_list)
    assert json.loads(sent[14:]) == {"id":1,"cmd":"q_sens"}
    c._client.write_gatt_char.reset_mock()
    await obj.sleep_request("anti_snore", Request("anti_snore",left=1,right=0))
    sent = b"".join(call.args[1] for call in c._client.write_gatt_char.call_args_list)
    assert json.loads(sent[14:]) == {"id":2,"cmd":"s_antiSnore","val":{"L":1,"R":0}}
    obj._sleep.begin("q_sens")
    old_link = obj._link
    obj.on_disconnect()
    assert obj._sleep.last is None
    obj._notification(old_link, old_link.rx, bytearray(sleep_packet(1,"q_sens",{})))
    assert obj._link is None
