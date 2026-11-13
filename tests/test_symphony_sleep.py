"""Row078: frozen literals, all 15 routes and the real HA command lifecycle."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.keeson import symphony_sleep as ctrl
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.codec import okin_nframe
from custom_components.adjustable_bed.const import (
    BED_TYPE_SYMPHONY_SLEEP,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
from custom_components.adjustable_bed.profiles import symphony_sleep as app
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator

VECTORS = json.loads((Path(__file__).parent / "fixtures/symphony_sleep/vectors.json").read_text())
ADDRESS = "AA:BB:CC:DD:00:78"
FUNCTIONS = {1: (1, 2), 2: (4, 8), 3: (5, 10), 4: (16, 32), 5: (64, 128)}
WORDS = {6: 0, 7: app.PRESETS["flat"], 8: app.PRESETS["anti_snore"],
         9: app.MEMORY[1], 12: app.MEMORY[2], 11: app.PRESETS["zero_g"], 14: app.LIGHT}


@pytest.mark.parametrize("row", VECTORS["builders"], ids=lambda r: r["id"])
def test_all_relevant_frozen_final_literals(row):
    route = "box1" if row["protocol"] == "P1" else "box2"
    fields = row["inputs"]
    f, s = fields["function"], fields["subfunction"]
    if f in FUNCTIONS:
        word = FUNCTIONS[f][s != 1]
        actual = app.normal(route, word)
    elif f in WORDS:
        actual = app.normal(route, WORDS[f])
    elif f in (17, 18, 19, 20):
        key = {(17, 8): "massage_wave_next", (17, 9): "massage_wave_previous",
               (18, 4): "massage_off", (19, 0): "massage_timer",
               (20, 8): "massage_intensity_up", (20, 9): "massage_intensity_down"}.get((f, s))
        actual = app.normal(route, app.MASSAGE[key]) if key else okin_nframe.request(0xB0)
    elif f == 55:
        now = datetime.fromisoformat(fields["now"]) if route == "box2" else datetime(2026, 11, 12, 6, 45, 59)
        actual = app.clock(route, now)
    elif s not in (3, 4):
        actual = app.alarm_query(route)
    else:
        hour, minute, _, wake = fields.get("params", (0, 0, 0, 0))
        actual = app.alarm(route, enabled=s == 3, hour=hour, minute=minute,
                           wake={17: "memory_1", 19: "memory_2"}.get(wake, "none"))
    assert actual.hex() == row["expected_bytes"]
    if actual[:2] == b"\x05\x02":
        assert actual == okin_nframe.frame40(int.from_bytes(actual[2:6], "big"))


@pytest.mark.parametrize("group", VECTORS["parsers"], ids=lambda r: r["id"])
def test_frozen_parser_semantics_and_safe_failures(group):
    parser = codec.SymphonyParser(p2=group["steps"][0]["box"] == 2)
    for step in group["steps"]:
        result = None if step["box"] == -1 else parser.feed(bytes.fromhex(step["input_hex"]), step.get("current_minutes", 0))
        if "expected_error" in step or step.get("expected") is None:
            assert result is None
        elif "massage_minutes" in step["expected"]:
            assert result == codec.SymphonyTimer(step["expected"]["massage_minutes"])
        else:
            expected = step["expected"]
            assert result == codec.SymphonyAlarm(expected["alarm_enabled"], expected["hour"], expected["minute"],
                {"MA": "memory_1", "MB": "memory_2", "NONE": "none"}[expected["wake"]])


def test_parser_fragment_bounds_consumption_and_comparison_quirk():
    parser = codec.SymphonyParser(p2=False)
    prefix = bytes.fromhex("f4fe") + bytes(14)
    assert parser.feed(prefix) is None
    assert parser.feed(bytes(3)) is None  # Must actually reach offset 19.
    assert parser.feed(bytes(5)) is None  # Prefix consumed, no stale replay.
    assert parser.feed(prefix) is None
    assert parser.feed(bytes(15)) is None  # Fixed 30-byte buffer overflow.
    assert parser.feed(prefix) is None
    assert parser.feed(bytes.fromhex("e7fe") + bytes(6) + b"\x02\x00", 2) == codec.SymphonyTimer(2)
    assert parser.feed(bytes(5)) is None  # A complete reply invalidates the prefix.
    for length in range(7):
        assert parser.feed((b"\xed\x80\x03" + bytes(13))[:length]) is None
    for raw in (b"\xed\x80\x03\xff\x00\xff\x11", b"\xed\x80\x03" + bytes(14)):
        assert parser.feed(raw) is None
    assert parser.feed(b"\xf4\xfe" + bytes(17)) is None
    assert parser.feed(b"\x03") == codec.SymphonyTimer(30)
    p2 = codec.SymphonyParser(p2=True)
    for length in range(10):
        assert p2.feed((b"\0\x0c" + bytes(8))[:length]) is None
    assert p2.feed(bytes.fromhex("000c0000000224990001")) is None


@pytest.mark.parametrize("model", app.MODELS)
@pytest.mark.parametrize("route", app.PROFILES)
async def test_complete_matrix_setup_factory_restore_and_side_ownership(model, route):
    coordinator = _FactoryCoordinator()
    data = {CONF_BED_TYPE: BED_TYPE_SYMPHONY_SLEEP, CONF_PRODUCT_TYPE: model, CONF_PROTOCOL_VARIANT: route}
    coordinator.entry.data.update(data)
    profile = setup_profile_for(data)
    assert profile.validate is not None and profile.derive is not None
    assert profile.validate(data) == {}
    assert profile.derive(data)[CONF_HAS_MASSAGE] == app.MODELS[model].accessories
    assert profile.derive(data)[CONF_MOTOR_COUNT] == 2  # Never gates the model's UI.
    c = await create_controller(coordinator, BED_TYPE_SYMPHONY_SLEEP, route, None)
    assert isinstance(c, ctrl.SymphonySleepController)
    assert tuple(s.key for s in c.motor_control_specs) == app.MODELS[model].axes
    assert all(s.scheduler_resource == "*" for s in c.motor_control_specs)
    assert c.supports_massage == c.supports_lights == app.MODELS[model].accessories
    assert c.memory_slot_names == ("Memory A", "Memory B") and c.supports_memory_programming
    assert not c.supports_single_address_pairing and not c.supports_position_feedback
    assert not c.supports_massage_toggle_control and not c.supports_massage_intensity_preset_control
    assert not c.supports_head_massage_intensity_step_control and not c.supports_foot_massage_intensity_step_control
    assert c.supports_massage_wave_direction_control == app.MODELS[model].accessories
    assert c.execution.hold == "stream" and not c.execution.concurrent
    assert CONF_PRODUCT_TYPE in per_side_profile(BED_TYPE_SYMPHONY_SLEEP, route).keys
    assert per_side_profile(BED_TYPE_SYMPHONY_SLEEP, route).variant_owned
    assert "Symphony Sleep" in BED_TYPE_DISPLAY_NAMES[BED_TYPE_SYMPHONY_SLEEP]
    for bad in ({CONF_PRODUCT_TYPE: "400"}, {CONF_PROTOCOL_VARIANT: "auto"}):
        assert profile.validate({**data, **bad})


class Char:
    def __init__(self, **fields):
        self.__dict__.update(fields)



class Services(list):
    def get_service(self, uuid):
        return next((s for s in self if s.uuid == uuid), None)

    def get_characteristic(self, uuid):
        return next((c for s in self for c in s.characteristics if c.uuid == uuid), None)


def gatt(route, properties=("write",)):
    transport = codec.TRANSPORTS[app.PROFILES[route].transport]
    def service(uuid, char_uuid, props):
        char = Char(uuid=char_uuid, properties=list(props), handle=1 if "write" in props or "write-without-response" in props else 2, descriptors=[])
        return SimpleNamespace(uuid=uuid, characteristics=[char], get_characteristic=lambda key: char if key == char.uuid else None)
    if route == "box2":
        s = service(transport.service_uuid, transport.write_uuid, properties)
        n = service(transport.service_uuid, transport.notify_uuid, ("notify",))
        s.characteristics.extend(n.characteristics)
        s.get_characteristic = lambda key: next((c for c in s.characteristics if c.uuid == key), None)
        return Services([s])
    return Services([service(transport.service_uuid, transport.write_uuid, properties),
                     service(codec.JALON_NOTIFY_SERVICE, transport.notify_uuid, ("notify",))])


def entry(hass, model="600E", route="box1", address=ADDRESS):
    e = MockConfigEntry(domain=DOMAIN, title="Symphony Sleep", unique_id=address, data={
        CONF_ADDRESS: address, CONF_NAME: "Symphony Sleep", CONF_BED_TYPE: BED_TYPE_SYMPHONY_SLEEP,
        CONF_PRODUCT_TYPE: model, CONF_PROTOCOL_VARIANT: route, CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: model != "400E", CONF_DISABLE_ANGLE_SENSING: True,
    })
    e.add_to_hass(hass)
    return e


async def connected(hass, client, route="box1", model="600E"):
    client.services = gatt(route)
    coordinator = AdjustableBedCoordinator(hass, entry(hass, model, route))
    await coordinator.async_connect()
    assert isinstance(coordinator.controller, ctrl.SymphonySleepController)
    client.write_gatt_char.reset_mock()
    return coordinator


def frames(client):
    return [bytes(c.args[1]).hex() for c in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("route", app.PROFILES)
async def test_actual_coordinator_cancel_cleanup_and_next_gesture(hass, mock_coordinator_connected, mock_bleak_client, route):
    c = await connected(hass, mock_bleak_client, route)
    events = []
    async def record(char, frame, **kwargs):
        events.append((asyncio.get_running_loop().time(), frame.hex()))
    mock_bleak_client.write_gatt_char.side_effect = record
    stop = app.normal(route, 0).hex()
    with virtual_clock():
        task = asyncio.create_task(c.async_execute_controller_command(lambda bed: bed.hold_control("head_up", 2000)))
        await asyncio.sleep(0.35)
        await c.async_stop_command()
        await asyncio.gather(task, return_exceptions=True)
        boundary = len(events)
        await c.async_execute_controller_command(lambda bed: bed.hold_control("feet_down", 650))
    tail = events[boundary:]
    assert [f for _, f in tail] == [app.normal(route, 8).hex()] * 3 + [stop] * 3
    assert [round((t-tail[-3][0])*1000) for t, _ in tail[-3:]] == [0, 300, 600]
    await c.async_disconnect()


@pytest.mark.parametrize("route", ("box1", "box2"))
async def test_queries_survive_gesture_end_but_never_reconnect(hass, mock_coordinator_connected, mock_bleak_client, route):
    c = await connected(hass, mock_bleak_client, route)
    bed = c.controller
    with virtual_clock():
        await c.async_execute_controller_command(lambda b: b.hold_control("massage_intensity_down", 50))
        if route == "box2":
            assert frames(mock_bleak_client).count("00b0") == 2
        else:
            assert set(frames(mock_bleak_client)) == {app.normal(route, 0x1800000).hex(), app.normal(route, 0).hex()}
        await bed.query_alarm()
        bed.on_disconnect()
        boundary = len(frames(mock_bleak_client))
        await asyncio.sleep(1)
        assert len(frames(mock_bleak_client)) == boundary
    await c.async_disconnect()


@pytest.mark.parametrize("route", app.PROFILES)
async def test_session_parser_and_recreated_controller_owns_publisher(hass, mock_coordinator_connected, mock_bleak_client, route):
    c = await connected(hass, mock_bleak_client, route)
    bed = c.controller
    link = bed._link
    timer = bytes.fromhex("000b000003") if route == "box2" else bytes.fromhex("e7fe0000000000000200")
    bed._notification(link, link.notify, bytearray(timer))
    if route != "fallback":
        assert c.controller_state[ctrl.TIMER] == 20
    replacement = ctrl.SymphonySleepController(c)
    assert replacement._app_state is bed._app_state
    await replacement.start_notify()
    replacement._notification(replacement._link, replacement._link.notify, bytearray(timer))
    bed.on_disconnect()
    bed._notification(link, link.notify, bytearray.fromhex("e7fe000000000000ff00"))
    if route != "fallback":
        assert c.controller_state[ctrl.TIMER] == 20
    await replacement.stop_notify()
    await c.async_disconnect()


@pytest.mark.parametrize("model", app.MODELS)
async def test_actual_entities_card_and_alarm_action(hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch, model):
    mock_bleak_client.services = gatt("box2")
    e = entry(hass, model, "box2")
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    def entity(domain, key):
        return registry.async_get_entity_id(domain, DOMAIN, f"{ADDRESS}_{key}")
    for axis in app.MODELS[model].axes:
        state = hass.states.get(entity("cover", axis))
        assert state.attributes["hold_lease_mode"] == "stream"
        assert state.attributes["held_stop_scope"] == "side"
    assert bool(entity("button", "massage_wave_next")) == (model != "400E")
    assert bool(entity("button", "toggle_light")) == (model != "400E")
    assert entity("button", "program_memory_1") and entity("button", "program_memory_2")
    assert not entity("switch", "under_bed_lights")
    if model != "400E":
        for key, held in (("massage_all_up", "massage_intensity_up"), ("massage_all_down", "massage_intensity_down"), ("massage_all_off", "massage_off")):
            state = hass.states.get(entity("button", key))
            assert state.attributes["held_control"] == held
            assert state.attributes["card_section"] == "massage"
    dev = next(x.device_id for x in registry.entities.values() if x.config_entry_id == e.entry_id)
    monkeypatch.setattr(ctrl.dt_util, "now", lambda: datetime(2026, 11, 12, 6, 45, 59))
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(DOMAIN, "symphony_set_alarm", {"device_id": dev, "enabled": True, "time": "23:59:00", "wake_mode": "memory_2"}, blocking=True)
        await asyncio.sleep(0.6)
    assert frames(mock_bleak_client) == ["070426111204064559", "0705ff032359000100", "00c0", "00c0"]
    for bad in ({"enabled": True}, {"enabled": True, "time": "12:00:01"}, {"enabled": True, "time": "12:00:00", "wake_mode": "massage"}):
        mock_bleak_client.write_gatt_char.reset_mock()
        with pytest.raises((ServiceValidationError, vol.Invalid)):
            await hass.services.async_call(DOMAIN, "symphony_set_alarm", {"device_id": dev, **bad}, blocking=True)
        assert not frames(mock_bleak_client)
    assert await hass.config_entries.async_unload(e.entry_id)


async def setup_entities(hass, client, route):
    client.services = gatt(route)
    e = entry(hass, "SS600", route)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    dev = next(x.device_id for x in registry.entities.values() if x.config_entry_id == e.entry_id)
    client.write_gatt_char.reset_mock()
    return e, hass.data[DOMAIN][e.entry_id], dev


@pytest.mark.parametrize("route", app.PROFILES)
@pytest.mark.parametrize("ack_s", (0, 0.45))
async def test_registered_timed_move_obeys_elapsed_deadline_with_fast_and_slow_ack(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, route, ack_s
):
    e, c, dev = await setup_entities(hass, mock_bleak_client, route)
    events = []
    async def write(char, frame, **kwargs):
        events.append((asyncio.get_running_loop().time(), frame.hex()))
        await asyncio.sleep(ack_s)
    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock():
        start = asyncio.get_running_loop().time()
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": dev, "motor": "lumbar", "direction": "up", "duration_ms": 650,
        }, blocking=True)
    stop = app.normal(route, 0).hex()
    moving = [(t-start, f) for t, f in events if f != stop]
    release = [(t-start, f) for t, f in events if f == stop]
    assert moving and all(t < 0.65 for t, _ in moving)
    assert all(f == app.normal(route, 16).hex() for _, f in moving)
    assert 0.65 - 0.001 <= release[0][0] <= 0.65 + ack_s + 0.001
    assert len(release) == 3
    assert not c._command_lock.locked()
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("service", ("timed_move", "hold_control"))
async def test_actual_registered_card_lease_renewal_and_cover_stop(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, service
):
    e, c, dev = await setup_entities(hass, mock_bleak_client, "box2")
    c._motor_pulse_count = 1
    data = {"device_id": dev, "hold_owner": "card", "hold_generation": 1,
            **({"motor": "lumbar", "direction": "up", "duration_ms": 200} if service == "timed_move"
               else {"control": "memory_1", "duration": 0.2})}
    async def renew():
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    stop = app.normal("box2", 0).hex()
    with virtual_clock():
        task = asyncio.create_task(renew())
        for _ in range(6):
            await asyncio.sleep(0.1)
            await renew()
            assert stop not in frames(mock_bleak_client)
        cover = er.async_get(hass).async_get_entity_id("cover", DOMAIN, f"{ADDRESS}_lumbar")
        await hass.services.async_call("cover", "stop_cover", {"entity_id": cover}, blocking=True)
        await task
        count = len(frames(mock_bleak_client))
        # A late renewal never resurrects this ended generation.
        with pytest.raises(ServiceValidationError, match="has ended"):
            await renew()
        assert len(frames(mock_bleak_client)) == count
        await hass.services.async_call(DOMAIN, "hold_control", {
            "device_id": dev, "control": "feet_down", "duration": 0.65,
        }, blocking=True)
    after = frames(mock_bleak_client)[count:]
    assert after == [app.normal("box2", 8).hex()] * 3 + [stop] * 3
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_program_memory_uses_same_source_stream_for_5200ms(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await connected(hass, mock_bleak_client)
    times = []
    async def record(char, frame, **kwargs):
        times.append((asyncio.get_running_loop().time(), frame.hex()))
    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        start = asyncio.get_running_loop().time()
        await c.async_execute_controller_command(lambda b: b.program_memory(2))
    stop = app.normal("box1", 0).hex()
    assert all(f == app.normal("box1", 0x4000).hex() for _, f in times[:-3])
    assert len(times[:-3]) == 18
    assert round((times[-3][0]-start)*1000) == 5200
    assert [f for _, f in times[-3:]] == [stop] * 3
    await c.async_disconnect()


async def test_live_gatt_admission_and_stale_captured_cleanup(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await connected(hass, mock_bleak_client)
    bed = c.controller
    old = bed._link
    old.write.properties = ["read"]
    with pytest.raises(ConnectionError):
        await c.async_execute_controller_command(lambda b: b.preset_flat())
    assert not frames(mock_bleak_client)
    mock_bleak_client.services = gatt("box1", ("write-without-response",))
    await bed.async_discover_capabilities()
    with virtual_clock():
        await bed.hold_control("head_up", 1)
    assert all(call.kwargs["response"] is False for call in mock_bleak_client.write_gatt_char.call_args_list)
    boundary = len(frames(mock_bleak_client))
    with virtual_clock(), pytest.raises(ConnectionError):
        await bed._release(old)
    assert len(frames(mock_bleak_client)) == boundary
    await c.async_disconnect()


async def test_explicit_picker_and_saved_setup_roundtrip(hass, enable_custom_integrations, monkeypatch):
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import complete, form_fields
    from tests.test_setup_routes import _typed

    result = await _typed(hass, BED_TYPE_SYMPHONY_SLEEP)
    assert result["step_id"] == "profile_questions"
    assert {CONF_PRODUCT_TYPE, CONF_PROTOCOL_VARIANT} <= {str(m.schema) for m in form_fields(result["data_schema"])}
    monkeypatch.setattr(AdjustableBedConfigFlow, "_verification_possible", lambda self: False)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        CONF_PRODUCT_TYPE: "SS600", CONF_PROTOCOL_VARIANT: "fallback",
    })
    result = await complete(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    saved = result["data"]
    assert saved[CONF_PRODUCT_TYPE] == "SS600" and saved[CONF_PROTOCOL_VARIANT] == "fallback"
    assert saved[CONF_MOTOR_COUNT] == 2 and saved[CONF_HAS_MASSAGE] is True
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize("service", ("symphony_set_alarm", "sync_clock"))
async def test_family_alarm_all_targets_validated_before_requested_writes_and_later_stop_wins(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch, service
):
    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.beds.keeson.symphony_services import (
        register_symphony_services,
    )
    first = await connected(hass, mock_bleak_client)
    other_entry = entry(hass, "400E", "box1", "AA:BB:CC:DD:00:79")
    second = AdjustableBedCoordinator(hass, other_entry)
    # Independent schedulers/physical addresses, with the fixture's one simulated transport.
    await second.async_connect()
    register_symphony_services(hass)
    await services.async_register_services(hass)
    data = {"enabled": True, "time": "06:00:00"} if service == "symphony_set_alarm" else {}
    devices = [dr.async_get(hass).async_get_or_create(config_entry_id=c.entry.entry_id, identifiers={(DOMAIN, c.address)}).id
               for c in (first, second)]
    monkeypatch.setattr("custom_components.adjustable_bed.beds.keeson.symphony_services._call_targets", lambda call: [(first, "both"), (second, "both")])
    monkeypatch.setattr(services, "_call_targets", lambda call: [(first, "both"), (second, "both")])
    mock_bleak_client.write_gatt_char.reset_mock()
    original_live = second.controller._live
    second.controller._live = MagicMock(side_effect=ConnectionError("invalid later GATT"))
    with pytest.raises(ServiceValidationError, match="invalid later GATT"):
        await hass.services.async_call(DOMAIN, service, {"device_id": devices, **data}, blocking=True)
    assert not frames(mock_bleak_client)
    second.controller._live = original_live
    original_send = first.controller._send
    stopped = False
    async def stop_later(link, packet, event):
        nonlocal stopped
        if not stopped:
            stopped = True
            await second.async_stop_command()
        await original_send(link, packet, event)
    monkeypatch.setattr(first.controller, "_send", stop_later)
    with virtual_clock():
        await hass.services.async_call(DOMAIN, service, {"device_id": devices, **data}, blocking=True)
    alarm = app.alarm("box1", enabled=True, hour=6, minute=0, wake="none").hex()
    if service == "symphony_set_alarm":
        assert frames(mock_bleak_client).count(alarm) == 1
    else:
        assert sum(frame.startswith("e78001") for frame in frames(mock_bleak_client)) == 1
    await first.async_disconnect()
    await second.async_disconnect()


async def test_alarm_delays_start_at_action_instead_of_after_slow_ack(
    hass, mock_coordinator_connected, mock_bleak_client
):
    c = await connected(hass, mock_bleak_client, "box2")
    writes = []
    async def slow_write(char, packet, **kwargs):
        writes.append((asyncio.get_running_loop().time(), packet.hex()))
        await asyncio.sleep(0.45)
    mock_bleak_client.write_gatt_char.side_effect = slow_write
    with virtual_clock():
        started = asyncio.get_running_loop().time()
        await c.async_execute_controller_command(lambda bed: bed.configure_clock_alarm(
            enabled=True, weekdays=(), hour=6, minute=45, preset="none"))
        await asyncio.sleep(1)
    assert [round((t-started)*1000) for t, _ in writes] == [0, 450, 900, 1350]
    assert [packet for _, packet in writes[2:]] == ["00c0", "00c0"]
    await c.async_disconnect()
