"""Catalog selection, gestures, state gates and independent sleep sessions (row173)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import CONTROLLER_GESTURE_RELEASE
from custom_components.adjustable_bed.beds.richmat_app import controller as bed
from custom_components.adjustable_bed.beds.richmat_app.catalog import (
    ACTIONS,
    FOUR_COLORS,
    PRODUCTS,
    PROFILE_CHOICES,
    RESTORED_CHOICES,
    descriptors,
    normalize_product,
    scan_matches,
)
from custom_components.adjustable_bed.beds.richmat_app.protocol import BlanketSleep
from custom_components.adjustable_bed.beds.richmat_app.receive import Receiver
from custom_components.adjustable_bed.beds.richmat_app.requests import DemoStep, Request
from custom_components.adjustable_bed.beds.richmat_app.sleep import SleepController, parse_response
from tests.state_helpers import state_writer


@pytest.fixture
def coordinator():
    c = MagicMock()
    c.address = "AA:BB:CC:DD:EE:73"
    c.capability_controller = None
    c.cancel_command = asyncio.Event()
    c.client.is_connected = True
    c.client.write_gatt_char = AsyncMock()
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.mtu_size = 23
    c.controller_state = {}
    c.handle_controller_state_updates.side_effect = state_writer(c.controller_state)
    return c


def controller(coordinator, product="7IRM", single=False):
    c = bed.RichmatAppController(coordinator, product=product)
    c._link = bed.Link(
        coordinator.client,
        SimpleNamespace(uuid="tx", properties=["write", "write-without-response"], handle=73),
        SimpleNamespace(uuid="rx", properties=["notify"], handle=74),
        single,
    )
    return c


@pytest.fixture
def clocked(monkeypatch):
    now = [0.0]

    async def wait(self, seconds, cancel):
        now[0] += seconds
        return not cancel.is_set()

    async def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.RichmatAppController, "_wait", wait)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    return now


def written(c):
    return [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list]


def test_full_catalog_identity_selection_and_actual_routes():
    assert len(PRODUCTS) == 1118 and len(PROFILE_CHOICES) == 756 and len(RESTORED_CHOICES) == 362
    assert not set(PROFILE_CHOICES) & set(RESTORED_CHOICES)
    assert normalize_product(" 7i\nrm ") == "7IRM"
    assert normalize_product("\t7irm") == "\t7IRM"
    assert scan_matches("vendor-7IRM-extra") and not scan_matches("vendor-7irm-extra")
    assert scan_matches("Luffabenz") and not scan_matches(None)
    assert sum(len(p["versions"]["other"]["motors"]) for p in PRODUCTS.values()) == 3179
    assert sum(len(p["versions"]["one"]["motors"]) for p in PRODUCTS.values()) == 20
    assert (
        sum(sum(bool(m[3]) for m in p["versions"]["one"]["motors"]) for p in PRODUCTS.values())
        == 14
    )
    for p in PRODUCTS.values():
        assert len(p["selectors"]) == 20
        for version in p["versions"].values():
            assert all(str(d) in ACTIONS for m in version["motors"] for d in m[1:3])
            assert all(str(d[0]) in ACTIONS for d in version["presets"])


async def test_held_tick_cancel_and_release_uses_captured_side(coordinator, clocked):
    c = controller(coordinator)
    with c.side_scope("right"):
        await c.hold_control("richmat_app_cb18d1", 200)
    assert written(c) == ["6e01012494", "6e01012494", "6e01016ede"]
    coordinator.client.write_gatt_char.reset_mock()
    await c.hold_control("richmat_app_cb18d1", 50)
    assert written(c) == []
    token = CONTROLLER_GESTURE_RELEASE.set(True)
    try:
        await c.stop_all()
    finally:
        CONTROLLER_GESTURE_RELEASE.reset(token)
    assert written(c) == []
    await c.stop_all()
    assert written(c) == ["6e01006edd"]


async def test_release_even_when_write_fails_and_no_retry(coordinator, clocked):
    c = controller(coordinator)
    coordinator.client.write_gatt_char.side_effect = [OSError("failed movement"), None]
    with pytest.raises(OSError):
        await c.hold_control("richmat_app_cb18d1", 100)
    assert len(written(c)) == 2 and written(c)[-1] == "6e01006edd"


async def test_save_tap_uses_long_opcode_without_stop(coordinator, clocked):
    c = controller(coordinator)
    await c.press("caf951", save=True)
    assert written(c) == ["6e01002b9a"]
    assert c._detail_label("caf7d1", "0x1230d") != c._detail_label("cafa51", "0x1230d")
    assert any(ACTIONS[d]["enum"] == "deviceFunctionItemMotorReset" for d in c.auxiliary_actions)
    assert any(ACTIONS[d]["enum"] == "deviceFunctionItemBedLight" for d in c.auxiliary_actions)


async def test_version_drives_exact_entities_and_does_not_alias_extended_position(
    coordinator, clocked
):
    c = controller(coordinator)
    assert c.controller_number_specs == ()
    c.version = 1
    assert len(c.controller_number_specs) == 5  # three angles, two massage intensities
    angle = next(s for s in c.controller_number_specs if s.key == "richmat_app_motor_0")
    await angle.set_fn(c, 30)
    assert written(c) == ["6e88301e44"]
    c._accept("common", {"no": 0, "status": 1, "angle": 42})
    c._accept("group_1_3", {"position": 0, "angle": 10})
    assert c._motor_values[0] == 42
    c.version = 0
    with pytest.raises(ValueError):
        await angle.set_fn(c, 30)


async def test_massage_sends_both_intensities_at_commit(coordinator, clocked):
    c = controller(coordinator)
    c.version = 1
    c._massage_values = [1, 3]
    spec = next(s for s in c.controller_number_specs if s.key == "richmat_app_massage_0")
    await spec.set_fn(c, 2)
    assert written(c) == ["6e88a01ab0"]
    with pytest.raises(ValueError):
        await spec.set_fn(c, 8)


async def test_product_and_capability_gates_before_settings(coordinator, clocked):
    c = controller(coordinator, "6BRM")
    with pytest.raises(ValueError):
        await c.execute_request(Request("blanket_power"))
    with pytest.raises(ValueError):
        await c.execute_request(Request("strip_power"))
    assert written(c) == []
    c = controller(coordinator, "LURN")
    c._accept("light_available", {})
    c.validate_request(Request("therapy_sound", mode=2))
    with pytest.raises(ValueError):
        c.validate_request(Request("therapy_timer", value=30))
    with pytest.raises(ValueError):
        c.validate_request(Request("light_rgb", rgb=(1, 2, 3)))
    c._accept("group_4_1", {"rgb": [1, 2, 3]})
    assert c.local["groove_palette_index"] == -1
    c._accept("group_4_1", {"rgb": list(FOUR_COLORS[2])})
    assert c.local["groove_palette_index"] == 4


async def test_blanket_mite_clamp_partial_merge_and_sleep_order(coordinator, clocked):
    product = next(k for k, p in PRODUCTS.items() if p["selectors"]["0xea47"])
    c = controller(coordinator, product)
    c._accept("group_13_1", {"7": True})
    await c.execute_request(Request("blanket_mite", enabled=True))
    assert c.blanket["f"] == c.blanket["17"] == 55 and written(c) == ["6e20090d06010001ac"]
    with pytest.raises(ValueError):
        await c.execute_request(Request("blanket_temperature", temperature=30))
    await c.execute_request(Request("blanket_mite", enabled=False))
    c._accept(
        "group_13_8", {"3f": True, "43": False, "47": True, "4b": False, "4f": False, "3b": True}
    )
    c._accept("group_13_9", {"f": 1, "17": 2, "4f": True, "3b": False, "5b": 3, "63": 1, "6b": 0})
    assert c.blanket["f"] == 25 and c.blanket["3b"] is True and c.blanket["4f"] is True
    await c.execute_request(
        Request("blanket_sleep", zone=1, sleep=BlanketSleep(mode=1, temperatures=(20, 21, 23, 22)))
    )
    assert written(c)[-2].startswith("6e20160d070101")
    assert written(c)[-1] == "6e200b0d050100011919df"


def test_alarm_append_escalation_and_ack_persistence(coordinator):
    c = controller(coordinator)
    row = {"7": 1, "f": 0, "17": 7, "1f": 30, "27": 69, "2f": 129}
    c._accept("group_5_1", {"fields": row, "direction": 2})
    c._accept("group_5_1", {"fields": {**row, "1f": 31}, "direction": 2})
    assert len(c.alarms) == 2
    c._accept("group_5_1", {"fields": {**row, "1f": 32}, "direction": 3})
    assert c.alarms[0]["1f"] == 32
    c._pending_alarm = {"action": "caf951", "hour": 7, "minute": 30}
    c._accept("alarm_saved", {})
    saved = c.persisted_app_state["saved_alarm"]
    assert isinstance(saved, dict) and saved["hour"] == 7
    c._accept("alarm_cancelled", {})
    assert "saved_alarm" not in c.persisted_app_state


def test_receive_buffer_partial_length_and_nonprogress():
    events = []
    rx = Receiver(lambda *v: events.append(v))
    rx.feed(bytes.fromhex("006e2009040402"))
    assert not events
    rx.feed(bytes.fromhex("0001a2"))
    assert events == [("group_4_4", {"power": True})]
    with pytest.raises(ValueError):
        rx.feed(bytes.fromhex("6e2000"))
    assert rx.pending == b""
    with pytest.raises(ValueError):
        rx.feed(
            bytes.fromhex("6e2100008f")
        )  # shadowed by length branch, never a snore acknowledgement
    assert len(events) == 1


async def test_demo_sustain_zero_still_ticks_and_stops(coordinator, clocked):
    c = controller(coordinator)
    await c.execute_request(
        Request("demo", steps=(DemoStep("deviceFunctionItemHeadUp", True, 0, 0),))
    )
    assert written(c) == ["6e01002493", "6e01006edd", "6e01006edd"]


async def test_stale_notification_and_link_never_mutate_or_write(coordinator, clocked):
    c = controller(coordinator)
    old = c._link
    c.on_disconnect()
    c._notification(old, None, bytearray.fromhex("6e90000100"))
    assert c.version == 0
    with pytest.raises(ConnectionError):
        await c.press("caf951")
    assert written(c) == []


def test_sleep_required_nullable_fields_and_metadata():
    assert parse_response({}, "s_time", "hj") == {"id": None, "cmd": None, "val": None}
    for variant in ("mm", "old_mm", "old_hj"):
        with pytest.raises(ValueError):
            parse_response({}, "s_time", variant)
    with pytest.raises(ValueError):
        parse_response({"id": 1, "cmd": "q_time", "val": {"utc": 5}}, "q_time", "hj")
    assert parse_response({"id": 2, "cmd": "s_part", "val": 12}, "s_part", "mm")["val"] == 12


async def test_sleep_fragments_response_mode_sequence_and_local_stop(coordinator, monkeypatch):
    c = SleepController(coordinator, variant="mm")
    c._owner = coordinator.client
    c._tx = SimpleNamespace(uuid="tx")
    c.sequence = 254
    await c.send("s_part", 12)
    assert c.sequence == 1
    assert all(
        len(call.args[1]) <= 20 and call.kwargs["response"] is False
        for call in coordinator.client.write_gatt_char.await_args_list
    )
    before = coordinator.client.write_gatt_char.await_count
    await c.stop_all()
    assert c.receiver.current is None and coordinator.client.write_gatt_char.await_count == before
    c.on_disconnect()
    with pytest.raises(ConnectionError):
        await c.send("q_part", None)


def test_sleep_fsize_followup_and_public_snore_do_not_change_bed_product(coordinator, monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_app.sleep import packet

    c = SleepController(coordinator, variant="hj")
    c._owner = coordinator.client
    followups = []
    monkeypatch.setattr(c, "_task", lambda *a: followups.append(a))
    c._report_context = {"part": 12, "type": 1, "y": 2026, "m": 11, "d": 10}
    c.receiver.current = "q_report"
    wire = packet(1, "q_report", {"fsize": 42})
    c._notification(coordinator.client, None, bytearray(wire))
    assert followups == [("q_report_allow", {"allow": 1})] and c.receiver.report_size == 42
    c.receiver.current = "s_time"
    wire = packet(1, "s_time", {"error": 0, "ver": "0.0.3.0", "type": "HJ"})
    c._notification(coordinator.client, None, bytearray(wire))
    assert c.state["version"] == "0.0.3.0" and c.state["type"] == "HJ"


@pytest.mark.parametrize(
    "variant,version,expected",
    [
        ("hj", "0.0.3.0", "hj_new_day"),
        ("old_hj", "1.9.9", "hj_old_day"),
        ("hj", "0.0.2", "hj_old_day"),
        ("mm", "not-a-HJ-version", "mm_day"),
    ],
)
def test_report_transfer_retains_format_boundary_without_health_interpretation(
    variant, version, expected
):
    import gzip
    import json

    from custom_components.adjustable_bed.beds.richmat_app.sleep import Receiver

    packed = gzip.compress(json.dumps({"algorithmVersion": version, "date": "2026-11-10"}).encode())
    rx = Receiver(variant, current="q_report_allow", report_size=len(packed))
    prefix = b"\0" * 14 if variant.endswith("hj") else b""
    assert rx.feed(prefix + packed[:8]) is None
    result = rx.feed(prefix + packed[8:])
    assert result[0] == "report_transfer" and result[1]["format"] == expected
    assert result[1]["interpretation"] == "excluded"


def test_old_hj_time_followups_and_mm_init_has_no_successful_builder(coordinator, monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_app.sleep import packet

    c = SleepController(coordinator, variant="old_hj")
    c._owner = coordinator.client
    followups = []
    monkeypatch.setattr(c, "_task", lambda *a: followups.append(a))
    c.receiver.current = "s_time"
    c._notification(
        coordinator.client,
        None,
        bytearray(packet(1, "s_time", {"error": 0, "ver": "0.0.3.0", "type": "HJ"})),
    )
    assert followups == [("q_time", None)]
    c.receiver.current = "q_time"
    c._notification(coordinator.client, None, bytearray(packet(2, "q_time", {"ts": 1, "utc": "1"})))
    assert followups[-1] == ("q_part", None)
    mm = SleepController(coordinator, variant="mm")
    with pytest.raises(ValueError):
        mm.validate_request(Request("sleep_init"))


def test_main_transport_keeps_first_handles_and_last_selected_format(coordinator):
    from custom_components.adjustable_bed.codec.richmat import TRANSPORTS

    first = TRANSPORTS["w1"]
    last = TRANSPORTS["n1"]
    tx = SimpleNamespace(uuid=first.write_uuid, properties=["write"], handle=1)
    rx = SimpleNamespace(uuid="notify", properties=["notify"], handle=2)
    coordinator.client.services = [
        SimpleNamespace(uuid=first.service_uuid, characteristics=[tx, rx]),
        SimpleNamespace(uuid=last.service_uuid, characteristics=[]),
    ]
    link = bed.select_link(coordinator.client)
    assert link.tx is tx and link.rx is rx and link.single is True


async def test_main_startup_subscribes_before_exit_and_product_queries(coordinator, clocked):
    from custom_components.adjustable_bed.codec.richmat import TRANSPORTS

    route = TRANSPORTS["w1"]
    tx = SimpleNamespace(uuid=route.write_uuid, properties=["write"], handle=1)
    rx = SimpleNamespace(uuid=route.notify_uuid, properties=["notify"], handle=2)
    coordinator.client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])
    ]
    c = controller(coordinator, "6BRM")
    await c.start_notify()
    assert coordinator.client.start_notify.await_count == 1
    assert written(c) == [
        "6e02010071",
        "6e08010178",
        "6e0a000179",
        "6e1a000088",
        "5e1a000179",
        "6e01000170",
        "6e2100008f",
        "6e22000090",
        "6e9ac000c8",
        "6e9a000008",
    ]
    assert all(
        call.kwargs["response"] is True
        for call in coordinator.client.write_gatt_char.await_args_list
    )
    c.on_disconnect()


async def test_old_mm_filter_accepts_main_service_while_new_requires_sleep_service(
    coordinator, clocked
):
    from custom_components.adjustable_bed.codec.richmat import TRANSPORTS

    route = TRANSPORTS["w1"]
    tx = SimpleNamespace(uuid=route.write_uuid, properties=["write-without-response"], handle=1)
    rx = SimpleNamespace(uuid=route.notify_uuid, properties=["notify"], handle=2)
    coordinator.client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])
    ]
    coordinator.hass.config.time_zone = "Europe/Oslo"
    current = SleepController(coordinator, variant="mm")
    with pytest.raises(ValueError):
        await current.start_notify()
    old = SleepController(coordinator, variant="old_mm")
    await old.start_notify()
    assert old._tx is tx and coordinator.client.start_notify.await_count == 1
    old.on_disconnect()


async def test_restored_demo_validates_then_runs_and_resets_progress(coordinator, clocked):
    c = controller(coordinator)
    c.restore_persisted_app_state(
        {
            "demo": [
                {"action": "deviceFunctionItemHeadUp", "sustain": True, "seconds": 0, "delay": 0}
            ]
        }
    )
    await c.execute_request(Request("demo"))
    assert written(c) == ["6e01002493", "6e01006edd", "6e01006edd"]
    assert c.local["demo_running"] is False and c.local["demo_step"] == -1
    c.restore_persisted_app_state(
        {
            "demo": [
                {
                    "action": "deviceFunctionItemHeadUp",
                    "sustain": True,
                    "seconds": 10000,
                    "delay": 0,
                }
            ]
        }
    )
    with pytest.raises(ValueError):
        c.validate_request(Request("demo"))


async def test_usb_preserves_optimistic_mode_throttle_and_delayed_toggle(
    coordinator, clocked, monkeypatch
):
    from custom_components.adjustable_bed.beds.richmat_app import actions

    product = next(k for k, p in PRODUCTS.items() if "caf651" in descriptors(p, "0xeea5"))
    c = controller(coordinator, product)
    monkeypatch.setattr(actions, "monotonic", lambda: clocked[0])
    await c.press("caf651")
    assert c.local["ble"] is True and c.local["usb"] is True
    assert len(written(c)) == 2
    await c.execute_request(Request("usb", enabled=False))
    assert len(written(c)) == 2
    clocked[0] = 3
    await c.execute_request(Request("usb"))
    assert len(written(c)) == 3 and c.local["usb"] is False


async def test_sleep_settings_preempt_realtime_without_bed_stop(coordinator, monkeypatch):
    c = SleepController(coordinator, variant="hj")
    timer = MagicMock()
    c._poll = timer
    c.receiver.current = "q_realtime"
    send = AsyncMock()
    monkeypatch.setattr(c, "send", send)
    await c.execute_request(Request("sleep_part", value=12))
    timer.cancel.assert_called_once()
    assert c._poll is None and c.receiver.current is None
    send.assert_awaited_once_with("s_part", 12)


async def test_unchanged_blanket_mode_preserves_current_temperatures(coordinator, clocked):
    product = next(k for k, p in PRODUCTS.items() if p["selectors"]["0xea47"])
    c = controller(coordinator, product)
    c.blanket.update({"7": True, "b": "warm", "f": 40, "17": 41})
    await c.execute_request(Request("blanket_mode", mode=2))
    assert c.blanket["f"] == 40 and c.blanket["17"] == 41 and written(c) == []


@pytest.mark.parametrize("operation", ["hold", "demo"])
async def test_selector_change_during_movement_keeps_stop_on_owning_side(
    coordinator, clocked, operation
):
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c = controller(coordinator)
    coordinator.capability_controller = c
    coordinator.entity_side = None
    selector = AdjustableBedControllerSelect(coordinator, c.controller_select_specs[0])
    await selector.async_select_option("left")

    async def switch_side(*args, **kwargs):
        await selector.async_select_option("right")

    coordinator.client.write_gatt_char.side_effect = switch_side
    if operation == "hold":
        await c.press("cb18d1", duration_ms=200)
        assert written(c) == ["6e01002493", "6e01002493", "6e01006edd"]
    else:
        await c.execute_request(
            Request("demo", steps=(DemoStep("deviceFunctionItemHeadUp", True, 0, 0),))
        )
        assert written(c) == ["6e01002493", "6e01006edd", "6e01006edd"]
    assert c._side() == 1
    coordinator.async_execute_controller_command.assert_not_called()


@pytest.mark.parametrize("domain", ["number", "button"])
async def test_notification_refreshes_actual_platform_controls_and_retires_old_rows(
    hass, coordinator, domain
):
    from unittest.mock import patch

    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed import button, number
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.entity_sweep import async_sweep_after_setup
    from tests.state_helpers import published
    from tests.test_controller_custom_entities import runtime_for

    c = controller(coordinator)
    # This test follows discovery, not the separately tested V1 query task.
    c._version_task = MagicMock()
    c._version_task.done.return_value = False
    runtime = runtime_for(hass, c)
    runtime.client = coordinator.client
    callbacks = []
    runtime.register_controller_state_callback.side_effect = lambda callback: (
        callbacks.append(callback) or (lambda: None)
    )

    def publish(*updates):
        state = published(*updates)
        runtime.controller_state.update(state)
        for callback in tuple(callbacks):
            callback(state)

    coordinator.handle_controller_state_updates.side_effect = publish
    hass.data[DOMAIN] = {runtime.entry.entry_id: runtime}
    registry = er.async_get(hass)
    added = []

    def add(entities):
        for entity in entities:
            row = registry.async_get_or_create(
                domain, DOMAIN, entity.unique_id, config_entry=runtime.entry
            )
            entity.entity_id = row.entity_id
            added.append(entity.unique_id)

    module = number if domain == "number" else button
    with patch.object(module, "entity_runtimes", return_value=[runtime]):
        await module.async_setup_entry(hass, runtime.entry, add)
    async_sweep_after_setup(hass, runtime.entry, (domain,))
    initial = {
        row.unique_id for row in er.async_entries_for_config_entry(registry, runtime.entry.entry_id)
    }
    assert callbacks
    c._notification(c._current_link(), None, bytearray.fromhex("6e900001ff"))
    await hass.async_block_till_done()
    v1 = {
        row.unique_id for row in er.async_entries_for_config_entry(registry, runtime.entry.entry_id)
    }
    if domain == "number":
        assert len(v1 - initial) == 5
    else:
        assert v1 - initial
    new = v1 - initial
    c._notification(c._current_link(), None, bytearray.fromhex("6e900000fe"))
    await hass.async_block_till_done()
    final = {
        row.unique_id for row in er.async_entries_for_config_entry(registry, runtime.entry.entry_id)
    }
    assert not new & final
    assert final == initial
    c._notification(c._current_link(), None, bytearray.fromhex("6e900001ff"))
    await hass.async_block_till_done()
    assert all(added.count(identity) == 2 for identity in new)
