"""Frozen KONFURT vectors, current-link lifecycle and real Home Assistant ingress."""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson import konfurt as bed
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.profiles import konfurt as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.hold_lease_wire import virtual_clock
from tests.test_somos import Char, written

FIXTURE = Path(__file__).parent / "fixtures/konfurt"
VECTORS = json.loads((FIXTURE / "vectors.json").read_text())
PARSERS = json.loads((FIXTURE / "parser-vectors.json").read_text())
ADDRESS = "AA:BB:CC:DD:0A:27"


def gatt():
    tx, rx = Char(app.WRITE, ["write"], 1), Char(app.NOTIFY, ["notify"], 2)
    return [SimpleNamespace(uuid=uuid, characteristics=[char],
                            get_characteristic=lambda key, char=char: char if char.uuid == key else None)
            for uuid, char in ((app.WRITE_SERVICE, tx), (app.NOTIFY_SERVICE, rx))]


def entry(hass, variant="2", address=ADDRESS):
    from custom_components.adjustable_bed.setup_questions import _konfurt_settings
    e = MockConfigEntry(domain=const.DOMAIN, title="KONFURT", unique_id=address, version=5,
        minor_version=3, data={CONF_ADDRESS: address, CONF_NAME: "KONFURT",
        const.CONF_BED_TYPE: "konfurt", const.CONF_PROTOCOL_VARIANT: variant,
        const.CONF_MOTOR_PULSE_COUNT: 1, const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        **_konfurt_settings({const.CONF_PROTOCOL_VARIANT: variant})})
    e.add_to_hass(hass)
    return e


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_every_frozen_literal_matches_existing_codec(row):
    inputs, expected = row["inputs"], bytes.fromhex(row["expected_bytes"])
    function, sub = inputs["function"], inputs["sub"]
    controls = {1: ("back_up", "back_down"), 2: ("feet_up", "feet_down"),
                4: ("head_up", "head_down"), 5: ("lumbar_up", "lumbar_down")}
    single = {6: "stop", 7: "flat", 8: "anti_snore", 9: "reading", 10: "memory_1",
              11: "zero_g", 12: "tv", 14: "light", 15: "massage_head", 16: "massage_foot",
              17: "massage_wave", 18: "massage", 19: "massage_timer"}
    if function in controls:
        actual = app.frame(controls[function][sub - 1], app.LAYOUTS["4"])
    elif function in single:
        actual = app.frame(single[function], app.LAYOUTS["2"])
    elif sub == 5:
        actual = app.ALARM_QUERY
    elif sub == 4:
        actual = app.alarm(0, 0, 0, 0)
    elif sub == 3:
        actual = app.alarm(*inputs["payload"])
    else:
        actual = codec.clock_fields(inputs["payload"])
    assert actual == expected


@pytest.mark.parametrize("case", PARSERS, ids=lambda row: row["id"])
def test_frozen_parser_sequences(case):
    parser = codec.KonfurtParser()
    for step in case["steps"]:
        result = parser.feed(bytes.fromhex(step["bytes"]))
        expected = step["expected"]
        if expected is None:
            assert result is None
        elif isinstance(result, codec.KonfurtAlarm):
            assert {**asdict(result), "on": result.on} == {k: v for k, v in expected.items() if k != "kind"}
        else:
            assert asdict(result) == {k: v for k, v in expected.items() if k != "kind"}


def test_parser_pending_bypass_replace_short_and_signed():
    p = codec.KonfurtParser()
    first = bytes.fromhex("f4fe000000000000000000060100000000000303")
    p.feed(first)
    assert p.feed(b"\0") is None
    assert p.pending == first
    assert p.feed(bytes.fromhex("ed80ff80ff800100")).hour == -128
    assert p.feed(bytes(16)) is None
    assert p.pending == first
    assert p.feed(bytes.fromhex("0002")).head == 3
    assert p.pending is None
    p.feed(first + b"\0\2")  # Even a complete initial frame must wait for a tail.
    assert p.pending is not None
    p.feed(b"\xf4\xfe")
    assert p.feed(b"\0\0") is None
    assert p.pending is None


@pytest.mark.parametrize("variant", app.LAYOUTS)
async def test_manual_setup_and_offline_factory(hass, variant):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import (
        BED_TYPE_DISPLAY_NAMES,
        detect_bed_type_detailed,
    )
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed
    from tests.test_controller_contract import _FactoryCoordinator
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["konfurt"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    await finish_new_bed(flow, await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: variant}))
    data = flow._finish_with_verify.await_args.args[0]
    assert data[const.CONF_MOTOR_COUNT] == int(variant)
    assert data[const.CONF_HAS_MASSAGE]
    assert data[const.CONF_MOTOR_PULSE_DELAY_MS] == 300
    assert resolve_profile_id(data) == f"konfurt:{variant}"
    c = await create_controller(_FactoryCoordinator(), "konfurt", variant, None)
    assert isinstance(c, bed.KonfurtController)
    assert c.execution.declared == {"hold"}
    assert not c.supports_single_address_pairing and not c.supports_memory_programming
    assert c.supports_preset_reading is (variant == "2")
    assert c.memory_slot_count == 1
    assert c.layout == app.LAYOUTS[variant]
    from tests.test_detection import _make_service_info
    assert detect_bed_type_detailed(_make_service_info(name="KONFURT", service_uuids=[app.WRITE_SERVICE])).bed_type != "konfurt"


async def connected(hass, client, variant="2"):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    e = entry(hass, variant)
    c = AdjustableBedCoordinator(hass, e)
    c._client = client
    c._controller = controller = bed.KonfurtController(c, variant=variant)
    client.services = gatt()
    client.start_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return c, controller


@pytest.mark.parametrize("variant", app.LAYOUTS)
async def test_real_entities_every_held_command_and_alarm_service(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, variant, monkeypatch
):
    mock_bleak_client.services = gatt()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    e = entry(hass, variant)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    c = hass.data[const.DOMAIN][e.entry_id]
    controller = c.controller
    assert isinstance(controller, bed.KonfurtController)
    assert mock_bleak_client.write_gatt_char.await_count == 0  # No invented startup.
    registry = er.async_get(hass)
    entities = [v for v in registry.entities.values() if v.config_entry_id == e.entry_id]
    device = next(v.device_id for v in entities if v.device_id)
    assert len([v for v in entities if v.domain == "cover"]) == int(variant)
    assert not any("program" in v.unique_id for v in entities)
    now = datetime(2026, 11, 27, 16, 21, 22)
    monkeypatch.setattr(bed.dt_util, "now", lambda: now)
    with virtual_clock():
        for control in controller.layout.controls:
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(const.DOMAIN, "hold_control",
                {"device_id": device, "control": control, "duration": .1}, blocking=True)
            assert written(mock_bleak_client) == [app.frame(control, controller.layout).hex(),
                app.frame("stop", controller.layout).hex(), app.frame("stop", controller.layout).hex()]
        # Native buttons, cover, light and massage switch also use the scheduler.
        for domain, suffix, service in (("cover", "_back", "open_cover"),
            ("button", "konfurt_massage_head", "press"), ("button", "preset_flat", "press")):
            target = next(v.entity_id for v in entities if v.domain == domain and v.unique_id.endswith(suffix))
            await hass.services.async_call(domain, service, {"entity_id": target}, blocking=True)
        if variant == "2":
            reading = next(v.entity_id for v in entities if v.unique_id.endswith("preset_reading"))
            await hass.services.async_call("button", "press", {"entity_id": reading}, blocking=True)
        receive = mock_bleak_client.start_notify.call_args.args[1]
        sender = controller._link.notify
        receive(sender, bytearray.fromhex("edfe0000000000050400000000023200"))
        assert c.controller_state[bed.MASSAGE] is True
        assert c.controller_state[UNDER_BED_LIGHTS_ON] is True
        light = next(v.entity_id for v in entities if v.domain == "light")
        massage = next(v.entity_id for v in entities if v.domain == "switch" and v.unique_id.endswith("konfurt_massage"))
        for domain, target in (("light", light), ("switch", massage)):
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(domain, "turn_off", {"entity_id": target}, blocking=True)
            assert len(written(mock_bleak_client)) == 3
        for wake, kind in app.ALARM_TYPES.items():
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(const.DOMAIN, "set_alarm",
                {"device_id": device, "enabled": True, "time": "07:30", "wake_action": wake}, blocking=True)
            assert written(mock_bleak_client) == [codec.clock(now).hex(), app.alarm(7, 30, 32, kind).hex()]
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(const.DOMAIN, "set_alarm", {"device_id": device, "enabled": False}, blocking=True)
        assert written(mock_bleak_client) == [app.alarm(0, 0, 0, 0).hex()]
        query = next(v.entity_id for v in entities if v.unique_id.endswith("konfurt_query_alarm"))
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call("button", "press", {"entity_id": query}, blocking=True)
        assert written(mock_bleak_client) == [app.ALARM_QUERY.hex()] * 2
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(const.DOMAIN, "set_alarm", {"device_id": device,
                "enabled": True, "time": "07:30", "weekdays": ["monday"]}, blocking=True)
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("change", ["cancel", "reconnect", "replace"])
async def test_held_cleanup_cannot_retarget(hass, mock_bleak_client, change):
    coordinator, c = await connected(hass, mock_bleak_client)
    events = []
    async def write(_char, data, **_kwargs):
        events.append(bytes(data))
        if len(events) == 1:
            if change == "cancel":
                coordinator.cancel_command.set()
            elif change == "reconnect":
                c.on_disconnect()
                await c.async_discover_capabilities()
            else:
                coordinator._controller = None
    mock_bleak_client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises((asyncio.CancelledError, ConnectionError)):
        await c.hold_control("back_up", 1000)
    assert events[0] == app.frame("back_up", c.layout)
    assert events[1:] == ([app.frame("stop", c.layout)] * 2 if change == "cancel" else [])


async def test_old_notifications_clear_pending_on_reconnect(hass, mock_bleak_client):
    coordinator, c = await connected(hass, mock_bleak_client)
    old = mock_bleak_client.start_notify.call_args.args[1]
    sender = c._link.notify
    old(sender, bytearray.fromhex("f4fe000000000000000000060100000000000303"))
    c.on_disconnect()
    await c.async_discover_capabilities()
    await c.start_notify()
    fresh = mock_bleak_client.start_notify.call_args.args[1]
    old(sender, bytearray.fromhex("edfe0000000000050400000000023200"))
    fresh(c._link.notify, bytearray.fromhex("0002"))
    assert coordinator.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    assert c._parser.pending is None


async def test_new_report_beats_sent_state_and_no_delivery_is_unknown(hass, mock_bleak_client):
    coordinator, c = await connected(hass, mock_bleak_client)
    receive = mock_bleak_client.start_notify.call_args.args[1]
    packet = bytearray.fromhex("edfe0000000000050400000000023200")
    receive(c._link.notify, packet)
    async def newer(_char, _data, **_kwargs):
        receive(c._link.notify, packet)
    mock_bleak_client.write_gatt_char.side_effect = newer
    with virtual_clock():
        await c.lights_off()
    assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True
    c.invalidate_diagnostics()
    with pytest.raises(ServiceValidationError):
        await c.set_massage(False)


async def test_paired_hold_preflights_both_layouts_before_either_write(hass, monkeypatch):
    from functools import partial

    from custom_components.adjustable_bed import services
    from tests.test_controller_contract import _FactoryCoordinator
    from tests.test_paired_coordinator import _pair
    pair, left, right = _pair([])
    controls = []
    for child, layout in ((left, "4"), (right, "2")):
        controller = bed.KonfurtController(_FactoryCoordinator(), variant=layout)
        controls.append(controller)
        controller.hold_control = AsyncMock()
        monkeypatch.setattr(child, "capability_controller", controller, raising=False)
        async def execute(ctrl, command, **kwargs):
            await command(ctrl)
        monkeypatch.setattr(child, "async_execute_controller_command", partial(execute, controller))
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(pair, const.SIDE_BOTH)], []))
    await services.async_register_services(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(const.DOMAIN, "hold_control",
            {"device_id": "pair", "control": "lumbar_up", "duration": .1}, blocking=True)
    assert all(not c.hold_control.called for c in controls)


async def test_public_offline_actions_do_not_bypass_connection_admission(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch
):
    from custom_components.adjustable_bed.runtime_data import loaded_runtime
    mock_bleak_client.services = gatt()
    mock_bleak_client.write_gatt_char = AsyncMock()
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    coordinator = loaded_runtime(hass, e.entry_id)
    entities = [v for v in er.async_get(hass).entities.values() if v.config_entry_id == e.entry_id]
    cover = next(v for v in entities if v.domain == "cover")
    coordinator._client = None
    coordinator._controller = None
    monkeypatch.setattr(coordinator, "async_ensure_connected", AsyncMock(return_value=False))
    mock_bleak_client.write_gatt_char.reset_mock()
    for service, data in (("hold_control", {"control": "back_up", "duration": .1}),
                          ("set_alarm", {"enabled": True, "time": "07:30"})):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(const.DOMAIN, service,
                {"device_id": cover.device_id, **data}, blocking=True)
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_release_absolute_offsets_and_gatt_mode(hass, mock_bleak_client):
    _, c = await connected(hass, mock_bleak_client)
    writes = []
    with virtual_clock() as clock:
        async def record(_char, data, **kwargs):
            writes.append((round(clock.now * 1000), bytes(data), kwargs["response"]))
            await asyncio.sleep(.020)
        mock_bleak_client.write_gatt_char.side_effect = record
        await c.hold_control("back_up", 650)
    assert [at for at, _, _ in writes] == [0, 300, 600, 950, 1250]
    assert all(response for _, _, response in writes)
    mock_bleak_client.services[0].characteristics[0].properties = ["write-without-response"]
    assert bed.select_link(mock_bleak_client).response is False
    mock_bleak_client.services[1].characteristics[0].properties = ["read"]
    with pytest.raises(ConnectionError):
        bed.select_link(mock_bleak_client)


@pytest.mark.parametrize("valid", [True, False])
async def test_setup_probe_checks_exact_roles(hass, monkeypatch, mock_bleak_client, valid):
    from custom_components.adjustable_bed import config_flow
    from tests.test_config_flow import _fresh_gate
    client = mock_bleak_client
    client.services = gatt()
    if not valid:
        client.services[1].uuid = app.WRITE_SERVICE
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    freshness, device = _fresh_gate("hci0", -55)
    monkeypatch.setattr(config_flow, "async_gate_connection", lambda *a, **kw: (freshness, device))
    monkeypatch.setattr("bleak_retry_connector.establish_connection", AsyncMock(return_value=client))
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    info = AsyncMock()
    monkeypatch.setattr(config_flow, "read_ble_device_info", info)
    report = await flow._probe_capabilities(ADDRESS, "auto", "konfurt", "3")
    assert report.connected is valid
    assert report.konfurt_transport_valid is valid
    assert bool(report.error) is not valid
    info.assert_not_awaited()
    client.write_gatt_char.assert_not_called()
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("cause", ["cancel", "reconnect"])
async def test_alarm_sequence_cannot_resume_on_new_session(hass, mock_bleak_client, cause):
    from custom_components.adjustable_bed.alarm import AlarmRequest
    coordinator, c = await connected(hass, mock_bleak_client)
    async def clock_written(_char, _data, **_kwargs):
        if cause == "cancel":
            coordinator.cancel_command.set()
        else:
            await c.async_discover_capabilities()
    mock_bleak_client.write_gatt_char.side_effect = clock_written
    with virtual_clock(), pytest.raises((asyncio.CancelledError, ConnectionError)):
        await c.configure_alarm(AlarmRequest(enabled=True, hour=7, minute=30, reference_time=datetime(2026, 11, 27, 16, 21, 22)))
    assert len(written(mock_bleak_client)) == 1
    assert bytes(mock_bleak_client.write_gatt_char.call_args.args[1]).startswith(b"\xe7\x80\x01")
