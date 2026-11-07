"""Accepted app vectors, profile gates, release cleanup and live receiver state."""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.richmat_mh import resolve_model
from custom_components.adjustable_bed.beds.richmat_mh_protocol import GATT_MAPS, Event, finalize
from custom_components.adjustable_bed.beds.row061 import (
    AppClassifier,
    Row061Controller,
    load_app_model,
    waist_init,
)
from custom_components.adjustable_bed.beds.row061_sleep import Row061SleepController
from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
from custom_components.adjustable_bed.row061_models import MODEL_IDS
from custom_components.adjustable_bed.row061_profiles import APPS, profiles
from custom_components.adjustable_bed.row061_protocol import (
    AlarmRequest,
    alarm_frame,
    calendar_clock,
    sleep_frame,
)
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type


def coordinator():
    c = MagicMock()
    c.entry = SimpleNamespace(data={})
    c.cancel_command = asyncio.Event()
    c.motor_pulse_count = 2
    c.controller_state = {}
    c.handle_controller_state_update.side_effect = lambda k, v: c.controller_state.update({k: v})
    c.handle_controller_state_updates.side_effect = c.controller_state.update
    c.client = MagicMock(is_connected=True)
    c.client.write_gatt_char = AsyncMock()
    return c


def make(app="bailey2", model="2i", version="0000"):
    c = Row061Controller(coordinator(), app=app, protocol_variant=f"model_{model}")
    c._version, c._call_page = version, version != "0000"
    c._write_char = SimpleNamespace(uuid=GATT_MAPS[0][1], properties=["write"], handle=1)
    return c


def frames(c):
    return [bytes(x.args[1]).hex() for x in c.client.write_gatt_char.call_args_list]


@pytest.fixture
def delays(monkeypatch):
    values = []
    real = asyncio.sleep

    async def sleep(delay, result=None):
        values.append(delay)
        await real(0)
        return result

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return values


def test_all_selected_apps_are_findable_and_models_resolve():
    for bed, app in APPS.items():
        assert bed in SUPPORTED_BED_TYPES and bed in BED_TYPE_DISPLAY_NAMES
        for model in MODEL_IDS[app]:
            assert resolve_model(app, f"model_{model}", None) == (model, None)
            assert load_app_model(app, model) is not None
        assert resolve_model(app, "model_unrecognized", None)[1] == "unknown_model"
    assert resolve_model("ruf", "auto", None) == ("bqrm", None)
    for app in ("wsilver2", "americanstar", "bailey2", "tx"):
        assert resolve_model(app, "auto", "Cool Touch 123")[1] == "choose_model"
    assert resolve_model("tx", "auto", "QRRM123")[1] == "choose_model"
    assert is_valid_variant_for_bed_type("richmat_sleep_receiver", "wsilver2")
    assert not is_valid_variant_for_bed_type("richmat_sleep_receiver", "auto")


def test_catalog_bindings_match_all_committed_app_vectors():
    rows = json.loads(
        gzip.decompress(
            (Path(__file__).parent / "fixtures/row061_control_vectors.json.gz").read_bytes()
        )
    )
    for app, model, route, code, wire in rows:
        assert any(c[0] == route and c[5] == code for c in profiles(app)[model]["controls"]), (
            app,
            model,
            route,
            code,
        )
        assert bytes.fromhex(wire) == finalize([0x6E, 1, 0, code, 0])


@pytest.mark.parametrize("app", MODEL_IDS)
def test_every_model_exposes_unique_real_entities(app):
    for model in MODEL_IDS[app]:
        for version in ("0000", "0001", "0002"):
            c = make(app, model, version)
            c._dev = dict.fromkeys(("alarm", "led", "aroma", "speech", "snore"), True)
            for specs in (
                c.motor_control_specs,
                c.controller_button_specs,
                c.controller_select_specs,
                c.controller_number_specs,
                c.controller_state_sensor_specs,
            ):
                keys = [s.key for s in specs]
                assert len(keys) == len(set(keys)), (app, model, version, keys)


@pytest.mark.parametrize("app", MODEL_IDS)
def test_every_motor_cover_has_a_translated_name(app):
    """An untranslated cover key names the cover after its device alone (#711)."""
    strings = Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json"
    covers = json.loads(strings.read_text())["entity"]["cover"]
    for model in MODEL_IDS[app]:
        for version in ("0000", "0001", "0002"):
            for spec in make(app, model, version).motor_control_specs:
                assert spec.translation_key in covers, (app, model, version, spec.key)


@pytest.mark.parametrize(
    "app,model,interval,release",
    [
        ("ruf", "bqrm", 0.15, 0),
        ("bailey2", "2i", 0.08, 0.12),
        ("tx", "3i", 0.1, 0.12),
        ("americanstar", "2i", 0.1, 0.12),
        ("wsilver2", "6brm", 0.1, 0.12),
    ],
)
async def test_movement_uses_each_apps_interval_and_fresh_release(
    app, model, interval, release, delays
):
    c = make(app, model)
    axis = c._axes()[0]
    await c.move_axis(axis.key, "up")
    assert frames(c) == ["6e01002493", "6e01002493", "6e01006edd"]
    assert any(abs(d - interval) < 0.005 for d in delays)
    if release:
        assert release in delays
    c._coordinator.cancel_command.set()
    c.client.write_gatt_char.reset_mock()
    await c.move_axis(axis.key, "up")
    assert frames(c) == ["6e01006edd"]


async def test_task_cancellation_still_sends_stop():
    c = make("ruf", "bqrm")
    began = asyncio.Event()

    async def write(command, **kwargs):
        if command[3] != 0x6E:
            began.set()
            await asyncio.Event().wait()
        else:
            assert kwargs["cancel_event"].is_set() is False

    c.write_command = AsyncMock(side_effect=write)
    task = asyncio.create_task(c.move_axis("head", "up"))
    await began.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert c.write_command.call_args.args[0].hex() == "6e01006edd"


async def test_bailey_once_uses_100ms_and_exact_memory_save(delays):
    c = make("bailey2", "3i")
    await c.tap(0x2E)
    assert frames(c) == ["6e01002e9d", "6e01006edd"]
    assert 0.1 in delays and 0.12 not in delays


@pytest.mark.parametrize(
    "app,model,version,first_delay,query_count",
    [
        ("ruf", "bqrm", "0000", 0.1, 11),
        ("wsilver2", "6brm", "0000", 0.3, 3),
        ("bailey2", "2i", "0002", 0.1, 9),
        ("tx", "3i", "0001", 0.3, 16),
        ("americanstar", "2i", "0001", 0.1, 17),
    ],
)
async def test_initialization_is_app_and_version_specific(
    app, model, version, first_delay, query_count, delays
):
    c = make(app, model)
    original = c._write_query

    async def query(raw):
        await original(raw)
        if raw.hex() == "6e9a000008":
            c._apply(Event("version", version))

    c._write_query = query
    await c._run_session_setup()
    assert len(frames(c)) == query_count
    assert delays[0] == first_delay
    assert c.version == version


@pytest.mark.parametrize("app", ["wsilver2", "americanstar", "tx"])
def test_normal_mattress_requires_opt_in_fresh_powered_response_and_legacy_version(app):
    for selected, version, expected in [
        (False, "0000", False),
        (True, "0001", False),
        (True, "0000", True),
    ]:
        c = make(app, "bfrm" + ("_mattress" if selected else ""), version)
        raw = bytearray([0x5E, 0x1A] + [0, 1] + [0] * 23 + [0])
        raw[19] = 1
        c._apply(Event("mattress_init", finalize(raw).hex()))
        assert c._normal_ready == expected
        if expected:
            assert len(c.motor_control_specs) >= 2
        c.on_disconnect()
        assert not c._normal_ready


def test_bailey_waist_zero_is_feedback_only_and_warmth_routes_by_keys():
    c = make()
    c._waist = True
    specs = {s.key: s for s in c.controller_select_specs}
    assert "off" not in specs["richmat_mh_waist_left_pressure"].options
    assert "off" not in specs["richmat_mh_waist_left_duration"].options
    raw = bytearray(31)
    raw[:6] = bytes([0x5E, 0x1B, 0, 1, 1, 2])
    raw[6:12] = bytes([4, 3, 2, 1, 4, 2])
    values = waist_init(finalize(raw).hex())
    assert values["left_heat"] == 1 and values["both_heat"] == 2
    assert "right_heat" not in values


async def test_extended_angle_and_mode_frames_are_not_legacy(delays):
    c = make("bailey2", "2i", "0002")
    await c.set_angle(1, 20)
    await c.set_motor_mode("mode2")
    assert frames(c) == ["6e200a010301010014b2", "6e20090b02010001a6"]
    with pytest.raises(ValueError):
        await c.set_angle(1, 181)


@pytest.mark.parametrize("app", ["wsilver2", "americanstar", "bailey2", "tx"])
@pytest.mark.parametrize("model", ["7irm", "kwrm"])
async def test_legacy_motor_modes_expose_selection_writes_and_reported_state(app, model):
    c = make(app, model, "0001")
    spec = next(s for s in c.controller_select_specs if s.key == "richmat_mh_motor_mode")
    assert spec.options == ("mode1", "mode2", "mode3")
    c._apply(Event("motor_mode", "11"))
    assert c._coordinator.controller_state[spec.state_key] == "mode3"
    await spec.select_fn(c, "mode2")
    assert frames(c) == ["6e8818000e"]
    assert c._coordinator.controller_state[spec.state_key] == "mode2"
    c._call_page = False
    assert c.motor_mode_options == ()


@pytest.mark.parametrize("app", ["ruf", "bailey2", "americanstar"])
@pytest.mark.parametrize("alarm", ["6e09010078", "6e09010179"])
def test_version_two_alarm_reply_does_not_hide_extended_replies(app, alarm):
    """The 0002 init leaves the receive type NONE; its alarm reply must still be consumed."""
    c = AppClassifier(app)
    assert c.feed(bytes.fromhex("6e900002ff")) == [Event("version", "0002")]
    assert c.feed(bytes.fromhex(alarm)) == [Event("init", alarm)]
    assert c.buffer == ""
    extended = "6e20080b020000a3"
    assert c.feed(bytes.fromhex(extended)) == [Event("extended", extended)]


def test_classifier_fragmented_extended_and_version_two():
    p = AppClassifier("bailey2")
    assert p.feed(bytes.fromhex("6e900002ff")) == [Event("version", "0002")]
    raw = bytes.fromhex("6e200a010301010014b2")
    assert p.feed(raw[:4]) == []
    assert p.feed(raw[4:]) == [Event("extended", raw.hex())]
    p = AppClassifier("tx")
    assert p.feed(bytes.fromhex("6e900001ff")) == [Event("version", "0001")]


def test_calendar_and_mattress_alarm_exact_frames():
    now = datetime(2026, 11, 7, 9, 8, 7, tzinfo=UTC)
    req = AlarmRequest("mattress", True, hour=7, minute=30, intensity=2)
    assert alarm_frame(req, now).hex() == "5e010b0102071e0908a3"
    req = AlarmRequest("calendar", True, hour=7, minute=30, slot=2, mode=0x2E, weekdays=(0, 6))
    assert alarm_frame(req, now).hex() == "6e200d0501010200071e2e837a"
    assert len(calendar_clock(now)[0]) == 12
    assert len(calendar_clock(now)[1]) == 13


@pytest.mark.parametrize("remaining", [False, True])
@pytest.mark.parametrize("app", ["wsilver2", "americanstar", "bailey2", "tx"])
async def test_calendar_refresh_removes_deleted_slots_and_keeps_reported_records(delays, remaining, app):
    c = make(app, "amrn")
    records = [
        finalize([0x6E, 0x20, 13, 5, 1, 2, slot, 2, 7, 30, 0x2E, 0x83, 0])
        for slot in (1, 2)
    ]
    for record in records:
        c._apply(Event("extended", record.hex()))
    state = c._coordinator.controller_state
    assert state["row061_calendar_alarm_count"] == 2
    previous = state["row061_calendar_alarms"]
    original = c.write_command
    query_count = 0

    async def write(command, **kwargs):
        nonlocal query_count
        await original(command, **kwargs)
        if command.hex() == "6e2008050100009c":
            query_count += 1
            if query_count == 2 and remaining:
                c._apply(Event("extended", records[1].hex()))

    c.write_command = AsyncMock(side_effect=write)
    await c.row061_alarm(AlarmRequest("calendar", False, delete=True, slot=1))
    assert query_count == 2
    assert frames(c)[-2:] == ["6e2008050201019f", "6e2008050100009c"]
    assert state["row061_calendar_alarm_count"] == int(remaining)
    assert state["row061_calendar_alarms"] == ({2: previous[2]} if remaining else {})
    assert len(previous) == 2


def test_sleep_frames_and_reply_semantics():
    assert sleep_frame(1).hex() == "fa025e01"
    assert sleep_frame(0x14, bytes.fromhex("010301")).hex() == "fa059614010301"
    c = Row061SleepController(coordinator(), app="wsilver2")
    for op, result, key, expected in [
        (1, 1, "left_intervention", "on"),
        (1, 0, "left_intervention", "off"),
        (2, 1, "right_intervention", "on"),
        (3, 2, "mode", "double"),
        (3, 1, "mode", "single"),
    ]:
        c._notify(None, bytearray(sleep_frame(0xA5, bytes([0x14, op, result]))))
        assert c._coordinator.controller_state[f"row061_sleep_{key}"] == expected


async def test_sleep_attributes_ack_before_parse_and_mode_guards(delays):
    c = Row061SleepController(coordinator(), app="wsilver2")
    c._queue_reply = MagicMock()
    c._apply_frame(sleep_frame(0x12, b"{bad"))
    assert c._queue_reply.call_args.args[0] == sleep_frame(0xA5, b"\x12")
    assert c._attributes is None
    with pytest.raises(ValueError):
        await c.set_sleep_option("mode", "double")
    c._apply_frame(sleep_frame(0x12, b'{"SDMode":1,"SDModeSet":1}'))
    with pytest.raises(ValueError):
        await c.set_sleep_option("mode", "double")
    c._apply_frame(sleep_frame(0x12, b'{"SDMode":2,"SDModeSet":2,"LI":1}'))
    c.write_command = AsyncMock()
    await c.set_sleep_option("right_intervention", "on")
    assert c.write_command.call_args.args[0] == sleep_frame(0x14, bytes([1, 2, 1]))


def test_sleep_json_has_exact_raw_rate_and_boolean_meaning():
    c = Row061SleepController(coordinator(), app="tx")
    c._apply_frame(
        sleep_frame(0x11, b'{"Left":{"HD":63,"BD":12,"IsOnBed":1,"IsMove":2},"Right":null}')
    )
    state = c._coordinator.controller_state
    assert state["row061_sleep_left_heart_rate"] == 63
    assert state["row061_sleep_left_breathing_rate"] == 12
    assert state["row061_sleep_left_occupancy"] is True
    assert state["row061_sleep_left_movement"] is False
    assert "row061_sleep_right_heart_rate" not in state


@pytest.mark.parametrize("bed,app", APPS.items())
async def test_factory_selects_real_app_controller(bed, app):
    c = coordinator()

    async def imports(fn, *args):
        return fn(*args)

    c.hass.async_add_import_executor_job = imports
    c.hass.async_add_executor_job = imports
    result = await create_controller(
        c, bed, protocol_variant=f"model_{MODEL_IDS[app][0]}", client=None
    )
    assert isinstance(result, Row061Controller) and result.app == app


def test_restored_normal_mattress_matches_all_accepted_vectors():
    from custom_components.adjustable_bed.beds.richmat_mh_protocol import mattress_frame

    data = json.loads(
        (Path(__file__).parent / "fixtures/row061_normal_mattress_vectors.json").read_text()
    )
    for row in data:
        p = row["inputs"]
        if p["property"] != 11:
            result = mattress_frame(p["side"], p["property"], p["value"])
        else:
            request = AlarmRequest(
                "mattress",
                "cancel" not in p,
                mattress_side="left" if p["side"] == 1 else "right",
                repeat="daily" if p.get("repeat") == 2 else "once",
                intensity=p.get("level", 1),
                hour=p.get("target", [0, 0])[0],
                minute=p.get("target", [0, 0])[1],
            )
            clock = p.get("now", [0, 0])
            result = alarm_frame(request, datetime(2026, 11, 7, *clock, tzinfo=UTC))
        assert result.hex() == row["expected_bytes"]


async def test_verified_intensity_ranges_are_exposed_and_writes_preserve_other_zone(delays):
    for app, expected in [("wsilver2", 8), ("americanstar", 20), ("bailey2", 20), ("tx", 18)]:
        assert sum(len(make(app, m, "0001")._intensities()) for m in MODEL_IDS[app]) == expected
    c = make("wsilver2", "7irm", "0001")
    await c.write_massage_intensity("head", 2)
    await c.write_massage_intensity("foot", 6)
    assert frames(c) == ["6e88a00298", "6e88a032c8"]
    with pytest.raises(ValueError):
        await c.write_massage_intensity("foot", 8)


async def test_tx_legacy_memory_recall_and_save_do_not_alias(delays):
    c = make("tx", "3i")
    assert c.memory_slot_count == 5
    await c.preset_memory(1)
    await c.program_memory(1)
    assert frames(c) == ["6e01002e9d", "6e01006edd", "6e01002b9a", "6e01006edd"]


async def test_normal_pillow_cancellation_uses_its_own_stop():
    c = make("wsilver2", "bfrm_mattress")
    c._normal_ready = True
    c._coordinator.cancel_command.set()
    await c.normal_pillow("right", 1)
    assert frames(c) == ["5e02060066"]


def test_calendar_capability_and_position_gates_are_model_specific():
    for app in ("wsilver2", "americanstar", "bailey2", "tx"):
        model = next(
            m
            for m, p in profiles(app).items()
            if p["fields"].get("hasNewAlarm") and p["fields"].get("alarmList")
        )
        c = make(app, model)
        c._dev = {}  # Weekly alarm attachment does not require the old alarm reply.
        alarm_list = profiles(app)[model]["fields"]["alarmList"]
        assert isinstance(alarm_list, list)
        code = int(str(alarm_list[0]), 16)
        c.validate_row061_alarm(AlarmRequest("calendar", True, mode=code))
        with pytest.raises(ValueError):
            c.validate_row061_alarm(AlarmRequest("calendar", True, mode=0))
    c = make("ruf", "bqrm")
    assert not c.supports_row061_alarms


async def test_alarm_service_schema_and_validation(hass, monkeypatch):
    from homeassistant.core import ServiceCall

    from custom_components.adjustable_bed import row061_services as service

    c = make("wsilver2", "bfrm_mattress")
    c._normal_ready = True

    async def execute(call, capability, label, command, validate):
        assert capability == "supports_row061_alarms"
        validate(c)
        await command(c)

    monkeypatch.setattr(service, "_execute", execute)
    data = service.SCHEMA(
        {"device_id": ["bed"], "family": "mattress", "time": "07:30:00", "mattress_side": "right"}
    )
    await service.handle_alarm(ServiceCall(hass, "adjustable_bed", service.SERVICE, data))
    assert frames(c)[0].startswith("5e020b0101071e")


@pytest.mark.parametrize("app", MODEL_IDS)
@pytest.mark.parametrize("gatt", GATT_MAPS)
@pytest.mark.parametrize("without_response", [False, True])
async def test_each_app_uses_its_reported_gatt_roles_and_advertised_write_mode(
    app, gatt, without_response
):
    c = make(app, MODEL_IDS[app][0])
    write = SimpleNamespace(
        uuid=gatt[1],
        properties=["write-without-response" if without_response else "write"],
        handle=2,
    )
    notify = SimpleNamespace(uuid=gatt[2], properties=["notify"], handle=3)
    c.client.services = [SimpleNamespace(uuid=gatt[0], characteristics=[write, notify])]
    await c.async_discover_capabilities()
    await c.write_command(bytes.fromhex("6e01006edd"))
    assert c.client.write_gatt_char.call_args.args[0] is write
    assert c.client.write_gatt_char.call_args.kwargs["response"] is not without_response
    assert c._notify_chars == [notify]


def test_late_waist_capability_is_published_without_reusing_other_apps_snapshot():
    c = make("ruf", "bqrm")
    c._apply(Event("detection_available"))
    assert c._detection
    assert c._coordinator.remember_richmat_mh_snapshot.called
    assert c.capability_snapshot()["app"] == "ruf"
    other = coordinator()
    other.entry.data = {
        "capabilities": {
            "richmat_mh": {"model": "bfrm", "app": "tx", "version": "0001", "dev": {"led": True}}
        }
    }
    c = Row061Controller(other, app="wsilver2", protocol_variant="model_bfrm")
    assert c.route == "L" and c._light_page() is None


def test_extended_two_zone_intensity_uses_both_reported_values_and_unknown_default():
    c = make("bailey2", "4i", "0002")
    c._extended(bytes.fromhex("6e200b0201000108020600"))
    assert c._intensity == {"head": 1, "foot": 6}
    c._dev["alarm"] = True
    assert c.richmat_mh_alarm_positions  # Map2 owns this version's alarm choices.


@pytest.mark.parametrize("model", ["2i", "3i", "4i"])
def test_normal_mattress_variant_preserves_verified_ver2_bed_controls(model):
    c = make("americanstar", model + "_mattress", "0002")
    assert c.route == "D"
    assert c.motor_control_specs
    assert c.supports_memory_presets
    assert not c._normal_ready


def test_selector_validation_does_not_load_catalog_files(monkeypatch):
    from custom_components.adjustable_bed import row061_profiles

    def blocked(_app):
        pytest.fail("A synchronous setup selector must not read/decompress a catalog")

    monkeypatch.setattr(row061_profiles, "profiles", blocked)
    assert resolve_model("americanstar", "model_2i_mattress", None) == ("2i_mattress", None)
    assert resolve_model("wsilver2", "auto", "6BRM1234") == ("6brm", None)
    assert resolve_model("bailey2", "model_2i_mattress", None)[1] == "unknown_model"


async def test_factory_preloads_only_the_selected_catalog_in_executor(monkeypatch):
    from custom_components.adjustable_bed import row061_profiles
    from tests.test_controller_contract import _FactoryCoordinator

    c = _FactoryCoordinator()
    original = row061_profiles.profiles
    order = []

    def recorded(app):
        order.append(("read", app))
        return original(app)

    async def executor(fn, *args):
        order.append(("executor", args[0]))
        return fn(*args)

    monkeypatch.setattr(row061_profiles, "profiles", recorded)
    c.hass.async_add_executor_job = executor
    result = await create_controller(c, "richmat_americanstar", "model_2i_mattress", None)
    assert isinstance(result, Row061Controller)
    assert order[0:2] == [("executor", "americanstar"), ("read", "americanstar")]
