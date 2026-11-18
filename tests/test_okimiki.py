"""Okimiki product, parser, HA caller and captured-session contracts."""

from __future__ import annotations

import asyncio
import gzip
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from custom_components.adjustable_bed.beds.goodvibe.controller import Link
from custom_components.adjustable_bed.beds.okimiki import controller as bed
from custom_components.adjustable_bed.beds.okimiki import protocol as p
from custom_components.adjustable_bed.beds.okimiki.services import Request
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.okimiki import (
    CONTROLS,
    PRODUCTS,
    SCAN_KEYWORDS,
    WIRE,
    scan_matches,
)
from tests.test_goodvibe import coordinator as coordinator
from tests.test_goodvibe import writes
from tests.test_okimiki_vectors import FIXTURES
from tests.test_wire_snapshot import _load_tool


@pytest.fixture
def obj(coordinator):
    coordinator.entry.data = {"bed_type": "okimiki", "protocol_variant": "KWRN"}
    coordinator.motor_pulse_count = 10
    coordinator.motor_count = 2
    obj = bed.OkimikiController(coordinator, "KWRN")
    tx = SimpleNamespace(uuid="tx", handle=1, properties=["write", "write-without-response"])
    rx = SimpleNamespace(uuid="rx", handle=2, properties=["notify"])
    obj._link = Link(coordinator.client, tx, rx, False)
    return obj


@pytest.fixture
async def virtual():
    tool = _load_tool()
    with tool.virtual_time(tool.FakeClock()) as clock:
        yield clock


def test_full_catalog_metadata_and_actual_body_bindings():
    data = json.loads(gzip.decompress((FIXTURES / "catalog.json.gz").read_bytes()))
    rows = data["variants"]
    assert len(rows) == len({row["id"] for row in rows}) == 1029
    assert {row["enum_index"] for row in rows} == set(range(1029))
    live = {row["id"] for row in rows if "supportOkimiki" in row["support_values"]}
    assert live == set(PRODUCTS)
    for row in rows:
        assert row["disposition"] == ("REACHABLE" if row["id"] in live else "DEAD/UNUSED")
        assert row["factory_allocation"] and row["factory_branch"].startswith("0x")
        for dispatch in row["dispatch"].values():
            assert dispatch["raw_index"] == 4096 + row["cid"] + dispatch["signed_element_offset"]
            assert dispatch["target"].startswith("0x") and dispatch["body_source"]["file"]
        if row["id"] in PRODUCTS:
            product = PRODUCTS[row["id"]]
            assert (product.enum_index, product.cid, product.factory_branch) == (
                row["enum_index"],
                row["cid"],
                row["factory_branch"],
            )
            assert (product.support_body, product.menu_body, product.alarm_body) == tuple(
                row["dispatch"][key]["target"]
                for key in ("appSupportList", "detailsPageDisplayList", "alarmList")
            )
    assert PRODUCTS["IQRM"].menu_body == PRODUCTS["KWRN"].menu_body
    assert PRODUCTS["IQRM"].alarm_body != PRODUCTS["KWRN"].alarm_body
    assert PRODUCTS["IPRM"].memory_slots == 0


@pytest.mark.parametrize("code", PRODUCTS)
async def test_factory_setup_profile_persistence_and_native_entities(hass, coordinator, code):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import APP_VARIANT_CHOICES, get_bed_type_options
    from custom_components.adjustable_bed.profile_id import profile_route, with_profile_ids
    from custom_components.adjustable_bed.setup_questions import setup_profile
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    coordinator.entry.data = {"bed_type": "okimiki", "protocol_variant": code}
    controller = await create_controller(coordinator, "okimiki", code, None)
    assert isinstance(controller, bed.OkimikiController)
    assert controller.profile is WIRE and controller.product_key == code
    assert {spec.key for spec in controller.motor_control_specs} == {"back", "legs", "both"}
    assert controller.memory_slot_count == PRODUCTS[code].memory_slots
    assert not controller.supports_single_address_pairing
    assert not controller.supports_lights
    assert not controller.controller_number_specs
    assert all("goodvibe" not in spec.key for spec in controller.controller_button_specs)
    assert is_valid_variant_for_bed_type("okimiki", code)
    assert not is_valid_variant_for_bed_type("okimiki", "auto")
    assert "Okimiki" in APP_VARIANT_CHOICES["okimiki", code]
    assert any("Okimiki" in row["label"] for row in get_bed_type_options())
    setup = setup_profile("okimiki")
    assert setup is not None and set(setup.questions[0].options({})) == set(PRODUCTS)
    assert setup.fixed_values()["motor_count"] == 2
    assert "motor_count" in hidden_generic_fields("okimiki", code)
    assert per_side_profile("okimiki", code).variant_owned
    data = with_profile_ids(coordinator.entry.data)
    assert data["profile_id"] == "okimiki:" + code
    assert profile_route(data["profile_id"]).variant == code
    for bad in ("", "auto", "6BRM", "sleep_rm", "iqrm"):
        with pytest.raises(ValueError):
            bed.OkimikiController(coordinator, bad)


def test_scan_keeps_substrings_case_and_no_product_inference():
    for keyword in SCAN_KEYWORDS:
        assert scan_matches("prefix" + keyword + "suffix")
    assert not scan_matches(None)
    assert not scan_matches("hcrn")


def test_app_hint_is_opt_in_without_contesting_established_receivers():
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_detection import _make_service_info

    advert = _make_service_info(
        "QRRM157738",
        service_uuids=["0000fee9-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={19543: bytes.fromhex("54307651")},
    )
    detected = detect_bed_type_detailed(advert)
    assert detected.bed_type == "bedtech" and "okimiki" in detected.ambiguous_types
    for selected, variant in (("richmat", "auto"), ("bedtech", "auto"), ("okimiki", "HCRN")):
        result = recommend_profile({"bed_type": selected, "protocol_variant": variant}, advert, {})
        if selected == "richmat":
            assert result is not None and result.suggested == "bedtech"
            assert "okimiki" not in result.choices
        else:
            assert result is None
    candidate = _make_service_info("prefix-HCRN-suffix", service_uuids=[])
    result = detect_bed_type_detailed(candidate)
    assert result.bed_type == "okimiki" or "okimiki" in (result.ambiguous_types or ())
    assert result.confidence < 0.7 and _confident_auto_detect(result) is None
    if result.bed_type == "okimiki":
        assert detect_bed_type(candidate) is None
    assert not hasattr(result, "protocol_variant")


@pytest.mark.parametrize("legacy", (False, True))
async def test_startup_exact_order_query_headers_and_gatt_properties(
    obj, coordinator, virtual, legacy
):
    route = codec.TRANSPORTS["n1" if legacy else "w1"]
    tx = SimpleNamespace(uuid=route.write_uuid, handle=1, properties=["write"])
    rx = SimpleNamespace(uuid="not-the-nominal-notify", handle=2, properties=["notify"])
    coordinator.client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])
    ]
    await obj.start_notify()
    assert coordinator.client.start_notify.await_args.args[0] is rx
    packets = writes(coordinator)
    assert packets[0] == codec.function(0, single=legacy)
    assert packets[-2:] == [
        codec.function(1, action="deviceFunctionItemCheckClock", single=legacy),
        codec.function(1, action="deviceFunctionItemCheckLight", single=legacy),
    ]
    assert len(packets) == 5
    assert packets[1][1:6] == bytes((12, 32, 8, 2, 1))
    assert all(
        call.kwargs["response"] for call in coordinator.client.write_gatt_char.await_args_list
    )
    assert all(packet != codec.record(6, 3, 0, (0,)) for packet in packets)


async def test_mixed_services_first_handles_but_last_service_selects_framing(
    obj, coordinator, virtual
):
    services = []
    for name in ("w1", "n1"):
        route = codec.TRANSPORTS[name]
        services.append(
            SimpleNamespace(
                uuid=route.service_uuid,
                characteristics=[
                    SimpleNamespace(
                        uuid=route.write_uuid,
                        handle=1,
                        properties=["write", "write-without-response"],
                    ),
                    SimpleNamespace(uuid="notify-" + name, handle=2, properties=["notify"]),
                ],
            )
        )
    coordinator.client.services = services
    await obj.start_notify()
    assert obj._link.tx is services[0].characteristics[0]
    assert obj._link.rx is services[0].characteristics[1]
    assert obj._link.legacy
    assert writes(coordinator)[0] == bytes((0,))
    coordinator.client.services[0].characteristics[0].properties = ["write-without-response"]
    await obj.start_notify()
    assert obj._link.tx is services[1].characteristics[0]


@pytest.mark.parametrize("code", PRODUCTS)
def test_capability_gates_and_alarm_ack_never_music(obj, coordinator, code):
    obj = bed.OkimikiController(coordinator, code)
    obj._link = Link(
        coordinator.client, SimpleNamespace(uuid="tx"), SimpleNamespace(uuid="rx"), False
    )
    obj._notification(obj._link, obj._link.rx, bytearray.fromhex("6e0e00037f"))
    assert obj.supports_lights and obj.controller_number_specs
    obj._notification(obj._link, obj._link.rx, bytearray.fromhex("6e09010078"))
    assert obj.menu_available("alarm") == (PRODUCTS[code].alarm != "none")
    for frame, event in (
        ("6e07010177", "alarm_add_success"),
        ("6e07010278", "alarm_cancel_success"),
    ):
        obj._notification(obj._link, obj._link.rx, bytearray.fromhex(frame))
        assert event in obj._observations
        assert not obj._requests
    assert not any("music" in key for key in obj._observations)
    old = obj._link
    obj.on_disconnect()
    obj._notification(old, old.rx, bytearray.fromhex("6e0e00037f"))
    assert not obj.supports_lights and not obj._observations


def test_parser_exact_common_consumption_and_extended_reassembly():
    events = []
    receiver = p.Receiver(lambda *event: events.append(event))
    receiver.feed(bytes.fromhex("6e0901"))
    receiver.feed(bytes.fromhex("0078"))
    assert not events
    receiver.feed(bytes.fromhex("6e090100786e0e00037f"))
    assert not events
    receiver.feed(bytes.fromhex("00aa6e07010177"))
    assert events == [("alarm_add_success", None)]
    packet = bytes.fromhex("6e200d0501020100071e5989ab")
    receiver.feed(packet[:5])
    assert len(receiver.buffer) == 5
    receiver.feed(packet[5:])
    assert events[-1] == ("alarm_list", p.Alarm(1, 0, 7, 30, 89, 137))
    receiver.feed(packet[:-1] + b"\x00")
    assert len(events) == 2
    receiver.feed(bytes.fromhex("6e2000"))
    assert receiver.rejection and not receiver.buffer


@pytest.mark.parametrize("control", CONTROLS)
async def test_actual_native_control_caller_bytes_release_and_save(
    obj, coordinator, virtual, control
):
    row = CONTROLS[control]
    await obj.press(control, 250 if row.held else 0)
    packets = writes(coordinator)
    assert packets[0] == codec.function(row.opcode)
    assert (
        packets[-1] == codec.command(codec.STOP)
        if row.held or control == "flat"
        else packets == [codec.command(row.opcode)]
    )
    if row.save is not None:
        coordinator.client.write_gatt_char.reset_mock()
        await obj.press(control, 4000)
        assert writes(coordinator) == [codec.command(row.save)]


async def test_iprm_only_two_axes_and_no_invented_memory(obj, coordinator, virtual):
    obj = bed.OkimikiController(coordinator, "IPRM")
    obj._link = Link(
        coordinator.client,
        SimpleNamespace(uuid="tx", handle=1, properties=["write"]),
        SimpleNamespace(uuid="rx"),
        False,
    )
    assert len(obj.control_actions) == 7
    with pytest.raises(ValueError):
        await obj.preset_memory(1)
    with pytest.raises(ValueError):
        await obj.program_memory(1)
    assert not writes(coordinator)


async def test_elapsed_deadline_includes_gatt_time_and_releases(obj, coordinator, virtual):
    stamps = []

    async def slow(_char, packet, **_kwargs):
        stamps.append((asyncio.get_running_loop().time(), packet))
        await asyncio.sleep(0.4)

    coordinator.client.write_gatt_char.side_effect = slow
    started = asyncio.get_running_loop().time()
    await obj.press("head_up", 250)
    assert [packet for _, packet in stamps] == [codec.command(0x24), codec.command(codec.STOP)]
    assert stamps[0][0] < started + 0.25


async def test_queued_refresh_that_misses_deadline_never_submits(obj, coordinator, virtual):
    obj._next_write_at = asyncio.get_running_loop().time() + 0.5
    await obj.press("head_up", 250)
    assert not writes(coordinator)


async def test_cancelled_inflight_frame_drains_then_same_link_stop(obj, coordinator):
    submitted, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def blocked(_char, packet, **_kwargs):
        calls.append(packet)
        if len(calls) == 1:
            submitted.set()
            await finish.wait()

    coordinator.client.write_gatt_char.side_effect = blocked
    task = asyncio.create_task(obj.press("head_up", 1000))
    await submitted.wait()
    coordinator.cancel_command.set()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == [codec.command(0x24), codec.command(codec.STOP)]


async def test_replacement_during_rgb_pair_never_writes_new_session(obj, coordinator, virtual):
    obj._menus.add("alarm")
    original = obj._link

    async def replace_session(*_args, **_kwargs):
        obj._link = replace(original)

    coordinator.client.write_gatt_char.side_effect = replace_session
    obj.model = PRODUCTS["IQRM"]
    with pytest.raises(ConnectionError):
        await obj.execute_request(
            Request("single", when=datetime.now(ZoneInfo("Europe/Oslo")) + timedelta(hours=1))
        )
    assert len(writes(coordinator)) == 1


async def test_alarm_records_modes_reserved_byte_enable_and_exhaustion(obj, hass):
    await hass.config.async_set_time_zone("Europe/Oslo")
    obj._menus.add("alarm")
    row = p.Alarm(1, 213, 7, 30, 89, 137)
    obj._event("alarm_list", row)
    plan = Request("repeat", alarm_id=1, days=(), enabled=False).plan(obj)
    assert plan.frames(obj) == (p.Alarm(1, 213, 7, 30, 89, 0).frame(),)
    assert Request("enable", alarm_id=1, enabled=False).plan(obj).frames(obj) == (
        replace(row, mask=136).frame(),
    )
    assert Request("delete", alarm_id=1).plan(obj).frames(obj) == (codec.record(5, 2, 1, (1,)),)
    changed = replace(row, reserved=7, minute=31)
    obj._event("alarm_update", changed)
    assert obj._alarms == [changed]
    obj._event("alarm_update", replace(row, id=2))
    assert obj._alarms == [changed]
    obj._alarms = [replace(row, id=n) for n in range(1, 8)]
    assert p.next_alarm_id(tuple(obj._alarms)) == -1
    when = datetime(2026, 11, 17, 7, 30, tzinfo=ZoneInfo("Europe/Oslo"))
    assert (
        p.Alarm(p.next_alarm_id(tuple(obj._alarms)), 0, 7, 30, 89, p.repeat_mask((0, 4), True)).frame().hex()
        == "6e0d20050101ff00071e5989a8"
    )
    for mode in ("lounge", "zero_gravity", "memory_1", "memory_2"):
        assert Request("repeat", alarm_id=1, mode=mode, when=when).frames(obj)[0][-3] == CONTROLS[mode].opcode


def test_countdown_subminute_rollover_zone_and_restore_no_hardware_assumption(obj):
    now = datetime(2026, 11, 17, 7, 30, 40, tzinfo=ZoneInfo("Europe/Oslo"))
    assert p.countdown_minutes(now, now + timedelta(seconds=10)) == 1440
    assert p.countdown_minutes(now, now + timedelta(seconds=61)) == 1
    assert p.color_byte(0.5) == 128
    assert p.light_seconds(0).hex() == "6e0bffff77"
    obj.restore_persisted_app_state({"rgb": [1, 2, 3], "seconds": 300, "scheduled": "untrusted"})
    assert dict(obj.persisted_app_state) == {"rgb": [1, 2, 3], "seconds": 300}
    obj.on_disconnect()
    assert not obj.supports_lights and not obj._alarms
    assert dict(obj.persisted_app_state)["seconds"] == 300
    with pytest.raises(ValueError):
        obj.restore_persisted_app_state({"seconds": -1})


@pytest.mark.parametrize("changed", ("same", "address", "profile"))
def test_light_identity_restore_is_scoped_without_session_permission(obj, coordinator, changed):
    legacy = bed.GoodVibeController(coordinator, profile="selector-0001")
    assert legacy.unavailable_controller_entity_keys == ()
    obj._event("light", True)
    saved = dict(obj.persisted_app_state)
    if changed == "address":
        coordinator.address = "AA:BB:CC:DD:EE:70"
    restored = bed.OkimikiController(coordinator, "IPRM" if changed == "profile" else "KWRN")
    restored.restore_persisted_app_state(saved)
    assert bool(restored.retained_entity_keys) is (changed == "same")
    assert not restored.supports_lights and not restored.menu_available("light")
    assert restored.unavailable_controller_entity_keys == (
        "under_bed_lights", "controller_number_okimiki_light_seconds"
    )
    assert coordinator.controller_state[bed.DURATION] is None


async def test_native_covers_and_programming_use_profile_timing(obj, coordinator, virtual):
    await obj.move_back_up()
    assert writes(coordinator)[0] == codec.command(0x24)
    assert writes(coordinator)[-1] == codec.command(codec.STOP)
    coordinator.client.write_gatt_char.reset_mock()
    await obj.program_memory(2)
    assert writes(coordinator) == [codec.command(0x2C)]


async def test_alarm_ack_cannot_revalidate_pre_mutation_fields(obj, coordinator, virtual):
    obj._menus.add("alarm")
    row = p.Alarm(1, 7, 6, 30, 69, 137)
    obj._event("alarm_list", row)
    await obj.execute_request(Request("repeat", alarm_id=1, mode="lounge").plan(obj))
    obj._event("alarm_add_success", None)
    with pytest.raises(ValueError, match="fresh record"):
        Request("enable", alarm_id=1, enabled=False).plan(obj)
    obj._event("alarm_update", replace(row, opcode=89))
    assert Request("enable", alarm_id=1, enabled=False).plan(obj).record.opcode == 89


@pytest.mark.parametrize("remaining", (False, True))
async def test_alarm_refresh_requires_explicit_slot_after_delete(obj, coordinator, virtual, remaining):
    obj._menus.add("alarm")
    obj._event("alarm_list", p.Alarm(1, 7, 6, 30, 69, 137))
    obj._event("alarm_list", p.Alarm(2, 8, 8, 0, 69, 1))
    await obj.execute_request(Request("delete", alarm_id=2).plan(obj))
    obj._event("alarm_cancel_success", None)
    new = Request("repeat", when=datetime(2026, 11, 17, 6, 30, tzinfo=UTC), mode="lounge")
    with pytest.raises(ValueError, match="explicit alarm ID"):
        new.plan(obj)
    await obj.execute_request(Request("alarms"))
    if remaining:
        obj._event("alarm_list", p.Alarm(1, 7, 6, 30, 69, 137))
    count = len(writes(coordinator))
    with pytest.raises(ValueError, match="explicit alarm ID"):
        await obj.execute_request(new.plan(obj))
    assert len(writes(coordinator)) == count
    with pytest.raises(ValueError, match="Query this bed's alarms"):
        Request("enable", alarm_id=2, enabled=False).plan(obj)
    await obj.execute_request(replace(new, alarm_id=2).plan(obj))
    assert writes(coordinator)[-1][6] == 2


async def test_failed_alarm_refresh_keeps_edits_guarded(obj, coordinator, virtual):
    from bleak.exc import BleakError

    obj._menus.add("alarm")
    obj._event("alarm_list", p.Alarm(1, 7, 6, 30, 69, 137))
    await obj.execute_request(Request("delete", alarm_id=1).plan(obj))
    coordinator.client.write_gatt_char.side_effect = BleakError("query failed")
    with pytest.raises(BleakError, match="query failed"):
        await obj.execute_request(Request("alarms"))
    with pytest.raises(ValueError, match="Query this bed's alarms"):
        Request("enable", alarm_id=1, enabled=False).plan(obj)


async def test_new_alarm_plan_rejects_a_slot_observed_after_preflight(obj, coordinator, virtual):
    obj._menus.add("alarm")
    plan = Request("repeat", alarm_id=2, when=datetime(2026, 11, 17, 6, 30, tzinfo=UTC), mode="lounge").plan(obj)
    obj._event("alarm_list", p.Alarm(2, 91, 8, 0, 69, 137))
    with pytest.raises(ValueError, match="fresh record"):
        await obj.execute_request(plan)
    assert not writes(coordinator)


@pytest.mark.parametrize("month,hour", ((11, 7), (7, 8)))
@pytest.mark.parametrize("edit", (False, True))
async def test_recurring_alarm_uses_clock_sync_timezone(obj, hass, month, hour, edit):
    await hass.config.async_set_time_zone("Europe/Oslo")
    obj._menus.add("alarm")
    if edit:
        obj._event("alarm_list", p.Alarm(1, 7, 5, 0, 69, 137))
    request = Request(
        "repeat",
        alarm_id=1,
        when=datetime(2026, month, 17, 6, 30, tzinfo=UTC),
        mode="lounge",
    ).plan(obj)
    expected = p.Alarm(1, 7 if edit else 0, hour, 30, 89, 137 if edit else 1)
    assert request.frames(obj) == (expected.frame(),)


async def test_failed_fifo_head_drops_without_retry_then_drains_next_item(
    obj, coordinator, virtual
):
    from bleak.exc import BleakError

    obj.model = PRODUCTS["IQRM"]
    obj._menus.add("alarm")
    coordinator.client.write_gatt_char.side_effect = [BleakError("dropped head"), None]
    with pytest.raises(BleakError, match="dropped head"):
        await obj.execute_request(Request("cancel_single"))
    assert writes(coordinator) == list(p.countdown(0, 0))


def test_source_numeric_conversion_and_clock_first_digits():
    assert [p.color_byte(value) for value in (0, 0.5, 1, -0.5)] == [0, 128, 255, 128]
    now = datetime.fromtimestamp(0x123456789, UTC)
    assert p.sync_time(now, now)[0] == codec.record(8, 2, 1, (0x12, 0x34, 0x56, 0x78, 0))


@pytest.mark.parametrize("code", PRODUCTS)
def test_save_labels_and_no_raw_status_entity(coordinator, code):
    obj = bed.OkimikiController(coordinator, code)
    labels = {
        spec.key: spec.translation_placeholders["action"]
        for spec in obj.controller_button_specs
        if spec.translation_placeholders
    }
    saves = {
        "okimiki_save_lounge": "Save lounge position",
        "okimiki_save_zero_gravity": "Save zero-gravity position",
    }
    assert labels == ({} if code == "IPRM" else saves)
    # Decoded events and alarm records stay in diagnostics.
    assert obj.controller_state_sensor_specs == ()


def test_shared_alarm_maps_to_the_product_alarm_page(coordinator):
    from custom_components.adjustable_bed.alarm import AlarmRequest

    now = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)
    single = bed.OkimikiController(coordinator, "IQRM")
    assert single.alarm_capability.wake_actions == ("lounge",)
    on = single._alarm_request(AlarmRequest(enabled=True, hour=7, minute=0, reference_time=now))
    assert (on.operation, on.when) == ("single", now.replace(hour=7))
    assert single._alarm_request(AlarmRequest(enabled=False, reference_time=now)).operation == "cancel_single"
    repeat = bed.OkimikiController(coordinator, "KWRN")
    assert repeat.alarm_capability.slots == 7
    alarm = AlarmRequest(enabled=True, hour=7, minute=0, weekdays=(0, 6), slot=3,
                         wake_action="zero_g", reference_time=now)
    request = repeat._alarm_request(alarm)
    assert (request.operation, request.alarm_id, request.mode, request.days) == ("repeat", 3, "zero_gravity", (0, 6))
    off = repeat._alarm_request(AlarmRequest(enabled=False, slot=3, reference_time=now))
    assert (off.operation, off.alarm_id, off.enabled) == ("enable", 3, False)
    assert bed.OkimikiController(coordinator, "HCRN").alarm_capability is None
